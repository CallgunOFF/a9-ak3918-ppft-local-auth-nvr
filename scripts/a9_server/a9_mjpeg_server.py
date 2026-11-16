NVR = None
import os as _os
_env_file = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), ".env")
if _os.path.exists(_env_file):
    with open(_env_file, "r", encoding="utf-8") as _ef:
        for _line in _ef:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                _os.environ.setdefault(_k.strip(), _v.strip().strip("\"\x27"))

#!/usr/bin/env python3
"""
a9_mjpeg_server.py - live MJPEG/snapshot server for an XCThings/Linklemo A9 camera.

Holds one PPRPC session to a camera you own, decodes the MJPEG stream continuously,
and serves it over HTTP so a browser or Home Assistant can show a live feed:

 if False:
    python3 a9_mjpeg_server.py                 # discover (or read a9_camera.json)
    python3 a9_mjpeg_server.py 192.168.3.114   # a specific camera
    # then open http://127.0.0.1:8080/

Endpoints:
    /               small HTML viewer
    /stream.mjpg    multipart/x-mixed-replace MJPEG stream  (HA: "MJPEG IP Camera")
    /snapshot.jpg   the latest single frame                 (HA: "Generic Camera" still)
    /status         JSON: battery, firmware, connected/streaming (from cmd-2780 pushes)
    /stream?raw=1   multiplexed A9AV binary stream: b'A9AV' + uint32le(type: 1=JPEG, 2=PCM8k) + uint32le(len) + payload
    /live.ts        vlc, mpv and possibly other players stream with audio
    
Uses the shared protocol/crypto in a9_proto.py, so
no external dependencies. Reconnects automatically if the camera drops the session.

Credentials come from --did/--secret, else a9_camera.json, else UDP discovery
(same precedence as the client). The stream is unauthenticated, so it binds to
127.0.0.1 by default; use --bind 0.0.0.0 to expose it to other hosts (e.g. HA on
another machine) and put it behind your own network controls.

For a camera you own.
"""
import sys
import os
import socket
import time
import threading
CMD_PSP_ADD, CMD_PSP_CALL, CMD_PSP_LIST, CMD_PSP_DEL = 2666, 2667, 2668, 2669
CMD_OSD_GET, CMD_OSD_SET = 2648, 2649
CMD_WIFI_GET, CMD_WIFI_SET = 2661, 2662
CMD_REBOOT = 2670


_ep0 = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_ep0):
    for _ln in open(_ep0, encoding="utf-8"):
        if "=" in _ln and not _ln.lstrip().startswith("#"):
            _k0, _v0 = _ln.strip().split("=", 1)
            os.environ.setdefault(_k0.strip(), _v0.strip())

_PATROL = {"on": os.environ.get("PATROL_ON", "0") == "1", "sec": max(5, int(os.environ.get("PATROL_SEC", "15") or "15")), "pts": [int(x) for x in os.environ.get("PATROL_PTS", "1,2,3,4").split(",") if x.strip().isdigit()]}

_cx, _cy = map(float, os.environ.get("CUR_POS", "6.0,3.0").split(",", 1)) if "," in os.environ.get("CUR_POS", "") else (6.0, 3.0)
_PTZ_LOCK = threading.Lock()
_LAST_PTZ_TS = 0.0
_PTZ_POS = {"x": float(_cx), "y": float(_cy), "dir": 10, "t": time.time(), "pts": {}}
for _k in (1, 2, 3, 4):
    _v = os.environ.get(f"PSP_{_k}", "").strip("()")
    if "," in _v:
        try:
            _a, _b = _v.split(",", 1)
            _PTZ_POS["pts"].update({_k: (float(_a), float(_b))})
        except Exception:
            pass

def _ptz_track(code):
  global _LAST_PTZ_TS
  _LAST_PTZ_TS = time.time()
  with _PTZ_LOCK:
    now = time.time()
    dt = min(15.0, max(0.0, now - _PTZ_POS["t"]))
    d = _PTZ_POS["dir"]
    if d == 14: _PTZ_POS["x"] = min(12.0, _PTZ_POS["x"] + dt)
    elif d == 13: _PTZ_POS["x"] = max(0.0, _PTZ_POS["x"] - dt)
    elif d == 11: _PTZ_POS["y"] = min(6.0, _PTZ_POS["y"] + dt)
    elif d == 12: _PTZ_POS["y"] = max(0.0, _PTZ_POS["y"] - dt)
    _PTZ_POS["dir"] = code
    _PTZ_POS["t"] = now

import gc
def _get_st():
    st = globals().get("state")
    if st is not None: return st
    for o in gc.get_objects():
        if hasattr(o, "push_cmd") and hasattr(o, "camera_socket"):
            globals()["state"] = o
            return o
    return None

def _ptz_goto(st, sid, is_patrol=False):
    sid = int(sid if isinstance(sid, list) else sid)
    with _PTZ_LOCK:
        pt = next((v for k, v in _PTZ_POS.get("pts", {}).items() if int(k) == sid), None)
        cx, cy = _PTZ_POS["x"], _PTZ_POS["y"]
    st = st or _get_st()
    if pt is None or st is None:
        print(f"[PTZ-PTS] Точка T{sid} не найдена (pts={_PTZ_POS.get('pts')})", flush=True)
        return
    tx, ty = pt
    _ptz_track(10)
    dx, dy = tx - cx, ty - cy
    print(f"[PTZ-PTS] Плавный переход в T{sid} ({tx:.2f}с, {ty:.2f}с) из ({cx:.2f}с, {cy:.2f}с): dx={dx:+.2f}с, dy={dy:+.2f}с", flush=True)

    def _glide(code_dir, dist_sec):
        rem = dist_sec * 0.90
        step_idx = 0
        while rem > 0.015:
            if is_patrol and not _PATROL["on"]:
                st.push_cmd(2664, P.pb_varint_field(2, 10))
                return False
            # Плавный старт (первые 2 шага) и мягкий довод (при остатке < 0.16с)
            base_pulse = 0.055 if (step_idx < 2 or rem < 0.16) else 0.075
            pulse = min(base_pulse, rem)
            st.push_cmd(2664, P.pb_varint_field(2, code_dir))
            time.sleep(pulse)
            st.push_cmd(2664, P.pb_varint_field(2, 10))
            rem -= pulse
            step_idx += 1
            if rem > 0.015:
                time.sleep(0.18)
        return True

    if abs(dx) > 0.06:
        if _glide(14 if dx > 0 else 13, min(12.0, abs(dx))):
            with _PTZ_LOCK:
                _PTZ_POS["x"] = tx
    if abs(dy) > 0.06:
        if _glide(11 if dy > 0 else 12, min(6.0, abs(dy))):
            with _PTZ_LOCK:
                _PTZ_POS["y"] = ty

    with _PTZ_LOCK:
        _PTZ_POS["dir"], _PTZ_POS["t"] = 10, time.time()
        nx, ny = _PTZ_POS["x"], _PTZ_POS["y"]
    try:
        _save_env_kv({"CUR_POS": f"{nx:.2f},{ny:.2f}"})
    except Exception:
        pass

def _patrol_loop():
    idx = 0
    while True:
        if not _PATROL["on"] or _get_st() is None:
            time.sleep(0.5)
            continue
        pts = sorted(int(k) for k in _PTZ_POS.get("pts", {}).keys())
        if len(pts) < 2:
            time.sleep(1.0)
            continue
        sid = pts[idx % len(pts)]
        idx += 1
        print(f"[PTZ-PTS] Патруль -> T{sid} (пауза {_PATROL['sec']}с)", flush=True)
        _ptz_goto(_get_st(), sid, is_patrol=True)
        for _ in range(_PATROL["sec"] * 2):
            time.sleep(0.5)
            if not _PATROL["on"]:
                break

import argparse
import struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import a9_proto as P
import a9_discover as D
import av
import queue
from fractions import Fraction
import io
import numpy as np

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



# ---------- Camera session ----------

def camera_loop(ip, did, secret, state, timeout, start_seq):
    while not state.stop:

        # waits first client without opening connennection to camera.
        with state.cond:
            while not state.stop and not state.camera_wanted:
                state.cond.wait()

            if state.stop:
                break

        s = None

        try:
            # Verifies before opening new connection.
            with state.cond:
                if state.stop or not state.camera_wanted:
                    continue

            # --- wake-up UDP: камера открывает TCP только после discovery-пинга ---
            try:
                _us = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                _us.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    _us.bind(("", P.PORT))
                except OSError:
                    pass
                _us.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)
                if _us: _us.settimeout(2.0)
                _pkt = bytes.fromhex("5170480401a8140c")
                for _i in range(5):
                    _us.sendto(_pkt, (ip, P.PORT))
                    try:
                        _us.recvfrom(2048)
                        break
                    except socket.timeout:
                        continue
                _us.close()
            except Exception as _e:
                print(f"[WAKEUP-ERR] {_e!r}", flush=True)
            # --- /wake-up ---

            s = socket.create_connection(
                (ip, P.PORT),
                timeout=timeout,
            )

            with state.socket_lock:
                state.camera_socket = s

            # a client could have been disconnected during connect().
            with state.cond:
                wanted = state.camera_wanted and not state.stop

            if wanted:
                _run_session(
                    s, did, secret, state, timeout, start_seq
                )

        except Exception as exc:
            with state.cond:
                wanted = state.camera_wanted and not state.stop

            if wanted:
                sys.stderr.write(
                    f"[camera] session error: {exc}; "
                    "reconnecting in 2s\n"
                )

        finally:
            with state.socket_lock:
                if state.camera_socket is s:
                    state.camera_socket = None

            if s is not None:
                sys.stderr.write(
                    "[camera] Disconnection from camera.\n"
                )
                sys.stderr.flush()

                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

                try:
                    s.close()
                except OSError:
                    pass

            with state.cond:
                state.connected = False
                state.cond.notify_all()

        # Reconnection only if at least une client exists.
        with state.cond:
            if state.stop:
                break

            if not state.camera_wanted:
                continue

            # brakable wait: if every client exit,
            # go back to wait without making new connections.
            state.cond.wait_for(
                lambda: state.stop or not state.camera_wanted,
                timeout=2.0,
            )


