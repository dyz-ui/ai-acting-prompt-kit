"""电影感歌词片：代码绘制的场景 + 底部字幕

每句歌词一个完整画面（天空/远景/近景/气氛层），文字只做底部字幕。
镜头缓慢推进，颗粒 + 暗角 + 雾气 + 粒子制造景深。

    python scripts/lyric_cinema.py <文本> <输出.mp4>
    python scripts/lyric_cinema.py <文本> --stills out/cinema
"""
from __future__ import annotations

import argparse
import math
import random
import subprocess
import time
from pathlib import Path
from typing import Callable, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
SS = 2
PAD = 120          # 镜头推进余量

F_KAI = "C:/Windows/Fonts/simkai.ttf"
F_HEI = "C:/Windows/Fonts/msyh.ttc"


def font(path, size):
    for p in (path, "C:/Windows/Fonts/msyh.ttc"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def hexc(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vgrad(w, h, stops):
    """竖向渐变，stops = [(位置0-1, 颜色), ...]"""
    img = Image.new("RGB", (1, h))
    px = img.load()
    stops = sorted(stops)
    for y in range(h):
        p = y / (h - 1)
        for i in range(len(stops) - 1):
            p0, c0 = stops[i]
            p1, c1 = stops[i + 1]
            if p0 <= p <= p1:
                k = (p - p0) / max(1e-6, p1 - p0)
                px[0, y] = lerp(c0, c1, k)
                break
    return img.resize((w, h), Image.BILINEAR)


def glow_disc(size, color, softness=1.0):
    """发光圆盘：中心实心，向外指数衰减。"""
    s = size * 2
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    d = np.sqrt((xx - size) ** 2 + (yy - size) ** 2) / size
    a = np.clip(1.0 - d, 0, 1) ** (2.2 / max(0.2, softness))
    arr = np.zeros((s, s, 4), dtype=np.uint8)
    arr[:, :, 0], arr[:, :, 1], arr[:, :, 2] = color
    arr[:, :, 3] = (a * 255).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


def sprite(size, draw_fn):
    s = size * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(img), s)
    return img.resize((size, size), Image.LANCZOS)


def build_bg(draw_fn, w, h):
    img = Image.new("RGB", (w * SS, h * SS), (0, 0, 0))
    draw_fn(ImageDraw.Draw(img), w * SS, h * SS)
    return img.resize((w, h), Image.LANCZOS)


def fog_layer(w, h, alpha=12):
    """一团二维高斯衰减的雾：横竖都自然淡出，不会露出条带边缘。"""
    W2, H2 = int(w * 1.9), int(h * 0.46)
    yy, xx = np.mgrid[0:H2, 0:W2].astype(np.float32)
    cx, cy = W2 * 0.5, H2 * 0.5
    a = np.exp(-(((xx - cx) / (W2 * 0.40)) ** 2 + ((yy - cy) / (H2 * 0.28)) ** 2))
    arr = np.zeros((H2, W2, 4), dtype=np.uint8)
    arr[:, :, 0], arr[:, :, 1], arr[:, :, 2] = (214, 218, 230)
    arr[:, :, 3] = (a * alpha).astype(np.uint8)
    return Image.fromarray(arr, "RGBA")


# ---------------------------------------------------------------- 粒子
class Particles:
    """depth 0..1，越大越近：更大、更快、更亮。"""

    def __init__(self, kind, count, seed, area=(0, 0, W, H), size=(2, 6),
                 speed=(10, 34), color=(255, 255, 255), drift=26, alpha=(60, 170)):
        rnd = random.Random(seed)
        self.kind = kind
        self.items = []
        for _ in range(count):
            self.items.append({
                "x": rnd.uniform(area[0], area[2]),
                "y": rnd.uniform(area[1], area[3]),
                "z": rnd.random(),
                "ph": rnd.uniform(0, math.tau),
                "sp": rnd.uniform(*speed),
                "sz": rnd.uniform(*size),
                "al": rnd.uniform(*alpha),
            })
        self.area = area
        self.drift = drift
        self.color = color
        self.speed = speed

    def draw(self, canvas: Image.Image, t: float) -> None:
        d = ImageDraw.Draw(canvas, "RGBA")
        x0, y0, x1, y1 = self.area
        h = y1 - y0
        for p in self.items:
            sp = p["sp"] * (0.4 + p["z"])
            if self.kind == "snow":
                y = y0 + (p["y"] - y0 + sp * t) % h
                x = p["x"] + self.drift * p["z"] * math.sin(t * 0.5 + p["ph"])
                r = p["sz"] * (0.5 + p["z"])
                d.ellipse([x - r, y - r, x + r, y + r],
                          fill=self.color + (int(p["al"] * (0.4 + 0.6 * p["z"])),))
            elif self.kind == "rain":
                y = y0 + (p["y"] - y0 + sp * 6 * t) % h
                x = p["x"] - (y % 200) * 0.25
                ln = 14 + 26 * p["z"]
                d.line([(x, y), (x - ln * 0.22, y + ln)],
                       fill=self.color + (int(p["al"] * 0.55),), width=max(1, int(1 + p["z"])))
            elif self.kind == "dust":
                y = y0 + (p["y"] - y0 - sp * 0.35 * t) % h
                x = p["x"] + 18 * p["z"] * math.sin(t * 0.35 + p["ph"])
                r = p["sz"] * (0.4 + 0.5 * p["z"])
                d.ellipse([x - r, y - r, x + r, y + r],
                          fill=self.color + (int(p["al"] * (0.35 + 0.65 * p["z"])),))
            elif self.kind == "petal":
                y = y0 + (p["y"] - y0 + sp * t) % h
                x = p["x"] + 34 * p["z"] * math.sin(t * 0.7 + p["ph"])
                r = p["sz"] * (0.5 + p["z"])
                tilt = math.sin(t * 1.3 + p["ph"])
                d.ellipse([x - r * (0.6 + 0.5 * abs(tilt)), y - r, x + r * (0.6 + 0.5 * abs(tilt)), y + r],
                          fill=self.color + (int(p["al"] * 0.8),))
            elif self.kind == "star":
                tw = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * 1.6 + p["ph"]))
                r = p["sz"] * (0.35 + 0.5 * p["z"])
                d.ellipse([p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r],
                          fill=self.color + (int(p["al"] * tw),))


