# YEDAŞ NDVI Test Pipeline (dagitim_analiz_app)

## GitHub'a yükleme

1. Bu zip'i aç, tüm dosyaları `dagitim_analiz_app` reposunu clone'ladığın
   klasöre (veya boş bir klasöre) çıkar.
2. `.env.example`'ı `.env` olarak kopyala ve gerçek Sentinel Hub / Supabase
   bilgilerini gir (bu dosya `.gitignore` sayesinde GitHub'a gitmeyecek).
3. `github_push.bat` dosyasına çift tıkla (ya da cmd'den çalıştır).
   Script sırasıyla: `git init` → `git add .` → `git commit` →
   `git branch -M main` → `git remote add origin` → `git push` yapar.
4. GitHub şifre yerine **Personal Access Token** isteyecektir
   (Settings → Developer settings → Personal access tokens → Generate new token,
   en azından `repo` yetkisiyle). Push sırasında kullanıcı adı olarak
   GitHub kullanıcı adını, şifre olarak bu token'ı gir.


Bölüm 3.1 ve 6'daki "eksik adımlar"dan şunları karşılar:
- Gerçek bir test koridoru için polygon (bkz. `geometry.py`)
- `get_access_token()` + Statistical API isteğini test etme (bkz. `auth.py`, `sentinel_api.py`)
- Statistical API sonucunu `ndvi_measurements` tablosuna yazan kod (bkz. `db.py`)

## Kurulum

```bash
pip install -r requirements.txt
cp .env.example .env
# .env dosyasını gerçek Sentinel Hub ve Supabase bilgileriyle doldur
```

## Kullanım

### 1. Önce dry-run ile geometri ve isteği kontrol et (kimlik bilgisi gerekmez)

```bash
python run_test.py --dry-run
```

Bu, test koridorunu üretir ve Statistical API'ye gidecek request body'sini
ekrana basar — henüz hiçbir gerçek istek atılmaz.

### 2. Gerçek çalıştırma

Önce Supabase'de `power_lines` tablosuna test amaçlı bir satır ekleyip
UUID'sini al (bkz. Bölüm 5'teki şema), sonra:

```bash
python run_test.py --line-id <power_lines_tablosundaki_uuid>
```

## Client rotate + token testi

1. Sentinel Hub Dashboard'da (https://shapps.dataspace.copernicus.eu/dashboard/)
   eski OAuth client'ı sil, yenisini oluştur, `.env`'e yaz.
2. Token'ın gerçekten çalıştığını doğrula:

   ```bash
   python test_auth.py                # token alır, JWT içeriğini (süre, scope) gösterir
   python test_auth.py --live-check    # ek olarak Statistical API'ye karşı gerçek bir test isteği atar
   ```

   `--live-check` ile 401 alırsan credentials hâlâ yanlış demektir; 400/422 alırsan
   (kasıtlı olarak eksik body gönderdiğimiz için beklenen budur) token'ın kendisi
   geçerli demektir.

## Yapman gerekenler (bu kod seni oraya kadar götürür, ama şunları
sen tamamlamalısın):

1. **Client rotate**: Yukarıdaki adımı tamamla (yapıldıysa işaretle).

2. **`sentinel_api.parse_statistics_response()` alan yollarını doğrula**:
   Kod, Statistical API'nin dokümantasyonundaki *tipik* yanıt şemasına göre
   yazıldı (`data[].outputs.ndvi.bands.B0.stats.mean` gibi), ama gerçek bir
   yanıtla henüz test edilmedi. İlk gerçek çalıştırmada yanıtı
   `print(json.dumps(raw_response, indent=2))` ile incele ve gerekirse
   alan yollarını düzelt.

