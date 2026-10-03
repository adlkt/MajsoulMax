"""启动流程测试：导入无副作用，数据先准备、插件后创建。"""
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import addons


def test_ctrl_c_exits_without_traceback_and_runs_cleanup():
    script = '''
import asyncio
import os
import signal
import addons

addons.create_addon = lambda: object()
async def service(*args):
    loop = asyncio.get_running_loop()
    loop.call_later(0.05, os.kill, os.getpid(), signal.SIGINT)
    try:
        await asyncio.Event().wait()
    finally:
        print("CLEANED")
addons.start_mitm = service
addons.main()
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(addons.__file__).parent,
                            capture_output=True, text=True, timeout=10)
    assert 'CLEANED' in result.stdout
    assert result.returncode == 0, result.stderr
    assert 'Traceback' not in result.stderr
    assert '改包服务已停止' in result.stdout


def test_import_does_not_initialize_runtime():
    script = '''
import sys
import builtins
from pathlib import Path
from loguru import logger
from plugin import update

def forbidden(*args, **kwargs):
    raise AssertionError("import initialized runtime")

logger.remove = forbidden
logger.add = forbidden
update.missing_local_files = forbidden
update.update = forbidden
original_open = builtins.open
runtime_dirs = (Path.cwd() / "config", Path.cwd() / "proto")
def guarded_open(file, *args, **kwargs):
    if isinstance(file, (str, Path)) and any(Path(file).resolve().is_relative_to(directory) for directory in runtime_dirs):
        raise AssertionError("import accessed runtime files")
    return original_open(file, *args, **kwargs)
builtins.open = guarded_open
import addons
assert "liqi_new" not in sys.modules
assert "plugin.mod" not in sys.modules
assert "plugin.helper" not in sys.modules
assert "plugin.replace" not in sys.modules
assert not hasattr(addons, "SETTINGS")
assert not hasattr(addons, "liqi_proto")
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=Path(addons.__file__).parent,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_partial_settings_keep_defaults(tmp_path, monkeypatch):
    monkeypatch.setattr(addons, 'BASE_DIR', tmp_path)
    (tmp_path / 'config').mkdir()
    (tmp_path / 'config/settings.yaml').write_text('plugin_enable:\n  mod: false\n')
    settings = addons.load_settings()
    assert settings['plugin_enable'] == {'mod': False, 'helper': False, 'replace': False}
    assert settings['liqi']['auto_update'] is True
    settings['plugin_enable']['helper'] = True
    assert addons.load_settings()['plugin_enable']['helper'] is False


def test_prepare_missing_files_even_if_update_disabled(monkeypatch):
    settings = {'liqi': {'auto_update': False, 'liqi_version': 'test', 'github_token': ''}}
    calls = []
    missing = iter([[addons.BASE_DIR / 'proto/liqi.desc'], []])
    monkeypatch.setattr(addons.update, 'missing_local_files', lambda: next(missing))
    monkeypatch.setattr(addons.update, 'update', lambda *args: calls.append(args) or args[1])
    addons.prepare_protocol(settings)
    assert len(calls) == 1


def test_missing_files_stop_startup_after_update_failure(monkeypatch):
    settings = {'liqi': {'auto_update': True, 'liqi_version': 'test', 'github_token': ''}}
    monkeypatch.setattr(addons.update, 'missing_local_files',
                        lambda: [addons.BASE_DIR / 'proto/liqi.desc'])

    def fail_update(*args):
        raise RuntimeError('offline')

    monkeypatch.setattr(addons.update, 'update', fail_update)
    with pytest.raises(SystemExit, match='1'):
        addons.prepare_protocol(settings)


def test_update_failure_can_use_existing_files(monkeypatch):
    settings = {'liqi': {'auto_update': True, 'liqi_version': 'test', 'github_token': ''}}
    monkeypatch.setattr(addons.update, 'missing_local_files', lambda: [])

    def fail_update(*args):
        raise RuntimeError('offline')

    monkeypatch.setattr(addons.update, 'update', fail_update)
    addons.prepare_protocol(settings)


