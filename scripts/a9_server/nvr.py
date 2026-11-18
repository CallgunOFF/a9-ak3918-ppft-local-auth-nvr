# -*- coding: utf-8 -*-
import os, time, glob, struct, threading, datetime, subprocess, io

def _log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [NVR] {msg}", flush=True)

class _PureAviWriter:
    def __init__(self, path, fps=10):
        self.f = open(path, "wb")
        self.fps, self.frames, self.idx = fps, [], []
        self.movi_start, self.w, self.h = 0, 640, 480
        self._write_headers(0, 0)

    def _jpeg_size(self, jpg):
        i = 2
        while i + 9 < len(jpg):
            if jpg[i] != 0xFF: break
            m = jpg[i + 1]
            if m in (0xC0, 0xC1, 0xC2):
                return (jpg[i + 7] << 8) | jpg[i + 8], (jpg[i + 5] << 8) | jpg[i + 6]
            i += 2 + ((jpg[i + 2] << 8) | jpg[i + 3])
        return self.w, self.h

    def _write_headers(self, n_frames, movi_size):
        self.f.seek(0)
        usec = int(1_000_000 / max(1, self.fps))
        avih = struct.pack("<IIIIIIIIIIIIII", usec, 500000, 0, 0x10, n_frames, 0, 2, 65536, self.w, self.h, 0, 0, 0, 0)
        strh_v = struct.pack("<4s4sIHHIIIIIIIIhhhh", b"vids", b"MJPG", 0, 0, 0, 0, 1, self.fps, 0, n_frames, 65536, 0, 0, 0, 0, self.w, self.h)
        strf_v = struct.pack("<IiiHH4sIiiII", 40, self.w, self.h, 1, 24, b"MJPG", self.w * self.h * 3, 0, 0, 0, 0)
        strl_v = b"LIST" + struct.pack("<I4s", 20 + len(strh_v) + len(strf_v), b"strl") + b"strh" + struct.pack("<I", len(strh_v)) + strh_v + b"strf" + struct.pack("<I", len(strf_v)) + strf_v
        strh_a = struct.pack("<4s4sIHHIIIIIIIIhhhh", b"auds", b"\x01\x00\x00\x00", 0, 0, 0, 0, 2, 16000, 0, 0, 8192, 0, 2, 0, 0, 0, 0)
        strf_a = struct.pack("<HHIIHH", 1, 1, 8000, 16000, 2, 16)
        strl_a = b"LIST" + struct.pack("<I4s", 20 + len(strh_a) + len(strf_a), b"strl") + b"strh" + struct.pack("<I", len(strh_a)) + strh_a + b"strf" + struct.pack("<I", len(strf_a)) + strf_a
        hdrl_b = b"hdrl" + b"avih" + struct.pack("<I", len(avih)) + avih + strl_v + strl_a
        hdrl = b"LIST" + struct.pack("<I", len(hdrl_b)) + hdrl_b
        idx_b = b"".join(self.idx)
        riff_sz = 4 + len(hdrl) + 12 + movi_size + (8 + len(idx_b) if idx_b else 0)
        self.f.write(b"RIFF" + struct.pack("<I4s", riff_sz, b"AVI ") + hdrl + b"LIST" + struct.pack("<I4s", 4 + movi_size, b"movi"))
        if self.movi_start == 0: self.movi_start = self.f.tell()

    def write_video(self, jpg):
        if not self.idx: self.w, self.h = self._jpeg_size(jpg)
        pos = self.f.tell() - self.movi_start
        self.f.write(b"00dc" + struct.pack("<I", len(jpg)) + jpg + (b"\x00" if len(jpg) & 1 else b""))
        self.idx.append(struct.pack("<4sIII", b"00dc", 0x10, pos, len(jpg)))
        self.frames.append(1)

    def write_audio(self, pcm):
        if not pcm: return
        pos = self.f.tell() - self.movi_start
        self.f.write(b"01wb" + struct.pack("<I", len(pcm)) + pcm + (b"\x00" if len(pcm) & 1 else b""))
        self.idx.append(struct.pack("<4sIII", b"01wb", 0x10, pos, len(pcm)))

    def close(self):
        try:
            movi_sz = max(0, self.f.tell() - self.movi_start)
            idx_b = b"".join(self.idx)
            self.f.write(b"idx1" + struct.pack("<I", len(idx_b)) + idx_b)
            self._write_headers(len(self.frames), movi_sz)
            self.f.flush(); self.f.close()
        except Exception: pass

