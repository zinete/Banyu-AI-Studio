"""Answer-length policy, history hygiene, quality gates and safe speech segmentation."""
import re
from dataclasses import dataclass

DEFAULT_REPLY_LIMIT = 360
MAX_REPLY_LIMIT = 1600
MAX_REQUESTED_LENGTH = 1200
SPEECH_CHUNK_LIMIT = 150


@dataclass(frozen=True)
class ReplySpec:
    target: int | None = None
    maximum: int = DEFAULT_REPLY_LIMIT
    requested: int | None = None
    story: bool = False

    @property
    def instruction(self):
        if self.requested and self.requested > MAX_REQUESTED_LENGTH:
            return (f"用户要求{self.requested}字，超过本机演示版单次约{MAX_REQUESTED_LENGTH}字的上限。"
                    "请简短说明这个限制，建议分章节写，不要假装已经完成全文。")
        if self.target:
            structure = "故事要有起因、经过、结尾，写出具体的动作和对话，不能用几句话的梗概代替。" if self.story else "围绕用户要求的主题写出完整内容。"
            return (f"本轮请输出约{self.target}个汉字的完整正文，至少{int(self.target * .8)}个汉字（标点不计），"
                    f"含标点不超过{self.maximum}字符。{structure}"
                    "直接写正文，不写创作分析、思考过程或字数说明，不重复段落凑字。")
        return f"本轮先直接、自然地回答问题，简明但信息充分，最多{self.maximum}字符，不机械限制句数。"


def chinese_number(value):
    if value.isdecimal():
        return int(value)
    digits = dict(zip("零一二三四五六七八九", range(10)))
    digits["两"] = 2
    units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
    total = number = 0
    for char in value:
        if char in digits:
            number = digits[char]
        elif char in units:
            total += (number or 1) * units[char]
            number = 0
    return total + number


def reply_spec(question):
    matches = re.findall(r"([0-9零一二两三四五六七八九十百千万]+)\s*(?:个)?字", question)
    lengths = [chinese_number(value) for value in matches]
    lengths = [n for n in lengths if n >= 30]
    if not lengths:
        return ReplySpec()
    requested = lengths[-1]
    if requested > MAX_REQUESTED_LENGTH:
        return ReplySpec(requested=requested)
    target = min(requested, MAX_REQUESTED_LENGTH)
    return ReplySpec(target, min(MAX_REPLY_LIMIT, int(target * 1.25) + 40), requested,
                     bool(re.search(r"故事|童话|小说|短篇", question)))


def repair_instruction(issue, spec, previous_text):
    note = f"上一轮未通过回答质量检查：{issue}。请重新完整回答当前问题，不复述旧答案。"
    if spec.target:
        if issue == "回答超过本轮长度限制":
            note += f"上一轮过长。请压缩到约{spec.target}字、含标点最多{spec.maximum}字符，保留完整结尾。"
        else:
            note += (f"上一轮只有{len(normalize(previous_text))}个有效字符。"
                     f"现在请补充具体细节，写到约{spec.target}个汉字，至少{int(spec.target * .8)}个汉字，不能缩写。")
    return note


def normalize(text):
    return re.sub(r"[\W_]+", "", text.casefold())


def meaningful_turn(question, answer):
    q, a = normalize(question), normalize(answer)
    return bool(q and a) and not q.isdecimal() and not (q == a and len(q) < 20)


def selected_history(history, question):
    turns = [turn for turn in history if meaningful_turn(turn["input"], turn["answer"])]
    creative = re.search(r"故事|作文|文章|文案|童话|短篇|小说", question)
    referring = re.search(r"刚才|之前|上面|上述|接着|继续|这个|那个|同一个|扩写|改写|续写|再写|它", question)
    # A fresh writing task is independent of unrelated numbers, greetings and old stories.
    if creative and not referring:
        return []
    budget = 700 if (reply_spec(question).target or 0) >= 500 else 1200
    selected = []
    for turn in reversed(turns[-(2 if creative else 4):]):
        size = len(turn["input"]) + len(turn["answer"])
        if size > budget:
            if not selected:
                selected.append({"input": turn["input"][:160], "answer": turn["answer"][:max(80, budget - 160)]})
            break
        selected.append(turn)
        budget -= size
    return list(reversed(selected))


def quality_issue(question, text, spec, history):
    if len(text) > spec.maximum:
        return "回答超过本轮长度限制"
    if spec.target and len(normalize(text)) < int(spec.target * .8):
        return "回答未达到请求字数"
    if any(marker in text for marker in ("<think>", "</think>", "首先，用户", "首先,用户", "用户要求我", "思考过程：")):
        return "回答包含内部分析"
    q, answer = normalize(question), normalize(text)
    explicit_copy = re.search(r"原样|照抄|复述|重复|再说一遍|只输出", question)
    if not explicit_copy:
        if re.search(r"(.{1,24})\1{4,}", text):
            return "回答出现重复凑字"
        if answer.isdecimal() and re.search(r"故事|解释|介绍|为什么|如何|怎么|分析|总结|建议", question):
            return "回答未回应当前问题"
        if q == answer and len(q) > 2:
            return "回答原样复读了问题"
        if len(answer) > 24 and any(normalize(turn["answer"]) == answer and normalize(turn["input"]) != q for turn in history):
            return "回答重复了历史内容"
    if spec.story and text[-1] not in "。！？.!?\"'”’」』":
        return "故事似乎没有写完"
    return None


def compact_turn(question, answer):
    if not meaningful_turn(question, answer):
        return None
    context_answer = answer if len(answer) <= 400 else answer[:240] + "……" + answer[-150:]
    return {"input": question[:160], "answer": context_answer}


def speech_chunks(text, limit=SPEECH_CHUNK_LIMIT):
    chunks = []
    while len(text) > limit:
        window = text[:limit]
        boundary = max(window.rfind(mark) for mark in "。！？；\n.!?;") + 1
        cut = boundary if boundary >= limit // 2 else limit
        chunks.append(text[:cut])
        text = text[cut:]
    if text:
        chunks.append(text)
    return chunks
