#!/usr/bin/env bash
B=~/mjr-android/build/MjrSpike
echo "source copy: $(grep -c _http_errors $B/mahjong_rating.py)"
cd /tmp && rm -rf apkchk && mkdir apkchk && cd apkchk
unzip -q -o /mnt/e/Users/24737/Downloads/majsoul-mortal-rating-main/majsoul-mortal-rating-main/.scratch/android/app_diag.apk 'assets/*' 2>/dev/null
ls -la assets | head
for f in assets/private.*; do
  echo "== $f"; file "$f"
  (tar -xzOf "$f" mahjong_rating.py 2>/dev/null || tar -xOf "$f" mahjong_rating.py 2>/dev/null || tar -xzOf "$f" ./mahjong_rating.py 2>/dev/null) | grep -c _http_errors
done
