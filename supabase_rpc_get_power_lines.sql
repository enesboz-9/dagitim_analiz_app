-- supabase_rpc_get_power_lines.sql
-- ---------------------------------------------------------------------------
-- Supabase SQL Editor'da çalıştır (var olan fonksiyonun üzerine yazar).
-- ÖNKOŞUL: supabase_add_is_monitored.sql daha önce çalıştırılmış olmalı.
--
-- run_pipeline.py'nin (production, Sentinel Hub kredisi tüketen kısım)
-- hangi hatları işleyeceğini belirler:
--   - Parametresiz / varsayılan çağrı (p_only_monitored=true) -> SADECE
--     is_monitored=true olan (öncelikli/gerçek koridor) hatları döner.
--     Zamanlanmış GitHub Actions çalıştırması bunu kullanır, kredi israf
--     etmez.
--   - p_only_monitored=false ve/veya p_province / p_external_ids verilirse
--     -> manuel/on-demand çalıştırma: belirli il(ler) ya da belirli
--     external_id'lere sahip hatları (izlemede olsun olmasın) döner.
--     Bkz. run_pipeline.py --all / --province / --external-ids.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION get_active_power_lines(
    p_only_monitored boolean DEFAULT true,
    p_external_ids text[] DEFAULT NULL,
    p_province text DEFAULT NULL
)
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
    WHERE buffer_geom IS NOT NULL
      AND (p_only_monitored = false OR is_monitored = true)
      AND (p_external_ids IS NULL OR external_id = ANY(p_external_ids))
      AND (p_province IS NULL OR province = p_province);
$$;

-- Test (Supabase SQL Editor'da elle çalıştırıp kontrol edebilirsin):
-- SELECT * FROM get_active_power_lines();                              -- sadece izlenen hatlar
-- SELECT * FROM get_active_power_lines(false, NULL, 'Samsun');         -- Samsun'daki TÜM hatlar
-- SELECT * FROM get_active_power_lines(false, ARRAY['way/12345']);     -- belirli hat(lar)
