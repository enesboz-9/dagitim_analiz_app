"""
fix_line_provinces.py
-----------------------
`power_lines` tablosundaki YANLIŞ il (province) bilgisini düzeltir.

SORUN: `fetch_osm_powerlines.py --country` ile çekilen OSM verisinde
hatların il bilgisi yok. `import_power_lines.py --province` default'u
"Samsun" olduğu için, Türkiye genelinde import edilen TÜM hatlara
(gerçek konumları ne olursa olsun) yanlışlıkla "Samsun" yazılmıştı.

ÇÖZÜM: Her hattın kendi geometrisinden (koordinatlarından), gerçek il
sınırlarına (turkiye_il_sinirlari.geojson) göre doğru ili nokta-poligon
testiyle tespit edip düzeltir.

Bu script VERİTABANINA DOĞRUDAN YAZMAZ — projenin genel prensibiyle
tutarlı olarak (bkz. README: "manuel SQL workflow'u tercih edilir"),
sadece Supabase SQL Editor'da elle çalıştıracağın UPDATE komutlarını
içeren .sql dosya(lar)ı üretir. Böylece neyin değiştiğini çalıştırmadan
önce gözden geçirebilirsin.

Kullanım:
    # 1) Önce dry-run: kaç hat etkilenecek, hangi iller çıkacak — veritabanına
    #    dokunmaz, Supabase'e bağlanır (sadece okuma).
    python fix_line_provinces.py --dry-run

    # 2) SQL dosyalarını üret (15.000 satır tek dosyada Supabase SQL Editor'ı
    #    zorlayabileceği için varsayılan olarak 2000'erli parçalara bölünür —
    #    split_sql.py ile daha önce yaptığın chunking mantığının aynısı):
    python fix_line_provinces.py --mode sql --chunk-size 2000

    # 3) docs/fix_line_provinces_0001.sql, _0002.sql, ... dosyalarının
    #    içeriğini SIRAYLA Supabase SQL Editor'da yapıştırıp çalıştır.

Not: "tahmini" (kesin poligon eşleşmesi bulunamayan, örn. kıyı/ada
sınırındaki) hatlar ayrı bir uyarı listesinde raporlanır; bunları SQL'e
dahil etmek istemiyorsan --skip-uncertain kullan.
"""

import argparse
import os

from db import get_supabase_client
from turkey_provinces import detect_province_for_line


def _sql_escape(value: str) -> str:
    return value.replace("'", "''")


def fetch_all_lines(client) -> list[dict]:
    """
    power_line_risk_status view'inden (line_id, line_name, province,
    line_geojson) çeker. View zaten anon key ile de okunabilir olacak
    kadar basit ama biz service_role client kullanıyoruz — sayfalama
    (Supabase varsayılan olarak tek istekte max 1000 satır döner).
    """
    rows = []
    page_size = 1000
    start = 0
    while True:
        resp = (
            client.table("power_line_risk_status")
            .select("line_id,line_name,province,line_geojson")
            .range(start, start + page_size - 1)
            .execute()
        )
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["dry-run", "sql"], default="dry-run",
                         help="dry-run: sadece özet göster; sql: UPDATE dosyaları üret")
    parser.add_argument("--dry-run", action="store_const", dest="mode", const="dry-run",
                         help="--mode dry-run ile aynı")
    parser.add_argument("--output-prefix", default="fix_line_provinces",
                         help="Üretilecek SQL dosyalarının adı (örn. fix_line_provinces_0001.sql)")
    parser.add_argument("--chunk-size", type=int, default=2000,
                         help="Her SQL dosyasındaki UPDATE satırı sayısı (Supabase SQL Editor'da tek seferde çok büyük dosya sorun çıkarabiliyor)")
    parser.add_argument("--skip-uncertain", action="store_true",
                         help="Kesin poligon eşleşmesi bulunamayan (tahmini) hatları SQL'e dahil etme")
    args = parser.parse_args()

    print("[1/3] Supabase'den mevcut hatlar çekiliyor...")
    client = get_supabase_client()
    rows = fetch_all_lines(client)
    print(f"      {len(rows)} hat bulundu.")

    print("[2/3] Her hat için gerçek il tespit ediliyor (geometriye göre)...")
    changes = []          # (line_id, line_name, eski_il, yeni_il, kesin_mi)
    uncertain_count = 0
    unchanged_count = 0
    skipped_no_geom = 0

    for i, row in enumerate(rows, 1):
        geojson = row.get("line_geojson")
        if not geojson or not geojson.get("coordinates"):
            skipped_no_geom += 1
            continue

        coords = geojson["coordinates"]
        # LineString: [[lon, lat], ...]. MultiLineString ihtimaline karşı
        # (import_power_lines.py normalde segmentlere böldüğü için nadir)
        # ilk segmenti kullan.
        if geojson.get("type") == "MultiLineString":
            coords = coords[0] if coords else []

        detected, exact = detect_province_for_line(coords)
        if detected is None:
            continue
        if not exact:
            uncertain_count += 1
            if args.skip_uncertain:
                continue

        current = row.get("province")
        if detected != current:
            changes.append((row["line_id"], row["line_name"], current, detected, exact))
        else:
            unchanged_count += 1

        if i % 2000 == 0:
            print(f"      {i}/{len(rows)} işlendi...")

    print(f"[3/3] Sonuç: {len(changes)} hat il bilgisi düzeltilecek, "
          f"{unchanged_count} hat zaten doğru, {skipped_no_geom} hat geometri eksik "
          f"yüzünden atlandı. ({uncertain_count} hat sınır/kıyı nedeniyle tahmini tespit edildi.)")

    if not changes:
        print("Düzeltilecek hat yok — işlem tamam.")
        return

    # Yeni il dağılımını özetle (bilgi amaçlı).
    from collections import Counter
    dist = Counter(c[3] for c in changes)
    print("\nEn çok düzeltme yapılan iller (ilk 10):")
    for name, count in dist.most_common(10):
        print(f"  {name}: {count} hat")

    if args.mode == "dry-run":
        print("\n(dry-run modundasın — hiçbir SQL dosyası üretilmedi. "
              "SQL üretmek için: python fix_line_provinces.py --mode sql)")
        return

    # --- SQL dosyalarını chunk'lara bölerek üret ---
    total_files = 0
    for chunk_start in range(0, len(changes), args.chunk_size):
        chunk = changes[chunk_start:chunk_start + args.chunk_size]
        total_files += 1
        filename = f"{args.output_prefix}_{total_files:04d}.sql"
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"-- {filename}\n")
            f.write(f"-- fix_line_provinces.py tarafından otomatik üretildi.\n")
            f.write(f"-- Bu dosyadaki {len(chunk)} hattın il bilgisi, gerçek geometrisine göre düzeltiliyor.\n")
            f.write("-- Supabase SQL Editor'da çalıştır. Sırayla tüm parçaları çalıştırman gerekiyor.\n\n")
            for line_id, line_name, old_province, new_province, exact in chunk:
                note = "" if exact else "  -- TAHMİNİ (sınır/kıyı bölgesi, kontrol et)"
                f.write(
                    f"UPDATE power_lines SET province = '{_sql_escape(new_province)}' "
                    f"WHERE id = '{line_id}';{note}\n"
                )
        print(f"  yazıldı: {filename} ({len(chunk)} UPDATE satırı)")

    print(f"\n{total_files} SQL dosyası üretildi. Sırayla Supabase SQL Editor'da çalıştır: "
          f"{args.output_prefix}_0001.sql, {args.output_prefix}_0002.sql, ...")


if __name__ == "__main__":
    main()
