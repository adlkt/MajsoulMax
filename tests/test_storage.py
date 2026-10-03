"""配置保存失败不会破坏原文件，重复保存不替换原文件。"""
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from ruamel.yaml.representer import RepresenterError

from plugin import storage


def test_atomic_replace_and_unchanged_skip(tmp_path, monkeypatch):
    target = tmp_path / 'config/settings.yaml'
    assert storage.save_yaml(target, {'config': {'角色': 200001}}, YAML()) is True
    original = target.stat()

    def no_temp(**kwargs):
        pytest.fail('unchanged settings created a temporary file')

    monkeypatch.setattr(storage, 'NamedTemporaryFile', no_temp)
    assert storage.save_yaml(target, {'config': {'角色': 200001}}, YAML()) is False
    assert target.stat().st_ino == original.st_ino
    assert target.stat().st_mtime_ns == original.st_mtime_ns
    assert YAML().load(target)['config']['角色'] == 200001
    assert list(target.parent.iterdir()) == [target]


def test_replace_failure_preserves_original_and_removes_temp(tmp_path, monkeypatch):
    target = tmp_path / 'settings.yaml'
    target.write_bytes(b'original')

    def fail_replace(source, destination):
        assert destination == target
        assert source.read_bytes() == b'new'
        assert target.read_bytes() == b'original'
        raise PermissionError('replacement denied')

    monkeypatch.setattr(Path, 'replace', fail_replace)
    with pytest.raises(PermissionError):
        storage.atomic_write(target, b'new')
    assert target.read_bytes() == b'original'
    assert list(tmp_path.iterdir()) == [target]


def test_flush_failure_preserves_original_and_removes_temp(tmp_path, monkeypatch):
    target = tmp_path / 'settings.yaml'
    target.write_bytes(b'original')

    def fail_sync(fd):
        raise OSError('disk write failed')

    monkeypatch.setattr(storage.os, 'fsync', fail_sync)
    with pytest.raises(OSError):
        storage.atomic_write(target, b'new')
    assert target.read_bytes() == b'original'
    assert list(tmp_path.iterdir()) == [target]


def test_yaml_serialization_failure_leaves_original_untouched(tmp_path):
    target = tmp_path / 'settings.yaml'
    target.write_bytes(b'original')
    with pytest.raises(RepresenterError):
        storage.save_yaml(target, {'unserializable': object()}, YAML())
    assert target.read_bytes() == b'original'
    assert list(tmp_path.iterdir()) == [target]


def test_preserves_file_permissions(tmp_path):
    target = tmp_path / 'settings.yaml'
    target.write_bytes(b'original')
    target.chmod(0o600)
    storage.atomic_write(target, b'new')
    assert target.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('module_name', ['mod', 'helper', 'replace'])
def test_plugins_save_atomically_without_backup(module_name, tmp_path, monkeypatch):
    import importlib

    module = importlib.import_module(f'plugin.{module_name}')
    cls = getattr(module, module_name)
    instance = cls.__new__(cls)
    instance.yaml = YAML()
    instance.settings = {'config': {'value': 1}}
    monkeypatch.setattr(module, 'BASE_DIR', tmp_path)
    instance.SaveSettings()
    target = tmp_path / f'config/settings.{module_name}.yaml'
    original = target.stat()
    instance.SaveSettings()
    assert target.stat().st_ino == original.st_ino
    assert target.stat().st_mtime_ns == original.st_mtime_ns
    instance.settings['config']['value'] = 2
    instance.SaveSettings()
    assert YAML().load(target)['config']['value'] == 2
    assert list(target.parent.iterdir()) == [target]
