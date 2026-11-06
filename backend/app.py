import asyncio
import contextlib
import json
import secrets
import time
import ipaddress
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .engine import Engine
from .providers import ROOT, LocalLLM, LocalVoice
from .replies import MAX_REPLY_LIMIT


class Message(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    nickname: str = Field(min_length=1, max_length=24)
    text: str = Field(min_length=1, max_length=500)


class Edit(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=MAX_REPLY_LIMIT)


def create_app(engine=None, lan_config=None):
    token = secrets.token_urlsafe(32)
    if lan_config is None:
        config_path = ROOT / ".runtime/lan.json"
        lan_config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    lan_host = lan_config.get("host")
    lan_access = lan_config.get("access_token", "")
    if lan_host:
        address = ipaddress.ip_address(lan_host)
        if (address.version != 4 or not address.is_private or address.is_loopback
                or address.is_unspecified or address.is_multicast or len(lan_access) < 32):
            raise ValueError("Invalid LAN configuration")
    hosts = ["127.0.0.1", "localhost", "testserver"] + ([lan_host] if lan_host else [])
    origins = {"http://127.0.0.1:8765", "http://localhost:8765", "http://testserver"}
    if lan_host:
        origins.add(f"http://{lan_host}:8765")
    websocket_sources = " ".join(origin.replace("http://", "ws://") for origin in sorted(origins))

    @asynccontextmanager
    async def lifespan(app):
        app.state.engine = engine or Engine(LocalLLM(), LocalVoice(), ROOT)
        e = app.state.engine
        e.worker = asyncio.create_task(e.run())
        yield
        await e.stop("服务关闭")
        e.worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await e.worker
        await e.llm.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    def allowed_origin(origin):
        return origin in origins

    @app.middleware("http")
    async def guard(request: Request, call_next):
        local_peer = request.client and request.client.host in {"127.0.0.1", "::1", "testclient"}
        if lan_host and not local_peer:
            access = request.query_params.get("access", "")
            if (request.method == "GET" and request.url.path in {"/", "/display"}
                    and secrets.compare_digest(access.encode("utf-8"), lan_access.encode("utf-8"))):
                response = RedirectResponse(request.url.path, status_code=303)
                response.set_cookie("studio_session", token, httponly=True, samesite="strict")
                response.headers["Referrer-Policy"] = "no-referrer"
                response.headers["Cache-Control"] = "no-store"
                return response
            if not secrets.compare_digest(request.cookies.get("studio_session", "").encode("utf-8"), token.encode("utf-8")):
                return JSONResponse({"detail": "请使用带访问令牌的内网链接"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and not allowed_origin(origin):
            return JSONResponse({"detail": "Origin forbidden"}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site forbidden"}, status_code=403)
        if request.method not in {"GET", "HEAD"}:
            if request.cookies.get("studio_session") != token or request.headers.get("x-studio") != "1":
                return JSONResponse({"detail": "Control authentication required"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; media-src 'self' blob:; "
            f"connect-src 'self' blob: {websocket_sources}; "
            "worker-src 'self' blob:; frame-ancestors 'self'")
        return response

    def auth(request):
        if request.cookies.get("studio_session") != token:
            raise HTTPException(403, "Control authentication required")

    @app.get("/api/session")
    async def session():
        response = JSONResponse({"ok": True})
        response.set_cookie("studio_session", token, httponly=True, samesite="strict")
        return response

    @app.get("/favicon.ico")
    async def favicon():
        return Response(status_code=204)

    @app.get("/api/health")
    async def health():
        e = app.state.engine
        return {"llm": await e.llm.health(), "voice": e.voice.health(),
                "avatar": (ROOT / "frontend/src/bears.ts").exists(), "avatar_kind": "yier_bubu_3d",
                "local_only": not bool(lan_host), "lan_enabled": bool(lan_host), "offline_inference": True}

    @app.get("/api/state")
    async def state(request: Request):
        auth(request)
        return app.state.engine.snapshot()

    @app.post("/api/messages")
    async def submit(message: Message):
        try:
            return {"id": app.state.engine.submit(message.nickname, message.text)}
        except ValueError as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/control/{command}")
    async def control(command: str):
        e = app.state.engine
        async with e.lock:
            if command == "stop":
                await e.stop()
            elif command == "resume":
                if not e.player:
                    raise HTTPException(409, "请先连接并启用展示页声音")
                if await e.llm.health() != "ready" or e.voice.health() != "ready":
                    raise HTTPException(409, "本地模型或语音尚未就绪")
                e.stopped = False
                e.emit()
            elif command in {"auto", "manual"}:
                # Switch with revocation, then explicit resume is required.
                await e.stop("切换控制模式")
                e.mode = command
                e.emit()
            elif command == "reload-rules":
                await e.stop("重载风控规则")
                try:
                    e.rules.reload()
                except Exception:
                    raise HTTPException(422, "规则格式错误，系统保持暂停")
            elif command == "debug-on":
                e.debug = True
            elif command == "debug-off":
                e.debug = False
            elif command == "clear-logs":
                e.debug = False
                for name in ["events.jsonl", "debug.jsonl"]:
                    (e.data / name).unlink(missing_ok=True)
                e.events.clear()
            else:
                raise HTTPException(404)
            e.emit()
            return {"ok": True}

    @app.post("/api/review/{item_id}/edit")
    async def edit(item_id: str, body: Edit):
        try:
            app.state.engine.edit(item_id, body.text)
            return {"ok": True}
        except (KeyError, ValueError) as exc:
            raise HTTPException(409, str(exc))

    @app.post("/api/review/{item_id}/discard")
    async def discard(item_id: str):
        e = app.state.engine
        item = e.items.get(item_id)
        if not item or item.status != "review":
            raise HTTPException(409, "该条目不在待审队列")
        item.status = "discarded"
        item.candidate = ""
        e.emit()
        return {"ok": True}

    @app.get("/api/audio/{item_id}")
    async def audio(item_id: str):
        e = app.state.engine
        if e.stopped or e.playback_id != item_id or item_id not in e.audio:
            raise HTTPException(404)
        return Response(e.audio[item_id], media_type="audio/wav")

    @app.websocket("/ws/{role}")
    async def websocket(ws: WebSocket, role: str):
        if (role not in {"control", "display"} or not allowed_origin(ws.headers.get("origin"))
                or ws.cookies.get("studio_session") != token):
            await ws.close(code=1008)
            return
        e = app.state.engine
        await ws.accept()
        key = secrets.token_hex(16)
        queue = asyncio.Queue(maxsize=32)
        e.listeners[key] = (role, queue)
        e.emit()

        async def send():
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=3)
                except TimeoutError:
                    event = {"type": "heartbeat", "epoch": e.epoch, "stopped": e.stopped}
                if event["type"] == "disconnect":
                    await ws.close(code=1013)
                    return
                await asyncio.wait_for(ws.send_json(event), timeout=2)

        sender = asyncio.create_task(send())
        try:
            while True:
                message = await asyncio.wait_for(ws.receive_json(), timeout=12)
                if not isinstance(message, dict):
                    raise ValueError("Invalid message")
                kind = message.get("type")
                if role == "display" and kind == "ready":
                    if e.player and e.player != key and message.get("replace") is True:
                        await e.stop("切换展示页")
                        e.player = key
                        e.emit()
                    elif e.player and e.player != key:
                        await ws.send_json({"type": "error", "message": "已有展示页负责播放，请关闭重复页面"})
                    else:
                        e.player = key
                        e.emit()
                if role == "display" and e.player == key and kind == "playback":
                    if message.get("epoch") != e.epoch:
                        continue
                    if not e.playback_id or message.get("playback_id") != e.playback_id:
                        continue
                    phase = message.get("phase")
                    if phase == "error":
                        await e.stop("播放失败")
                    elif phase in {"started", "ended"}:
                        e.acknowledge(message.get("id"), phase, message.get("playback_id"))
                if role == "display" and e.player == key and kind == "fps":
                    value = float(message.get("value", 0))
                    if 0 <= value <= 1000:
                        e.metrics.append({"fps": round(value, 1), "time": time.time()})
        except (WebSocketDisconnect, TimeoutError, ValueError, RuntimeError, json.JSONDecodeError):
            pass
        finally:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sender
            e.listeners.pop(key, None)
            if e.player == key:
                e.player = None
                await e.stop("展示页已断开")

    dist = ROOT / "frontend/dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/avatar.vrm")
        async def avatar():
            return FileResponse(ROOT / "frontend/public/avatar.vrm", media_type="model/gltf-binary")

        @app.get("/{path:path}")
        async def frontend(path: str):
            if path not in {"", "display"}:
                raise HTTPException(404)
            return FileResponse(dist / "index.html")
    return app


app = create_app()
