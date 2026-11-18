#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

DEBUG_MODE=0
for arg in "$@"; do
    case "$arg" in
        --debug|-d) DEBUG_MODE=1 ;;
    esac
done
[ "${DEBUG:-0}" = "1" ] && DEBUG_MODE=1
export A9_DEBUG="$DEBUG_MODE"

pkill -f "a9_mjpeg_server.py" 2>/dev/null || true
pkill -f "pinggy.io" 2>/dev/null || true
pkill -f "localhost.run" 2>/dev/null || true
sleep 1

command -v termux-wake-lock >/dev/null 2>&1 && termux-wake-lock || true

cleanup() {
    echo ""
    echo "[*] Остановка сервера и туннеля..."
    [ -n "$LOOP_PID" ] && kill "$LOOP_PID" 2>/dev/null || true
    [ -n "$WATCH_PID" ] && kill "$WATCH_PID" 2>/dev/null || true
    pkill -f "a9_mjpeg_server.py" 2>/dev/null || true
    pkill -f "pinggy.io" 2>/dev/null || true
    pkill -f "localhost.run" 2>/dev/null || true
    command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock || true
    exit 0
}
trap cleanup INT TERM

[ "$DEBUG_MODE" = "1" ] && echo "[*] Режим ОТЛАДКИ (--debug) включён"

(
    while true; do
        CAM_IP_VAL=$(grep -E '^(CAMERA_IP|CAM_IP)=' .env 2>/dev/null | head -n 1 | cut -d'=' -f2 | tr -d '[:space:]"\x27' || true)
        if [ -n "$CAM_IP_VAL" ]; then
            python3 a9_mjpeg_server.py "$CAM_IP_VAL" || python3 a9_mjpeg_server.py || true
        else
            python3 a9_mjpeg_server.py || true
        fi
        sleep 3
    done
) &
LOOP_PID=$!
sleep 2

TUN_LOG="$DIR/tunnel.log"
: > "$TUN_LOG"
python3 - << 'PYEOF' &
import os, time, re, subprocess

env = {}
if os.path.exists(".env"):
    for line in open(".env", encoding="utf-8"):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

ntfy_topic = env.get("NTFY_TOPIC", "")
wu = env.get("WEB_USER", "admin")
wp = env.get("WEB_PASS", "")
last_url = ""
ansi_re = re.compile(r"\x1b\[[0-9;]*[mK]")

while True:
    time.sleep(2)
    if not os.path.exists("tunnel.log"):
        continue
    try:
        clean_txt = ansi_re.sub("", open("tunnel.log", encoding="utf-8", errors="ignore").read())
        urls = re.findall(r"https://[a-zA-Z0-9.-]+\.(?:pinggy\.link|pinggy\.io|trycloudflare\.com|lhr\.life)", clean_txt)
        if urls:
            cur_url = urls.pop()
            if cur_url != last_url:
                msg = f"Камера онлайн!\nСсылка: {cur_url}\nЛогин: {wu}\nПароль: {wp}"
                if ntfy_topic:
                    url_ntfy = "https://ntfy.sh" + chr(47) + ntfy_topic
                    res = subprocess.run(
                        ["curl", "-sS", "-m", "10", "-H", "Title: Camera A9 Online", "-H", f"Click: {cur_url}", "-d", msg, url_ntfy],
                        capture_output=True, text=True
                    )
                    if res.returncode == 0:
                        print(f"[*] Туннель:  {cur_url}  (отправлено в ntfy/{ntfy_topic})", flush=True)
                        last_url = cur_url
                else:
                    print(f"[*] Туннель:  {cur_url}", flush=True)
                    last_url = cur_url
    except Exception:
        pass
PYEOF
WATCH_PID=$!

HOST_PORT="127.0.0"
HOST_PORT="${HOST_PORT}.1:8080"

while true; do
    : > "$TUN_LOG"
    if [ "$DEBUG_MODE" = "1" ]; then
        ssh -tt -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 80:"$HOST_PORT" -i ~/.ssh/id_ed25519 localhost.run 2>&1 | tee -a "$TUN_LOG" || true
    else
        ssh -T -o StrictHostKeyChecking=no -o LogLevel=ERROR -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 80:"$HOST_PORT" -i ~/.ssh/id_ed25519 localhost.run >> "$TUN_LOG" 2>&1 || true
    fi
    sleep 3
done
