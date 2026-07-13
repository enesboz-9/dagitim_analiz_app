"""
fetch_osm_powerlines.py
------------------------
Overpass API (OpenStreetMap) üzerinden, test koridorunun etrafındaki
elektrik hatlarını (power=line / power=minor_line) çeker ve
geometry.py'deki TEST_LINE_COORDS formatına hazır şekilde bastırır.

Kullanım:
    python fetch_osm_powerlines.py
    python fetch_osm_powerlines.py --bbox 41.20 36.20 41.40 36.50
    python fetch_osm_powerlines.py --pick 2   # listeden 2 numaralı hattı seç ve coords bastır

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bbox", type=float, nargs=4,
                         metavar=("SOUTH", "WEST", "NORTH", "EAST"),
                         default=DEFAULT_BBOX,
                         help="Arama kutusu: south west north east (WGS84 derece)")
    parser.add_argument("--pick", type=int, default=None,
                         help="Listeden seçilecek hattın sıra numarası (sonuçları gördükten sonra tekrar çalıştır)")
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

    if args.pick is None:
        print("\nBir hattı seçmek için: python fetch_osm_powerlines.py --pick <numara>")
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
