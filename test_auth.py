"""
test_auth.py
------------
Yeni rotate edilen Sentinel Hub client'ının gerçekten çalışıp
çalışmadığını doğrular:

  1. .env'den client_id/secret okuyup get_access_token() çağırır
     (bu satır, CDSE'nin token endpoint'ine gerçek bir istek atar —
     eğer credentials yanlışsa burada 401/invalid_client hatası alırsın)
  2. Dönen JWT'nin payload kısmını (imza doğrulaması yapmadan, sadece
     okumak için) decode eder ve içindeki süre/scope gibi bilgileri
     okunabilir şekilde basar.
  3 opsiyonel. --live-check ile ufak bir Statistical API isteği atıp
     token'ın gerçekten kabul edildiğini (200 yanıt) teyit eder.

Kullanım:
    python test_auth.py
    python test_auth.py --live-check
"""

import argparse
import base64
import json
import sys
from datetime import datetime, timezone

from auth import get_access_token


def decode_jwt_payload(token: str) -> dict:
    """
    JWT'nin ortadaki (payload) kısmını decode eder.
    NOT: Bu imza DOĞRULAMASI yapmaz — sadece token'ın içeriğini
    okumak için kullanılır (debug amaçlı). Güvenlik kararı için
    kullanılmamalı, zaten burada öyle bir amaç yok.
    """
    try:
        payload_b64 = token.split(".")[1]
        # base64 padding düzeltmesi
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload_json = base64.urlsafe_b64decode(padded)
        return json.loads(payload_json)
    except Exception as e:
        raise ValueError(f"Token JWT formatında değil ya da decode edilemedi: {e}")


def run_live_check(token: str):
    """
    Token'ı gerçekten Statistical API'ye karşı test eder.
    Küçük, geçersiz-ama-authentication'ı test eden bir istek atar;
    401 alırsak token/credentials sorunu, başka bir hata (400 gibi)
    alırsak token GEÇERLİ demektir (çünkü auth katmanını geçmiş oluruz).
    """
    import requests

    url = "https://sh.dataspace.copernicus.eu/api/v1/statistics"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # Kasıtlı olarak eksik/minimal bir body gönderiyoruz — amaç sadece
    # auth katmanının token'ı kabul edip etmediğini görmek.
    minimal_body = {"input": {"bounds": {}}, "aggregation": {}}

    try:
        response = requests.post(url, json=minimal_body, headers=headers, timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"  [!] İstek gönderilemedi (ağ sorunu olabilir): {e}")
        return

    if response.status_code == 401:
        print(f"  [X] 401 Unauthorized — token kabul edilmedi. Client ID/Secret'ı kontrol et.")
    elif response.status_code in (400, 422):
        print(f"  [OK] {response.status_code} alındı — bu İYİ bir haber: "
              f"auth katmanı token'ı kabul etti, hata sadece eksik/hatalı body'den "
              f"kaynaklanıyor (beklenen, çünkü kasıtlı olarak minimal bir body gönderdik).")
    else:
        print(f"  [?] Beklenmeyen durum kodu: {response.status_code}")
        print(f"      Yanıt: {response.text[:300]}")


def main():
    parser = argparse.ArgumentParser(description="Sentinel Hub auth testi")
    parser.add_argument("--live-check", action="store_true",
                         help="Token'ı gerçekten Statistical API'ye karşı test et")
    args = parser.parse_args()

    print("[1/2] Token alınıyor (CDSE identity endpoint'ine gerçek istek)...")
    try:
        token = get_access_token(force_refresh=True)
    except Exception as e:
        print(f"  [X] Token alınamadı: {e}")
        print("      Kontrol et: .env dosyasında SENTINEL_HUB_CLIENT_ID / SECRET doğru mu?")
        sys.exit(1)

    print(f"  [OK] Token alındı (ilk 20 karakter): {token[:20]}...")

    print("\n[2/2] Token içeriği okunuyor...")
    try:
        payload = decode_jwt_payload(token)
        exp = payload.get("exp")
        if exp:
            exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
            now = datetime.now(timezone.utc)
            remaining_min = (exp_dt - now).total_seconds() / 60
            print(f"  Token süresi doluyor: {exp_dt.isoformat()} (~{remaining_min:.0f} dakika kaldı)")
        client_id_in_token = payload.get("clientId") or payload.get("azp") or payload.get("client_id")
        if client_id_in_token:
            print(f"  Token'daki client id: {client_id_in_token}")
        scope = payload.get("scope")
        if scope:
            print(f"  Scope: {scope}")
    except ValueError as e:
        print(f"  [!] {e}")

    if args.live_check:
        print("\n[live-check] Statistical API'ye karşı test ediliyor...")
        run_live_check(token)
    else:
        print("\nİpucu: Token'ın API'ye karşı gerçekten kabul edildiğini görmek için "
              "--live-check ile tekrar çalıştır.")


if __name__ == "__main__":
    main()
