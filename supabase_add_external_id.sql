-- supabase_add_external_id.sql
-- ---------------------------------------------------------------------------
-- Supabase SQL Editor'da BİR KEZ çalıştır.
--
-- Gerçek YEDAŞ hat verisini (GeoJSON/shapefile) import_power_lines.py ile
-- İÇE AKTARIRKEN, aynı script'i tekrar çalıştırdığında (veri güncellendiğinde,
-- ya da script yarıda kesilip tekrar başlatıldığında) power_lines tablosunda
-- duplicate satır oluşmaması için, YEDAŞ kaynağındaki hattın kendi kimliğini
-- (örn. şebeke bilgi sisteminden gelen hat kodu / OSM way id) tutan bir
-- external_id kolonu ekliyoruz. Bu kolon UNIQUE ama NULL'a izin veriyor,
-- böylece elle eklenmiş eski test satırları (power_lines_test_insert.sql)
-- bozulmaz.
-- ---------------------------------------------------------------------------

ALTER TABLE power_lines ADD COLUMN IF NOT EXISTS external_id TEXT UNIQUE;

-- Test (Supabase SQL Editor'da elle çalıştırıp kontrol edebilirsin):
-- SELECT id, name, external_id FROM power_lines;
