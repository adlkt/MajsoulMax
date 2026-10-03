from pathlib import Path

from loguru import logger
from ruamel.yaml import YAML

from plugin.storage import save_yaml

BASE_DIR = Path(__file__).resolve().parent.parent

class replace:
    def __init__(self):
        self.yaml = YAML()
        self.LoadSettings()
        logger.success('已载入replace')

    def LoadSettings(self):
        self.settings = self.yaml.load('''\
config:
  http: []
''')
        try:
            with open(BASE_DIR / 'config' / 'settings.replace.yaml', 'r', encoding='utf8') as f:
                self.settings.update(self.yaml.load(f))
        except FileNotFoundError:
            logger.warning(
                '未检测到replace配置文件，已生成默认配置，如需自定义replace配置请手动修改 ./config/settings.replace.yaml')
            self.SaveSettings()

    def SaveSettings(self):
        save_yaml(BASE_DIR / 'config' / 'settings.replace.yaml', self.settings, self.yaml)

    def main(self, request):
        for path in self.settings['config']['http']:
            if path in request.path:
                return path 
        return ''