#!/usr/bin/env bash
# 重新获取可合法下载的全文
set -e
cd "$(dirname "$0")/books"
curl -L -o graphic-design-fundamentals.pdf \
  "https://opentextbc.ca/graphicdesign/open/download?type=pdf"
echo "done: $(ls -lh graphic-design-fundamentals.pdf | awk '{print $5}')"
