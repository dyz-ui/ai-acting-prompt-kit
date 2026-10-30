"""纯代码文字影片：读一个歌词/文案文本，渲成电影质感的逐句浮现短片。

不依赖任何 AI 模型，纯 numpy + PIL + ffmpeg，本机 CPU 实时级。

用法：
    python scripts/lyric_film.py <文本文件> <输出mp4> [--title 标题] [--sub 副标题]
                                  [--size 1920x1080] [--fps 30] [--per 3.4]

文本格式：一行一句，空行跳过。以 # 开头的行为注释。
"""
from __future__ import annotations

import argparse
import math
import subprocess
import time
from pathlib import Path
from typing import List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_SERIF = "C:/Windows/Fonts/simkai.ttf"   # 楷体，文艺感
FONT_SANS = "C:/Windows/Fonts/msyh.ttc"      # 雅黑
FONT_SANS_BOLD = "C:/Windows/Fonts/msyhbd.ttc"  # 雅黑粗
FONT_SONG = "C:/Windows/Fonts/simsun.ttc"    # 宋体

WARM = np.array([255, 214, 170], dtype=np.float32)
TEXT_RGB = (246, 240, 230)


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    for p in (path, FONT_SANS, FONT_SONG):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _hex(c: str) -> np.ndarray:
    c = c.lstrip("#")
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def _draw_spaced(d: ImageDraw.ImageDraw, xy, text: str, font, fill, spacing: int) -> float:
    """带字距的绘制，返回总宽度。"""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=font, fill=fill)
        x += d.textlength(ch, font=font) + spacing
    return x - xy[0]


def _measure(d: ImageDraw.ImageDraw, text: str, font, spacing: int) -> float:
    return sum(d.textlength(ch, font=font) + spacing for ch in text) - spacing


def _text_layer(text: str, font, spacing: int, color=TEXT_RGB) -> Tuple[np.ndarray, np.ndarray]:
    """把一行字预渲染成 (rgb, alpha)，只渲染一次，之后每帧只做合成。"""
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    w = int(_measure(probe, text, font, spacing)) + 8
    h = int(font.size * 1.7) + 8
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    asc, desc = font.getmetrics()
    y = (h - (asc + desc)) / 2
    _draw_spaced(d, (4, y), text, font, color + (255,), spacing)
    arr = np.asarray(img, dtype=np.float32)
    return arr[:, :, :3], (arr[:, :, 3:4] / 255.0)


def _gradient_base(w: int, h: int) -> np.ndarray:
    top = _hex("#0A0A0C")
    bot = _hex("#191310")
    t = (np.linspace(0, 1, h, dtype=np.float32) ** 1.35)[:, None, None]
    base = top * (1 - t) + bot * t
    base = np.repeat(base, w, axis=1)

    # 左上角一团暖光
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.sqrt(((xx - w * 0.28) ** 2 + (yy - h * 0.18) ** 2)) / (w * 0.55)
    glow = np.clip(1 - r, 0, 1)[:, :, None] ** 2.4
    base = base + glow * np.array([42, 30, 20], dtype=np.float32)

    # 竖向晕影
    vx = np.abs(np.linspace(-1, 1, w, dtype=np.float32))[:, None]
    vy = np.abs(np.linspace(-1, 1, h, dtype=np.float32))[:, None]
    vig = np.clip(1.05 - 0.42 * (vx.T ** 2) - 0.30 * (vy ** 2), 0.45, 1.0)[:, :, None]
    base = base * vig

    # 细扫描线
    base[::3, :, :] *= 0.965
    return base.astype(np.float32)


def _grain_bank(w: int, h: int, n: int = 8, seed: int = 7) -> List[np.ndarray]:
    """灰度噪声，单通道，靠广播加到 RGB 上 —— 省 2/3 的内存带宽。"""
    rng = np.random.default_rng(seed)
    return [rng.normal(0, 3.4, (h, w, 1)).astype(np.float32) for _ in range(n)]


def _light_sweep(w: int, h: int, t: float) -> np.ndarray:
    """低分辨率算一团缓慢移动的光，放大后叠加 —— 比全分辨率算便宜 60 倍。"""
    sw, sh = 96, 54
    yy, xx = np.mgrid[0:sh, 0:sw]
    cx = sw * (0.5 + 0.30 * math.sin(t * 0.22))
    cy = sh * (0.55 + 0.18 * math.cos(t * 0.17))
    r = np.sqrt(((xx - cx) / sw) ** 2 + ((yy - cy) / sh) ** 2)
    g = np.clip(1 - r * 1.5, 0, 1) ** 2.2
    small = (g * 26.0).astype(np.uint8)
    img = Image.fromarray(small).resize((w, h), Image.BILINEAR)
    a = np.asarray(img, dtype=np.float32)[:, :, None] / 255.0
    return a * np.array([1.0, 0.72, 0.5], dtype=np.float32)


def _composite(frame: np.ndarray, rgb: np.ndarray, alpha: np.ndarray, x: int, y: int, a: float) -> None:
    h, w = alpha.shape[:2]
    H, W = frame.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sub = frame[y0:y1, x0:x1]
    sa = alpha[y0 - y:y1 - y, x0 - x:x1 - x] * a
    sr = rgb[y0 - y:y1 - y, x0 - x:x1 - x]
    sub *= (1.0 - sa)
    sub += sr * sa


