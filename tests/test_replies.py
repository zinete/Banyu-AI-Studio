import asyncio

import pytest

from backend.engine import Item
from backend.replies import (compact_turn, quality_issue, reply_spec, selected_history, speech_chunks)
from test_safety import ALLOW, Voice, engine


@pytest.mark.parametrize("question,target", [("给我讲100字的故事", 100), ("给我输出500字的故事", 500),
                                            ("讲一千字的故事", 1000), ("写约1000字的故事", 1000)])
def test_explicit_requested_length_is_honoured(question, target):
    spec = reply_spec(question)
    assert spec.target == target and spec.maximum >= target
    assert quality_issue(question, "一只小猫发现蘑菇里的星星，你今天真勇敢。", spec, []) == "回答未达到请求字数"


def test_unrelated_numeric_history_is_not_a_writing_instruction():
    history = [{"input": "111", "answer": "111"}, {"input": "你好", "answer": "你好呀"}]
    assert selected_history(history, "给我写500字的故事") == []
    assert compact_turn("111", "111") is None
    assert quality_issue("给我讲个故事", "111", reply_spec("给我讲个故事"), []) == "回答未回应当前问题"


def test_story_followup_retains_meaningful_context():
    history = [{"input": "讲个故事", "answer": "小熊在森林里找到一封信。"}]
    assert selected_history(history, "把刚才的故事扩写到1000字") == history


def test_long_followup_reserves_context_space_for_its_answer():
    history = [{"input": "描述前情" * 20, "answer": "这是此前的故事内容。" * 40} for _ in range(4)]
    selected = selected_history(history, "把刚才的故事扩写到1000字")
    assert sum(len(t["input"]) + len(t["answer"]) for t in selected) <= 700


def test_request_above_supported_length_gets_an_honest_limit_instead_of_a_silent_shortcut():
    spec = reply_spec("写一万字的故事")
    assert spec.target is None and spec.requested == 10000
    assert "说明" in spec.instruction and "分章节" in spec.instruction


def test_quality_does_not_reject_numeric_math_or_explicit_copy():
    assert quality_issue("17加25是多少", "42", reply_spec("17加25是多少"), []) is None
    assert quality_issue("请只输出111", "111", reply_spec("请只输出111"), []) is None


def test_identical_old_story_is_not_accepted_for_a_different_question():
    story = "小猫在雨中追着彩虹跑，发现一朵会发光的蘑菇，蘑菇里的星星向它问好。"
    assert quality_issue("换一个故事", story, reply_spec("换一个故事"),
                         [{"input": "讲个故事", "answer": story}]) == "回答重复了历史内容"


def test_length_alone_cannot_pass_repeated_padding_or_unfinished_story():
    spec = reply_spec("讲100字故事")
    text = "小熊找到朋友，一起走过森林。" + "✅" * 60
    assert quality_issue("讲个故事", text, reply_spec("讲个故事"), []) == "回答出现重复凑字"
    assert quality_issue("讲100字故事", "小熊找到了一片树林，" * 9 + "它走进去", spec, []) is not None


def test_speech_segmentation_is_lossless_and_bounded():
    text = "一二打开窗户，看见布布正在花园里种花。" * 50
    chunks = speech_chunks(text)
    assert len(chunks) > 1 and "".join(chunks) == text
    assert all(0 < len(chunk) <= 150 for chunk in chunks)


async def finish(e, item, edited=None):
    e.items[item.id] = item
    task = asyncio.create_task(e.process(item, edited, 0))
    seen = set()
    while not task.done():
        if e.playback_id and e.playback_id not in seen:
            seen.add(e.playback_id)
            e.acknowledge(item.id, "started", e.playback_id)
            e.acknowledge(item.id, "ended", e.playback_id)
        await asyncio.sleep(0)
    await task
    return seen


def test_failed_answer_is_regenerated_before_auditing_and_speech(tmp_path):
    async def scenario():
        good = "小熊在森林里发现一封信。它沿着信上的地图找到迷路的小鸟，陪它回到了树上的家。"
        e = engine(tmp_path, [ALLOW, {"text": "111", "action": "idle"}, {"text": good, "action": "nod"}, ALLOW])
        item = Item("x", "小麦", "讲个故事")
        await asyncio.wait_for(finish(e, item), 2)
        assert item.status == "done" and item.candidate == good and e.voice.calls == 1
        assert e.llm.calls == 4
    asyncio.run(scenario())


def test_two_irrelevant_replies_go_to_review_without_speaking(tmp_path):
    async def scenario():
        e = engine(tmp_path, [ALLOW, {"text": "111", "action": "idle"}, {"text": "111", "action": "idle"}])
        item = Item("x", "小麦", "讲个故事")
        await e.process(item, None, 0)
        assert item.status == "review" and not e.history and e.voice.calls == 0
    asyncio.run(scenario())


def test_long_approved_answer_plays_unique_segments_and_finishes_once(tmp_path):
    async def scenario():
        e = engine(tmp_path, [ALLOW])
        text = "小熊和朋友沿着山路走到湖边，看见水面映着星星。" * 20
        item = Item("x", "小麦", "讲个故事")
        ids = await asyncio.wait_for(finish(e, item, text), 2)
        assert item.status == "done" and len(ids) == len(speech_chunks(text)) > 1
        assert e.voice.calls == len(ids) and not e.audio and not e.playback_id
        assert len(e.history) == 1
    asyncio.run(scenario())


def test_late_acknowledgement_cannot_finish_a_new_segment(tmp_path):
    async def scenario():
        e = engine(tmp_path, [ALLOW])
        item = Item("x", "小麦", "讲个故事")
        e.items[item.id] = item
        task = asyncio.create_task(e.process(item, "这是一个已审核的长故事。" * 30, 0))
        while not e.playback_id:
            await asyncio.sleep(0)
        old = e.playback_id
        e.acknowledge(item.id, "ended", old)
        while not e.playback_id or e.playback_id == old:
            await asyncio.sleep(0)
        with pytest.raises(ValueError, match="片段"):
            e.acknowledge(item.id, "ended", old)
        assert not e.play_done.is_set()
        while not task.done():
            if e.playback_id:
                e.acknowledge(item.id, "ended", e.playback_id)
            await asyncio.sleep(0)
        await task
    asyncio.run(scenario())


def test_stop_between_segments_revokes_late_speech(tmp_path):
    class WaitingVoice(Voice):
        async def speak(self, text):
            self.calls += 1
            if self.calls == 2:
                entered.set()
                await release.wait()
            return b"wav", .01

    async def scenario():
        nonlocal entered, release
        entered, release = asyncio.Event(), asyncio.Event()
        e = engine(tmp_path, [ALLOW], WaitingVoice())
        item = Item("x", "小麦", "讲个故事", status="review")
        e.items[item.id] = item
        worker = asyncio.create_task(e.run())
        e.edit(item.id, "这是一个已审核的长故事。" * 30)
        while not e.playback_id:
            await asyncio.sleep(0)
        e.acknowledge(item.id, "ended", e.playback_id)
        await entered.wait()
        await e.stop()
        release.set()
        await asyncio.sleep(.01)
        assert item.status == "cancelled" and not e.audio and e.playback_id is None
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
    entered = release = None
    asyncio.run(scenario())