# ---------------------------------------------------------------- 七个场景
def sc_window(w, h):
    """1 · 深夜的窗，窗外有月亮，屋里亮着一盏灯。"""
    sky = vgrad(w, h, [(0.0, hexc("#0A0E22")), (0.45, hexc("#182142")), (0.75, hexc("#2C3358")), (1.0, hexc("#101426"))])
    moon = glow_disc(150 * SS, (250, 246, 225), 1.4)
    win = Image.new("RGBA", (int(w * 0.26 * SS), int(h * 0.40 * SS)), (0, 0, 0, 0))
    wd = ImageDraw.Draw(win)
    ww, wh = win.size
    wd.rectangle([0, 0, ww, wh], fill=(252, 232, 184, 255))
    # 窗内的人：坐着的侧影
    wd.ellipse([ww * 0.34, wh * 0.42, ww * 0.48, wh * 0.58], fill=(34, 26, 24, 255))
    wd.polygon([(ww * 0.24, wh), (ww * 0.30, wh * 0.62), (ww * 0.52, wh * 0.62), (ww * 0.58, wh)], fill=(34, 26, 24, 255))
    # 窗棂
    wd.rectangle([ww * 0.47, 0, ww * 0.53, wh], fill=(24, 18, 18, 255))
    wd.rectangle([0, wh * 0.46, ww, wh * 0.52], fill=(24, 18, 18, 255))
    win = win.filter(ImageFilter.GaussianBlur(1.5))

    def draw(d, W_, H_):
        d._image.paste(sky.resize((W_, H_)), (0, 0))
        d._image.paste(moon, (int(W_ * 0.60), int(H_ * 0.10)), moon)
        # 远处屋顶剪影
        ridge = [(0, H_ * 0.70)]
        x = 0.0
        y = 0.70
        while x < 1.0:
            x += 0.055
            y += random.Random(int(x * 1000)).uniform(-0.035, 0.035)
            ridge.append((W_ * x, H_ * max(0.56, min(0.76, y))))
        d.polygon(ridge + [(W_, H_), (0, H_)], fill=hexc("#0A0E1C"))
        # 墙
        d.rectangle([0, H_ * 0.60, W_, H_], fill=hexc("#151018"))
        # 窗：外框 + 窗台
        wx, wy = 0.10, 0.26
        ww_, wh_ = 0.28, 0.42
        d.rectangle([W_ * (wx - 0.012), H_ * (wy - 0.016), W_ * (wx + ww_ + 0.012), H_ * (wy + wh_ + 0.016)],
                    fill=hexc("#241A16"))
        ws = win.resize((int(W_ * ww_), int(H_ * wh_)))
        d._image.paste(ws, (int(W_ * wx), int(H_ * wy)), ws)
        # 窗光洒到地面
        for i in range(14):
            k = i / 14
            d.rectangle([W_ * (wx - 0.02 - k * 0.10), H_ * (wy + wh_ + 0.02 + k * 0.028),
                         W_ * (wx + ww_ + 0.02 + k * 0.10), H_ * (wy + wh_ + 0.02 + k * 0.028 + 0.012)],
                        fill=hexc("#2A2018"))
        d.rectangle([0, H_ * 0.93, W_, H_], fill=hexc("#0A0709"))

    return build_bg(draw, w, h), lambda t: Particles("snow", 46, 11, (0, 0, w, h * 0.7), (1.5, 4), (14, 40), (220, 226, 240)), hexc("#0A0C16")


