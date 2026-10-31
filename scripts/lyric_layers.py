"""分层歌词片：场景按图层顺序生长 + 代码合成配乐

每个场景由 4–6 个图层构成，进屋式地一层层浮现（天 → 远山 → 近景 → 细节），
最后落字幕。音频用 numpy 合成，不引外部素材。

    python scripts/lyric_layers.py <文本> <输出.mp4>
    python scripts/lyric_layers.py <文本> --stills out/layers
"""
from __future__ import annotations

import argparse
import math
import random
import subprocess
import time
import wave
from pathlib import Path
from typing import Callable, List, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from lyric_cinema import (Particles, font, fog_layer, glow_disc, hexc, lerp,
                          sub_layer, vgrad, F_KAI)

W, H = 1920, 1080
SS = 2
PAD = 110
BIG_W, BIG_H = W + PAD * 2, H + PAD * 2


# ---------------------------------------------------------------- 图层工具
def layer(draw_fn) -> Image.Image:
    """按画面尺寸（W×H）绘制一个图层，2 倍超采样后降采样。透明底。"""
    img = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    draw_fn(ImageDraw.Draw(img), W * SS, H * SS)
    return img.resize((W, H), Image.LANCZOS)


def rail(d, pts, color, width):
    """折线（PIL 的 line 带 joint 才圆滑）"""
    d.line(pts, fill=color, width=width, joint="curve")


# ---------------------------------------------------------------- 七个场景（分层）
def sc_window():
    sky = layer(lambda d, W_, H_: (
        d._image.paste(vgrad(W_, H_, [(0.0, hexc("#0A0E22")), (0.45, hexc("#182142")),
                                      (0.75, hexc("#2C3358")), (1.0, hexc("#101426"))]).resize((W_, H_)), (0, 0)),
        d._image.paste(glow_disc(150 * SS, (250, 246, 225), 1.4), (int(W_ * 0.60), int(H_ * 0.10)),
                       glow_disc(150 * SS, (250, 246, 225), 1.4)),
    ))

    def _ridge(d, W_, H_):
        ridge = [(0, H_ * 0.70)]
        x, y = 0.0, 0.70
        while x < 1.0:
            x += 0.055
            y += random.Random(int(x * 1000)).uniform(-0.035, 0.035)
            ridge.append((W_ * x, H_ * max(0.56, min(0.76, y))))
        d.polygon(ridge + [(W_, H_), (0, H_)], fill=hexc("#0A0E1C"))
    ridge = layer(_ridge)

    def _wall(d, W_, H_):
        d.rectangle([0, H_ * 0.60, W_, H_], fill=hexc("#151018"))
        d.rectangle([0, H_ * 0.93, W_, H_], fill=hexc("#0A0709"))
    wall = layer(_wall)

    def _win(d, W_, H_):
        wx, wy, ww_, wh_ = 0.10, 0.26, 0.28, 0.42
        d.rectangle([W_ * (wx - 0.012), H_ * (wy - 0.016), W_ * (wx + ww_ + 0.012), H_ * (wy + wh_ + 0.016)],
                    fill=hexc("#241A16"))
        d.rectangle([W_ * wx, H_ * wy, W_ * (wx + ww_), H_ * (wy + wh_)], fill=(252, 232, 184, 255))
        cx, cy = 0.34, 0.42
        d.ellipse([W_ * (wx + ww_ * (cx - 0.07)), H_ * (wy + wh_ * cy),
                   W_ * (wx + ww_ * (cx + 0.07)), H_ * (wy + wh_ * (cy + 0.14))], fill=(34, 26, 24, 255))
        d.polygon([(W_ * (wx + ww_ * 0.24), H_ * (wy + wh_)),
                   (W_ * (wx + ww_ * 0.30), H_ * (wy + wh_ * 0.60)),
                   (W_ * (wx + ww_ * 0.52), H_ * (wy + wh_ * 0.60)),
                   (W_ * (wx + ww_ * 0.58), H_ * (wy + wh_))], fill=(34, 26, 24, 255))
        d.rectangle([W_ * (wx + ww_ * 0.47), H_ * wy, W_ * (wx + ww_ * 0.53), H_ * (wy + wh_)], fill=(24, 18, 18, 255))
        d.rectangle([W_ * wx, H_ * (wy + wh_ * 0.46), W_ * (wx + ww_), H_ * (wy + wh_ * 0.52)], fill=(24, 18, 18, 255))
    window = layer(_win)

    def _pool(d, W_, H_):
        for i in range(14):
            k = i / 14
            d.rectangle([W_ * (0.08 - k * 0.10), H_ * (0.68 + k * 0.028),
                         W_ * (0.40 + k * 0.10), H_ * (0.692 + k * 0.028)], fill=(42, 32, 24, 255))
    pool = layer(_pool)

    return [(sky, 0.00), (ridge, 0.30), (wall, 0.55), (window, 0.80), (pool, 1.05)], \
           (lambda t: Particles("snow", 46, 11, (0, 0, W, H * 0.7), (1.5, 4), (14, 40), (220, 226, 240))), \
           hexc("#0A0C16")


