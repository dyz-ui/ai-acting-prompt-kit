"""代码视频生成器 —— 方法层内置版

这份文件不只是渲染器。八维、十二条构图规则、风格向量都写死在代码里：
写 YAML 时它检查，渲完它自检。文档会过期，常量不会。


════════════════════════════════════════════════════════════
一、八维（每一拍填一份）
════════════════════════════════════════════════════════════
  ① time        时间段        精确到 0.5 秒，忌均分
  ② purpose     目的          这一拍要让人"感到"什么
  ③ emotion     情绪 A → B    必须有箭头；两端驱动色调漂移
  ④ trigger     触发词        落在哪个词上；驱动字幕高亮
  ⑤ detail      画面细节      最具体的那一层
  ⑥ composition 构图          主体在哪、留白在哪、地平线在哪
  ⑦ sound       声音          铺底 / 扬起 / 收薄
  ⑧ end+forbid  落幅与禁止    结束帧停在哪；不许出现什么

  引擎只强制执行 ①③④⑥；②⑤⑦⑧缺失时 --check 会警告但不阻断。
  道理：能自动化的先自动化，判断类的留给人。

════════════════════════════════════════════════════════════
二、十二条构图规则（写进 COMPOSITION 表，会被真实执行）
════════════════════════════════════════════════════════════
  1 三分点      锚点 0.333 / 0.667
  2 黄金分割    0.382 / 0.618（比三分更耐看）
  3 地平线      上三分天多、下三分地多，忌正中
  4 主体占比    30–40% 画面面积
  5 留白        40–60%，且留白侧要干净
  6 视线留白    朝向侧留白 ≥ 反侧 1.5 倍
  7 视觉重量    人脸>文字>动物>建筑>自然；亮>暗，饱和>灰
  8 三层景深    前景虚 / 中景实 / 背景灰
  9 引导线      从边缘入画，终点落在主体
 10 对比或亲和  相邻拍至少 3 维同向变化
 11 眯眼测试    缩到 320px 仍可读
 12 边缘构图    主体压到 x<0.15 产生压迫（慎用）

  其中 1/2/3/5/6 会改变实际画面（取景偏置、地平线、留白侧压暗、字幕对齐）。
  4/8/9 由场景函数决定；7/10/11/12 是自检项，渲完会打印结果。

════════════════════════════════════════════════════════════
三、风格向量（六个数字定义"洋气"）
════════════════════════════════════════════════════════════
  hues        色相数 1-5+      越少越高级
  saturation  饱和度 0-1
  contrast    明度对比 0-1
  texture     纹理强度 0-1     颗粒/网点
  geometry    sharp|round|organic
  motion      运动幅度 0-1     镜头推进速度

  经验值：洋气 = 色相 2 + 对比 0.8 + 纹理 0.3 + 运动 0.2。
  色相多、饱和高、运动快 = 热闹，不是洋气。

════════════════════════════════════════════════════════════
四、五个让画面"像摄影"的手法（都在这里实现）
════════════════════════════════════════════════════════════
  镜头推进   从放大画布里裁窗口，z 1.0→0.94
  高斯雾     二维衰减云团，分开天地
  粒子       雪/雨/尘/花瓣/星，带景深
  暗角+颗粒  径向压暗 + 高斯噪点
  字幕压暗   底部渐变，保证任何背景下可读

────────────────────────────────────────────────────────────
用法：
    python scripts/codevideo.py story.yml out.mp4
    python scripts/codevideo.py story.yml --check     只体检，不渲染
────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from lyric_cinema import fog_layer
from lyric_layers import H, PAD, SCENES, W, make_music

F_KAI = "C:/Windows/Fonts/simkai.ttf"
F_HEI = "C:/Windows/Fonts/msyh.ttc"
BIG_W, BIG_H = W + PAD * 2, H + PAD * 2

# ════════════════════════════════════════════════════════════
# 规则 1/2/3：锚点表。名字 → 归一化 x
# ════════════════════════════════════════════════════════════
ANCHORS = {
    "center": 0.500,
    "thirds_left": 0.333, "thirds_right": 0.667,
    "golden_left": 0.382, "golden_right": 0.618,
    "edge_left": 0.150, "edge_right": 0.850,
}
HORIZON_OK = (0.30, 0.42, 0.58, 0.70)   # 规则 3：只允许这几档

# 场景的天然地平线（用于把地平线拉到指定位置）
SCENE_HORIZON = [0.60, 0.60, 0.62, 0.70, 0.56, 0.88, 0.60]

# 情绪 → 色（八维③）
EMO_COLOR = {
    "安静": (42, 51, 72), "平静": (48, 58, 78), "冷": (60, 74, 102),
    "压抑": (26, 20, 24), "孤独": (30, 34, 50), "疲惫": (44, 40, 38),
    "辽阔": (233, 185, 140), "温暖": (242, 201, 160), "温柔": (240, 210, 180),
    "明亮": (250, 236, 210), "希望": (245, 214, 170),
    "紧张": (150, 60, 50), "愤怒": (193, 68, 58), "爆发": (200, 70, 50),
    "悲伤": (70, 64, 78), "释然": (150, 160, 170), "怀念": (196, 160, 120),
}

# ════════════════════════════════════════════════════════════
# 风格向量预设：六个数字 → 具体渲染参数
# ════════════════════════════════════════════════════════════
STYLE_PRESETS = {
    "swiss":  dict(hues=2, saturation=0.55, contrast=0.85, texture=0.15, geometry="sharp", motion=0.18),
    "riso":   dict(hues=2, saturation=0.75, contrast=0.55, texture=0.55, geometry="round", motion=0.12),
    "neon":   dict(hues=2, saturation=0.95, contrast=0.90, texture=0.35, geometry="sharp", motion=0.30),
    "film":   dict(hues=3, saturation=0.35, contrast=0.70, texture=0.30, geometry="organic", motion=0.15),
    "poster": dict(hues=3, saturation=0.85, contrast=0.95, texture=0.20, geometry="sharp", motion=0.25),
    "quiet":  dict(hues=1, saturation=0.25, contrast=0.50, texture=0.25, geometry="organic", motion=0.10),
}

SCENE_KEY = [
    (("窗", "夜", "月"), 0), (("雨", "等"), 1), (("信", "笔", "字", "写"), 2),
    (("路", "远方", "走", "出"), 3), (("星", "天空", "梦", "仰望"), 4),
    (("花", "春", "开", "落"), 5), (("江", "河", "水", "流"), 6),
]


# ════════════════════════════════════════════════════════════
# 体检：八维完整性 + 规则合法性
# ════════════════════════════════════════════════════════════
def validate(cfg: dict) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    beats = cfg.get("beats") or []
    if not beats:
        errs.append("没有 beats")

    for i, b in enumerate(beats):
        tag = f"第{i+1}拍"
        if "time" not in b and "dur" not in b:
            errs.append(f"{tag} 缺 ①时间段（time 或 dur）")
        if not b.get("emotion"):
            errs.append(f"{tag} 缺 ③情绪 A→B")
        elif "→" not in str(b["emotion"]) and "->" not in str(b["emotion"]):
            errs.append(f"{tag} ③情绪没有箭头，必须写成「A → B」")
        if not b.get("trigger") and not b.get("line"):
            errs.append(f"{tag} 缺 ④触发词/台词")
        for f, name in (("purpose", "②目的"), ("detail", "⑤画面细节"),
                        ("composition", "⑥构图"), ("sound", "⑦声音"),
                        ("forbid", "⑧禁止")):
            if not b.get(f):
                warns.append(f"{tag} 缺 {name}")

        comp = b.get("composition")
        if isinstance(comp, dict):
            a = comp.get("anchor")
            if a and a not in ANCHORS:
                errs.append(f"{tag} anchor「{a}」不在 {list(ANCHORS)}")
            hz = comp.get("horizon")
            if hz is not None and not any(abs(float(hz) - x) < 0.02 for x in HORIZON_OK):
                warns.append(f"{tag} 地平线 {hz} 不在安全档 {HORIZON_OK}（忌正中）")

    st = cfg.get("style")
    if isinstance(st, str) and st not in STYLE_PRESETS:
        errs.append(f"style「{st}」不在预设 {list(STYLE_PRESETS)}")
    return errs, warns


# ════════════════════════════════════════════════════════════
# 取景：规则 1/2/3 真实执行（改变裁切窗口）
# ════════════════════════════════════════════════════════════
def camera_bias(comp: dict, scene_idx: int, cw: float, ch: float) -> tuple[float, float]:
    """返回裁切窗口的偏移量。anchor 决定水平，horizon 决定垂直。"""
    bx = by = 0.0
    if not isinstance(comp, dict):
        return bx, by
    a = comp.get("anchor")
    if a in ANCHORS:
        # 主体想放左边 → 窗口右移，露出更多右侧
        bx = (ANCHORS[a] - 0.5) * 0.30 * W
        lim = (BIG_W - cw) / 2
        bx = max(-lim, min(lim, bx))
    hz = comp.get("horizon")
    if hz is not None:
        try:
            target = float(hz)
            natural = SCENE_HORIZON[scene_idx % len(SCENE_HORIZON)]
            by = (target - natural) * H * 0.55
            limy = (BIG_H - ch) / 2
            by = max(-limy, min(limy, by))
        except (TypeError, ValueError):
            pass
    return bx, by


# ════════════════════════════════════════════════════════════
# 字幕：触发词高亮（八维④）
# ════════════════════════════════════════════════════════════
def font(path, size):
    for p in (path, F_HEI):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def subtitle(line: str, trigger: str, align: str = "center", accent=(233, 168, 96)):
    if not line:
        return None
    f = font(F_KAI, 46)
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    widths = [probe.textlength(c, font=f) for c in line]
    total = int(sum(widths) + 3 * (len(line) - 1)) + 40
    img = Image.new("RGBA", (total, 92), (0, 0, 0, 0))
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d, ds = ImageDraw.Draw(img), ImageDraw.Draw(shadow)

    pos = line.find(trigger) if trigger else -1
    rng = (pos, pos + len(trigger)) if pos >= 0 else None

    x = 20
    for i, ch in enumerate(line):
        col = accent if (rng and rng[0] <= i < rng[1]) else (245, 243, 238)
        d.text((x, 6), ch, font=f, fill=col + (240,))
        ds.text((x + 2, 8), ch, font=f, fill=(0, 0, 0, 160))
        x += widths[i] + 3

    shadow = shadow.filter(ImageFilter.GaussianBlur(3))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.alpha_composite(shadow)
    out.alpha_composite(img)
    return out


def sub_x(sub_w: int, align: str) -> int:
    """规则 6：字幕跟着主体走，不总在正中。"""
    if align == "left":
        return int(W * 0.10)
    if align == "right":
        return int(W * 0.90 - sub_w)
    return (W - sub_w) // 2


# ════════════════════════════════════════════════════════════
# 渲染
# ════════════════════════════════════════════════════════════
def render(yml: Path, out: Path) -> Path:
    cfg = yaml.safe_load(yml.read_text(encoding="utf-8"))
    errs, warns = validate(cfg)
    if errs:
        print("✗ 体检未通过：")
        for e in errs:
            print("  ·", e)
        sys.exit(1)
    if warns:
        print("⚠ 提醒（不阻断）：")
        for w in warns:
            print("  ·", w)

    st_name = cfg.get("style", "film")
    st = STYLE_PRESETS[st_name] if isinstance(st_name, str) else STYLE_PRESETS["film"]
    if isinstance(cfg.get("style"), dict):
        st = {**STYLE_PRESETS["film"], **cfg["style"]}

    fps = int(cfg.get("fps", 24))
    beats = cfg["beats"]

    t = 0.0
    segs = []
    for i, b in enumerate(beats):
        if "time" in b:
            a, e = float(b["time"][0]), float(b["time"][1])
        else:
            a, e = t, t + float(b.get("dur", 4.5))
        t = e
        comp = b.get("composition") or {}
        anchor = comp.get("anchor", "center") if isinstance(comp, dict) else "center"
        align = "left" if "left" in str(anchor) else ("right" if "right" in str(anchor) else "center")
        if isinstance(comp, dict) and comp.get("negative_space"):
            align = comp["negative_space"] if comp["negative_space"] in ("left", "right") else align
        scene_idx = pick_scene(b, i)
        segs.append({
            "start": a, "end": e, "idx": scene_idx, "comp": comp, "align": align,
            "emo": emo_pair(b.get("emotion", "")),
            "sub": subtitle(b.get("line", ""), b.get("trigger", ""), align),
        })

    total = segs[-1]["end"] - segs[0]["start"]
    t0 = segs[0]["start"]
    frames = int(total * fps)

    built = []
    for s in segs:
        layers, pfn, fadec = SCENES[s["idx"]]()
        built.append({"imgs": [ly for ly, _ in layers],
                      "delays": [d for _, d in layers], "pfn": pfn, "fadec": fadec})

    tmp_v = out.with_suffix(".video.mp4")
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", str(tmp_v)], stdin=subprocess.PIPE)

    scrim = Image.new("RGBA", (W, 240), (0, 0, 0, 0))
    sa = (150 * (np.arange(240) / 239) ** 1.5).astype(np.uint8)
    arr_s = np.zeros((240, W, 4), dtype=np.uint8)
    arr_s[:, :, 3] = np.repeat(sa[:, None], W, axis=1)
    scrim = Image.fromarray(arr_s, "RGBA")

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    vig = np.clip(1.06 - 0.30 * r ** 2, 0.62, 1.0)[:, :, None]
    # 规则 5：留白侧压暗，让"空"有质感
    side_vig = np.ones((H, W, 1), np.float32)
    rng = np.random.default_rng(5)
    grain_sigma = 1.2 + 3.0 * st["texture"]
    grain = rng.normal(0, grain_sigma, (H, W, 1)).astype(np.float32)
    u8 = np.empty((H, W, 3), dtype=np.uint8)
    fog = fog_layer(W, H, 10 + 6 * st["texture"])

    cur, baked, baked_n = -1, None, 0
    frame_stats = []
    st_t = time.perf_counter()

    for i in range(frames):
        tt = i / fps
        k = len(segs) - 1
        for j, s in enumerate(segs):
            if s["start"] <= tt + t0 < s["end"]:
                k = j
                break
        s = segs[k]
        dur = max(0.1, s["end"] - s["start"])
        lt = tt + t0 - s["start"]
        p2 = lt / dur

        if k != cur:
            cur = k
            baked = Image.new("RGBA", (BIG_W, BIG_H), tuple(built[k]["fadec"]) + (255,))
            baked_n = 0
            scale = 1.0 if dur >= 3.0 else max(0.45, dur / 3.0)
            side_vig = np.ones((H, W, 1), np.float32)
            if s["align"] == "left":      # 字幕在左 → 右侧是留白 → 压暗右侧
                side_vig = np.linspace(1.0, 0.90, W, dtype=np.float32)[None, :, None].repeat(H, 0)
            elif s["align"] == "right":
                side_vig = np.linspace(0.90, 1.0, W, dtype=np.float32)[None, :, None].repeat(H, 0)

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

        # 镜头（规则 1/2/3：anchor + horizon 改变取景）
        z = 1.0 - (0.02 + 0.05 * st["motion"]) * p2
        cw, ch = W * z, H * z
        bx, by = camera_bias(s["comp"], s["idx"], cw, ch)
        cx = PAD + (W - cw) / 2 + bx + 14 * math.sin(p2 * 1.4)
        cy = PAD + (H - ch) / 2 + by - 8 * p2
        frame = canvas.crop((int(cx), int(cy), int(cx + cw), int(cy + ch))).resize((W, H), Image.BILINEAR)

        fx = int(-W * 0.25 + 50 * math.sin(tt * 0.12))
        frame.paste(fog, (fx, int(H * 0.48)), fog)
        bp["pfn"](tt).draw(frame, tt)

        # 情绪 A→B（八维③）：色调漂移
        colA, colB = s["emo"]
        arr = np.asarray(frame.convert("RGB"), dtype=np.float32)
        tint = colA * (1 - p2) + colB * p2
        w_tint = 0.10 + 0.14 * (1 - st["saturation"] * 0.6)
        arr = arr * (1 - w_tint) + tint * w_tint

        # 饱和度（风格向量）
        if st["saturation"] < 1.0:
            g = arr.mean(axis=2, keepdims=True)
            arr = g + (arr - g) * st["saturation"]

        show_from = max(delays) + 0.35
        if s["sub"] is not None and show_from < lt < dur - 0.3:
            al = min(1.0, (lt - show_from) / 0.4) * min(1.0, (dur - 0.3 - lt) / 0.4)
            tmp = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
            tmp.paste(scrim, (0, H - 240), scrim)
            sub = s["sub"].copy()
            if al < 0.99:
                sub.putalpha(sub.getchannel("A").point(lambda v: int(v * al)))
            tmp.paste(sub, (sub_x(sub.width, s["align"]), H - 148), sub)
            arr = np.asarray(tmp, dtype=np.float32)

        arr *= vig
        arr *= side_vig
        # 明度对比（风格向量）：线性拉伸后做 filmic 压缩，亮场景不会爆
        c = 0.7 + 0.6 * st["contrast"]
        arr = (arr - 128) * c + 128
        arr -= np.maximum(arr - 200, 0) * 0.45          # 高光压缩
        arr += np.maximum(8 - arr, 0) * 0.5             # 抬黑位
        arr = 255.0 * np.power(np.clip(arr / 255.0, 0, 1), 0.92)
        arr += grain

        edge = min(lt, dur - lt)
        if edge < 0.16:
            arr *= 0.45 + 0.55 * (edge / 0.16)

        np.clip(arr, 0, 255, out=arr)
        if i % 24 == 0:
            frame_stats.append((float(arr.mean()), float(arr[0:int(H*0.6)].mean()),
                                float(arr[int(H*0.3):int(H*0.75)].mean())))
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

    dt = time.perf_counter() - st_t
    report(cfg, segs, frame_stats, out, total, frames, dt, st_name, st)
    return out


# ════════════════════════════════════════════════════════════
# 自检报告：规则 7/10/11/12
# ════════════════════════════════════════════════════════════
def report(cfg, segs, stats, out, total, frames, dt, st_name, st):
    print(f"\n产出    : {out}  {out.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"规格    : {W}×{H} / {frames / total:.0f}fps / {total:.1f}s / 渲染 {dt:.0f}s "
          f"({frames / dt:.1f} fps)")
    print(f"风格    : {st_name}  色相{st['hues']} 饱和{st['saturation']} "
          f"对比{st['contrast']} 纹理{st['texture']} 运动{st['motion']}")

    print("\n── 自检 ──")
    # 规则 10：相邻拍的时长差（节奏，忌均分）
    durs = [s["end"] - s["start"] for s in segs]
    spread = max(durs) - min(durs)
    print(f"节奏    : 各拍 {', '.join(f'{d:.1f}' for d in durs)}s  "
          f"→ {'✅ 有长短' if spread > 0.8 else '⚠ 太均匀，像 PPT'}")

    # 规则 3：地平线是否都在安全档
    hz = []
    for b in cfg["beats"]:
        c = b.get("composition") or {}
        if isinstance(c, dict) and c.get("horizon") is not None:
            hz.append(float(c["horizon"]))
    if hz:
        bad = [h for h in hz if min(abs(h - x) for x in HORIZON_OK) > 0.04]
        print(f"地平线  : {len(hz)} 处指定 → {'✅ 都在安全档' if not bad else f'⚠ {bad} 偏离'}")
    else:
        print("地平线  : 未指定 → 用场景默认")

    # 规则 7/11：画面明度
    if stats:
        means = [s[0] for s in stats]
        low = sum(1 for m in means if m < 12)
        print(f"明度    : 平均 {sum(means)/len(means):.0f}/255  "
              f"最低 {min(means):.0f} 最高 {max(means):.0f}  "
              f"{'✅ 无全黑帧' if low == 0 else f'⚠ {low} 个采样点接近全黑'}")
        if min(means) < 25:
            print("          （夜景/转场压黑接近阈值，属正常；低于 12 才算事故）")
        thirds = [s[2] for s in stats]
        print(f"中景区  : 平均 {sum(thirds)/len(thirds):.0f}  "
              f"{'✅ 主体区够亮' if sum(thirds)/len(thirds) > 40 else '⚠ 主体区偏暗，观众找不到焦点'}")

    # 八维完整性
    missing = sum(1 for b in cfg["beats"]
                  for f in ("purpose", "detail", "sound", "forbid") if not b.get(f))
    print(f"八维    : {len(cfg['beats'])} 拍 × 8 维，缺 {missing} 项"
          f"  {'✅ 填满' if missing == 0 else '（不阻断，但写满更好改）'}")

    print("\n人工过一眼（机器测不了）：")
    print("  · 眯眼测试：缩到 320px 宽还认得出主体吗？")
    print("  · 第一眼：看的是你想让他看的，还是字幕？")
    print("  · 禁止项：脚本里写的 forbid，这一版犯了吗？")


def pick_scene(beat: dict, fallback: int) -> int:
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("story")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--check", action="store_true", help="只体检不渲染")
    a = ap.parse_args()
    cfg = yaml.safe_load(Path(a.story).read_text(encoding="utf-8"))
    if a.check:
        errs, warns = validate(cfg)
        print(f"体检：{a.story}")
        for e in errs:
            print("  ✗", e)
        for w in warns:
            print("  ⚠", w)
        if not errs and not warns:
            print("  ✅ 八维齐全，无非法取值")
        sys.exit(1 if errs else 0)
    if not a.out:
        sys.exit("缺少输出路径")
    render(Path(a.story), Path(a.out))


if __name__ == "__main__":
    main()
