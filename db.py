"""
db.py
-----
Supabase'e bağlanıp `ndvi_measurements` tablosuna kayıt yazar.

.env dosyasında şunlar tanımlı olmalı:
    SUPABASE_URL=https://xxxx.supabase.co
    SUPABASE_KEY=...   (service_role key önerilir; bu script backend/pipeline tarafında koşacak)

Kurulum: pip install supabase
"""

import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()


def get_supabase_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL / SUPABASE_KEY .env dosyasında bulunamadı.")
    return create_client(url, key)


def insert_ndvi_measurements(line_id: str, corridor_wkt: str, records: list[dict]) -> int:
    """
    Ayrıştırılmış NDVI kayıtlarını ndvi_measurements tablosuna yazar.

    Parametreler
    ------------
    line_id : str
        power_lines tablosundaki ilgili hattın UUID'si.
        (Henüz gerçek bir power_lines kaydın yoksa, test amaçlı
        önce power_lines tablosuna bir satır ekleyip o UUID'yi buraya ver.)
    corridor_wkt : str
        geometry.build_test_corridor() çıktısındaki "corridor_wkt".
        segment_geom kolonuna PostGIS'in anlayacağı formatta yazılır.
    records : list[dict]
        sentinel_api.parse_statistics_response() çıktısı.

    Döndürür
    --------
    int : eklenen satır sayısı
    """
    client = get_supabase_client()

    rows = []
    for r in records:
        rows.append({
            "line_id": line_id,
            # Supabase PostgREST üzerinden PostGIS geometry kolonuna WKT yazmak için
            # genelde bir SQL fonksiyonu / RPC ya da ST_GeomFromText çağrısı gerekir.
            # Basit bir yol: tabloda segment_geom kolonunu `geometry` yerine
            # `text` alan + bir trigger ile geometry'e çevirmek, ya da
            # burada RPC (bkz. aşağıdaki not) kullanmak.
            "segment_geom": corridor_wkt,
            "measurement_date": r["measurement_date"],
            "ndvi_mean": r["ndvi_mean"],
            "ndvi_max": r["ndvi_max"],
            "cloud_cover_pct": r["cloud_cover_pct"],
            "source": r["source"],
        })

    if not rows:
        return 0

    result = client.table("ndvi_measurements").insert(rows).execute()
    return len(result.data) if result.data else 0


# ---------------------------------------------------------------------------
# NOT (PostGIS + Supabase PostgREST uyumu hakkında):
# Supabase'in otomatik REST API'si (PostgREST), `geometry` tipi kolonlara
# doğrudan WKT string'i yazmaya izin vermeyebilir; PostGIS geometry kolonu
# genelde WKB/hex ya da GeoJSON bekler, RPC üzerinden de yapılabilir.
# En sağlam çözüm: Supabase'de aşağıdaki gibi bir SQL fonksiyonu tanımlayıp
# buradan `client.rpc(...)` ile çağırmak:
#
#   CREATE OR REPLACE FUNCTION insert_ndvi_measurement(
#       p_line_id UUID,
#       p_segment_wkt TEXT,
#       p_measurement_date DATE,
#       p_ndvi_mean FLOAT,
#       p_ndvi_max FLOAT,
#       p_cloud_cover_pct FLOAT,
#       p_source TEXT
#   ) RETURNS UUID AS $$
#   DECLARE new_id UUID;
#   BEGIN
#       INSERT INTO ndvi_measurements
#           (line_id, segment_geom, measurement_date, ndvi_mean, ndvi_max, cloud_cover_pct, source)
#       VALUES
#           (p_line_id, ST_GeomFromText(p_segment_wkt, 4326), p_measurement_date,
#            p_ndvi_mean, p_ndvi_max, p_cloud_cover_pct, p_source)
#       RETURNING id INTO new_id;
#       RETURN new_id;
#   END;
#   $$ LANGUAGE plpgsql;
#
# Bu henüz kurulmadı — ilk gerçek test çalıştırmasında bu adımı
# tamamlaman gerekecek (yukarıdaki insert_ndvi_measurements fonksiyonunu
# rpc çağrısına çevirerek).
# ---------------------------------------------------------------------------