def sc_rain():
    sky = layer(lambda d, W_, H_: (
        d._image.paste(vgrad(W_, H_, [(0.0, hexc("#151A2A")), (0.5, hexc("#2A2438")),
                                      (1.0, hexc("#3A2E36"))]).resize((W_, H_)), (0, 0)),
        d._image.paste(glow_disc(190 * SS, (255, 196, 128), 1.1), (int(W_ * 0.52), int(H_ * 0.18)),
                       glow_disc(190 * SS, (255, 196, 128), 1.1)),
    ))

    def _fig(d, W_, H_):
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
    figs = layer(_fig)

    def _frame(d, W_, H_):
        d.rectangle([0, 0, W_ * 0.02, H_], fill=hexc("#0A0B12"))
        d.rectangle([W_ * 0.98, 0, W_, H_], fill=hexc("#0A0B12"))
        d.rectangle([0, 0, W_, H_ * 0.035], fill=hexc("#0A0B12"))
        d.rectangle([0, H_ * 0.96, W_, H_], fill=hexc("#0A0B12"))
    frame = layer(_frame)

    return [(sky, 0.00), (figs, 0.40), (frame, 0.85)], \
           (lambda t: Particles("rain", 150, 21, (0, 0, W, H), (1, 2), (26, 52), (188, 204, 226))), \
           hexc("#0B0D16")