class NVRRecorder:
    def __init__(self, state=None):
        self.state = state
        self.enabled = os.environ.get("NVR_ENABLED", "0").strip() in ("1", "true", "yes")
        self.motion_level = int(os.environ.get("NVR_MOTION", "0").strip() or "0")
        self.rec_dir = os.environ.get("NVR_DIR", "/storage/emulated/0/Download/Cam_Records").strip()
        self.seg_sec = max(60, int(os.environ.get("NVR_SEG_MIN", "10")) * 60)
        self.max_bytes = max(100, int(os.environ.get("NVR_MAX_MB", "5120"))) * 1024 * 1024
        self.cur, self._motion_until, self._prev_gray, self._last_mot_chk = "", 0.0, None, 0.0
        os.makedirs(self.rec_dir, exist_ok=True)
        _log(f"Инициализирован (AVI): запись={'ВКЛ' if self.enabled else 'ВЫКЛ'}, датчик_движения={self.motion_level}, папка={self.rec_dir}")
        threading.Thread(target=self._loop, daemon=True).start()

    def attach_state(self, state): self.state = state

    def _notify_motion(self, diff_val, thr_val):
        now = time.time()
        if now - getattr(self, "_last_ntfy", 0.0) < 60.0: return
        self._last_ntfy = now
        topic = os.environ.get("NTFY_TOPIC", "").strip()
        if not topic: return
        msg = f"Движение в {datetime.datetime.now().strftime('%H:%M:%S')}! Уровень={diff_val:.1f} (порог {thr_val}). Запись AVI..."
        url = "https://ntfy.sh" + chr(47) + topic
        threading.Thread(target=lambda: subprocess.run(["curl", "-sS", "-m", "10", "-H", "Title: Motion Detected (Camera A9)", "-H", "Priority: high", "-d", msg, url], capture_output=True), daemon=True).start()

    def set_motion(self, level: int):
        self.motion_level = max(0, min(3, int(level)))
        if self.motion_level == 0: self._motion_until, self._prev_gray = 0.0, None
        self._save_env()
        _log(f"Датчик движения NVR: { {0:'ВЫКЛ',1:'Низкая',2:'Средняя',3:'Высокая'}.get(self.motion_level, self.motion_level) }")

    def update_config(self, rec_dir, seg_min, max_mb, enabled=None):
        if rec_dir: self.rec_dir = rec_dir.strip()
        if seg_min: self.seg_sec = max(60, int(seg_min) * 60)
        if max_mb: self.max_bytes = max(100, int(max_mb)) * 1024 * 1024
        if enabled is not None: self.enabled = bool(enabled)
        os.makedirs(self.rec_dir, exist_ok=True); self._save_env()

    def _save_env(self):
        from config import _save_env_kv
        _save_env_kv({"NVR_ENABLED": "1" if self.enabled else "0", "NVR_MOTION": str(self.motion_level), "NVR_DIR": self.rec_dir, "NVR_SEG_MIN": str(self.seg_sec // 60), "NVR_MAX_MB": str(self.max_bytes // 1048576)})

    def _decode_gray_32x24(self, jpg_bytes):
        try:
            import av
            for frame in av.open(io.BytesIO(jpg_bytes)).decode(video=0):
                return bytes(next(iter(frame.reformat(width=32, height=24, format="gray").planes)))
        except Exception:
            step = max(1, len(jpg_bytes) // 512)
            return jpg_bytes[128::step][:512]

    def feed_frame(self, jpg_bytes: bytes, suppress_motion: bool = False):
        if self.motion_level <= 0 or suppress_motion:
            if suppress_motion: self._prev_gray = None
            return
        now = time.time()
        if now - self._last_mot_chk < 1.0: return
        self._last_mot_chk = now
        cur_gray = self._decode_gray_32x24(jpg_bytes)
        if cur_gray and self._prev_gray and len(cur_gray) == len(self._prev_gray):
            diff = sum(abs(a - b) for a, b in zip(cur_gray, self._prev_gray)) / len(cur_gray)
            thr = {1: 18.0, 2: 10.0, 3: 5.5}.get(self.motion_level, 10.0)
            if diff >= thr:
                was = now < self._motion_until
                self._motion_until = now + 45.0
                if not was and not self.enabled:
                    _log(f"[MOTION-ALERT] Движение ({diff:.1f} >= {thr})! Запись AVI 45с..."); self._notify_motion(diff, thr)
        self._prev_gray = cur_gray

    def _all_files(self):
        pats = [os.path.join(self.rec_dir, p) for p in ("rec_*.avi", "motion_*.avi", "rec_*.ts", "motion_*.ts")]
        res = []
        for p in pats: res.extend(glob.glob(p))
        return res

    def list_files(self):
        out = []
        for f in sorted(self._all_files(), key=os.path.getmtime, reverse=True):
            bn = os.path.basename(f)
            kind = "Движение" if bn.startswith("motion_") else "Запись"
            dt_str = ""
            parts = bn.split("_")
            if len(parts) >= 3 and len(parts) == 8 and len(parts) >= 6:
                d_s, t_s = parts, parts[:6]
                dt_str = f"{d_s[6:8]}.{d_s[4:6]}.{d_s[:4]} {t_s[:2]}:{t_s[2:4]}:{t_s[4:6]}"
            else:
                dt_str = datetime.datetime.fromtimestamp(os.path.getmtime(f)).strftime("%d.%m.%Y %H:%M:%S")
            out.append({
                "name": bn,
                "kind": kind,
                "dt": dt_str,
                "size_mb": round(os.path.getsize(f) / 1048576, 2),
                "active": bn == self.cur,
            })
        return out

    def delete_file(self, name):
        bn = os.path.basename(name or "")
        if not bn or bn == self.cur:
            return False
        fp = os.path.join(self.rec_dir, bn)
        if os.path.isfile(fp):
            os.remove(fp)
            return True
        return False

    def _cleanup(self):
        files = sorted(self._all_files(), key=os.path.getmtime)
        tot = sum(os.path.getsize(f) for f in files if os.path.exists(f))
        while tot > self.max_bytes and len(files) > 1:
            o = files.pop(0); sz = os.path.getsize(o); os.remove(o); tot -= sz

    def _loop(self):
        while True:
            st = self.state
            if st is None:
                try: import config as _cfg; st = _cfg._get_st()
                except Exception: st = None
            if st is None or (not self.enabled and not (self.motion_level > 0 and time.time() < self._motion_until)):
                self.cur = ""; time.sleep(0.4); continue
            self._cleanup(); os.makedirs(self.rec_dir, exist_ok=True)
            fn = ("rec_" if self.enabled else "motion_") + datetime.datetime.now().strftime("%Y%m%d_%H%M%S") + ".avi"
            fp = os.path.join(self.rec_dir, fn); self.cur = fn; t0 = time.time()
            _log(f"Начата запись AVI: {fn}")
            w = _PureAviWriter(fp, fps=10); vs, a_s = 0, 0
            try:
                while (self.enabled or (self.motion_level > 0 and time.time() < self._motion_until)) and (time.time() - t0 < self.seg_sec):
                    jpg, _, vs = st.wait_frame(vs, timeout=0.5)
                    if jpg: w.write_video(jpg)
                    pcm, a_s = st.wait_audio(a_s, timeout=0.01)
                    if pcm: w.write_audio(pcm)
            finally:
                w.close()
                _log(f"AVI сохранён: {fn} ({(os.path.getsize(fp)/1048576 if os.path.exists(fp) else 0):.2f} МБ, {int(time.time()-t0)}с)")
                self.cur = ""
