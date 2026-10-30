"""FACS / AU 查询与强度换算。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

_DATA = Path(__file__).resolve().parent.parent / "data" / "au.json"

INTENSITY_CN = {1: "A 极轻", 2: "B 轻", 3: "C 中等", 4: "D 强", 5: "E 极强"}


class AULibrary:
    def __init__(self, path: Optional[Path] = None) -> None:
        raw = json.loads(Path(path or _DATA).read_text(encoding="utf-8"))
        self.meta: Dict = raw.get("meta", {})
        self.presets: Dict[str, dict] = raw.get("presets", {})
        self.au: Dict[str, dict] = {}
        for item in raw["au"]:
            self.au[item["code"].upper()] = item
        self._alias: Dict[str, str] = {}
        for code, item in self.au.items():
            self._alias[item["cn"]] = code
            self._alias[item["en"].lower()] = code

    # ---------- 查询 ----------
    def get(self, code: str) -> dict:
        key = code.strip().upper()
        if key not in self.au:
            key = self._alias.get(code.strip(), "")
        if not key:
            raise KeyError(f"未知 AU：{code}")
        return self.au[key]

    def describe(self, spec: str) -> str:
        """'AU7:3' -> '眼睑收紧（AU7，C 中等）'"""
        code, _, level = spec.partition(":")
        item = self.get(code)
        lv = int(level) if level.strip().isdigit() else 3
        lv = max(1, min(5, lv))
        return f"{item['cn']}（{item['code']}，{INTENSITY_CN[lv]}）"

    def natural_sentence(self, specs: List[str]) -> str:
        """把 AU 列表翻成一句自然语言（用于 prompt 面部行）。"""
        parts = [self.get(s.split(":")[0])["prompt"] for s in specs]
        return "；".join(parts)

    # ---------- 输出 ----------
    def table(self) -> str:
        rows = [
            "| 编号 | 动作 | 英文 | 区域 | 读起来像 | 提示词写法 |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for code, it in self.au.items():
            rows.append(
                f"| {code} | {it['cn']} | {it['en']} | {it['region']} | {it['feel']} | {it['prompt']} |"
            )
        return "\n".join(rows)

    def list_codes(self, region: Optional[str] = None) -> List[str]:
        return [c for c, it in self.au.items() if region is None or it["region"] == region]


def validate_specs(specs: List[str], lib: AULibrary) -> List[str]:
    """返回错误列表，空列表表示通过。"""
    errors: List[str] = []
    for spec in specs:
        code, _, level = str(spec).partition(":")
        try:
            lib.get(code)
        except KeyError:
            errors.append(f"AU 编号不存在：{code}")
            continue
        if level and not (level.strip().isdigit() and 1 <= int(level) <= 5):
            errors.append(f"{code} 的强度必须是 1-5（A-E），当前为 {level!r}")
    return errors
