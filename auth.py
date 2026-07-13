"""
auth.py
-------
CDSE (Copernicus Data Space Ecosystem) OAuth2 Client Credentials akışı
ile Sentinel Hub Statistical API için access token alır.

.env dosyasında şunlar tanımlı olmalı:
    SENTINEL_HUB_CLIENT_ID=...
    SENTINEL_HUB_CLIENT_SECRET=...

NOT: Token ~1 saat geçerli. Bu modül basit bir in-memory cache
tutar; süresi dolmadan tekrar istek atılırsa aynı token'ı döner,
böylece her segment sorgusunda gereksiz token isteği yapılmaz.
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

_cached_token = None
_cached_expiry = 0  # unix timestamp


def get_access_token(force_refresh: bool = False) -> str:
    """
    Access token döner. Süresi dolmuşsa (veya force_refresh=True ise)
    yeni token alır, aksi halde cache'teki token'ı kullanır.
    """
    global _cached_token, _cached_expiry

    if not force_refresh and _cached_token and time.time() < _cached_expiry:
        return _cached_token

    client_id = os.getenv("SENTINEL_HUB_CLIENT_ID")
    client_secret = os.getenv("SENTINEL_HUB_CLIENT_SECRET")

    if not client_id or not client_secret:
        raise RuntimeError(
            "SENTINEL_HUB_CLIENT_ID / SENTINEL_HUB_CLIENT_SECRET .env dosyasında bulunamadı. "
            "Client'ı rotate ettiysen yeni secret'ı .env'e yazmayı unutma."
        )

    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }
    response = requests.post(TOKEN_URL, data=data, timeout=30)
    response.raise_for_status()
    payload = response.json()

    _cached_token = payload["access_token"]
    # expires_in genelde saniye cinsinden gelir (~3600). 60sn güvenlik payı bırakıyoruz.
    expires_in = payload.get("expires_in", 3600)
    _cached_expiry = time.time() + expires_in - 60

    return _cached_token


if __name__ == "__main__":
    # Hızlı manuel test — gerçek .env credentials gerektirir
    token = get_access_token()
    print(f"Token alındı (ilk 20 karakter): {token[:20]}...")
