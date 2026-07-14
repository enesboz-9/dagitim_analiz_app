-- supabase_view_power_line_risk_status.sql
-- ---------------------------------------------------------------------------
-- Supabase SQL Editor'da BİR KEZ çalıştır (ya da mevcut bir sürümün üzerine
-- yazmak için tekrar çalıştır). index.html (frontend) bu view'i
-- `client.from("power_line_risk_status").select("*")` ile okuyor.
--
-- ÖNEMLİ: LEFT JOIN kullanılıyor. Böylece henüz hiç NDVI ölçümü
-- (ndvi_measurements satırı) olmayan hatlar da SORGUDAN DÜŞMEZ —
-- risk_level='unknown' ("veri yok", gri) olarak haritada görünmeye devam
-- eder. Türkiye genelindeki ~15.000 hattı topluca import edip sadece bir
-- kısmını otomatik NDVI sorgusuna (is_monitored=true) sokmak istediğimiz
-- için bu kritik: aksi halde INNER JOIN kullanılsaydı, henüz sorgulanmamış
-- binlerce hat haritada hiç görünmezdi.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW power_line_risk_status AS
SELECT
    pl.id AS line_id,
    pl.name AS line_name,
    pl.province,
    pl.voltage_level,
    pl.is_monitored,
    ST_AsGeoJSON(pl.geom)::json AS line_geojson,
    -- Buffer (koridor) polygon'unu sadece gerçek bir NDVI ölçümü varsa
    -- döndürüyoruz: veri yok hatlar haritada kalın dolu poligon yerine
    -- ince bir çizgi olarak çizilsin diye (binlerce dolu poligon
    -- tarayıcıyı ciddi şekilde yavaşlatır, ince çizgi çok daha hafif).
    CASE WHEN latest.ndvi_mean IS NOT NULL
         THEN ST_AsGeoJSON(pl.buffer_geom)::json
         ELSE NULL
    END AS corridor_geojson,
    latest.ndvi_mean,
    latest.measurement_date,
    latest.cloud_cover_pct,
    CASE
        WHEN latest.ndvi_mean IS NULL THEN 'unknown'
        WHEN latest.ndvi_mean >= 0.60 THEN 'high'
        WHEN latest.ndvi_mean >= 0.35 THEN 'medium'
        ELSE 'low'
    END AS risk_level
FROM power_lines pl
LEFT JOIN LATERAL (
    SELECT nm.ndvi_mean, nm.measurement_date, nm.cloud_cover_pct
    FROM ndvi_measurements nm
    WHERE nm.line_id = pl.id
    ORDER BY nm.measurement_date DESC
    LIMIT 1
) latest ON true;

-- RLS/anon erişimi: view'in altındaki tablolarda (power_lines,
-- ndvi_measurements) zaten sadece SELECT'e izin veren bir policy olmalı.
-- Frontend anon key ile sadece okuma yapıyor (bkz. docs/index.html içindeki not).

-- Test (Supabase SQL Editor'da elle çalıştırıp kontrol edebilirsin):
-- SELECT risk_level, count(*) FROM power_line_risk_status GROUP BY risk_level;