def sc_letter():
    bg = layer(lambda d, W_, H_: (
        d._image.paste(vgrad(W_, H_, [(0.0, hexc("#120E0A")), (0.6, hexc("#241A12")),
                                      (1.0, hexc("#0C0906"))]).resize((W_, H_)), (0, 0)),
        d._image.paste(glow_disc(230 * SS, (255, 208, 140), 1.0), (int(W_ * 0.24), int(H_ * 0.10)),
                       glow_disc(230 * SS, (255, 208, 140), 1.0)),
    ))

    def _desk(d, W_, H_):
        d.rectangle([0, H_ * 0.62, W_, H_], fill=hexc("#1A120C"))
        for i in range(16):
            y = H_ * (0.64 + i * 0.023)
            d.line([(0, y), (W_, y + H_ * 0.004)], fill=hexc("#22170F"), width=max(1, int(H_ * 0.0022)))
    desk = layer(_desk)

    def _lamp(d, W_, H_):
        d.polygon([(W_ * 0.30, H_ * 0.20), (W_ * 0.58, H_ * 0.20),
                   (W_ * 0.64, H_ * 0.33), (W_ * 0.24, H_ * 0.33)], fill=hexc("#241A12"))
        d.rectangle([W_ * 0.425, H_ * 0.33, W_ * 0.445, H_ * 0.64], fill=hexc("#1E150E"))
        d.ellipse([W_ * 0.39, H_ * 0.62, W_ * 0.48, H_ * 0.655], fill=hexc("#1E150E"))
    lamp = layer(_lamp)

    def _letter(d, W_, H_):
        ex0, ey0, ex1, ey1 = W_ * 0.34, H_ * 0.62, W_ * 0.66, H_ * 0.80
        d.polygon([(ex0, ey0), (ex1, ey0), (ex1, ey1), (ex0, ey1)], fill=hexc("#E8DCC2"))
        rail(d, [(ex0, ey0), (W_ * 0.50, H_ * 0.72), (ex1, ey0)], hexc("#B8A886"), int(W_ * 0.003))
        d.ellipse([W_ * 0.49, H_ * 0.705, W_ * 0.515, H_ * 0.735], fill=hexc("#8C3B2A"))
    letter = layer(_letter)

    cone = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
    ImageDraw.Draw(cone).polygon(
        [(W * SS * 0.34, H * SS * 0.26), (W * SS * 0.56, H * SS * 0.26),
         (W * SS * 0.88, H * SS * 0.80), (W * SS * 0.06, H * SS * 0.80)],
        fill=(255, 214, 150, 46))
    cone = cone.filter(ImageFilter.GaussianBlur(int(W * SS * 0.03))).resize((W, H), Image.LANCZOS)

    return [(bg, 0.00), (cone, 0.30), (desk, 0.52), (lamp, 0.72), (letter, 0.92)], \
           (lambda t: Particles("dust", 54, 31, (0, 0, W, H * 0.8), (1, 3.2), (8, 22), (255, 226, 180), alpha=(50, 150))), \
           hexc("#0C0906")


def sc_road():
    sky = layer(lambda d, W_, H_: (
        d._image.paste(vgrad(W_, H_, [(0.0, hexc("#2B1E3A")), (0.35, hexc("#7A3B4A")),
                                      (0.62, hexc("#D97A4A")), (0.78, hexc("#F0B070"))]).resize((W_, H_)), (0, 0)),
        d._image.paste(glow_disc(120 * SS, (255, 214, 150), 1.6), (int(W_ * 0.60), int(H_ * 0.48)),
                       glow_disc(120 * SS, (255, 214, 150), 1.6)),
    ))

    def _far(d, W_, H_):
        d.polygon([(0, H_ * 0.66), (W_ * 0.22, H_ * 0.55), (W_ * 0.42, H_ * 0.64),
                   (W_ * 0.66, H_ * 0.52), (W_ * 0.86, H_ * 0.62), (W_, H_ * 0.58),
                   (W_, H_), (0, H_)], fill=hexc("#4A2A34"))
    far = layer(_far)

    def _near(d, W_, H_):
        d.polygon([(0, H_ * 0.74), (W_ * 0.26, H_ * 0.66), (W_ * 0.52, H_ * 0.73),
                   (W_ * 0.78, H_ * 0.65), (W_, H_ * 0.72), (W_, H_), (0, H_)], fill=hexc("#2A1822"))
    near = layer(_near)

    def _road(d, W_, H_):
        d.polygon([(W_ * 0.46, H_ * 0.70), (W_ * 0.54, H_ * 0.70),
                   (W_ * 0.82, H_), (W_ * 0.18, H_)], fill=hexc("#1A1218"))
        for i in range(7):
            p = i / 7
            y = H_ * (0.72 + p * 0.28)
            wd = W_ * (0.004 + p * 0.012)
            d.rectangle([W_ * 0.5 - wd, y, W_ * 0.5 + wd, y + H_ * (0.006 + p * 0.02)], fill=hexc("#C9A06A"))
    road = layer(_road)

    def _poles(d, W_, H_):
        for (px, s) in [(0.22, 0.92), (0.30, 0.78), (0.68, 0.74)]:
            top = H_ * (0.72 - (0.72 - 0.34) * (1 - s) - 0.06)
            d.rectangle([W_ * px, top, W_ * px + W_ * 0.004, H_ * 0.76], fill=hexc("#120C12"))
            d.rectangle([W_ * px - W_ * 0.012, top, W_ * px + W_ * 0.016, top + H_ * 0.006], fill=hexc("#120C12"))
        cx, cy = W_ * 0.585, H_ * 0.80
        d.ellipse([cx - W_ * 0.006, cy - H_ * 0.045, cx + W_ * 0.006, cy - H_ * 0.026], fill=hexc("#0B0810"))
        d.polygon([(cx - W_ * 0.008, cy + H_ * 0.02), (cx - W_ * 0.006, cy - H_ * 0.026),
                   (cx + W_ * 0.006, cy - H_ * 0.026), (cx + W_ * 0.008, cy + H_ * 0.02)], fill=hexc("#0B0810"))
    poles = layer(_poles)

    return [(sky, 0.00), (far, 0.28), (near, 0.52), (road, 0.74), (poles, 0.96)], \
           (lambda t: Particles("dust", 30, 41, (0, H * 0.2, W, H * 0.7), (1, 2.4), (6, 14), (255, 210, 170), alpha=(30, 90))), \
           hexc("#120C12")