def _run_session(s, did, secret, state, timeout, start_seq):
    rdr = P.FrameReader(s)
    seq = start_seq

    s.sendall(
        P.build_ctrl(
            seq,
            P.CMD_LANAUTH,
            P.pb_field_bytes(2, did) + P.pb_field_bytes(3, secret),
        )
    )
    seq += 1

    # Obtain session key from LanAuth reply.
    session_key = None
    t_end = time.time() + timeout

    while time.time() < t_end and session_key is None:
        mt, mf, body = rdr.next_frame(timeout=timeout)

        if mt == 4:
            cmd, rseq, rpc, ct = P.ctrl_exhdr(body)

            if cmd == P.CMD_LANAUTH:
                pt = P.ctrl_decrypt(cmd, rseq, rpc, ct)

                if pt:
                    f = P.pb_parse(pt)
                    if 1 in f and isinstance(f[1][0], bytes):
                        session_key = f[1][0]
                        _fields_dbg = {}
                        for _k, _v in f.items():
                            _fields_dbg[_k] = (type(_v[0]).__name__, repr(_v[0])[:100])
                        print(f"[LANAUTH-ALL] {_fields_dbg}", flush=True)

    if not session_key:
        raise RuntimeError(
            "LanAuth gave no session key (wrong credentials?)"
        )

    def answer(cmd, rseq, rpc, ct):
        if rpc != 0:
            return

        if cmd == P.CMD_PING:
            pt = P.ctrl_decrypt(cmd, rseq, rpc, ct)
            echo = P.pb_parse(pt).get(1, [0])[0] if pt else 0

            pong = (
                P.pb_varint_field(1, echo)
                + P.pb_varint_field(2, P.HB_CONST)
                + P.pb_varint_field(3, int(time.time() * 1000))
            )

            s.sendall(
                P.build_ctrl(rseq, P.CMD_PING, pong, flag=0x0D)
            )

        elif cmd == P.CMD_HELLO:
            s.sendall(
                P.build_ctrl(
                    rseq,
                    P.CMD_HELLO,
                    P.pb_varint_field(1, 1),
                    flag=0x0D,
                )
            )
    last_video_avseq = 0
    frags = P.MediaFragments()
    started = False
    last_media = time.time()
    frame_count = 0
    frame_fragments = 0
    media_counts = {}
    # Diagnostic counters, indexed by MEDIA subtype.
    media_counts = {}

    def process(mt, body):
        if mt == 4:
            try:
                _c, _rs, _rp, _ct = P.ctrl_exhdr(body)
                pass
            except Exception as _e:
                print(f"[RX-CTRL-ERR] {_e!r}", flush=True)
        elif mt == 6:
            _sub = (body[0] & 0x7f) if len(body) else -1
            _fs = (body[0] >> 7) if len(body) else -1
            pass
        nonlocal seq, frags, started, last_media, frame_count, frame_fragments, last_video_avseq

        if mt == 4:
            cmd, rseq, rpc, ct = P.ctrl_exhdr(body)
            answer(cmd, rseq, rpc, ct)

            if cmd == P.CMD_STATUS and ct and len(ct) % 16 == 0:
                pt = P.ctrl_decrypt(cmd, rseq, rpc, ct)

                if pt:
                    st = P.decode_status_2780(pt)
                    if st:
                        state.set_status(st)

        elif mt == 6:
            if not body:
                return

            last_media = time.time()

            # Bit 7: frame-start flag.
            # Bits 0-6: MEDIA subtype.
            subtype = body[0] & 0x7F
            frame_start = bool(body[0] & 0x80)
            pass
            if subtype == 4 and frame_start:
                try:
                    _, _, last_video_avseq, _, _, _ = P.media_exhdr(body)
                except ValueError:
                    pass

            media_counts[subtype] = (
                media_counts.get(subtype, 0) + 1
            )
            count = media_counts[subtype]

            if subtype in (21, 121):
                import hashlib
                try:
                    start, avch, avseq, tt, enclen, data = P.media_exhdr(body)
                    if enclen > 0:
                        if len(data) < enclen:
                            print(f"[AUDIO-DIAG] short data {len(data)} < {enclen}", flush=True)
                            return
                        if enclen % 16 != 0:
                            print(f"[AUDIO-DIAG] unaligned enclen={enclen}", flush=True)
                        n = enclen
                        n -= n % 16
                        if n > 0:
                            sk_str = session_key.decode("utf-8") if isinstance(session_key, (bytes, bytearray)) else str(session_key)
                            ks = f"{sk_str},AVSeq:{avseq}-TT:{tt}-AVChannel:{avch}".encode("utf-8")
                            key = hashlib.md5(ks).hexdigest().encode("ascii")
                            data = P.aes_cbc_decrypt(key, key[16:32], data[:n]) + data[n:]
                    if not hasattr(process, "_audio_logged"):
                        process._audio_logged = True
                        print(f"[AUDIO-OK] subtype={subtype} len={len(data)} avch={avch} head={data[:8].hex()}", flush=True)
                    state.publish_audio(data)
                except Exception as exc:
                    print(f"[AUDIO-DIAG] parse error: {exc!r}", flush=True)
                return

            # IMPORTANT:
            # Only subtype 4 is passed to the JPEG reconstruction.
            # Audio subtype 21 must never be appended to frags.
            if subtype != 4:
                return

            if frame_start:
                frame_count += 1

                # decodes precedent frame if present
                if started and frame_fragments > 0:
                    try:
                        jpg = P.decrypt_media_frame(
                            frags, session_key
                        )

                        if jpg and jpg.startswith(b"\xff\xd8") and jpg.endswith(b"\xff\xd9"):
                            pass
                            state.publish(jpg)
                        
                    except Exception as exc:
                        print(
                            f"[VIDEO-CHECK] error "
                            f"frame={frame_count} "
                            f"fragments={frame_fragments}: {exc!r}",
                            flush=True,
                        )

                # starts new frame.
                frags = P.MediaFragments()
                frags.append(body)
                frame_fragments = 1
                started = True

            elif started:
            
                if (body[0] & 0x7F) != 4:
                    return
            
                frags.append(body)
                frame_fragments += 1

    def pump(dur):
        end = time.time() + dur

        while (
            time.time() < end
            and not state.stop
            and state.camera_wanted
        ):
            try:
                mt, mf, body = rdr.next_frame(
                    timeout=max(0.05, end - time.time())
                )
            except (TimeoutError, socket.timeout):
                break

            process(mt, body)

    # Answer initial handshake before starting video.
    s.sendall(
        P.build_ctrl(
            seq, P.CMD_HELLO, P.pb_varint_field(1, 1)
        )
    )
    seq += 1
    pump(0.3)

    # Original startup sequence: audio is not enabled here.
    _dq_hd = 1 if os.environ.get("DEFAULT_QUALITY", "HD").strip().upper() == "HD" else 0
    for cmd, pt in [
        (2653, b""),
        (2645, b""),
        (P.CMD_VIDEOPLAY, b""),
        (P.CMD_VIDEOPLAY, P.pb_varint_field(1, 0) + P.pb_varint_field(2, 1)),
        (getattr(P, "CMD_SETRES", 2612), P.pb_varint_field(1, 0) + P.pb_varint_field(2, _dq_hd)),
    ]:
        s.sendall(P.build_ctrl(seq, cmd, pt))
        seq += 1
        pump(0.15)

    state.connected = True
    if state.stop or not state.camera_wanted:
        state.connected = False
        return
    last_media = time.time()

    # --- LAN-AUTH dump ---
    try:
        print(f"[LANAUTH] type={type(session_key).__name__} repr={session_key[:80]!r}", flush=True)
    except Exception as _e:
        print(f"[LANAUTH-ERR] {_e!r}", flush=True)
    # --- /LAN-AUTH dump ---
    sys.stderr.write("[camera] authenticated; streaming\n")

    # Keepalive and delayed audio activation.
    STALL = 12.0
    last_ping = 0.0

     #Send RPC 2614 once, can add varible delay after entering the main loop.
    audio_at = time.time() + 0.8
    audio_sent = False

    while not state.stop:
        with state.cond:
            if state.client_count == 0 and state.camera_wanted:
                if time.time() - state.last_client_left_ts > 10.0:
                    state.camera_wanted = False
                    state.connected = False
            if not state.camera_wanted:
                break
        now = time.time()

        for _cmd, _pl in state.pop_cmds():
            try:
                s.sendall(P.build_ctrl(seq, _cmd, _pl))
                print(f"[CTRL-TX] cmd={_cmd} seq={seq} payload={_pl.hex()}", flush=True)
                seq += 1
            except Exception as _ce:
                print(f"[CTRL-ERR] {_ce!r}", flush=True)

        if now - last_ping >= 1.0:
            s.sendall(
                P.build_ctrl(
                    seq,
                    P.CMD_PING,
                    P.pb_varint_field(1, int(now * 1000))
                    + P.pb_varint_field(4, last_video_avseq),
                )
            )
            seq += 1
            last_ping = now

        if not audio_sent and now >= audio_at:
            print(
#                "[RPC TEST] cmd=2614",
                flush=True,
            )
            s.sendall(P.build_ctrl(seq, 2614, b""))
            seq += 1
            audio_sent = True

        try:
            mt, mf, body = rdr.next_frame(timeout=0.3)
            process(mt, body)

        except (TimeoutError, socket.timeout):
            pass

        if time.time() - last_media > STALL:
            sys.stderr.write("[camera] media stalled; reconnecting\n")
            break


# ---------- HTTP server ----------

