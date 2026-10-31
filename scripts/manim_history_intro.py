"""课件导入片头 · 历史学科 · Manim 实现

纯矢量，无 GPU，无 LaTeX（中文用系统字体）。参数从环境变量读，方便批量出片：

    set INTRO_KICKER=第一章
    set INTRO_TITLE=秦汉
    set INTRO_SUB=公元前 221 — 公元 220
    set INTRO_TAG=史
    manim -qh --fps 30 scripts/manim_history_intro.py HistoryIntro

产出：media/videos/manim_history_intro/1080p30/HistoryIntro.mp4
"""
from __future__ import annotations

import os

import numpy as np
from manim import (
    DOWN, LEFT, RIGHT, UP, Create, FadeIn, FadeOut, GrowFromCenter, Line,
    Rotate, Scene, Square, Text, VGroup, Write, config, rate_functions,
)

# 两套视觉：paper = 纸感墨色（默认），chalk = 黑板粉笔
STYLE = os.environ.get("INTRO_STYLE", "paper").strip().lower()
if STYLE == "chalk":
    PAPER = "#1C2A25"   # 深墨绿板面
    INK = "#F2EFE6"     # 白粉笔
    RUST = "#E9A03C"    # 橙粉笔（只做强调）
    FADED = "#8FA39A"   # 淡粉笔（年份）
else:
    PAPER = "#EFE6D4"   # 纸色
    INK = "#232120"     # 墨色
    RUST = "#C1543A"    # 锈红（强调）
    FADED = "#8A8272"   # 淡墨（年份）

CJK = "Microsoft YaHei"
SERIF = "SimSun"

KICKER = os.environ.get("INTRO_KICKER", "第一章")
TITLE = os.environ.get("INTRO_TITLE", "秦汉")
SUB = os.environ.get("INTRO_SUB", "公元前 221 — 公元 220")
TAG = os.environ.get("INTRO_TAG", "史")
YEARS = os.environ.get("INTRO_YEARS", "前221,前202,220").split(",")


def t(text: str, size: int, color=INK, font=CJK, weight="NORMAL"):
    return Text(text, font=font, font_size=size, color=color, weight=weight)


class HistoryIntro(Scene):
    def construct(self):
        self.camera.background_color = PAPER

        # 稿纸横线
        rules = VGroup(*[
            Line(LEFT * 7.4, RIGHT * 7.4, stroke_width=1, color=FADED, stroke_opacity=0.045 if STYLE == "chalk" else 0.16)
            .shift(UP * y)
            for y in np.arange(-4.0, 4.1, 0.42)
        ])
        self.add(rules)

        # 时间轴（YEARS 为空则整条不画）
        has_axis = bool(YEARS) and any(y.strip() for y in YEARS)
        axis = Line(LEFT * 5.0 + DOWN * 1.15, RIGHT * 4.8 + DOWN * 1.15,
                    stroke_width=2.4, color=INK)
        ticks = VGroup()
        labels = VGroup()
        xs = [-4.2, 0.0, 4.0]
        for x, y in zip(xs, YEARS):
            tick = Line(UP * 0.16, DOWN * 0.16, stroke_width=2.0, color=INK).move_to([x, -1.15, 0])
            lab = t(y.strip(), 26, FADED).next_to(tick, DOWN, buff=0.18)
            ticks.add(tick)
            labels.add(lab)

        # 主标题（超过安全宽度自动缩字号）
        title = t(TITLE, 132, INK, CJK, "BOLD")
        if title.width > 7.4:
            title.scale(7.4 / title.width)
        title.move_to(UP * (1.05 if has_axis else 0.50))

        # 导语（同样自动收）
        kicker = t(KICKER, 34, RUST)
        if kicker.width > 5.6:
            kicker.scale(5.6 / kicker.width)
        kicker.move_to(UP * (2.25 if has_axis else 1.70))

        # 副标题（长副标题自动缩）
        sub = t(SUB, 40, INK)
        if sub.width > 8.2:
            sub.scale(8.2 / sub.width)
        sub.next_to(title, DOWN, buff=0.42)

        # 竖排细线（标题左侧的装饰）
        bar = Line(UP * 0.19, DOWN * 0.19, stroke_width=3.6, color=RUST)

        # 印章
        seal_box = Square(side_length=0.92, stroke_width=4.0, color=RUST,
                          fill_color=RUST, fill_opacity=0.0 if STYLE == "chalk" else 0.08)
        seal_txt = t(TAG, 46, RUST)
        seal = VGroup(seal_box, seal_txt).move_to([5.55, -2.55, 0]).rotate(-6 * np.pi / 180)

        # ---------------- 时间线 ----------------
        if has_axis and len(ticks) > 0:
            self.play(Create(axis), run_time=1.15, rate_func=rate_functions.ease_out_cubic)
            self.play(
                *[GrowFromCenter(tk) for tk in ticks],
                *[FadeIn(lb, shift=DOWN * 0.1) for lb in labels],
                run_time=0.85, lag_ratio=0.25,
            )

        # ---------------- 章节 ----------------
        self.play(FadeIn(kicker, shift=UP * 0.2), run_time=0.7)
        bar.move_to(kicker.get_left() + LEFT * 0.26)
        self.play(Create(bar), run_time=0.4)

        # ---------------- 主标题 ----------------
        self.play(
            FadeIn(title, shift=UP * 0.45, scale=1.06),
            run_time=1.15, rate_func=rate_functions.ease_out_cubic,
        )

        # ---------------- 副标题 ----------------
        self.play(FadeIn(sub, shift=UP * 0.2), run_time=0.75)

        # ---------------- 印章 ----------------
        self.play(
            seal.animate.scale(1.0).set_opacity(1),
            FadeIn(seal, shift=UP * 0.5),
            run_time=0.55, rate_func=rate_functions.ease_out_back,
        )

        self.wait(3.6)

        # 收：整体退出
        group = VGroup(kicker, title, sub, seal, rules, bar)
        if has_axis:
            group.add(axis, ticks, labels)
        self.play(FadeOut(group), run_time=0.7)
