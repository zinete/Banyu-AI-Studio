"""Explicit online setup. Runtime code is offline and never imports this module."""
import argparse
import concurrent.futures
import hashlib
import json
import shutil
import struct
import urllib.request
import zipfile
import time
import re
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def download(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Xiaolan-Local-Studio/0.1"})
    with urllib.request.urlopen(request, timeout=60) as response:
        expected = int(response.headers.get("Content-Length", 0))
        resolved = response.url
    if not expected:
        raise RuntimeError(f"Cannot verify resource length: {path.name}")
    if path.exists() and path.stat().st_size == expected:
        print(f"Exists: {path.name}", flush=True)
        return path
    print(f"Downloading: {path.name} ({expected:,} bytes)", flush=True)
    temp = path.with_suffix(path.suffix + ".partial")
    if path.exists():
        path.replace(temp)
    if expected < 8 * 1024 * 1024:
        with urllib.request.urlopen(resolved, timeout=60) as response, temp.open("wb") as output:
            shutil.copyfileobj(response, output)
    else:
        prefix = temp.stat().st_size if temp.exists() else 0
        chunk_size = 16 * 1024 * 1024
        ranges = [(start, min(start + chunk_size, expected) - 1)
                  for start in range(prefix, expected, chunk_size)]

        def fetch_range(bounds):
            start, end = bounds
            part = path.with_name(f"{path.name}.part-{start}")
            for attempt in range(5):
                present = part.stat().st_size if part.exists() else 0
                if present == end - start + 1:
                    return part
                try:
                    req = urllib.request.Request(resolved, headers={
                        "Range": f"bytes={start + present}-{end}", "User-Agent": "Xiaolan-Local-Studio/0.1"})
                    with urllib.request.urlopen(req, timeout=60) as response:
                        content_range = response.headers.get("Content-Range", "")
                        if response.status != 206 or not content_range.startswith(f"bytes {start+present}-"):
                            raise RuntimeError("Server did not honor byte range")
                        with part.open("ab") as output:
                            shutil.copyfileobj(response, output, length=1024 * 1024)
                except Exception:
                    if attempt == 4:
                        raise
                    time.sleep(1)
            if part.stat().st_size != end-start+1:
                raise RuntimeError(f"Incomplete chunk: {part.name}")
            return part

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            parts = list(pool.map(fetch_range, ranges))
        with temp.open("ab") as output:
            for part in parts:
                with part.open("rb") as source:
                    shutil.copyfileobj(source, output)
        for part in parts:
            part.unlink()
    if temp.stat().st_size != expected:
        raise RuntimeError(f"Incomplete resource {path.name}: {temp.stat().st_size}/{expected}")
    temp.replace(path)
    print(f"Ready: {path.name} ({path.stat().st_size:,} bytes)", flush=True)
    return path


def avatar():
    url = "https://raw.githubusercontent.com/pixiv/three-vrm/dev/packages/three-vrm/examples/models/VRM1_Constraint_Twist_Sample.vrm"
    path = download(url, ROOT / ".runtime/avatar-candidate.vrm")
    data = path.read_bytes()
    length, kind = struct.unpack_from("<II", data, 12)
    if kind != 0x4E4F534A:
        raise ValueError("Invalid VRM JSON chunk")
    gltf = json.loads(data[20:20+length])
    meta = gltf.get("extensions", {}).get("VRMC_vrm", {}).get("meta", {})
    print("Avatar metadata: " + json.dumps(meta, ensure_ascii=True), flush=True)
    record = {"source": url, "sha256": hashlib.sha256(data).hexdigest(), "meta": meta}
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs/avatar-license.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    # Approval is based on the asset's embedded terms, never the renderer's MIT license.
    if (meta.get("avatarPermission") != "everyone" or meta.get("commercialUsage") != "corporation"
            or meta.get("modification") != "allowModificationRedistribution"):
        raise RuntimeError("Avatar license needs review; metadata saved, candidate NOT published")
    target = ROOT / "frontend/public/avatar.vrm"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)


