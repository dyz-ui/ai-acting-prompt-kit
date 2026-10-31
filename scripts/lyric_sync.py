"""按真实音频时间轴渲染：每句歌词的时长跟歌声对齐。

复用 lyric_layers 的七个场景与图层机制，只是把"每句等长"换成"每句按 ASR 时间码"。

    python scripts/lyric_sync.py <文本> <音频> <输出.mp4> --start 24.60 --times times.json
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from lyric_cinema import Particles, fog_layer, sub_layer
from lyric_layers import (BIG_H, BIG_W, H, PAD, SCENES, W)


def render(text_path: Path, audio: Path, out: Path, times,
           fps: int = 24, fade: float = 0.4) -> Path:
    lines = [ln.strip() for ln in text_path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    if len(times) != len(lines):
        raise SystemExit(f"时间码 {len(times)} 个，歌词 {len(lines)} 句，对不上")

    t_start = times[0][0]
    t_end = times[-1][1]
    total = t_end - t_start

    # 每句：(场景索引, 视频起点, 视频终点, 字幕显示区间)
    slots = []
    for i, item in enumerate(times):
        a, b = item[0], item[1]
        sub_end = item[2] if len(item) > 2 else b
        slots.append((i, a - t_start, b - t_start, sub_end - t_start))

    scenes = [SCENES[i % len(SCENES)]() for i in range(len(lines))]
    subs = [sub_layer(ln) for ln in lines]

    frames = int(total * fps)
    tmp_v = out.with_suffix(".video.mp4")
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", str(tmp_v)], stdin=subprocess.PIPE)

    scrim = Image.new("RGBA", (W, 240), (0, 0, 0, 0))
    sa = (110 * (np.arange(240) / 239) ** 1.6).astype(np.uint8)
    arr_s = np.zeros((240, W, 4), dtype=np.uint8)
    arr_s[:, :, 3] = np.repeat(sa[:, None], W, axis=1)
    scrim = Image.fromarray(arr_s, "RGBA")

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vig = np.clip(1.06 - 0.30 * r ** 2, 0.62, 1.0)[:, :, None]
    rng = np.random.default_rng(5)
    grain = rng.normal(0, 3.0, (H, W, 1)).astype(np.float32)
    u8 = np.empty((H, W, 3), dtype=np.uint8)

    cur = -1
    baked = None
    baked_n = 0
    fog_cache = {}

    t0 = time.perf_counter()
    for i in range(frames):
        t = i / fps
        # 定位当前句
        idx = len(slots) - 1
        for k, (_, a, b, _s) in enumerate(slots):
            if a <= t < b:
                idx = k
                break
        _, s_start, s_end, s_sub = slots[idx]
        lt = t - s_start
        dur = s_end - s_start

        if idx != cur:
            cur = idx
            layers, pfn, fadec = scenes[idx]
            imgs = [ly for ly, _ in layers]
            delays = [d for _, d in layers]
            scaled = 1.0 if dur >= 3.0 else max(0.45, dur / 3.0)
            delays = [d * scaled for d in delays]
            baked = Image.new("RGBA", (BIG_W, BIG_H), (0, 0, 0, 255))
            baked_n = 0
            if idx not in fog_cache:
                fog_cache[idx] = fog_layer(W, H, 13)
            ctxt = {"imgs": imgs, "delays": delays, "pfn": pfn,
                    "fog": fog_cache[idx], "sub": subs[idx]}

        while baked_n < len(ctxt["imgs"]) and lt >= ctxt["delays"][baked_n] + 0.75:
            baked.alpha_composite(ctxt["imgs"][baked_n], (PAD, PAD))
            baked_n += 1

        canvas = baked.copy()
        for k in range(baked_n, len(ctxt["imgs"])):
            p = (lt - ctxt["delays"][k]) / 0.75
            if p <= 0:
                continue
            a = min(1.0, p) ** 1.4
            ly = ctxt["imgs"][k]
            if a < 0.995:
                ly = ly.copy()
                ly.putalpha(ly.getchannel("A").point(lambda v: int(v * a)))
            canvas.alpha_composite(ly, (PAD, PAD + int((1 - min(1.0, p)) * 26)))

        p2 = lt / max(0.1, dur)
        z = 1.0 - 0.055 * p2
        cw, ch = W * z, H * z
        cx = PAD + (W - cw) / 2 + 22 * math.sin(p2 * 1.5)
        cy = PAD + (H - ch) / 2 - 10 * p2
        frame = canvas.crop((int(cx), int(cy), int(cx + cw), int(cy + ch))).resize((W, H), Image.BILINEAR)

        fog = ctxt["fog"]
        fx = int(-W * 0.25 + 60 * math.sin(t * 0.12))
        frame.paste(fog, (fx, int(H * 0.48)), fog)
        ctxt["pfn"](t).draw(frame, t)

        last_delay = max(ctxt["delays"])
        show_from = last_delay + 0.35
        show_to = min(dur - 0.30, s_sub - 0.30)
        if show_to > show_from and show_from < lt < show_to:
            al = min(1.0, (lt - show_from) / fade) * min(1.0, (show_to - lt) / fade)
            frame.paste(scrim, (0, H - 240), scrim)
            s = ctxt["sub"].copy()
            if al < 0.99:
                s.putalpha(s.getchannel("A").point(lambda v: int(v * al)))
            frame.paste(s, ((W - s.width) // 2, H - 148), s)

        arr = np.asarray(frame.convert("RGB"), dtype=np.float32)
        arr *= vig
        arr = 255.0 * np.power(np.clip(arr / 255.0, 0, 1), 0.92)
        arr += grain

        edge = min(lt, dur - lt)
        if edge < 0.16:
            arr *= 0.45 + 0.55 * (edge / 0.16)

        np.clip(arr, 0, 255, out=arr)
        np.copyto(u8, arr, casting="unsafe")
        proc.stdin.write(u8.tobytes())

    proc.stdin.close()
    proc.wait()

    # 裁音频并对齐
    cut = out.with_suffix(".cut.m4a")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t_start:.3f}", "-t", f"{total:.3f}",
                    "-i", str(audio), "-c:a", "aac", "-b:a", "192k", str(cut)], check=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp_v), "-i", str(cut),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True)
    tmp_v.unlink(missing_ok=True)
    cut.unlink(missing_ok=True)

    dt = time.perf_counter() - t0
    print(f"句数    : {len(lines)}")
    print(f"时长    : {total:.2f}s ({frames} 帧)")
    print(f"耗时    : {dt:.1f}s  {frames / dt:.1f} fps")
    print(f"输出    : {out}  {out.stat().st_size / 1024 / 1024:.1f} MB")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("audio")
    ap.add_argument("out")
    ap.add_argument("--times", required=True, help="JSON：[[start,end],...]")
    ap.add_argument("--fps", type=int, default=24)
    a = ap.parse_args()
    times = json.loads(Path(a.times).read_text(encoding="utf-8"))
    render(Path(a.text), Path(a.audio), Path(a.out), times, a.fps)


if __name__ == "__main__":
    main()
