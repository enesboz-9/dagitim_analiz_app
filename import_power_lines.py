"""
import_power_lines.py
----------------------
Gerçek YEDAŞ hat verisini (GeoJSON FeatureCollection, LineString/
MultiLineString) `power_lines` tablosuna aktarır. run_pipeline.py zaten
tablodaki TÜM hatları otomatik işliyor (get_active_power_lines RPC'si
sayesinde) — bu script sadece o tabloyu gerçek/çoklu hatlarla doldurmak
için var.

Veri kaynağı hakkında:
  YEDAŞ'tan gelen veri genelde shapefile (.shp) ya da CAD/CBS export'u
  olur. Bu script GeoJSON bekliyor; shapefile'ın varsa önce GeoJSON'a
  çevir, örn:
      ogr2ogr -f GeoJSON hatlar.geojson hatlar.shp -t_srs EPSG:4326
  (ogr2ogr, GDAL kurulumuyla gelir; QGIS de "Farklı Kaydet -> GeoJSON"
  ile aynı işi yapar.)

Alan (property) eşlemesi:
  GeoJSON feature'larındaki property adları kaynağa göre değişeceğinden
  (örn. "HAT_ADI" ya da "line_name" gibi), hangi property'nin isim/il/
  gerilim seviyesi/dış-kimlik olduğunu --*-field argümanlarıyla belirt.
  Eşleşen property yoksa --province / --voltage-level default'ları
  kullanılır.

Kullanım
--------
1) Önce her zaman dry-run ile kontrol et (hiçbir şey yazılmaz):

    python import_power_lines.py --input hatlar.geojson --mode dry-run

2) SQL dosyası üret, Supabase SQL Editor'da elle çalıştır (en güvenli yol,
   büyük/az sayıda hat için ya da ilk import için önerilir):

    python import_power_lines.py --input hatlar.geojson --mode sql \\
        --output power_lines_import.sql

   ÖNKOŞUL: supabase_add_external_id.sql daha önce çalıştırılmış olmalı
   (external_id kolonu için).

3) Doğrudan Supabase'e yaz (çok sayıda hat / periyodik re-sync için):

    python import_power_lines.py --input hatlar.geojson --mode rpc

   ÖNKOŞUL: supabase_add_external_id.sql VE
   supabase_rpc_upsert_power_line.sql daha önce çalıştırılmış olmalı.
   Bu mod, .env'deki SUPABASE_URL/KEY ile gerçek bir bağlantı açar.

Her iki gerçek mod da external_id üzerinden upsert yapar: aynı script
aynı dosyayla tekrar çalıştırılırsa (veri YEDAŞ'ta güncellendiğinde)
duplicate satır oluşmaz, mevcut satır güncellenir.
"""

import argparse
import json
import sys

from geometry import build_corridor


def _iter_line_coords(geometry: dict):
    """
    Bir GeoJSON geometry'sinden (LineString ya da MultiLineString) bir
    ya da birden fazla (lon, lat) koordinat listesi üretir (generator).
    MultiLineString'in her parçası ayrı bir hat/segment olarak ele alınır
    (örn. bir hat gerçek dünyada birden fazla ayrı çizim parçasından
    oluşuyorsa).
    """
    gtype = geometry.get("type")
    if gtype == "LineString":
        yield geometry["coordinates"]
    elif gtype == "MultiLineString":
        for part in geometry["coordinates"]:
            yield part
    else:
        raise ValueError(f"Desteklenmeyen geometry tipi: {gtype} (LineString/MultiLineString bekleniyor)")


