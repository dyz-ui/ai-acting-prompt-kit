"""把 library/catalog.json 变成脑图

产出三样：
  library/视觉方法书库.xmind   XMind 直接打开（含书↔概念↔代码的关联线）
  library/mindmap.png          两栏连线预览图，不用装软件也能看
  library/mindmap.md           大纲，可导入幕布/Notion/Obsidian

    python scripts/make_mindmap.py
"""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "library"
CAT = LIB / "catalog.json"

F_HEI = "C:/Windows/Fonts/msyhbd.ttc"
F_REG = "C:/Windows/Fonts/msyh.ttc"

ACCESS_COLOR = {
    "local": (46, 160, 110),
    "buy": (200, 140, 40),
    "library": (70, 120, 190),
    "blocked": (170, 90, 90),
}
ACCESS_CN = {"local": "本地", "buy": "购买", "library": "图书馆", "blocked": "不可达"}


def nid() -> str:
    return uuid.uuid4().hex[:12]


def topic(title: str, children=None, note: str | None = None, marker: str | None = None) -> dict:
    t = {"id": nid(), "class": "topic", "title": title}
    if note:
        t["notes"] = {"plain": {"content": note}}
    if marker:
        t["markers"] = [{"markerId": marker}]
    if children:
        t["children"] = {"attached": children}
    return t


def build_xmind(cat: dict, path: Path) -> None:
    books = cat["books"]
    concepts = cat["concepts"]

    # ---- 分支一：书 ----
    book_topics = {}
    groups = {"local": [], "buy": [], "library": [], "blocked": []}
    for b in books:
        groups[b["access"]].append(b)

    book_branch = []
    for key, label in (("local", "✅ 本地全文"), ("buy", "🛒 需购买"),
                       ("library", "📚 图书馆"), ("blocked", "⛔ 不可达")):
        if not groups[key]:
            continue
        kids = []
        for b in groups[key]:
            note = f"{b['author']}（{b['year']}）\n{b['license']}\n\n为什么读：{b['why']}"
            if b.get("sections"):
                note += "\n\n相关章节：\n" + "\n".join(
                    f"· {k}" + (f" p.{v}" if v else "") for k, v in b["sections"].items())
            if b.get("route"):
                note += f"\n\n获取：{b['route']}"
            node = topic(b["title"], note=note)
            book_topics[b["id"]] = node["id"]
            kids.append(node)
        book_branch.append(topic(f"{label}（{len(groups[key])}）", kids))

    # ---- 分支二：概念 ----
    concept_topics = {}
    concept_branch = []
    for c in concepts:
        note = f"规则：{c['rule']}\n\n代码：{c['code']}"
        if c.get("quote"):
            note += f"\n\n原文：「{c['quote']}」"
        src = []
        for s in c["sources"]:
            b = next((x for x in books if x["id"] == s["book"]), None)
            if b:
                loc = f" p.{s['page']}" if s.get("page") else f" {s.get('chapter','')}"
                src.append(f"《{b['title']}》{loc}")
        if src:
            note += "\n\n出处：\n" + "\n".join("· " + x for x in src)
        node = topic(c["cn"], note=note)
        concept_topics[c["id"]] = node["id"]
        concept_branch.append(node)

    # ---- 分支三：代码字段 ----
    field_groups: dict[str, list] = {}
    for c in concepts:
        code = c["code"].split("=")[0].strip().split(":")[0].strip()
        root_field = code.split(".")[0].split()[0] or "其他"
        field_groups.setdefault(root_field, []).append(topic(c["cn"], note=c["code"]))
    code_branch = [topic(f"{k}()", v) for k, v in field_groups.items()]

    root = topic("视觉方法书库", [
        topic(f"一、书（{len(books)}）", book_branch),
        topic(f"二、概念（{len(concepts)}）", concept_branch),
        topic("三、代码字段", code_branch),
    ])

    # ---- 关联线：书 ↔ 概念 ----
    rels = []
    for c in concepts:
        for s in c["sources"]:
            if s["book"] in book_topics:
                rels.append({"id": nid(), "end1Id": book_topics[s["book"]],
                             "end2Id": concept_topics[c["id"]], "title": "支撑"})

    content = [{
        "id": nid(),
        "class": "sheet",
        "title": "视觉方法书库",
        "rootTopic": root,
        "relationships": rels,
    }]
    meta = {"creator": {"name": "aiacting", "version": "1.0"}}

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.json", json.dumps(content, ensure_ascii=False, indent=2))
        z.writestr("metadata.json", json.dumps(meta, ensure_ascii=False))
        z.writestr("manifest.json", json.dumps(
            {"file-entries": {"content.json": {}, "metadata.json": {}}}, ensure_ascii=False))
    print(f"xmind : {path}  ({path.stat().st_size / 1024:.0f} KB, {len(rels)} 条关联)")


