from types import SimpleNamespace

import pytest
from mitmproxy import http

from addons import MajsoulMaxAddon
from plugin.unity_emoji import PATCH_TAG, patch_panel


def flow(path, body=b'original'):
    return SimpleNamespace(request=http.Request.make('GET', 'https://game.maj-soul.com'+path),
                           response=http.Response.make(200, body), metadata={})


def test_panel_patch_uses_game_permissions_without_changing_skin_unlocks():
    source = 'function UI_BlockEmo:InitRoom()local j=DesktopMgr.Inst:get_main_role_character_info()self.emos=EmojiMgr.GetUnlockEmojiList(j.charid)self:ShowEmo()end'
    patched = patch_panel(source)
    assert 'j.enabled_emoji' in patched
    assert 'allowed[emo.emoji_id]' in patched
    assert 'self:ShowEmo()end' in patched
    assert 'skin_map' not in patched


def test_changed_upstream_script_fails_instead_of_replacing_unrelated_code():
    with pytest.raises(ValueError):
        patch_panel('return UI_BlockEmo')


def test_known_panel_request_bypasses_http_cache_and_response_gets_patched(monkeypatch):
    addon = MajsoulMaxAddon(None, mod_plugin=object())
    addon.emoji_panel_assets['/assetbundles/ASTC/panel.majset'] = {'name':'panel.majset', 'url':'/assetbundles/ASTC/panel.majset'}
    request = flow('/assetbundles/ASTC/panel.majset')
    request.request.headers['if-none-match'] = 'old'
    addon.request(request)
    assert request.request.path == '/assetbundles/ASTC/panel.majset'
    assert 'if-none-match' not in request.request.headers
    monkeypatch.setattr('plugin.unity_emoji.patch_bundle', lambda body: b'filtered')
    addon.response(request)
    assert request.response.content == b'filtered'


def test_mod_disabled_leaves_game_resources_untouched():
    addon = MajsoulMaxAddon(None)
    request = flow('/assetbundles/ASTC/bundle_hash.txt')
    addon.request(request)
    addon.response(request)
    assert request.response.content == b'original'


def test_patch_failure_preserves_original_response(monkeypatch):
    addon = MajsoulMaxAddon(None, mod_plugin=object())
    request = flow('/assetbundles/ASTC/bundle_info_so.majset')
    def fail(*args, **kwargs):
        raise ValueError('changed asset format')
    monkeypatch.setattr('plugin.unity_emoji.patch_bundle', fail)
    addon.response(request)
    assert request.response.content == b'original'


def test_manifest_only_lists_the_panel_asset():
    import json
    addon = MajsoulMaxAddon(None, mod_plugin=object())
    addon.emoji_panel_assets['/assetbundles/ASTC/panel.majset'] = {'name': 'panel.majset', 'url': '/assetbundles/ASTC/panel.majset'}
    request = flow('/_majsoulmax/emoji-panel-assets')
    addon.request(request)
    manifest = json.loads(request.response.content)
    assert manifest['tag'] == PATCH_TAG
    assert len(manifest['assets']) == 1


def test_loader_bootstrap_runs_before_unity_and_limits_cache_to_panel_assets():
    addon = MajsoulMaxAddon(None, mod_plugin=object())
    request = flow('/1/Build/game.loader.js', b'var createUnityInstance=function(){};')
    addon.response(request)
    assert b'window.createUnityInstance = async' in request.response.content
    assert b"key.includes('/ABM-Fold/')" in request.response.content
    assert b"key.endsWith('/' + asset.name)" in request.response.content
    assert b'return original(...args)' in request.response.content


@pytest.mark.parametrize('path', ['/1/Build/game.wasm.gz', '/assetbundles/ASTC/texture.majset', '/1/image.png'])
def test_unrelated_resources_are_skipped_without_reading_or_decompressing_body(path):
    class UnreadResponse:
        status_code = 200
        accessed = False

        @property
        def content(self):
            self.accessed = True
            raise AssertionError('unrelated response must not be decoded')

    addon = MajsoulMaxAddon(None, mod_plugin=object())
    request = flow(path)
    request.response = UnreadResponse()
    addon.response(request)
    assert not request.response.accessed


@pytest.mark.parametrize('scenario', ['success_empty', 'success_write', 'already_patched',
                                     'timeout_fetch', 'timeout_body', 'timeout_open', 'timeout_write'])
def test_bootstrap_starts_unity_and_cancels_late_cache_work(scenario):
    import shutil
    import subprocess
    from pathlib import Path

    node = shutil.which('node')
    if node is None:
        pytest.skip('Node.js is required to execute the browser bootstrap harness')
    root = Path(__file__).resolve().parent.parent
    subprocess.run([node, str(root / 'tests/fixtures/unity_emoji_bootstrap.cjs'),
                    str(root / 'plugin/unity_emoji_bootstrap.js'), scenario],
                   check=True, capture_output=True, text=True, timeout=10)
