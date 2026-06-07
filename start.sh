#!/bin/bash
cd "$(dirname "$0")"

# 从 config/mitmdump.yaml 读取 mitmdump 参数
read_mitmdump_args() {
  .venv/bin/python3 -c "
from ruamel.yaml import YAML
cfg = YAML().load(open('config/mitmdump.yaml')) or {}
for k, v in cfg.items():
    print(f' --{k.replace(\"_\", \"-\")} {v}', end='')
"
}

PORT=23410
if lsof -ti:$PORT > /dev/null 2>&1; then
  echo "端口 $PORT 被占用，正在释放..."
  lsof -ti:$PORT | xargs kill -9 2>/dev/null
  sleep 1
  echo "端口已释放"
fi

MITMDUMP_ARGS=$(read_mitmdump_args)
.venv/bin/mitmdump -p $PORT -s addons.py $MITMDUMP_ARGS
