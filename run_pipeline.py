"""
run_pipeline.py
----------------
Production çalıştırması: run_test.py'nin aksine TEK bir --line-id almaz,
Supabase'deki `power_lines` tablosundaki TÜM hatları otomatik işler.

Akış:
  1. get_active_power_lines() ile tüm hatları (+ hazır corridor geometrisini) çek
  2. Her hat için Sentinel Hub Statistical API'den NDVI zaman serisini çek
  3. Yanıtı ayrıştır
  4. ndvi_measurements tablosuna yaz (upsert — aynı hat+tarih tekrar gelirse günceller)

Bir hat için hata oluşursa (API zaman aşımı, geçici 5xx, vb.) pipeline
DURMAZ — hatayı loglar, bir sonraki hatta devam eder. Çalıştırma sonunda
kaç hattın başarılı/başarısız olduğunu özetler ve en az bir hata varsa
exit code 1 ile çıkar (cron/CI'da "başarısız" olarak işaretlenmesi için).

Kullanım:
    python run_pipeline.py                    # tüm hatları, varsayılan 6 ay geriye dönük işler
    python run_pipeline.py --months-back 3
    python run_pipeline.py --log-file pipeline.log

ÖNEMLİ: Çalıştırmadan önce:
  - .env dosyasında (veya CI/CD secrets'ta) SENTINEL_HUB_CLIENT_ID / SECRET
    ve SUPABASE_URL / KEY dolu olmalı
  - `supabase_rpc_get_power_lines.sql` Supabase'de bir kez çalıştırılmış olmalı
  - `supabase_rpc_insert_ndvi.sql` ve `supabase_add_unique_constraint.sql`
    da bir kez çalıştırılmış olmalı (bkz. README)
"""

import argparse
import logging
import sys
from datetime import datetime, timedelta, timezone

from sentinel_api import fetch_ndvi_statistics, parse_statistics_response

logger = logging.getLogger("ndvi_pipeline")


def setup_logging(log_file: str | None):
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
    )


def process_line(line: dict, date_from_str: str, date_to_str: str) -> int:
    """Tek bir hat için NDVI çek + yaz. Yazılan kayıt sayısını döner."""
    from db import insert_ndvi_measurements  # gecikmeli import (dry-run senaryolarını kolaylaştırır)

    line_id = line["line_id"]
    line_name = line.get("line_name") or line_id

    raw_response = fetch_ndvi_statistics(
        corridor_geojson=line["corridor_geojson"],
        date_from=date_from_str,
        date_to=date_to_str,
    )
    records = parse_statistics_response(raw_response)
    logger.info("  [%s] %d NDVI kaydı ayrıştırıldı.", line_name, len(records))

    inserted = insert_ndvi_measurements(
        line_id=line_id,
        corridor_wkt=line["corridor_wkt"],
        records=records,
    )
    return inserted


def main():
    parser = argparse.ArgumentParser(description="YEDAŞ NDVI production pipeline (tüm hatlar)")
    parser.add_argument("--months-back", type=int, default=6,
                         help="Kaç ay geriye dönük veri çekilsin")
    parser.add_argument("--log-file", type=str, default=None,
                         help="Konsola ek olarak loglanacak dosya yolu (örn. pipeline.log)")
    args = parser.parse_args()

    setup_logging(args.log_file)

    from db import get_active_power_lines  # gecikmeli import

    date_to = datetime.now(timezone.utc)
    date_from = date_to - timedelta(days=30 * args.months_back)
    date_from_str = date_from.strftime("%Y-%m-%dT00:00:00Z")
    date_to_str = date_to.strftime("%Y-%m-%dT00:00:00Z")

    logger.info("NDVI pipeline başlıyor. Tarih aralığı: %s -> %s", date_from_str, date_to_str)

    lines = get_active_power_lines()
    logger.info("Supabase'den %d hat alındı.", len(lines))

    if not lines:
        logger.warning("İşlenecek hat bulunamadı. power_lines tablosu boş olabilir "
                        "ya da get_active_power_lines RPC'si henüz kurulmamış olabilir.")
        sys.exit(0)

    success_count = 0
    failure_count = 0
    total_inserted = 0

    for line in lines:
        line_name = line.get("line_name") or line["line_id"]
        logger.info("İşleniyor: %s (id=%s)", line_name, line["line_id"])
        try:
            inserted = process_line(line, date_from_str, date_to_str)
            total_inserted += inserted
            success_count += 1
            logger.info("  [OK] %s: %d satır yazıldı.", line_name, inserted)
        except Exception as e:
            failure_count += 1
            logger.error("  [HATA] %s işlenirken sorun oluştu: %s", line_name, e, exc_info=True)
            continue

    logger.info(
        "Pipeline tamamlandı. Başarılı: %d, Başarısız: %d, Toplam yazılan satır: %d",
        success_count, failure_count, total_inserted,
    )

    if failure_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
