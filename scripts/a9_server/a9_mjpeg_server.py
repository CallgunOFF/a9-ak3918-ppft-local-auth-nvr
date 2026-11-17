#!/usr/bin/env python3
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
    /stream?raw=1   multiplexed A9AV binary stream: b'A9AV' + struct.pack('>BQI', kind: 1=JPEG/2=PCM8k, ts_usec, len) + payload
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
import struct
import json
import signal
from urllib.parse import urlparse, parse_qs
import base64
import traceback
import socket
import time
import threading
import argparse
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import ThreadingMixIn
import a9_proto as P
import a9_discover as D
import nvr as _nvr
CMD_PSP_ADD, CMD_PSP_CALL, CMD_PSP_LIST, CMD_PSP_DEL = 2666, 2667, 2668, 2669
CMD_OSD_GET, CMD_OSD_SET = 2648, 2649
CMD_WIFI_GET, CMD_WIFI_SET = 2661, 2662
CMD_REBOOT = 2670




import config as _cfg
from config import Latest, _get_st, _save_env_kv
from ptz_control import _PTZ_POS, _PTZ_LOCK, _PTZ_MOVE_LOCK, _PATROL, _ptz_track, _ptz_goto, start_patrol_thread, _ptz_calibrate, _ptz_save_slot, _ptz_park_home
import ptz_control as _ptz_mod

import media_stream as _media_mod
import camera_conn as _cam_mod
from camera_conn import camera_loop, _run_session

# ---------- HTTP server ----------

from web_ui import VIEWER

