#!/usr/bin/env bash
# 在 buildozer.spec 里设置 key = value (已存在则替换, 注释掉的也替换)
set -e
F=$1; K=$2; V=$3
if grep -qE "^#?\s*${K//./\\.}\s*=" "$F"; then
  sed -i -E "s|^#?\s*${K//./\\.}\s*=.*|${K} = ${V}|" "$F"
else
  sed -i "/^\[app\]/a ${K} = ${V}" "$F"
fi
grep -E "^${K//./\\.}\s*=" "$F"
