-- supabase_rpc_get_power_lines.sql
-- ---------------------------------------------------------------------------
-- Supabase SQL Editor'da BİR KEZ çalıştırılması gereken kurulum.
--
-- Production pipeline'ın (run_pipeline.py) tek bir --line-id yerine
-- power_lines tablosundaki TÜM hatları otomatik işleyebilmesi için,
-- her satırın buffer_geom kolonunu GeoJSON + WKT olarak döndüren bir
-- RPC fonksiyonu tanımlıyoruz. PostgREST, geometry kolonlarını
-- doğrudan sorgularsa (hex EWKB gibi) uygulama tarafında işlenmesi
-- zor bir formatta döndürdüğü için bu dönüşümü sunucu tarafında
-- (ST_AsGeoJSON / ST_AsText ile) yapıyoruz.
--
-- Önkoşul: PostGIS eklentisi açık olmalı:
--   CREATE EXTENSION IF NOT EXISTS postgis;
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION get_active_power_lines()
RETURNS TABLE (
    line_id UUID,
    line_name TEXT,
    corridor_geojson JSON,
    corridor_wkt TEXT
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        id AS line_id,
        name AS line_name,
        ST_AsGeoJSON(buffer_geom)::json AS corridor_geojson,
        ST_AsText(buffer_geom) AS corridor_wkt
    FROM power_lines
    WHERE buffer_geom IS NOT NULL;
$$;

-- Test (Supabase SQL Editor'da elle çalıştırıp kontrol edebilirsin):
-- SELECT * FROM get_active_power_lines();

-- NOT: İleride power_lines tablosuna bir "is_active boolean default true"
-- kolonu eklersen, yukarıdaki WHERE satırını
--   WHERE buffer_geom IS NOT NULL AND is_active = true
-- olarak güncelleyip pasif/silinmiş hatları pipeline'dan hariç tutabilirsin.
