#!/usr/bin/env bash
# 完整应用的安卓构建:
#   1. 把项目源码 (*.py, qml/, mobile/, 图标) 同步进 ~/mjr-android/build/MjrSpike (复用 .buildozer 缓存)
#   2. pyside6-android-deploy 按 main.py + qml 重新分析 Qt 模块, 生成 recipe 和 buildozer.spec
#   3. 补上 numpy/matplotlib/mahjong 等依赖, 用 rebuild.sh 正式构建
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
SRC=$(cd "$HERE/.." && pwd)  # 源码根目录 = android_build 的上一级, 与所在盘符/路径无关
ROOT=$HOME/mjr-android
B=$ROOT/build/MjrSpike
. "$HERE/net_env.sh"
# 限制并行编译数, 避免 clang++ 同时跑太多把内存吃光
export MAKEFLAGS=-j14
export CMAKE_BUILD_PARALLEL_LEVEL=14
export MAX_JOBS=14
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
mkdir -p "$B"
rsync -a --delete \
  --exclude /.buildozer --exclude '*.apk' --exclude build.log \
  --include '/*.py' --include '/qml/***' --include '/mobile/***' --include '/assets/***' \
  --include '/installer/' --include '/installer/app.ico' --exclude '*' \
  "$SRC"/ "$B"/
rm -f "$B/gui.py" "$B/buildozer.spec" "$B/pysidedeploy.spec"
rm -rf "$B/deployment"
cd "$B"
ls -la . qml mobile
. "$ROOT/venv/bin/activate"
rm -rf "$B"/.buildozer/android/platform/build-*/build/venv
# 第一次: 只为生成 spec/recipe (它会顺带跑一次 buildozer, 缺依赖也没关系)
pyside6-android-deploy --name MajsoulRating \
  --wheel-pyside="$ROOT/wheels/pyside6-6.12.0-6.12.0-cp310-abi3-android_aarch64.whl" \
  --wheel-shiboken="$ROOT/wheels/shiboken6-6.12.0-6.12.0-cp310-abi3-android_aarch64.whl" \
  --ndk-path="$ROOT/sdk/ndk/28.2.13676358" --sdk-path="$ROOT/sdk" \
  --keep-deployment-files -f > deploy.log 2>&1
echo "deploy rc=$?"
grep -E "^\s*modules|^\s*plugins|^\s*qml_files" pysidedeploy.spec
S=$B/buildozer.spec
[ -f "$S" ] || { echo "no buildozer.spec"; tail -40 deploy.log; exit 1; }
bash "$HERE/spec_set.sh" "$S" requirements "python3,shiboken6,PySide6,numpy,matplotlib,mahjong"
bash "$HERE/spec_set.sh" "$S" source.include_exts "py,png,jpg,qml,js,ico,css,svg"
bash "$HERE/spec_set.sh" "$S" version "2.0.0"
bash "$HERE/spec_set.sh" "$S" icon.filename "$HERE/icon_android.png"
# targetSdk 35 默认禁止明文 http; 报告页走 http://127.0.0.1 本机服务, 需要放开
bash "$HERE/spec_set.sh" "$S" android.extra_manifest_application_arguments "$HERE/manifest_app_args.xml"
bash "$HERE/spec_set.sh" "$S" android.permissions "android.permission.INTERNET, android.permission.ACCESS_NETWORK_STATE"
grep -E "^p4a.extra_args|^title|^package" "$S"
bash "$HERE/rebuild.sh" MjrSpike
