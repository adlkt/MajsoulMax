#!/bin/bash
cd "$(dirname "$0")"

PORT=23410
if lsof -ti:$PORT > /dev/null 2>&1; then
  echo "端口 $PORT 被占用，正在释放..."
  lsof -ti:$PORT | xargs kill -9 2>/dev/null
  sleep 1
  echo "端口已释放"
fi

.venv/bin/mitmdump -p $PORT -s addons.py
