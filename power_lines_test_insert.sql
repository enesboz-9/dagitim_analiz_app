-- power_lines_test_insert.sql
-- ---------------------------------------------------------------------------
-- Supabase SQL Editor'da çalıştırıp dönen UUID'yi kopyala; bu UUID'yi
-- "python run_test.py --line-id <uuid>" komutunda kullanacaksın.
--
-- geom / buffer_geom değerleri geometry.py'deki TEST_LINE_COORDS'tan
-- (Samsun kırsalında örnek bir test hattı, buffer=20m) üretildi.
-- ---------------------------------------------------------------------------

INSERT INTO power_lines (name, province, voltage_level, geom, buffer_geom)
VALUES (
    'Test Hattı - Samsun kırsalı (pipeline test)',
    'Samsun',
    'OG',  -- gerekirse gerçek gerilim seviyesiyle değiştir (örn. 'AG', 'YG')
    ST_GeomFromText('LINESTRING (36.33 41.287, 36.345 41.295)', 4326),
    ST_GeomFromText('POLYGON ((36.34486223259328 41.29514696232078, 36.34513776679805 41.29485303753426, 36.33013778604036 41.2868530547162, 36.32986221335108 41.2871469451387, 36.34486223259328 41.29514696232078))', 4326)
)
RETURNING id;

-- Yukarıdaki sorguyu çalıştırdıktan sonra dönen "id" sütunundaki UUID'yi kopyala.
-- Örnek kullanım:
--   python run_test.py --line-id <buraya_gelen_uuid>