VIEWER = b"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
html,body { margin:0; width:100%; height:100%; background:#000; overflow:hidden; }
canvas { display:block; width:100%; height:100%; object-fit:contain; }
#enable-audio { position:fixed; top:1rem; right:1rem; padding:0.6rem 1rem; }
</style>
<style id="ptz-pad-fix">
#ptz-pad { left: auto !important; right: 14px !important; bottom: 56px !important; }
#enable-audio { display: inline-flex !important; align-items: center;  position: static !important; margin: 0 !important; }
</style>
</head>
<body>
<img id="mjpg" src="/stream.mjpg" style="position:fixed;inset:0;width:100%;height:100%;object-fit:contain;background:#000;z-index:1;pointer-events:none;" />
<canvas id="video" style="display:none;"></canvas>
<div id="top-bar" style="position:fixed;top:12px;left:12px;right:12px;display:flex;flex-wrap:wrap;gap:8px;z-index:9999;pointer-events:none;">
  <button id="enable-audio" type="button" style="pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;">&#128266; &#1047;&#1074;&#1091;&#1082;</button>
  <button id="btn-ir" type="button" onclick="uiIr(this)" style="pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;">&#127769; &#1048;&#1050;: &#1040;&#1074;&#1090;&#1086;</button>
  <button id="btn-res" type="button" onclick="uiRes(this)" style="pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;">&#128250; &#1050;&#1072;&#1095;&#1077;&#1089;&#1090;&#1074;&#1086;: SD</button>
  <button id="btn-flip" type="button" onclick="uiFlip(this)" style="pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;">&#128260; &#1053;&#1086;&#1088;&#1084;&#1072;&#1083;&#1100;&#1085;&#1099;&#1081;</button>
  <button id="btn-sd" type="button" style="pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;">&#128190; SD</button>
  <button id="btn-nvr" type="button" style="cursor:pointer;position:relative;z-index:9999;pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;">&#127902; NVR</button>
<button id="btn-cam-ext" type="button" onclick="document.getElementById('cam-ext-modal').style.display='flex'" style="pointer-events:auto !important;background:#1e293b;color:#fff;border:1px solid #475569;border-radius:8px;padding:6px 10px;font-size:13px;">&#9881; &#1050;&#1072;&#1084;&#1077;&#1088;&#1072;</button>


  <button id="btn-mot" type="button" style="pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;">&#128680; &#1044;&#1074;&#1080;&#1078;&#1077;&#1085;&#1080;&#1077;: &#1042;&#1099;&#1082;&#1083;</button>
  <a href="/snapshot.jpg" download="cam_snap.jpg" style="pointer-events:auto;padding:8px 12px;border-radius:8px;border:1px solid rgba(255,255,255,.3);background:rgba(0,0,0,.6);color:#fff;font-size:14px;text-decoration:none;">&#128247; &#1060;&#1086;&#1090;&#1086;</a>
</div>
<div id="ptz-pad" data-pos="1" style="position:fixed;bottom:20px;left:20px;display:grid;grid-template-columns:repeat(3,52px);grid-template-rows:repeat(3,52px);gap:6px;z-index:9999;touch-action:none;user-select:none;-webkit-user-select:none;">
  <div></div>
  <button data-dir="up" style="border-radius:12px;border:1px solid rgba(255,255,255,.35);background:rgba(0,0,0,.55);color:#fff;font-size:20px;">&#9650;</button>
  <div></div>
  <button data-dir="left" style="border-radius:12px;border:1px solid rgba(255,255,255,.35);background:rgba(0,0,0,.55);color:#fff;font-size:20px;">&#9664;</button>
  <button data-dir="stop" style="border-radius:12px;border:1px solid rgba(255,255,255,.35);background:rgba(180,40,40,.6);color:#fff;font-size:13px;">&#9632;</button>
  <button data-dir="right" style="border-radius:12px;border:1px solid rgba(255,255,255,.35);background:rgba(0,0,0,.55);color:#fff;font-size:20px;">&#9654;</button>
  <div></div>
  <button data-dir="down" style="border-radius:12px;border:1px solid rgba(255,255,255,.35);background:rgba(0,0,0,.55);color:#fff;font-size:20px;">&#9660;</button>
  <div></div>
</div>
<script>
(async () => {
  let audio = null, nextT = 0, aCtrl = null;
  const audioButton = document.getElementById("enable-audio");
  function playRawPCM(buf) {
    if (!audio || audio.state !== "running") return;
    const cnt = Math.floor(buf.byteLength / 2);
    if (!cnt) return;
    const ab = audio.createBuffer(1, cnt, 8000);
    const ch = ab.getChannelData(0);
    const i16 = new Int16Array(buf, 0, cnt);
    for (let i = 0; i < cnt; i++) ch.set([i16.at(i) / 32768], i);
    const src = audio.createBufferSource();
    src.buffer = ab;
    src.connect(audio.destination);
    const now = audio.currentTime;
    if (nextT < now || nextT > now + 0.4) nextT = now + 0.06;
    src.start(nextT);
    nextT += ab.duration;
  }
  async function runAudio() {
    aCtrl = new AbortController();
    try {
      const r = await fetch("/audio.pcm", {cache: "no-store", signal: aCtrl.signal});
      const rd = r.body.getReader();
      while (true) {
        const res = await rd.read();
        if (res.done) break;
        const v = res.value;
        playRawPCM(v.buffer.slice(v.byteOffset, v.byteOffset + v.byteLength));
      }
    } catch (e) {}
  }
  if (audioButton) {
    audioButton.onclick = async () => {
      try {
        if (!audio) var AC = window.AudioContext || window.webkitAudioContext; try { audio = new AC({sampleRate: 8000}); } catch(e) { audio = new AC(); }
        if (audio.state === "running") {
          if (aCtrl) { aCtrl.abort(); aCtrl = null; }
          await audio.suspend();
          nextT = 0;
          audioButton.style.background = "";
          audioButton.innerHTML = "&#128263; &#1047;&#1074;&#1091;&#1082;";
        } else {
          await audio.resume();
          nextT = 0;
          audioButton.style.background = "#16a34a";
          audioButton.innerHTML = "&#128266; &#1047;&#1074;&#1091;&#1082;";
          runAudio();
        }
      } catch (e) {}
    };
  }
})();
</script>
<div id="sd-m" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:10000;align-items:center;justify-content:center;padding:16px;"><div style="background:#1c1e24;color:#fff;border:1px solid #444;border-radius:14px;padding:18px;width:100%;max-width:360px;font-family:sans-serif;"><div style="display:flex;justify-content:space-between;margin-bottom:10px;"><b>&#128190; SD-&#1082;&#1072;&#1088;&#1090;&#1072;</b><span id="sd-x" style="font-size:22px;cursor:pointer;">&times;</span></div><div id="sd-t" style="background:#262932;padding:10px;border-radius:8px;font-size:13px;line-height:1.5;margin-bottom:10px;">&#1054;&#1078;&#1080;&#1076;&#1072;&#1085;&#1080;&#1077;...</div><div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px;"><button id="sd-r" type="button" style="padding:9px;border-radius:8px;border:1px solid #4a90e2;background:#23466e;color:#fff;">&#128260; &#1048;&#1085;&#1092;&#1086;</button><button id="sd-d" type="button" style="padding:9px;border-radius:8px;border:1px solid #4a90e2;background:#23466e;color:#fff;">&#128197; &#1044;&#1085;&#1080;</button><button id="sd-o" type="button" style="padding:9px;border-radius:8px;border:1px solid #2ecc71;background:#1e5631;color:#fff;">&#9210; &#1047;&#1072;&#1087;&#1080;&#1089;&#1100; 30&#1089;</button><button id="sd-s" type="button" style="padding:9px;border-radius:8px;border:1px solid #888;background:#3a3f47;color:#fff;">&#9209; &#1057;&#1090;&#1086;&#1087;</button></div><button id="sd-f" type="button" style="width:100%;padding:9px;border-radius:8px;border:1px solid #e74c3c;background:#6e2323;color:#fff;">&#9888;&#65039; &#1060;&#1086;&#1088;&#1084;&#1072;&#1090;&#1080;&#1088;&#1086;&#1074;&#1072;&#1090;&#1100; SD</button></div></div><script>(()=>{const m=document.getElementById("sd-m"),t=document.getElementById("sd-t"),upd=(p)=>fetch("/sd/info?poll="+(p?1:0),{cache:"no-store"}).then(r=>r.json()).then(d=>{const tot=d.total_mb?(d.total_mb/1024).toFixed(2)+" GB":"-",u=d.used_mb?(d.used_mb/1024).toFixed(2)+" GB":"0 MB",fr=(d.total_mb&&d.total_mb>=d.used_mb)?((d.total_mb-d.used_mb)/1024).toFixed(2)+" GB":"-";t.innerHTML="<b>&#1057;&#1090;&#1072;&#1090;&#1091;&#1089;:</b> "+d.last_msg+"<br><b>&#1042;&#1089;&#1077;&#1075;&#1086;:</b> "+tot+"<br><b>&#1047;&#1072;&#1085;&#1103;&#1090;&#1086; / &#1057;&#1074;&#1086;&#1073;&#1086;&#1076;&#1085;&#1086;:</b> "+u+" / "+fr;});document.getElementById("btn-sd").onclick=()=>{m.style.display="flex";upd(1);setTimeout(()=>upd(0),1200);};document.getElementById("sd-x").onclick=()=>{m.style.display="none";};document.getElementById("sd-r").onclick=()=>{upd(1);setTimeout(()=>upd(0),1200);};document.getElementById("sd-d").onclick=()=>fetch("/sd/days").then(()=>setTimeout(()=>upd(0),1200));document.getElementById("sd-o").onclick=()=>fetch("/sd/record?dur=30").then(()=>setTimeout(()=>upd(0),1000));document.getElementById("sd-s").onclick=()=>fetch("/sd/record?dur=0").then(()=>setTimeout(()=>upd(0),1000));document.getElementById("sd-f").onclick=()=>{if(confirm("&#1060;&#1086;&#1088;&#1084;&#1072;&#1090;&#1080;&#1088;&#1086;&#1074;&#1072;&#1090;&#1100; SD?"))fetch("/sd/format").then(()=>setTimeout(()=>upd(0),1500));};})();</script>
<div id="nvr-m" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.84);z-index:99999;align-items:center;justify-content:center;padding:16px;">
  <div style="background:#1c1e24;color:#fff;border:1px solid #444;border-radius:14px;padding:18px;width:100%;max-width:400px;max-height:85vh;display:flex;flex-direction:column;font-family:sans-serif;">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <b>&#127902; NVR &#1040;&#1088;&#1093;&#1080;&#1074;</b>
      <span id="nvr-x" style="font-size:26px;cursor:pointer;padding:0 6px;">&times;</span>
    </div>
    <div style="background:#262932;padding:10px;border-radius:8px;margin-bottom:10px;font-size:12px;">
      <div style="margin-bottom:6px;">&#1055;&#1091;&#1090;&#1100; &#1087;&#1072;&#1087;&#1082;&#1080;: <input id="nvr-dir" style="width:100%;margin-top:3px;padding:6px;border-radius:6px;border:1px solid #555;background:#16181d;color:#fff;box-sizing:border-box;"></div>
      <div style="display:flex;gap:8px;margin-bottom:8px;">
        <div style="flex:1;">&#1056;&#1086;&#1083;&#1080;&#1082; (&#1084;&#1080;&#1085;): <input id="nvr-seg" type="number" style="width:100%;margin-top:3px;padding:6px;border-radius:6px;border:1px solid #555;background:#16181d;color:#fff;box-sizing:border-box;"></div>
        <div style="flex:1;">&#1051;&#1080;&#1084;&#1080;&#1090; (&#1052;&#1041;): <input id="nvr-max" type="number" style="width:100%;margin-top:3px;padding:6px;border-radius:6px;border:1px solid #555;background:#16181d;color:#fff;box-sizing:border-box;"></div>
      </div>
      <button id="nvr-sav" type="button" style="width:100%;padding:7px;border-radius:6px;border:1px solid #4a90e2;background:#23466e;color:#fff;cursor:pointer;">&#128190; &#1057;&#1086;&#1093;&#1088;&#1072;&#1085;&#1080;&#1090;&#1100; &#1074; .env</button>
    </div>
    <div style="display:flex;gap:8px;margin-bottom:10px;">
      <button id="nvr-tog" type="button" style="flex:1;padding:9px;border-radius:8px;border:1px solid #2ecc71;background:#1e5631;color:#fff;cursor:pointer;">REC</button>
      <button id="nvr-ref" type="button" style="padding:9px 14px;border-radius:8px;border:1px solid #4a90e2;background:#23466e;color:#fff;cursor:pointer;">&#128260;</button>
    </div>
    <div id="nvr-list" style="overflow-y:auto;flex:1;background:#262932;border-radius:8px;padding:8px;font-size:13px;"></div>
  </div>
