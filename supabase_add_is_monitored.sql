-- supabase_add_is_monitored.sql
-- ---------------------------------------------------------------------------
-- Supabase SQL Editor'da BİR KEZ çalıştır. supabase_add_external_id.sql'den
-- SONRA, supabase_rpc_get_power_lines.sql'i GÜNCELLEMEDEN ÖNCE çalıştırılmalı.
--
-- NEDEN: Türkiye genelinde OSM'den çekilen ~15.000 hattın TAMAMINI
-- power_lines tablosuna aktarmak istiyoruz (harita hepsini göstersin),
-- ama Sentinel Hub Statistical API'nin her ay TÜM bu hatlar için otomatik
-- çalıştırılması kredi/kotayı çok hızlı tüketir. Çözüm: her hat için
-- "is_monitored" bayrağı — sadece bu bayrağı true olan (öncelikli/gerçek
-- YEDAŞ koridoru olduğu bilinen) hatlar run_pipeline.py tarafından OTOMATİK
-- işlenir. Geri kalan tüm hatlar haritada görünmeye devam eder ("veri yok"
-- gri renkte), ve istenildiğinde run_pipeline.py --province / --external-ids
-- ile MANUEL olarak sorgulanabilir.
-- ---------------------------------------------------------------------------

ALTER TABLE power_lines ADD COLUMN IF NOT EXISTS is_monitored BOOLEAN NOT NULL DEFAULT false;

-- Manuel/toplu import sonrası hangi hatların otomatik izlemeye alınacağını
-- seçmek için mark_monitored.py kullan, örn:
--   python mark_monitored.py --province Samsun
--   python mark_monitored.py --external-ids way/12345,way/67890

-- Test (Supabase SQL Editor'da elle çalıştırıp kontrol edebilirsin):
-- SELECT province, count(*) FILTER (WHERE is_monitored) AS izlenen,
--        count(*) AS toplam
-- FROM power_lines GROUP BY province ORDER BY toplam DESC;
