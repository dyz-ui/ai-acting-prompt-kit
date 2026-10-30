"""对照实验：同样一帧画面，MoviePy 写法 vs 直接管道写法。

目的：量出 MoviePy 的逐帧开销，判断本机该用哪种写法。
"""
import math
import os
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, SECONDS = 1920, 1080, 30, 3
FONT = "C:/Windows/Fonts/msyh.ttc"
TITLE = "把情绪编译成可执行的表演"


def frame_rgb(i: int) -> np.ndarray:
    """返回 H×W×3 uint8，和 render_bench 用的是同一套画法。"""
    t = i / FPS
    img = Image.new("RGB", (W, H), (14, 16, 20))
    d = ImageDraw.Draw(img)
    for y in range(0, H, 6):
        v = int(18 + 16 * math.sin((y / H) * math.pi + t * 0.8))
        d.line([(0, y), (W, y)], fill=(v, v + 2, v + 6))
    cx, cy, r = W / 2, H / 2, 260 + 40 * math.sin(t * 1.6)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(60, 70, 90), width=2)
    f = ImageFont.truetype(FONT, 72)
    tw = d.textlength(TITLE, font=f)
    d.text((cx - tw / 2, cy - 36), TITLE, font=f, fill=(240, 242, 246))
    return np.asarray(img, dtype=np.uint8)


def bench_moviepy(total: int) -> float:
    from moviepy import VideoClip

    t0 = time.perf_counter()
    clip = VideoClip(lambda t: frame_rgb(int(round(t * FPS))), duration=total / FPS)
    clip.write_videofile("mp_out.mp4", fps=FPS, codec="libx264", audio=False,
                         preset="veryfast", logger=None)
    return time.perf_counter() - t0


def bench_pipe(total: int) -> float:
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
           "-pix_fmt", "yuv420p", "pipe_out.mp4"]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.perf_counter()
    for i in range(total):
        p.stdin.write(frame_rgb(i).tobytes())
    p.stdin.close()
    p.wait()
    return time.perf_counter() - t0


if __name__ == "__main__":
    total = FPS * SECONDS
    os.chdir(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(f"对比 {total} 帧  {W}x{H}@{FPS}  同一套画法\n")

    t_pipe = bench_pipe(total)
    print(f"直接管道  : {t_pipe:6.2f} s   {total / t_pipe:6.1f} fps   {total / t_pipe / FPS:.2f}x 实时")

    t_mp = bench_moviepy(total)
    print(f"MoviePy   : {t_mp:6.2f} s   {total / t_mp:6.1f} fps   {total / t_mp / FPS:.2f}x 实时")
    print(f"\nMoviePy 额外开销：{t_mp / t_pipe:.1f}x")
