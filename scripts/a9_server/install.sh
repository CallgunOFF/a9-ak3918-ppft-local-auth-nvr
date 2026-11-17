#!/usr/bin/env bash
set -e

echo "[*] Установка зависимостей для A9 Camera Server..."

if command -v pkg >/dev/null 2>&1; then
    pkg update -y
    pkg install -y python python-numpy python-pip ffmpeg clang make pkg-config openssh curl
    pip install av
elif command -v apt-get >/dev/null 2>&1; then
    apt-get update -y
    apt-get install -y python3 python3-av python3-numpy ffmpeg openssh-client curl
else
    echo "[!] Неизвестный пакетный менеджер. Установите вручную: python3, ffmpeg, numpy, av."
    exit 1
fi

chmod +x "$(dirname "$0")/start.sh" "$(dirname "$0")/install.sh"
echo "[+] Установка завершена! Для запуска выполните: bash start.sh (или bash start.sh --debug)"
