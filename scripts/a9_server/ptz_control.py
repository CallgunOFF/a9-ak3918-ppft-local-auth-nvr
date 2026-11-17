# -*- coding: utf-8 -*-
from dataclasses import dataclass, field
import os, sys, time, threading
import a9_proto as P
import config as _cfg

PTZ_MAX_X_SEC, PTZ_MAX_Y_SEC, PTZ_MAX_STEP_DT = 15.0, 8.0, 5.0
PTZ_DEADZONE_SEC, PTZ_BACKLASH_SEC = 0.15, 0.15
PTZ_KICK_INTERVAL, PTZ_POLL_STEP_SEC, PTZ_AXIS_PAUSE_SEC = 0.25, 0.02, 0.15
PTZ_CAL_X_SEC, PTZ_CAL_Y_SEC, PTZ_PATROL_TICK_SEC = 4.2, 2.8, 0.3
CMD_PTZ, PTZ_STOP, PTZ_UP, PTZ_DOWN, PTZ_LEFT, PTZ_RIGHT = 2664, 10, 11, 12, 13, 14

def _get_st(): return _cfg._STATE_REF

def _parse_pair(raw, default=None):
    if not raw or "," not in raw: return default
    try:
        px, py = raw.split(",", 1)
        return (round(float(px.strip()), 2), round(float(py.strip()), 2))
    except (ValueError, TypeError): return default

def _parse_int(raw, default):
    try: return int(str(raw).strip())
    except (ValueError, TypeError): return default

@dataclass
class PTZState:
    x: float = 0.0
    y: float = 0.0
    dir: int = PTZ_STOP
    t: float = field(default_factory=time.time)
    pts: dict = field(default_factory=dict)
    home: tuple | None = None

_PTZ_LOCK = threading.Lock()
_PTZ_MOVE_LOCK = threading.Lock()
_PATROL_STARTED = False
_CALIBRATING = False

_ix, _iy = _parse_pair(os.environ.get("CUR_POS", "0.0,0.0"), (0.0, 0.0))
_PTZ_POS = PTZState(x=_ix, y=_iy, home=_parse_pair(os.environ.get("PSP_HOME", ""), None))
for _i in range(1, 7):
    _p = _parse_pair(os.environ.get(f"PSP_{_i}", ""), None)
    if _p is not None: _PTZ_POS.pts[str(_i)] = _p

_PATROL = {
    "on": os.environ.get("PATROL_ON", "0").strip() == "1",
    "sec": max(5, _parse_int(os.environ.get("PATROL_SEC", "15") or "15", 15)),
    "pts": [x.strip() for x in os.environ.get("PATROL_PTS", "1,2,3,4,5,6").split(",") if x.strip() in ("1","2","3","4","5","6")],
}

def _is_patrol_on():
    with _PTZ_LOCK: return bool(_PATROL["on"])

def _apply_delta_unlocked(d, dt, max_dt=None):
    if dt <= 0.0 or (max_dt is not None and dt > max_dt): return
    if d == PTZ_LEFT: _PTZ_POS.x = max(0.0, round(_PTZ_POS.x - dt, 2))
    elif d == PTZ_RIGHT: _PTZ_POS.x = min(PTZ_MAX_X_SEC, round(_PTZ_POS.x + dt, 2))
    elif d == PTZ_UP: _PTZ_POS.y = max(0.0, round(_PTZ_POS.y - dt, 2))
    elif d == PTZ_DOWN: _PTZ_POS.y = min(PTZ_MAX_Y_SEC, round(_PTZ_POS.y + dt, 2))

def _ptz_track(code):
    if code == PTZ_STOP:
        st = _get_st()
        if st is not None:
            try: st.push_cmd(CMD_PTZ, P.pb_varint_field(2, PTZ_STOP))
            except Exception: pass
    if not _PTZ_MOVE_LOCK.acquire(blocking=False): return False
    try:
        now, save_pos = time.time(), None
        with _PTZ_LOCK:
            dt = max(0.0, now - _PTZ_POS.t)
            if _PTZ_POS.dir != PTZ_STOP: _apply_delta_unlocked(_PTZ_POS.dir, dt, PTZ_MAX_STEP_DT)
            _PTZ_POS.dir, _PTZ_POS.t = code, now
            if code == PTZ_STOP: save_pos = f"{_PTZ_POS.x},{_PTZ_POS.y}"
        if save_pos is not None: _cfg._save_env_kv({"CUR_POS": save_pos})
        return True
    finally: _PTZ_MOVE_LOCK.release()

