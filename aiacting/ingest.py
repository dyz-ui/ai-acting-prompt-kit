"""把一条参考视频拆开：解析 -> 下载 -> 抽音 -> 抽帧 -> 转写。

抖音有反爬，yt-dlp 需要新鲜 cookie；这里同时提供公开解析接口作为兜底。
"""
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
PARSERS = [
    "https://api.xingzhige.com/API/douyin/?url={url}",
]


def _get_json(url: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))


def resolve(url: str) -> Tuple[str, str, str]:
    """返回 (标题, mp4 直链, 作者)。"""
    errors = []
    if shutil.which("yt-dlp") and "douyin" not in url:
        try:
            cp = subprocess.run(
                ["yt-dlp", "--no-warnings", "-f", "bv*+ba/b", "-g", "--print", "%(title)s", url],
                capture_output=True, text=True, timeout=120,
            )
            if cp.returncode == 0:
                lines = [x for x in cp.stdout.splitlines() if x.strip()]
                return lines[0], lines[-1], ""
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))

    for tpl in PARSERS:
        try:
            data = _get_json(tpl.format(url=urllib.parse.quote(url, safe="")))
            d = data.get("data") or {}
            item = d.get("item") or {}
            title = (item.get("title") or "").strip()
            mp4 = item.get("url") or ""
            author = ((d.get("author") or {}).get("name") or "")
            if mp4:
                return title, mp4, author
            errors.append(f"{tpl} 无 url 字段")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{tpl}: {e}")
    raise RuntimeError("解析失败：\n" + "\n".join(errors))


def download(url: str, outdir: Path, name: str = "video") -> Tuple[Path, str]:
    title, mp4, author = resolve(url)
    outdir.mkdir(parents=True, exist_ok=True)
    dst = outdir / f"{name}.mp4"
    req = urllib.request.Request(mp4, headers={"User-Agent": UA, "Referer": "https://www.douyin.com/"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dst, "wb") as f:
        shutil.copyfileobj(r, f)
    (outdir / "meta.json").write_text(
        json.dumps({"title": title, "author": author, "src": url}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return dst, title


def to_audio(video: Path, out: Optional[Path] = None, rate: int = 16000) -> Path:
    out = out or video.with_suffix(".mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(video), "-vn", "-ac", "1",
         "-ar", str(rate), "-c:a", "libmp3lame", "-b:a", "48k", str(out)],
        check=True,
    )
    return out


def transcribe(audio: Path, model_size: str = "small") -> str:
    """需要可选依赖：pip install faster-whisper。纯 CPU 可用，7 分钟音频约 3-6 分钟。"""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "转写需要 faster-whisper：pip install faster-whisper\n"
            "（不想装的话，可以把音频直接丢给任意支持长音频的转写工具）"
        ) from e
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(audio), language="zh", vad_filter=True, beam_size=5)
    lines = []
    for seg in segments:
        m, s = divmod(int(seg.start), 60)
        lines.append(f"[{m:02d}:{s:02d}] {seg.text.strip()}")
    return "\n".join(lines)
