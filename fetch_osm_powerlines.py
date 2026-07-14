"""
fetch_osm_powerlines.py
------------------------
Overpass API (OpenStreetMap) üzerinden, test koridorunun etrafındaki
elektrik hatlarını (power=line / power=minor_line) çeker.

Üç kullanım şekli var:

1) Tek hat / hızlı bakış (eski davranış): sonuçları listeler, --pick ile
   birini seçip geometry.py'deki TEST_LINE_COORDS formatına hazır şekilde
   ekrana basar (tek hatlı hızlı test için).

2) Toplu entegrasyon (--output-geojson): bulunan TÜM hatları (istersen
   --min-voltage / --power-type ile filtrelenmiş halini) tek bir GeoJSON
   FeatureCollection dosyasına yazar. Bu dosya doğrudan
   import_power_lines.py'ye verilebilir, böylece tüm hatlar tek seferde
   power_lines tablosuna aktarılır.

3) Türkiye geneli (--country): tek bir --bbox yerine, Overpass'ın tek
   sorguda zaman aşımına uğramaması için Türkiye'yi küçük kutucuklara
   (tile) bölüp her birini ayrı ayrı sorgular, sonuçları birleştirir
   (aynı hat birden fazla tile'a düşerse id'ye göre tekilleştirilir).
   YEDAŞ'a özgü veri bulunamadığında "elimizdeki tüm Türkiye hatlarını
   ekleyelim" senaryosu için kullanılır.

Kullanım:
    python fetch_osm_powerlines.py
    python fetch_osm_powerlines.py --bbox 41.20 36.20 41.40 36.50
    python fetch_osm_powerlines.py --pick 2   # listeden 2 numaralı hattı seç ve coords bastır
    python fetch_osm_powerlines.py --output-geojson osm_lines.geojson
    python fetch_osm_powerlines.py --output-geojson osm_lines.geojson --power-type line --min-voltage 154000
    python fetch_osm_powerlines.py --country --output-geojson turkiye_hatlari.geojson

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
import time
import urllib.request

OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

# urllib'in varsayılan User-Agent'ı ("Python-urllib/3.x") bazı Overpass
# aynalarında (özellikle overpass-api.de) "406 Not Acceptable" ile
# reddediliyor; tanımlayıcı bir User-Agent göndermek bunu çözüyor.
REQUEST_HEADERS = {
    "User-Agent": "dagitim-analiz-app-fetch-osm-powerlines/1.0 (+https://github.com/)",
    "Content-Type": "text/plain; charset=utf-8",
    "Accept": "application/json",
}

# Varsayılan bbox: mevcut test koridorunun (geometry.py) etrafında biraz
# geniş bir kutu (south, west, north, east). Gerekirse --bbox ile değiştir.
DEFAULT_BBOX = (41.20, 36.20, 41.40, 36.50)

# Türkiye'nin tamamını kabaca kapsayan dış kutu (south, west, north, east).
# --country ile kullanılır; kıyıdan biraz taşması sorun değil, Overpass
# sadece bu kutu içindeki elemanları döner.
TURKEY_BBOX = (35.80, 25.60, 42.20, 44.90)

# Tek bir Overpass sorgusu tüm Türkiye'yi kapsayacak kadar büyük olursa
# public sunucularda zaman aşımına uğrar; bu yüzden --country modunda
# bbox'ı bu boyuttaki (derece) kutucuklara bölüp tek tek sorgularız.
DEFAULT_TILE_SIZE_DEG = 1.5

# Ardışık Overpass isteklerinin arasına konan bekleme (saniye) — public
# sunucuları aşırı yüklememek için (hızlı ardışık istekler timeout'a yol açabiliyor).
TILE_REQUEST_DELAY_SEC = 2.0

# Sunucu tarafı sorgu zaman aşımı (Overpass query içindeki [timeout:] ile aynı olmalı).
QUERY_TIMEOUT_SEC = 90

# İki endpoint de başarısız olursa, kısa bir bekleme sonrası tekrar denenecek
# tur sayısı (geçici ağ/rate-limit sorunlarına karşı).
MAX_RETRY_PASSES = 2
RETRY_BACKOFF_SEC = 8


def generate_tiles(bbox: tuple, tile_size_deg: float) -> list:
    """
    Verilen dış bbox'ı (south, west, north, east) tile_size_deg boyutunda
    kare kutucuklara böler, her biri (south, west, north, east) olan bir
    liste döner.
    """
    south, west, north, east = bbox
    tiles = []
    lat = south
    while lat < north:
        lat_end = min(lat + tile_size_deg, north)
        lon = west
        while lon < east:
            lon_end = min(lon + tile_size_deg, east)
            tiles.append((lat, lon, lat_end, lon_end))
            lon = lon_end
        lat = lat_end
    return tiles


def build_query(bbox):
    south, west, north, east = bbox
    return f"""
