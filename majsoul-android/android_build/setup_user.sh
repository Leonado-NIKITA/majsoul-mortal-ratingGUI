#!/usr/bin/env bash
# 以普通用户运行: Android SDK/NDK、构建用 venv. Qt 安卓 wheel 从 Windows 侧下载好放在 wheels/.
set -euo pipefail
QT_VER=6.12.0
HOST=$(ip route show default | awk '{print $3}')
export http_proxy=http://$HOST:57778 https_proxy=http://$HOST:57778
export HTTP_PROXY=$http_proxy HTTPS_PROXY=$https_proxy
ROOT=$HOME/mjr-android
SDK=$ROOT/sdk
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$ROOT/wheels" "$SDK"
cd "$ROOT"
cp -u "$HERE"/wheels/*.whl "$ROOT/wheels/"

export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
SM="$SDK/cmdline-tools/latest/bin/sdkmanager"
PX=(--proxy=http --proxy_host="$HOST" --proxy_port=57778)
yes | "$SM" --sdk_root="$SDK" "${PX[@]}" --licenses >/dev/null || true
"$SM" --sdk_root="$SDK" "${PX[@]}" "platform-tools" "platforms;android-35" "build-tools;35.0.0" "ndk;28.2.13676358"
ls "$SDK/ndk"
echo SDK_DONE

if [ ! -d venv ]; then python3 -m venv venv; fi
. venv/bin/activate
pip install -q -U pip
pip install -q "PySide6==${QT_VER}" buildozer Cython jinja2 pkginfo tqdm packaging toml
pyside6-android-deploy --help | head -3
echo ENV_DONE
