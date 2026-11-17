# -*- coding: utf-8 -*-
import os, sys, time, threading

_STATE_REF = None
_ENV_LOCK = threading.Lock()

def _get_st():
    return _STATE_REF if _STATE_REF is not None else globals().get("state")

def _save_env_kv(updates):
    ep = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    with _ENV_LOCK:
        lines = open(ep, encoding="utf-8").readlines() if os.path.exists(ep) else []
        prefixes = tuple(f"{k}=" for k in updates.keys())
        out = [ln for ln in lines if not ln.startswith(prefixes)]
        for k, v in updates.items():
            out.append(f"{k}={v}\n")
        open(ep, "w", encoding="utf-8").writelines(out)

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
        self.last_frame_ts = 0.0
        self.socket_lock = threading.Lock()
        self.camera_socket = None
        self.audio_cond = threading.Condition()
        self.audio_chunks = []
        self.audio_bytes = 0
        self.audio_max_bytes = 32000
        self.audio_seq = 0
        self.cmd_lock = threading.Lock()
        self.cmd_queue = []

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
                _, _, old_pcm = self.audio_chunks.pop(0)
                self.audio_bytes -= len(old_pcm)

            self.audio_cond.notify_all()            
            

    def set_status(self, st):
        self._f_cnt += 1
        self._b_cnt += len(st)
        _now = time.time()
        _dt = _now - self._stat_ts
        if _dt >= 1.0:
            self.fps_val = round(self._f_cnt / _dt, 1)
            self.kbps_val = int((self._b_cnt * 8) / (_dt * 1000))
            self._f_cnt = 0
            self._b_cnt = 0
            self._stat_ts = _now
        with self.cond:
            self.status = st

    def wait_newer(self, last_seq, timeout):
        with self.cond:
            if self.seq == last_seq:
                self.cond.wait(timeout)
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



