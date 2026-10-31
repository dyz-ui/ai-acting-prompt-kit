"""风格化歌词片：多风格 × 多转场

每句歌词换一种视觉风格，句与句之间用不同转场连接。
纯 PIL + numpy 绘制，不依赖 AI 模型。

    python scripts/lyric_styles.py <文本> <输出.mp4>
    python scripts/lyric_styles.py <文本> --stills out/styles    # 只出静帧
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

SS = 2
W, H = 1920, 1080

F_HEI = "C:/Windows/Fonts/msyhbd.ttc"    # 雅黑粗
F_SONG = "C:/Windows/Fonts/simsun.ttc"   # 宋体
F_KAI = "C:/Windows/Fonts/simkai.ttf"    # 楷体

INK = (17, 17, 17)
PAPER = (242, 240, 235)
BLUE = (31, 79, 216)
ORANGE = (240, 90, 40)
CYAN = (111, 227, 255)
NAVY = (18, 58, 107)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    for p in (path, "C:/Windows/Fonts/msyh.ttc"):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def text_layer(text: str, f, color, spacing: int = 6) -> Tuple[np.ndarray, np.ndarray]:
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    w = int(sum(probe.textlength(c, font=f) + spacing for c in text) - spacing) + 8
    asc, desc = f.getmetrics()
    h = asc + desc + 10
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    x = 4
    for c in text:
        d.text((x, 4), c, font=f, fill=color + (255,))
        x += d.textlength(c, font=f) + spacing
    a = np.asarray(img, dtype=np.float32)
    return a[:, :, :3], a[:, :, 3:4] / 255.0


def paste_text(frame: np.ndarray, rgb, alpha, x: int, y: int, a: float = 1.0) -> None:
    if a <= 0:
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


def build_bg(draw_fn, w=W, h=H) -> Image.Image:
    img = Image.new("RGB", (w * SS, h * SS), (255, 255, 255))
    d = ImageDraw.Draw(img)
    draw_fn(d, w * SS, h * SS)
    return img.resize((w, h), Image.LANCZOS)


def to_font_size_for(text: str, f_path: str, size: int, max_w: float) -> ImageFont.FreeTypeFont:
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    while size > 34:
        f = font(f_path, size)
        w = sum(probe.textlength(c, font=f) + 6 for c in text) - 6
        if w <= max_w:
            return f
        size -= 2
    return font(f_path, size)


# ---------------------------------------------------------------- 5 种风格
def style_swiss(text: str):
    """瑞士国际主义：米白网格 + 黑体大字 + 一个红方块。"""
    def draw(d, w, h):
        d.rectangle([0, 0, w, h], fill=PAPER)
        for x in range(0, w, int(w / 16)):
            d.line([(x, 0), (x, h)], fill=(211, 205, 193), width=2)
        for y in range(0, h, int(h / 9)):
            d.line([(0, y), (w, y)], fill=(211, 205, 193), width=2)
        d.rectangle([w * 0.083, h * 0.155, w * 0.083 + w * 0.021, h * 0.155 + w * 0.021], fill=ORANGE)

    bg = build_bg(draw)
    f = to_font_size_for(text, F_HEI, 132, W * 0.88)
    rgb, a = text_layer(text, f, INK, spacing=4)
    return bg, rgb, a, 160, int(H * 0.46), "瑞士网格"


def style_riso(text: str):
    """孔版双色：蓝橙错位套印 + 网点。"""
    def draw(d, w, h):
        d.rectangle([0, 0, w, h], fill=(245, 239, 224))
        r = w * 0.0011
        for yy in range(0, h, int(w * 0.0075)):
            for xx in range(0, w, int(w * 0.0075)):
                d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=(224, 214, 192))

    bg = build_bg(draw)
    f = to_font_size_for(text, F_SONG, 130, W * 0.82)
    rgb_b, a_b = text_layer(text, f, BLUE, spacing=6)
    rgb_o, a_o = text_layer(text, f, ORANGE, spacing=6)
    # 用蓝色层做主体，橙色层错位叠印（孔版印刷的特征就是错位处颜色加深）
    return bg, rgb_b, a_b, 200, int(H * 0.45), "孔版双色", (rgb_o, a_o * 0.72, 13, 10)


def style_neon(text: str):
    """霓虹：深底 + 青光辉。"""
    def draw(d, w, h):
        d.rectangle([0, 0, w, h], fill=(10, 10, 18))
        for i in range(0, h, 4):
            v = int(6 + 6 * (i / h))
            d.line([(0, i), (w, i)], fill=(v, v, v + 4))

    bg = build_bg(draw)
    f = to_font_size_for(text, F_HEI, 110, W * 0.82)
    rgb, a = text_layer(text, f, CYAN, spacing=8)

    # 辉光：alpha 四周留出余量再模糊，否则边缘会露出一个方块
    pad = 90
    hh, ww = a.shape[0], a.shape[1]
    H2, W2 = hh + pad * 2, ww + pad * 2
    ap = np.zeros((H2, W2), dtype=np.float32)
    ap[pad:pad + hh, pad:pad + ww] = a[:, :, 0]
    blurred = Image.fromarray((ap * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(20))
    ga = (np.asarray(blurred, dtype=np.float32) / 255.0)[:, :, None] * 0.85
    grgb = np.broadcast_to(np.array(CYAN, dtype=np.float32), (H2, W2, 3))
    return bg, rgb, a, 200, int(H * 0.46), "霓虹", (grgb, ga, -pad, -pad)


def style_blueprint(text: str):
    """蓝图：深蓝底 + 白网格 + 技术标注。"""
    def draw(d, w, h):
        d.rectangle([0, 0, w, h], fill=NAVY)
        step = int(w / 20)
        for x in range(0, w, step):
            d.line([(x, 0), (x, h)], fill=(24, 66, 116), width=2)
        for y in range(0, h, step):
            d.line([(0, y), (w, y)], fill=(24, 66, 116), width=2)
        # 四角标记
        m = int(w * 0.03)
        for (cx, cy, dx, dy) in [(m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1)]:
            d.line([(cx, cy), (cx + dx * w * 0.04, cy)], fill=(150, 200, 255), width=2)
            d.line([(cx, cy), (cx, cy + dy * h * 0.06)], fill=(150, 200, 255), width=2)

    bg = build_bg(draw)
    f = to_font_size_for(text, F_HEI, 96, W * 0.78)
    rgb, a = text_layer(text, f, (232, 242, 255), spacing=14)
    return bg, rgb, a, 240, int(H * 0.44), "蓝图"


def style_halftone(text: str):
    """半调：白底网点 + 黑色横排大字 + 色带。"""
    def draw(d, w, h):
        d.rectangle([0, 0, w, h], fill=(250, 248, 244))
        cx, cy = w * 0.35, h * 0.42
        maxd = math.hypot(w * 0.75, h * 0.75)
        step = int(w * 0.0082)
        for yy in range(0, h, step):
            for xx in range(0, w, step):
                dist = math.hypot(xx - cx, yy - cy) / maxd
                r = (0.62 - 0.42 * dist) * step * 0.5
                if r > 0.5:
                    d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=(206, 199, 188))
        d.rectangle([0, h * 0.858, w, h * 0.872], fill=ORANGE)

    bg = build_bg(draw)
    f = to_font_size_for(text, F_HEI, 108, W * 0.80)
    rgb, a = text_layer(text, f, INK, spacing=2)
    return bg, rgb, a, 170, int(H * 0.38), "半调"


STYLES: List[Callable] = [style_swiss, style_riso, style_neon, style_blueprint, style_halftone]


# ---------------------------------------------------------------- 转场遮罩
def mask_fade(t: float, w: int, h: int) -> np.ndarray:
    """交叉溶解：整屏均匀过渡。"""
    return np.full((h, w, 1), np.float32(t), dtype=np.float32)


def mask_wipe(t: float, w: int, h: int) -> np.ndarray:
    """横向擦除：硬边界 + 40px 柔边，显式切片实现，不做广播。"""
    m = np.zeros((h, w, 1), dtype=np.float32)
    soft = 40
    cut = int(t * (w + soft)) - soft
    solid = max(0, min(w, cut))
    if solid:
        m[:, :solid, :] = 1.0
    if 0 <= cut < w - soft:
        ramp = np.linspace(1.0, 0.0, soft, dtype=np.float32)[None, :, None]
        m[:, cut:cut + soft, :] = np.broadcast_to(ramp, (h, soft, 1))
    return m


def mask_push(t: float, w: int, h: int) -> np.ndarray:
    """上下分屏推入：上半先走，下半后跟。"""
    m = np.zeros((h, w, 1), dtype=np.float32)
    half = h // 2
    top = min(1.0, t / 0.62)
    bot = min(1.0, max(0.0, (t - 0.22) / 0.62))
    m[:half, :, :] = top
    m[half:, :, :] = bot
    return m


MASKS = [mask_fade, mask_wipe, mask_push]


def ease(x: float) -> float:
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- 渲染
def render(text_path: Path, out: Path, fps: int = 24, per: float = 3.2,
           trans: float = 0.7) -> Path:
    lines = [ln.strip() for ln in text_path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln and not ln.startswith("#")]

    built = []
    for i, ln in enumerate(lines):
        res = STYLES[i % len(STYLES)](ln)
        bg, rgb, a, x, y = res[0], res[1], res[2], res[3], res[4]
        glow = res[6] if len(res) > 6 else None
        built.append((bg, rgb, a, x, y, glow))

    total = len(lines) * per
    frames = int(total * fps)
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "21",
           "-pix_fmt", "yuv420p", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    base = [np.array(b[0], dtype=np.float32) for b in built]
    u8 = np.empty((H, W, 3), dtype=np.uint8)
    rng = np.random.default_rng(3)
    grain = rng.normal(0, 2.2, (H, W, 1)).astype(np.float32)

    t0 = time.perf_counter()
    for i in range(frames):
        t = i / fps
        idx = min(int(t // per), len(lines) - 1)
        local = t - idx * per

        def draw_text_on(f: np.ndarray, k: int, alpha: float, dy: int = 0) -> None:
            """文字独立成层：不参与背景遮罩，永远不会被切。"""
            if alpha <= 0.004:
                return
            bg, rgb, a, x, y, glow = built[k]
            if glow is not None:
                gdx = glow[2] if len(glow) > 2 else -6
                gdy = glow[3] if len(glow) > 3 else -6
                paste_text(f, glow[0], glow[1], x + gdx, y + gdy + dy, alpha * 0.85)
            paste_text(f, rgb, a, x, y + dy, alpha)

        # 转场：遮罩只作用于背景，文字独立淡入。
        # 结构性转场（擦除/竖条/百叶窗）负责气势，文字保持干净完整。
        if idx > 0 and local < trans:
            p = ease(local / trans)
            kind = (idx - 1) % len(MASKS)
            m = MASKS[kind](p, W, H)
            f = base[idx - 1] * (1 - m) + base[idx] * m
            ain_t = ease(min(1.0, max(0.0, (p - 0.32) / 0.50)))
            draw_text_on(f, idx, ain_t, dy=int((1 - ain_t) * 14))
            cur = f
        else:
            cur = base[idx].copy()
            ain = min(1.0, local / 0.55)
            aout = min(1.0, max(0.0, (per - local) / 0.45))
            draw_text_on(cur, idx, max(0.0, min(ain, aout)), dy=int((1 - ain) * 16))

        cur += grain
        np.clip(cur, 0, 255, out=cur)
        np.copyto(u8, cur, casting="unsafe")
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
        res = STYLES[i % len(STYLES)](ln)
        bg, rgb, a, x, y = res[0], res[1], res[2], res[3], res[4]
        glow = res[6] if len(res) > 6 else None
        arr = np.array(bg, dtype=np.float32)
        if glow is not None:
            gdx = glow[2] if len(glow) > 2 else -6
            gdy = glow[3] if len(glow) > 3 else -6
            paste_text(arr, glow[0], glow[1], x + gdx, y + gdy, 0.85)
        paste_text(arr, rgb, a, x, y, 1.0)
        Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(outdir / f"s{i + 1}.jpg", quality=93)
        print(" ", outdir / f"s{i + 1}.jpg", res[5])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("text")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--fps", type=int, default=24)
    ap.add_argument("--per", type=float, default=3.2)
    ap.add_argument("--trans", type=float, default=0.7)
    ap.add_argument("--stills")
    a = ap.parse_args()
    if a.stills:
        stills(Path(a.text), Path(a.stills))
    else:
        render(Path(a.text), Path(a.out), a.fps, a.per, a.trans)


if __name__ == "__main__":
    main()