def sc_rain(w, h):
    """2 · 隔着雨窗的两个身影。"""
    sky = vgrad(w, h, [(0.0, hexc("#151A2A")), (0.5, hexc("#2A2438")), (1.0, hexc("#3A2E36"))])
    lamp = glow_disc(190 * SS, (255, 196, 128), 1.1)

    def draw(d, W_, H_):
        d._image.paste(sky.resize((W_, H_)), (0, 0))
        d._image.paste(lamp, (int(W_ * 0.52), int(H_ * 0.18)), lamp)
        # 两个模糊身影（窗外）
        for cx, deep, sc in ((0.29, "#141726", 1.0), (0.71, "#0F1220", 0.94)):
            hw = W_ * 0.016 * sc
            hy = H_ * 0.44
            d.ellipse([W_ * cx - hw * 0.95, hy - hw * 1.05, W_ * cx + hw * 0.95, hy + hw * 1.05], fill=hexc(deep))
            d.polygon([(W_ * cx - hw * 1.0, hy + hw * 0.85),
                       (W_ * cx - hw * 2.5, hy + hw * 4.2),
                       (W_ * cx - hw * 2.0, hy + hw * 14.0),
                       (W_ * cx - hw * 1.5, hy + hw * 20.0),
                       (W_ * cx + hw * 1.5, hy + hw * 20.0),
                       (W_ * cx + hw * 2.0, hy + hw * 14.0),
                       (W_ * cx + hw * 2.5, hy + hw * 4.2),
                       (W_ * cx + hw * 1.0, hy + hw * 0.85)], fill=hexc(deep))
        # 窗棂
        d.rectangle([0, 0, W_ * 0.02, H_], fill=hexc("#0A0B12"))
        d.rectangle([W_ * 0.98, 0, W_, H_], fill=hexc("#0A0B12"))
        d.rectangle([0, 0, W_, H_ * 0.035], fill=hexc("#0A0B12"))
        d.rectangle([0, H_ * 0.96, W_, H_], fill=hexc("#0A0B12"))

    return build_bg(draw, w, h), lambda t: Particles("rain", 150, 21, (0, 0, w, h), (1, 2), (26, 52), (188, 204, 226)), hexc("#0B0D16")


