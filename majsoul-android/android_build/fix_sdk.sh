#!/usr/bin/env bash
set -e
S=$HOME/mjr-android/sdk
rm -rf "$S/tools"
cp -a "$S/cmdline-tools/latest" "$S/tools"
ls "$S/tools/bin" "$S/tools/lib" | head
JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64 "$S/tools/bin/sdkmanager" --sdk_root="$S" --list_installed 2>&1 | tail -8
