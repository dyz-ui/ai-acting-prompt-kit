"""八维描述 → 代码视频

读一份 codevideo.yml（每个节拍按八维填），映射成画面参数并渲染成片。
八个维度不是给演员的，而是给导演的：每一维都对应一个可以拧的旋钮。

    python scripts/render_codevideo.py story.yml out.mp4
"""
from __future__ import annotations

import argparse
import math
import subprocess
import time
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFont

from lyric_cinema import fog_layer
from lyric_layers import BIG_H, BIG_W, H, PAD, SCENES, W, make_music

F_KAI = "C:/Windows/Fonts/simkai.ttf"
F_HEI = "C:/Windows/Fonts/msyh.ttc"

# 情绪词 → 色。八维里的"情绪 A → B"直接变成画面色调的起止。
EMO_COLOR = {
    "安静": (42, 51, 72), "平静": (48, 58, 78), "冷": (60, 74, 102),
    "压抑": (26, 20, 24), "孤独": (30, 34, 50), "疲惫": (44, 40, 38),
    "辽阔": (233, 185, 140), "温暖": (242, 201, 160), "温柔": (240, 210, 180),
    "明亮": (250, 236, 210), "希望": (245, 214, 170),
    "紧张": (150, 60, 50), "愤怒": (193, 68, 58), "爆发": (200, 70, 50),
    "悲伤": (70, 64, 78), "释然": (150, 160, 170), "怀念": (196, 160, 120),
}

# 场景关键词 → SCENES 索引
SCENE_KEY = [
    (("窗", "夜", "月"), 0),
    (("雨", "窗", "等"), 1),
    (("信", "笔", "字", "写"), 2),
    (("路", "远方", "走", "出"), 3),
    (("星", "天空", "梦", "仰望"), 4),
    (("花", "春", "开", "落"), 5),
    (("江", "河", "水", "流"), 6),
]


def pick_scene(beat: dict, fallback: int) -> int:
    """按 scene → line → purpose 的优先级匹配，避免"夜里"抢走"窗"这类串味。"""
    for field in ("scene", "line", "purpose"):
        txt = str(beat.get(field) or "")
        if not txt:
            continue
        for keys, idx in SCENE_KEY:
            if any(k in txt for k in keys):
                return idx
    return fallback % len(SCENES)


def emo_pair(s: str):
    parts = [p.strip() for p in str(s).replace("->", "→").split("→") if p.strip()]
    a = EMO_COLOR.get(parts[0], (40, 48, 66)) if parts else (40, 48, 66)
    b = EMO_COLOR.get(parts[-1], (230, 190, 150)) if parts else (230, 190, 150)
    return np.array(a, np.float32), np.array(b, np.float32)


def font(path, size):
    for p in (path, F_HEI):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def subtitle(line: str, trigger: str, accent=(233, 168, 96)):
    """字幕：触发词用强调色标出来——八维里的"触发词"落到画面就是这个。"""
    f = font(F_KAI, 46)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    widths = [probe.textlength(c, font=f) for c in line]
    total = int(sum(widths) + 3 * (len(line) - 1)) + 40
    img = Image.new("RGBA", (total, 92), (0, 0, 0, 0))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ds = ImageDraw.Draw(shadow)

    trig_range = None
    if trigger:
        pos = line.find(trigger)
        if pos >= 0:
            trig_range = (pos, pos + len(trigger))

    x = 20
    for i, ch in enumerate(line):
        col = accent if (trig_range and trig_range[0] <= i < trig_range[1]) else (245, 243, 238)
        d.text((x, 6), ch, font=f, fill=col + (240,))
        ds.text((x + 2, 8), ch, font=f, fill=(0, 0, 0, 160))
        x += widths[i] + 3

    from PIL import ImageFilter
    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(shadow)
    out.alpha_composite(img)
    return out