def sc_letter(w, h):
    """3 · 台灯下的一封没寄出的信。"""
    bgc = vgrad(w, h, [(0.0, hexc("#120E0A")), (0.6, hexc("#241A12")), (1.0, hexc("#0C0906"))])
    lamp = glow_disc(230 * SS, (255, 208, 140), 1.0)

    # 柔光锥：画个三角形再重度模糊
    cone = Image.new("RGBA", (int(w * SS), int(h * SS)), (0, 0, 0, 0))
    ImageDraw.Draw(cone).polygon(
        [(w * SS * 0.34, h * SS * 0.26), (w * SS * 0.56, h * SS * 0.26),
         (w * SS * 0.88, h * SS * 0.80), (w * SS * 0.06, h * SS * 0.80)],
        fill=(255, 214, 150, 40))
    cone = cone.filter(ImageFilter.GaussianBlur(int(w * SS * 0.03)))

    def draw(d, W_, H_):
        d._image.paste(bgc.resize((W_, H_)), (0, 0))
        d._image.paste(lamp, (int(W_ * 0.24), int(H_ * 0.10)), lamp)
        d._image.paste(cone.resize((W_, H_)), (0, 0), cone.resize((W_, H_)))
        # 灯罩 + 灯杆
        d.polygon([(W_ * 0.30, H_ * 0.20), (W_ * 0.58, H_ * 0.20),
                   (W_ * 0.64, H_ * 0.33), (W_ * 0.24, H_ * 0.33)], fill=hexc("#241A12"))
        d.rectangle([W_ * 0.425, H_ * 0.33, W_ * 0.445, H_ * 0.64], fill=hexc("#1E150E"))
        d.ellipse([W_ * 0.39, H_ * 0.62, W_ * 0.48, H_ * 0.655], fill=hexc("#1E150E"))
        # 桌面 + 木纹
        d.rectangle([0, H_ * 0.62, W_, H_], fill=hexc("#1A120C"))
        for i in range(16):
            y = H_ * (0.64 + i * 0.023)
            d.line([(0, y), (W_, y + H_ * 0.004)], fill=hexc("#22170F"), width=max(1, int(H_ * 0.0022)))
        pass
        # 信封
        ex0, ey0, ex1, ey1 = W_ * 0.34, H_ * 0.66, W_ * 0.66, H_ * 0.84
        d.polygon([(ex0, ey0), (ex1, ey0), (ex1, ey1), (ex0, ey1)], fill=hexc("#E8DCC2"))
        d.line([(ex0, ey0), (W_ * 0.50, H_ * 0.76), (ex1, ey0)], fill=hexc("#B8A886"), width=int(W_ * 0.003))
        d.ellipse([W_ * 0.49, H_ * 0.745, W_ * 0.515, H_ * 0.775], fill=hexc("#8C3B2A"))

    return build_bg(draw, w, h), lambda t: Particles("dust", 54, 31, (0, 0, w, h * 0.8), (1, 3.2), (8, 22), (255, 226, 180), alpha=(50, 150)), hexc("#0C0906")


def sc_road(w, h):
    """4 · 黄昏公路，一个人走向远方。"""
    sky = vgrad(w, h, [(0.0, hexc("#2B1E3A")), (0.35, hexc("#7A3B4A")), (0.62, hexc("#D97A4A")), (0.78, hexc("#F0B070"))])
    sun = glow_disc(120 * SS, (255, 214, 150), 1.6)

    def draw(d, W_, H_):
        d._image.paste(sky.resize((W_, H_)), (0, 0))
        d._image.paste(sun, (int(W_ * 0.60), int(H_ * 0.48)), sun)
        # 远山三层
        d.polygon([(0, H_ * 0.66), (W_ * 0.22, H_ * 0.55), (W_ * 0.42, H_ * 0.64),
                   (W_ * 0.66, H_ * 0.52), (W_ * 0.86, H_ * 0.62), (W_, H_ * 0.58),
                   (W_, H_), (0, H_)], fill=hexc("#4A2A34"))
        d.polygon([(0, H_ * 0.74), (W_ * 0.26, H_ * 0.66), (W_ * 0.52, H_ * 0.73),
                   (W_ * 0.78, H_ * 0.65), (W_, H_ * 0.72), (W_, H_), (0, H_)], fill=hexc("#2A1822"))
        # 公路
        d.polygon([(W_ * 0.46, H_ * 0.70), (W_ * 0.54, H_ * 0.70),
                   (W_ * 0.82, H_), (W_ * 0.18, H_)], fill=hexc("#1A1218"))
        for i in range(7):
            p = i / 7
            y = H_ * (0.72 + p * 0.28) ** 1.0
            wd = W_ * (0.004 + p * 0.012)
            d.rectangle([W_ * 0.5 - wd, y, W_ * 0.5 + wd, y + H_ * (0.006 + p * 0.02)], fill=hexc("#C9A06A"))
        # 电线杆
        for i, (px, s) in enumerate([(0.22, 0.92), (0.30, 0.78), (0.68, 0.74)]):
            top = H_ * (0.72 - (0.72 - 0.34) * (1 - s) - 0.06)
            d.rectangle([W_ * px, top, W_ * px + W_ * 0.004, H_ * 0.76], fill=hexc("#120C12"))
            d.rectangle([W_ * px - W_ * 0.012, top, W_ * px + W_ * 0.016, top + H_ * 0.006], fill=hexc("#120C12"))
        # 人影
        cx, cy = W_ * 0.585, H_ * 0.80
        d.ellipse([cx - W_ * 0.006, cy - H_ * 0.045, cx + W_ * 0.006, cy - H_ * 0.026], fill=hexc("#0B0810"))
        d.polygon([(cx - W_ * 0.008, cy + H_ * 0.02), (cx - W_ * 0.006, cy - H_ * 0.026),
                   (cx + W_ * 0.006, cy - H_ * 0.026), (cx + W_ * 0.008, cy + H_ * 0.02)], fill=hexc("#0B0810"))

    return build_bg(draw, w, h), lambda t: Particles("dust", 30, 41, (0, H * 0.2, w, H * 0.7), (1, 2.4), (6, 14), (255, 210, 170), alpha=(30, 90)), hexc("#120C12")


