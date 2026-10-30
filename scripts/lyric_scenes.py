"""二维平面风格 · 歌词意境片

每句歌词配一个纯几何构成的平面插画场景，静态部分用 2x 超采样后降采样保证边缘平滑，
动态元素预渲染成精灵逐帧粘贴。全部用 PIL 图元画，不依赖任何 AI 模型。

用法：
    python scripts/lyric_scenes.py <文本> <输出mp4> [--title 标题] [--sub 副标题]
    python scripts/lyric_scenes.py <文本> --stills out/stills      # 只出 7 张静帧检查
"""
from __future__ import annotations

import argparse
import math
import subprocess
import time
from pathlib import Path
from typing import Callable, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- 调色板
PAPER = (236, 226, 209)
CREAM = (247, 241, 229)
INK = (33, 31, 29)
RUST = (193, 84, 58)
TEAL = (56, 86, 102)
DUSK = (74, 68, 76)
GOLD = (214, 162, 66)
SAND = (206, 186, 154)

F_SERIF = "C:/Windows/Fonts/simkai.ttf"
F_SANS = "C:/Windows/Fonts/msyhbd.ttc"

SS = 2          # 超采样倍率
BAND_Y = 762    # 图注纸带起始行
W, H = 1920, 1080


# ---------------------------------------------------------------- 基础图元
def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    for p in (path, "C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simsun.ttc"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def rect(d, box, fill):
    d.rectangle(box, fill=fill)


def circ(d, cx, cy, r, fill):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)


def poly(d, pts, fill):
    d.polygon(pts, fill=fill)


def ring(d, cx, cy, r, width, fill):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fill, width=width)


def line(d, pts, fill, width):
    d.line(pts, fill=fill, width=width, joint="curve")


def rrect(d, box, radius, fill):
    d.rounded_rectangle(box, radius=radius, fill=fill)


def flower(d, cx, cy, r, petal_color, core_color):
    """五瓣花：五个圆绕心 + 一个花心。平面风格里这样最像花。"""
    for k in range(5):
        a = -math.pi / 2 + k * 2 * math.pi / 5
        circ(d, cx + math.cos(a) * r * 0.86, cy + math.sin(a) * r * 0.86, r * 0.60, petal_color)
    circ(d, cx, cy, r * 0.34, core_color)


def chair(d, x, y, w_, h_, facing, color):
    """侧视椅子。facing=1 朝右，-1 朝左。"""
    seat_h = h_ * 0.13
    rect(d, [x, y - seat_h / 2, x + w_, y + seat_h / 2], color)
    bx = x if facing > 0 else x + w_ - w_ * 0.16
    rect(d, [bx, y - h_, bx + w_ * 0.16, y + seat_h / 2], color)
    for lx in (x + w_ * 0.10, x + w_ * 0.86):
        rect(d, [lx - w_ * 0.035, y + seat_h / 2, lx + w_ * 0.035, y + h_ * 0.52], color)


def text_layer(text: str, f: ImageFont.FreeTypeFont, color, spacing: int = 6) -> Tuple[np.ndarray, np.ndarray]:
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    w = int(sum(probe.textlength(c, font=f) + spacing for c in text) - spacing) + 6
    asc, desc = f.getmetrics()
    h = asc + desc + 8
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = 3
    for c in text:
        d.text((x, 2), c, font=f, fill=color + (255,))
        x += d.textlength(c, font=f) + spacing
    a = np.asarray(img, dtype=np.float32)
    return a[:, :, :3], a[:, :, 3:4] / 255.0


