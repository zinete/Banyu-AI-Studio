"""Check answer relevance with the real local model, including follow-up context."""
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.conversation import BEIJING, WEEKDAYS, host_messages, host_system
from backend.providers import LocalLLM


async def main():
    llm = LocalLLM()
    now = datetime.now(BEIJING)
    history = [{"input": "你可以干啥", "answer": "我是小岚，虚拟主播，能陪你聊游戏、看动画。"},
               {"input": "你是什么模型", "answer": "嗨，小麦！我是小岚，今天想和你一起玩什么呀？"}]
    cases = [
        ("你叫什么名字", lambda s: "一二" in s),
        ("今天几号", lambda s: str(now.year) in s and f"{now.month}月" in s and f"{now.day}日" in s),
        ("你是什么模型，可以做啥", lambda s: "qwen3" in s.lower() and "4b" in s.lower()),
        ("17加25是多少", lambda s: "42" in s),
        ("把刚才的结果乘2", lambda s: "84" in s),
    ]
    results = []
    try:
        for question, check in cases:
            result = await llm.json(host_system(llm.model, now), host_messages(history, question))
            answer = result["text"]
            passed = bool(check(answer)) and len(answer) <= 120
            if question == "今天几号" and "星期" in answer:
                passed = passed and f"星期{WEEKDAYS[now.weekday()]}" in answer
            results.append({"question": question, "answer": answer, "passed": passed})
            print(json.dumps(results[-1], ensure_ascii=True), flush=True)
            history.append({"input": question, "answer": answer})
            history = history[-4:]
        target = Path(__file__).resolve().parents[1] / "docs/verification/dialogue-relevance.json"
        target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        if not all(row["passed"] for row in results):
            raise AssertionError("Real-model relevance regression failed")
    finally:
        await llm.close()


asyncio.run(main())