def sc_stars(w, h):
    """5 · 山脊上仰望星空。"""
    sky = vgrad(w, h, [(0.0, hexc("#04060F")), (0.4, hexc("#0A1230")), (0.7, hexc("#16203F")), (1.0, hexc("#0A0F20"))])
    milky = glow_disc(320 * SS, (150, 170, 255), 0.8)

    def draw(d, W_, H_):
        d._image.paste(sky.resize((W_, H_)), (0, 0))
        d._image.paste(milky, (int(-W_ * 0.1), int(-H_ * 0.2)), milky)
        # 山脊
        d.polygon([(0, H_ * 0.78), (W_ * 0.16, H_ * 0.62), (W_ * 0.30, H_ * 0.72),
                   (W_ * 0.46, H_ * 0.56), (W_ * 0.62, H_ * 0.70), (W_ * 0.80, H_ * 0.60),
                   (W_, H_ * 0.74), (W_, H_), (0, H_)], fill=hexc("#05070E"))
        # 山脊上的人
        cx, cy = W_ * 0.47, H_ * 0.555
        d.ellipse([cx - W_ * 0.005, cy - H_ * 0.030, cx + W_ * 0.005, cy - H_ * 0.016], fill=hexc("#03040A"))
        d.polygon([(cx - W_ * 0.007, cy), (cx - W_ * 0.005, cy - H_ * 0.016),
                   (cx + W_ * 0.005, cy - H_ * 0.016), (cx + W_ * 0.007, cy)], fill=hexc("#03040A"))

    return build_bg(draw, w, h), lambda t: Particles("star", 130, 51, (0, 0, w, h * 0.7), (1, 2.6), (0, 1), (222, 232, 255)), hexc("#05070E")


def sc_blossom(w, h):
    """6 · 逆光的花枝，花瓣在落。"""
    bgc = vgrad(w, h, [(0.0, hexc("#F7E2C8")), (0.45, hexc("#E9B98C")), (1.0, hexc("#8A5A4A"))])
    sun = glow_disc(210 * SS, (255, 236, 200), 1.3)

    def draw(d, W_, H_):
        d._image.paste(bgc.resize((W_, H_)), (0, 0))
        d._image.paste(sun, (int(W_ * 0.60), int(H_ * 0.12)), sun)
        # 枝
        d.line([(-W_ * 0.02, H_ * 0.30), (W_ * 0.22, H_ * 0.42), (W_ * 0.40, H_ * 0.36)],
               fill=hexc("#3A2018"), width=int(W_ * 0.007))
        d.line([(W_ * 0.22, H_ * 0.42), (W_ * 0.30, H_ * 0.60)], fill=hexc("#3A2018"), width=int(W_ * 0.004))
        d.line([(W_ * 0.16, H_ * 0.38), (W_ * 0.10, H_ * 0.16)], fill=hexc("#3A2018"), width=int(W_ * 0.004))
        # 花
        for (cx, cy, r) in [(0.12, 0.18, 0.030), (0.24, 0.40, 0.026), (0.36, 0.34, 0.022), (0.30, 0.56, 0.018)]:
            for k in range(6):
                a = -math.pi / 2 + k * math.tau / 6 + 0.2
                px = W_ * cx + math.cos(a) * W_ * r * 0.78
                py = H_ * cy + math.sin(a) * W_ * r * 0.78
                d.ellipse([px - W_ * r * 0.62, py - H_ * r * 0.55,
                           px + W_ * r * 0.62, py + H_ * r * 0.55], fill=hexc("#C4553B"))
            for k in range(6):
                a = -math.pi / 2 + k * math.tau / 6 + 0.2
                px = W_ * cx + math.cos(a) * W_ * r * 0.62
                py = H_ * cy + math.sin(a) * W_ * r * 0.62
                d.ellipse([px - W_ * r * 0.30, py - H_ * r * 0.26,
                           px + W_ * r * 0.30, py + H_ * r * 0.26], fill=hexc("#D9705A"))
            d.ellipse([W_ * cx - W_ * r * 0.22, H_ * cy - H_ * r * 0.22,
                       W_ * cx + W_ * r * 0.22, H_ * cy + H_ * r * 0.22], fill=hexc("#F2D08A"))
        # 地面
        d.rectangle([0, H_ * 0.88, W_, H_], fill=hexc("#4A2A22"))

    return build_bg(draw, w, h), lambda t: Particles("petal", 42, 61, (0, 0, w, h * 0.95), (2, 5), (22, 46), (232, 150, 130)), hexc("#3A2018")


