"""
fetch_osm_powerlines.py
------------------------
Overpass API (OpenStreetMap) üzerinden, test koridorunun etrafındaki
elektrik hatlarını (power=line / power=minor_line) çeker.

İki kullanım şekli var:

1) Tek hat / hızlı bakış (eski davranış): sonuçları listeler, --pick ile
   birini seçip geometry.py'deki TEST_LINE_COORDS formatına hazır şekilde
   ekrana basar (tek hatlı hızlı test için).

2) Toplu entegrasyon (--output-geojson): bulunan TÜM hatları (istersen
   --min-voltage / --power-type ile filtrelenmiş halini) tek bir GeoJSON
   FeatureCollection dosyasına yazar. Bu dosya doğrudan
   import_power_lines.py'ye verilebilir, böylece tüm hatlar tek seferde
   power_lines tablosuna aktarılır.

Kullanım:
    python fetch_osm_powerlines.py
    python fetch_osm_powerlines.py --bbox 41.20 36.20 41.40 36.50
    python fetch_osm_powerlines.py --pick 2   # listeden 2 numaralı hattı seç ve coords bastır
    python fetch_osm_powerlines.py --output-geojson osm_lines.geojson
    python fetch_osm_powerlines.py --output-geojson osm_lines.geojson --power-type line --min-voltage 154000

Ardından toplu entegrasyon için:
    python import_power_lines.py --input osm_lines.geojson --mode dry-run \\
        --name-field name --external-id-field id --voltage-field voltage_level
    python import_power_lines.py --input osm_lines.geojson --mode sql \\
        --output power_lines_import.sql --name-field name --external-id-field id --voltage-field voltage_level

Not: Bu script sadece OSM'de HARİTALANMIŞ hatları bulur. Kırsal alanda
OSM kapsamı eksik olabilir; sonuç boş gelirse --bbox ile daha geniş bir
alan dene, ya da manuel dijitalleştirmeye (uydu görüntüsünden elle
iz sürme) geç.
"""

import argparse
import json
import sys
import urllib.request

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# Varsayılan bbox: mevcut test koridorunun (geometry.py) etrafında biraz
# geniş bir kutu (south, west, north, east). Gerekirse --bbox ile değiştir.
DEFAULT_BBOX = (41.20, 36.20, 41.40, 36.50)


def build_query(bbox):
    south, west, north, east = bbox
    return f"""
[out:json][timeout:60];
(
  way["power"="line"]({south},{west},{north},{east});
  way["power"="minor_line"]({south},{west},{north},{east});
);
out geom;
"""


def fetch(bbox):
    query = build_query(bbox)
    data = query.encode("utf-8")
    last_error = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            req = urllib.request.Request(endpoint, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=70) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            last_error = e
            print(f"[UYARI] {endpoint} başarısız oldu ({e}), diğer endpoint deneniyor...")
    raise RuntimeError(f"Hiçbir Overpass endpoint'i yanıt vermedi: {last_error}")


def _voltage_level_label(raw_voltage: str) -> str:
    """
    OSM'deki ham voltaj değerini (volt, örn. '154000') YEDAŞ tarzı kısa
    gerilim seviyesi etiketine çevirir (AG/OG/YG). Bilinmeyen/parse
    edilemeyen değerler için 'OG' varsayılan olarak döner (import_power_lines.py
    ile aynı varsayılan).

    Kabaca (TR dağıtım/iletim pratiği):
      < 1 kV        -> AG (Alçak Gerilim)
      1 kV - 36 kV   -> OG (Orta Gerilim)     -- tipik YEDAŞ dağıtım hattı
      > 36 kV        -> YG (Yüksek Gerilim)   -- genelde TEİAŞ iletim hattı (154kV/380kV)
    """
    try:
        volts = int(str(raw_voltage).split(";")[0])
    except (ValueError, AttributeError):
        return "OG"
    if volts < 1000:
        return "AG"
    if volts <= 36000:
        return "OG"
    return "YG"


def _element_name(tags: dict, element_id) -> str:
    return tags.get("name") or tags.get("operator") or f"OSM Hattı {element_id}"


def elements_to_feature_collection(elements: list[dict]) -> dict:
    """
    Overpass 'way' elemanlarının listesini, import_power_lines.py'nin
    doğrudan tüketebileceği bir GeoJSON FeatureCollection'a çevirir.

    Her feature'ın properties'i:
      - id       -> external_id olarak kullanılabilir (--external-id-field id)
      - name     -> hat adı (--name-field name)
      - voltage  -> OSM'deki ham voltaj değeri, örn. "154000" (--voltage-field voltage)
      - power    -> "line" ya da "minor_line" (bilgi amaçlı, import'ta kullanılmaz)

    Nokta sayısı 2'den az olan (geometrisi eksik/bozuk) elemanlar atlanır.
    """
    features = []
    skipped = 0
    for el in elements:
        geom = el.get("geometry", [])
        coords = [(pt["lon"], pt["lat"]) for pt in geom if "lon" in pt and "lat" in pt]
        if len(coords) < 2:
            skipped += 1
            continue
        tags = el.get("tags", {})
        raw_voltage = tags.get("voltage", "?")
        features.append({
            "type": "Feature",
            "properties": {
                "id": el["id"],
                "name": _element_name(tags, el["id"]),
                "voltage": raw_voltage,
                "voltage_level": _voltage_level_label(raw_voltage),
                "power": tags.get("power", "?"),
            },
            "geometry": {
                "type": "LineString",
                "coordinates": [[lon, lat] for lon, lat in coords],
            },
        })
    if skipped:
        print(f"[UYARI] {skipped} eleman geometri eksikliği nedeniyle atlandı.")
    return {"type": "FeatureCollection", "features": features}


