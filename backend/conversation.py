"""Build standard conversation turns and trusted runtime facts independently of audience input."""
from datetime import datetime, timedelta, timezone

from .safety import HOST
from .replies import ReplySpec, selected_history

BEIJING = timezone(timedelta(hours=8), name="Asia/Shanghai")
WEEKDAYS = ("一", "二", "三", "四", "五", "六", "日")


def host_system(model_id="qwen3:4b", now=None, spec=None):
    current = (now or datetime.now(BEIJING)).astimezone(BEIJING)
    model_name = ("Qwen3 4B Instruct 2507（Q4_K_M量化版）" if model_id.startswith("qwen3:4b-instruct")
                  else "Qwen3 4B（Q4_K_M量化版）" if model_id == "qwen3:4b" else model_id)
    return (f"{HOST}\n\n以下为程序提供的可信运行信息：\n"
            "主播名字：一二；同台陪伴角色：布布。旧对话中的其他主播称呼不再使用。\n"
            f"北京时间：{current.year}年{current.month}月{current.day}日，"
            f"星期{WEEKDAYS[current.weekday()]}，{current:%H:%M}。\n"
            f"底层对话模型：{model_name}；通过本机Ollama运行。\n"
            "语音合成：本地Kokoro。能力：中文聊天、一般知识问答、简单计算、游戏影视讨论。\n"
            "无联网查询、电脑控制、支付或外部操作权限。以上日期和模型信息优先于历史回答。\n"
            + (spec or ReplySpec()).instruction)


def host_messages(history, question):
    messages = []
    for turn in selected_history(history, question):
        messages.append({"role": "user", "content": turn["input"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    messages.append({"role": "user", "content": question})
    return messages