def load_features(input_path: str, name_field: str, external_id_field: str,
                   province_field: str, voltage_field: str,
                   default_province: str, default_voltage: str) -> list[dict]:
    """
    GeoJSON dosyasını okuyup her hat/segment için düz (flat) bir kayıt
    listesi döner: {"external_id", "name", "province", "voltage_level", "coords"}
    """
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    features = data.get("features", [])
    if not features:
        raise ValueError(f"{input_path} içinde hiç feature bulunamadı (boş FeatureCollection mi?)")

    records = []
    skipped = 0

    for i, feature in enumerate(features):
        props = feature.get("properties", {}) or {}
        geometry = feature.get("geometry")
        if not geometry:
            skipped += 1
            print(f"[UYARI] feature[{i}]: geometry yok, atlanıyor.")
            continue

        base_name = props.get(name_field) or f"YEDAŞ Hattı {i}"
        base_external_id = props.get(external_id_field) or f"import-{i}"
        province = props.get(province_field) or default_province
        voltage_level = props.get(voltage_field) or default_voltage

        try:
            parts = list(_iter_line_coords(geometry))
        except ValueError as e:
            skipped += 1
            print(f"[UYARI] feature[{i}] ({base_name}): {e}, atlanıyor.")
            continue

        for j, coords in enumerate(parts):
            if len(coords) < 2:
                skipped += 1
                print(f"[UYARI] feature[{i}] parça[{j}] ({base_name}): 2'den az nokta, atlanıyor.")
                continue
            suffix = "" if len(parts) == 1 else f" (parça {j + 1}/{len(parts)})"
            records.append({
                "external_id": base_external_id if len(parts) == 1 else f"{base_external_id}-{j}",
                "name": f"{base_name}{suffix}",
                "province": province,
                "voltage_level": voltage_level,
                "coords": [(x, y) for x, y, *_ in coords],  # olası z-koordinatını at
            })

    print(f"{len(records)} hat/segment okundu, {skipped} feature atlandı.")
    return records


def build_rows(records: list[dict], buffer_meters: float) -> list[dict]:
    """Her kayıt için buffer geometrisini üretir, DB'ye yazılacak satırları döner."""
    rows = []
    for r in records:
        try:
            corridor = build_corridor(r["coords"], buffer_meters=buffer_meters)
        except Exception as e:
            print(f"[HATA] {r['name']}: buffer üretilemedi ({e}), atlanıyor.")
            continue
        rows.append({**r, "line_wkt": corridor["line_wkt"], "buffer_wkt": corridor["corridor_wkt"]})
    return rows


def _sql_escape(value: str) -> str:
    return value.replace("'", "''")


def write_sql(rows: list[dict], output_path: str):
    """
    Elle Supabase SQL Editor'da çalıştırılacak bir upsert SQL dosyası üretir.
    Doğrudan bağlantı açmadığından, ilk import ya da gözden geçirilmesi
    istenen importlar için en güvenli yoldur.
    """
    lines = [
        "-- import_power_lines.py tarafından otomatik üretildi.",
        "-- Supabase SQL Editor'da çalıştırmadan önce gözden geçir.",
        "-- ÖNKOŞUL: supabase_add_external_id.sql daha önce çalıştırılmış olmalı.",
        "",
    ]
    for r in rows:
        lines.append(
            "INSERT INTO power_lines (external_id, name, province, voltage_level, geom, buffer_geom)\n"
            f"VALUES (\n"
            f"    '{_sql_escape(r['external_id'])}',\n"
            f"    '{_sql_escape(r['name'])}',\n"
            f"    '{_sql_escape(r['province'])}',\n"
            f"    '{_sql_escape(r['voltage_level'])}',\n"
            f"    ST_GeomFromText('{r['line_wkt']}', 4326),\n"
            f"    ST_GeomFromText('{r['buffer_wkt']}', 4326)\n"
            ")\n"
            "ON CONFLICT (external_id) DO UPDATE SET\n"
            "    name = EXCLUDED.name,\n"
            "    province = EXCLUDED.province,\n"
            "    voltage_level = EXCLUDED.voltage_level,\n"
            "    geom = EXCLUDED.geom,\n"
            "    buffer_geom = EXCLUDED.buffer_geom;\n"
        )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"{len(rows)} satırlık SQL dosyası yazıldı: {output_path}")
    print("Sonraki adım: bu dosyanın içeriğini Supabase Dashboard -> SQL Editor'da çalıştır.")