[out:json][timeout:{QUERY_TIMEOUT_SEC}];
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
    for attempt in range(1, MAX_RETRY_PASSES + 1):
        for endpoint in OVERPASS_ENDPOINTS:
            try:
                req = urllib.request.Request(endpoint, data=data, method="POST", headers=REQUEST_HEADERS)
                with urllib.request.urlopen(req, timeout=QUERY_TIMEOUT_SEC + 20) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except Exception as e:
                last_error = e
                print(f"[UYARI] {endpoint} başarısız oldu ({e}), diğer endpoint deneniyor...")
        if attempt < MAX_RETRY_PASSES:
            print(f"[UYARI] İki endpoint de başarısız oldu, {RETRY_BACKOFF_SEC}sn sonra tekrar denenecek "
                  f"(deneme {attempt}/{MAX_RETRY_PASSES})...")
            time.sleep(RETRY_BACKOFF_SEC)
    raise RuntimeError(f"Hiçbir Overpass endpoint'i yanıt vermedi: {last_error}")


def fetch_tiles(tiles: list) -> tuple:
    """
    Verilen tile (south, west, north, east) listesini tek tek sorgular,
    tüm 'way' elemanlarını id'ye göre tekilleştirip döner. Bir tile
    başarısız olursa (zaman aşımı, 5xx, DNS hatası vb.) o tile'ı atlayıp
    diğerleriyle devam eder — tüm çalıştırmayı iptal etmez.

    Dönüş: (elements listesi, başarısız_olan_tile'ların listesi)
    başarısız_olan_tile'lar ileride --retry-failed ile tekrar denenebilsin
    diye ham (south, west, north, east) tuple'ları olarak döner.
    """
    elements_by_id = {}
    failed_tiles = []
    for i, tile in enumerate(tiles):
        south, west, north, east = tile
        print(f"  [{i + 1}/{len(tiles)}] bbox=({south:.2f},{west:.2f},{north:.2f},{east:.2f}) sorgulanıyor...", end=" ")
        try:
            result = fetch(tile)
            tile_elements = [el for el in result.get("elements", []) if el.get("type") == "way"]
            new_count = 0
            for el in tile_elements:
                if el["id"] not in elements_by_id:
                    elements_by_id[el["id"]] = el
                    new_count += 1
            print(f"{len(tile_elements)} hat ({new_count} yeni).")
        except Exception as e:
            failed_tiles.append(tile)
            print(f"[HATA] atlanıyor: {e}")
        if i < len(tiles) - 1:
            time.sleep(TILE_REQUEST_DELAY_SEC)

    if failed_tiles:
        print(f"\n[UYARI] {len(failed_tiles)}/{len(tiles)} kutucuk sorgulanamadı (Overpass zaman aşımı/hata). "
              "Kapsam eksik olabilir; --retry-failed ile sadece bu kutucukları tekrar deneyebilirsin.")

    return list(elements_by_id.values()), failed_tiles


def fetch_all_tiles(outer_bbox: tuple, tile_size_deg: float) -> tuple:
    """
    outer_bbox'ı tile_size_deg boyutunda kutucuklara bölüp fetch_tiles ile
    sorgular. Dönüş: (elements listesi, başarısız_olan_tile'ların listesi).
    """
    tiles = generate_tiles(outer_bbox, tile_size_deg)
    print(f"Türkiye {len(tiles)} kutucuğa ({tile_size_deg}°x{tile_size_deg}°) bölündü, "
          f"her biri ayrı ayrı sorgulanacak (bu birkaç dakika sürebilir)...")
    return fetch_tiles(tiles)


def failed_tiles_path(output_geojson: str) -> str:
    """--output-geojson yoluna göre başarısız-tile sidecar dosyasının yolunu üretir."""
    base = output_geojson or "turkiye_hatlari.geojson"
    return base + ".failed_tiles.json"


