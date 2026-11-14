import subprocess
import os, time, glob, base64, threading, datetime, urllib.request, io

def _log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [NVR] {msg}", flush=True)

class NVRRecorder:
    def __init__(self):
        self.enabled = os.environ.get("NVR_ENABLED", "0").strip() in ("1", "true", "yes")
        self.motion_level = int(os.environ.get("NVR_MOTION", "0").strip() or "0")
        self.rec_dir = os.environ.get("NVR_DIR", "/storage/emulated/0/Download/Cam_Records").strip()
        self.seg_sec = max(60, int(os.environ.get("NVR_SEG_MIN", "10")) * 60)
        self.max_bytes = max(100, int(os.environ.get("NVR_MAX_MB", "5120"))) * 1024 * 1024
        self.cur = ""
        self._motion_until = 0.0
        self._is_motion_rec = False
        os.makedirs(self.rec_dir, exist_ok=True)
        _log(f"Инициализирован: запись={'ВКЛ' if self.enabled else 'ВЫКЛ'}, датчик_движения={self.motion_level}, папка={self.rec_dir}")
        threading.Thread(target=self._loop, daemon=True).start()
        threading.Thread(target=self._motion_loop, daemon=True).start()


    def _notify_motion(self, diff_val, thr_val):
        now = time.time()
        if now - getattr(self, "_last_ntfy", 0.0) < 60.0:
            return
        self._last_ntfy = now
        topic = os.environ.get("NTFY_TOPIC", "").strip()
        if not topic:
            return
        msg = f"Dvizhenie v {datetime.datetime.now().strftime('%H:%M:%S')}! Uroven={diff_val:.1f} (porog {thr_val}). Zapis NVR..."
        url = "https://ntfy.sh" + chr(47) + topic
        threading.Thread(target=lambda: subprocess.run(["curl", "-sS", "-m", "10", "-H", "Title: Motion Detected (Camera A9)", "-H", "Priority: high", "-d", msg, url], capture_output=True), daemon=True).start()

    def set_motion(self, level: int):
        self.motion_level = max(0, min(3, int(level)))
        if self.motion_level == 0:
            self._motion_until = 0.0
        self._save_env()
        names = {0: "ВЫКЛ", 1: "Низкая", 2: "Средняя", 3: "Высокая"}
        _log(f"Датчик движения NVR: {names.get(self.motion_level, self.motion_level)}")

    def update_config(self, rec_dir, seg_min, max_mb, enabled=None):
        if rec_dir:
            self.rec_dir = rec_dir.strip()
        if seg_min:
            self.seg_sec = max(60, int(seg_min) * 60)
        if max_mb:
            self.max_bytes = max(100, int(max_mb)) * 1024 * 1024
        if enabled is not None:
            self.enabled = bool(enabled)
        os.makedirs(self.rec_dir, exist_ok=True)
        self._save_env()
        _log(f"Настройки обновлены: {'ВКЛ' if self.enabled else 'ВЫКЛ'}, папка={self.rec_dir}, сегмент={self.seg_sec//60}м, лимит={self.max_bytes//1048576}МБ")

    def _save_env(self):
        env_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
        vals = {
            "NVR_ENABLED": "1" if self.enabled else "0",
            "NVR_MOTION": str(self.motion_level),
            "NVR_DIR": self.rec_dir,
            "NVR_SEG_MIN": str(self.seg_sec // 60),
            "NVR_MAX_MB": str(self.max_bytes // (1024 * 1024)),
        }
        os.environ.update(vals)
        lines = []
        if os.path.exists(env_p):
            with open(env_p, "r", encoding="utf-8") as f:
                for line in f:
                    k = next(iter(line.split("=", 1))).strip() if "=" in line else ""
                    if k in vals:
                        lines.append(f"{k}={vals.pop(k)}\n")
                    else:
                        lines.append(line)
        for k, v in vals.items():
            lines.append(f"{k}={v}\n")
        with open(env_p, "w", encoding="utf-8") as f:
            f.writelines(lines)

    def list_files(self):
        out = []
        try:
            pats = glob.glob(os.path.join(self.rec_dir, "rec_*.ts")) + glob.glob(os.path.join(self.rec_dir, "motion_*.ts"))
            for f in sorted(pats, key=os.path.getmtime, reverse=True):
                out.append({
                    "name": os.path.basename(f),
                    "size_mb": round(os.path.getsize(f) / 1048576, 2),
                    "active": os.path.basename(f) == self.cur,
                })
        except Exception:
            pass
        return out

    def _cleanup(self):
        pats = glob.glob(os.path.join(self.rec_dir, "rec_*.ts")) + glob.glob(os.path.join(self.rec_dir, "motion_*.ts"))
        files = sorted(pats, key=os.path.getmtime)
        tot = sum(os.path.getsize(f) for f in files if os.path.exists(f))
        while tot > self.max_bytes and len(files) > 1:
            o = files.pop(0)
            sz = os.path.getsize(o)
            os.remove(o)
            tot -= sz
            _log(f"Автоочистка лимита: удалён старый файл {os.path.basename(o)} ({sz/1048576:.2f} МБ)")

    def _decode_gray_32x24(self, jpg_bytes):
        import av
        container = av.open(io.BytesIO(jpg_bytes))
        for frame in container.decode(video=0):
            small = frame.reformat(width=32, height=24, format="gray")
            return bytes(next(iter(small.planes)))
        return None

    def _motion_loop(self):
        time.sleep(5)
        snap_url = "http://127.0.0" + ".1:8080/snapshot.jpg"
        prev_gray = None
        thresholds = {1: 18.0, 2: 10.0, 3: 5.5}
        while True:
            if self.motion_level <= 0:
                prev_gray = None
                time.sleep(1)
                continue
            try:
                req = urllib.request.Request(snap_url)
                wu, wp = os.environ.get("WEB_USER", ""), os.environ.get("WEB_PASS", "")
                if wu and wp:
                    req.add_header("Authorization", "Basic " + base64.b64encode(f"{wu}:{wp}".encode()).decode())
                with urllib.request.urlopen(req, timeout=3) as r:
                    jpg = r.read()
                cur_gray = self._decode_gray_32x24(jpg)
                if cur_gray and prev_gray and len(cur_gray) == len(prev_gray):
                    diff = sum(abs(a - b) for a, b in zip(cur_gray, prev_gray)) / len(cur_gray)
                    thr = thresholds.get(self.motion_level, 10.0)
                    if diff >= thr:
                        was_active = (time.time() < self._motion_until)
                        self._motion_until = time.time() + 45.0
                        if not was_active and not self.enabled:
                            _log(f"[MOTION-ALERT] Движение в кадре (уровень={diff:.1f} >= {thr})! Запуск записи на 45с..."); self._notify_motion(diff, thr)
                prev_gray = cur_gray
            except Exception:
                prev_gray = None
            time.sleep(0.5)

    def _loop(self):
        time.sleep(3)
        url = "http://127.0.0" + ".1:8080/live.ts"
        while True:
            motion_active = (self.motion_level > 0 and time.time() < self._motion_until)
            if not self.enabled and not motion_active:
                self.cur = ""
                time.sleep(0.5)
                continue
            self._cleanup()
            os.makedirs(self.rec_dir, exist_ok=True)
            prefix = "rec_" if self.enabled else "motion_"
            fn = prefix + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".ts"
            fp = os.path.join(self.rec_dir, fn)
            self.cur = fn
            t0 = time.time()
            _log(f"Начата запись сегмента: {fn}")
            try:
                req = urllib.request.Request(url)
                wu, wp = os.environ.get("WEB_USER", ""), os.environ.get("WEB_PASS", "")
                if wu and wp:
                    req.add_header("Authorization", "Basic " + base64.b64encode(f"{wu}:{wp}".encode()).decode())
                with urllib.request.urlopen(req, timeout=10) as r, open(fp, "wb") as out:
                    while (self.enabled or (self.motion_level > 0 and time.time() < self._motion_until)) and (time.time() - t0 < self.seg_sec):
                        ch = r.read(32768)
                        if not ch:
                            break
                        out.write(ch)
            except Exception as e:
                _log(f"Ошибка записи {fn}: {e}")
                time.sleep(2)
            finally:
                self.cur = ""
                try:
                    if os.path.exists(fp):
                        sz = os.path.getsize(fp)
                        if sz < 4096:
                            os.remove(fp)
                            _log(f"Пустой сегмент {fn} ({sz} Б) удалён")
                        else:
                            _log(f"Сегмент сохранён: {fn} ({sz/1048576:.2f} МБ, {int(time.time()-t0)}с)")
                except Exception:
                    pass