def filter_elements(elements: list[dict], power_type: str | None, min_voltage: int | None) -> list[dict]:
    filtered = []
    for el in elements:
        tags = el.get("tags", {})
        if power_type and tags.get("power") != power_type:
            continue
        if min_voltage is not None:
            raw_voltage = tags.get("voltage", "")
            try:
                # voltage bazen "154000;380000" gibi birden fazla değer içerebilir; ilkini al
                voltage_val = int(raw_voltage.split(";")[0])
            except (ValueError, AttributeError):
                continue  # voltaj bilinmiyorsa ve bir eşik isteniyorsa dışarıda bırak
            if voltage_val < min_voltage:
                continue
        filtered.append(el)
    return filtered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bbox", type=float, nargs=4,
                         metavar=("SOUTH", "WEST", "NORTH", "EAST"),
                         default=DEFAULT_BBOX,
                         help="Arama kutusu: south west north east (WGS84 derece)")
    parser.add_argument("--pick", type=int, default=None,
                         help="Listeden seçilecek hattın sıra numarası (sonuçları gördükten sonra tekrar çalıştır)")
    parser.add_argument("--output-geojson", type=str, default=None,
                         help="Verilirse, bulunan TÜM hatları (filtrelenmiş hâliyle) bu yola tek bir "
                              "GeoJSON FeatureCollection olarak yazar (toplu entegrasyon için)")
    parser.add_argument("--power-type", choices=["line", "minor_line"], default=None,
                         help="--output-geojson için: sadece bu power= tipindeki hatları dahil et")
    parser.add_argument("--min-voltage", type=int, default=None,
                         help="--output-geojson için: sadece bu voltaj (V) değerine eşit/üstü hatları dahil et "
                              "(voltajı bilinmeyenler otomatik dışarıda bırakılır)")
    args = parser.parse_args()

    print(f"Overpass'a sorgu gönderiliyor (bbox={args.bbox})...")
    result = fetch(tuple(args.bbox))
    elements = [el for el in result.get("elements", []) if el.get("type") == "way"]

    if not elements:
        print("\nHiç sonuç bulunamadı. Bu bölgede OSM'de haritalanmış power hattı yok görünüyor.")
        print("Öneriler: --bbox ile daha geniş bir alan dene, ya da manuel dijitalleştirmeye geç.")
        sys.exit(0)

    print(f"\n{len(elements)} hat bulundu:\n")
    for i, el in enumerate(elements):
        tags = el.get("tags", {})
        geom = el.get("geometry", [])
        n_points = len(geom)
        name = tags.get("name") or tags.get("operator") or "(isimsiz)"
        power_type = tags.get("power", "?")
        voltage = tags.get("voltage", "?")
        print(f"  [{i}] id={el['id']} power={power_type} voltage={voltage} "
              f"nokta_sayısı={n_points} isim/operatör={name}")

    if args.output_geojson:
        filtered = filter_elements(elements, args.power_type, args.min_voltage)
        if not filtered:
            print("\n[HATA] Filtrelerden sonra hiç hat kalmadı. --power-type / --min-voltage değerlerini gözden geçir.")
            sys.exit(1)
        fc = elements_to_feature_collection(filtered)
        with open(args.output_geojson, "w", encoding="utf-8") as f:
            json.dump(fc, f, ensure_ascii=False, indent=2)
        print(f"\n{len(fc['features'])} hat '{args.output_geojson}' dosyasına yazıldı "
              f"({len(elements) - len(filtered)} hat filtrelerle elendi).")
        print("\nToplu entegrasyon için sıradaki adım:")
        print(f"  python import_power_lines.py --input {args.output_geojson} --mode dry-run \\")
        print("      --name-field name --external-id-field id --voltage-field voltage_level")
        print("  (dry-run çıktısı iyi görünüyorsa --mode sql ya da --mode rpc ile gerçek yazıma geç)")
        return

    if args.pick is None:
        print("\nBir hattı seçmek için: python fetch_osm_powerlines.py --pick <numara>")
        print("Tüm hatları toplu aktarmak için: python fetch_osm_powerlines.py --output-geojson <dosya.geojson>")
        return

    if not (0 <= args.pick < len(elements)):
        print(f"\n[HATA] Geçersiz --pick değeri. 0 ile {len(elements) - 1} arasında olmalı.")
        sys.exit(1)

    chosen = elements[args.pick]
    coords = [(pt["lon"], pt["lat"]) for pt in chosen.get("geometry", [])]

    print(f"\nSeçilen hat: id={chosen['id']} ({len(coords)} nokta)")
    print("\ngeometry.py içindeki TEST_LINE_COORDS'u şununla değiştir:\n")
    print("TEST_LINE_COORDS = [")
    for lon, lat in coords:
        print(f"    ({lon}, {lat}),")
    print("]")


if __name__ == "__main__":
    main()