def render(yml_path: Path, out: Path) -> Path:
    cfg = yaml.safe_load(yml_path.read_text(encoding="utf-8"))
    fps = int(cfg.get("fps", 24))
    beats = cfg["beats"]
    if not beats:
        raise SystemExit("beats 为空")

    # 时间：优先用 time，否则按 dur 累积
    t = 0.0
    segs = []
    for i, b in enumerate(beats):
        if "time" in b:
            a, e = float(b["time"][0]), float(b["time"][1])
        else:
            a, e = t, t + float(b.get("dur", 4.5))
        t = e
        scene_idx = pick_scene(b, i)
        segs.append({
            "start": a, "end": e, "idx": scene_idx,
            "line": b.get("line", "") or b.get("trigger", ""),
            "trigger": b.get("trigger", ""),
            "emo": emo_pair(b.get("emotion", "")),
            "comp": b.get("composition", ""),
            "sub": subtitle(b.get("line", "") or b.get("trigger", ""), b.get("trigger", "")),
        })

    total = segs[-1]["end"] - segs[0]["start"]
    t0 = segs[0]["start"]
    frames = int(total * fps)

    built = []
    for s in segs:
        layers, pfn, fadec = SCENES[s["idx"]]()
        built.append({"layers": layers, "pfn": pfn,
                      "imgs": [ly for ly, _ in layers],
                      "delays": [d for _, d in layers]})

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
    fog = fog_layer(W, H, 12)

    cur, baked, baked_n = -1, None, 0
    st = time.perf_counter()
    for i in range(frames):
        tt = i / fps
        k = len(segs) - 1
        for j, s in enumerate(segs):
            if s["start"] <= tt + t0 < s["end"]:
                k = j
                break
        s = segs[k]
        dur = s["end"] - s["start"]
        lt = tt + t0 - s["start"]
        p2 = lt / max(0.1, dur)

        if k != cur:
            cur = k
            baked = Image.new("RGBA", (BIG_W, BIG_H), (0, 0, 0, 255))
            baked_n = 0
            scale = 1.0 if dur >= 3.0 else max(0.45, dur / 3.0)

        bp = built[k]
        delays = [d * scale for d in bp["delays"]]
        while baked_n < len(bp["imgs"]) and lt >= delays[baked_n] + 0.75:
            baked.alpha_composite(bp["imgs"][baked_n], (PAD, PAD))
            baked_n += 1

        canvas = baked.copy()
        for q in range(baked_n, len(bp["imgs"])):
            pp = (lt - delays[q]) / 0.75
            if pp <= 0:
                continue
            a = min(1.0, pp) ** 1.4
            ly = bp["imgs"][q]
            if a < 0.995:
                ly = ly.copy()
                ly.putalpha(ly.getchannel("A").point(lambda v: int(v * a)))
            canvas.alpha_composite(ly, (PAD, PAD + int((1 - min(1.0, pp)) * 26)))

        z = 1.0 - 0.055 * p2
        cw, ch = W * z, H * z
        cx = PAD + (W - cw) / 2 + 20 * math.sin(p2 * 1.4)
        cy = PAD + (H - ch) / 2 - 10 * p2
        frame = canvas.crop((int(cx), int(cy), int(cx + cw), int(cy + ch))).resize((W, H), Image.BILINEAR)

        fx = int(-W * 0.25 + 60 * math.sin(tt * 0.12))
        frame.paste(fog, (fx, int(H * 0.48)), fog)
        bp["pfn"](tt).draw(frame, tt)

        # 八维 · 情绪 A→B：整段的色调从 A 漂到 B
        colA, colB = s["emo"]
        arr = np.asarray(frame.convert("RGB"), dtype=np.float32)
        tint = colA * (1 - p2) + colB * p2
        arr = arr * 0.80 + tint * 0.20

        # 字幕（触发词高亮）
        show_from = max(delays) + 0.35
        if show_from < lt < dur - 0.3 and s["sub"] is not None:
            al = min(1.0, (lt - show_from) / 0.4) * min(1.0, (dur - 0.3 - lt) / 0.4)
            frame2 = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
            frame2.paste(scrim, (0, H - 240), scrim)
            sub = s["sub"].copy()
            if al < 0.99:
                sub.putalpha(sub.getchannel("A").point(lambda v: int(v * al)))
            frame2.paste(sub, ((W - sub.width) // 2, H - 148), sub)
            arr = np.asarray(frame2, dtype=np.float32)

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

    wav = out.with_suffix(".wav")
    make_music(total, wav)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(tmp_v), "-i", str(wav),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(out)], check=True)
    tmp_v.unlink(missing_ok=True)
    wav.unlink(missing_ok=True)

    dt = time.perf_counter() - st
    print(f"节拍    : {len(segs)}")
    print(f"时长    : {total:.1f}s ({frames} 帧)")
    print(f"耗时    : {dt:.1f}s  {frames / dt:.1f} fps")
    print(f"输出    : {out}  {out.stat().st_size / 1024 / 1024:.1f} MB")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("out")
    a = ap.parse_args()
    render(Path(a.story), Path(a.out))


if __name__ == "__main__":
    main()
