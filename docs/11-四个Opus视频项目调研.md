# 四个「代码做视频」开源项目 · 调研与取舍

> 来源：抖音 @特黑洞Lab《Claude Opus 5.5 视频制作的四大神器》（57 秒）
> 视频里报的是语音识别后的名字，这里都核对到了真实仓库。检索时间 2026-10-31。

---

## 一、四个项目分别是什么

| 视频里的叫法 | 真实仓库 | 星标 | 许可 | 实质 |
| --- | --- | --- | --- | --- |
| "Lemon opus car"（实为「那么 OPUSCAR」） | [lemomo-ai/lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar) | 9.8k | MIT | **66 个用代码做片的风格库**，每个风格 = 一份 STYLE.md 规格书 + 一条示例片 + 源码 |
| awesome-opus5-5-videos | [yihui-dev/awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos) | 12.8k | MIT | 爆款视频合集 + 原始 prompt + 出处链接 |
| "PDM video"（实为 P(doom) video） | [mexicat/pdoom-video](https://github.com/mexicat/pdoom-video) | 3.7k | MIT | 一支音乐视频的完整源码：分镜、动画指南、渲染脚本全公开 |
| opusvideo prompts | [joeseesun/opus-video-prompts](https://github.com/joeseesun/opus-video-prompts) | 860 | 未标 | 54 个可复制提示词 + 案例，中文 |

**共同点：全部是「用代码渲染画面」，不调用任何视频生成模型。** 和我们这套 Manim / PIL 管线是同一条路。

---

## 二、lemo-opuscar：这个最值钱

它的目录结构是这样的：

```
styles/
  chalkboard/          ← 一个风格
    STYLE.md           ← 18 KB 的视觉规格书（这就是精华）
    DEMO.md            ← 示例片的镜头说明
    style.json         ← 元数据
    demo/              ← 渲染源码
    poster.jpg / .srt
  dataviz/  blueprint/  dark-keynote/  briefing-board/
  caption-news/  countdown/  art-deco/  ascii-crt/ ...
```

`style.json` 长这样：

```json
{
 "slug": "chalkboard", "num": "73", "cn": "黑板粉笔",
 "category_cn": "手绘与绘画",
 "film": "The Story of Chinese Characters",
 "line_cn": "粉笔写下网上的说法，再一擦，把「射」写回三千年前。",
 "uses": ["Word origins", "Myth-busting", "Lessons"]
}
```

`STYLE.md` 的骨架（这是真正可复用的部分）：

1. **一句话本质** + 明确的"它不是什么"（比如黑板 ≠ 白板讲解，逐条列出区别）
2. **材质与渲染**：画布用什么、每个笔触怎么烘、光怎么打
3. **配色逻辑**：每种颜色只准干一件事（白粉笔写结构、橙粉笔只标被讲的那个部件）
4. **字体规则**：中文用笔画数据不是字体轮廓、英文用哪一款
5. 后面还有分镜节奏、时长、字幕、常见错误

**这套写法的价值不在代码，在于把"感觉"变成了可交付的规格。** 我们的 Manim 片头现在是凭手感调的，换个人做就变样；有了 STYLE.md，风格可以交接。

### 直接能用的风格（对课件）

| 风格 | 中文名 | 为什么对课件有用 |
| --- | --- | --- |
| `chalkboard` | 黑板粉笔 | 天生就是课堂，讲一个概念的由来最贴 |
| `dataviz` | 数据可视化 | 讲经济史、人口史、战争伤亡 |
| `blueprint` | 蓝图 | 讲技术史、工程史、地图 |
| `briefing-board` | 简报板 | 讲事件时间线、战役推演 |
| `dark-keynote` | 深色演讲 | 发布会感的章节片头 |
| `countdown` | 倒计时 | 考前复习、章节切换 |

---

## 三、pdoom-video：工程结构值得抄

一支 6 分钟的代码渲染 MV，仓库里有：

```
docs/ENGINE.md       渲染引擎说明
docs/TREATMENT.md    创作阐述（为什么这么拍）
STORYBOARD.md        逐镜头分镜表
ANIMATION_GUIDE.md   动画规范
src/ lyrics/ audio/ analysis/ app/
```

`STORYBOARD.md` 的格式是一张表：

| 时间 | 画面 | 动作 | 转场 |
| --- | --- | --- | --- |
| 0.0–1.5 | 红色幕布拉开，"I'M UPPING MY P(DOOM)" 绘在背景上 | Clawd 从地板门钻出挥手 | 笔刷擦除 |

**这正是我们片头缺的东西。** 现在 `manim_history_intro.py` 里的时间全散在 `run_time` 参数里，没人能一眼看出"第 4 秒在干什么"。

---

## 四、另外两个：参考价值 > 直接使用

**awesome-opus5-5-videos**：12.8k 星，本质是个索引站（README + data/ + prompts/）。适合"想看某个效果别人怎么写的"时翻。做课件片头用不上，但找灵感快。

**opus-video-prompts**：54 个 prompt，中文。案例多是"一句话出片"的短视频，跟课件这种要精确控制排版的需求差得远。当语料看可以。

---

## 五、结论：抄什么，不抄什么

### 要抄

1. **STYLE.md 这个文体** —— 立刻用。给我们的历史片头写一份规格书，把"纸感 + 墨色 + 锈红印章"从手感变成可复现的规则。
2. **STORYBOARD.md 的时间轴表** —— 立刻用。片头 10 秒也只有 9 个动作，列出来比埋在代码里强。
3. **配色职责制** —— 每种颜色只管一件事。我们现在的锈红既做章节号又做印章，其实已经有点冲突。

### 不抄

1. **不装 Claude Code 插件** —— 它是 `.claude-plugin` 形态，我们不需要，规格书本身是纯 Markdown。
2. **不追它的 Canvas/WebGL 实现** —— 那是给浏览器渲染的，我们走 Manim/PIL，结论一致但实现不同。
3. **不搬示例片** —— 风格是别人的，课件要自己的视觉语言。

### 落地动作

- [x] 按 STYLE.md 文体给历史片头写一份规格 → `docs/12-片头视觉规格.md`
- [x] 加一个「黑板粉笔」变体（同一套代码，换配色与质感）→ `make_intro.ps1 -Style chalk`
- [x] 给片头补一张 STORYBOARD 时间轴表
