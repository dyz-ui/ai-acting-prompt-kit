"""命令行入口：aiacting <command>"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import compiler, ingest, lint, post, schema, tts
from .au import AULibrary


def _fix_console() -> None:
    """统一按 UTF-8 输出，并把 Windows 控制台代码页切到 65001。

    只选定一种编码（UTF-8）是刻意的：混用 GBK 会在管道、重定向、CI、
    Git Bash 之间来回出错。如果看到乱码，先执行 `chcp 65001`，
    或在宿主里设 `[Console]::OutputEncoding = [Text.Encoding]::UTF8`。
    """
    import os as _os

    if _os.name == "nt":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:  # noqa: BLE001
            pass
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            pass


def _write(text: str, out: str | None) -> None:
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print(f"已写入 {out}（{len(text)} 字）")
    else:
        print(text)


def cmd_au(args: argparse.Namespace) -> int:
    lib = AULibrary()
    if args.table:
        print(lib.table())
        return 0
    if args.preset:
        presets = lib.presets
        key = args.preset
        if key not in presets:
            match = [k for k in presets if key in k]
            if not match:
                print("可用预设：" + "、".join(presets))
                return 1
            key = match[0]
        p = presets[key]
        print(f"【{key}】")
        print("AU：" + "，".join(lib.describe(x) for x in p["au"]))
        print("自然语言：" + p["natural"])
        print("禁止：" + "；".join(p["forbidden"]))
        return 0
    if args.code:
        try:
            it = lib.get(args.code)
        except KeyError as e:
            print(e)
            return 1
        for k, v in it.items():
            print(f"{k:8}: {v}")
        return 0
    print("用法：aiacting au AU7 ｜ aiacting au --table ｜ aiacting au --preset 悲伤")
    print("可用预设：" + "、".join(lib.presets))
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    proj = schema.load(args.project)
    issues = lint.lint_project(proj)
    print(lint.format_issues(issues))
    return 1 if any(lv == "ERROR" for lv, _ in issues) else 0


def cmd_build(args: argparse.Namespace) -> int:
    proj = schema.load(args.project)
    issues = lint.lint_project(proj)
    errs = [m for lv, m in issues if lv == "ERROR"]
    if errs:
        print("先修掉这些错误：")
        for m in errs:
            print("  · " + m)
        if not args.force:
            return 1
    text = compiler.compile_flat(proj) if args.flat else compiler.compile_text(proj, layers=args.layer)
    _write(text, args.out)
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    if args.text:
        text = args.text
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    issues = lint.lint_text(text)
    print(lint.format_issues(issues))
    return 0


SCAFFOLD = """project:
  title: {title}
  duration: 30
  genre: 家庭剧情
  style: 写实电影质感
  aspect: "16:9"      # 引号不能去掉：YAML 会把 16:9 当成六十进制数算成 969
  resolution: 1080p
  camera: 35mm 胶片颗粒，24fps 观感，浅景深，轻微手持呼吸感
  era: 20 世纪中期美国普通工人家庭
  location: 后院门廊，冬末残雪
  lighting: 阴天柔光，整体冷调，面部保留一点暖色补光
  sound: 原生同步对白
  guardrail:
    - 不出现任何字幕、片头片尾、水印
    - 不出现第三个人物
    - 人物面孔与服装在全片保持不变

characters:
  - id: woman
    name: 女人
    age: 38 岁
    look: 金色短发，鼻尖发红，眼周有哭过的痕迹
    costume: 红色格纹毛领外套
    voice: 中低音，沙哑，句尾容易破
  - id: man
    name: 男人
    age: 41 岁
    look: 深色短发，胡茬，眼窝深
    costume: 旧皮夹克，深色高领毛衣
    voice: 低沉，语速慢，几乎不抬音量

shots:
  - id: S1
    start: 0.0
    end: 3.7
    framing: 中景双人，侧面
    camera_move: 固定机位
    focus: 女人
    note: 交代两人的距离与沉默
    beats:
      - start: 0.0
        end: 3.7
        who: 女人
        objective: 确认对方还愿不愿意开口
        emotion_curve: 强撑 → 迟疑
        face_au: [AU7:2, AU24:2]
        face_natural: 视线压在对方胸口位置，不上移；双唇压紧，下巴轻微抬起
        gaze_body: 双手在身前交握，肩膀不动
        voice: 只有呼吸声，鼻吸口呼，节奏偏快
        end_state: 目光仍未上移，嘴唇分开一条缝
        forbidden: [不要微笑, 不要摇头, 不要提前流泪]
