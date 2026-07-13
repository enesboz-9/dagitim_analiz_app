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

from shapely.geometry import LineString, Polygon, mapping
from pyproj import Transformer

# Samsun kırsalında örnek bir OG hattı güzergahı (lon, lat sırasıyla, WGS84 / EPSG:4326)
# Not: Bu sadece pipeline'ı test etmek için seçilmiş 2 noktalı basit bir hat.
# Gerçek kullanımda çok noktalı (multi-vertex) bir LineString olacaktır.
TEST_LINE_COORDS = [
    (36.3300, 41.2870),  # başlangıç noktası
    (36.3450, 41.2950),  # bitiş noktası
]

WGS84_EPSG = "EPSG:4326"


def _utm_epsg_for_lon(lon: float) -> str:
    """
    Verilen boylama (lon) göre en uygun kuzey yarımküre UTM diliminin
    EPSG kodunu döner. Samsun (~36-37 derece) UTM 36N (EPSG:32636)
    içine düşer, ama YEDAŞ dağıtım bölgesi (Samsun/Amasya/Çorum/Sinop)
    sınır bölgelerde 35N/37N'e de kayabilir. Gerçek hat verisiyle
    (birden fazla ilçe/il) çalışırken bunu sabit kodlamak yerine
    her hat için merkez boylamdan otomatik hesaplıyoruz, aksi halde
    dilim sınırına yakın hatlarda buffer mesafesi hafifçe bozulur.
    """
    zone = int((lon + 180) / 6) + 1
    return f"EPSG:{32600 + zone}"


def build_corridor(coords: "list[tuple[float, float]]", buffer_meters: float = 20.0):
    """
    Genel amaçlı emniyet mesafesi zarfı (buffer polygon) üretici.
    Hem test hattı (TEST_LINE_COORDS) hem de gerçek YEDAŞ hatları
    (bkz. import_power_lines.py) için kullanılır.

    Parametreler
    ------------
    coords : list[(lon, lat)]
        Hattın köşe noktaları, WGS84 (EPSG:4326), en az 2 nokta.
    buffer_meters : float
        Hattın her iki yanına uygulanacak buffer mesafesi (metre).
        OG hatları için tipik değer aralığı ~15-25m, ihtiyaca göre ayarla.

    Döndürür
    --------
    dict
        {
            "line_geojson": <hattın kendisinin GeoJSON'u, WGS84>,
            "line_wkt": <hattın kendisinin WKT'si, WGS84>,
            "corridor_geojson": <buffer edilmiş polygon'un GeoJSON'u, WGS84>,
            "corridor_wkt": <aynı polygon, WKT formatında (DB'ye yazarken işine yarar)>
        }
    """
    if len(coords) < 2:
        raise ValueError("build_corridor en az 2 noktalı bir hat bekliyor.")

    line_wgs84 = LineString(coords)

    # Hattın merkez boylamına göre doğru UTM dilimini otomatik seç.
    mean_lon = sum(x for x, _ in coords) / len(coords)
    utm_epsg = _utm_epsg_for_lon(mean_lon)

    to_utm = Transformer.from_crs(WGS84_EPSG, utm_epsg, always_xy=True)
    to_wgs84 = Transformer.from_crs(utm_epsg, WGS84_EPSG, always_xy=True)

    utm_coords = [to_utm.transform(x, y) for x, y in coords]
    line_utm = LineString(utm_coords)

    # Buffer: cap_style=2 -> flat uçlar (hat segmenti mantığına daha uygun)
    corridor_utm = line_utm.buffer(buffer_meters, cap_style=2)

    # Geri WGS84'e projekte et
    corridor_wgs84_coords = [to_wgs84.transform(x, y) for x, y in corridor_utm.exterior.coords]
    corridor_wgs84 = Polygon(corridor_wgs84_coords)

    return {
        "line_geojson": mapping(line_wgs84),
        "line_wkt": line_wgs84.wkt,
        "corridor_geojson": mapping(corridor_wgs84),
        "corridor_wkt": corridor_wgs84.wkt,
    }


def build_test_corridor(buffer_meters: float = 20.0):
    """Geriye dönük uyumluluk: sadece TEST_LINE_COORDS ile build_corridor çağırır."""
    return build_corridor(TEST_LINE_COORDS, buffer_meters=buffer_meters)


if __name__ == "__main__":
    # Hızlı manuel test
    import json
    result = build_test_corridor(buffer_meters=20.0)
    print("Corridor GeoJSON:")
    print(json.dumps(result["corridor_geojson"], indent=2))
    print("\nCorridor WKT (ilk 120 karakter):")
    print(result["corridor_wkt"][:120] + "...")
