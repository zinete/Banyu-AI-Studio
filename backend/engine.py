import asyncio
import json
import time
import uuid
from collections import deque
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .safety import ACTIONS, AUDITOR, CATEGORIES, Rules, Verdict
from .conversation import host_messages, host_system
from .replies import MAX_REPLY_LIMIT, compact_turn, quality_issue, repair_instruction, reply_spec, selected_history, speech_chunks


class Stale(Exception):
    pass


@dataclass
class Item:
    id: str
    nickname: str
    text: str
    status: str = "queued"
    category: str = "等待检查"
    candidate: str = ""
    action: str = "idle"
    submitted: float = field(default_factory=time.monotonic)
    latency: float | None = None
    segment_index: int = 0
    segments_total: int = 1


class Engine:
    def __init__(self, llm, voice, root: Path):
        self.llm, self.voice, self.root = llm, voice, root
        self.rules = Rules(root / "config/rules.json")
        self.items: dict[str, Item] = {}
        self.queue = asyncio.Queue(maxsize=30)
        self.listeners = {}
        self.player = None
        self.epoch = 0
        self.stopped = True
        self.mode = "auto"
        self.history = deque(maxlen=4)
        self.events = deque(maxlen=100)
        self.metrics = deque(maxlen=1000)
        self.audio = {}
        self.playing = None
        self.playback_id = None
        self.play_done = asyncio.Event()
        self.job = None
        self.worker = None
        self.lock = asyncio.Lock()
        self.debug = False
        self.data = root / "data"
        self.data.mkdir(exist_ok=True)

    def snapshot(self):
        return {"stopped": self.stopped, "mode": self.mode, "epoch": self.epoch,
                "player_connected": self.player is not None,
                "items": [asdict(x) for x in reversed(list(self.items.values()))],
                "events": list(self.events), "playing": self.playing,
                "debug": self.debug, "rules_version": self.rules.version,
                "metrics": list(self.metrics)}

    def emit(self, kind="state", **payload):
        for key, (role, queue) in list(self.listeners.items()):
            if kind == "play" and (role != "display" or key != self.player):
                continue
            # Raw audience data and pending output never leave the control channel.
            if kind == "state":
                event = {"type": "state", **self.snapshot()} if role == "control" else {
                    "type": "state", "stopped": self.stopped, "epoch": self.epoch}
            else:
                event = {"type": kind, "epoch": self.epoch, **payload}
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # A slow consumer is disconnected by its writer. Never silently lose a stop.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"type": "disconnect", "epoch": self.epoch})

    def record(self, category, duration=0):
        event = {"category": category, "duration": round(duration, 3), "time": time.time()}
        self.events.appendleft(event)
        with (self.data / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def check_epoch(self, epoch):
        if self.stopped or epoch != self.epoch:
            raise Stale()

    def submit(self, nickname, text):
        if self.stopped:
            raise ValueError("已暂停，请先启用自动回答")
        if self.queue.full() or sum(x.status == "review" for x in self.items.values()) >= 50:
            raise ValueError("队列已满，请先处理待审内容")
        item = Item(uuid.uuid4().hex, nickname, text)
        self.items[item.id] = item
        # Bound raw data held in memory; pending items are never evicted.
        for old in list(self.items):
            if len(self.items) <= 200:
                break
            if self.items[old].status in {"done", "refused", "discarded", "cancelled", "error"}:
                del self.items[old]
        if self.debug:
            with (self.data / "debug.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"id": item.id, "nickname": nickname, "text": text}, ensure_ascii=False) + "\n")
        self.queue.put_nowait((item.id, None, self.epoch))
        self.emit()
        return item.id

    async def moderate(self, text, context, epoch, allow_support=False):
        self.check_epoch(epoch)
        hard = self.rules.check(text)
        if hard.decision == "refuse":
            return hard
        # A supportive edited response can clear the self-harm review through semantic auditing.
        if hard.decision == "review" and not (allow_support and hard.category == "自伤求助"):
            return hard
        try:
            result = await self.llm.json(AUDITOR, [{"role": "user", "content": json.dumps({
                "content": text, "approved_context": context}, ensure_ascii=False)}], audit=True)
            self.check_epoch(epoch)
            if (not isinstance(result, dict) or result.get("decision") not in {"allow", "refuse", "review"}
                    or not isinstance(result.get("category"), str) or result["category"] not in CATEGORIES):
                return Verdict("review", "审核格式错误")
            decision, category = result["decision"], result["category"]
            # A contradictory "allow" must never override an explicitly risky classification.
            if category in {"提示注入", "越权操作", "危险实施", "性剥削", "隐私窃取", "威胁骚扰", "色情", "仇恨煽动", "不适宜"}:
                decision = "refuse"
            elif category in {"无法判断", "争议话题", "高风险个体建议"} or (category == "自伤求助" and not allow_support):
                if decision == "allow":
                    decision = "review"
            return Verdict(decision, category)
        except (Stale, asyncio.CancelledError):
            raise
        except Exception:
            return Verdict("review", "审核服务不可用")

    async def process(self, item, edited, epoch):
        self.check_epoch(epoch)
        item.status = "checking"
        self.emit()
        # Original hard restrictions cannot be overridden by an administrator edit.
        original = self.rules.check(item.nickname + "\n" + item.text)
        if original.decision == "refuse":
            return self.resolve(item, original)
        context = selected_history(list(self.history), item.text)
        quality_context = [{"input": old.text, "answer": old.candidate}
                           for old in list(self.items.values())[-8:] if old.status == "done"] + list(self.history)
        if edited is None:
            verdict = await self.moderate(item.nickname + "\n" + item.text, context, epoch)
            if verdict.decision != "allow":
                return self.resolve(item, verdict)
            item.status = "generating"
            self.emit()
            spec = reply_spec(item.text)
            issue = None
            previous_text = ""
            for attempt in range(2):
                system = host_system(getattr(self.llm, "model", "qwen3:4b"), spec=spec)
                if attempt:
                    system += "\n" + repair_instruction(issue, spec, previous_text)
                    item.category = "正在重新生成：" + issue
                    self.emit()
                reply = await self.llm.json(system, host_messages(context, item.text), max_chars=spec.maximum)
                self.check_epoch(epoch)
                if (not isinstance(reply, dict) or not isinstance(reply.get("text"), str)
                        or not 0 < len(reply["text"].strip()) <= MAX_REPLY_LIMIT * 3
                        or not isinstance(reply.get("action"), str) or reply["action"] not in ACTIONS):
                    return self.resolve(item, Verdict("review", "回答格式或动作不合法"))
                issue = quality_issue(item.text, reply["text"].strip(), spec, quality_context)
                previous_text = reply["text"].strip()
                if not issue:
                    break
            if issue:
                return self.resolve(item, Verdict("review", issue))
            item.candidate, item.action = reply["text"].strip(), reply["action"]
        else:
            item.candidate, item.action = edited, "nod"
        item.status = "checking_output"
        self.emit()
        verdict = await self.moderate(item.candidate, context, epoch, allow_support=True)
        self.check_epoch(epoch)
        if verdict.decision != "allow":
            return self.resolve(item, verdict)
        if self.mode == "manual" and edited is None:
            return self.resolve(item, Verdict("review", "人工模式待确认"))
        item.category = "审核通过"
        chunks = speech_chunks(item.candidate)
        item.segments_total = len(chunks)
        for index, chunk in enumerate(chunks, 1):
            self.check_epoch(epoch)
            item.status, item.segment_index = "synthesizing", index
            self.emit()
            wav, duration = await self.voice.speak(chunk)
            self.check_epoch(epoch)
            if not self.player:
                return self.resolve(item, Verdict("review", "展示页未连接"))
            playback_id = uuid.uuid4().hex
            self.playback_id = playback_id
            item.status = "playing"
            self.audio[playback_id] = wav
            self.playing = item.id
            self.play_done.clear()
            self.emit("play", id=item.id, playback_id=playback_id, text=chunk, action=item.action,
                      audio=f"/api/audio/{playback_id}", duration=duration)
            self.emit()
            try:
                await asyncio.wait_for(self.play_done.wait(), timeout=duration + 15)
            except TimeoutError:
                await self.stop("播放确认超时")
                return
            self.check_epoch(epoch)
            self.audio.pop(playback_id, None)
            self.playback_id = None
        item.status = "done"
        turn = compact_turn(item.text, item.candidate)
        if turn:
            self.history.append(turn)
        self.playing = None
        self.record("播放完成", time.monotonic() - item.submitted)
        self.emit()

    def resolve(self, item, verdict):
        if self.playing == item.id:
            self.audio.pop(self.playback_id, None)
            self.playback_id = None
            self.playing = None
            self.play_done.set()
            self.emit("stop")
        item.status = "refused" if verdict.decision == "refuse" else "review"
        item.category = verdict.category
        self.record(verdict.category, time.monotonic() - item.submitted)
        self.emit()

    async def run(self):
        while True:
            item_id, edited, epoch = await self.queue.get()
            item = self.items[item_id]
            try:
                self.check_epoch(epoch)
                self.job = asyncio.create_task(self.process(item, edited, epoch))
                await self.job
            except asyncio.CancelledError:
                if asyncio.current_task().cancelling():
                    raise
            except Stale:
                pass
            except Exception:
                if epoch == self.epoch and not self.stopped:
                    self.resolve(item, Verdict("review", "处理失败，请检查本地服务"))
            finally:
                self.job = None
                self.queue.task_done()

    async def stop(self, reason="管理员急停"):
        # No await before revoking every pending capability.
        self.stopped = True
        self.epoch += 1
        self.audio.clear()
        self.playing = None
        self.playback_id = None
        self.history.clear()
        self.play_done.set()
        while not self.queue.empty():
            self.queue.get_nowait()
            self.queue.task_done()
        for item in self.items.values():
            if item.status not in {"done", "refused", "discarded", "cancelled"}:
                item.status, item.category = "cancelled", reason
        if self.job and self.job is not asyncio.current_task():
            self.job.cancel()
        self.record(reason)
        self.emit("stop")
        self.emit()

    def acknowledge(self, item_id, phase, playback_id=None):
        item = self.items.get(item_id)
        if self.stopped or self.playing != item_id or not item or item.status != "playing":
            raise ValueError("播放任务已失效")
        if playback_id is not None and playback_id != self.playback_id:
            raise ValueError("播放片段已失效")
        if phase == "started":
            if item.latency is None:
                item.latency = time.monotonic() - item.submitted
                self.metrics.append({"latency": round(item.latency, 3), "time": time.time()})
                self.emit()
        elif phase == "ended":
            self.play_done.set()

    def edit(self, item_id, text):
        if self.stopped or self.queue.full():
            raise ValueError("当前已暂停或队列已满")
        item = self.items[item_id]
        if item.status != "review":
            raise ValueError("该条目不在待审队列")
        item.status = "queued"
        self.queue.put_nowait((item.id, text, self.epoch))
        self.emit()
