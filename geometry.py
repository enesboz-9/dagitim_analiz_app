"""
geometry.py
-----------
Test amaçlı örnek bir hat koridoru (LineString) oluşturur ve bunu
emniyet mesafesi zarfı (buffer polygon) haline getirir.

ÖNEMLİ: Aşağıdaki koordinatlar GERÇEK bir YEDAŞ hattı DEĞİLDİR.
Samsun kırsalında, kod/pipeline'ı uçtan uca test etmek için seçilmiş
plausible (mantıklı görünen) bir örnek güzergahtır. Gerçek hat
verisi (YEDAŞ'tan shapefile/GeoJSON ya da OSM'den çekilen veri)
geldiğinde, sadece `TEST_LINE_COORDS` listesini değiştirmen yeterli;
geri kalan pipeline (buffer, Statistical API isteği, DB yazımı)
aynı şekilde çalışmaya devam eder.
"""

from shapely.geometry import LineString, mapping
from pyproj import Transformer

# Samsun kırsalında örnek bir OG hattı güzergahı (lon, lat sırasıyla, WGS84 / EPSG:4326)
# Not: Bu sadece pipeline'ı test etmek için seçilmiş 2 noktalı basit bir hat.
# Gerçek kullanımda çok noktalı (multi-vertex) bir LineString olacaktır.
TEST_LINE_COORDS = [
    (36.3300, 41.2870),  # başlangıç noktası
    (36.3450, 41.2950),  # bitiş noktası
]

# Samsun ili yaklaşık olarak UTM 36N diliminde (EPSG:32636).
# Buffer işlemini metre cinsinden yapabilmek için önce bu projeksiyona geçiyoruz.
UTM_EPSG = "EPSG:32636"
WGS84_EPSG = "EPSG:4326"


def build_test_corridor(buffer_meters: float = 20.0):
    """
    Test hattı için emniyet mesafesi zarfını (buffer polygon) üretir.

    Parametreler
    ------------
    buffer_meters : float
        Hattın her iki yanına uygulanacak buffer mesafesi (metre).
        OG hatları için tipik değer aralığı ~15-25m, ihtiyaca göre ayarla.

    Döndürür
    --------
    dict
        {
            "line_geojson": <hattın kendisinin GeoJSON'u, WGS84>,
            "corridor_geojson": <buffer edilmiş polygon'un GeoJSON'u, WGS84>,
            "corridor_wkt": <aynı polygon, WKT formatında (DB'ye yazarken işine yarar)>
        }
    """
    line_wgs84 = LineString(TEST_LINE_COORDS)

    # WGS84 -> UTM (metre bazlı buffer için)
    to_utm = Transformer.from_crs(WGS84_EPSG, UTM_EPSG, always_xy=True)
    to_wgs84 = Transformer.from_crs(UTM_EPSG, WGS84_EPSG, always_xy=True)

    utm_coords = [to_utm.transform(x, y) for x, y in TEST_LINE_COORDS]
    line_utm = LineString(utm_coords)

    # Buffer: cap_style=2 -> flat uçlar (hat segmenti mantığına daha uygun)
    corridor_utm = line_utm.buffer(buffer_meters, cap_style=2)

    # Geri WGS84'e projekte et
    corridor_wgs84_coords = [to_wgs84.transform(x, y) for x, y in corridor_utm.exterior.coords]
    from shapely.geometry import Polygon
    corridor_wgs84 = Polygon(corridor_wgs84_coords)

    return {
        "line_geojson": mapping(line_wgs84),
        "corridor_geojson": mapping(corridor_wgs84),
        "corridor_wkt": corridor_wgs84.wkt,
    }


if __name__ == "__main__":
    # Hızlı manuel test
    import json
    result = build_test_corridor(buffer_meters=20.0)
    print("Corridor GeoJSON:")
    print(json.dumps(result["corridor_geojson"], indent=2))
    print("\nCorridor WKT (ilk 120 karakter):")
    print(result["corridor_wkt"][:120] + "...")