3. **`db.py`'deki PostGIS/RPC kurulumunu tamamla**: Kod tarafı hazır —
   `insert_ndvi_measurements()` artık `client.rpc(...)` ile
   `insert_ndvi_measurement` fonksiyonunu çağırıyor. Senin yapman gereken
   tek şey: `supabase_rpc_insert_ndvi.sql` dosyasının içeriğini Supabase
   Dashboard → SQL Editor'da BİR KEZ çalıştırmak (fonksiyonu oluşturur).
   PostGIS eklentisi kapalıysa dosyanın başındaki `CREATE EXTENSION`
   satırının yorumunu kaldırıp önce onu çalıştır.

4. **Gerçek hat verisiyle değiştir**: `geometry.py` içindeki
   `TEST_LINE_COORDS`, gerçek YEDAŞ hat güzergahı verisiyle (veya OSM'den
   çekilen veriyle) değiştirilmeli.

5. **Token otomatik yenileme**: `auth.py` basit bir in-memory cache içerir
   (tek script çalıştırması için yeterli). Pipeline periyodik/sürekli
   çalışacaksa (örn. cron job), bu haliyle her çalıştırmada script yeniden
   başladığından cache sıfırlanır — bu genelde sorun değil, ama uzun süre
   canlı kalan bir process içinde kullanacaksan token yenileme mantığını
   gözden geçir.

## Çoklu hat / gerçek YEDAŞ verisiyle içe aktarım

`run_pipeline.py` zaten `power_lines` tablosundaki TÜM hatları otomatik
işliyor — eksik olan sadece o tabloyu gerçek/çok sayıda hatla doldurmaktı.
Bunun için `import_power_lines.py` eklendi.

1. **Supabase kurulumu (bir kez)**: `supabase_add_external_id.sql` ve
   `supabase_rpc_upsert_power_line.sql` dosyalarını SQL Editor'da çalıştır
   (idempotent import için — aynı hat tekrar import edilirse duplicate
   satır oluşmaz, günceller).
2. **Veriyi GeoJSON'a çevir**: YEDAŞ'tan gelen veri shapefile ise:
   `ogr2ogr -f GeoJSON hatlar.geojson hatlar.shp -t_srs EPSG:4326`
3. **Önce dry-run**:
   ```bash
   python import_power_lines.py --input hatlar.geojson --mode dry-run
   ```
4. **SQL üret ve elle çalıştır** (ilk import için önerilir):
   ```bash
   python import_power_lines.py --input hatlar.geojson --mode sql --output power_lines_import.sql
   ```
   Ardından `power_lines_import.sql` içeriğini Supabase SQL Editor'da çalıştır.
5. **Ya da doğrudan yaz** (çok sayıda hat / periyodik re-sync için):
   ```bash
   python import_power_lines.py --input hatlar.geojson --mode rpc
   ```

GeoJSON'daki property adları kaynağa göre farklıysa (örn. `"HAT_ADI"`),
`--name-field`, `--external-id-field`, `--province-field`, `--voltage-field`
argümanlarıyla eşle. MultiLineString geometriler otomatik olarak ayrı
segmentlere bölünür.

## Türkiye genelinde TÜM hatları import etme + Sentinel Hub kredisini korumak

Senaryo: `fetch_osm_powerlines.py --country` ile Türkiye genelinde ~15.000
hat çektin (`turkiye_hatlari.geojson`), TAMAMINI haritada görmek istiyorsun,
ama her ay 15.000 hat için Sentinel Hub Statistical API'yi otomatik
çalıştırmak kredini/kotanı çok hızlı tüketir. Çözüm: `is_monitored` bayrağı
— haritada TÜM hatlar görünür, ama otomatik NDVI sorgusu SADECE
işaretlediğin küçük öncelikli alt kümede çalışır; geri kalanı istediğinde
manuel/on-demand sorgularsın.

### 1. Supabase kurulumu (SIRAYLA, bir kez)

