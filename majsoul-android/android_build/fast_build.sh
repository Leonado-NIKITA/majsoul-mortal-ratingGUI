#!/usr/bin/env bash
# 只改了 *.py / qml / mobile 时用: 跳过 pyside6-android-deploy, 复用已有 buildozer.spec 和编译缓存
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$(cd "$HERE/.." && pwd)  # 源码根目录 = android_build 的上一级, 与所在盘符/路径无关
B=$HOME/mjr-android/build/MjrSpike
[ -f "$B/buildozer.spec" ] || { echo "no spec, run build_app.sh first"; exit 1; }
rsync -a --exclude gui.py --include '/*.py' --include '/qml/***' --include '/mobile/***' --include '/assets/***' --include '/qtapp/***' --exclude '*' "$SRC"/ "$B"/
# QT=1: 用 qtapp 作为入口 (旧 main.py 改名 legacy_main.py 留着给 qtapp.main 复用 _android_ca_bundle)
if [ "${QT:-0}" = 1 ]; then
  cp "$SRC/main.py" "$B/legacy_main.py" && cp "$SRC/qtapp/launch.py" "$B/main.py"
  echo "entry: qtapp"
fi
bash "$HERE/rebuild.sh" MjrSpike
