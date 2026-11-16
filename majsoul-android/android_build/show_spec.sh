#!/usr/bin/env bash
# 打印 spike 构建配置, 供完整应用打包参考
cd ~/mjr-android/build/MjrSpike || exit 1
grep -v '^#' buildozer.spec | grep -v '^\s*$'
echo ----
grep -v '^#' pysidedeploy.spec | grep -v '^\s*$'
echo ----
ls deployment
ls ~/mjr-android/spike
cat "$(dirname "$0")/net_env.sh" 2>/dev/null | sed 's/=.*/=.../'