def write_via_rpc(rows: list[dict]):
    """Her satırı doğrudan Supabase'e yazar (upsert_power_line RPC'si üzerinden)."""
    from db import get_supabase_client  # gecikmeli import (dry-run/sql modlarında supabase gerekmesin)

    client = get_supabase_client()
    success, failure = 0, 0
    for r in rows:
        try:
            client.rpc("upsert_power_line", {
                "p_external_id": r["external_id"],
                "p_name": r["name"],
                "p_province": r["province"],
                "p_voltage_level": r["voltage_level"],
                "p_line_wkt": r["line_wkt"],
                "p_buffer_wkt": r["buffer_wkt"],
            }).execute()
            success += 1
            print(f"  [OK] {r['name']}")
        except Exception as e:
            failure += 1
            print(f"  [HATA] {r['name']}: {e}")
    print(f"\nTamamlandı. Başarılı: {success}, Başarısız: {failure}")
    if failure > 0:
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Gerçek YEDAŞ hat verisini power_lines tablosuna aktarır")
    parser.add_argument("--input", required=True, help="GeoJSON dosya yolu (LineString/MultiLineString feature'ları)")
    parser.add_argument("--mode", choices=["dry-run", "sql", "rpc"], default="dry-run",
                         help="dry-run: sadece özet göster; sql: SQL dosyası üret; rpc: doğrudan Supabase'e yaz")
    parser.add_argument("--output", default="power_lines_import.sql", help="--mode sql için çıktı dosyası")
    parser.add_argument("--buffer-meters", type=float, default=20.0, help="Emniyet mesafesi zarfı genişliği (metre)")
    parser.add_argument("--name-field", default="name", help="Hat adı için GeoJSON property anahtarı")
    parser.add_argument("--external-id-field", default="id", help="Kararlı dış kimlik için GeoJSON property anahtarı")
    parser.add_argument("--province-field", default="province", help="İl için GeoJSON property anahtarı")
    parser.add_argument("--voltage-field", default="voltage_level", help="Gerilim seviyesi için GeoJSON property anahtarı")
    parser.add_argument("--province", default="Samsun", help="property'de bulunamazsa kullanılacak varsayılan il")
    parser.add_argument("--voltage-level", default="OG", help="property'de bulunamazsa kullanılacak varsayılan gerilim seviyesi")
    args = parser.parse_args()

    print(f"[1/3] {args.input} okunuyor...")
    records = load_features(
        args.input,
        name_field=args.name_field,
        external_id_field=args.external_id_field,
        province_field=args.province_field,
        voltage_field=args.voltage_field,
        default_province=args.province,
        default_voltage=args.voltage_level,
    )
    if not records:
        print("İşlenecek hat kalmadı, çıkılıyor.")
        sys.exit(0)

    print(f"\n[2/3] {len(records)} hat için buffer (emniyet zarfı) hesaplanıyor (buffer={args.buffer_meters}m)...")
    rows = build_rows(records, buffer_meters=args.buffer_meters)

    print(f"\n[3/3] Mod: {args.mode}")
    if args.mode == "dry-run":
        for r in rows[:10]:
            print(f"  - {r['name']} | il={r['province']} | gerilim={r['voltage_level']} | "
                  f"external_id={r['external_id']} | corridor_wkt (kısaltılmış)={r['buffer_wkt'][:60]}...")
        if len(rows) > 10:
            print(f"  ... ve {len(rows) - 10} hat daha.")
        print("\nDry-run tamamlandı. Gerçek yazım için --mode sql ya da --mode rpc kullan.")
    elif args.mode == "sql":
        write_sql(rows, args.output)
    elif args.mode == "rpc":
        write_via_rpc(rows)


if __name__ == "__main__":
    main()
