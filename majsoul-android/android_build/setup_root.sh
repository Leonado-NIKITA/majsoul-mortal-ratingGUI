#!/usr/bin/env bash
# 以 root 运行: 安装安卓构建所需的系统包
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q autoconf automake libtool pkg-config zlib1g-dev libncurses-dev \
  libffi-dev libssl-dev unzip zip build-essential python3-venv python3-dev lld ccache patch \
  openjdk-17-jdk-headless wget libltdl-dev
echo APT_DONE
