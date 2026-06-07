from ruamel.yaml import YAML
from loguru import logger

class replace:
    def __init__(self):
        self.yaml = YAML()
        self.LoadSettings()
        logger.success('已载入replace')

    def LoadSettings(self):
        self.settings = self.yaml.load('''\
config:
  http: []
  lq: []
''')
        try:
            with open('./config/settings.replace.yaml', 'r', encoding='utf8') as f:
                self.settings.update(self.yaml.load(f))
        except Exception as e:
            logger.warning(f'无法读取 replace 配置 ({e})，已使用默认配置')
            self.SaveSettings()

    def SaveSettings(self):
        with open('./config/settings.replace.yaml', 'w', encoding='utf8') as f:
            self.yaml.dump(self.settings, f)

    def main(self, request):
        for path in self.settings['config']['http']:
            if path in request.path:
                return path 
        return ''