def make_handler(state, first_timeout, max_age):
    class H(BaseHTTPRequestHandler):

        def log_message(self, *a):
            pass

        def _check_auth(self):
            _wu = os.environ.get("WEB_USER", "")
            _wp = os.environ.get("WEB_PASS", "")
            if _wu and _wp:
                _exp = "Basic " + base64.b64encode(f"{_wu}:{_wp}".encode()).decode()
                if self.headers.get("Authorization") != _exp:
                    print(f"[{time.strftime('%H:%M:%S')}] [HTTP-AUTH-FAIL] ip={self.client_address} path={self.path}", flush=True)
                    self.send_response(401)
                    self.send_header("WWW-Authenticate", 'Basic realm="Camera"')
                    self.end_headers()
                    return False
            return True

        def do_HEAD(self):
            if not self._check_auth():
                return
            self.send_response(200)
            if self.path.startswith("/live.ts"):
                self.send_header("Content-Type", "video/mp2t")
            else:
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()

        def _wait_first(self):
            return _media_mod.wait_first(self, state, first_timeout)

        def stream_ts(self):
            return _media_mod.stream_ts(self, state, first_timeout)

        def do_GET(self):
            if not self._check_auth():
                return
            _cip = self.headers.get("CF-Connecting-IP") or self.headers.get("X-Forwarded-For") or self.client_address
            if self.path in ("/", "/live.mp4", "/live.ts", "/stream.mjpg") or self.path.startswith("/?"):
                if os.environ.get("A9_DEBUG") == "1": print(f"[{time.strftime('%H:%M:%S')}] [HTTP-CONN] client={_cip} path={self.path}", flush=True)
            state.acquire_client()
            try:
                return self._do_GET_inner()
            except (BrokenPipeError, ConnectionResetError):
                return
            finally:
                if self.path in ("/", "/live.mp4", "/live.ts", "/stream.mjpg") or self.path.startswith("/?"):
                    if os.environ.get("A9_DEBUG") == "1": print(f"[{time.strftime('%H:%M:%S')}] [HTTP-DISC] client={_cip} path={self.path}", flush=True)
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
                    traceback.print_exc()
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
                    last_audio = state.audio_seq - len(state.audio_chunks)

                try:
                    while not state.stop:
                        jpg, last_video = state.wait_newer(
                            last_video, 0.02
                        )

                        if jpg is not None:
                            send_record(1, time.monotonic(), jpg)
                            state.tick_stat(len(jpg), True)

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
                _age = round(time.time() - (getattr(state, "last_frame_ts", 0.0) or getattr(state, "_stat_ts", time.time())), 1)
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
                qs = parse_qs(urlparse(self.path).query)
                act = qs.get("act", [""])[0]
                sid = int(qs.get("id", ["1"])[0])
                if act == "ptz_cal":
                    with _PTZ_LOCK: _PATROL["on"] = False
                    _save_env_kv({"PATROL_ON": "0"})
                    threading.Thread(target=_ptz_calibrate, args=(state,), daemon=True).start()
                elif act == "ptz_home_set":
                    hx, hy = _ptz_save_slot("home")
                    if os.environ.get("A9_DEBUG") == "1": print(f"[PTZ-PTS] Записана парковка: X={hx}с, Y={hy}с", flush=True)
                elif act == "ptz_park":
                    with _PTZ_LOCK: _PATROL["on"] = False
                    _save_env_kv({"PATROL_ON": "0"})
                    threading.Thread(target=_ptz_park_home, args=(state,), daemon=True).start()
                elif act == "psp_add":
                    px, py = _ptz_save_slot(str(sid))
                    if os.environ.get("A9_DEBUG") == "1": print(f"[PTZ-PTS] Записана точка T{sid}: X={px}с, Y={py}с", flush=True)
                elif act == "psp_call":
                    threading.Thread(target=_ptz_goto, args=(_get_st(), str(sid)), daemon=True).start()
                elif act == "patrol":
                    with _PTZ_LOCK:
                        _PATROL["on"] = qs.get("on", ["false"])[0] in ("true", "1")
                        if "sec" in qs: _PATROL["sec"] = max(5, int(qs["sec"][0]))
                    _save_env_kv({"PATROL_ON": "1" if _PATROL["on"] else "0", "PATROL_SEC": str(_PATROL["sec"])})
                    if os.environ.get("A9_DEBUG") == "1": print(f"[PTZ-PTS] Патруль={_PATROL['on']}, пауза={_PATROL['sec']}с, точки={list(_PTZ_POS.pts.keys())}", flush=True)
                elif act == "light":
                    md = int(qs.get("mode", ["0"])[0])
                    if md in (2, 3): state.push_cmd(2664, P.pb_varint_field(2, 34))
                    elif md == 1: state.push_cmd(2664, P.pb_varint_field(2, 35))
                    else: state.push_cmd(2664, P.pb_varint_field(2, 35)); state.push_cmd(getattr(P, "CMD_NIGHT", 2642), P.pb_varint_field(2, 0))
                elif act == "osd":
                    _oen = str(int(next(iter(qs.get("enable", ("0",)))))); os.environ["CAM_OSD"] = _oen; _save_env_kv({"CAM_OSD": _oen})
                    en = int(qs.get("enable", ["1"])[0])
                    state.push_cmd(2649, P.pb_varint_field(1, 0) + _pb_b(2, P.pb_varint_field(1, en) + _pb_b(2, b"A9") + P.pb_varint_field(5, en)))
                elif act == "wifi" and qs.get("ssid", [""])[0]:
                    state.push_cmd(2662, P.pb_varint_field(1, 0) + _pb_b(2, qs["ssid"][0].encode()) + _pb_b(3, qs.get("pwd", [""])[0].encode()) + _pb_b(4, b"RU"))
                elif act == "freq":
                    _fhz = str(int(next(iter(qs.get("hz", ("50",)))))); os.environ["CAM_FREQ"] = _fhz; _save_env_kv({"CAM_FREQ": _fhz})
                    hz = int(str(qs.get("hz", "50")).strip("[]'\""))
                    state.push_cmd(2639, P.pb_varint_field(1, 0) + P.pb_varint_field(2, hz))
                elif act == "reboot": state.push_cmd(2670, P.pb_varint_field(1, 0))
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(b'{"ok":true}')
                return
            if self.path.startswith("/nvr/"):
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
                import datetime
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

                body = json.dumps(st, indent=2).encode()
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

def _kill_previous_instances(port=8080):
    my_pid = os.getpid()
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == my_pid:
                continue
            try:
                cmd = open(f"/proc/{pid}/cmdline", "rb").read().decode("utf-8", "ignore")
                if "a9_mjpeg_server.py" in cmd:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.3)
            except Exception:
                pass
    except Exception:
        pass


def main():
    global NVR
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    start_patrol_thread()

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
        default=os.environ.get("HTTP_BIND", "127.0.0.1"),
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
    _cfg._STATE_REF = state

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
            NVR = _nvr.NVRRecorder()
            _cam_mod.NVR = NVR
            NVR.attach_state(state)
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