</div>
<div id="hud-stat" style="position:fixed;bottom:14px;left:14px;z-index:9998;pointer-events:none;background:rgba(0,0,0,.65);border:1px solid rgba(255,255,255,.22);border-radius:8px;padding:6px 10px;color:#fff;font-family:monospace;font-size:12px;line-height:1.4;">
  <span id="hud-sig">&#128994; &#1057;&#1080;&#1075;&#1085;&#1072;&#1083;: ...</span> | <span id="hud-fps">0.0 FPS</span> | <span id="hud-kbps">0 Kbit/s</span>
</div>
<script>
(() => {
  const sEl = document.getElementById("hud-sig");
  const fEl = document.getElementById("hud-fps");
  const kEl = document.getElementById("hud-kbps");
  const updHud = () => {
    const t0 = performance.now();
    fetch("/telemetry", {cache: "no-store"})
      .then(r => r.json())
      .then(d => {
        const ping = Math.round(performance.now() - t0);
        fEl.textContent = (d.fps || 0).toFixed(1) + " FPS";
        kEl.textContent = (d.kbps || 0) + " Kbit/s";
        if (!d.fps || d.fps <= 0) {
          sEl.innerHTML = "&#128308; &#1053;&#1077;&#1090; &#1087;&#1086;&#1090;&#1086;&#1082;&#1072;";
        } else if (ping < 90 && d.fps >= 1) {
          sEl.innerHTML = "&#128994; &#1054;&#1090;&#1083;&#1080;&#1095;&#1085;&#1099;&#1081; (" + ping + " ms)";
        } else if (ping < 250 && d.fps > 0) {
          sEl.innerHTML = "&#128993; &#1057;&#1088;&#1077;&#1076;&#1085;&#1080;&#1081; (" + ping + " ms)";
        } else {
          sEl.innerHTML = "&#128308; &#1057;&#1083;&#1072;&#1073;&#1099;&#1081; (" + ping + " ms)";
        }
      })
      .catch(() => { sEl.innerHTML = "&#128308; &#1054;&#1092;&#1092;&#1083;&#1072;&#1081;&#1085;"; });
  };
  setInterval(updHud, 2000);
  updHud();
})();
</script>
<div id="cam-ext-modal"  style="display:none;pointer-events:auto !important;position:fixed;inset:0;background:rgba(0,0,0,.8);z-index:99999 !important;align-items:center;justify-content:center;padding:12px;">
<div id="cam-ext-box" style="pointer-events:auto !important;background:#1e293b;color:#fff;border:1px solid #475569;border-radius:12px;padding:14px;width:100%;max-width:360px;font-family:sans-serif;font-size:13px;">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;"><b>&#9881; &#1050;&#1072;&#1084;&#1077;&#1088;&#1072; <span id="ce-st" style="color:#4ade80;font-weight:normal;margin-left:6px;"></span></b><button type="button" onclick="document.getElementById('cam-ext-modal').style.display='none'" style="pointer-events:auto !important;background:none;border:none;color:#94a3b8;font-size:20px;cursor:pointer;">&#10005;</button></div>
<div style="margin-bottom:10px;padding:8px;background:#0f172a;border-radius:8px;">
  <div style="margin-bottom:6px;color:#94a3b8;">&#128205; &#1058;&#1086;&#1095;&#1082;&#1080; &#1086;&#1073;&#1079;&#1086;&#1088;&#1072;:</div>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:6px;">
    <button type="button" style="pointer-events:auto !important;padding:11px 0;background:#2563eb;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:bold;cursor:pointer;" onclick="camExt('psp_call',{id:1})">T1</button>
    <button type="button" style="pointer-events:auto !important;padding:11px 0;background:#2563eb;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:bold;cursor:pointer;" onclick="camExt('psp_call',{id:2})">T2</button>
    <button type="button" style="pointer-events:auto !important;padding:11px 0;background:#2563eb;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:bold;cursor:pointer;" onclick="camExt('psp_call',{id:3})">T3</button>
    <button type="button" style="pointer-events:auto !important;padding:11px 0;background:#2563eb;color:#fff;border:none;border-radius:8px;font-size:15px;font-weight:bold;cursor:pointer;" onclick="camExt('psp_call',{id:4})">T4</button>
  </div>
  <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;">
    <button type="button" style="pointer-events:auto !important;padding:9px 0;background:#334155;color:#cbd5e1;border:none;border-radius:7px;font-size:12px;cursor:pointer;" onclick="camExt('psp_add',{id:1})">&#1047;&#1072;&#1087;. 1</button>
    <button type="button" style="pointer-events:auto !important;padding:9px 0;background:#334155;color:#cbd5e1;border:none;border-radius:7px;font-size:12px;cursor:pointer;" onclick="camExt('psp_add',{id:2})">&#1047;&#1072;&#1087;. 2</button>
    <button type="button" style="pointer-events:auto !important;padding:9px 0;background:#334155;color:#cbd5e1;border:none;border-radius:7px;font-size:12px;cursor:pointer;" onclick="camExt('psp_add',{id:3})">&#1047;&#1072;&#1087;. 3</button>
    <button type="button" style="pointer-events:auto !important;padding:9px 0;background:#334155;color:#cbd5e1;border:none;border-radius:7px;font-size:12px;cursor:pointer;" onclick="camExt('psp_add',{id:4})">&#1047;&#1072;&#1087;. 4</button>
  </div>
</div>
<div style="margin-bottom:8px;padding:8px;background:#0f172a;border-radius:8px;display:flex;justify-content:space-between;align-items:center;">
  <span>&#128660; &#1055;&#1072;&#1090;&#1088;&#1091;&#1083;&#1100;:</span>
  <div>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#16a34a;" onclick="camExt('patrol',{on:true,sec:15})">&#1042;&#1082;&#1083;</button>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#475569;" onclick="camExt('patrol',{on:false})">&#1042;&#1099;&#1082;&#1083;</button>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#334155;" onclick="camExt('patrol',{on:true,sec:10})">10c</button>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#334155;" onclick="camExt('patrol',{on:true,sec:25})">25c</button>
  </div>
</div>
<div style="margin-bottom:8px;padding:8px;background:#0f172a;border-radius:8px;display:flex;justify-content:space-between;align-items:center;">
  <span>&#9889; &#1063;&#1072;&#1089;&#1090;&#1086;&#1090;&#1072;:</span>
  <div>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#0284c7;" onclick="camExt('freq',{hz:50})">50 &#1043;&#1094;</button>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#334155;" onclick="camExt('freq',{hz:60})">60 &#1043;&#1094;</button>
  </div>
</div>
<div style="margin-bottom:8px;padding:8px;background:#0f172a;border-radius:8px;display:flex;justify-content:space-between;align-items:center;">
  <span>&#128338; &#1042;&#1088;&#1077;&#1084;&#1103; OSD:</span>
  <div>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#16a34a;" onclick="camExt('osd',{enable:1})">&#1042;&#1082;&#1083;</button>
    <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#475569;" onclick="camExt('osd',{enable:0})">&#1042;&#1099;&#1082;&#1083;</button>
  </div>
