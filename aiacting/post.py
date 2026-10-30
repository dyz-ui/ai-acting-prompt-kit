"""本地后期工具（只在 CPU 上跑，不需要显卡）。"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


def _run(cmd: List[str], quiet: bool = True) -> subprocess.CompletedProcess:
    if shutil.which(cmd[0]) is None:
        raise RuntimeError(f"找不到 {cmd[0]}，请先安装并加入 PATH")
    return subprocess.run(
        cmd,
        check=True,
        capture_output=True if quiet else None,
        text=True,
    )


def concat(clips: List[Path], out: Path, reencode: bool = True) -> Path:
    """按顺序拼接多条生成片段。AI 片段的编码参数经常不一致，默认重编码。"""
    out.parent.mkdir(parents=True, exist_ok=True)
    lst = out.with_suffix(".txt")
    lst.write_text("".join(f"file '{Path(c).resolve().as_posix()}'\n" for c in clips), encoding="utf-8")
    if reencode:
        cmd = [
            "ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
            "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", str(out),
        ]
    else:
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)]
    _run(cmd)
    return out


def loudnorm(src: Path, out: Optional[Path] = None, target: float = -14.0) -> Path:
    """短视频平台常用 -14 LUFS；对白片别压太狠。"""
    out = out or src.with_name(src.stem + "_norm" + src.suffix)
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-af", f"loudnorm=I={target}:TP=-1.5:LRA=11",
        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", str(out),
    ])
    return out


def contact_sheet(src: Path, out: Optional[Path] = None, every: float = 3.0, cols: int = 5) -> Path:
    """每 N 秒抽一帧做拼图，用来检查人物/服装是否跨镜头漂移。"""
    out = out or src.with_name(src.stem + "_sheet.jpg")
    rows = max(1, min(6, int(30 // (every * cols)) + 1))
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-vf", f"fps=1/{every},scale=320:-1,tile={cols}x{rows}",
        "-frames:v", "1", "-q:v", "3", str(out),
    ])
    return out


def burn_subtitle(src: Path, srt: Path, out: Optional[Path] = None, size: int = 22) -> Path:
    out = out or src.with_name(src.stem + "_sub" + src.suffix)
    # Windows 路径里的反斜杠和冒号要转义，否则 ffmpeg 滤镜链会崩
    esc = str(Path(srt).resolve()).replace("\\", "/").replace(":", "\\:")
    style = (
        f"FontName=Microsoft YaHei,FontSize={size},PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,MarginV=42"
    )
    _run([
        "ffmpeg", "-y", "-v", "error", "-i", str(src),
        "-vf", f"subtitles='{esc}':force_style='{style}'",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-c:a", "copy", str(out),
    ])
    return out


def probe(src: Path) -> str:
    cp = _run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,codec_name",
        "-show_entries", "format=duration", "-of", "default=nw=1", str(src),
    ])
    return cp.stdout.strip()


def frames(src: Path, outdir: Path, stamps: List[float]) -> List[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    made = []
    for t in stamps:
        p = outdir / f"{src.stem}_{t:g}s.jpg"
        _run(["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", str(src), "-frames:v", "1", "-q:v", "2", str(p)])
        made.append(p)
    return made