def _drive_continuous(st, code, duration_sec, check_patrol=False):
    if st is None: return 0.0
    if duration_sec <= PTZ_DEADZONE_SEC:
        with _PTZ_LOCK:
            was = (_PTZ_POS.dir != PTZ_STOP)
            _PTZ_POS.dir, _PTZ_POS.t = PTZ_STOP, time.time()
        if was:
            try: st.push_cmd(CMD_PTZ, P.pb_varint_field(2, PTZ_STOP))
            except Exception: pass
        return 0.0
    t_start = time.monotonic()
    t_end, last_kick = t_start + duration_sec, 0.0
    try:
        while time.monotonic() < t_end:
            if check_patrol and not _is_patrol_on(): break
            now_m = time.monotonic()
            if now_m - last_kick >= PTZ_KICK_INTERVAL:
                st.push_cmd(CMD_PTZ, P.pb_varint_field(2, code))
                last_kick = now_m
            time.sleep(PTZ_POLL_STEP_SEC)
    finally:
        try: st.push_cmd(CMD_PTZ, P.pb_varint_field(2, PTZ_STOP))
        except Exception: pass
        actual_dt = round(max(0.0, time.monotonic() - t_start), 2)
        with _PTZ_LOCK:
            _apply_delta_unlocked(code, actual_dt)
            _PTZ_POS.dir, _PTZ_POS.t = PTZ_STOP, time.time()
    return actual_dt

def _ptz_calibrate(st=None):
    global _CALIBRATING
    if st is None: st = _get_st()
    if st is None: return False
    with _PTZ_LOCK:
        _PATROL["on"] = False
    _cfg._save_env_kv({"PATROL_ON": "0"})
    with _PTZ_LOCK:
        if _CALIBRATING: return False
        _CALIBRATING = True
    try:
        if not _PTZ_MOVE_LOCK.acquire(timeout=30): return False
        try:
            _drive_continuous(st, PTZ_LEFT, PTZ_CAL_X_SEC, False)
            time.sleep(PTZ_AXIS_PAUSE_SEC)
            _drive_continuous(st, PTZ_UP, PTZ_CAL_Y_SEC, False)
            time.sleep(PTZ_AXIS_PAUSE_SEC)
            with _PTZ_LOCK: _PTZ_POS.x, _PTZ_POS.y, _PTZ_POS.t = 0.0, 0.0, time.time()
        except Exception: return False
        finally: _PTZ_MOVE_LOCK.release()
        _cfg._save_env_kv({"CUR_POS": "0.0,0.0"})
        return True
    finally:
        with _PTZ_LOCK: _CALIBRATING = False

def _ptz_save_slot(slot_key):
    now, key, st = time.time(), str(slot_key), _get_st()
    if st is not None:
        try: st.push_cmd(CMD_PTZ, P.pb_varint_field(2, PTZ_STOP))
        except Exception: pass
    with _PTZ_LOCK:
        dt = max(0.0, now - _PTZ_POS.t)
        if _PTZ_POS.dir != PTZ_STOP: _apply_delta_unlocked(_PTZ_POS.dir, dt, PTZ_MAX_STEP_DT)
        _PTZ_POS.dir, _PTZ_POS.t = PTZ_STOP, now
        x, y = round(_PTZ_POS.x, 2), round(_PTZ_POS.y, 2)
        if key != "home" and any(v == (x, y) for v in _PTZ_POS.pts.values()):
            sys.stderr.write(f"[PTZ-WARN] Точка T{key} ({x},{y}) совпадает с уже записанной\n")
        if key == "home": _PTZ_POS.home = (x, y)
        else: _PTZ_POS.pts[key] = (x, y)
    _cfg._save_env_kv({"PSP_HOME" if key == "home" else f"PSP_{key}": f"{x},{y}", "CUR_POS": f"{x},{y}"})
    return x, y