</div>
<div style="margin-bottom:10px;padding:8px;background:#0f172a;border-radius:8px;">
  <input id="ws" placeholder="Wi-Fi SSID" style="pointer-events:auto !important;width:42%;padding:6px;border-radius:6px;border:1px solid #334155;background:#1e293b;color:#fff;">
  <input id="wp" type="password" placeholder="&#1055;&#1072;&#1088;&#1086;&#1083;&#1100;" style="pointer-events:auto !important;width:41%;padding:6px;border-radius:6px;border:1px solid #334155;background:#1e293b;color:#fff;">
  <button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;background:#0284c7;" onclick="if(confirm('&#1057;&#1084;&#1077;&#1085;&#1080;&#1090;&#1100; Wi-Fi?'))camExt('wifi',{ssid:ws.value,pwd:wp.value})">OK</button>
</div>
<button type="button" style="pointer-events:auto !important;padding:7px 10px;border:none;border-radius:7px;color:#fff;font-size:13px;cursor:pointer;width:100%;padding:9px;background:#dc2626;font-weight:bold;" onclick="if(confirm('&#1055;&#1077;&#1088;&#1077;&#1079;&#1072;&#1075;&#1088;&#1091;&#1079;&#1080;&#1090;&#1100; &#1082;&#1072;&#1084;&#1077;&#1088;&#1091;?'))camExt('reboot',{})">&#128260; &#1055;&#1077;&#1088;&#1077;&#1079;&#1072;&#1075;&#1088;&#1091;&#1079;&#1080;&#1090;&#1100; &#1082;&#1072;&#1084;&#1077;&#1088;&#1091;</button></div></div><script>
window.applyOsd = function(on) {
  var oc = document.getElementById("osd-clk");
  if (!oc) return;
  oc.style.display = on ? "block" : "none";
  if (on) {
    var tick = function() {
      var d = new Date();
      oc.textContent = d.toLocaleDateString("ru-RU") + " " + d.toLocaleTimeString("ru-RU");
    };
    tick();
    if (!window._ot) window._ot = setInterval(tick, 1000);
  } else if (window._ot) {
    clearInterval(window._ot);
    window._ot = null;
  }
};
window.addEventListener("DOMContentLoaded", function(){ window.applyOsd(localStorage.getItem("a9_osd") === "1"); });
setTimeout(function(){ window.applyOsd(localStorage.getItem("a9_osd") === "1"); }, 100);
window._unusedOsd = function(on) {
  var oc = document.getElementById("osd-clk");
  if (!oc) return;
  oc.style.display = on ? "block" : "none";
  if (on) {
    oc.textContent = new Date().toLocaleString("ru-RU");
    if (!window._ot) window._ot = setInterval(function() { oc.textContent = new Date().toLocaleString("ru-RU"); }, 1000);
  }
};
window.applyOsd(localStorage.getItem("a9_osd") === "1");
window.camExt = function(a, e) {
  var q = new URLSearchParams(Object.assign({act: a}, e || {})).toString();
  var st = document.getElementById("ce-st"); if (st) st.textContent = "...";
  fetch("/cam/ext?" + q, {cache: "no-store"}).then(function(r) { return r.json(); }).then(function() {
    if (st) st.textContent = "OK: " + a;
    if (a === "osd") { var _on = Boolean(e && Number(e.enable)); localStorage.setItem("a9_osd", _on ? "1" : "0"); if (window.applyOsd) window.applyOsd(_on);
      localStorage.setItem("a9_osd", e && e.enable ? "1" : "0");
      window.applyOsd(!!(e && e.enable));
    }
    if (a === "reboot" || a === "wifi") document.getElementById("cam-ext-modal").style.display = "none";
  }).catch(function() { if (st) st.textContent = "Err"; });
};

(function() {
  window._sndOn = false; window._audio = null; window._aCtrl = null; window._nextT = 0;
  var abtn = document.getElementById("enable-audio");
  function playPCM(buf) {
    if (!window._sndOn || !window._audio) return;
    var cnt = Math.floor(buf.byteLength / 2); if (!cnt) return;
    var ab = window._audio.createBuffer(1, cnt, 8000);
    ab.copyToChannel(Float32Array.from(new Int16Array(buf, 0, cnt), function(v) { return v / 32768; }), 0);
    var src = window._audio.createBufferSource(); src.buffer = ab; src.connect(window._audio.destination);
    var now = window._audio.currentTime; if (window._nextT < now || window._nextT > now + 0.35) window._nextT = now + 0.05;
    src.start(window._nextT); window._nextT += ab.duration;
  }
  async function startAudio() {
    window._aCtrl = new AbortController();
    try {
      var r = await fetch("/audio.pcm", {cache: "no-store", signal: window._aCtrl.signal});
      var rd = r.body.getReader();
      while (window._sndOn) { var res = await rd.read(); if (res.done || !window._sndOn) break; playPCM(res.value.buffer.slice(res.value.byteOffset, res.value.byteOffset + res.value.byteLength)); }
    } catch (e) {}
  }
  if (abtn) {
    abtn.innerHTML = "&#128263; &#1047;&#1074;&#1091;&#1082;";
    abtn.onclick = async function(e) {
      e.stopPropagation();
      if (window._sndOn) {
        window._sndOn = false;
        if (window._aCtrl) { try { window._aCtrl.abort(); } catch(_) {} window._aCtrl = null; }
        if (window._audio) { try { await window._audio.close(); } catch(_) {} window._audio = null; }
        abtn.style.background = "rgba(0,0,0,.6)"; abtn.innerHTML = "&#128263; &#1047;&#1074;&#1091;&#1082;";
      } else {
        var AC = window.AudioContext || window.webkitAudioContext;
        try { window._audio = new AC({sampleRate: 8000}); } catch(_) { window._audio = new AC(); }
        await window._audio.resume(); window._sndOn = true; window._nextT = 0;
        abtn.style.background = "#16a34a"; abtn.innerHTML = "&#128266; &#1047;&#1074;&#1091;&#1082;";
        startAudio();
      }
    };
  }
})();
</script>
<script>
window._irI = 0; window._irL = Array.of("&#127769; &#1048;&#1050;: &#1040;&#1074;&#1090;&#1086;", "&#9728;&#65039; &#1048;&#1050;: &#1042;&#1099;&#1082;&#1083;", "&#127761; &#1048;&#1050;: &#1042;&#1082;&#1083;");
window.uiIr = function(b) { window._irI = (window._irI + 1) % 3; b.innerHTML = window._irL.at(window._irI); fetch("/ctrl?act=ir&val=" + window._irI, {cache: "no-store"}).catch(function(){}); };
window._hd = false;
window.uiRes = function(b) { window._hd = !window._hd; b.innerHTML = window._hd ? "&#128250; &#1050;&#1072;&#1095;&#1077;&#1089;&#1090;&#1074;&#1086;: HD" : "&#128250; &#1050;&#1072;&#1095;&#1077;&#1089;&#1090;&#1074;&#1086;: SD"; fetch("/ctrl?act=res&val=" + (window._hd ? 1 : 0), {cache: "no-store"}).catch(function(){}); };
window._flI = parseInt(localStorage.getItem("a9_flip") || "0", 10) || 0;
window._flL = Array.of("&#128260; &#1053;&#1086;&#1088;&#1084;&#1072;&#1083;&#1100;&#1085;&#1099;&#1081;", "&#128260; &#1055;&#1086;&#1074;&#1086;&#1088;&#1086;&#1090; 180&#176;", "&#8596; &#1047;&#1077;&#1088;&#1082;&#1072;&#1083;&#1086; &#1043;", "&#8597; &#1047;&#1077;&#1088;&#1082;&#1072;&#1083;&#1086; &#1042;");
window._flT = Array.of("none", "rotate(180deg)", "scaleX(-1)", "scaleY(-1)");
window.applyFlip = function(idx) { var im = document.getElementById("mjpg"), b = document.getElementById("btn-flip"); if (im) im.style.transform = window._flT.at(idx) || "none"; if (b) b.innerHTML = window._flL.at(idx); };
window.uiFlip = function(b) { window._flI = (window._flI + 1) % 4; localStorage.setItem("a9_flip", String(window._flI)); window.applyFlip(window._flI); };
window.applyFlip(window._flI);

