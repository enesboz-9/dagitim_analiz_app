-- supabase_rpc_upsert_power_line.sql
-- ---------------------------------------------------------------------------
-- Supabase SQL Editor'da BİR KEZ çalıştırılması gereken kurulum.
--
-- import_power_lines.py --mode rpc kullanıldığında, her hat için bu RPC
-- fonksiyonu çağrılır. PostgREST geometry kolonlarına doğrudan WKT
-- yazılmasına izin vermediği için (insert_ndvi_measurement RPC'sindeki
-- ile aynı sebep), WKT -> geometry dönüşümü burada sunucu tarafında
-- yapılıyor. external_id üzerinden ON CONFLICT ile upsert yapıldığından,
-- aynı hat tekrar import edilirse (veri güncellendiğinde) yeni satır
-- oluşmaz, mevcut satır güncellenir.
--
-- ÖNKOŞUL:
--   1. PostGIS eklentisi açık olmalı (bkz. supabase_rpc_insert_ndvi.sql)
--   2. supabase_add_external_id.sql BİR KEZ çalıştırılmış olmalı
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION upsert_power_line(
    p_external_id TEXT,
    p_name TEXT,
    p_province TEXT,
    p_voltage_level TEXT,
    p_line_wkt TEXT,
    p_buffer_wkt TEXT
) RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    result_id UUID;
BEGIN
    INSERT INTO power_lines
        (external_id, name, province, voltage_level, geom, buffer_geom)
    VALUES
        (p_external_id, p_name, p_province, p_voltage_level,
         ST_GeomFromText(p_line_wkt, 4326),
         ST_GeomFromText(p_buffer_wkt, 4326))
    ON CONFLICT (external_id) DO UPDATE SET
        name = EXCLUDED.name,
        province = EXCLUDED.province,
        voltage_level = EXCLUDED.voltage_level,
        geom = EXCLUDED.geom,
        buffer_geom = EXCLUDED.buffer_geom
    RETURNING id INTO result_id;

    RETURN result_id;
END;
$$;

-- Not (SECURITY DEFINER): insert_ndvi_measurement'taki ile aynı gerekçe —
-- çağıran rolün power_lines'a doğrudan INSERT/UPDATE yetkisi olmasa bile
-- fonksiyon sahibinin yetkisiyle çalışır. İstemiyorsan SECURITY DEFINER
-- satırını kaldır (satırı tamamen silmen SECURITY INVOKER'a eşdeğerdir).

-- Test (Supabase SQL Editor'da elle çalıştırıp kontrol edebilirsin):
-- SELECT upsert_power_line(
--     'test-external-id-1',
--     'Test Hattı 2',
--     'Samsun',
--     'OG',
--     'LINESTRING (36.33 41.287, 36.345 41.295)',
--     'POLYGON ((36.34486223259328 41.29514696232078, 36.34513776679805 41.29485303753426, 36.33013778604036 41.2868530547162, 36.32986221335108 41.2871469451387, 36.34486223259328 41.29514696232078))'
-- );
