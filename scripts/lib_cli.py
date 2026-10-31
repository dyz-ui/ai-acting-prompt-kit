"""书库检索：概念 → 书与页码 → 代码参数

    python scripts/lib_cli.py list                 列出书目与获取状态
    python scripts/lib_cli.py search 留白           按概念/规则/字段搜
    python scripts/lib_cli.py show anchor          看一条概念的完整链路
    python scripts/lib_cli.py open bccampus-gd     打印本地文件路径或获取方式
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAT = ROOT / "library" / "catalog.json"

ACCESS_CN = {"local": "✅ 本地", "buy": "🛒 购买", "library": "📚 图书馆", "blocked": "⛔ 网络不可达"}


def load() -> dict:
    return json.loads(CAT.read_text(encoding="utf-8"))


def cmd_list(cat: dict) -> None:
    books = cat["books"]
    w = max(len(b["title"]) for b in books)
    print(f"{'书名':<{w}}  {'年':<6} {'获取':<12} 说明")
    print("-" * (w + 60))
    for b in books:
        print(f"{b['title']:<{w}}  {b['year']:<6} {ACCESS_CN.get(b['access'], b['access']):<12} {b['why'][:38]}")
    local = sum(1 for b in books if b["access"] == "local")
    print(f"\n共 {len(books)} 本，本地有全文 {local} 本，概念 {len(cat['concepts'])} 条")


def book_by_id(cat: dict, bid: str) -> dict | None:
    for b in cat["books"]:
        if b["id"] == bid:
            return b
    return None


def cmd_search(cat: dict, kw: str) -> None:
    hits = []
    for c in cat["concepts"]:
        blob = " ".join([c["cn"], c["en"], c["rule"], c["code"]]).lower()
        if kw.lower() in blob:
            hits.append(c)
    if not hits:
        print(f"没找到「{kw}」。试：主体 留白 对比 节奏 网格 肌理 眯眼")
        return
    for c in hits:
        print(f"\n▸ {c['cn']}（{c['en']}）")
        print(f"  规则：{c['rule']}")
        for s in c["sources"]:
            b = book_by_id(cat, s["book"])
            if not b:
                continue
            loc = f"p.{s['page']}" if s.get("page") else (s.get("chapter") or "全书")
            mark = "" if b["access"] == "local" else f"（{ACCESS_CN.get(b['access'])}）"
            print(f"  出处：{b['title']} {loc}{mark}")
        if c.get("quote"):
            print(f"  原文：{c['quote'][:90]}")
        print(f"  代码：{c['code']}")


def cmd_show(cat: dict, cid: str) -> None:
    for c in cat["concepts"]:
        if c["id"] == cid or c["cn"] == cid:
            print(f"▸ {c['cn']}（{c['en']}）\n")
            print(f"规则：{c['rule']}\n")
            print("出处：")
            for s in c["sources"]:
                b = book_by_id(cat, s["book"])
                if not b:
                    continue
                loc = f"p.{s['page']}" if s.get("page") else (s.get("chapter") or "全书")
                extra = ""
                if b["access"] == "local":
                    extra = f" → {b['file']}"
                elif b.get("route"):
                    extra = f" → {b['route']}"
                print(f"  · {b['title']}（{b['year']}）{loc}{extra}")
            if c.get("quote"):
                print(f"\n原文：「{c['quote']}」")
            print(f"\n代码：{c['code']}")
            print("\n怎么用：把上面这条规则翻成一句话写进 codevideo.yml 的 composition / style 里，")
            print("        渲完用 docs/18 的自检八条过一遍。")
            return
    print(f"没有 id 为 {cid} 的概念")


def cmd_open(cat: dict, bid: str) -> None:
    b = book_by_id(cat, bid)
    if not b:
        print(f"没有 id 为 {bid} 的书；用 list 看全部")
        return
    print(f"《{b['title']}》{b['author']}（{b['year']}）· {b['license']} · {ACCESS_CN.get(b['access'])}")
    if b["access"] == "local":
        p = ROOT / "library" / b["file"]
        print(f"本地文件：{p}")
        print(f"存在：{p.exists()}  大小：{p.stat().st_size / 1024 / 1024:.1f} MB" if p.exists() else "文件缺失")
        if b.get("sections"):
            print("相关章节：")
            for k, v in b["sections"].items():
                print(f"  · {k}" + (f" p.{v}" if v else ""))
    else:
        print(f"获取方式：{b.get('route') or '购买正版 / 图书馆借阅'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "search", "show", "open"])
    ap.add_argument("arg", nargs="?")
    a = ap.parse_args()
    if not CAT.exists():
        sys.exit("找不到 library/catalog.json")
    cat = load()
    if a.cmd == "list":
        cmd_list(cat)
    elif a.cmd == "search":
        cmd_search(cat, a.arg or "")
    elif a.cmd == "show":
        cmd_show(cat, a.arg or "")
    else:
        cmd_open(cat, a.arg or "")


if __name__ == "__main__":
    main()