def render(text_path: Path, out: Path, title: str = "", sub: str = "",
           size: str = "1920x1080", fps: int = 30, per: float = 3.4,
           font_size: int = 84) -> Path:
    w, h = (int(v) for v in size.lower().split("x"))
    lines = [ln.rstrip("\n").strip() for ln in text_path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    if not lines:
        raise SystemExit("文本里没有内容")

    f_lyric = _font(FONT_SERIF, font_size)
    f_title = _font(FONT_SANS_BOLD, int(font_size * 1.85))
    f_sub = _font(FONT_SERIF, int(font_size * 0.55))

    base = _gradient_base(w, h)
    grains = _grain_bank(w, h)

    # 预渲染所有文字层（长句自动缩字号，保证不超出画面 88%）
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    max_w = w * 0.88
    layers = []
    for ln in lines:
        fs = font_size
        while fs > 36:
            f_try = _font(FONT_SERIF, fs)
            if _measure(probe, ln, f_try, spacing=10) <= max_w:
                break
            fs -= 2
        rgb, a = _text_layer(ln, _font(FONT_SERIF, fs), spacing=10)
        layers.append((rgb, a, (w - a.shape[1]) // 2, int(h * 0.5 - a.shape[0] / 2)))

    title_layers = []
    if title:
        rgb, a = _text_layer(title, f_title, spacing=18, color=(250, 244, 232))
        title_layers.append((rgb, a, (w - a.shape[1]) // 2, int(h * 0.42 - a.shape[0] / 2)))
        if sub:
            rgb2, a2 = _text_layer(sub, f_sub, spacing=8, color=(176, 158, 138))
            sx = (w - a2.shape[1]) // 2
            sy = int(h * 0.42 + a.shape[0] * 0.92)
            title_layers.append((rgb2, a2, sx, sy))

    # 时间轴（相对时间：0 表示第一句开始）
    HEAD = 3.0 if title else 0.0
    segue = 0.68
    spans = []
    t_cursor = 0.0
    for _ in lines:
        spans.append((t_cursor, t_cursor + per))
        t_cursor += per - 0.05
    total = HEAD + t_cursor + 1.8
    frames = int(total * fps)

    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", str(22),
           "-x264-params", "aq-mode=3:deblock=1,1", "-pix_fmt", "yuv420p", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    buf = np.empty((h, w, 3), dtype=np.float32)
    u8 = np.empty((h, w, 3), dtype=np.uint8)

    t0 = time.perf_counter()
    for i in range(frames):
        t = i / fps

        # 复用缓冲区，避免每帧几十 MB 的反复分配
        np.add(base, grains[i % len(grains)], out=buf)
        np.add(buf, _light_sweep(w, h, t), out=buf)

        if title and t < HEAD:
            k = min(1.0, t / 0.9) * min(1.0, (HEAD - t) / 0.7)
            rise = int((1 - min(1.0, t / 0.9)) * 14)
            for rgb, a, x, y in title_layers:
                _composite(buf, rgb, a, x, y + rise, max(0.0, k))
            # 标题下的一条细线，慢慢拉开
            prog = min(1.0, max(0.0, (t - 0.5) / 0.8))
            if prog > 0:
                lw = int(w * 0.20 * prog)
                cy = int(h * 0.42 + 168)
                buf[cy:cy + 1, (w - lw) // 2:(w + lw) // 2] += 64 * k
        else:
            local = t - HEAD
            for idx, (s, e) in enumerate(spans):
                if s <= local < e:
                    p = (local - s) / (e - s)
                    a_in = min(1.0, (local - s) / segue)
                    a_out = min(1.0, (e - local) / segue)
                    a = max(0.0, min(a_in, a_out))
                    rgb, al, x, y = layers[idx]
                    rise = int((1 - a_in) * 10 - p * 6)
                    _composite(buf, rgb, al, x, y + rise, a)
                    break

        # 片尾整体压暗
        if t > total - 1.5:
            buf *= max(0.0, (total - t) / 1.5)

        np.clip(buf, 0, 255, out=buf)
        np.copyto(u8, buf, casting="unsafe")
        proc.stdin.write(u8.tobytes())

    proc.stdin.close()
    proc.wait()
    dt = time.perf_counter() - t0
    print(f"句数      : {len(lines)}")
    print(f"总时长    : {total:.1f} s  ({frames} 帧)")
    print(f"渲染耗时  : {dt:.1f} s   {frames / dt:.1f} fps   {frames / dt / fps:.2f}x 实时")
    print(f"输出      : {out}  {out.stat().st_size / 1024 / 1024:.1f} MB")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("out")
    ap.add_argument("--title", default="")
    ap.add_argument("--sub", default="")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--per", type=float, default=3.4, help="每句停留秒数")
    ap.add_argument("--font-size", type=int, default=92)
    a = ap.parse_args()
    render(Path(a.text), Path(a.out), a.title, a.sub, a.size, a.fps, a.per, a.font_size)


if __name__ == "__main__":
    main()
