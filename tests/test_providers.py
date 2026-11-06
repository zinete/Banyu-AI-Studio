import asyncio
import json

import httpx

from backend.providers import LocalLLM


def test_model_requests_enforce_schema_disable_thinking_and_limit_context():
    async def scenario():
        seen = []

        def handler(request):
            body = json.loads(request.content)
            seen.append(body)
            payload = {"decision": "allow", "category": "常规"} if len(seen) == 1 else {"text": "你好", "action": "nod"}
            return httpx.Response(200, json={"message": {"content": json.dumps(payload)}})

        llm = LocalLLM()
        llm.model = "qwen3:4b"
        await llm.close()
        llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11435")
        await llm.json("audit", [{"role": "user", "content": "hello"}], audit=True)
        await llm.json("host", [{"role": "user", "content": "hello"}])
        assert seen[0]["format"]["required"] == ["decision", "category"]
        assert seen[0]["format"]["properties"]["decision"]["enum"] == ["allow", "refuse", "review"]
        assert seen[1]["format"]["properties"]["action"]["enum"] == ["idle", "nod", "wave", "smile", "confused"]
        assert all(x["think"] is False and x["stream"] is False and x["options"]["num_ctx"] == 4096 for x in seen)
        await llm.close()

    asyncio.run(scenario())


def test_instruct_chat_uses_native_text_and_keeps_safety_review_structured():
    async def scenario():
        seen = []

        def handler(request):
            body = json.loads(request.content)
            seen.append(body)
            content = "这是一个完整的故事。" if len(seen) == 1 else json.dumps({"decision": "allow", "category": "常规"})
            return httpx.Response(200, json={"message": {"content": content}})

        llm = LocalLLM()
        await llm.close()
        llm.client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:11435")
        reply = await llm.json("host", [{"role": "user", "content": "讲500字故事"}], max_chars=665)
        audit = await llm.json("audit", [{"role": "user", "content": reply["text"]}], audit=True)
        assert reply == {"text": "这是一个完整的故事。", "action": "nod"}
        assert "format" not in seen[0] and "think" not in seen[0]
        assert seen[0]["options"]["num_predict"] > 1000
        assert seen[1]["format"]["required"] == ["decision", "category"]
        assert audit["decision"] == "allow"
        await llm.close()
    asyncio.run(scenario())
