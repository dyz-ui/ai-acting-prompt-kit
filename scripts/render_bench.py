"""代码生视频基准：逐帧绘制 -> 管道推给 ffmpeg -> 出 mp4。

测的是「本机用代码渲染画面」的真实速度，不涉及任何 AI 模型。
"""
import math
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H, FPS, SECONDS = 1920, 1080, 30, 10
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "code_render.mp4")
FONT = "C:/Windows/Fonts/msyh.ttc"

TITLE = "把情绪编译成可执行的表演"
SUB = "aiacting · 八维公式"


def main() -> None:
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
        "-pix_fmt", "yuv420p", str(OUT),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    f_title = ImageFont.truetype(FONT, 72)
    f_sub = ImageFont.truetype(FONT, 34)
    total = FPS * SECONDS
    t0 = time.perf_counter()

    for i in range(total):
        t = i / FPS
        img = Image.new("RGB", (W, H), (14, 16, 20))
        d = ImageDraw.Draw(img)

        for k in range(0, H, 4):
            v = int(18 + 16 * math.sin((k / H) * math.pi + t * 0.8))
            d.line([(0, k), (W, k)], fill=(v, v + 2, v + 6))

        cx, cy = W / 2, H / 2
        r = 260 + 40 * math.sin(t * 1.6)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(60, 70, 90), width=2)

        n, rad = 8, r * 0.78
        for j in range(n):
            a = t * 0.55 + j * (2 * math.pi / n)
            x, y = cx + rad * math.cos(a), cy + rad * math.sin(a)
            rr = 7 + 4 * math.sin(t * 2 + j)
            d.ellipse([x - rr, y - rr, x + rr, y + rr], fill=(210, 220, 235))

        tw = d.textlength(TITLE, font=f_title)
        d.text((cx - tw / 2, cy - 70), TITLE, font=f_title, fill=(240, 242, 246))
        sw = d.textlength(SUB, font=f_sub)
        d.text((cx - sw / 2, cy + 26), SUB, font=f_sub, fill=(140, 150, 168))

        bar = int((W - 240) * (i / total))
        d.rectangle([120, H - 96, 120 + bar, H - 92], fill=(90, 130, 200))

        proc.stdin.write(img.tobytes())

    proc.stdin.close()
    proc.wait()
    dt = time.perf_counter() - t0
    fps = total / dt
    print(f"帧数      : {total}")
    print(f"总耗时    : {dt:.2f} s")
    print(f"渲染速度  : {fps:.1f} fps  ({fps / FPS:.1f}x 实时)")
    print(f"推到 30 秒: 约 {900 / fps:.1f} s ({900 / fps / 60:.1f} 分钟)")
    print(f"输出      : {OUT}  {OUT.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
