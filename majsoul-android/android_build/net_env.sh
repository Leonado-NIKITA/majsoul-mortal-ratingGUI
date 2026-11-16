#!/usr/bin/env bash
# 被其它脚本 source: 主机上的转发代理通就用它, 不通就直连
HOST=$(ip route show default | awk '{print $3}')
if timeout 3 bash -c "</dev/tcp/$HOST/57777" 2>/dev/null; then
  export http_proxy=http://$HOST:57777 https_proxy=http://$HOST:57777
  export HTTP_PROXY=$http_proxy HTTPS_PROXY=$https_proxy
  echo "[net] via proxy $HOST:57777"
else
  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
  echo "[net] direct"
fi
