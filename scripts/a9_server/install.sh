#!/data/data/com.termux/files/usr/bin/bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "=== Установка и настройка сервера камеры A9 / PPFT ==="
echo "[*] Рабочая директория: $DIR"

if [ ! -f "$DIR/.env" ]; then
    echo "[!] Файл .env не найден! Создаю шаблон..."
    cat << 'ENVEOF' > "$DIR/.env"
DID=ВПИШИТЕ_DID_КАМЕРЫ
SECRET=ВПИШИТЕ_SECRET_КЛЮЧ
CAM_IP=192.168.0.101
WEB_USER=admin
WEB_PASS=cam2026
NVR_ENABLED=0
NVR_DIR=/storage/emulated/0/Download/Cam_Records
NVR_SEG_MIN=10
NVR_MAX_MB=5120
ENVEOF
    echo "[!] Заполните $DIR/.env и запустите install.sh снова."
    exit 1
fi

if [ -d "/data/data/com.termux" ]; then
    mkdir -p "$HOME/.termux/boot"
    cat << BOOTEOF > "$HOME/.termux/boot/start_cam.sh"
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
sleep 25
if ! pgrep -f "a9_mjpeg_server.py" >/dev/null 2>&1; then
    nohup bash "$DIR/start.sh" > "$DIR/boot.log" 2>&1 &
fi
BOOTEOF
    chmod +x "$HOME/.termux/boot/start_cam.sh"
    echo "[*] Автозапуск настроен: $HOME/.termux/boot/start_cam.sh"
fi

chmod +x "$DIR/start.sh"
exec bash "$DIR/start.sh"

# Каскадная установка PyAV (4 способа)
python3 -c "import av" 2>/dev/null || pkg install -y python-av || pkg install -y python-pyav || (pkg install -y tur-repo && pkg update -y && pkg install -y python-av) || (pkg install -y clang make pkg-config python-dev libjpeg-turbo-dev && CFLAGS="-Wno-incompatible-function-pointer-types" LDFLAGS="-lm" pip install --no-build-isolation --no-binary av av) || (CFLAGS="-Wno-incompatible-function-pointer-types" LDFLAGS="-lm" pip install --no-build-isolation --no-binary av "av==12.3.0")
