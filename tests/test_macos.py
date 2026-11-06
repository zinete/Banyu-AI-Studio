import subprocess
from unittest.mock import Mock

import pytest

from scripts import macos


def test_platform_accepts_native_apple_silicon(monkeypatch):
    monkeypatch.setattr(macos.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(macos.platform, 'machine', lambda: 'arm64')
    monkeypatch.setattr(macos.platform, 'mac_ver', lambda: ('14.0', (), ''))
    monkeypatch.setattr(macos.sys, 'version_info', (3, 12, 0))
    macos.check_platform()


def test_platform_rejects_rosetta(monkeypatch):
    monkeypatch.setattr(macos.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(macos.platform, 'machine', lambda: 'x86_64')
    with pytest.raises(RuntimeError, match='Rosetta'):
        macos.check_platform()


def test_services_get_separate_local_offline_configuration():
    env = macos.environment()
    assert env['OLLAMA_HOST'] == '127.0.0.1:11435'
    assert env['OLLAMA_NO_CLOUD'] == env['HF_HUB_OFFLINE'] == '1'
    assert env['OLLAMA_MODELS'] == str(macos.ROOT / 'models/ollama')


def test_cleanup_only_owned_children_and_kills_on_timeout():
    finished, hung, running = Mock(), Mock(), Mock()
    finished.poll.return_value = 0
    hung.poll.return_value = running.poll.return_value = None
    hung.wait.side_effect = [subprocess.TimeoutExpired('ollama', 12), 0]
    macos.stop_children([finished, hung, running])
    finished.terminate.assert_not_called()
    running.terminate.assert_called_once()
    running.kill.assert_not_called()
    hung.kill.assert_called_once()


def test_dead_service_fails_without_waiting_for_timeout():
    child = Mock()
    child.poll.return_value = 1
    with pytest.raises(RuntimeError, match='exited'):
        macos.wait_ready('http://127.0.0.1:11435/api/tags', child)


def test_start_missing_model_never_downloads_or_starts_backend(tmp_path, monkeypatch):
    monkeypatch.setattr(macos, 'ROOT', tmp_path)
    python = tmp_path / '.venv-macos/bin/python'
    python.parent.mkdir(parents=True)
    python.touch()
    (tmp_path / 'frontend/dist').mkdir(parents=True)
    (tmp_path / 'frontend/dist/index.html').touch()
    monkeypatch.setattr(macos, 'PYTHON', python)
    monkeypatch.setattr(macos, 'check_platform', lambda: None)
    monkeypatch.setattr(macos, 'ollama_binary', lambda: '/Applications/Ollama.app/Contents/Resources/ollama')
    monkeypatch.setattr(macos, 'probe', lambda url: None if '8765' in url else {'models': []})
    monkeypatch.setattr(macos.sys, 'argv', ['macos.py', 'start', '--no-browser'])
    popen, run = Mock(), Mock()
    monkeypatch.setattr(macos.subprocess, 'Popen', popen)
    monkeypatch.setattr(macos.subprocess, 'run', run)
    monkeypatch.setattr(macos.signal, 'signal', Mock())
    with pytest.raises(RuntimeError, match='never downloads'):
        macos.main()
    popen.assert_not_called()
    run.assert_not_called()


def test_lan_binding_validates_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(macos, 'ROOT', tmp_path)
    assert macos.lan_host() == '127.0.0.1'
    (tmp_path / '.runtime').mkdir()
    config = tmp_path / '.runtime/lan.json'
    config.write_text('{"host":"0.0.0.0", "access_token":"short"}')
    with pytest.raises(RuntimeError, match='Invalid'):
        macos.lan_host()
    config.write_text('{"host":"192.168.1.77", "access_token":"xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}')
    assert macos.lan_host() == '0.0.0.0'
