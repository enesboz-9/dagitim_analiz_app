"""
turkey_provinces.py
--------------------
Bir (lon, lat) koordinatının Türkiye'nin hangi iline düştüğünü bulur.

Veri kaynağı: turkiye_il_sinirlari.geojson (81 il, MultiPolygon sınırları,
WGS84 / EPSG:4326). Bu dosya, açık kaynak "alpers/Turkey-Maps-GeoJSON"
reposundaki tr-cities.json'dan alınmıştır (Apache-2.0 lisanslı).

Neden gerekli oldu:
--------------------
`fetch_osm_powerlines.py --country` ile Türkiye genelinde çekilen OSM
verisinde hatların "province" (il) property'si YOK — OSM, elektrik
hatlarını il bilgisiyle etiketlemiyor. Bu yüzden `import_power_lines.py`
--province default'u ("Samsun") TÜM Türkiye'ye yanlışlıkla uygulanmıştı.
Bu modül, hattın geometrisinden (koordinatından) gerçek ili nokta-poligon
testiyle otomatik tespit eder.

Kullanım:
    from turkey_provinces import detect_province
    il = detect_province(36.33, 41.29)   # -> "Samsun"
"""

import json
import os
from functools import lru_cache

from shapely.geometry import shape, Point

_GEOJSON_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "turkiye_il_sinirlari.geojson")


@lru_cache(maxsize=1)
def _load_provinces():
    """
    İl poligonlarını bir kere yükleyip belleğe alır (lru_cache sayesinde
    aynı process içinde tekrar tekrar diskten okunmaz). Her il için
    shapely.prepared.prep() ile "hazırlanmış" geometri kullanılır —
    binlerce nokta testi yapılacaksa bu, ham geometriye göre belirgin
    şekilde daha hızlıdır.
    """
    from shapely.prepared import prep

    with open(_GEOJSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    provinces = []
    for feature in data["features"]:
        name = feature["properties"]["name"]
        geom = shape(feature["geometry"])
        provinces.append((name, geom, prep(geom), geom.centroid))
    return provinces


def detect_province(lon: float, lat: float) -> "str | None":
    """
    Verilen koordinatın içine düştüğü ili döner. Tam olarak hiçbir
    poligonun içine düşmüyorsa (örn. kıyı şeridi/adalar gibi sınır
    hassasiyeti nedeniyle veri setindeki basitleştirilmiş poligonun
    tam dışında kalan noktalar), en yakın ilin merkezine göre bir
    tahminde bulunur — bu durumlarda sonuç kesin değil, yaklaşıktır.

    Türkiye sınırları tamamen dışında kalan bir koordinat verilirse
    yine de en yakın ile "tahmin" döner; sonucu kullanmadan önce
    makul bir mesafede olup olmadığını kontrol etmek istersen
    detect_province_with_distance() kullan.
    """
    result, _ = detect_province_with_distance(lon, lat)
    return result


def detect_province_with_distance(lon: float, lat: float):
    """
    (il_adı, kesin_mi) çifti döner. kesin_mi=True ise nokta gerçekten
    ilin poligonu içinde; False ise en yakın il merkezine göre tahmin
    edilmiş demektir (sonucu SQL'e yazarken bir uyarı/log ile
    işaretlemek isteyebilirsin).
    """
    point = Point(lon, lat)
    provinces = _load_provinces()

    for name, geom, prepared, _centroid in provinces:
        if prepared.contains(point):
            return name, True

    # Kesin eşleşme yoksa (kıyı/ada gibi sınır durumları), merkezine en
    # yakın ili tahmini olarak döndür.
    nearest_name = min(provinces, key=lambda p: p[3].distance(point))[0]
    return nearest_name, False


def detect_province_for_line(coords: "list[tuple[float, float]]") -> "tuple[str | None, bool]":
    """
    Bir hattın (LineString) tüm köşe noktalarının orta noktasını
    (basit ortalama, hattın gerçek orta noktası değil ama il tespiti
    için yeterince yakın) kullanarak ili tespit eder. Çok uzun hatlar
    iki ilin sınırında kalabilir; bu durumda "en fazla noktanın düştüğü
    il" mantığı daha isabetli olur — bkz. detect_province_majority.
    """
    if not coords:
        return None, False
    mean_lon = sum(c[0] for c in coords) / len(coords)
    mean_lat = sum(c[1] for c in coords) / len(coords)
    return detect_province_with_distance(mean_lon, mean_lat)


def detect_province_majority(coords: "list[tuple[float, float]]") -> "tuple[str | None, bool]":
    """
    Hattın İKİ İLİN SINIRINDA kalma ihtimaline karşı daha sağlam bir
    yöntem: her köşe noktası için ayrı ayrı il tespiti yapıp en sık
    çıkan ili döner (çoğunluk oyu). Uzun/sınır hatları için
    detect_province_for_line()'dan daha isabetlidir, ama N kat daha
    fazla nokta-poligon testi çalıştırır (N = köşe sayısı).
    """
    if not coords:
        return None, False
    from collections import Counter

    votes = Counter()
    any_exact = False
    for lon, lat in coords:
        name, exact = detect_province_with_distance(lon, lat)
        if name:
            votes[name] += 1
            any_exact = any_exact or exact
    if not votes:
        return None, False
    winner = votes.most_common(1)[0][0]
    return winner, any_exact


if __name__ == "__main__":
    # Hızlı manuel test: Samsun merkez, Ankara merkez, Adana civarı
    tests = [
        ("Samsun merkez", 36.33, 41.29),
        ("Ankara merkez", 32.85, 39.93),
        ("Adana civarı", 35.30, 37.00),
    ]
    for label, lon, lat in tests:
        name, exact = detect_province_with_distance(lon, lat)
        print(f"{label}: {name} ({'kesin' if exact else 'tahmini'})")
