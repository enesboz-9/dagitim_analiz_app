"""
run_test.py
-----------
Uçtan uca test çalıştırması:
  1. Test koridoru polygonunu oluştur (geometry.py)
  2. Sentinel Hub Statistical API'den NDVI zaman serisini çek (sentinel_api.py)
  3. Yanıtı ayrıştır (sentinel_api.py)
  4. ndvi_measurements tablosuna yaz (db.py)

Kullanım:
    python run_test.py --dry-run          # API/DB'ye gerçekten dokunmadan, sadece
                                            # koridoru üretip request body'sini yazdırır
    python run_test.py --line-id <uuid>   # gerçek çalıştırma, power_lines tablosundaki
                                            # ilgili satırın UUID'si ile

ÖNEMLİ: --dry-run olmadan çalıştırmadan önce:
  - .env dosyasında SENTINEL_HUB_CLIENT_ID / SECRET ve SUPABASE_URL / KEY dolu olmalı
  - power_lines tablosunda test için bir satır oluşturulmuş ve UUID'si alınmış olmalı
  - db.py içindeki PostGIS/RPC notunu okuyup segment_geom yazma yöntemine karar vermiş olmalısın
"""

import argparse
import json
from datetime import datetime, timedelta, timezone

from geometry import build_test_corridor
from sentinel_api import fetch_ndvi_statistics, parse_statistics_response


def main():
    parser = argparse.ArgumentParser(description="YEDAŞ NDVI test pipeline")
    parser.add_argument("--dry-run", action="store_true",
                         help="Gerçek API/DB çağrısı yapmadan sadece koridoru ve isteği göster")
    parser.add_argument("--line-id", type=str, default=None,
                         help="power_lines tablosundaki test hattının UUID'si (dry-run değilse zorunlu)")
    parser.add_argument("--buffer-meters", type=float, default=20.0,
                         help="Emniyet mesafesi zarfı için buffer genişliği (metre)")
    parser.add_argument("--months-back", type=int, default=6,
                         help="Kaç ay geriye dönük veri çekilsin")
    args = parser.parse_args()

    print("[1/4] Test koridoru oluşturuluyor...")
    corridor = build_test_corridor(buffer_meters=args.buffer_meters)
    print(f"      Koridor WKT (kısaltılmış): {corridor['corridor_wkt'][:80]}...")

    date_to = datetime.now(timezone.utc)
    date_from = date_to - timedelta(days=30 * args.months_back)
    date_from_str = date_from.strftime("%Y-%m-%dT00:00:00Z")
    date_to_str = date_to.strftime("%Y-%m-%dT00:00:00Z")
    print(f"      Tarih aralığı: {date_from_str} -> {date_to_str}")

    if args.dry_run:
        print("\n[dry-run] Gerçek istek atılmıyor. Gönderilecek request body:")
        body_preview = {
            "input": {
                "bounds": {"geometry": corridor["corridor_geojson"]},
                "data": [{"type": "sentinel-2-l2a"}],
            },
            "aggregation": {
                "timeRange": {"from": date_from_str, "to": date_to_str},
                "aggregationInterval": {"of": "P30D"},
                "evalscript": "<sentinel_api.EVALSCRIPT icerigi>",
            },
        }
        print(json.dumps(body_preview, indent=2, ensure_ascii=False))
        print("\nDry-run tamamlandı. Gerçek çalıştırma için --line-id ile tekrar çağır.")
        return

    if not args.line_id:
        raise SystemExit("Hata: --dry-run kullanmıyorsan --line-id zorunlu.")

    print("\n[2/4] Sentinel Hub Statistical API'ye istek atılıyor...")
    raw_response = fetch_ndvi_statistics(
        corridor_geojson=corridor["corridor_geojson"],
        date_from=date_from_str,
        date_to=date_to_str,
    )

    print("[3/4] Yanıt ayrıştırılıyor...")
    records = parse_statistics_response(raw_response)
    print(f"      {len(records)} adet NDVI kaydı ayrıştırıldı.")
    if records:
        print(f"      Örnek kayıt: {records[0]}")

    print("[4/4] Supabase'e yazılıyor...")
    # db.py'yi burada import ediyoruz ki --dry-run modunda supabase kütüphanesi
    # (ve SUPABASE_URL/KEY .env'i) hiç gerekmesin.
    from db import insert_ndvi_measurements
    inserted = insert_ndvi_measurements(
        line_id=args.line_id,
        corridor_wkt=corridor["corridor_wkt"],
        records=records,
    )
    print(f"      {inserted} satır yazıldı.")


if __name__ == "__main__":
    main()