(function() {
  var mm = Array.of({l:"&#128680; &#1044;&#1074;&#1080;&#1078;&#1077;&#1085;&#1080;&#1077;: &#1042;&#1099;&#1082;&#1083;",v:0,bg:"rgba(0,0,0,.6)"},{l:"&#128680; &#1044;&#1074;&#1080;&#1078;: &#1053;&#1080;&#1079;&#1082;",v:1,bg:"rgba(210,160,20,.85)"},{l:"&#128680; &#1044;&#1074;&#1080;&#1078;: &#1057;&#1088;&#1077;&#1076;",v:2,bg:"rgba(230,110,20,.85)"},{l:"&#128680; &#1044;&#1074;&#1080;&#1078;: &#1042;&#1099;&#1089;&#1086;&#1082;",v:3,bg:"rgba(210,40,40,.85)"});
  var mi = 0, bm = document.getElementById("btn-mot");
  if (bm) bm.onclick = function() { mi = (mi + 1) % mm.length; var cur = mm.at(mi); fetch("/ctrl?act=motion&val=" + cur.v, {cache: "no-store"}).catch(function(){}); bm.innerHTML = cur.l; bm.style.background = cur.bg; };

  var nm = document.getElementById("nvr-m"), bNvr = document.getElementById("btn-nvr"), xNvr = document.getElementById("nvr-x"), dIn = document.getElementById("nvr-dir"), sIn = document.getElementById("nvr-seg"), mIn = document.getElementById("nvr-max"), lst = document.getElementById("nvr-list"), tog = document.getElementById("nvr-tog"), sav = document.getElementById("nvr-sav"), ref = document.getElementById("nvr-ref");
  var ldNvr = function() {
    fetch("/nvr/list", {cache: "no-store"}).then(function(r) { return r.json(); }).then(function(d) {
      if (dIn) dIn.value = d.dir || ""; if (sIn) sIn.value = d.seg || 10; if (mIn) mIn.value = d.max || 5120;
      if (tog) { tog.textContent = d.enabled ? "REC: ON (Stop)" : "REC: OFF (Start)"; tog.style.background = d.enabled ? "#1e5631" : "#6e2323"; }
      if (lst) lst.innerHTML = (d.files && d.files.length) ? d.files.map(function(f) { return "<div style='display:flex;justify-content:space-between;padding:6px;border-bottom:1px solid #333'><span>" + (f.active ? "&#128308; " : "") + f.name + " (" + f.size_mb + " MB)</span><a href='/nvr/file?name=" + encodeURIComponent(f.name) + "' style='color:#4da3ff;text-decoration:none;font-weight:bold'>&#11015; TS</a></div>"; }).join("") : "<div style='color:#888;padding:8px'>&#1047;&#1072;&#1087;&#1080;&#1089;&#1077;&#1081; &#1087;&#1086;&#1082;&#1072; &#1085;&#1077;&#1090;</div>";
    }).catch(function(){});
  };
  if (bNvr && nm) bNvr.onclick = function() { nm.style.display = "flex"; ldNvr(); };
  if (xNvr && nm) xNvr.onclick = function() { nm.style.display = "none"; };
  if (tog) tog.onclick = function() { fetch("/nvr/toggle", {cache: "no-store"}).then(ldNvr).catch(function(){}); };
  if (ref) ref.onclick = ldNvr;
  if (sav) sav.onclick = function() { fetch("/nvr/save?dir=" + encodeURIComponent(dIn.value) + "&seg=" + encodeURIComponent(sIn.value) + "&max=" + encodeURIComponent(mIn.value), {cache: "no-store"}).then(ldNvr).catch(function(){}); };

  var pad = document.getElementById("ptz-pad");
  if (pad) {
    var activeDir = null, sendPtz = function(dir) { fetch("/ctrl?act=" + dir, {cache: "no-store"}).catch(function(){}); };
    pad.querySelectorAll("button[data-dir]").forEach(function(btn) {
      var dir = btn.getAttribute("data-dir");
      var start = function(e) { if (e.cancelable) e.preventDefault(); if (dir === "stop") { activeDir = null; sendPtz("stop"); return; } if (activeDir === dir) return; activeDir = dir; sendPtz(dir); };
      var stop = function(e) { if (e && e.cancelable) e.preventDefault(); if (activeDir && dir !== "stop") { activeDir = null; sendPtz("stop"); } };
      btn.addEventListener("pointerdown", start); btn.addEventListener("pointerup", stop); btn.addEventListener("pointercancel", stop);
      btn.addEventListener("touchstart", start, {passive: false}); btn.addEventListener("touchend", stop);
    });
  }

  setInterval(function() {
    var t0 = performance.now();
    fetch("/telemetry", {cache: "no-store"}).then(function(r) { return r.json(); }).then(function(d) {
      var ms = Math.round(performance.now() - t0);
      var q = ms < 60 ? "&#1054;&#1090;&#1083;&#1080;&#1095;&#1085;&#1099;&#1081;" : (ms < 180 ? "&#1057;&#1088;&#1077;&#1076;&#1085;&#1080;&#1081;" : "&#1057;&#1083;&#1072;&#1073;&#1099;&#1081;");
      var dot = ms < 60 ? "#4ade80" : (ms < 180 ? "#facc15" : "#f87171");
      var st = document.getElementById("hud-stat");
      if (st) st.innerHTML = '<span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:' + dot + ';margin-right:6px;"></span>' + q + ' (' + ms + ' ms) | ' + (d.fps || 0) + ' FPS | ' + (d.kbps || 0) + ' Kbit/s';
      var rb = document.getElementById("rec-badge");
      if (rb) rb.style.display = d.rec ? "flex" : "none";
    }).catch(function(){});
  }, 1000);
})();
</script>
<div id="osd-clk" style="display:none;position:fixed;bottom:52px;left:14px;z-index:9998;color:#fff;background:rgba(0,0,0,.65);border:1px solid rgba(255,255,255,.25);padding:4px 9px;border-radius:6px;font-family:monospace;font-size:13px;font-weight:bold;pointer-events:none;"></div>
</body>
</html>
"""

def make_handler(state, first_timeout, max_age):
    class H(BaseHTTPRequestHandler):

        def log_message(self, *a):
            pass

        def do_HEAD(self):
            self.send_response(200)
            if self.path.startswith("/live.ts"):
                self.send_header("Content-Type", "video/mp2t")
            else:
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

        def _wait_first(self):
            with state.cond:
                state.cond.wait_for(
                    lambda: state.jpeg is not None or state.stop,
                    timeout=first_timeout,
                )
                return state.jpeg

        def jpeg0(self):
            with state.cond:
                return state.jpeg

        def stream_ts(self):
        
            output = av.open(
                self.wfile,
                mode="w",
                format="mpegts",
                options={
                    "mpegts_flags": "resend_headers",
                    "flush_packets": "1",
                },
                buffer_size=188 * 7,
            )

            video = output.add_stream("libx264", rate=10)
            video.width = 640
            video.height = 480
            video.pix_fmt = "yuv420p"
            video.time_base = Fraction(1, 10)
            video.codec_context.time_base = Fraction(1, 10)
            video.options = {
                "preset": "ultrafast",
                "threads": "2",
                "tune": "zerolatency",
                "bf": "0",
                "g": "5",
                "sc_threshold": "0",
            }

            audio = output.add_stream("aac", rate=8000)
            audio.layout = "mono"
            audio.bit_rate = 64000
            audio.time_base = Fraction(1, 8000)
            audio.codec_context.time_base = Fraction(1, 8000)
            audio.codec_context.options = {"aac_coder": "twoloop"}

            video_pts = 0
            audio_pts = 0
            audio_pending = np.empty(0, dtype=np.int16)
            last_video = 0

            with state.audio_cond:
                last_audio = state.audio_seq

            def mux_packets(packets):
                for packet in packets:
                    output.mux(packet)

            stream_start = time.monotonic()
            last_video_pts = -1

            def encode_video(jpg):
                nonlocal video_pts, last_video_pts

                with av.open(
                    io.BytesIO(jpg), mode="r", format="mjpeg"
                ) as source:
                    frame = next(source.decode(video=0))

                frame = frame.reformat(
                    width=video.width,
                    height=video.height,
                    format="yuv420p",
                )

                # Timestamp based on elapsed time,
                # not on number of frames received.
                pts = int((time.monotonic() - stream_start) * 10)
                pts = max(pts, last_video_pts + 1)
                if last_video_pts >= 0 and pts - last_video_pts > 3:
                    pts = last_video_pts + 3

                frame.pts = pts
                frame.time_base = Fraction(1, 10)

                video_pts = pts + 1
                last_video_pts = pts

                mux_packets(video.encode(frame))

            def encode_audio(samples):
                nonlocal audio_pts

                frame = av.AudioFrame.from_ndarray(
                    samples.reshape(1, -1),
                    format="s16",
                    layout="mono",
                )
                frame.sample_rate = 8000
                frame.pts = audio_pts
                frame.time_base = Fraction(1, 8000)
                audio_pts += len(samples)

                mux_packets(audio.encode(frame))

            try:
                while not state.stop:
                    jpg, last_video = state.wait_newer(
                        last_video, 0.01
                    )

                    if jpg is not None:
                        encode_video(jpg)

                    with state.audio_cond:
                        chunks = [
                            item for item in state.audio_chunks
                            if item[0] > last_audio
                        ]

                    for seq, timestamp, pcm in chunks:
                        audio_pending = np.concatenate((
                            audio_pending,
                            np.frombuffer(pcm, dtype="<i2"),
                        ))
                        last_audio = seq

                    while len(audio_pending) >= 1024:
                        block = audio_pending[:1024]
                        audio_pending = audio_pending[1024:]
                        encode_audio(block)

                    # If client slows down, flushes audio to avoid latency
                    if len(audio_pending) > 16000:
                        audio_pending = audio_pending[-8192:]

            finally:
                try:
                    mux_packets(video.encode(None))
                    if len(audio_pending) >= 1024:
                        encode_audio(audio_pending[:1024])
                    mux_packets(audio.encode(None))
                except Exception:
                    pass
                try:
                    output.close()
                except Exception:
                    pass

        def do_GET(self):
            import base64 as _b64
            _wu = os.environ.get("WEB_USER", "")
            _wp = os.environ.get("WEB_PASS", "")
            if _wu and _wp:
                _exp = "Basic " + _b64.b64encode(f"{_wu}:{_wp}".encode()).decode()
                if self.headers.get("Authorization") != _exp:
                    print(f"[{time.strftime('%H:%M:%S')}] [HTTP-AUTH-FAIL] ip={self.client_address} path={self.path}", flush=True)
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", "Basic realm=\"Camera\"")
                    self.end_headers()
                    return
            _cip = self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For") or self.client_address
            if self.path in ("/", "/live.mp4", "/live.ts", "/stream.mjpg") or self.path.startswith("/?"):
                print(f"[{time.strftime('%H:%M:%S')}] [HTTP-CONN] client={_cip} path={self.path}", flush=True)
            state.acquire_client()
            try:
                return self._do_GET_inner()
            except (BrokenPipeError, ConnectionResetError):
                return
            finally:
                if self.path in ("/", "/live.mp4", "/live.ts", "/stream.mjpg") or self.path.startswith("/?"):
                    print(f"[{time.strftime('%H:%M:%S')}] [HTTP-DISC] client={_cip} path={self.path}", flush=True)
                state.release_client()
        def _do_GET_inner(self):
        
            if self.path == "/live.ts":
                if self._wait_first() is None:
                    self.send_error(503, "no frame yet")
                    return

                self.send_response(200)
                self.send_header(
                    "Content-Type", "video/mp2t"
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()

                try:
                    self.stream_ts()

                except (
                    BrokenPipeError,
                    ConnectionResetError,
                    OSError,
                ):
                    # player disconnected.
                    pass

                except Exception as exc:
                    # PyAV error management.
                    import traceback; traceback.print_exc()
                    if type(exc).__name__ == "PyAVCallbackError":
                        sys.stderr.write(
                            "[MPEGTS] Client player disconnected.\n"
                        )
                    else:
                        sys.stderr.write(
                            f"[MPEGTS] error: {exc!r}\n"
                        )

                return        
        
            if self.path in ("/", "/index.html", "/stream"):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Content-Length", str(len(VIEWER)))
                self.end_headers()
                self.wfile.write(VIEWER)
                return

            if self.path == "/stream?raw=1":
                if self._wait_first() is None:
                    self.send_error(503, "no frame yet")
                    return

                self.send_response(200)
                self.send_header(
                    "Content-Type", "application/octet-stream"
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()

                def send_record(kind, timestamp, payload):
                    header = (
                        b"A9AV"
                        + struct.pack(
                            ">BQI", kind,
                            int(timestamp * 1_000_000),
                            len(payload)
                        )
                    )
                    self.wfile.write(header)
                    self.wfile.write(payload)
                    self.wfile.flush()

                last_video = 0
                with state.audio_cond:
                    last_audio = state.audio_seq

                try:
                    while not state.stop:
                        jpg, last_video = state.wait_newer(
                            last_video, 0.02
                        )

                        if jpg is not None:
                            send_record(1, time.monotonic(), jpg)

                        with state.audio_cond:
                            new_audio = [
                                item for item in state.audio_chunks
                                if item[0] > last_audio
                            ]

                        for seq, timestamp, pcm in new_audio:
                            send_record(2, timestamp, pcm)
                            last_audio = seq

                except (BrokenPipeError, ConnectionResetError, OSError):
                    return

                return

            if self.path == "/telemetry":
                import json
                _age = round(time.time() - getattr(state, "last_frame_ts", 0.0) or getattr(state, "_stat_ts", time.time()), 1)
                _tb = json.dumps({
                    "fps": state.fps_val,
                    "kbps": state.kbps_val,
                    "age": _age
                }).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(_tb)))
                self.end_headers()
                self.wfile.write(_tb)
                return

            if self.path.startswith("/audio.pcm"):
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                aseq = getattr(state, "audio_seq", 0)
                try:
                    while not state.stop:
                        out = []
                        with state.audio_cond:
                            state.audio_cond.wait_for(lambda: state.stop or state.audio_seq != aseq, timeout=1.0)
                            if state.stop: break
                            for seq_i, _, pcm_i in state.audio_chunks:
                                if seq_i > aseq:
                                    out.append(pcm_i)
                                    aseq = seq_i
                        for chunk in out:
                            self.wfile.write(chunk)
                        if out:
                            self.wfile.flush()
                except Exception:
                    pass
                return
            if self.path.startswith("/cam/ext"):
                _pb_b = lambda fn, b: P.enc_varint((fn << 3) | 2) + P.enc_varint(len(b)) + b
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                act = qs.get("act", [""])[0]
                sid = int(qs.get("id", ["1"])[0])
                if act == "psp_add":
                    _ptz_track(10)
                    px, py = round(_PTZ_POS["x"], 2), round(_PTZ_POS["y"], 2)
                    _PTZ_POS["pts"].update({int(sid): (px, py)})
                    print(f"[PTZ-PTS] Записана точка T{sid}: X={px}с, Y={py}с", flush=True)
                    ep = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
                    ls = [l for l in open(ep, encoding="utf-8") if not l.startswith(f"PSP_{sid}=")] if os.path.exists(ep) else []
                    ls.append(f"PSP_{sid}={px},{py}" + chr(10))
                    open(ep, "w", encoding="utf-8").writelines(ls)
                elif act == "psp_call": _ptz_goto(_get_st(), sid)
                elif act == "patrol":
                    _PATROL["on"] = qs.get("on", ["false"])[0] in ("true", "1")
                    if "sec" in qs: _PATROL["sec"] = max(5, int(qs["sec"][0]))
                    ep = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
                    ls = [l for l in open(ep, encoding="utf-8") if not l.startswith(("PATROL_ON=", "PATROL_SEC="))] if os.path.exists(ep) else []
                    ls += [f"PATROL_ON={1 if _PATROL['on'] else 0}\n", f"PATROL_SEC={_PATROL['sec']}\n"]
                    open(ep, "w", encoding="utf-8").writelines(ls)
                    print(f"[PTZ-PTS] Патруль={_PATROL['on']}, пауза={_PATROL['sec']}с, точки={list(_PTZ_POS['pts'].keys())}", flush=True)
                elif act == "light":
                    md = int(qs.get("mode", ["0"])[0])
                    if md in (2, 3): state.push_cmd(2664, P.pb_varint_field(2, 34))
                    elif md == 1: state.push_cmd(2664, P.pb_varint_field(2, 35))
                    else: state.push_cmd(2664, P.pb_varint_field(2, 35)); state.push_cmd(getattr(P, "CMD_NIGHT", 2642), P.pb_varint_field(2, 0))
                elif act == "osd":
                    en = int(qs.get("enable", ["1"])[0])
                    state.push_cmd(2649, P.pb_varint_field(1, 0) + _pb_b(2, P.pb_varint_field(1, en) + _pb_b(2, b"A9") + P.pb_varint_field(5, en)))
                elif act == "wifi" and qs.get("ssid", [""])[0]:
                    state.push_cmd(2662, P.pb_varint_field(1, 0) + _pb_b(2, qs["ssid"][0].encode()) + _pb_b(3, qs.get("pwd", [""])[0].encode()) + _pb_b(4, b"RU"))
                elif act == "freq":
                    hz = int(str(qs.get("hz", "50")).strip("[]'\""))
                    state.push_cmd(2639, P.pb_varint_field(1, 0) + P.pb_varint_field(2, hz))
                elif act == "reboot": state.push_cmd(2670, P.pb_varint_field(1, 0))
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b'{"ok":true}')
                return
            if self.path.startswith("/nvr/"):
                import json
                from urllib.parse import urlparse, parse_qs
                u=urlparse(self.path); qs=parse_qs(u.query)
                if u.path=="/nvr/save" and NVR:
                    NVR.update_config(qs.get("dir",[""])[0], qs.get("seg",[""])[0], qs.get("max",[""])[0])
                    b=b"{\"ok\":true}"
                    self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b); return
                elif u.path=="/nvr/list":
                    b=json.dumps({"enabled":bool(NVR and NVR.enabled),"motion":(NVR.motion_level if NVR else 0),"dir":NVR.rec_dir if NVR else "","seg":(NVR.seg_sec//60) if NVR else 10,"max":(NVR.max_bytes//1048576) if NVR else 5120,"files":NVR.list_files() if NVR else []},ensure_ascii=False).encode("utf-8")
                    self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b); return
                elif u.path=="/nvr/toggle":
                    if NVR: NVR.update_config(None, None, None, not NVR.enabled)
                    b=json.dumps({"enabled":bool(NVR and NVR.enabled)}).encode("utf-8")
                    self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b); return
                elif u.path=="/nvr/file" and NVR:
                    fn=os.path.basename(qs.get("name",[""])[0]); fp=os.path.join(NVR.rec_dir,fn)
                    if (fn.startswith("rec_") or fn.startswith("motion_")) and fn.endswith(".ts") and os.path.isfile(fp):
                        self.send_response(200); self.send_header("Content-Type","video/mp2t"); self.send_header("Content-Disposition",f"attachment; filename=\"{fn}\""); self.send_header("Content-Length",str(os.path.getsize(fp))); self.end_headers()
                        with open(fp,"rb") as vf:
                            while True:
                                ch=vf.read(65536)
                                if not ch: break
                                self.wfile.write(ch)
                        return
                self.send_response(404); self.end_headers(); return
            if self.path.startswith("/sd/"):
                import json, datetime
                from urllib.parse import urlparse, parse_qs
                u=urlparse(self.path); qs=parse_qs(u.query)
                if u.path=="/sd/info":
                    if qs.get("poll",["0"])[0]=="1":
                        for sc in (2669,2670,2671,2672,2616,2621,2625): state.push_cmd(sc,P.pb_varint_field(1,0))
                    body=json.dumps(state.sd_data,ensure_ascii=False).encode("utf-8")
                elif u.path=="/sd/format":
                    for fc in (2673,2674,2676,2677,2622,2626): state.push_cmd(fc,P.pb_varint_field(1,0))
                    state.sd_data["last_msg"]="Форматирование запущено..."
                    body=b"{\"ok\":true}"
                elif u.path=="/sd/record":
                    dur=int(qs.get("dur",["30"])[0])
                    for rc in (2684,2685,2686,2687,2628): state.push_cmd(rc,P.pb_varint_field(1,0)+P.pb_varint_field(2,dur))
                    state.sd_data["last_msg"]=f"Запись: {dur}с" if dur>0 else "Запись выкл"
                    body=b"{\"ok\":true}"
                elif u.path=="/sd/days":
                    n=datetime.datetime.now(); pl=P.pb_varint_field(1,0)+P.pb_varint_field(2,n.year)+P.pb_varint_field(3,n.month)
                    for hc in (2617,2618,2619,2620,2679,2681): state.push_cmd(hc,pl)
                    state.sd_data["last_msg"]=f"Архив {n.month:02d}.{n.year}..."
                    body=b"{\"ok\":true}"
                else: body=b"{\"ok\":false}"
                self.send_response(200); self.send_header("Content-Type","application/json; charset=utf-8"); self.send_header("Cache-Control","no-store"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body); return
            if self.path.startswith("/ctrl"):
                from urllib.parse import urlparse, parse_qs
                qs = parse_qs(urlparse(self.path).query)
                act = qs.get("act", [""])[0]
                val = int(qs.get("val", ["0"])[0])
                ptz_map = {"stop": 10, "up": 11, "down": 12, "left": 13, "right": 14, "light_on": 34, "light_off": 35}
                if act in ptz_map:
                    state.push_cmd(2664, P.pb_varint_field(2, ptz_map[act])); _ptz_track(ptz_map[act])
                elif act == "ir":
                    state.push_cmd(getattr(P, "CMD_NIGHT", 2642), P.pb_varint_field(2, val))
                elif act == "res":
                    state.push_cmd(getattr(P, "CMD_SETRES", 2612), P.pb_varint_field(2, val))
                elif act == "motion":
                    if NVR:
                        NVR.set_motion(int(next(iter(qs.get("val", ("0",))))))
                    mv = int(qs.get("val", ["0"])[0])
                    state.push_cmd(2637, P.pb_varint_field(1, 0) + P.pb_varint_field(2, mv))
                elif act == "flip":
                    fval = int(next(iter(qs.get("val", ("1",)))))
                    state.push_cmd(2646, P.pb_varint_field(1, 0) + P.pb_varint_field(2, fval))
                    state.push_cmd(2656, P.pb_varint_field(1, 0) + P.pb_varint_field(2, fval))
                elif act == "led_full":
                    ch = int(qs.get("ch", ["0"])[0])
                    md = int(qs.get("mode", ["1"])[0])
                    c_num = int(qs.get("cmd", ["2655"])[0])
                    pl = P.pb_varint_field(1, ch) + P.pb_varint_field(2, md)
                    state.push_cmd(c_num, pl)
                elif act == "whitelight":
                    def _enc_vi(n):
                        out = bytearray()
                        while True:
                            b = n & 0x7F
                            n >>= 7
                            if n:
                                out.append(b | 0x80)
                            else:
                                out.append(b)
                                break
                        return bytes(out)
                    p0 = int(qs.get("p0", ["0"])[0])
                    cid_num = int(qs.get("cid", ["201"])[0])
                    # BaseCmdExec: cid=201 (field 1), pints=[p0, 0, 0] как 3 отдельных varint-поля №2
                    base_cmd = (
                        P.pb_varint_field(1, cid_num)
                        + P.pb_varint_field(2, p0)
                        + P.pb_varint_field(2, 0)
                        + P.pb_varint_field(2, 0)
                    )
                    _cam_did = (state.status or {}).get("did") or "PPFT0302D37F51CC9A"
                    did_b = _cam_did.encode("utf-8")
                    _arr = P.enc_varint(p0) + b"\x00\x00"; base_cmd = P.pb_varint_field(1, cid_num) + b"\x12" + P.enc_varint(len(_arr)) + _arr
                    ppiot = (
                        P.pb_varint_field(1, 1)
                        + b"\x12" + _enc_vi(len(did_b)) + did_b
                        + b"\x22" + _enc_vi(len(base_cmd)) + base_cmd
                        + P.pb_varint_field(5, 1)
                        + P.pb_varint_field(6, int(time.time()))
                    )
                    outer = b"\x0a" + _enc_vi(len(ppiot)) + ppiot
                    c_target = int(qs.get("cmd", ["2630"])[0])
                    state.push_cmd(c_target, outer)
                elif act == "dp":
                    dpid = int(qs.get("dpid", ["2352"])[0])
                    vfield = int(qs.get("vf", ["2"])[0])
                    if vfield == 7:
                        inner = P.pb_varint_field(1, dpid) + b"\x3a\x01" + bytes([val])
                    else:
                        inner = P.pb_varint_field(1, dpid) + P.pb_varint_field(vfield, val)
                    outer = b"\x0a" + P.enc_varint(len(inner)) + inner
                    state.push_cmd(2633, outer)
                elif act == "raw":
                    c_num = int(qs.get("cmd", ["0"])[0])
                    fld = int(qs.get("f", ["2"])[0])
                    state.push_cmd(c_num, P.pb_varint_field(fld, val))
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path.startswith("/status"):
                import json as _json

                with state.cond:
                    st = dict(state.status) if state.status else {}
                    age = (
                        time.time() - state.last_frame_ts
                        if state.last_frame_ts
                        else None
                    )
                    st["connected"] = state.connected
                    st["streaming"] = (
                        age is not None and age < 3
                    )
                    st["last_frame_age_s"] = (
                        round(age, 1) if age is not None else None
                    )

                body = _json.dumps(st, indent=2).encode()
                self.send_response(200)
                self.send_header(
                    "Content-Type", "application/json"
                )
                self.send_header(
                    "Content-Length", str(len(body))
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return

            if self.path.startswith("/snapshot"):
                jpg = self._wait_first()

                if not jpg:
                    self.send_error(503, "no frame yet")
                    return

                with state.cond:
                    age = (
                        time.time() - state.last_frame_ts
                        if state.last_frame_ts
                        else 1e9
                    )

                if age > max_age:
                    self.send_error(
                        503, f"snapshot stale ({age:.1f}s old)"
                    )
                    return

                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(jpg)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(jpg); state.tick_stat(len(jpg), True)
                return

            if self.path.startswith("/stream.mjpg"):
                if self._wait_first() is None:
                    self.send_error(503, "no frame yet")
                    return

                self.send_response(200)
                self.send_header(
                    "Content-Type",
                    "multipart/x-mixed-replace; boundary=frame",
                )
                self.send_header("Cache-Control", "no-store")
                self.end_headers()

                last = 0

                try:
                    while not state.stop:
                        jpg, last = state.wait_newer(last, 5.0)

                        if jpg is None:
                            continue

                        hdr = (
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            b"Content-Length: "
                            + str(len(jpg)).encode()
                            + b"\r\n\r\n"
                        )

                        self.wfile.write(hdr)
                        self.wfile.write(jpg); state.tick_stat(len(jpg), True)
                        self.wfile.write(b"\r\n")
                        self.wfile.flush()

                except (
                    BrokenPipeError,
                    ConnectionResetError,
                    OSError,
                ):
                    return

                return

            self.send_error(404)

    return H

def resolve_creds(a):
    return D.resolve_credentials(
        None if a.ip in (None, "auto") else a.ip,
        a.did,
        a.secret,
        a.config,
        a.no_config,
        a.disc_wait,
    )

def _kill_previous_instances():
    pass

def main():
    global NVR
    import signal as _sig
    _sig.signal(_sig.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    threading.Thread(target=_patrol_loop, daemon=True).start()

    _kill_previous_instances()
    ap = argparse.ArgumentParser(
        description="live MJPEG/snapshot server for an A9 camera"
    )
    ap.add_argument("ip", nargs="?", help="camera IP")
    ap.add_argument("--did")
    ap.add_argument("--secret")
    ap.add_argument("--config", default="a9_camera.json")
    ap.add_argument("--no-config", action="store_true")
    ap.add_argument("--disc-wait", type=float, default=3.0)
    ap.add_argument(
        "--bind",
        default=os.environ.get("HTTP_BIND", "0.0.0.0"),
        help="HTTP bind address",
    )
    ap.add_argument("--http-port", type=int, default=int(os.environ.get("HTTP_PORT", "8080")))
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--max-age", type=float, default=10.0)
    ap.add_argument("--start-seq", type=int, default=3)

    a = ap.parse_args()

    if not a.ip:
        env_ip = os.environ.get("CAMERA_IP", "").strip()
        if env_ip:
            a.ip = env_ip
        else:
            try:
                entered = input("Введите IP камеры (или Enter для автопоиска): ").strip()
                if entered:
                    a.ip = entered
            except EOFError:
                pass

    ip, did, secret = resolve_creds(a)

    if not (ip and did and secret):
        sys.exit(
            "could not resolve camera IP + credentials "
            "(try --did/--secret, a9_camera.json, or discovery)"
        )

    sys.stderr.write(
        f"[*] camera {did.decode()} @ {ip}  (secret hidden)\n"
    )

    state = Latest()

    th = threading.Thread(
        target=camera_loop,
        args=(ip, did, secret, state, a.timeout, a.start_seq),
        daemon=True,
    )
    th.start()

    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer(
        (a.bind, a.http_port),
        make_handler(state, a.timeout + 4, a.max_age),
    )

    def _get_lan_ip():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip_addr = s.getsockname()[0]
            s.close()
            return ip_addr
        except Exception:
            return None

    local_url = f"http://127.0.0.1:{a.http_port}"
    sys.stderr.write(
        f"[*] Локальный доступ (этот телефон):\n"
        f"    Браузер (видео+звук): {local_url}/\n"
        f"    VLC / MX (MPEG-TS):    {local_url}/live.ts\n"
        f"    VLC / MX (MJPEG):      {local_url}/stream.mjpg\n"
        f"    Снимок (JPEG):         {local_url}/snapshot.jpg\n"
        f"    Статус (JSON):         {local_url}/status\n"
    )

    if a.bind == "0.0.0.0":
        lan_ip = _get_lan_ip()
        if lan_ip and lan_ip != "127.0.0.1":
            lan_url = f"http://{lan_ip}:{a.http_port}"
            sys.stderr.write(
                f"[*] Доступ по Wi-Fi (с других устройств):\n"
                f"    Браузер:  {lan_url}/\n"
                f"    VLC / MX: {lan_url}/live.ts\n"
            )

    if a.bind == "0.0.0.0":
        sys.stderr.write(
            "[!] bound to 0.0.0.0: the feed is UNAUTHENTICATED "
            "and reachable on the LAN.\n"
        )

    try:
        try:
            import nvr as _nvr
            NVR = _nvr.NVRRecorder()
        except Exception as _ne:
            print(f'[NVR] Disabled: {_ne}', flush=True)
        httpd.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write("\n[shutdown] Ctrl+C received\n")
    finally:
        # 1. Stops server and camera session.
        with state.cond:
            state.stop = True
            state.camera_wanted = False
            state.cond.notify_all()

        # 3. Stops TCP socket
        with state.socket_lock:
            s = state.camera_socket
            if s is not None:
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    s.close()
                except OSError:
                    pass

        # 4. Closes HTTP server and waits for camera thread
        httpd.server_close()
        th.join(timeout=5.0)

        if th.is_alive():
            sys.stderr.write(
                "[shutdown] WARNING: camera thread  "
                "didn't stop in 5 seconds\n"
            )
        else:
            sys.stderr.write(
                "[shutdown] connection and camera thread stopped\n"
            )

if __name__ == "__main__":
    main()
