"""Validate setup boundaries without installing Linux services on Windows."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from scripts import kaggle_setup as setup


@pytest.mark.parametrize('name', ['../outside.txt', '/outside.txt', 'folder\\..\\outside.txt'])
def test_archive_cannot_escape_destination(tmp_path, name):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        item = zipfile.ZipInfo()
        item.filename = name  # Preserve hostile backslashes on Windows too.
        z.writestr(item, 'bad')
    with pytest.raises(ValueError, match='Unsafe'):
        setup.safe_extract(archive, tmp_path / 'out')
    assert not (tmp_path / 'out').exists()


def test_manifest_rejects_corrupted_package(tmp_path):
    data = tmp_path / 'payload.txt'
    data.write_bytes(b'original')
    (tmp_path / 'manifest.json').write_text(json.dumps({'sha256': {
        'payload.txt': hashlib.sha256(data.read_bytes()).hexdigest()}}))
    setup.verify_manifest(tmp_path, 'manifest.json')
    data.write_bytes(b'changed')
    with pytest.raises(ValueError, match='checksum'):
        setup.verify_manifest(tmp_path, 'manifest.json')


def test_frontend_origin_restart_config_preserves_proxy(tmp_path):
    config = tmp_path / 'next.config.ts'
    source = (Path(__file__).parents[1] / 'src/frontend/next.config.ts').read_text()
    config.write_text(source)
    setup.configure_frontend(tmp_path)
    setup.configure_frontend(tmp_path, 'test.ngrok-free.app')
    setup.configure_frontend(tmp_path, 'test.ngrok-free.app')
    result = config.read_text()
    assert result.count('allowedDevOrigins:') == 1
    assert result.count('proxyTimeout:') == 1
    assert '"test.ngrok-free.app"' in result
    assert 'proxyTimeout: 360000' in result
    assert 'destination: `${BACKEND_URL}/api/:path*`' in result


def test_model_and_artifact_child_scripts_compile(monkeypatch, tmp_path):
    captured = []
    def capture(args, *positional, **kwargs):
        captured.append(args[2])
        compile(args[2], '<setup-child>', 'exec')
    monkeypatch.setattr(setup, 'checked', capture)
    monkeypatch.setenv('HF_HUB_OFFLINE', '0')
    monkeypatch.setenv('EXPECTED_DATA_USAGE', 'synthetic_demo')
    setup.download_models(tmp_path, tmp_path, 'python', True)
    setup.validate_data(tmp_path, tmp_path, 'python')
    assert len(captured) == 2
    assert 'QwenLoRAProvider' in captured[0]
    assert 'demo_menu_cuisine' in captured[1]
