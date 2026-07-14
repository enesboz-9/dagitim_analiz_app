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


def get_active_power_lines(only_monitored: bool = True,
                            external_ids: "list[str] | None" = None,
                            province: "str | None" = None) -> list[dict]:
    """
    power_lines tablosundaki hatları, her biri için hazır corridor_geojson /
    corridor_wkt alanlarıyla birlikte döner.

    ÖNKOŞUL: Supabase'de `supabase_add_is_monitored.sql` VE
    `supabase_rpc_get_power_lines.sql` dosyalarındaki kurulum bir kez
    yapılmış olmalı.

    Parametreler
    ------------
    only_monitored : bool
        True (varsayılan) ise SADECE is_monitored=true olan (öncelikli,
        gerçek koridor olduğu bilinen) hatları döner. Zamanlanmış/otomatik
        çalıştırmalar (run_pipeline.py, GitHub Actions) için varsayılan
        budur — Türkiye genelinde binlerce hat import edilmiş olsa bile
        Sentinel Hub kredisi sadece işaretlenen küçük öncelikli alt kümede
        harcanır.
    external_ids, province : opsiyonel
        Belirtilirse (manuel/on-demand çalıştırma), only_monitored=false
        olsa bile is_monitored bayrağından bağımsız olarak bu il'e /
        external_id listesine ait hatları döner. Bkz. run_pipeline.py
        --province / --external-ids.

    Döndürür
    --------
    list[dict] : her biri {"line_id", "line_name", "corridor_geojson", "corridor_wkt"}
    anahtarlarını içeren kayıtlar.
    """
    client = get_supabase_client()
    params = {"p_only_monitored": only_monitored}
    if external_ids:
        params["p_external_ids"] = external_ids
    if province:
        params["p_province"] = province
    response = client.rpc("get_active_power_lines", params).execute()
    return response.data or []


def insert_ndvi_measurements(line_id: str, corridor_wkt: str, records: list[dict]) -> int:
    """
    Ayrıştırılmış NDVI kayıtlarını ndvi_measurements tablosuna yazar.

    ÖNKOŞUL: Supabase'de `supabase_rpc_insert_ndvi.sql` dosyasındaki
    `insert_ndvi_measurement` fonksiyonu bir kez oluşturulmuş olmalı.
    PostgREST, `geometry` tipi kolonlara doğrudan WKT string yazılmasına
    izin vermediği için, WKT -> geometry dönüşümü (ST_GeomFromText) bu
    RPC fonksiyonu üzerinden sunucu tarafında yapılıyor.

    Parametreler
    ------------
    line_id : str
        power_lines tablosundaki ilgili hattın UUID'si.
        (Henüz gerçek bir power_lines kaydın yoksa, test amaçlı
        önce power_lines tablosuna bir satır ekleyip o UUID'yi buraya ver.)
    corridor_wkt : str
        geometry.build_test_corridor() çıktısındaki "corridor_wkt".
        RPC içinde ST_GeomFromText(..., 4326) ile geometry'e çevrilir.
    records : list[dict]
        sentinel_api.parse_statistics_response() çıktısı.

    Döndürür
    --------
    int : başarıyla eklenen satır sayısı
    """
    client = get_supabase_client()

    inserted = 0
    for r in records:
        response = client.rpc("insert_ndvi_measurement", {
            "p_line_id": line_id,
            "p_segment_wkt": corridor_wkt,
            "p_measurement_date": r["measurement_date"],
            "p_ndvi_mean": r["ndvi_mean"],
            "p_ndvi_max": r["ndvi_max"],
            "p_cloud_cover_pct": r["cloud_cover_pct"],
            "p_source": r["source"],
        }).execute()

        # RPC scalar (UUID) döndürür; başarılı ise response.data dolu gelir.
        if response.data:
            inserted += 1

    return inserted
