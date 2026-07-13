@echo off
REM ============================================================
REM  github_push.bat
REM  dagitim_analiz_app projesini GitHub'a yukler.
REM  Bu dosyayi proje klasorunun (diger .py dosyalariyla ayni
REM  yerde) icine koyup cift tiklayarak veya cmd'den calistir.
REM ============================================================

echo.
echo === dagitim_analiz_app - GitHub Push ===
echo.

REM Bu .bat dosyasinin bulundugu klasore gec (nereden calistirilirsa calistirilsin dogru calisir)
cd /d "%~dp0"

REM Git kurulu mu kontrol et
where git >nul 2>nul
if %errorlevel% neq 0 (
    echo [HATA] Git bulunamadi. Once https://git-scm.com/download/win adresinden Git kur.
    pause
    exit /b 1
)

REM .env dosyasi yanlislikla commit'e girmesin diye kontrol
if exist ".env" (
    echo [UYARI] .env dosyasi bulundu. Bu dosya .gitignore ile haric tutuluyor,
    echo         ama icinde gercek sifre/anahtar varsa bir kez daha kontrol et.
    echo.
)

REM Zaten bir git reposu var mi kontrol et
if exist ".git" (
    echo [BILGI] Bu klasor zaten bir git reposu. init adimi atlaniyor.
) else (
    echo [1/6] git init calistiriliyor...
    git init
    if %errorlevel% neq 0 goto :error
)

echo [2/6] Dosyalar ekleniyor (git add .)...
git add .
if %errorlevel% neq 0 goto :error

echo [3/6] Commit olusturuluyor...
git commit -m "YEDAS NDVI test pipeline guncelleme"
REM Not: Eger degisiklik yoksa (ornegin ikinci calistirmada) commit basarisiz
REM olabilir, bu normal - devam ediyoruz.

echo [4/6] Ana dal 'main' olarak ayarlaniyor...
git branch -M main
if %errorlevel% neq 0 goto :error

echo [5/6] Remote (origin) ekleniyor...
git remote remove origin >nul 2>nul
git remote add origin https://github.com/enesboz-9/dagitim_analiz_app.git
if %errorlevel% neq 0 goto :error

echo [6/6] GitHub'a push ediliyor...
git push -u origin main
if %errorlevel% equ 0 goto :success

echo.
echo [BILGI] Direkt push reddedildi (uzak repoda yerelde olmayan commit'ler var).
echo         Otomatik olarak uzaktaki gecmisle birlestiriliyor...
echo         (Cakisma olursa yerel dosyalar tercih edilecek.)
echo.

git fetch origin
if %errorlevel% neq 0 goto :error

git merge origin/main --allow-unrelated-histories -X ours --no-edit
if %errorlevel% neq 0 (
    echo.
    echo [UYARI] Otomatik birlestirme basarisiz oldu.
    echo         Uzaktaki tum icerigin uzerine yazmak icin zorla push
    echo         deneyecegim. Bu, GitHub'daki mevcut icerigi SILECEK.
    echo.
    set /p onay="Devam edilsin mi? (E/H): "
    if /i not "%onay%"=="E" goto :error
    git push -u origin main --force
    if %errorlevel% neq 0 goto :error
    goto :success
)

echo [BILGI] Birlestirme tamamlandi, tekrar push deneniyor...
git push -u origin main
if %errorlevel% neq 0 goto :error

:success
echo.
echo === Basarili! Proje https://github.com/enesboz-9/dagitim_analiz_app adresine yuklendi ===
echo.
pause
exit /b 0

:error
echo.
echo [HATA] Bir adimda sorun olustu. Yukaridaki mesaji kontrol et.
echo        Sik karsilasilan sorunlar:
echo        - GitHub kullanici adi/sifre yerine Personal Access Token istenir
echo          (Settings - Developer settings - Personal access tokens)
echo        - Cakisan dosyalar varsa "git status" ile kontrol edip
echo          elle "git add" + "git commit" yapman gerekebilir
echo.
pause
exit /b 1