def sc_river(w, h):
    """7 · 江面，一条船远去。"""
    sky = vgrad(w, h, [(0.0, hexc("#101A2E")), (0.35, hexc("#3C4A66")), (0.55, hexc("#C08A6A")), (0.62, hexc("#8A6A62"))])
    sun = glow_disc(130 * SS, (255, 214, 170), 1.5)

    def draw(d, W_, H_):
        d._image.paste(sky.resize((W_, H_)), (0, 0))
        d._image.paste(sun, (int(W_ * 0.66), int(H_ * 0.44)), sun)
        # 远岸
        shore = [(0, H_ * 0.60)]
        x = 0.0
        y = 0.60
        while x < 1.0:
            x += 0.07
            y += random.Random(int(x * 777)).uniform(-0.018, 0.018)
            shore.append((W_ * x, H_ * max(0.545, min(0.625, y))))
        d.polygon(shore + [(W_, H_ * 0.66), (0, H_ * 0.66)], fill=hexc("#282836"))
        # 水面
        d.rectangle([0, H_ * 0.60, W_, H_], fill=hexc("#20303F"))
        # 波光
        rnd = random.Random(9)
        for row in range(22):
            p = (row / 22) ** 1.35
            y = H_ * (0.635 + p * 0.34)
            spread = W_ * (0.020 + 0.085 * p)
            for _ in range(rnd.randint(1, 3)):
                x0 = W_ * 0.665 + rnd.uniform(-spread, spread)
                ln = W_ * rnd.uniform(0.008, 0.030) * (0.5 + p * 1.6)
                al = int(60 + 150 * rnd.random() * (0.4 + 0.6 * p))
                d.line([(x0 - ln, y), (x0 + ln, y)], fill=hexc("#F0C48E") + (al,),
                       width=max(2, int(H_ * (0.0022 + 0.0026 * p))))

    return build_bg(draw, w, h), lambda t: Particles("dust", 26, 71, (0, H * 0.55, w, H), (1, 3), (6, 16), (255, 220, 180), alpha=(25, 80)), hexc("#141C28")


SCENES: List[Callable] = [sc_window, sc_rain, sc_letter, sc_road, sc_stars, sc_blossom, sc_river]


# ---------------------------------------------------------------- 字幕
def sub_layer(text: str):
    f = font(F_KAI, 46)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    tw = int(sum(probe.textlength(c, font=f) + 3 for c in text))
    img = Image.new("RGBA", (tw + 40, 90), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = 20
    for c in text:
        d.text((x, 6), c, font=f, fill=(245, 243, 238, 236))
        x += probe.textlength(c, font=f) + 3
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).text((22, 8), text, font=f, fill=(0, 0, 0, 150))
    sh = sh.filter(ImageFilter.GaussianBlur(3))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(sh)
    out.alpha_composite(img)
    return out


