# AI Acting Prompt Kit

**把「情绪」编译成「可执行的表演」。**

一条 30 秒、纯文本提示词、不垫图不垫视频的 AI 演技短片工作流。核心是一套从爆款教学视频里拆出来的**八维表演提示词公式**，加上一个能把它变成命令行工具的编译器。

> 不会再出现"她非常悲伤地哭泣"这种写法——因为 AI 看不见心理，只看得见证据。

---

## 它解决什么问题

你写 `女人愤怒地哭泣`，模型会把愤怒和哭**同时**端上来，因为它在求并集。

真人不是这样的：人先用愤怒保护自己，保护层撑不住了，悲伤才漏出来。**你要给的不是状态，是曲线。**

这个仓库干三件事：

1. **把曲线写成结构**（YAML）—— 三层提示词 × 八个维度
2. **把结构编译成提示词**（`build`）—— 一份可直接粘贴给小云雀 / Seedance 2.5 的文本
3. **在生成之前就抓出毛病**（`check` / `lint`）—— 缺目的、缺触发词、缺禁止项、AU 编号写错

> **不想装任何东西？** 直接打开 [`AI表演提示词调试台.md`](AI表演提示词调试台.md)，
> 整个文件粘给任意 AI，填完最后一栏，就能在对话里一拍一拍改提示词。
> 那个文件里自带角色设定、八维公式、AU 表、症状诊断表和自检清单，不依赖本仓库的任何代码。

---

## 三十秒上手

**第一次用，先看 [`docs/06-五分钟上手.md`](docs/06-五分钟上手.md)** —— 从零到拿到一条能粘贴的提示词，全程不用写代码。

```bash
# 1. 跑一个 10 秒单镜头的样板，看清提示词长什么样
aiacting build examples/quickstart-10s.yml -o prompt.txt

# 2. 建一个自己的项目骨架（里面已经有一场可直接跑 3.7 秒的样板）
./aiacting.sh new 我的戏

# 3. 看完整的 30 秒四镜头范本
cat examples/what-about-my-life.yml

# 4. 体检
./aiacting.sh check examples/what-about-my-life.yml

# 5. 编译成提示词
./aiacting.sh build examples/what-about-my-life.yml -o prompt.txt
```

然后打开 **小云雀 AI → Agent → Seedance 2.5**，设 30 秒 / 横屏 / 开原声，把 `prompt.txt` 整段粘进去。

> Windows 用 `aiacting.cmd`，macOS / Linux 用 `./aiacting.sh`，也可以 `pip install -e .` 之后直接用 `aiacting`。

---

## 本地安装（不走 GitHub，不联网也能用）

克隆不下来、或者访问 GitHub 有问题时，直接用本机这份源码装一遍：

```powershell
# 在项目根目录
powershell -ExecutionPolicy Bypass -File scripts\install_local.ps1
```

脚本会做四件事：建 `.venv` → `pip install -e .` → 在 `%USERPROFILE%\bin` 放入口 →
确保该目录在用户 PATH。完成后**新开一个终端**，任何目录都能直接敲：

```
aiacting check examples\what-about-my-life.yml
aiacting build examples\what-about-my-life.yml -o prompt.txt
```

> 控制台如果出现乱码，先执行 `chcp 65001`。程序统一输出 UTF-8，不混用 GBK。
>
> 卸载：删掉 `%USERPROFILE%\bin\aiacting.cmd` 和项目里的 `.venv` 即可，不写注册表、不进系统目录。

---

## 八维公式

```
01 时间段        02 人物目的      03 情绪变化      04 台词触发词
05 面部动作与AU  06 目光和身体    07 声音、呼吸与停顿   08 结束状态与禁止反应
```

这不是检查表，是因果链：

| 维度 | 它在回答什么 | 缺了会怎样 |
| --- | --- | --- |
| 时间段 | 什么时候发生 | 模型平均分配，情绪变一条平线 |
| 人物目的 | 她想要什么 | 情绪没有动机，观众觉得她无理取闹 |
| 情绪变化 | 从哪到哪 | 愤怒和哭同时端上来 |
| 台词触发词 | 哪个词让它变 | 表情随机落在某个字上 |
| 面部动作与AU | 哪块肌肉在动 | 只有形容词，模型自己编 |
| 目光和身体 | 眼睛在躲还是在钉 | 只有脸在动，像贴图 |
| 声音呼吸停顿 | 哪里**没有**声音 | 一口气念完，没有气口 |
| 结束状态与禁止 | 她停在哪、什么不许提前 | 每段都演满，没有留白 |

完整说明见 [`docs/01-八维公式手册.md`](docs/01-八维公式手册.md)。

---

## 三层提示词结构

```
LAYER 01  全局控制      只搭片场：时长/画幅/年代/场景/人物一致性 —— 不写表演
LAYER 02  镜头时间轴     分几个镜头、几秒、机位、观察谁 —— 按镜头分级，时间码做子集
LAYER 03  表演控制      八维公式落点 —— 真正决定这个 AI 演员会不会演
```

