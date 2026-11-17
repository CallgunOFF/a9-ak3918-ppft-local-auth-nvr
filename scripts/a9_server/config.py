# -*- coding: utf-8 -*-
from collections import deque
import os, sys, time, threading

_STATE_REF = None
_ENV_LOCK = threading.Lock()

def _get_st():
    return _STATE_REF

def _key_of_env_line(line):
    s = line.lstrip()
    if s.startswith("#"):
        s = s.lstrip("#").lstrip()
    if "=" in s:
        return s.split("=", 1)[0].strip()
    return None

def _save_env_kv(updates):
    if not updates:
        return
    ep = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    target_keys = set(updates.keys())
    with _ENV_LOCK:
        lines = open(ep, "r", encoding="utf-8").readlines() if os.path.exists(ep) else []
        out = [ln for ln in lines if _key_of_env_line(ln) not in target_keys]
        if out and not out[-1].endswith("\n"):
            out[-1] += "\n"
        for k, v in updates.items():
            clean_v = str("" if v is None else v).replace("\n", " ").replace("\r", "")
            out.append(f"{k}={clean_v}\n")
        tmp = ep + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.writelines(out)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, ep)

# ---------- Shared latest-frame state ----------

class Latest:
    def __init__(self):
        self.client_count = 0
        self.camera_wanted = False
        self.last_client_left_ts = 0.0
        self.cond = threading.Condition()
        self.jpeg = None
        self.seq = 0
        self.stop = False
        self.fps_val = 0.0
        self.kbps_val = 0
        self._f_cnt = 0
        self._b_cnt = 0
        self._stat_ts = time.time()
        self.sd_data = {"status":-1,"total_mb":0,"used_mb":0,"last_msg":"Ready","raw":{}}
        self.connected = False
        self.status = None
        self.status_ts = 0.0
        self.last_frame_ts = 0.0
        self.socket_lock = threading.Lock()
        self.camera_socket = None
        self.audio_cond = threading.Condition()
        self.audio_chunks = deque()
        self.audio_bytes = 0
        self.audio_max_bytes = 160000
        self.audio_seq = 0
        self.cmd_lock = threading.Lock()
        self.cmd_queue = deque(maxlen=64)

    def tick_stat(self, nbytes: int, is_frame: bool = True):
        if is_frame:
            self._f_cnt += 1
        self._b_cnt += nbytes
        _now = time.time()
        _dt = _now - self._stat_ts
        if _dt >= 1.0:
            self.fps_val = round(self._f_cnt / _dt, 1)
            self.kbps_val = int((self._b_cnt * 8) / (_dt * 1000))
            self._f_cnt = 0
            self._b_cnt = 0
            self._stat_ts = _now

    def push_cmd(self, cmd, payload=b""):
        with self.cmd_lock:
            if len(self.cmd_queue) == self.cmd_queue.maxlen:
                sys.stderr.write(f"[CMD-QUEUE] overflow (maxlen={self.cmd_queue.maxlen}), dropping oldest before cmd={cmd}\n")
            self.cmd_queue.append((cmd, payload))

    def pop_cmds(self):
        with self.cmd_lock:
            items = list(self.cmd_queue)
            self.cmd_queue.clear()
            return items

    def publish(self, jpeg):
        with self.cond:
            self.jpeg = jpeg
            self.seq += 1
            self.last_frame_ts = time.time()
            self.cond.notify_all()
            
    def publish_audio(self, pcm):
        if not pcm:
            return

        with self.audio_cond:
            self.audio_seq += 1
            self.audio_chunks.append(
                (self.audio_seq, time.monotonic(), pcm)
            )
            self.audio_bytes += len(pcm)

            while (
                self.audio_chunks
                and self.audio_bytes > self.audio_max_bytes
            ):
                _, _, old_pcm = self.audio_chunks.popleft()
                self.audio_bytes -= len(old_pcm)

            self.audio_cond.notify_all()            
            

    def set_status(self, st):
        with self.cond:
            self.status = st if isinstance(st, dict) else {}
            self.status_ts = time.time()

    def wait_newer(self, last_seq, timeout):
        with self.cond:
            self.cond.wait_for(lambda: self.seq != last_seq or self.stop, timeout)
            if self.stop:
                return None, last_seq
            if self.seq != last_seq:
                return self.jpeg, self.seq
            return None, last_seq

    def acquire_client(self):
        """Registration of client requesting streaming."""
        with self.cond:
            self.client_count += 1

            if self.client_count == 1:
                self.camera_wanted = True
                self.connected = False
                self.jpeg = None
                self.last_frame_ts = 0.0

                with self.audio_cond:
                    self.audio_chunks.clear()
                    self.audio_bytes = 0

            self.cond.notify_all()

    def release_client(self):
        """Release client and stops sessione if necessary."""
        
        with self.cond:
            if self.client_count > 0:
                self.client_count -= 1

            if self.client_count == 0:
                self.last_client_left_ts = time.time()

            self.cond.notify_all()



