# 视觉方法书库

> 不只是存书，是把「概念 → 书与页码 → 代码参数」串起来，方便写片子时随时调用。

## 用法

```bat
python scripts\lib_cli.py list             :: 15 本书 + 获取状态
python scripts\lib_cli.py search 留白       :: 按概念/规则/代码字段搜
python scripts\lib_cli.py show anchor      :: 一条概念的完整链路
python scripts\lib_cli.py open bccampus-gd :: 本地文件或获取方式
```

## 目录

```
library/
├─ catalog.json      15 本书 + 16 条概念（概念带出处页码与代码字段）
├─ books/            已下载的全文（只放可合法下载的）
└─ README.md         本文件
```

## 目前有什么

| 状态 | 数量 | 说明 |
| --- | --- | --- |
| ✅ 本地全文 | 1 | BCcampus《Graphic Design and Print Production Fundamentals》，CC BY 4.0 |
| 🛒 需购买 | 9 | 阿恩海姆、贡布里希、Albers、Robin Williams、Müller-Brockmann、Samara、Molly Bang、Bruce Block、Mateu-Mestre |
| 📚 图书馆 | 3 | 朝仓直巳、辛华泉、王受之 |
| ⛔ 不可达 | 1 | 康定斯基《点线面》（archive.org 在本机被墙） |

**说明**：版权书不下盗版。只下载了公共领域或开放授权的，其余留获取路径，需要时去买或借。

## 为什么只下一本也够用

那本 CC BY 的教材第三章（p.55–93）正好覆盖**视觉元素（点线面/色彩/肌理/空间）→ 构图原则（平衡·对比·层级·节奏）→ 组织原则（网格·分组·对齐）**，这是我们引擎真正要用的部分。其余书补的是"为什么"和"更高层的判断"。

## 概念索引怎么建立的

每条概念三件事：

```json
{
  "id": "negative-space",
  "cn": "留白 / 负空间",
  "rule": "留白占 40–60%，主体朝向侧留白 ≥ 反侧 1.5 倍",
  "sources": [{"book": "bccampus-gd", "page": 58}, {"book": "picture-this", "chapter": "位置与情绪"}],
  "code": "composition.negative_space = left | right"
}
```

- `rule` 是可执行的判断（带数值）
- `sources` 指向具体页码或章节，不是"某本书里说过"
- `code` 直接对应渲染器的字段，写片子时照抄

## 补一本新书

1. 把 PDF 放进 `books/`（确认可合法分发）
2. 在 `catalog.json` 的 `books` 里加一条，`access: "local"`
3. 把它的章节页码补进相关 `concepts` 的 `sources`
4. `python scripts\lib_cli.py list` 验证

## 版权

`books/` 里的文件按原许可分发：
- Graphic Design and Print Production Fundamentals — CC BY 4.0，需保留署名，见 `books/ATTRIBUTION.md`
