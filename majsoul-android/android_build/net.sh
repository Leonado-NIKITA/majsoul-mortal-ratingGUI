#!/usr/bin/env bash
# 测试 WSL 能否通过 Windows 主机上的代理联网
HOST=$(ip route show default | awk '{print $3}')
echo "host=$HOST"
for u in https://pypi.org/simple/ https://dl.google.com/android/repository/repository2-3.xml https://github.com/ https://www.python.org/ftp/python/; do
  printf "%s direct=" "$u"; curl -s -m 10 -o /dev/null -w "%{http_code}" "$u" || printf FAIL
  printf " proxy=";       curl -s -m 10 -x "http://$HOST:57777" -o /dev/null -w "%{http_code}" "$u" || printf FAIL
  echo
done