判断标准：**删掉一句话，画面还是那个画面 → 它属于第三层；删掉之后人物会变脸 → 它必须留在第一层。**

---

## 命令

| 命令 | 作用 |
| --- | --- |
| `aiacting new <名字>` | 生成项目骨架 |
| `aiacting check <yml>` | 结构体检（时间码 / AU / 缺项 / 节拍过长） |
| `aiacting build <yml>` | 编译成提示词（`--flat` 出单段纯文本版） |
| `aiacting lint <文件>` | 给任意旧提示词做体检 |
| `aiacting au AU7` | 查 FACS 动作单元 |
| `aiacting au --preset 悲伤` | 取现成的情绪预设 |
| `aiacting ingest <url>` | 拆别人的片子：下载 / 抽音 / 抽帧拼图 |
| `aiacting tts "台词"` | 免费中文配音 + 自动生成 srt |
| `aiacting post concat/loud/sub/contact/probe` | 拼镜头 / 压响度 / 烧字幕 / 抽帧质检 |

全部参数见 [`docs/02-命令手册.md`](docs/02-命令手册.md)。

---

## 一个真实的体检输出

```bash
$ aiacting lint -t "女人非常悲伤地哭泣，眼泪止不住流下来。"
! 建议修（3）
   · 「女人非常悲伤地哭泣，眼泪止不住流下来」只给了情绪词（悲伤），没有可见动作，模型会自己编
   · 「女人非常悲伤地哭泣，眼泪止不住流下来」用了程度副词「非常」，模型无法量化，改成幅度或秒数
   · 全文没有禁止项（NO），模型会把情绪提前演满
```

改成：

> 眉毛内侧缓慢抬起，嘴角轻微下沉，下巴开始绷紧；张开嘴想继续说话，却没有立刻发出声音；眼眶逐渐湿润，但**眼泪暂时不能落下**。辅助校准：AU1:3，AU15:2，AU17:2。

---

## 目录

```
AI表演提示词调试台.md  单文件调试台（粘给任意 AI，不依赖代码）
aiacting/          编译器（schema / compiler / lint / au / post / ingest / tts / cli）
data/au.json       28 个常用 FACS 动作单元 + 5 组情绪预设
examples/          quickstart-10s（入门）+ what-about-my-life（30 秒完整范本）
docs/              00 视频拆解 ｜ 01 八维手册 ｜ 02 命令手册 ｜ 03 硬件现实 ｜ 04 开源生态 ｜ 05 本地安装 ｜ 06 五分钟上手 ｜ 07 平台与额度 ｜ 08 本机实测
scripts/           环境安装、远程 GPU 骨架
```

---

## 关于硬件：说清楚

作者的成片是**云端生成**的，不是本地跑的。这个仓库也建议你这么做：

| 环节 | 在哪跑 | 为什么 |
| --- | --- | --- |
| 提示词设计 / 体检 / 编译 | 本机（纯 CPU） | 计算量为零 |
| 视频生成 | 云端（小云雀 / Seedance 2.5） | 2 GB 显存连权重都放不下 |
| 抽帧质检 / 拼接 / 字幕 / 响度 | 本机（ffmpeg） | CPU 足够 |
| 配音 | 本机（edge-tts） | 免费、够用 |

详细测算见 [`docs/03-本机方案与硬件现实.md`](docs/03-本机方案与硬件现实.md)。想跑开源模型（Wan-Animate-2 / InfiniteTalk / HunyuanVideo-Avatar）需要 24 GB 显存，用 `scripts/remote_gpu_setup.sh` 去租卡，不在本机硬撑。

开源生态里各层有什么、缺什么，见 [`docs/04-开源生态调研.md`](docs/04-开源生态调研.md)。一句话结论：**生成层的轮子很全，控制层几乎是空的**——这也是为什么那套写法值钱。

---

## Roadmap

- [x] v0.1 三层结构 + 八维公式编译、体检、后期、拆片、配音
- [ ] v0.2 `aiacting analyze <video>`：用 [OpenFace](https://github.com/TadasBaltrusaitis/OpenFace) 提取 AU 时间序列，自动生成 beat 骨架
- [ ] v0.3 角色一致性检查：多镜头间人脸比对，发现漂移就报警
- [ ] v0.4 多语言台词对齐（中英日），自动换算口型时长

---

## 方法来源

本仓库的方法论拆解自抖音 **@foyege** 的教程《400万播放的AI爆款演技短片：我把唐国强老师的表演法则，写进了AI提示词》（视频 ID `7669413558211778661`）。

逐段拆解、原话引用、幻灯片原文见 [`docs/00-视频拆解.md`](docs/00-视频拆解.md)。

AU 体系来自 **FACS**（Facial Action Coding System, Ekman & Friesen）。AU 不是情绪公式——同一个 AU4 配上不同组合，可以是愤怒，也可以是痛苦。永远先写人话，再用 AU 校准。

`examples/what-about-my-life.yml` 是按八维公式**反向重建**的同结构范本，不是原作者提示词的拷贝（原文在视频里始终以小字窗口出现，未公开全屏）。

---

## License

MIT