def voice():
    base = "https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/"
    files = ["config.json", "kokoro-v1_0.pth", "voices/zf_xiaobei.pt", "README.md"]
    for filename in files:
        download(base + filename, ROOT / "models/kokoro" / filename)


def ollama():
    if platform.system() == 'Darwin':
        binary = shutil.which('ollama')
        app_binary = Path('/Applications/Ollama.app/Contents/Resources/ollama')
        if not binary and app_binary.is_file():
            binary = str(app_binary)
        if not binary:
            raise RuntimeError('Install native Ollama from https://ollama.com/download/mac first.')
        print('Using installed macOS Ollama: ' + binary, flush=True)
        return
    if platform.system() != 'Windows':
        raise RuntimeError('Portable Ollama setup supports Windows; on macOS use Setup-macOS.sh.')
    request = urllib.request.Request("https://api.github.com/repos/ollama/ollama/releases/latest", headers={"User-Agent": "Xiaolan-Local-Studio"})
    with urllib.request.urlopen(request, timeout=30) as response:
        release = json.load(response)
    asset = next(x for x in release["assets"] if x["name"] == "ollama-windows-amd64.zip")
    path = download(asset["browser_download_url"], ROOT / ".runtime/ollama.zip")
    if asset.get("digest", "").startswith("sha256:"):
        actual = hashlib.file_digest(path.open("rb"), "sha256").hexdigest()
        if actual != asset["digest"].split(":")[1]:
            raise RuntimeError("Ollama checksum mismatch")
    target = (ROOT / ".runtime/ollama").resolve()
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if not (target / name).resolve().is_relative_to(target):
                raise RuntimeError("Unsafe archive path")
        archive.extractall(target)
    (ROOT / ".runtime/ollama-release.json").write_text(json.dumps({"version": release["tag_name"], "asset": asset}, indent=2), encoding="utf-8")
    print("Portable Ollama extracted", flush=True)


def diagnose():
    for url in ["https://huggingface.co/hexgrad/Kokoro-82M/resolve/main/kokoro-v1_0.pth",
                "https://github.com/ollama/ollama/releases/download/v0.40.14/ollama-windows-amd64.zip"]:
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Xiaolan-Local-Studio"})
        with urllib.request.urlopen(request, timeout=30) as response:
            print(json.dumps({"url":url,"status":response.status,"headers":dict(response.headers)}, ensure_ascii=True), flush=True)


def qwen(tag="4b"):
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", tag):
        raise ValueError("Invalid model tag")
    base = "https://registry.ollama.ai/v2/library/qwen3/"
    request = urllib.request.Request(base + "manifests/" + tag, headers={"Accept": "application/vnd.docker.distribution.manifest.v2+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        manifest = response.read()
    parsed = json.loads(manifest)
    for layer in [parsed["config"], *parsed["layers"]]:
        digest = layer["digest"]
        if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise RuntimeError("Invalid model blob digest")
        path = ROOT / "models/ollama/blobs" / digest.replace(":", "-")
        download(base + "blobs/" + digest, path)
        with path.open("rb") as source:
            checksum = hashlib.file_digest(source, "sha256").hexdigest()
        if checksum != digest.split(":")[1]:
            raise RuntimeError(f"Model blob checksum mismatch: {digest}")
        print(f"Verified {digest[:24]}", flush=True)
    path = ROOT / "models/ollama/manifests/registry.ollama.ai/library/qwen3" / tag
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(manifest)
    record_name = "qwen-manifest.json" if tag == "4b" else f"qwen-{tag}-manifest.json"
    (ROOT / "docs" / record_name).write_bytes(manifest)
    print("Official Qwen3 manifest and all blobs verified", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--component", choices=["avatar", "voice", "ollama", "qwen", "diagnose", "all"], default="all")
    parser.add_argument("--qwen-tag", default="4b-instruct-2507-q4_K_M")
    args = parser.parse_args()
    jobs = {"avatar": avatar, "voice": voice, "ollama": ollama, "qwen": lambda: qwen(args.qwen_tag), "diagnose": diagnose}
    selected = [avatar, voice, ollama] if args.component == "all" else [jobs[args.component]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        results = [pool.submit(fn) for fn in selected]
        for result in results:
            result.result()
