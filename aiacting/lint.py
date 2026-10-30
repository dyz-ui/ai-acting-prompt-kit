"""提示词体检：找出那些「AI 一定会自己瞎编」的地方。

规则来源：把情绪写成情绪形容词 = 把表演交给模型随机决定。
"""
from __future__ import annotations

import re
from typing import List, Tuple

from .au import AULibrary
from .schema import Project

Issue = Tuple[str, str]  # (level, message)

EMOTION_WORDS = [
    "悲伤", "难过", "痛苦", "委屈", "绝望", "崩溃", "愤怒", "生气", "恼火", "暴怒",
    "开心", "高兴", "快乐", "兴奋", "激动", "紧张", "害怕", "恐惧", "焦虑", "羞愧",
    "尴尬", "内疚", "平静", "冷漠", "温柔", "深情", "心碎", "崩溃", "无助", "释然",
]

# 可被摄影机看见的动作动词
ACTION_VERBS = [
    "抬", "压", "收", "松", "张", "闭", "垂", "移", "转", "低", "仰", "倾", "握",
    "推开", "后退", "前探", "呼吸", "吸气", "吞咽", "咬", "抿", "绷", "颤", "抖",
    "眨眼", "盯", "避", "看", "落", "停", "笑", "皱眉", "点头", "摇头",
]

INTENSIFIERS = ["非常", "十分", "极其", "特别", "无比", "深深地", "剧烈的", "强烈地"]


def _has_action(text: str) -> bool:
    return any(v in text for v in ACTION_VERBS)


def lint_text(text: str) -> List[Issue]:
    """扫描任意自由文本（粘贴进来的旧提示词也能用）。"""
    issues: List[Issue] = []
    for seg in re.split(r"[。；;\n]", text):
        seg = seg.strip()
        if not seg:
            continue
        hits = [w for w in EMOTION_WORDS if w in seg]
        if hits and not _has_action(seg):
            issues.append(
                ("WARN", f"「{seg[:40]}」只给了情绪词（{'/'.join(hits)}），没有可见动作，模型会自己编")
            )
        for adv in INTENSIFIERS:
            if adv in seg:
                issues.append(("WARN", f"「{seg[:40]}」用了程度副词「{adv}」，模型无法量化，改成幅度或秒数"))
                break
    if "禁止" not in text and "不要" not in text:
        issues.append(("WARN", "全文没有禁止项（NO），模型会把情绪提前演满"))
    if not re.search(r"\d+(\.\d+)?\s*(秒|s\b)", text):
        issues.append(("WARN", "全文没有秒级时间码，无法控制节奏"))
    return issues


def lint_project(p: Project, lib: AULibrary | None = None) -> List[Issue]:
    from .schema import check

    lib = lib or AULibrary()
    issues: List[Issue] = []
    for line in check(p, lib):
        if line.startswith("[INFO]"):
            issues.append(("INFO", line.split("]", 1)[1].strip()))
        elif line.startswith("[ERROR]"):
            issues.append(("ERROR", line.split("]", 1)[1].strip()))
        else:
            issues.append(("WARN", line.split("]", 1)[1].strip()))

    for s in p.shots:
        for i, b in enumerate(s.beats, 1):
            where = f"{s.id}-B{i}"
            if b.face_natural:
                for seg in re.split(r"[；;，,]", b.face_natural):
                    hits = [w for w in EMOTION_WORDS if w in seg]
                    if hits and not _has_action(seg):
                        issues.append(("WARN", f"{where} 面部描写出现裸情绪词「{'/'.join(hits)}」"))
            if b.face_au:
                codes = {x.split(":")[0].upper() for x in b.face_au}
                strong = {x.split(":")[0].upper() for x in b.face_au if x.partition(":")[2] in ("4", "5")}
                if {"AU4", "AU1"} <= codes and strong & {"AU4", "AU1"}:
                    issues.append(
                        ("WARN", f"{where} 同时强压眉(AU4)与抬内眉(AU1)，属于复合情绪，请标明先后顺序")
                    )
            if b.emotion_curve and "→" not in b.emotion_curve and "->" not in b.emotion_curve:
                issues.append(("WARN", f"{where} 情绪曲线只写了一个状态，没有转折（建议 A → B）"))
    return issues


def format_issues(issues: List[Issue]) -> str:
    if not issues:
        return "✓ 体检通过，没有发现会让模型瞎编的地方。"
    errs = [m for lv, m in issues if lv == "ERROR"]
    warns = [m for lv, m in issues if lv == "WARN"]
    infos = [m for lv, m in issues if lv == "INFO"]
    out = []
    if errs:
        out.append(f"✗ 必须修（{len(errs)}）")
        out += [f"   · {m}" for m in errs]
    if warns:
        out.append(f"! 建议修（{len(warns)}）")
        out += [f"   · {m}" for m in warns]
    if infos:
        out.append(f"i 提示（{len(infos)}）")
        out += [f"   · {m}" for m in infos]
    if not errs and not warns:
        out.insert(0, "✓ 没有会阻塞生成的问题。")
    return "\n".join(out)