def _ptz_goto(st, sid, is_patrol=False):
    if st is None: st = _get_st()
    if st is None or (is_patrol and not _is_patrol_on()): return False
    if not _PTZ_MOVE_LOCK.acquire(blocking=False): return False
    try:
        key, now = str(sid), time.time()
        with _PTZ_LOCK:
            dt = max(0.0, now - _PTZ_POS.t)
            if _PTZ_POS.dir != PTZ_STOP: _apply_delta_unlocked(_PTZ_POS.dir, dt, PTZ_MAX_STEP_DT)
            _PTZ_POS.dir, _PTZ_POS.t = PTZ_STOP, now
            target = _PTZ_POS.home if key == "home" else _PTZ_POS.pts.get(key)
            if target is None: return False
            tx, ty = target
            cx, cy = _PTZ_POS.x, _PTZ_POS.y
        dx, dy = round(tx - cx, 2), round(ty - cy, 2)
        if is_patrol and not _is_patrol_on(): return False
        if abs(dx) > PTZ_DEADZONE_SEC:
            _drive_continuous(st, PTZ_RIGHT if dx > 0 else PTZ_LEFT, max(abs(dx) + PTZ_BACKLASH_SEC, PTZ_DEADZONE_SEC), is_patrol)
        if is_patrol and not _is_patrol_on(): return False
        if abs(dx) > PTZ_DEADZONE_SEC and abs(dy) > PTZ_DEADZONE_SEC: time.sleep(PTZ_AXIS_PAUSE_SEC)
        if is_patrol and not _is_patrol_on(): return False
        if abs(dy) > PTZ_DEADZONE_SEC:
            _drive_continuous(st, PTZ_DOWN if dy > 0 else PTZ_UP, max(abs(dy) + PTZ_BACKLASH_SEC, PTZ_DEADZONE_SEC), is_patrol)
        if is_patrol and not _is_patrol_on(): return False
        with _PTZ_LOCK:
            cur_x, cur_y = _PTZ_POS.x, _PTZ_POS.y
            _PTZ_POS.dir, _PTZ_POS.t = PTZ_STOP, time.time()
    finally: _PTZ_MOVE_LOCK.release()
    _cfg._save_env_kv({"CUR_POS": f"{cur_x},{cur_y}"})
    return True

def _ptz_park_home(st=None):
    if st is None: st = _get_st()
    with _PTZ_LOCK:
        has_home = _PTZ_POS.home is not None
        if st is None or not has_home: return False
        _PATROL["on"] = False
    _cfg._save_env_kv({"PATROL_ON": "0"})
    _ptz_goto(st, "home", False)
    time.sleep(PTZ_AXIS_PAUSE_SEC)
    return True

def _patrol_loop():
    idx, _warned = 0, False
    while True:
        with _PTZ_LOCK:
            on, sec = bool(_PATROL["on"]), int(_PATROL["sec"])
            order = _PATROL["pts"] or ["1","2","3","4","5","6"]
            pts = [k for k in order if k in _PTZ_POS.pts]
            stuck = (not on and _PTZ_POS.dir != PTZ_STOP and (time.time() - _PTZ_POS.t) > 1.2)
            if stuck: _PTZ_POS.dir, _PTZ_POS.t = PTZ_STOP, time.time()
        if stuck:
            sw = _get_st()
            if sw is not None:
                try: sw.push_cmd(CMD_PTZ, P.pb_varint_field(2, PTZ_STOP))
                except Exception: pass
        if not on:
            idx = 0; time.sleep(0.4); continue
        st = _get_st()
        if not pts or st is None:
            if st is None and not _warned:
                sys.stderr.write("[PTZ-WARN] Патруль ждёт подключения...\n"); _warned = True
            time.sleep(0.8); continue
        _warned = False
        sid = pts[idx % len(pts)]; idx += 1
        if not _ptz_goto(st, sid, True):
            time.sleep(0.5); continue
        t_end = time.time() + sec
        while _is_patrol_on() and time.time() < t_end: time.sleep(PTZ_PATROL_TICK_SEC)

def start_patrol_thread():
    global _PATROL_STARTED
    with _PTZ_LOCK:
        if _PATROL_STARTED: return
        _PATROL_STARTED = True
    threading.Thread(target=_patrol_loop, daemon=True).start()
