#!/usr/bin/env bash
HOST=$(ip route show default | awk '{print $3}')
echo "host=$HOST"
for p in 57777 57778; do
  printf "port %s tcp: " "$p"
  if timeout 3 bash -c "</dev/tcp/$HOST/$p" 2>/dev/null; then echo open; else echo closed; fi
  printf "  github via proxy: "; curl -s -m 10 -x "http://$HOST:$p" -o /dev/null -w "%{http_code}\n" https://github.com/ || echo FAIL
done