1. `supabase_add_external_id.sql`
2. `supabase_add_is_monitored.sql` — yeni `is_monitored` kolonu (varsayılan `false`)
3. `supabase_rpc_upsert_power_line.sql`
4. `supabase_rpc_get_power_lines.sql` — GÜNCELLENDİ: artık varsayılan olarak
   sadece `is_monitored=true` hatları döner (`run_pipeline.py`'nin otomatik
   çalıştırması için)
5. `supabase_rpc_insert_ndvi.sql` + `supabase_add_unique_constraint.sql`
6. `supabase_view_power_line_risk_status.sql` — frontend'in okuduğu view.
   LEFT JOIN kullanır: NDVI verisi olmayan hatlar da (gri, "veri yok"
   olarak) haritada görünür, sorgudan düşmez.

### 2. TÜM hatları içe aktar (harita için, kredi harcamaz)

```bash
python import_power_lines.py --input turkiye_hatlari.geojson --mode sql \
    --name-field name --external-id-field id --voltage-field voltage_level \
    --output power_lines_import.sql
```

`power_lines_import.sql` içeriğini Supabase SQL Editor'da çalıştır (15.000
satırlık dosya tek seferde çalıştırılabilir; çok büyükse birkaç parçaya
bölüp sırayla çalıştır). Bu adım sadece geometriyi tabloya yazar, Sentinel
Hub'a hiç istek atmaz — dolayısıyla kredi harcamaz. İçe aktarılan tüm
hatlar `is_monitored=false` ile gelir ve harita üzerinde ince gri çizgi
("veri yok") olarak görünür.

Not: `--mode rpc` ile doğrudan yazmak da mümkün, ama 15.000 satır için tek
tek RPC çağrısı yavaş olur ve yarıda kesilirse nerede kaldığını takip etmek
zorlaşır — ilk toplu import için `--mode sql` önerilir.

### 3. Otomatik izlenecek öncelikli hatları seç (kredi burada harcanır)

```bash
python mark_monitored.py --province Samsun
# ya da belirli hatları external_id ile:
python mark_monitored.py --external-ids way/12345,way/67890
```

