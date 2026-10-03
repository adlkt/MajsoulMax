"""plugin/update.py 下载校验逻辑测试（纯内存，不碰真实 config/proto 文件）。

_validate_blobs 是写盘前的最后防线：GitHub 返回 403/404 错误页时，
错误内容必须在校验阶段被拦下，而不是写坏本地可用的 liqi.desc。
"""
from types import SimpleNamespace

import pytest
from google.protobuf import descriptor_pb2
from ruamel.yaml import YAML

from plugin import update as updater
from plugin.update import _validate_blobs


def _mock_releases(monkeypatch):
    monkeypatch.setattr(updater, '_download_liqi_latest_release', lambda token: SimpleNamespace(
        headers={}, raise_for_status=lambda: None,
        json=lambda: {'tag_name': 'same-version'}))
    monkeypatch.setattr(updater, '_download_max_latest_release', lambda token: SimpleNamespace(
        headers={}, raise_for_status=lambda: None,
        json=lambda: {'tag_name': 'max-version'}))


def test_missing_data_downloads_even_when_version_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, 'BASE_DIR', tmp_path)
    _mock_releases(monkeypatch)
    downloads = []

    def download(release, token):
        downloads.append(release)
        return {'liqi.desc': _make_valid_desc(), 'max_data.yaml': _make_valid_max_data()}

    monkeypatch.setattr(updater, '_download_liqi_assets', download)
    assert updater.update('max-version', 'same-version', '') == 'same-version'
    assert len(downloads) == 1
    assert (tmp_path / 'proto/liqi.desc').is_file()
    assert (tmp_path / 'proto/liqi.json').is_file()
    assert (tmp_path / 'config/max_data.yaml').is_file()


def test_missing_rpc_map_regenerated_without_download(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, 'BASE_DIR', tmp_path)
    (tmp_path / 'proto').mkdir()
    (tmp_path / 'config').mkdir()
    (tmp_path / 'proto/liqi.desc').write_bytes(_make_valid_desc())
    (tmp_path / 'config/max_data.yaml').write_bytes(_make_valid_max_data())
    _mock_releases(monkeypatch)
    monkeypatch.setattr(updater, '_download_liqi_assets', lambda *args: pytest.fail('unexpected download'))
    updater.update('max-version', 'same-version', '')
    assert (tmp_path / 'proto/liqi.json').is_file()


def _make_valid_desc() -> bytes:
    """构造一个最小合法 FileDescriptorSet（带一个 file 条目）。"""
    fds = descriptor_pb2.FileDescriptorSet()
    f = fds.file.add()
    f.name = "liqi.proto"
    f.package = "lq"
    return fds.SerializeToString()


def _make_valid_max_data() -> bytes:
    buf = b"character:\n  200001: 400101\n"
    assert isinstance(YAML().load(buf), dict)
    return buf


def test_validate_blobs_passes_on_valid_content():
    _validate_blobs({"liqi.desc": _make_valid_desc(),
                     "max_data.yaml": _make_valid_max_data()})


def test_validate_blobs_rejects_html_error_page_as_desc():
    """GitHub 403/404 返回的 HTML 错误页不能通过校验。"""
    bad = b"<html>API rate limit exceeded</html>"
    with pytest.raises(ValueError, match="liqi.desc"):
        _validate_blobs({"liqi.desc": bad,
                         "max_data.yaml": _make_valid_max_data()})


def test_validate_blobs_rejects_empty_desc():
    with pytest.raises(ValueError, match="liqi.desc"):
        _validate_blobs({"liqi.desc": b"",
                         "max_data.yaml": _make_valid_max_data()})


def test_validate_blobs_rejects_non_yaml_max_data():
    bad = b"{invalid yaml: [unclosed"
    with pytest.raises(ValueError, match="max_data.yaml"):
        _validate_blobs({"liqi.desc": _make_valid_desc(),
                         "max_data.yaml": bad})


def test_validate_blobs_rejects_non_dict_max_data():
    bad = b"- just\n- a\n- list\n"
    with pytest.raises(ValueError, match="max_data.yaml"):
        _validate_blobs({"liqi.desc": _make_valid_desc(),
                         "max_data.yaml": bad})
