import threading
# -*- coding: utf-8 -*-
import os, sys, time, socket, struct, traceback
import a9_proto as P
import ptz_control as _ptz_mod

NVR = None

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
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 262144)

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
                        if os.environ.get("A9_DEBUG") == "1": print(f"[LANAUTH-ALL] {_fields_dbg}", flush=True)

    if not session_key:
        raise RuntimeError(
            "LanAuth gave no session key (wrong credentials?)"
        )

    def answer(cmd, rseq, rpc, ct):
        if cmd in (2601, 2603) and ct:
            try:
                w_pt = P.ctrl_decrypt(cmd, rseq, rpc, ct)
                if not w_pt and len(ct) > 4:
                    w_pt = P.ctrl_decrypt(cmd, rseq, 0, ct)
                if w_pt:
                    # Пробуем разобрать protobuf (со смещением 0 и со смещением после кода ответа)
                    parsed_list = []
                    for off in range(0, min(6, len(w_pt))):
                        try:
                            parsed_list.append(P.pb_parse(w_pt[off:]))
                        except Exception:
                            pass
                    if cmd == 2603:
                        for wf in parsed_list:
                            for fn in (2, 1, 3):
                                v = next(iter(wf.get(fn, ())), None)
                                if isinstance(v, bytes):
                                    stxt = v.decode("utf-8", "replace").strip(chr(0)).strip()
                                    if stxt and all(32 <= ord(ch) < 127 or ord(ch) > 160 for ch in stxt):
                                        state.wifi_cur = stxt
                                        break
                            if getattr(state, "wifi_cur", ""):
                                break
                    elif cmd == 2601:
                        aps = []
                        wf_main = P.pb_parse(w_pt)
                        for raw_ap in wf_main.get(2, ()):
                            if not isinstance(raw_ap, bytes):
                                continue
                            try:
                                ap_f = P.pb_parse(raw_ap)
                            except Exception:
                                continue
                            ssid_b = next(iter(ap_f.get(1, ())), None)
                            if not isinstance(ssid_b, bytes):
                                ssid_b = next(iter(ap_f.get(2, ())), None)
                            if not isinstance(ssid_b, bytes):
                                continue
                            s_txt = ssid_b.decode("utf-8", "replace").strip(chr(0)).strip()
                            if not s_txt or "\ufffd" in s_txt or len(s_txt) > 32:
                                continue
                            if not all(32 <= ord(ch) < 127 or 1040 <= ord(ch) <= 1103 for ch in s_txt):
                                continue
                            sig_raw = next(iter(ap_f.get(3, ())), 0) or next(iter(ap_f.get(4, ())), 0)
                            sig_val = 0
                            if isinstance(sig_raw, int) and sig_raw != 0:
                                if sig_raw > 1000000:
                                    sig_raw = sig_raw - (1 << 64)
                                sig_val = max(0, min(100, 2 * (sig_raw + 100))) if sig_raw < 0 else min(100, sig_raw)
                            if not any(x.get("ssid") == s_txt for x in aps):
                                aps.append({"ssid": s_txt, "sig": sig_val})
                        state.wifi_aps = aps
            except Exception:
                pass
        if rpc != 0:
            return

        if cmd == P.CMD_PING:
            pt = P.ctrl_decrypt(cmd, rseq, rpc, ct)
            echo = P.pb_parse(pt).get(1, [0])[0] if pt else 0

            pong = (
                P.pb_varint_field(1, echo)
                + P.pb_varint_field(2, P.HB_CONST)
                + P.pb_varint_field(3, int((time.time() + getattr(time.localtime(), 'tm_gmtoff', 0)) * 1000))
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
                        if os.environ.get("A9_DEBUG") == "1": print(f"[AUDIO-OK] subtype={subtype} len={len(data)} avch={avch} head={data[:8].hex()}", flush=True)
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
    _dq_hd = int(os.environ.get("CAM_QOS", "0") or 0)
    for cmd, pt in [
        (2653, b""),
        (2617, b""),
        (2657, P.pb_varint_field(1, 0) + P.pb_varint_field(2, 0)),
        (2645, b""),
        (P.CMD_VIDEOPLAY, b""),
        (P.CMD_VIDEOPLAY, P.pb_varint_field(1, 0) + P.pb_varint_field(2, 30)),
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
        if os.environ.get("A9_DEBUG") == "1": print(f"[LANAUTH] type={type(session_key).__name__} repr={session_key[:80]!r}", flush=True)
    except Exception as _e:
        if os.environ.get("A9_DEBUG") == "1": print(f"[LANAUTH-ERR] {_e!r}", flush=True)
    # --- /LAN-AUTH dump ---
    sys.stderr.write("[camera] authenticated; streaming\n")
    state.push_cmd(2603, b"")
    state.push_cmd(2601, b"")
    def _delayed_restore():
        time.sleep(1.5)
        if state.stop or not state.connected:
            return
        try:
            _ir = int(os.environ.get("CAM_IR", "0") or 0)
            if _ir in (1, 2):
                state.push_cmd(P.CMD_NIGHT, P.pb_varint_field(1, 0) + P.pb_varint_field(2, _ir))
                time.sleep(0.25)
            _fl = int(os.environ.get("CAM_FLIP", "0") or 0)
            if _fl:
                state.push_cmd(2646, P.pb_varint_field(1, 0) + P.pb_varint_field(2, 4))
                time.sleep(0.25)
                state.push_cmd(2656, P.pb_varint_field(1, 0) + P.pb_varint_field(2, 4))
                time.sleep(0.25)
            _mot = int(os.environ.get("CAM_MOTION", "0") or 0)
            if _mot in (1, 2, 3):
                state.push_cmd(2637, P.pb_varint_field(1, 0) + P.pb_varint_field(2, _mot))
                time.sleep(0.25)
            _hz = int(os.environ.get("CAM_FREQ", "50") or 50)
            if _hz == 60:
                state.push_cmd(2639, P.pb_varint_field(1, 0) + P.pb_varint_field(2, 60))
        except Exception:
            pass
    threading.Thread(target=_delayed_restore, daemon=True).start()

    # Keepalive and delayed audio activation.
    STALL = 12.0
    last_ping = 0.0

     #Send RPC 2614 once, can add varible delay after entering the main loop.
    audio_at = time.time() + 0.8
    audio_sent = False

    while not state.stop:
        with state.cond:
            if state.client_count == 0 and state.camera_wanted:
                state.camera_wanted = True
        now = time.time()

        for _cmd, _pl in state.pop_cmds():
            try:
                s.sendall(P.build_ctrl(seq, _cmd, _pl))
                if os.environ.get("A9_DEBUG") == "1": print(f"[CTRL-TX] cmd={_cmd} seq={seq} payload={_pl.hex()}", flush=True)
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


