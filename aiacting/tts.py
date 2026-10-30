"""免费中文配音：edge-tts（需要网络，不需要显卡、不需要 API Key）。

注意：中文音色返回的是 SentenceBoundary（整句一个时间点），英文音色才是
WordBoundary。所以这里不用官方 SubMaker，自己按标点切分并等比例分配时间。
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import List, Optional, Tuple

VOICES = {
    "女-温柔": "zh-CN-XiaoxiaoNeural",
    "女-冷静": "zh-CN-XiaoyiNeural",
    "男-低沉": "zh-CN-YunxiNeural",
    "男-成熟": "zh-CN-YunjianNeural",
    "男-旁白": "zh-CN-YunyangNeural",
}

MAX_LINE = 16  # 单行字幕最多字符数


def _split_text(text: str, limit: int = MAX_LINE) -> List[str]:
    """按标点优先切，其次硬切，保证每行不超过 limit。"""
    seps = "，。！？；、,.!?;"
    parts: List[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in seps or len(buf) >= limit:
            parts.append(buf)
            buf = ""
    if buf:
        parts.append(buf)
    # 二次合并过短的片段
    merged: List[str] = []
    for p in parts:
        if merged and len(merged[-1]) + len(p) <= limit:
            merged[-1] += p
        else:
            merged.append(p)
    return [p for p in merged if p.strip()]


def _srt(cues: List[Tuple[float, float, str]]) -> str:
    def ts(sec: float) -> str:
        ms = int(round(sec * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    out = []
    for i, (a, b, text) in enumerate(cues, 1):
        out.append(f"{i}\n{ts(a)} --> {ts(b)}\n{text}\n")
    return "\n".join(out)


async def _synth(text: str, voice: str, out: Path, rate: str, pitch: str) -> None:
    import edge_tts  # type: ignore

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    boundaries: List[dict] = []
    with open(out, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                boundaries.append(chunk)

    cues: List[Tuple[float, float, str]] = []
    for b in boundaries:
        start = b["offset"] / 10_000_000
        dur = b["duration"] / 10_000_000
        pieces = _split_text(b["text"])
        if not pieces:
            continue
        total_chars = sum(len(p) for p in pieces) or 1
        cursor = start
        for p in pieces:
            span = dur * len(p) / total_chars
            cues.append((cursor, cursor + span, p.strip()))
            cursor += span
    if cues:
        out.with_suffix(".srt").write_text(_srt(cues), encoding="utf-8")


def synth(text: str, out: Optional[Path] = None, voice: str = "女-温柔",
          rate: str = "+0%", pitch: str = "+0Hz") -> Path:
    try:
        import edge_tts  # noqa: F401
    except ImportError as e:
        raise RuntimeError("需要：pip install edge-tts") from e
    out = out or Path("voice.mp3")
    asyncio.run(_synth(text, VOICES.get(voice, voice), out, rate, pitch))
    return out


def script_from_lines(lines: List[str]) -> str:
    """把台词表拼成一段适合朗读的文本。"""
    return "，".join(x.strip().rstrip("。，") for x in lines if x.strip()) + "。"