def sc_stars():
    sky = layer(lambda d, W_, H_: (
        d._image.paste(vgrad(W_, H_, [(0.0, hexc("#04060F")), (0.4, hexc("#0A1230")),
                                      (0.7, hexc("#16203F")), (1.0, hexc("#0A0F20"))]).resize((W_, H_)), (0, 0)),
        d._image.paste(glow_disc(320 * SS, (150, 170, 255), 0.8), (int(-W_ * 0.1), int(-H_ * 0.2)),
                       glow_disc(320 * SS, (150, 170, 255), 0.8)),
    ))

    def _ridge(d, W_, H_):
        d.polygon([(0, H_ * 0.78), (W_ * 0.16, H_ * 0.62), (W_ * 0.30, H_ * 0.72),
                   (W_ * 0.46, H_ * 0.56), (W_ * 0.62, H_ * 0.70), (W_ * 0.80, H_ * 0.60),
                   (W_, H_ * 0.74), (W_, H_), (0, H_)], fill=hexc("#05070E"))
    ridge = layer(_ridge)

    def _man(d, W_, H_):
        cx, cy = W_ * 0.47, H_ * 0.555
        d.ellipse([cx - W_ * 0.005, cy - H_ * 0.030, cx + W_ * 0.005, cy - H_ * 0.016], fill=hexc("#03040A"))
        d.polygon([(cx - W_ * 0.007, cy), (cx - W_ * 0.005, cy - H_ * 0.016),
                   (cx + W_ * 0.005, cy - H_ * 0.016), (cx + W_ * 0.007, cy)], fill=hexc("#03040A"))
    man = layer(_man)

    return [(sky, 0.00), (ridge, 0.45), (man, 0.80)], \
           (lambda t: Particles("star", 130, 51, (0, 0, W, H * 0.7), (1, 2.6), (0, 1), (222, 232, 255))), \
           hexc("#05070E")


