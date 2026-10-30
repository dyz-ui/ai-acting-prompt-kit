"""项目 YAML 的读取、校验与归一化。

设计原则：宁可宽松地读完，再集中报错，也不要让用户对着 KeyError 猜。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .au import AULibrary, validate_specs

# 「两人」「众人」这类群体指代，不要求出现在 characters 里
GROUP_TOKENS = {"两人", "二人", "众人", "所有人", "all", "both"}


@dataclass
class Character:
    id: str
    name: str
    age: str = ""
    look: str = ""
    costume: str = ""
    voice: str = ""


@dataclass
class Beat:
    start: float
    end: float
    who: str = ""
    objective: str = ""
    emotion_curve: str = ""
    trigger_line: str = ""
    line: str = ""
    face_au: List[str] = field(default_factory=list)
    face_natural: str = ""
    gaze_body: str = ""
    voice: str = ""
    pause: str = ""
    end_state: str = ""
    forbidden: List[str] = field(default_factory=list)


@dataclass
class Shot:
    id: str
    start: float
    end: float
    framing: str = ""
    camera_move: str = ""
    focus: str = ""
    note: str = ""
    beats: List[Beat] = field(default_factory=list)


@dataclass
class Project:
    title: str
    duration: float
    genre: str = "家庭剧情"
    style: str = "写实电影质感"
    aspect: str = "16:9"
    resolution: str = "1080p"
    camera: str = ""
    era: str = ""
    location: str = ""
    lighting: str = ""
    sound: str = "原生同步对白"
    ambience: str = ""
    guardrail: List[str] = field(default_factory=list)
    characters: List[Character] = field(default_factory=list)
    shots: List[Shot] = field(default_factory=list)
    source: str = ""
    notes: List[str] = field(default_factory=list)

    def character(self, key: str) -> Optional[Character]:
        for c in self.characters:
            if key in (c.id, c.name):
                return c
        return None


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _fix_aspect(v: Any) -> Tuple[str, Optional[str]]:
    """YAML 1.1 会把 16:9 当成六十进制数算成 969，这里还原并给出提示。"""
    if isinstance(v, int) and 60 < v < 6000:
        a, b = divmod(v, 60)
        if 1 <= a <= 100 and 1 <= b <= 45:
            return f"{a}:{b}", f"画幅被 YAML 解析成了六十进制数 {v}，已自动还原为 {a}:{b}；建议在 YAML 里写成 \"{a}:{b}\""
    if isinstance(v, str) and ":" in v:
        return v, None
    if isinstance(v, str) and v:
        return v, f"画幅写法 {v!r} 建议写成 16:9 这种带冒号的格式"
    return "16:9", "画幅缺失，已按 16:9 处理"


def load(path: str | Path) -> Project:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    p = raw.get("project", {}) or {}
    aspect, aspect_note = _fix_aspect(p.get("aspect", "16:9"))
    proj = Project(
        title=str(p.get("title", "未命名")),
        duration=_f(p.get("duration"), 30),
        genre=str(p.get("genre", "家庭剧情")),
        style=str(p.get("style", "写实电影质感")),
        aspect=aspect,
        resolution=str(p.get("resolution", "1080p")),
        camera=str(p.get("camera", "")),
        era=str(p.get("era", "")),
        location=str(p.get("location", "")),
        lighting=str(p.get("lighting", "")),
        sound=str(p.get("sound", "原生同步对白")),
        ambience=str(p.get("ambience", "")),
        guardrail=[str(x) for x in (p.get("guardrail") or [])],
        source=str(path),
    )
    if aspect_note:
        proj.notes.append(aspect_note)
    for c in raw.get("characters") or []:
        proj.characters.append(
            Character(
                id=str(c.get("id") or c.get("name") or "?"),
                name=str(c.get("name") or c.get("id") or "?"),
                age=str(c.get("age", "")),
                look=str(c.get("look", "")),
                costume=str(c.get("costume", "")),
                voice=str(c.get("voice", "")),
            )
        )
    for s in raw.get("shots") or []:
        shot = Shot(
            id=str(s.get("id", f"S{len(proj.shots) + 1}")),
            start=_f(s.get("start")),
            end=_f(s.get("end")),
            framing=str(s.get("framing", "")),
            camera_move=str(s.get("camera_move", "")),
            focus=str(s.get("focus", "")),
            note=str(s.get("note", "")),
        )
        for b in s.get("beats") or []:
            shot.beats.append(
                Beat(
                    start=_f(b.get("start"), shot.start),
                    end=_f(b.get("end"), shot.end),
                    who=str(b.get("who", "")),
                    objective=str(b.get("objective", "")),
                    emotion_curve=str(b.get("emotion_curve", "")),
                    trigger_line=str(b.get("trigger_line", "")),
                    line=str(b.get("line", "")),
                    face_au=[str(x) for x in (b.get("face_au") or [])],
                    face_natural=str(b.get("face_natural", "")),
                    gaze_body=str(b.get("gaze_body", "")),
                    voice=str(b.get("voice", "")),
                    pause=str(b.get("pause", "")),
                    end_state=str(b.get("end_state", "")),
                    forbidden=[str(x) for x in (b.get("forbidden") or [])],
                )
            )
        proj.shots.append(shot)
    return proj


def check(proj: Project, lib: Optional[AULibrary] = None) -> List[str]:
    """返回问题列表，前缀 [ERROR] / [WARN]。"""
    lib = lib or AULibrary()
    out: List[str] = []
    for n in proj.notes:
        out.append(f"[INFO] {n}")

    if proj.duration <= 0:
        out.append("[ERROR] project.duration 必须大于 0")
    if not proj.shots:
        out.append("[ERROR] 没有任何镜头（shots）")

    cursor = 0.0
    for shot in proj.shots:
        if shot.end <= shot.start:
            out.append(f"[ERROR] 镜头 {shot.id} 的 end 必须大于 start")
        if abs(shot.start - cursor) > 0.35:
            out.append(
                f"[WARN] 镜头 {shot.id} 起点 {shot.start:.1f}s 与上一镜头终点 {cursor:.1f}s 不连续"
            )
        cursor = shot.end

        b_cursor = shot.start
        for i, beat in enumerate(shot.beats, 1):
            tag = f"{shot.id}-B{i}"
            if beat.end <= beat.start:
                out.append(f"[ERROR] 节拍 {tag} 的 end 必须大于 start")
            if beat.start < shot.start - 0.01 or beat.end > shot.end + 0.01:
                out.append(f"[WARN] 节拍 {tag} 超出镜头 {shot.id} 的时间范围")
            if beat.start < b_cursor - 0.01:
                out.append(f"[WARN] 节拍 {tag} 与上一节拍时间重叠")
            b_cursor = beat.end

            if beat.who and beat.who not in GROUP_TOKENS and not proj.character(beat.who):
                out.append(f"[WARN] 节拍 {tag} 的人物 {beat.who!r} 不在 characters 中")
            if not beat.objective:
                out.append(f"[WARN] 节拍 {tag} 缺少「人物目的」，AI 会自己编动机")
            if not beat.face_natural and not beat.face_au:
                out.append(f"[ERROR] 节拍 {tag} 既没有自然语言面部描写，也没有 AU")
            if beat.face_au:
                out.extend(f"[ERROR] 节拍 {tag}：{e}" for e in validate_specs(beat.face_au, lib))
            if beat.line and not beat.trigger_line:
                out.append(f"[WARN] 节拍 {tag} 有台词但没标「触发词」，表情不知道挂在哪一句上")
            if not beat.forbidden:
                out.append(f"[WARN] 节拍 {tag} 没有「禁止项」，AI 很容易提前把情绪演满")
            if beat.end - beat.start > 6.0:
                out.append(
                    f"[WARN] 节拍 {tag} 长达 {beat.end - beat.start:.1f}s，建议再拆细，模型对长区间控制力下降"
                )

    if abs(cursor - proj.duration) > 0.5:
        out.append(
            f"[WARN] 镜头总时长 {cursor:.1f}s 与 project.duration {proj.duration:.1f}s 不一致"
        )
    if len(proj.characters) > 3:
        out.append("[WARN] 角色超过 3 人，30 秒短片里一致性会明显下降")
    return out
