-- supabase_rpc_insert_ndvi.sql
-- ---------------------------------------------------------------------------
-- Supabase SQL Editor'da BİR KEZ çalıştırılması gereken kurulum.
-- PostgREST, `geometry` tipi kolonlara doğrudan WKT string yazılmasına
-- izin vermediği için, WKT -> geometry dönüşümünü sunucu tarafında
-- yapan bir RPC fonksiyonu tanımlıyoruz.
--
-- Önkoşul: PostGIS eklentisi açık olmalı (Supabase'de genelde varsayılan
-- olarak kurulu gelir; değilse önce şunu çalıştır):
--   CREATE EXTENSION IF NOT EXISTS postgis;
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION insert_ndvi_measurement(
    p_line_id UUID,
    p_segment_wkt TEXT,
    p_measurement_date DATE,
    p_ndvi_mean FLOAT,
    p_ndvi_max FLOAT,
    p_cloud_cover_pct FLOAT,
    p_source TEXT
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    new_id UUID;
BEGIN
    INSERT INTO ndvi_measurements
        (line_id, segment_geom, measurement_date, ndvi_mean, ndvi_max, cloud_cover_pct, source)
    VALUES
        (p_line_id, ST_GeomFromText(p_segment_wkt, 4326), p_measurement_date,
         p_ndvi_mean, p_ndvi_max, p_cloud_cover_pct, p_source)
    RETURNING id INTO new_id;

    RETURN new_id;
END;
$$;

-- Not (SECURITY DEFINER): Bu fonksiyon, çağıran rolün (service_role veya
-- anon key ile gelen kullanıcı) ndvi_measurements tablosuna doğrudan
-- INSERT yetkisi olmasa bile fonksiyon sahibinin (genelde postgres/owner)
-- yetkisiyle çalışır. Eğer bunu istemiyorsan (yani sadece zaten INSERT
-- yetkisi olan roller çağırabilsin istiyorsan) SECURITY DEFINER satırını
-- kaldırıp SECURITY INVOKER kullan (varsayılan zaten budur, satırı
-- tamamen silmen yeterli).

-- Test (Supabase SQL Editor'da elle çalıştırıp kontrol edebilirsin):
-- SELECT insert_ndvi_measurement(
--     '00000000-0000-0000-0000-000000000000'::uuid,  -- gerçek bir power_lines UUID'si ile değiştir
--     'POLYGON((0 0, 0 1, 1 1, 1 0, 0 0))',
--     '2026-01-15',
--     0.42, 0.61, 12.5, 'sentinel2'
-- );