def render(text_path: Path, out: Path, fps: int = 24, per: float = 4.2,
           trans: float = 0.9) -> Path:
    lines = [ln.strip() for ln in text_path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]

    built = []
    for i, ln in enumerate(lines):
        fn = SCENES[i % len(SCENES)]
        bg, pfn, fadec = fn(W, H)
        fog = fog_layer(W, H, 14 if i % 2 == 0 else 10)
        big = Image.new("RGB", (W + PAD * 2, H + PAD * 2), fadec)
        big.paste(bg, (PAD, PAD))
        fog_y = [0.50, 0.46, 0.28, 0.44, 0.46, 0.62, 0.52][i % 7]
        built.append((big, pfn, fadec, sub_layer(ln), fog, fog_y))

    total = len(lines) * per + 1.2
    frames = int(total * fps)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)

    scrim = Image.new("RGBA", (W, 240), (0, 0, 0, 0))
    sa = np.zeros((240, 1, 1), dtype=np.float32)
    for yy in range(240):
        sa[yy, 0, 0] = 110 * (yy / 239) ** 1.6
    arr_s = np.zeros((240, W, 4), dtype=np.uint8)
    arr_s[:, :, 3] = np.repeat(sa[:, :, 0], W, axis=1).astype(np.uint8)
    scrim = Image.fromarray(arr_s, "RGBA")

    rng = np.random.default_rng(5)
    grain = rng.normal(0, 3.0, (H, W, 1)).astype(np.float32)
    vig = None
    u8 = np.empty((H, W, 3), dtype=np.uint8)

    t0 = time.perf_counter()
    for i in range(frames):
        t = i / fps
        idx = min(int(t // per), len(lines) - 1)
        lt = t - idx * per
        big, pfn, fadec, sub, fog, fog_y = built[idx]

        # 镜头推进：从大图里裁一个缓慢移动的窗口
        p = lt / per
        z = 1.0 - 0.06 * p
        cw, ch = W * z, H * z
        cx = PAD + (W - cw) / 2 + 26 * math.sin(p * 1.6)
        cy = PAD + (H - ch) / 2 - 12 * p
        frame = big.crop((int(cx), int(cy), int(cx + cw), int(cy + ch))).resize((W, H), Image.BILINEAR)

        fx = int(-W * 0.25 + 70 * math.sin(t * 0.12))
        frame.paste(fog, (fx, int(H * fog_y)), fog)
        pfn(t).draw(frame, t)

        # 字幕
        frame.paste(scrim, (0, H - 240), scrim)
        if lt > 0.5 and lt < per - 0.35:
            al = min(1.0, (lt - 0.5) / 0.45) * min(1.0, (per - 0.35 - lt) / 0.45)
            s = sub.copy()
            if al < 0.99:
                a = s.split()[3].point(lambda v: int(v * al))
                s.putalpha(a)
            frame.alpha_composite(s, ((W - s.width) // 2, H - 148)) if frame.mode == "RGBA" else frame.paste(s, ((W - s.width) // 2, H - 148), s)

        arr = np.asarray(frame.convert("RGB"), dtype=np.float32)

        # 暗角
        if vig is None:
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
            vig = np.clip(1.06 - 0.30 * r ** 2, 0.62, 1.0)[:, :, None]
        arr *= vig
        # 提亮暗部（gamma），让夜景不死黑
        arr = 255.0 * np.power(np.clip(arr / 255.0, 0, 1), 0.90)
        arr += grain

        # 场景切换：短促压黑
        edge = min(lt, per - lt)
        if edge < 0.22:
            arr *= 0.35 + 0.65 * (edge / 0.22)

        if t > total - 1.0:
            arr *= max(0.0, (total - t) / 1.0)

        np.clip(arr, 0, 255, out=arr)
        np.copyto(u8, arr, casting="unsafe")
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
        fn = SCENES[i % len(SCENES)]
        bg, pfn, fadec = fn(W, H)
        frame = bg.copy()
        pfn(2.0).draw(frame, 2.0)
        s = sub_layer(ln)
        frame.paste(s, ((W - s.width) // 2, H - 148), s)
        arr = np.asarray(frame, dtype=np.float32)
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
        arr *= np.clip(1.06 - 0.30 * r ** 2, 0.62, 1.0)[:, :, None]
        Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(outdir / f"c{i + 1}.jpg", quality=93)
        print(" ", outdir / f"c{i + 1}.jpg")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--per", type=float, default=4.2)
    ap.add_argument("--stills")
    a = ap.parse_args()
    if a.stills:
        stills(Path(a.text), Path(a.stills))
    else:
        render(Path(a.text), Path(a.out), a.fps, a.per)


if __name__ == "__main__":
    main()