Sadece bu şekilde işaretlenen hatlar `run_pipeline.py`'nin varsayılan
(parametresiz, GitHub Actions'daki zamanlanmış) çalıştırmasına dahil olur.

### 4. Geri kalan hatları manuel/on-demand sorgula (istediğinde, elle)

Otomatik izlemeye almadığın ama ara sıra kontrol etmek istediğin hatlar
için (kredi kullanımını sen kontrol edersin):

```bash
python run_pipeline.py --province Çorum          # sadece bir il
python run_pipeline.py --external-ids way/111,way/222   # belirli hatlar
python run_pipeline.py --all                      # TÜM hatlar — DİKKAT, kredi
```

### 5. Harita neden boş görünüyordu?

`docs/index.html`, `power_line_risk_status` view'inden veri okuyor.
`power_lines` tablosu boşsa (henüz hiç import yapılmadıysa) view de boş
döner ve harita "0 hat" gösterir — bu bir hata değil, henüz veri
aktarılmadığının göstergesidir. Yukarıdaki 2. adımı tamamladığında hatlar
görünmeye başlar.

## İl (province) bilgisi yanlış görünüyorsa (Türkiye geneli import sonrası)

`fetch_osm_powerlines.py --country` ile çekilen OSM verisinde hatların il
bilgisi YOK. Daha önce `import_power_lines.py --province` default'u
"Samsun" olduğu için, Türkiye genelinde import edilmiş hatların province
kolonu gerçek konumdan bağımsız olarak "Samsun" yazılmış olabilir. Bunu
düzeltmek için:

1. **Önce dry-run** (veritabanına dokunmaz, sadece kaç hat etkilenecek
   ve hangi illere düzeltileceğini gösterir):
   ```bash
   python fix_line_provinces.py --dry-run
   ```
2. **SQL dosyalarını üret** (15.000 hat, Supabase SQL Editor'ı
   zorlamaması için varsayılan olarak 2000'erli parçalara bölünür —
   `split_sql.py` ile yaptığın chunking mantığının aynısı):
   ```bash
   python fix_line_provinces.py --mode sql --chunk-size 2000
   ```
3. Üretilen `fix_line_provinces_0001.sql`, `fix_line_provinces_0002.sql`, ...
   dosyalarının içeriğini **sırayla** Supabase SQL Editor'da çalıştır.

Bu düzeltme, hattın kendi koordinatlarını gerçek il sınırlarına
(`turkiye_il_sinirlari.geojson`, 81 il) karşı nokta-poligon testiyle
kontrol ederek yapılır (bkz. `turkey_provinces.py`). Kıyı/ada gibi sınır
bölgelerindeki hatlar "tahmini" olarak işaretlenir, SQL dosyasında
yanlarında bir uyarı yorumu bulunur.

`import_power_lines.py` da güncellendi: property'de il bilgisi
bulunamadığında artık körü körüne "Samsun" yazmak yerine, hattın
geometrisinden otomatik il tespiti yapıyor — bu hata gelecekteki
import'larda tekrarlanmayacak.



`run_test.py` tek bir hattı manuel olarak (`--line-id` ile) test etmek
içindir. Gerçek üretimde tüm hatların otomatik ve periyodik olarak
işlenmesi gerekir; bunun için `run_pipeline.py` ve bir GitHub Actions
workflow'u eklendi.

### 1. Supabase kurulumu (SIRAYLA, bir kez)

1. `supabase_rpc_insert_ndvi.sql` — NDVI kaydı yazan RPC fonksiyonu.
2. `supabase_add_unique_constraint.sql` — aynı hat+tarih için duplicate
   satır oluşmasını engeller (upsert için gerekli).
3. `supabase_rpc_get_power_lines.sql` — pipeline'ın tüm hatları otomatik
   çekebilmesi için gereken yeni RPC fonksiyonu.
4. `power_lines` tablosuna gerçek hat verilerini ekle (bkz.
   `power_lines_test_insert.sql` örnek olarak, ve/veya
   `fetch_osm_powerlines.py` ile OSM'den veri çek).

### 2. `run_pipeline.py` ile tüm hatları çalıştır

```bash
python run_pipeline.py --months-back 6 --log-file pipeline.log
```

`power_lines` tablosundaki tüm satırları otomatik işler, bir hatta
hata olursa diğerlerini durdurmadan devam eder ve sonunda
başarılı/başarısız özet basar.

### 3. Kodu GitHub'a yükle

`github_push.bat` dosyasını çalıştır (bkz. yukarıdaki "GitHub'a yükleme"
bölümü) — bu adım değişmedi.

### 4. Otomatik/periyodik çalıştırma (GitHub Actions)

`.github/workflows/ndvi-pipeline.yml` eklendi; bu, `run_pipeline.py`'yi
her ayın 1'inde otomatik çalıştırır (cron ifadesini workflow dosyasından
değiştirebilirsin) ve GitHub Actions sekmesinden manuel de tetiklenebilir
("Run workflow" butonu).

Bunun çalışması için repo ayarlarında şu secrets'ı **bir kez** tanımlaman
gerekiyor (Settings → Secrets and variables → Actions → New repository
secret):

- `SENTINEL_HUB_CLIENT_ID`
- `SENTINEL_HUB_CLIENT_SECRET`
- `SUPABASE_URL`
- `SUPABASE_KEY`

Bunlar `.env` dosyandaki değerlerle aynı olmalı — `.env` dosyasının
kendisi hiçbir zaman GitHub'a gitmez (`.gitignore`'da), secrets bunun
GitHub Actions için güvenli karşılığıdır.

Kurulumdan sonra Actions sekmesinden "Run workflow" ile bir kez elle
tetikleyip log'u kontrol etmen, ardından zamanlanmış çalıştırmalara
güvenmen önerilir.
