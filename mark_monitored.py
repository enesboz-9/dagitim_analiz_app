"""
mark_monitored.py
------------------
power_lines tablosundaki belirli hatları is_monitored=true yapar, böylece
run_pipeline.py'nin varsayılan (parametresiz, zamanlanmış) çalıştırması
bunları OTOMATİK olarak Sentinel Hub'a sorgular. is_monitored=false olan
(varsayılan, yeni import edilen) hatlar haritada görünmeye devam eder ama
otomatik sorguya girmez — kredi/kota israf edilmez. Bu hatlar için gerektiğinde
`python run_pipeline.py --province ... ` ya da `--external-ids ...` ile
manuel/on-demand sorgu yapılabilir.

ÖNKOŞUL: supabase_add_is_monitored.sql daha önce çalıştırılmış olmalı.

Kullanım
--------
İl bazında izlemeye al:
    python mark_monitored.py --province Samsun

Belirli hatları (external_id ile) izlemeye al:
    python mark_monitored.py --external-ids way/12345,way/67890

İzlemeden çıkarmak için (örn. yanlışlıkla işaretlendiyse):
    python mark_monitored.py --province Samsun --unmonitor
"""

import argparse

from db import get_supabase_client


def main():
    parser = argparse.ArgumentParser(
        description="power_lines tablosunda is_monitored bayrağını toplu günceller"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--province", type=str,
                        help="Bu ile ait TÜM hatları izlemeye al/çıkar")
    group.add_argument("--external-ids", type=str,
                        help="Virgülle ayrılmış external_id listesi")
    parser.add_argument("--unmonitor", action="store_true",
                         help="true yerine false yap (izlemeden çıkar)")
    args = parser.parse_args()

    value = not args.unmonitor
    client = get_supabase_client()
    query = client.table("power_lines").update({"is_monitored": value})

    if args.province:
        query = query.eq("province", args.province)
        target_desc = f"province={args.province}"
    else:
        ids = [x.strip() for x in args.external_ids.split(",") if x.strip()]
        query = query.in_("external_id", ids)
        target_desc = f"{len(ids)} external_id"

    response = query.execute()
    updated = len(response.data or [])
    print(f"{updated} hat güncellendi (is_monitored={value}), hedef: {target_desc}.")
    if updated == 0:
        print("[UYARI] Hiçbir satır eşleşmedi — il adı/external_id doğru mu kontrol et "
              "(province eşleşmesi büyük/küçük harf ve tam metin duyarlıdır).")


if __name__ == "__main__":
    main()
