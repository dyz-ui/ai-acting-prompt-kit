"""把结构化项目编译成可直接粘贴给小云雀 / Seedance 的提示词文本。"""
from __future__ import annotations

from typing import List

from .au import AULibrary
from .schema import Beat, Project, Shot


def _t(x: float) -> str:
    """3.70 -> '3.7'，整数保留一位小数：6.0 -> '6'"""
    s = f"{x:.1f}"
    return s[:-2] if s.endswith(".0") else s


def _rng(a: float, b: float) -> str:
    return f"{_t(a)}–{_t(b)} 秒"


# --------------------------------------------------------------------------
# 第一层：全局控制（只搭片场，不负责演戏）
# --------------------------------------------------------------------------
def render_layer1(p: Project) -> str:
    lines: List[str] = []
    head = f"生成一支 {_t(p.duration)} 秒、{p.style}、{p.sound}的{p.genre}短片。"
    lines.append(head)

    spec = [f"画幅 {p.aspect}"]
    if p.camera:
        spec.append(p.camera)
    if p.resolution:
        spec.append(f"{p.resolution} 输出")
    lines.append("，".join(spec) + "。")

    scene = []
    if p.era:
        scene.append(p.era)
    if p.location:
        scene.append(p.location)
    if p.lighting:
        scene.append(p.lighting)
    if scene:
        lines.append("故事发生在" + "，".join(scene) + "。")
    if p.ambience:
        lines.append(f"环境声：{p.ambience}。")

    if p.characters:
        lines.append("【人物一致性】全片人物始终保持相同面孔、年龄、服装、发型和站位：")
        for c in p.characters:
            bits = [b for b in [c.age, c.look, c.costume] if b]
            voice = f"声音：{c.voice}" if c.voice else ""
            body = "，".join(bits)
            tail = f"；{voice}" if voice else ""
            lines.append(f"- {c.name}：{body}{tail}")

    guards = list(p.guardrail)
    if guards:
        lines.append("全片禁止项：" + "；".join(guards) + "。")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 第二层：镜头时间轴（按镜头分级，再按时间码做子集）
# --------------------------------------------------------------------------
def render_shot_line(s: Shot) -> str:
    bits = [f"{s.id}｜{_rng(s.start, s.end)}"]
    if s.framing:
        bits.append(s.framing)
    if s.camera_move:
        bits.append(s.camera_move)
    if s.focus:
        bits.append(f"主要观察：{s.focus}")
    line = "｜".join(bits)
    if s.note:
        line += f"。{s.note}"
    return line


def render_layer2(p: Project) -> str:
    lines = [f"整段戏分为 {len(p.shots)} 个镜头，按以下时间轴切换，不允许自行增加镜头或改变机位："]
    for s in p.shots:
        lines.append("- " + render_shot_line(s))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 第三层：表演控制（八维公式）
# --------------------------------------------------------------------------
def render_beat(b: Beat, lib: AULibrary, index: int) -> str:
    rows: List[str] = []
    rows.append(f"  ▸ 节拍{index}｜{_rng(b.start, b.end)}" + (f"｜{b.who}" if b.who else ""))

    if b.objective:
        rows.append(f"    目的：{b.objective}")
    if b.emotion_curve:
        rows.append(f"    情绪：{b.emotion_curve}")
    if b.trigger_line:
        rows.append(f"    触发词：“{b.trigger_line}”")
    if b.line:
        rows.append(f"    台词：“{b.line}”")

    face_parts: List[str] = []
    if b.face_natural:
        face_parts.append(b.face_natural)
    if b.face_au:
        face_parts.append("辅助校准：" + "，".join(lib.describe(x) for x in b.face_au))
    if face_parts:
        rows.append("    面部：" + "；".join(face_parts))

    if b.gaze_body:
        rows.append(f"    目光与身体：{b.gaze_body}")
    if b.voice:
        rows.append(f"    声音、呼吸与停顿：{b.voice}")
    if b.pause:
        rows.append(f"    停顿：{b.pause}")
    if b.end_state:
        rows.append(f"    结束状态：{b.end_state}")
    if b.forbidden:
        rows.append("    禁止：" + "；".join(b.forbidden))
    return "\n".join(rows)


def render_layer3(p: Project, lib: AULibrary) -> str:
    lines = [
        "以下为表演控制层。只写可被镜头观察到的动作，不写情绪形容词。"
        "每个镜头内按节拍执行，前一个节拍没结束，不允许提前出现后一个节拍的反应。"
    ]
    for s in p.shots:
        if not s.beats:
            continue
        lines.append("")
        lines.append(f"【{s.id}｜{_rng(s.start, s.end)}｜{s.focus or '按节拍切换观察对象'}】")
        if s.beats:
            lines.append("  局部时间码拆解：")
        for i, b in enumerate(s.beats, 1):
            lines.append(render_beat(b, lib, i))
    return "\n".join(lines)


# --------------------------------------------------------------------------
# 汇总
# --------------------------------------------------------------------------
def render_submit(p: Project) -> str:
    return (
        "【提交参数】\n"
        f"- 平台：小云雀 AI（Agent 模式）\n"
        f"- 模型：Seedance 2.5（支持 30 秒直出与精确时间戳控制）\n"
        f"- 时长：{_t(p.duration)} 秒\n"
        f"- 画幅：{p.aspect}\n"
        f"- 原声：开启\n"
        f"- 参考图：不垫图（纯文本提示词）\n"
        "- 提示词：粘贴上文全文，整段提交，不要分段生成后再拼"
    )


def compile_text(p: Project, lib: AULibrary | None = None, layers: str = "all") -> str:
    lib = lib or AULibrary()
    blocks: List[str] = []
    if layers in ("all", "1"):
        blocks.append("【第一层 · 全局控制】\n" + render_layer1(p))
    if layers in ("all", "2"):
        blocks.append("【第二层 · 镜头时间轴】\n" + render_layer2(p))
    if layers in ("all", "3"):
        blocks.append("【第三层 · 表演控制】\n" + render_layer3(p, lib))
    if layers == "all":
        blocks.append(render_submit(p))
    return "\n\n".join(blocks)


def compile_flat(p: Project, lib: AULibrary | None = None) -> str:
    """单段纯文本版：部分模型对 markdown 结构不敏感，用这个。"""
    lib = lib or AULibrary()
    parts: List[str] = [render_layer1(p)]
    parts.append(f"全片 {len(p.shots)} 个镜头：" + "；".join(render_shot_line(s) for s in p.shots) + "。")
    for s in p.shots:
        for i, b in enumerate(s.beats, 1):
            seg = [f"{s.id} 的{_rng(b.start, b.end)}"]
            if b.who:
                seg.append(b.who)
            if b.objective:
                seg.append(f"目的是{b.objective}")
            if b.emotion_curve:
                seg.append(f"情绪走{b.emotion_curve}")
            if b.trigger_line:
                seg.append(f"变化挂在“{b.trigger_line}”这句上")
            if b.face_natural:
                seg.append(b.face_natural)
            if b.face_au:
                seg.append("辅助校准：" + "，".join(lib.describe(x) for x in b.face_au))
            if b.gaze_body:
                seg.append(b.gaze_body)
            if b.voice:
                seg.append(b.voice)
            if b.pause:
                seg.append(b.pause)
            if b.end_state:
                seg.append("最后" + b.end_state)
            if b.forbidden:
                seg.append("不要" + "、不要".join(b.forbidden))
            parts.append("，".join(x for x in seg if x) + "。")
    parts.append("所有人物在全片保持一致，不要出现字幕、水印和额外人物。")
    return "\n\n".join(parts)
