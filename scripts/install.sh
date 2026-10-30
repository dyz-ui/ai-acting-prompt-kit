#!/usr/bin/env bash
# 一键装好本机环境（只需要 Python 3.9+ 与 ffmpeg）
set -e
cd "$(dirname "$0")/.."

echo "== 检查前置 =="
command -v ffmpeg >/dev/null || { echo "缺 ffmpeg，请先安装并加入 PATH"; exit 1; }
ffmpeg -version | head -1

PY=${PYTHON:-python3}
$PY -c "import sys; assert sys.version_info >= (3,9), '需要 Python 3.9+'" || exit 1

echo "== 创建虚拟环境 =="
$PY -m venv .venv
if [ -x .venv/Scripts/python.exe ]; then VPY=.venv/Scripts/python; else VPY=.venv/bin/python; fi

echo "== 安装依赖 =="
$VPY -m pip install -q --upgrade pip
$VPY -m pip install -q -r requirements.txt

echo "== 自检 =="
$VPY -m aiacting au AU7 >/dev/null && echo "  ✓ 编译器可用"
$VPY -m pip show edge-tts >/dev/null 2>&1 && echo "  ✓ 配音可用"
$VPY -m pip show yt-dlp   >/dev/null 2>&1 && echo "  ✓ 抓片可用"
echo
echo "完成。试试： ./aiacting.sh check examples/what-about-my-life.yml"
