#!/usr/bin/env bash
# 在已生成 buildozer.spec 的目录里直接跑 buildozer, 完整日志写到 build.log
set -uo pipefail
. "$(dirname "$0")/net_env.sh"
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PYTHONFORANDROID_PREREQUISITES_INSTALL_INTERACTIVE=0
# OFFLINE=1: 依赖都已缓存, 把 git fetch/pull 变成空操作, 不再联网
if [ "${OFFLINE:-0}" = 1 ]; then
  chmod +x "$(dirname "$0")/offline_git/git"
  export PATH="$(cd "$(dirname "$0")" && pwd)/offline_git:$PATH"
  echo "[net] offline git shim"
fi
B=$HOME/mjr-android/build/$1
cd "$B"
# p4a 每次构建都在这个 venv 里升级 pip, 第二次构建时新旧 pip 混装会报 ImportError; 每次重建它
rm -rf "$B"/.buildozer/android/platform/build-*/build/venv
. "$HOME/mjr-android/venv/bin/activate"
# 边编译边输出到终端, 同时完整写进 build.log
export MAKEFLAGS=-j14 CMAKE_BUILD_PARALLEL_LEVEL=14 MAX_JOBS=14 GRADLE_OPTS="-Dorg.gradle.workers.max=14 -Dorg.gradle.parallel=true -Dorg.gradle.jvmargs=-Xmx8g"
python -m buildozer -v android debug 2>&1 | python3 -u -c "import sys,time; [print(time.strftime(\"%H:%M:%S\"), l, end=\"\", flush=True) for l in sys.stdin]" | tee build.log
rc=${PIPESTATUS[0]}
echo "rc=$rc"
grep -nE "Error|error:|ERROR|Exception|failed" build.log | grep -vE "Werror|error\.h|-error|_error|errors\.py" | tail -25
tail -15 build.log
find "$B" -maxdepth 2 -name "*.apk" -exec ls -la {} \;
