"""
sentinel_api.py
----------------
Sentinel Hub Statistical API'ye NDVI istatistiği isteği atar ve
JSON yanıtını `ndvi_measurements` tablosuna yazılabilecek düz
(flat) kayıt listesine çevirir.
"""

import requests
from auth import get_access_token

STATISTICS_URL = "https://sh.dataspace.copernicus.eu/api/v1/statistics"

# Bölüm 3.1'deki evalscript — NDVI + SCL bulut maskeleme
EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B04", "B08", "SCL", "dataMask"]
    }],
    output: [
      { id: "ndvi", bands: 1 },
      { id: "dataMask", bands: 1 }
    ]
  };
}

function evaluatePixel(samples) {
  let ndvi = (samples.B08 - samples.B04) / (samples.B08 + samples.B04);
  // SCL: 3=bulut golgesi, 8/9=bulut, 10=ince bulut
  let isCloud = [3, 8, 9, 10].includes(samples.SCL);
  let mask = (samples.dataMask === 1 && !isCloud) ? 1 : 0;
  return {
    ndvi: [ndvi],
    dataMask: [mask]
  };
}
"""


def fetch_ndvi_statistics(corridor_geojson: dict, date_from: str, date_to: str,
                           aggregation_days: int = 30) -> dict:
    """
    Verilen koridor polygonu için Statistical API'den NDVI zaman serisi çeker.

    Parametreler
    ------------
    corridor_geojson : dict
        geometry.build_test_corridor() içinden gelen "corridor_geojson" alanı.
    date_from, date_to : str
        ISO 8601 formatında tarih aralığı, örn "2023-01-01T00:00:00Z"
    aggregation_days : int
        Kaç günlük aralıklarla agregasyon yapılacağı (P30D için 30 gir).

    Döndürür
    --------
    dict : API'nin ham JSON yanıtı
    """
    token = get_access_token()

    body = {
        "input": {
            "bounds": {"geometry": corridor_geojson},
            "data": [{"type": "sentinel-2-l2a"}],
        },
        "aggregation": {
            "timeRange": {"from": date_from, "to": date_to},
            "aggregationInterval": {"of": f"P{aggregation_days}D"},
            "evalscript": EVALSCRIPT,
        },
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    response = requests.post(STATISTICS_URL, json=body, headers=headers, timeout=60)
    response.raise_for_status()
    return response.json()


def parse_statistics_response(raw_response: dict) -> list[dict]:
    """
    Statistical API'nin ham JSON yanıtını, ndvi_measurements tablosuna
    yazılabilecek düz kayıt listesine çevirir.

    Beklenen çıktı formatı (her eleman bir satır):
        {
            "measurement_date": "2023-01-15",
            "ndvi_mean": 0.42,
            "ndvi_max": 0.61,
            "cloud_cover_pct": 12.5,
        }

    NOT (doğrulandı): Gerçek API yanıtında ayrı bir "dataMask" çıktısı
    yok. "ndvi" çıktısının "stats" bloğu içinde zaten "sampleCount" ve
    "noDataCount" alanları geliyor; bulut/geçersiz piksel oranı
    doğrudan bunlardan hesaplanıyor:
        cloud_cover_pct = noDataCount / sampleCount * 100
    """
    records = []

    for interval_data in raw_response.get("data", []):
        interval = interval_data.get("interval", {})
        from_date = interval.get("from", "")[:10]  # "2023-01-01T00:00:00Z" -> "2023-01-01"

        outputs = interval_data.get("outputs", {})
        ndvi_stats = outputs.get("ndvi", {}).get("bands", {}).get("B0", {}).get("stats", {})

        sample_count = ndvi_stats.get("sampleCount")
        no_data_count = ndvi_stats.get("noDataCount")
        cloud_cover_pct = (
            round((no_data_count / sample_count) * 100, 2)
            if sample_count else None
        )

        records.append({
            "measurement_date": from_date,
            "ndvi_mean": ndvi_stats.get("mean"),
            "ndvi_max": ndvi_stats.get("max"),
            "cloud_cover_pct": cloud_cover_pct,
            "source": "sentinel2",
        })

    return records