def sc_blossom():
    def _bg(d, W_, H_):
        base = vgrad(W_, H_, [(0.0, hexc("#F7E2C8")), (0.45, hexc("#E9B98C")),
                              (1.0, hexc("#8A5A4A"))]).resize((W_, H_))
        arr = np.asarray(base, dtype=np.float32)
        yy, xx = np.mgrid[0:H_, 0:W_].astype(np.float32)
        # 加色光晕：亮背景上用覆盖会发灰，必须相加
        dist = np.sqrt(((xx - W_ * 0.58) / (W_ * 0.30)) ** 2 +
                       ((yy - H_ * 0.20) / (H_ * 0.26)) ** 2)
        glow = np.clip(1.0 - dist, 0, 1) ** 2.0
        arr += glow[:, :, None] * np.array([90, 55, 18], dtype=np.float32)
        d._image.paste(Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), (0, 0))
    bg = layer(_bg)

    def _branch(d, W_, H_):
        rail(d, [(-W_ * 0.02, H_ * 0.30), (W_ * 0.22, H_ * 0.42), (W_ * 0.40, H_ * 0.36)],
             hexc("#3A2018"), int(W_ * 0.007))
        rail(d, [(W_ * 0.22, H_ * 0.42), (W_ * 0.30, H_ * 0.60)], hexc("#3A2018"), int(W_ * 0.004))
        rail(d, [(W_ * 0.16, H_ * 0.38), (W_ * 0.10, H_ * 0.16)], hexc("#3A2018"), int(W_ * 0.004))
    branch = layer(_branch)

    def _flowers(d, W_, H_):
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
    flowers = layer(_flowers)

    def _ground(d, W_, H_):
        d.rectangle([0, H_ * 0.88, W_, H_], fill=hexc("#4A2A22"))
    ground = layer(_ground)

    return [(bg, 0.00), (branch, 0.35), (flowers, 0.62), (ground, 0.88)], \
           (lambda t: Particles("petal", 42, 61, (0, 0, W, H * 0.95), (2, 5), (22, 46), (232, 150, 130))), \
           hexc("#3A2018")


def sc_river():
    sky = layer(lambda d, W_, H_: (
        d._image.paste(vgrad(W_, H_, [(0.0, hexc("#101A2E")), (0.35, hexc("#3C4A66")),
                                      (0.55, hexc("#C08A6A")), (0.62, hexc("#8A6A62"))]).resize((W_, H_)), (0, 0)),
        d._image.paste(glow_disc(130 * SS, (255, 214, 170), 1.5), (int(W_ * 0.66), int(H_ * 0.44)),
                       glow_disc(130 * SS, (255, 214, 170), 1.5)),
    ))

    def _shore(d, W_, H_):
        shore = [(0, H_ * 0.60)]
        x, y = 0.0, 0.60
        while x < 1.0:
            x += 0.07
            y += random.Random(int(x * 777)).uniform(-0.018, 0.018)
            shore.append((W_ * x, H_ * max(0.545, min(0.625, y))))
        d.polygon(shore + [(W_, H_ * 0.66), (0, H_ * 0.66)], fill=hexc("#282836"))
    shore = layer(_shore)

    def _water(d, W_, H_):
        d.rectangle([0, H_ * 0.60, W_, H_], fill=hexc("#20303F"))
    water = layer(_water)

    def _glints(d, W_, H_):
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
    glints = layer(_glints)

    return [(sky, 0.00), (shore, 0.34), (water, 0.58), (glints, 0.86)], \
           (lambda t: Particles("dust", 26, 71, (0, H * 0.55, W, H), (1, 3), (6, 16), (255, 220, 180), alpha=(25, 80))), \
           hexc("#141C28")


SCENES = [sc_window, sc_rain, sc_letter, sc_road, sc_stars, sc_blossom, sc_river]


