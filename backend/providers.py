import asyncio
import io
import json
import os
import threading
import sys
from pathlib import Path

import httpx
from .safety import CATEGORIES
from .replies import DEFAULT_REPLY_LIMIT

ROOT = Path(__file__).resolve().parents[1]
# The application never downloads weights at runtime.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"


def _local_connections_only(event, args):
    if event == "socket.connect":
        address = args[1]
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise PermissionError("Studio runtime permits loopback connections only")


sys.addaudithook(_local_connections_only)


class LocalLLM:
    model = "qwen3:4b-instruct-2507-q4_K_M"

    def __init__(self):
        self.client = httpx.AsyncClient(base_url="http://127.0.0.1:11435", timeout=90, trust_env=False)

    async def close(self):
        await self.client.aclose()

    async def health(self):
        try:
            response = await self.client.get("/api/tags", timeout=2)
            response.raise_for_status()
            models = [m["name"] for m in response.json()["models"]]
            return "ready" if self.model in models else "model_missing"
        except Exception:
            return "unavailable"

    async def json(self, system: str, messages: list[dict], audit=False, max_chars=DEFAULT_REPLY_LIMIT):
        plain_reply = not audit and "instruct" in self.model
        if not audit:
            system += ("\n只输出给观众的回答正文，不输出JSON、分析过程或动作标签。" if plain_reply
                       else "\n按指定JSON结构返回text和action。")
        schema = {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["allow", "refuse", "review"]},
                "category": {"type": "string", "enum": list(CATEGORIES)},
            } if audit else {
                "text": {"type": "string", "maxLength": max_chars},
                "action": {"type": "string", "enum": ["idle", "nod", "wave", "smile", "confused"]},
            },
            "required": ["decision", "category"] if audit else ["text", "action"],
            "additionalProperties": False,
        }
        body = {
            "model": self.model, "stream": False, "format": schema,
            "messages": [{"role": "system", "content": system}, *messages],
            "options": {"num_ctx": 4096, "num_predict": 180 if audit else min(3200, max_chars * 2 + 200),
                        "temperature": 0 if audit else 0.7, "repeat_penalty": 1.1},
            "keep_alive": "30m",
        }
        if plain_reply:
            body.pop("format")
        if "instruct" not in self.model:
            body["think"] = False
        response = await self.client.post("/api/chat", json=body, timeout=90 if audit else 240)
        response.raise_for_status()
        content = response.json()["message"]["content"]
        if plain_reply:
            question = messages[-1]["content"] if messages else ""
            action = "wave" if any(word in question for word in ("挥手", "你好", "招呼", "再见")) else "smile" if any(word in question for word in ("笑话", "开心", "微笑")) else "nod"
            return {"text": content.strip(), "action": action}
        return json.loads(content)


class LocalVoice:
    def __init__(self):
        self.pipeline = None
        self.lock = threading.Lock()
        self.directory = ROOT / "models" / "kokoro"

    def health(self):
        return "ready" if all((self.directory / p).exists() for p in
                              ["config.json", "kokoro-v1_0.pth", "voices/zf_xiaobei.pt"]) else "model_missing"

    def synthesize(self, text: str) -> tuple[bytes, float]:
        # A cancelled asyncio waiter cannot cancel Torch; the lock prevents overlapping CPU jobs.
        with self.lock:
            import numpy as np
            import soundfile as sf
            import torch
            from kokoro import KModel, KPipeline

            if self.pipeline is None:
                if self.health() != "ready":
                    raise RuntimeError("voice_model_missing")
                torch.set_num_threads(4)
                model = KModel(repo_id="hexgrad/Kokoro-82M", config=str(self.directory / "config.json"),
                               model=str(self.directory / "kokoro-v1_0.pth")).to("cpu").eval()
                self.pipeline = KPipeline(lang_code="z", model=model, device="cpu", repo_id="hexgrad/Kokoro-82M")
            chunks = [result.audio.numpy() for result in self.pipeline(
                text, voice=str(self.directory / "voices/zf_xiaobei.pt"), speed=1.05)
                      if result.audio is not None]
            if not chunks:
                raise RuntimeError("voice_empty")
            audio = np.concatenate(chunks)
            if not np.isfinite(audio).all() or len(audio) > 24000 * 60:
                raise RuntimeError("voice_invalid")
            buffer = io.BytesIO()
            sf.write(buffer, audio, 24000, format="WAV", subtype="PCM_16")
            return buffer.getvalue(), len(audio) / 24000

    async def speak(self, text):
        return await asyncio.wait_for(asyncio.to_thread(self.synthesize, text), timeout=60)
