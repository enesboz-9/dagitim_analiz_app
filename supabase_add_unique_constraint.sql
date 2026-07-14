-- supabase_add_unique_constraint.sql
-- ---------------------------------------------------------------------------
-- Supabase SQL Editor'da BİR KEZ çalıştır. ndvi_measurements tablosuna
-- (line_id, measurement_date) üzerinde bir unique constraint ekler, böylece
-- run_test.py aynı hat + aynı tarih için tekrar çalıştırıldığında duplicate
-- satır birikmez.
--
-- ÖNEMLİ: Eğer tabloda hâlâ eski (dataMask-tabanlı, yanlış cloud_cover_pct
-- içeren) test satırları varsa, constraint eklemeden ÖNCE onları temizle,
-- yoksa "could not create unique index" hatası alırsın:
--
--   DELETE FROM ndvi_measurements WHERE line_id = '<eski_test_line_id>';
--
-- ---------------------------------------------------------------------------

ALTER TABLE ndvi_measurements
    ADD CONSTRAINT ndvi_measurements_line_date_unique
    UNIQUE (line_id, measurement_date);
