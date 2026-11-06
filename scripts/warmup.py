import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.providers import LocalVoice

started = time.perf_counter()
audio, duration = LocalVoice().synthesize("你好，我是小岚，今天想聊些什么？")
target = Path(__file__).resolve().parents[1] / ".runtime/voice-check.wav"
target.parent.mkdir(exist_ok=True)
target.write_bytes(audio)
print(f"Local speech ready: {duration:.2f}s audio in {time.perf_counter()-started:.2f}s; {target}")
