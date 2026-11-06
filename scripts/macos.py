"""macOS setup/launcher. Standard library only; never imported by offline backend."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / '.venv-macos/bin/python'
MODEL = 'qwen3:4b-instruct-2507-q4_K_M'
OLLAMA_URL = 'http://127.0.0.1:11435'
STUDIO_URL = 'http://127.0.0.1:8765'


def check_platform():
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise RuntimeError('This entry requires an Apple Silicon Mac and native arm64 Python (not Rosetta).')
    if int(platform.mac_ver()[0].split('.')[0]) < 14:
        raise RuntimeError('macOS 14 Sonoma or newer is required.')
    if sys.version_info[:2] != (3, 12):
        raise RuntimeError('Use Python 3.12: python3.12 scripts/macos.py setup|start')


def ollama_binary():
    binary = shutil.which('ollama')
    if not binary:
        candidate = Path('/Applications/Ollama.app/Contents/Resources/ollama')
        if candidate.is_file():
            binary = str(candidate)
    if not binary:
        raise RuntimeError('Install Ollama from https://ollama.com/download/mac first.')
    return binary


def environment():
    return {**os.environ, 'OLLAMA_HOST': '127.0.0.1:11435',
            'OLLAMA_MODELS': str(ROOT / 'models/ollama'), 'OLLAMA_NO_CLOUD': '1',
            'OLLAMA_NUM_PARALLEL': '1', 'OLLAMA_MAX_LOADED_MODELS': '1',
            'OLLAMA_CONTEXT_LENGTH': '4096', 'HF_HUB_OFFLINE': '1',
            'TRANSFORMERS_OFFLINE': '1', 'PYTHONUTF8': '1'}


def get_json(url):
    # Local probes must not inherit an HTTP proxy configured on the Mac.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=2) as response:
        return json.load(response)


def probe(url):
    try:
        return get_json(url)
    except (OSError, ValueError):
        return None


def wait_ready(url, child, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError('Service exited. See .runtime/*-macos.log.')
        result = probe(url)
        if result is not None:
            return result
        time.sleep(.5)
    raise RuntimeError('Service startup timed out. See .runtime/*-macos.log.')


def stop_children(children):
    # Only terminate subprocesses created by this invocation, never the user's Ollama app.
    for child in reversed(children):
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=12)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


def lan_host():
    path = ROOT / '.runtime/lan.json'
    if not path.exists():
        return '127.0.0.1'
    config = json.loads(path.read_text(encoding='utf-8'))
    address = ipaddress.ip_address(config.get('host', ''))
    if (address.version != 4 or not address.is_private or address.is_loopback
            or address.is_unspecified or address.is_multicast
            or len(config.get('access_token', '')) < 32):
        raise RuntimeError('Invalid .runtime/lan.json; update it for this Mac.')
    print(f"LAN: http://{address}:8765/?access={config['access_token']}", flush=True)
    return '0.0.0.0'


def run(args, env, cwd=ROOT):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['setup', 'start'])
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    check_platform()
    env = environment()
    children = []
    logs = []
    (ROOT / '.runtime').mkdir(exist_ok=True)

    def spawn(command, log_name):
        log = (ROOT / '.runtime' / log_name).open('ab')
        logs.append(log)
        child = subprocess.Popen([str(arg) for arg in command], cwd=ROOT, env=env,
                                 stdout=log, stderr=subprocess.STDOUT)
        children.append(child)
        return child

    def interrupted(signum, frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.command == 'start':
            if not PYTHON.is_file() or not (ROOT / 'frontend/dist/index.html').is_file():
                raise RuntimeError('Run bash Setup-macOS.sh first.')
            existing = probe(STUDIO_URL + '/api/health')
            if existing and existing.get('avatar_kind') == 'yier_bubu_3d':
                print('Studio already running: ' + STUDIO_URL)
                if not args.no_browser:
                    webbrowser.open(STUDIO_URL)
                return
        ollama = ollama_binary()
        if args.command == 'setup':
            if not shutil.which('node') or not shutil.which('npm'):
                raise RuntimeError('Install Node.js 22+ (including npm) first.')
            version = subprocess.check_output(['node', '--version'], text=True)
            if int(version.lstrip('v').split('.')[0]) < 22:
                raise RuntimeError('Node.js 22+ required.')
            if not PYTHON.exists():
                run([sys.executable, '-m', 'venv', PYTHON.parent.parent], env)
            run([PYTHON, '-m', 'pip', 'install', '-r', 'requirements.txt', '-r', 'requirements-voice.txt'], env)
            run(['npm', 'ci'], env, ROOT / 'frontend')
            # The live avatar is procedural: no Windows Ollama archive or unused VRM needed.
            run([PYTHON, 'scripts/prepare.py', '--component', 'voice'], env)
            run(['npm', 'run', 'build'], env, ROOT / 'frontend')
        tags = probe(OLLAMA_URL + '/api/tags')
        if tags is None:
            child = spawn([ollama, 'serve'], 'ollama-macos.log')
            tags = wait_ready(OLLAMA_URL + '/api/tags', child)
        if args.command == 'setup':
            run([ollama, 'pull', MODEL], env)
            run([PYTHON, 'scripts/warmup.py'], env)
            print('Ready. Run bash Start-Studio-macOS.sh')
            return
        if MODEL not in [model.get('name') for model in tags.get('models', [])]:
            raise RuntimeError('Local model missing. Run bash Setup-macOS.sh; start never downloads models.')
        child = spawn([PYTHON, '-m', 'uvicorn', 'backend.app:app', '--host', lan_host(),
                       '--port', '8765', '--no-access-log'], 'api-macos.log')
        wait_ready(STUDIO_URL + '/api/health', child)
        print('Banyu AI Studio: ' + STUDIO_URL + '\nKeep this terminal open. Ctrl+C stops owned services.', flush=True)
        if not args.no_browser:
            webbrowser.open(STUDIO_URL)
        if child.wait() != 0:
            raise RuntimeError('Studio exited with an error. See .runtime/api-macos.log.')
    except KeyboardInterrupt:
        print('\nStopping Banyu AI Studio.', flush=True)
    finally:
        stop_children(children)
        for log in logs:
            log.close()


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError) as error:
        print(f'Error: {error}', file=sys.stderr)
        sys.exit(1)
