# 在「租来的 GPU 机器」上跑这个脚本，不要在本地笔记本跑。
# 用途：装好 Wan-Animate-2 / InfiniteTalk 这类需要 24GB 显存的开源方案，
#      做「表演迁移」（把真人表演搬到 AI 角色上）或固定角色的长镜头。
#
# 前置：Ubuntu 22.04 + CUDA 12.1 镜像，显存 >= 24GB（A10 / 4090 / L20 / A100）

set -euo pipefail

WORK=${WORK:-/workspace}
mkdir -p "$WORK" && cd "$WORK"

echo "== 0. 环境自检 =="
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
python3 --version

echo "== 1. 基础依赖 =="
apt-get update -qq && apt-get install -y -qq git ffmpeg libgl1 libglib2.0-0 >/dev/null

echo "== 2. Python 环境 =="
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip

echo "== 3. 拉取模型仓库 =="
# 按需取消注释，别一次全装（磁盘和显存都吃不住）
# --- 人物动画 / 表演迁移 ---
# git clone https://github.com/Wan-Video/Wan2.2.git
# git clone https://github.com/MeiGen-AI/InfiniteTalk.git
# --- 口型对齐 ---
# git clone https://github.com/Tencent-Hunyuan/HunyuanVideo-Avatar.git
# --- 表情驱动（轻量，可先验流程） ---
# git clone https://github.com/KlingAIResearch/LivePortrait.git

echo "== 4. 装 PyTorch（按 CUDA 版本） =="
pip install -q torch torchvision --index-url https://download.pytorch.org/whl/cu121

echo "== 5. 下载权重 =="
# 权重动辄 30-70 GB，确认磁盘够再下
# huggingface-cli download Wan-AI/Wan2.2-Animate-14B --local-dir "$WORK/weights/wan-animate"

echo "== 6. 跑一条最小样例 =="
# 具体命令看各自仓库的 README，务必先用 480p / 5 秒跑通再上 1080p

cat <<'EOF'

完成后把成片拉回本机，用本仓库收尾：

  aiacting post concat shot*.mp4 -o final.mp4
  aiacting post loud final.mp4
  aiacting post contact final.mp4          # 检查人物有没有漂移

注意：租来的机器用完就关，按小时计费。训练/推理脚本请放在持久盘，
      实例释放后系统盘会清空。
EOF
