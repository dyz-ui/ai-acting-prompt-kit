"""把项目 YAML 渲染成「节拍预览片」（animatic）。

用途：在花钱生成之前，先用代码渲一版只看节奏和节拍的草稿，
确认 30 秒里的情绪曲线是不是你想要的那条。

这不是 AI 生成，是纯代码绘制 —— 本机最快能到几十 fps。
"""
from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from .schema import Beat, Project, Shot

BG = (14, 16, 20)
FG = (238, 240, 244)
DIM = (138, 146, 162)
FAINT = (58, 64, 76)
ACCENTS = ["#4C8DFF", "#E8A33D", "#5DCAA5", "#D4537E", "#AFA9EC", "#F0997B"]

FONT_CANDIDATES = [
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/msyhl.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]


def _font(size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _hex(c: str) -> Tuple[int, int, int]:
    c = c.lstrip("#")
    return tuple(int(c[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _tint(c: Tuple[int, int, int], f: float) -> Tuple[int, int, int]:
    """f<1 压暗（与背景混合），f>1 提亮。"""
    if f <= 1:
        return tuple(int(v * f + b * (1 - f)) for v, b in zip(c, BG))  # type: ignore[return-value]
    return tuple(min(255, int(v * f)) for v in c)  # type: ignore[return-value]


def _wrap(d: ImageDraw.ImageDraw, text: str, font, width: float, max_lines: int) -> List[str]:
    """按宽度断行；超出行数就截断并加省略号。中文按字断，不依赖空格。"""
    text = " ".join(str(text).split())
    if not text:
        return []
    lines: List[str] = []
    cur = ""
    for ch in text:
        if d.textlength(cur + ch, font=font) <= width:
            cur += ch
            continue
        lines.append(cur)
        cur = ch
        if len(lines) >= max_lines:
            break
    if len(lines) < max_lines and cur:
        lines.append(cur)
        cur = ""
    if cur and lines:
        while lines[-1] and d.textlength(lines[-1] + "…", font=font) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


class _Seg:
    __slots__ = ("start", "end", "shot", "beat", "index", "color")

    def __init__(self, start: float, end: float, shot: Shot, beat: Optional[Beat], index: int, color):
        self.start, self.end = start, end
        self.shot, self.beat, self.index, self.color = shot, beat, index, color


def _segments(proj: Project) -> List[_Seg]:
    segs: List[_Seg] = []
    n = 0
    for si, shot in enumerate(proj.shots):
        color = _hex(ACCENTS[si % len(ACCENTS)])
        if shot.beats:
            for b in shot.beats:
                n += 1
                segs.append(_Seg(b.start, b.end, shot, b, n, color))
        else:
            segs.append(_Seg(shot.start, shot.end, shot, None, 0, color))
    return sorted(segs, key=lambda s: s.start)


def render(
    proj: Project,
    out: Path,
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    crf: int = 22,
) -> Path:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    segs = _segments(proj)
    if not segs:
        raise RuntimeError("项目里没有任何镜头/节拍，无法渲染")

    f_title = _font(30)
    f_meta = _font(18)
    f_beat = _font(21)
    f_body = _font(17)
    f_tiny = _font(14)

    dur = max(proj.duration, segs[-1].end)
    total = int(round(dur * fps))

    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
        "-pix_fmt", "yuv420p", str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    m = 48
    track_y = height - 92
    track_h = 34

    for i in range(total):
        t = i / fps
        seg = segs[0]
        for s in segs:
            if s.start <= t < s.end:
                seg = s
                break

        img = Image.new("RGB", (width, height), BG)
        d = ImageDraw.Draw(img)

        # 顶部：标题 + 时间码
        d.text((m, 34), proj.title, font=f_title, fill=FG)
        tc = f"{int(t // 60):02d}:{t % 60:05.2f}"
        d.text((width - m - d.textlength(tc, font=f_meta), 44), tc, font=f_meta, fill=DIM)

        # 镜头行
        d.text((m, 80), f"{seg.shot.id}  ·  {seg.shot.framing or '—'}  ·  {seg.shot.camera_move or '固定'}",
               font=f_meta, fill=DIM)
        d.line([(m, 116), (width - m, 116)], fill=FAINT, width=1)

        # 节拍卡
        y = 140
        if seg.beat:
            b = seg.beat
            head = f"节拍 {seg.index}    {b.start:g}–{b.end:g}s" + (f"    {b.who}" if b.who else "")
            d.rectangle([m, y - 6, m + 6, y + 26], fill=seg.color)
            d.text((m + 18, y), head, font=f_beat, fill=seg.color)
            y += 44

            rows = [
                ("目的", b.objective),
                ("情绪", b.emotion_curve),
                ("触发", f"“{b.trigger_line}”" if b.trigger_line else ""),
                ("台词", f"“{b.line}”" if b.line else ""),
                ("面部", b.face_natural),
                ("目光", b.gaze_body),
                ("声音", b.voice),
                ("停顿", b.pause),
                ("结束", b.end_state),
                ("禁止", "；".join(b.forbidden)),
            ]
            for label, val in rows:
                if not val:
                    continue
                if y > track_y - 44:
                    break
                d.text((m, y + 2), label, font=f_tiny, fill=(96, 104, 120))
                lines = _wrap(d, val, f_body, width - m * 2 - 46, 2)
                for ln in lines:
                    d.text((m + 46, y), ln, font=f_body, fill=FG if label not in ("禁止",) else (214, 160, 160))
                    y += 25
                y += 6
        else:
            d.text((m, y), seg.shot.note or "（无节拍信息）", font=f_body, fill=DIM)

        # 时间轴
        d.rectangle([m, track_y, width - m, track_y + track_h], fill=(24, 27, 34))
        for s in segs:
            x0 = m + (width - 2 * m) * (s.start / dur)
            x1 = m + (width - 2 * m) * (s.end / dur)
            active = s is seg
            fill = _tint(s.color, 1.0 if active else 0.38)
            d.rectangle([x0 + 2, track_y + 4, max(x1 - 2, x0 + 3), track_y + track_h - 4], fill=fill)
            if active:
                d.rectangle([x0 + 2, track_y + 4, max(x1 - 2, x0 + 3), track_y + track_h - 4],
                            outline=_tint(s.color, 1.35), width=1)
            if s.beat and (x1 - x0) > 42:
                d.text((x0 + 6, track_y + track_h + 6), f"{s.start:g}", font=f_tiny,
                       fill=FG if active else DIM)

        px = m + (width - 2 * m) * (t / dur)
        d.rectangle([px - 1, track_y - 8, px + 1, track_y + track_h + 8], fill=(255, 255, 255))
        d.polygon([(px - 7, track_y - 16), (px + 7, track_y - 16), (px, track_y - 6)], fill=(255, 255, 255))

        # 节拍进度点
        done = sum(1 for s in segs if s.end <= t)
        d.text((m, height - 34), f"{done}/{len(segs)} 节拍    {proj.title} · animatic",
               font=f_tiny, fill=(84, 90, 104))

        proc.stdin.write(img.tobytes())

    proc.stdin.close()
    proc.wait()
    return out


def plan_text(proj: Project) -> str:
    """纯文本版的节拍表，方便贴到别处。"""
    segs = _segments(proj)
    lines = [f"{proj.title}  |  {proj.duration:g}s  |  {len(proj.shots)} 镜  |  {len(segs)} 节拍", ""]
    for s in segs:
        b = s.beat
        head = f"[{s.start:>5.1f}–{s.end:<5.1f}] {s.shot.id}"
        if b:
            lines.append(f"{head} {b.who or ''}")
            if b.objective:
                lines.append(f"          目的：{b.objective}")
            if b.emotion_curve:
                lines.append(f"          情绪：{b.emotion_curve}")
            if b.trigger_line:
                lines.append(f"          触发：“{b.trigger_line}”")
            if b.forbidden:
                lines.append(f"          禁止：{'；'.join(b.forbidden)}")
        else:
            lines.append(head)
    return "\n".join(lines)