# ---------------------------------------------------------------- 配乐
def make_music(dur: float, path: Path, sr: int = 44100) -> Path:
    """合成一段安静的环境乐：Pad 铺底 + 钢琴式琶音 + 简单混响。"""
    n = int(dur * sr)
    t = np.arange(n) / sr
    mix = np.zeros(n, dtype=np.float32)

    # 和弦进行（Am - F - C - G），每 4.2 秒一个
    chords = [(220.00, 261.63, 329.63), (174.61, 220.00, 261.63),
              (130.81, 164.81, 196.00), (196.00, 246.94, 293.66)]
    seg = 4.2
    for i in range(int(math.ceil(dur / seg))):
        s0, s1 = i * seg, min(dur, (i + 1) * seg)
        if s1 <= s0:
            break
        idx0, idx1 = int(s0 * sr), int(s1 * sr)
        tt = t[idx0:idx1] - s0
        env = np.minimum(1.0, tt / 1.6) * np.minimum(1.0, (s1 - s0 - tt) / 1.2 + 0.15)
        env = np.clip(env, 0, 1) ** 1.4
        ch = chords[i % len(chords)]
        pad = np.zeros_like(tt)
        for f in ch:
            for d in (0.996, 1.0, 1.004):
                pad += np.sin(2 * np.pi * f * d * tt + d) * 0.33
        # 低八度加厚
        pad += np.sin(2 * np.pi * ch[0] / 2 * tt) * 0.35
        mix[idx0:idx1] += pad * env * 0.10

        # 琶音：每 0.7 秒一个音，指数衰减
        k = 0
        while k * 0.7 < (s1 - s0):
            st = s0 + k * 0.7
            if st >= dur:
                break
            f = ch[k % len(ch)] * 2
            b0 = int(st * sr)
            dur_n = min(int(2.2 * sr), n - b0)
            if dur_n > 0:
                tn = np.arange(dur_n) / sr
                tone = (np.sin(2 * np.pi * f * tn) * 1.0
                        + np.sin(2 * np.pi * f * 2 * tn) * 0.28
                        + np.sin(2 * np.pi * f * 3 * tn) * 0.12)
                envn = np.exp(-tn * 2.6) * np.minimum(1.0, tn / 0.012)
                mix[b0:b0 + dur_n] += tone * envn * 0.055
            k += 1

    # 简单混响：四路延迟叠加
    rev = mix.copy()
    for dly, g in ((0.13, 0.32), (0.21, 0.22), (0.34, 0.14), (0.55, 0.08)):
        d0 = int(dly * sr)
        rev[d0:] += mix[:-d0] * g
    mix = rev

    # 轻微低通（滑动平均），去掉刺耳的高频
    k = 9
    ker = np.ones(k, dtype=np.float32) / k
    mix = np.convolve(mix, ker, mode="same").astype(np.float32)

    peak = np.max(np.abs(mix)) or 1.0
    mix = mix / peak * 0.70
    # 首尾淡入淡出
    fade = int(0.8 * sr)
    mix[:fade] *= np.linspace(0, 1, fade)
    mix[-fade:] *= np.linspace(1, 0, fade)

    pcm = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    stereo = np.stack([pcm, pcm], axis=1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(stereo.tobytes())
    return path


# ---------------------------------------------------------------- 渲染
def render(text_path: Path, out: Path, fps: int = 24, per: float = 4.6,
           with_audio: bool = True) -> Path:
    lines = [ln.strip() for ln in text_path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]

    specs = []
    for i, ln in enumerate(lines):
        layers, pfn, fadec = SCENES[i % len(SCENES)]()
        specs.append({"layers": layers, "pfn": pfn, "fadec": fadec, "sub": sub_layer(ln)})

    total = len(lines) * per + 1.0
    frames = int(total * fps)

    tmp_v = out.with_suffix(".video.mp4")
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", str(tmp_v)], stdin=subprocess.PIPE)

    cur_idx = -1
    baked = None
    baked_n = 0
    fog_cache = {}
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

    t0 = time.perf_counter()
    for i in range(frames):
        t = i / fps
        idx = min(int(t // per), len(lines) - 1)
        lt = t - idx * per

        if idx != cur_idx:
            cur_idx = idx
            spec = specs[idx]
            spec["imgs"] = [ly for ly, _ in spec["layers"]]
            spec["delays"] = [d for _, d in spec["layers"]]
            baked = Image.new("RGBA", (BIG_W, BIG_H), (0, 0, 0, 255))
            baked_n = 0
            if idx not in fog_cache:
                fog_cache[idx] = fog_layer(W, H, 13)
            spec["fog"] = fog_cache[idx]

        spec = specs[idx]
        imgs, delays = spec["imgs"], spec["delays"]

        # 已完成的图层烘进底图
        while baked_n < len(imgs) and lt >= delays[baked_n] + 0.75:
            baked.alpha_composite(imgs[baked_n], (PAD, PAD))
            baked_n += 1

        canvas = baked.copy()
        for k in range(baked_n, len(imgs)):
            p = (lt - delays[k]) / 0.75
            if p <= 0:
                continue
            a = min(1.0, p) ** 1.4
            ly = imgs[k]
            if a < 0.995:
                ly = ly.copy()
                ly.putalpha(ly.getchannel("A").point(lambda v: int(v * a)))
            dy = int((1 - min(1.0, p)) * 26)
            canvas.alpha_composite(ly, (PAD, PAD + dy))

        # 镜头推进
        p2 = lt / per
        z = 1.0 - 0.055 * p2
        cw, ch = W * z, H * z
        cx = PAD + (W - cw) / 2 + 22 * math.sin(p2 * 1.5)
        cy = PAD + (H - ch) / 2 - 10 * p2
        frame = canvas.crop((int(cx), int(cy), int(cx + cw), int(cy + ch))).resize((W, H), Image.BILINEAR)

        # 雾 + 粒子
        fog = spec["fog"]
        fx = int(-W * 0.25 + 60 * math.sin(t * 0.12))
        frame.paste(fog, (fx, int(H * 0.48)), fog)
        spec["pfn"](t).draw(frame, t)

        # 字幕（所有图层都落位后才出）
        last_delay = max(delays)
        if lt > last_delay + 0.45 and lt < per - 0.35:
            al = min(1.0, (lt - last_delay - 0.45) / 0.4) * min(1.0, (per - 0.35 - lt) / 0.4)
            frame.paste(scrim, (0, H - 240), scrim)
            s = spec["sub"].copy()
            if al < 0.99:
                s.putalpha(s.getchannel("A").point(lambda v: int(v * al)))
            frame.paste(s, ((W - s.width) // 2, H - 148), s)

        arr = np.asarray(frame.convert("RGB"), dtype=np.float32)
        arr *= vig
        arr = 255.0 * np.power(np.clip(arr / 255.0, 0, 1), 0.92)
        arr += grain

        # 场景切换：短暂压黑
        edge = min(lt, per - lt)
        if edge < 0.18:
            arr *= 0.30 + 0.70 * (edge / 0.18)
        if t > total - 0.9:
            arr *= max(0.0, (total - t) / 0.9)

        np.clip(arr, 0, 255, out=arr)
        np.copyto(u8, arr, casting="unsafe")
        proc.stdin.write(u8.tobytes())

    proc.stdin.close()
    proc.wait()

    if with_audio:
        wav = out.with_suffix(".wav")
        make_music(total, wav)
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp_v), "-i", str(wav),
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True)
        tmp_v.unlink(missing_ok=True)
        wav.unlink(missing_ok=True)
    else:
        tmp_v.replace(out)

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
        layers, pfn, fadec = SCENES[i % len(SCENES)]()
        canvas = Image.new("RGBA", (BIG_W, BIG_H), (0, 0, 0, 255))
        for ly, _ in layers:
            canvas.alpha_composite(ly, (PAD, PAD))
        frame = canvas.crop((PAD, PAD, PAD + W, PAD + H)).convert("RGB")
        pfn(2.0).draw(frame, 2.0)
        s = sub_layer(ln)
        frame.paste(s, ((W - s.width) // 2, H - 148), s)
        frame.save(outdir / f"l{i + 1}.jpg", quality=93)
        print(" ", outdir / f"l{i + 1}.jpg")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--per", type=float, default=4.6)
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--stills")
    a = ap.parse_args()
    if a.stills:
        stills(Path(a.text), Path(a.stills))
    else:
        render(Path(a.text), Path(a.out), a.fps, a.per, not a.no_audio)


if __name__ == "__main__":
    main()