def build_png(cat: dict, path: Path) -> None:
    W, H = 2400, 1800
    img = Image.new("RGB", (W, H), (250, 248, 243))
    d = ImageDraw.Draw(img)
    f_title = ImageFont.truetype(F_HEI, 46)
    f_head = ImageFont.truetype(F_HEI, 24)
    f_item = ImageFont.truetype(F_REG, 19)
    f_small = ImageFont.truetype(F_REG, 15)

    books = cat["books"]
    concepts = cat["concepts"]
    left_x, right_x = 80, 1330
    top = 190
    lh_b, lh_c = 94, 84
    bw, cw = 780, 990

    d.text((80, 62), "视觉方法书库", font=f_title, fill=(30, 28, 26))
    d.text((82, 122), f"{len(books)} 本书 · {len(concepts)} 条概念 · 连线只画主出处（完整关系见 .xmind）",
           font=f_small, fill=(120, 112, 100))

    d.text((left_x, top - 50), "书", font=f_head, fill=(60, 56, 50))
    by_id = {}
    for i, b in enumerate(books):
        y = top + i * lh_b
        col = ACCESS_COLOR[b["access"]]
        d.rounded_rectangle([left_x, y, left_x + bw, y + 72], radius=10,
                            fill=(255, 255, 255), outline=(228, 222, 210))
        d.rectangle([left_x, y, left_x + 8, y + 72], fill=col)
        title = b["title"]
        if len(title) > 58:
            title = title[:57] + "…"
        if " " in title[:29]:
            cut = title[:29].rfind(" ")
            l1, l2 = title[:cut], title[cut + 1:]
        else:
            l1, l2 = title[:29], title[29:]
        d.text((left_x + 26, y + 7), l1, font=f_item, fill=(36, 34, 32))
        if l2:
            d.text((left_x + 26, y + 29), l2, font=f_item, fill=(36, 34, 32))
        d.text((left_x + 26, y + 50), f"{b['year']} · {ACCESS_CN[b['access']]}",
               font=f_small, fill=col)
        by_id[b["id"]] = (left_x + bw, y + 36)

    d.text((right_x, top - 50), "概念 → 代码字段", font=f_head, fill=(60, 56, 50))
    cpos = {}
    for i, c in enumerate(concepts):
        y = top + i * lh_c
        d.rounded_rectangle([right_x, y, right_x + cw, y + 62], radius=10,
                            fill=(255, 255, 255), outline=(228, 222, 210))
        d.text((right_x + 22, y + 8), c["cn"], font=f_item, fill=(36, 34, 32))
        code = c["code"]
        if len(code) > 62:
            code = code[:61] + "…"
        d.text((right_x + 22, y + 36), code, font=f_small, fill=(122, 114, 102))
        cpos[c["id"]] = (right_x, y + 31)

    # 只连主出处，一本书一种线色，便于追踪
    HUES = [(198, 120, 90), (120, 150, 190), (150, 170, 120), (190, 150, 190),
            (120, 170, 170), (200, 170, 110), (160, 130, 110), (140, 140, 180),
            (180, 120, 140), (110, 150, 130), (170, 160, 120), (130, 160, 190),
            (190, 140, 120), (150, 140, 160), (170, 170, 150)]
    hue_of = {b["id"]: HUES[i % len(HUES)] for i, b in enumerate(books)}
    for ci, c in enumerate(concepts):
        src = next((x for x in c["sources"] if x["book"] in by_id), None)
        if not src:
            continue
        x1, y1 = by_id[src["book"]]
        x2, y2 = cpos[c["id"]]
        dx = x2 - x1
        c1 = (x1 + dx * 0.45, y1)
        c2 = (x1 + dx * 0.55, y2)
        pts = []
        for k in range(28):
            t = k / 27
            bx = (1 - t) ** 3 * x1 + 3 * (1 - t) ** 2 * t * c1[0] + 3 * (1 - t) * t ** 2 * c2[0] + t ** 3 * x2
            by = (1 - t) ** 3 * y1 + 3 * (1 - t) ** 2 * t * c1[1] + 3 * (1 - t) * t ** 2 * c2[1] + t ** 3 * y2
            pts.append((bx, by))
        d.line(pts, fill=hue_of[src["book"]], width=3, joint="curve")

    img.save(path)
    print(f"png   : {path}")


def build_md(cat: dict, path: Path) -> None:
    lines = ["# 视觉方法书库", ""]
    lines.append("## 书")
    for b in cat["books"]:
        lines.append(f"- **{b['title']}**（{b['author']}，{b['year']}）— {ACCESS_CN[b['access']]}")
        lines.append(f"  - {b['why']}")
    lines.append("")
    lines.append("## 概念")
    for c in cat["concepts"]:
        lines.append(f"- **{c['cn']}**（{c['en']}）")
        lines.append(f"  - 规则：{c['rule']}")
        lines.append(f"  - 代码：`{c['code']}`")
        for s in c["sources"]:
            b = next((x for x in cat["books"] if x["id"] == s["book"]), None)
            if b:
                loc = f"p.{s['page']}" if s.get("page") else s.get("chapter", "")
                lines.append(f"  - 出处：{b['title']} {loc}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"md    : {path}")


def main() -> None:
    cat = json.loads(CAT.read_text(encoding="utf-8"))
    build_xmind(cat, LIB / "视觉方法书库.xmind")
    build_png(cat, LIB / "mindmap.png")
    build_md(cat, LIB / "mindmap.md")


if __name__ == "__main__":
    main()