def paste_text(frame: np.ndarray, rgb, alpha, x: int, y: int, a: float) -> None:
    if a <= 0.003:
        return
    h, w = alpha.shape[:2]
    H_, W_ = frame.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W_, x + w), min(H_, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sub = frame[y0:y1, x0:x1]
    sa = alpha[y0 - y:y1 - y, x0 - x:x1 - x] * a
    sub *= (1.0 - sa)
    sub += rgb[y0 - y:y1 - y, x0 - x:x1 - x] * sa


# ---------------------------------------------------------------- 场景构件
def build_bg(draw_fn: Callable, w: int, h: int) -> Image.Image:
    """在 2x 画布上画静态层，再降采样 —— 消除图元锯齿。"""
    img = Image.new("RGB", (w * SS, h * SS), PAPER)
    d = ImageDraw.Draw(img)
    draw_fn(d, w * SS, h * SS)
    return img.resize((w, h), Image.LANCZOS)


def build_sprite(draw_fn: Callable, w: int, h: int) -> Image.Image:
    img = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    draw_fn(d, w * SS, h * SS)
    return img.resize((w, h), Image.LANCZOS)


def draw_band(arr: np.ndarray, w: int, h: int) -> None:
    """底部压一条纸色带做图注区，顺带把插画裁成统一画框。"""
    arr[BAND_Y:, :, :] = np.array(PAPER, dtype=np.float32)
    arr[BAND_Y:BAND_Y + 3, :, :] = np.array(INK, dtype=np.float32)


def paper_grain(w: int, h: int) -> np.ndarray:
    rng = np.random.default_rng(11)
    g = rng.normal(0, 2.6, (h, w, 1)).astype(np.float32)
    return g


# ---------------------------------------------------------------- 七个场景
def scene_window(w, h):
    """1 · 那是我日夜思念深深爱着的人啊 —— 夜里一扇窗，窗外有月亮。"""
    def draw(d, W_, H_):
        rect(d, [0, 0, W_, H_ * 0.72], TEAL)
        rect(d, [0, H_ * 0.72, W_, H_], INK)
        circ(d, W_ * 0.74, H_ * 0.26, W_ * 0.085, CREAM)
        # 窗框
        fx0, fy0, fx1, fy1 = W_ * 0.10, H_ * 0.20, W_ * 0.44, H_ * 0.74
        rect(d, [fx0, fy0, fx1, fy1], CREAM)
        rect(d, [fx0, fy0, fx0 + W_ * 0.012, fy1], INK)
        rect(d, [fx1 - W_ * 0.012, fy0, fx1, fy1], INK)
        rect(d, [fx0, fy0, fx1, fy0 + H_ * 0.014], INK)
        rect(d, [fx0, fy1 - H_ * 0.014, fx1, fy1], INK)
        rect(d, [fx0 + (fx1 - fx0) * 0.5 - W_ * 0.005, fy0, fx0 + (fx1 - fx0) * 0.5 + W_ * 0.005, fy1], INK)
        # 窗里的人的剪影
        cx = fx0 + (fx1 - fx0) * 0.32
        circ(d, cx, H_ * 0.46, W_ * 0.032, INK)
        poly(d, [(cx - W_ * 0.055, fy1 - H_ * 0.02), (cx - W_ * 0.038, H_ * 0.53),
                 (cx + W_ * 0.038, H_ * 0.53), (cx + W_ * 0.058, fy1 - H_ * 0.02)], INK)
        # 地面线
        rect(d, [0, H_ * 0.72, W_, H_ * 0.725], CREAM)

    bg = build_bg(draw, w, h)

    cloud = build_sprite(lambda d, W_, H_: (
        circ(d, W_ * 0.14, H_ * 0.10, W_ * 0.05, CREAM),
        circ(d, W_ * 0.22, H_ * 0.11, W_ * 0.06, CREAM),
        circ(d, W_ * 0.30, H_ * 0.10, W_ * 0.045, CREAM),
    ), 460, 150)

    def anim(t):
        dx = -((t * 16) % (w + 500)) - 250
        return [(cloud, int(dx), int(h * 0.10)), (cloud, int(dx + w * 0.7), int(h * 0.28))]

    return bg, anim, INK, "left"


def scene_faces(w, h):
    """2 · 到底我该如何表达 她会接受我吗 —— 两把相对的椅子，中间空着。"""
    def draw(d, W_, H_):
        rect(d, [0, 0, W_, H_], CREAM)
        rect(d, [0, H_ * 0.022, W_, H_ * 0.026], SAND)
        circ(d, W_ * 0.50, H_ * 0.20, W_ * 0.085, SAND)
        rect(d, [0, H_ * 0.795, W_, H_ * 0.80], INK)
        chair(d, W_ * 0.13, H_ * 0.795, W_ * 0.20, H_ * 0.30, 1, INK)
        chair(d, W_ * 0.67, H_ * 0.795, W_ * 0.20, H_ * 0.30, -1, INK)

    bg = build_bg(draw, w, h)

    def dot(d, W_, H_):
        circ(d, W_ * 0.5, H_ * 0.5, W_ * 0.5, RUST)

    s_dot = build_sprite(dot, 80, 80)

    def anim(t):
        p = 1.0 + 0.08 * math.sin(t * 1.5)
        s = s_dot.resize((max(4, int(80 * p)), max(4, int(80 * p))), Image.LANCZOS)
        return [(s, int(w * 0.5 - s.width / 2), int(h * 0.50 - s.height / 2))]

    return bg, anim, INK, "left"


def scene_letter(w, h):
    """3 · 也许永远都不会跟她说出那句话 —— 一封没寄出的信。"""
    def draw(d, W_, H_):
        rect(d, [0, 0, W_, H_], PAPER)
        ex0, ey0, ex1, ey1 = W_ * 0.30, H_ * 0.30, W_ * 0.70, H_ * 0.62
        rect(d, [ex0, ey0, ex1, ey1], CREAM)
        rect(d, [ex0, ey0, ex1, ey0 + H_ * 0.008], INK)
        rect(d, [ex0, ey1 - H_ * 0.008, ex1, ey1], INK)
        rect(d, [ex0, ey0, ex0 + W_ * 0.006, ey1], INK)
        rect(d, [ex1 - W_ * 0.006, ey0, ex1, ey1], INK)
        poly(d, [(ex0, ey0), (W_ * 0.5, H_ * 0.47), (ex1, ey0)], CREAM)
        line(d, [(ex0, ey0), (W_ * 0.5, H_ * 0.47), (ex1, ey0)], INK, int(W_ * 0.004))
        circ(d, W_ * 0.5, H_ * 0.505, W_ * 0.021, RUST)
        # 一支笔
        poly(d, [(W_ * 0.74, H_ * 0.70), (W_ * 0.80, H_ * 0.66),
                 (W_ * 0.815, H_ * 0.678), (W_ * 0.755, H_ * 0.718)], INK)
        poly(d, [(W_ * 0.74, H_ * 0.70), (W_ * 0.722, H_ * 0.724), (W_ * 0.748, H_ * 0.716)], RUST)

    bg = build_bg(draw, w, h)

    petal = build_sprite(lambda d, W_, H_: poly(
        d, [(W_ * 0.5, 0), (W_ * 0.92, H_ * 0.55), (W_ * 0.5, H_), (W_ * 0.08, H_ * 0.55)], RUST), 26, 34)

    def anim(t):
        out = []
        for i in range(5):
            ph = i * 1.7
            x = w * 0.14 + (i * 137 + t * 26) % (w * 0.76)
            y = (h * 0.16 + t * (22 + i * 5) + ph * 40) % (h * 0.66)
            out.append((petal.rotate(18 * math.sin(t + ph)), int(x), int(y)))
        return out

    return bg, anim, INK, "left"


def scene_road(w, h):
    """4 · 注定我要浪迹天涯 怎么能有牵挂 —— 一条向远方收束的公路。"""
    def draw(d, W_, H_):
        rect(d, [0, 0, W_, H_ * 0.66], GOLD)
        rect(d, [0, H_ * 0.66, W_, H_], SAND)
        hy = H_ * 0.66
        poly(d, [(W_ * 0.44, hy), (W_ * 0.56, hy), (W_ * 0.86, H_), (W_ * 0.14, H_)], DUSK)
        # 电杆
        for i, x in enumerate([0.30, 0.38, 0.46]):
            ph = H_ * (0.10 + i * 0.06)
            line(d, [(W_ * x, hy), (W_ * x, hy - ph)], INK, int(W_ * 0.005))
            line(d, [(W_ * (x - 0.03), hy - ph * 0.86), (W_ * (x + 0.03), hy - ph * 0.86)], INK, int(W_ * 0.004))
        circ(d, W_ * 0.74, H_ * 0.30, W_ * 0.07, RUST)
        # 小人 + 箱子
        bx, by = W_ * 0.36, H_ * 0.80
        circ(d, bx, by - H_ * 0.075, W_ * 0.011, INK)
        rect(d, [bx - W_ * 0.013, by - H_ * 0.062, bx + W_ * 0.013, by - H_ * 0.005], INK)
        rect(d, [bx + W_ * 0.020, by - H_ * 0.036, bx + W_ * 0.056, by - H_ * 0.002], INK)

    bg = build_bg(draw, w, h)

    def dash(d, W_, H_):
        rect(d, [W_ * 0.47, 0, W_ * 0.53, H_], CREAM)

    s_dash = build_sprite(dash, 40, 150)

    def anim(t):
        out = []
        for i in range(6):
            p = ((t * 0.16) + i / 6) % 1.0
            e = p ** 2.1
            y = h * 0.665 + e * (h * 0.34)
            sc = 0.25 + e * 2.4
            s = s_dash.resize((max(2, int(40 * sc)), max(3, int(150 * sc))), Image.LANCZOS)
            out.append((s, int(w * 0.5 - s.width / 2), int(y)))
        return out

    return bg, anim, INK, "right"


def scene_mountain(w, h):
    """5 · 梦想总是遥不可及 是不是应该放弃 —— 山与阶梯。"""
    def draw(d, W_, H_):
        rect(d, [0, 0, W_, H_], PAPER)
        circ(d, W_ * 0.24, H_ * 0.30, W_ * 0.10, GOLD)
        poly(d, [(W_ * 0.08, H_ * 0.92), (W_ * 0.40, H_ * 0.40), (W_ * 0.72, H_ * 0.92)], SAND)
        poly(d, [(W_ * 0.46, H_ * 0.92), (W_ * 0.70, H_ * 0.56), (W_ * 0.94, H_ * 0.92)], TEAL)
        # 阶梯：六级，逐级升高
        for i in range(6):
            x = W_ * (0.06 + i * 0.055)
            y = H_ * (0.92 - i * 0.032)
            rect(d, [x, y, x + W_ * 0.060, y + H_ * 0.020], INK)
            rect(d, [x, y, x + W_ * 0.008, y + H_ * 0.062], INK)
        rect(d, [0, H_ * 0.92, W_, H_], INK)

    bg = build_bg(draw, w, h)

    star = build_sprite(lambda d, W_, H_: (
        poly(d, [(W_ * 0.5, 0), (W_ * 0.62, H_ * 0.5), (W_ * 0.5, H_), (W_ * 0.38, H_ * 0.5)], CREAM),
        poly(d, [(0, H_ * 0.5), (W_ * 0.5, H_ * 0.38), (W_, H_ * 0.5), (W_ * 0.5, H_ * 0.62)], CREAM),
    ), 58, 58)

    def anim(t):
        p = 0.75 + 0.25 * math.sin(t * 2.2)
        s = star.resize((int(58 * p), int(58 * p)), Image.LANCZOS)
        return [(s, int(w * 0.24 - s.width / 2), int(h * 0.30 - h * 0.10 - s.height * 0.62))]

    return bg, anim, INK, "left"


def scene_blossom(w, h):
    """6 · 花开花落又是一季 春天啊你在哪里 —— 一根枝，几朵花，花瓣在落。"""
    def draw(d, W_, H_):
        rect(d, [0, 0, W_, H_], CREAM)
        circ(d, W_ * 0.74, H_ * 0.26, W_ * 0.105, SAND)
        # 枝干：主枝 + 两根细枝
        line(d, [(0, H_ * 0.90), (W_ * 0.26, H_ * 0.70), (W_ * 0.50, H_ * 0.62)], INK, int(W_ * 0.0075))
        line(d, [(W_ * 0.26, H_ * 0.70), (W_ * 0.36, H_ * 0.50)], INK, int(W_ * 0.005))
        line(d, [(W_ * 0.50, H_ * 0.62), (W_ * 0.60, H_ * 0.44)], INK, int(W_ * 0.0045))
        flower(d, W_ * 0.36, H_ * 0.475, W_ * 0.052, RUST, CREAM)
        flower(d, W_ * 0.60, H_ * 0.415, W_ * 0.043, RUST, CREAM)
        flower(d, W_ * 0.19, H_ * 0.635, W_ * 0.036, RUST, CREAM)
        flower(d, W_ * 0.47, H_ * 0.585, W_ * 0.030, RUST, CREAM)
        rect(d, [0, H_ * 0.94, W_, H_], SAND)

    bg = build_bg(draw, w, h)

    petal = build_sprite(lambda d, W_, H_: (
        circ(d, W_ * 0.5, H_ * 0.42, W_ * 0.30, RUST),
        circ(d, W_ * 0.5, H_ * 0.42, W_ * 0.10, CREAM),
    ), 30, 30)

    def anim(t):
        out = []
        for i in range(9):
            ph = i * 0.9
            x = w * (0.18 + 0.62 * ((i * 0.173 + t * 0.012) % 1.0)) + 26 * math.sin(t * 0.9 + ph)
            y = (h * 0.30 + t * (30 + i * 4) + ph * 70) % (h * 0.72)
            s = petal.rotate(24 * math.sin(t * 0.8 + ph), resample=Image.BICUBIC)
            out.append((s, int(x), int(y)))
        return out

    return bg, anim, INK, "left"


def scene_river(w, h):
    """7 · 青春如同奔流的江河 一去不回来不及道别 —— 江面与远去的小船。"""
    def draw(d, W_, H_):
        rect(d, [0, 0, W_, H_ * 0.40], CREAM)
        poly(d, [(0, H_ * 0.40), (W_ * 0.42, H_ * 0.34), (W_ * 0.70, H_ * 0.42), (W_, H_ * 0.38)], DUSK)
        rect(d, [0, H_ * 0.40, W_, H_], TEAL)
        for i in range(14):
            y = H_ * (0.44 + (i // 2) * 0.062 + (i % 2) * 0.014)
            x0 = W_ * (0.03 + ((i * 0.37) % 0.62))
            ln = W_ * (0.06 + ((i * 0.19) % 0.16))
            line(d, [(x0, y), (x0 + ln, y)], CREAM, max(2, int(H_ * 0.0032)))
        circ(d, W_ * 0.80, H_ * 0.22, W_ * 0.055, GOLD)

    bg = build_bg(draw, w, h)

    boat = build_sprite(lambda d, W_, H_: (
        poly(d, [(0, H_ * 0.62), (W_, H_ * 0.62), (W_ * 0.74, H_), (W_ * 0.26, H_)], INK),
        poly(d, [(W_ * 0.46, H_ * 0.62), (W_ * 0.54, H_ * 0.62), (W_ * 0.50, 0)], INK),
    ), 260, 170)

    def anim(t):
        # 一条主船由近及远，另一条远处缓行
        p = (t * 0.028) % 1.0
        sc = 1.0 - p * 0.55
        s = boat.resize((max(12, int(230 * sc)), max(8, int(150 * sc))), Image.LANCZOS)
        main = (s, int(w * (0.22 + p * 0.34)), int(h * (0.62 + p * 0.22)))
        p2 = (t * 0.012 + 0.5) % 1.0
        q = 0.45 - p2 * 0.20
        s2 = boat.resize((max(8, int(230 * q)), max(5, int(150 * q))), Image.LANCZOS)
        second = (s2, int(w * (0.55 + p2 * 0.22)), int(h * (0.50 + p2 * 0.10)))
        return [second, main]

    return bg, anim, CREAM, "left"


SCENES = [scene_window, scene_faces, scene_letter, scene_road,
          scene_mountain, scene_blossom, scene_river]


# ---------------------------------------------------------------- 渲染
def render(text_path: Path, out: Path, title: str = "", sub: str = "",
           fps: int = 24, per: float = 4.2) -> Path:
    lines = [ln.strip() for ln in text_path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    if not lines:
        raise SystemExit("文本为空")

    built = []
    for i, ln in enumerate(lines):
        fn = SCENES[i % len(SCENES)]
        bg, anim, tcolor, align = fn(W, BAND_Y)
        _full = Image.new("RGB", (W, H), PAPER)
        _full.paste(bg, (0, 0))
        bg = _full
        f = font(F_SERIF, 74)
        # 长句自动缩字号
        while True:
            rgb, a = text_layer(ln, f, INK, spacing=6)
            if a.shape[1] <= W * 0.86 or f.size <= 34:
                break
            f = font(F_SERIF, f.size - 2)
        tx = 140
        ty = BAND_Y + 52
        built.append((bg, anim, (rgb, a, tx, ty)))

    grain = paper_grain(W, H)
    total = len(lines) * per + 2.0
    frames = int(total * fps)

    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "21",
         "-pix_fmt", "yuv420p", str(out)],
        stdin=subprocess.PIPE)

    buf = np.empty((H, W, 3), dtype=np.float32)
    u8 = np.empty((H, W, 3), dtype=np.uint8)

    t0 = time.perf_counter()
    for i in range(frames):
        t = i / fps
        idx = min(int(t // per), len(lines) - 1)
        local = t - idx * per
        bg, anim, (trgb, ta, tx, ty) = built[idx]
        _ = None

        np.copyto(buf, np.asarray(bg, dtype=np.float32))
        buf += grain
        img = Image.fromarray(np.clip(buf, 0, 255).astype(np.uint8))
        for sp, x, y in anim(t):
            img.paste(sp, (x, y), sp)
        buf = np.array(img, dtype=np.float32)
        draw_band(buf, W, H)

        # 文字：进入 0.5s / 退出 0.45s
        a_in = min(1.0, local / 0.5)
        a_out = min(1.0, (per - local) / 0.45)
        al = max(0.0, min(a_in, a_out))
        paste_text(buf, trgb, ta, tx, ty + int((1 - a_in) * 12), al)

        if t > total - 1.2:
            buf *= max(0.0, (total - t) / 1.2)

        np.clip(buf, 0, 255, out=buf)
        np.copyto(u8, buf, casting="unsafe")
        proc.stdin.write(u8.tobytes())

    proc.stdin.close()
    proc.wait()
    dt = time.perf_counter() - t0
    print(f"句数    : {len(lines)}")
    print(f"时长    : {total:.1f}s ({frames} 帧)")
    print(f"耗时    : {dt:.1f}s  {frames / dt:.1f} fps")
    print(f"输出    : {out}  {out.stat().st_size / 1024 / 1024:.1f} MB")
    return out


def stills(text_path: Path, outdir: Path) -> None:
    lines = [ln.strip() for ln in text_path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]
    outdir.mkdir(parents=True, exist_ok=True)
    for i, ln in enumerate(lines):
        bg, anim, tcolor, align = SCENES[i % len(SCENES)](W, BAND_Y)
        img = Image.new("RGB", (W, H), PAPER)
        img.paste(bg, (0, 0))
        for sp, x, y in anim(1.8):
            img.paste(sp, (x, y), sp)
        f = font(F_SERIF, 74)
        while True:
            rgb, a = text_layer(ln, f, INK, spacing=6)
            if a.shape[1] <= W * 0.86 or f.size <= 34:
                break
            f = font(F_SERIF, f.size - 2)
        arr = np.array(img, dtype=np.float32)
        draw_band(arr, W, H)
        paste_text(arr, rgb, a, 140, BAND_Y + 52, 1.0)
        Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(outdir / f"s{i + 1}.jpg", quality=92)
        print(" ", outdir / f"s{i + 1}.jpg")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--title", default="")
    ap.add_argument("--sub", default="")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--per", type=float, default=4.2)
    ap.add_argument("--stills", help="只输出静帧到该目录")
    a = ap.parse_args()
    if a.stills:
        stills(Path(a.text), Path(a.stills))
    else:
        render(Path(a.text), Path(a.out), a.title, a.sub, a.fps, a.per)


if __name__ == "__main__":
    main()
