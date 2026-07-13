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
