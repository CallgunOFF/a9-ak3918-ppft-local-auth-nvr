# -*- coding: utf-8 -*-
import io, time
try:
    import av
except ImportError:
    av = None
try:
    import numpy as np
except ImportError:
    np = None

def wait_first(handler, state, first_timeout):
    with state.cond:
        state.cond.wait_for(
            lambda: state.jpeg is not None or state.stop,
            timeout=first_timeout,
        )
        return state.jpeg

def jpeg0(self):
    with state.cond:
        return state.jpeg

def stream_ts(handler, state, first_timeout):

    output = av.open(
        handler.wfile,
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

