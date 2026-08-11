"""pytest 全局配置：把项目根加入 sys.path，使 `import liqi_new` / `import plugin` 可用。

pytest 默认以 rootdir 为基准，但项目是顶层脚本 + 包混合布局（liqi_new.py 在根、
plugin/ 是包），直接 import 会失败。这里显式插入项目根（conftest.py 的 parent）。
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