def save_failed_tiles(path: str, tiles: list) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump([list(t) for t in tiles], f, ensure_ascii=False, indent=2)
    print(f"[BİLGİ] {len(tiles)} başarısız kutucuk '{path}' dosyasına kaydedildi. "
          f"Tekrar denemek için: --retry-failed {path}")


def load_failed_tiles(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [tuple(t) for t in raw]


def load_existing_features_by_id(path: str) -> dict:
    """
    Önceki bir --output-geojson çalıştırmasından kalan feature'ları
    properties.id'ye göre bir sözlükte döner (dosya yoksa boş sözlük).
    --retry-failed sonrası yeni bulunan hatlarla birleştirmek için kullanılır.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            fc = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    result = {}
    for feat in fc.get("features", []):
        fid = feat.get("properties", {}).get("id")
        if fid is not None:
            result[fid] = feat
    return result


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


def filter_elements(elements: list[dict], power_type: str | None, min_voltage: int | None,
                     max_voltage: int | None = None, operator_contains: str | None = None) -> list[dict]:
    filtered = []
    for el in elements:
        tags = el.get("tags", {})
        if power_type and tags.get("power") != power_type:
            continue
        if operator_contains:
            haystack = f"{tags.get('operator', '')} {tags.get('name', '')}".lower()
            if operator_contains.lower() not in haystack:
                continue
        if min_voltage is not None or max_voltage is not None:
            raw_voltage = tags.get("voltage", "")
            try:
                # voltage bazen "154000;380000" gibi birden fazla değer içerebilir; ilkini al
                voltage_val = int(raw_voltage.split(";")[0])
            except (ValueError, AttributeError):
                continue  # voltaj bilinmiyorsa ve bir eşik isteniyorsa dışarıda bırak
            if min_voltage is not None and voltage_val < min_voltage:
                continue
            if max_voltage is not None and voltage_val > max_voltage:
                continue
        filtered.append(el)
    return filtered


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bbox", type=float, nargs=4,
                         metavar=("SOUTH", "WEST", "NORTH", "EAST"),
                         default=DEFAULT_BBOX,
                         help="Arama kutusu: south west north east (WGS84 derece). --country verilirse yok sayılır.")
    parser.add_argument("--country", action="store_true",
                         help="Tek bir bölge yerine tüm Türkiye'yi tarar (kutucuklara bölerek, bkz. --tile-size). "
                              "YEDAŞ'a özgü veri bulunamadığında bulunabilen tüm Türkiye hatlarını toplamak için.")
    parser.add_argument("--tile-size", type=float, default=DEFAULT_TILE_SIZE_DEG,
                         help=f"--country için kutucuk boyutu (derece). Varsayılan {DEFAULT_TILE_SIZE_DEG}. "
                              "Zaman aşımı çok oluyorsa küçült (örn. 1.0); daha hızlı bitsin istiyorsan büyüt.")
    parser.add_argument("--retry-failed", type=str, default=None,
                         help="Önceki --country çalıştırmasında başarısız olan kutucukların kaydedildiği "
                              ".failed_tiles.json dosyasının yolu. Verilirse --country/--bbox yok sayılır, "
                              "sadece bu dosyadaki kutucuklar tekrar sorgulanır ve sonuçlar --output-geojson "
                              "ile verilen mevcut dosyayla birleştirilir (dosya varsa üzerine eklenir, "
                              "yeniden başarısız olanlar aynı dosyaya güncellenerek yazılır).")
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
    parser.add_argument("--max-voltage", type=int, default=None,
                         help="--output-geojson için: sadece bu voltaj (V) değerine eşit/altı hatları dahil et "
                              "(örn. TEİAŞ ileti hatlarını (154kV/380kV) elemek için --max-voltage 36000 kullan; "
                              "voltajı bilinmeyenler otomatik dışarıda bırakılır)")
    parser.add_argument("--operator", type=str, default=None,
                         help="--output-geojson için: sadece operator/name etiketi bu metni içeren hatları dahil et "
                              "(örn. --operator YEDAŞ). OSM'de operator etiketi olan Türkiye dağıtım hatları azdır, "
                              "boş sonuç alırsan bu filtreyi kaldırıp elle gözden geçirmen gerekebilir)")
    args = parser.parse_args()

    retry_mode = args.retry_failed is not None
    failed_tiles = []

    if retry_mode:
        tiles = load_failed_tiles(args.retry_failed)
        print(f"'{args.retry_failed}' dosyasından {len(tiles)} başarısız kutucuk okundu, "
              f"sadece bunlar tekrar sorgulanacak...")
        elements, failed_tiles = fetch_tiles(tiles)
    elif args.country:
        elements, failed_tiles = fetch_all_tiles(TURKEY_BBOX, args.tile_size)
    else:
        print(f"Overpass'a sorgu gönderiliyor (bbox={args.bbox})...")
        result = fetch(tuple(args.bbox))
        elements = [el for el in result.get("elements", []) if el.get("type") == "way"]

    # --country ya da --retry-failed sonrası, hâlâ başarısız olan kutucukları
    # (varsa) sidecar dosyaya yaz/güncelle — sonraki --retry-failed çalıştırması
    # için. retry_mode'da dosya, elimizdeki eski failed-tiles dosyasının yerini alır
    # (başarılı olanlar listeden düşer, yeniden başarısız olanlar kalır).
    if args.country or retry_mode:
        ft_path = args.retry_failed if retry_mode else failed_tiles_path(args.output_geojson)
        if failed_tiles:
            save_failed_tiles(ft_path, failed_tiles)
        elif retry_mode:
            print(f"[BİLGİ] Tüm kutucuklar bu sefer başarılı oldu, '{ft_path}' siliniyor.")
            try:
                import os
                os.remove(ft_path)
            except OSError:
                pass

    if not elements:
        if retry_mode:
            print("\nBu çalıştırmada hiç yeni hat bulunamadı (tüm tekrar denemeler de başarısız oldu "
                  "ya da bu kutucuklarda zaten hat yoktu). Mevcut çıktı dosyası değişmeden kalıyor.")
            sys.exit(0)
        print("\nHiç sonuç bulunamadı. Bu bölgede OSM'de haritalanmış power hattı yok görünüyor.")
        print("Öneriler: --bbox ile daha geniş bir alan dene, ya da manuel dijitalleştirmeye geç.")
        sys.exit(0)

    print(f"\nToplam {len(elements)} hat bulundu.")
    if not args.country:
        print()
        for i, el in enumerate(elements):
            tags = el.get("tags", {})
            geom = el.get("geometry", [])
            n_points = len(geom)
            name = tags.get("name") or tags.get("operator") or "(isimsiz)"
            power_type = tags.get("power", "?")
            voltage = tags.get("voltage", "?")
            print(f"  [{i}] id={el['id']} power={power_type} voltage={voltage} "
                  f"nokta_sayısı={n_points} isim/operatör={name}")
    elif args.pick is not None:
        print("[UYARI] --country modunda --pick sıra numarası tile sırasına göre değişebileceğinden "
              "güvenilir değil; --output-geojson kullan.")

    if args.output_geojson:
        filtered = filter_elements(elements, args.power_type, args.min_voltage,
                                    max_voltage=args.max_voltage, operator_contains=args.operator)
        if not filtered:
            print("\n[HATA] Filtrelerden sonra hiç hat kalmadı. --power-type / --min-voltage / "
                  "--max-voltage / --operator değerlerini gözden geçir.")
            sys.exit(1)
        fc = elements_to_feature_collection(filtered)

        if retry_mode:
            # Tekrar denenen kutucuklardan gelen yeni hatları, mevcut çıktı
            # dosyasındaki hatlarla birleştir (üzerine yazma değil, ekleme).
            existing_by_id = load_existing_features_by_id(args.output_geojson)
            before_count = len(existing_by_id)
            added = 0
            for feat in fc["features"]:
                fid = feat["properties"]["id"]
                if fid not in existing_by_id:
                    added += 1
                existing_by_id[fid] = feat
            merged_fc = {"type": "FeatureCollection", "features": list(existing_by_id.values())}
            with open(args.output_geojson, "w", encoding="utf-8") as f:
                json.dump(merged_fc, f, ensure_ascii=False, indent=2)
            print(f"\n'{args.output_geojson}' güncellendi: {before_count} mevcut hat + {added} yeni hat "
                  f"= toplam {len(merged_fc['features'])} hat.")
        else:
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
