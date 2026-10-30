# 换标题出片：.\scripts\make_intro.ps1 -Title 魏晋 -Sub "公元 220 — 公元 589" -Kicker 第二章 -Tag 史
param(
  [string]$Title  = "秦汉",
  [string]$Sub    = "公元前 221 — 公元 220",
  [string]$Kicker = "第一章",
  [string]$Tag    = "史",
  [string]$Years  = "前221,前202,220",
  [string]$Quality = "-qh"
)
$env:INTRO_TITLE  = $Title
$env:INTRO_SUB    = $Sub
$env:INTRO_KICKER = $Kicker
$env:INTRO_TAG    = $Tag
$env:INTRO_YEARS  = $Years
$env:PATH = "D:/video-stack/tools/ffmpeg/bin;D:/video-stack/python/venv/Scripts;$env:PATH"
python -m manim $Quality --fps 30 scripts\manim_history_intro.py HistoryIntro
Write-Output "产出：media\videos\manim_history_intro\1080p30\HistoryIntro.mp4"