"""


def cmd_new(args: argparse.Namespace) -> int:
    out = Path(args.out or f"{args.name}.yml")
    if out.exists() and not args.force:
        print(f"{out} 已存在，加 --force 覆盖")
        return 1
    out.write_text(SCAFFOLD.format(title=args.name), encoding="utf-8")
    print(f"已生成 {out}，填完 shots.beats 后运行：aiacting build {out}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    outdir = Path(args.out or "reference")
    video, title = ingest.download(args.url, outdir)
    print("标题：" + title)
    print("视频：" + str(video))
    audio = ingest.to_audio(video)
    print("音频：" + str(audio))
    sheet = post.contact_sheet(video, every=args.every)
    print("缩略图：" + str(sheet))
    if args.asr:
        print(ingest.transcribe(audio))
    return 0


def cmd_tts(args: argparse.Namespace) -> int:
    p = tts.synth(args.text, Path(args.out) if args.out else None, args.voice, args.rate)
    print(f"已生成 {p} 与 {p.with_suffix('.srt')}")
    return 0


def cmd_animatic(args: argparse.Namespace) -> int:
    proj = schema.load(args.project)
    from . import animatic

    if args.plan:
        print(animatic.plan_text(proj))
        return 0
    out = animatic.render(proj, Path(args.out), args.width, args.height, args.fps)
    print(f"已渲染 {out}（{args.width}x{args.height} @{args.fps}fps）")
    return 0


def cmd_post(args: argparse.Namespace) -> int:
    if args.action == "concat":
        p = post.concat([Path(x) for x in args.files], Path(args.out))
    elif args.action == "contact":
        p = post.contact_sheet(Path(args.files[0]), every=args.every)
    elif args.action == "sub":
        p = post.burn_subtitle(Path(args.files[0]), Path(args.files[1]))
    elif args.action == "loud":
        p = post.loudnorm(Path(args.files[0]))
    elif args.action == "probe":
        print(post.probe(Path(args.files[0])))
        return 0
    else:
        print("未知动作")
        return 1
    print("输出：" + str(p))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="aiacting", description="AI 表演提示词编译器（八维公式）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("au", help="查 FACS 动作单元 / 预设")
    p.add_argument("code", nargs="?")
    p.add_argument("--table", action="store_true")
    p.add_argument("--preset")
    p.set_defaults(func=cmd_au)

    p = sub.add_parser("check", help="校验项目 YAML")
    p.add_argument("project")
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("build", help="编译成完整提示词")
    p.add_argument("project")
    p.add_argument("-o", "--out")
    p.add_argument("--flat", action="store_true", help="输出单段纯文本版")
    p.add_argument("--layer", choices=["1", "2", "3", "all"], default="all")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("lint", help="给任意提示词做体检")
    p.add_argument("file", nargs="?")
    p.add_argument("-t", "--text")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("new", help="生成项目骨架")
    p.add_argument("name")
    p.add_argument("-o", "--out")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("ingest", help="下载参考视频并拆解")
    p.add_argument("url")
    p.add_argument("-o", "--out")
    p.add_argument("--every", type=float, default=8.0)
    p.add_argument("--asr", action="store_true", help="顺带转写（需 faster-whisper）")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("animatic", help="用代码渲染节拍预览片（不花积分）")
    p.add_argument("project")
    p.add_argument("-o", "--out", default="animatic.mp4")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--plan", action="store_true", help="只打印文本节拍表，不渲染")
    p.set_defaults(func=cmd_animatic)

    p = sub.add_parser("tts", help="免费配音")
    p.add_argument("text")
    p.add_argument("-o", "--out")
    p.add_argument("--voice", default="女-温柔")
    p.add_argument("--rate", default="+0%")
    p.set_defaults(func=cmd_tts)

    p = sub.add_parser("post", help="后期工具")
    p.add_argument("action", choices=["concat", "contact", "sub", "loud", "probe"])
    p.add_argument("files", nargs="+")
    p.add_argument("-o", "--out", default="out.mp4")
    p.add_argument("--every", type=float, default=3.0)
    p.set_defaults(func=cmd_post)
    return ap


def main(argv: list[str] | None = None) -> int:
    _fix_console()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, FileNotFoundError) as e:
        print(f"出错：{e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
