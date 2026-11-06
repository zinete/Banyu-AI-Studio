"""Real-model regressions for the user's numeric-echo and requested-length examples."""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.conversation import host_messages, host_system
from backend.providers import LocalLLM
from backend.replies import compact_turn, quality_issue, repair_instruction, reply_spec, speech_chunks
from backend.safety import AUDITOR


async def main():
    llm = LocalLLM()
    llm.model = "qwen3:4b-instruct-2507-q4_K_M"
    history = [{"input": "111", "answer": "111"}]
    results = []
    try:
        for question in ["给我讲个100字的故事", "给我输出500字的故事", "给我讲个1000字的故事"]:
            spec = reply_spec(question)
            issue = None
            previous_text = ""
            for attempt in range(2):
                system = host_system(llm.model, spec=spec)
                if attempt:
                    system += "\n" + repair_instruction(issue, spec, previous_text)
                reply = await llm.json(system, host_messages(history, question), max_chars=spec.maximum)
                text = reply["text"]
                issue = quality_issue(question, text, spec, history)
                previous_text = text
                if not issue:
                    break
            audit = await llm.json(AUDITOR, [{"role": "user", "content": json.dumps({"content": text, "approved_context": []}, ensure_ascii=False)}], audit=True)
            row = {"question": question, "answer": text, "characters": len(text), "target": spec.target,
                   "segments": len(speech_chunks(text)), "quality_issue": issue, "audit": audit,
                   "attempts": attempt + 1, "passed": issue is None and audit["decision"] == "allow"}
            results.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "answer"}, ensure_ascii=True), flush=True)
            turn = compact_turn(question, text)
            if turn:
                history.append(turn)
            target = Path(__file__).resolve().parents[1] / "docs/verification/story-quality.json"
            target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        if not all(row["passed"] for row in results):
            raise AssertionError("Story relevance / length / safety check failed")
    finally:
        await llm.close()


asyncio.run(main())
