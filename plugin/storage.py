"""配置写入：先完成序列化，再原子替换；内容未变化时保留原文件。"""
import os
from io import StringIO
from pathlib import Path
from stat import S_IMODE
from tempfile import NamedTemporaryFile

from ruamel.yaml import YAML


def atomic_write(target: Path, content: bytes) -> bool:
    try:
        if target.read_bytes() == content:
            return False
        mode = S_IMODE(target.stat().st_mode)
    except FileNotFoundError:
        mode = None
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile(dir=target.parent, prefix=f'.{target.name}.', suffix='.tmp',
                                delete=False) as f:
            temporary = Path(f.name)
            if mode is not None:
                os.fchmod(f.fileno(), mode)
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def save_yaml(target: Path, settings, yaml: YAML) -> bool:
    output = StringIO()
    yaml.dump(settings, output)
    return atomic_write(target, output.getvalue().encode('utf-8'))