def test_create_addon_prepares_data_before_constructing_plugins(monkeypatch):
    events = []
    settings = {'plugin_enable': {'mod': True, 'helper': False, 'replace': False}}
    monkeypatch.setattr(addons, 'load_settings', lambda: settings)
    monkeypatch.setattr(addons, 'prepare_protocol', lambda settings: events.append('prepare'))
    monkeypatch.setitem(sys.modules, 'plugin.mod', SimpleNamespace(
        mod=lambda version: events.append('mod') or object()))
    monkeypatch.setitem(sys.modules, 'liqi_new', SimpleNamespace(
        LiqiProto=lambda **kwargs: object(), load_rpc_map=lambda: {}))
    addon = addons.create_addon()
    assert events == ['prepare', 'mod']
    assert addon.mod_plugin is not None
    assert addon.helper_plugin is None
    assert addon.replace_plugin is None
    assert addon.connections == {}


def test_start_mitm_registers_prepared_addon(monkeypatch):
    import asyncio

    addon = object()
    registered = []
    options = []
    ran = []

    class Master:
        def __init__(self, opts):
            assert opts.listen_host == '127.0.0.1'
            assert opts.listen_port == 23411
            self.options = SimpleNamespace(update=lambda **kwargs: options.append(kwargs))
            self.addons = SimpleNamespace(add=lambda instance: registered.append(instance))

        def shutdown(self):
            pass

        async def run(self):
            ran.append(True)

    monkeypatch.setattr(addons, 'DumpMaster', Master)
    monkeypatch.setattr(addons, 'create_addon', lambda: pytest.fail('addon initialized twice'))

    async def start():
        loop = asyncio.get_running_loop()
        monkeypatch.setattr(loop, 'add_signal_handler', lambda *args: None)
        await addons.start_mitm(23411, addon)

    asyncio.run(start())
    assert registered == [addon]
    assert ran == [True]
    assert options[0]['flow_detail'] == 0


def test_service_loads_rpc_map_once_and_shares_only_mapping(tmp_path, monkeypatch):
    import json
    import liqi_new

    monkeypatch.setattr(addons, 'load_settings', lambda: {
        'plugin_enable': {'mod': False, 'helper': False, 'replace': False}})
    monkeypatch.setattr(addons, 'prepare_protocol', lambda settings: None)
    monkeypatch.setattr(liqi_new, 'BASE_DIR', tmp_path)
    (tmp_path / 'proto').mkdir()
    target = tmp_path / 'proto/liqi.json'
    target.write_text(json.dumps({'.lq.Test.call': {'req': '.lq.ReqCommon', 'resp': '.lq.ResCommon'}}))
    original_load = liqi_new.json.load
    loads = []

    def load(file):
        loads.append(file.name)
        return original_load(file)

    monkeypatch.setattr(liqi_new.json, 'load', load)
    addon = addons.create_addon()
    first, _ = addon._connection(SimpleNamespace(id='first'))
    second, _ = addon._connection(SimpleNamespace(id='second'))
    assert len(loads) == 1
    assert first.rpc_map is second.rpc_map
    assert first.res_type is not second.res_type
    first.res_type[1] = ('example', object())
    assert second.res_type == {}
    with pytest.raises(TypeError):
        first.rpc_map['new'] = {}
    with pytest.raises(TypeError):
        first.rpc_map['.lq.Test.call']['req'] = 'new'

    # 再启动服务读取新映射，不沿用上次运行的缓存。
    target.write_text('{}')
    restarted = addons.create_addon()
    third, _ = restarted._connection(SimpleNamespace(id='third'))
    assert third.rpc_map == {}
    assert '.lq.Test.call' in first.rpc_map
    assert len(loads) == 2
