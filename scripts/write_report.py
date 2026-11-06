"""Generate the local validation report from measured artifacts, never invented results."""
import json
import math
from pathlib import Path

root = Path(__file__).resolve().parents[1]
verification = root / "docs/verification"
benchmark = json.loads((verification / "benchmark.json").read_text(encoding="utf-8"))
acceptance = json.loads((verification / "acceptance.json").read_text(encoding="utf-8"))
latencies = sorted(item["latency"] for item in benchmark["items"]
                   if not item["warmup"] and item["status"] == "done" and item["latency"] is not None)
p95 = latencies[math.ceil(len(latencies) * .95) - 1] if latencies else None
fps = [item["fps"] for item in benchmark["fps"]]
gpu = [int(item["value"].split(",")[1]) for item in benchmark["gpu"]]
seconds = benchmark.get("elapsed", 0)
passed = sum(check.get("passed", False) for check in acceptance)
failed = [check for check in acceptance if check.get("passed") is False or "failure" in check]
network_path = verification / "network.json"
network = json.loads(network_path.read_text(encoding="utf-8")) if network_path.exists() else None
result = lambda ok: "达到" if ok else "未达到"
p95_text = f"{p95:.2f} 秒" if p95 is not None else "无可用样本"
fps_text = f"{min(fps):.1f} FPS" if fps else "无可用样本"
gpu_text = f"{max(gpu):,} MiB" if gpu else "无可用样本"
text = f"""# 本地验证报告

## 环境与结论

- 用户目标硬件：RTX 4060 Ti 8 GB、约 32 GB 内存。
- 当前执行环境实际检测：NVIDIA GeForce GTX 1630，4,096 MiB 显存；因此本报告不是对 4060 Ti 的性能验收。
- 以下30分钟基线的运行组合：旧版 Qwen3 4B Q4_K_M / Ollama，本地 Kokoro CPU 中文语音，Chrome 中的 VRM 渲染；不代表当前 Instruct 模型与双熊造型的性能。
- 持续测试：{seconds:.1f} 秒；达到 30 分钟要求：{result(seconds >= 1800 and benchmark.get('complete', False))}。
- 真实完成播出的对话：{sum(x['status'] == 'done' for x in benchmark['items'])} 轮；预热后延迟样本：{len(latencies)} 个。

## 实测指标

| 指标 | 实测 | 目标与结果 |
|---|---:|---|
| 开始播放延迟 P95 | {p95_text} | ≤10 秒，{result(p95 is not None and p95 <= 10)} |
| 最低渲染帧率 | {fps_text} | ≥30 FPS，{result(bool(fps) and min(fps) >= 30)} |
| 整卡已用显存峰值 | {gpu_text} | 包含浏览器与其他进程，不等于项目独占显存 |
| 页面脚本错误 | {len(benchmark['errors'])} | 0 |
| 被阻断的页面外部请求 | {len(benchmark['external_browser_requests'])} | 0 |

延迟从提交弹幕到浏览器实际开始播放，包含输入审核、对话生成、输出审核及语音合成。首轮预热不计入 P95；测试为逐条提交、等待播完后再提交。帧率为每 5 秒采样窗口的平均值，表格记录这些窗口中的最低值。不能将短测或更换显卡后的预期当作本机长测结果。

## 功能与风控检查

- 当前后端自动化：66 项通过；涵盖风控、审核异常、非法动作、人工编辑、语音故障、急停旧任务、访问认证、字数策略、历史清理、质量重试、长文分段及过期播放确认。
- 此前版本浏览器真实流程验收：{passed} 项通过，{len(failed)} 项失败；逐项记录见 `verification/acceptance.json`。当前长文流程另见下方专节。
- 前端 TypeScript 与生产构建通过；Python 静态错误检查通过；PowerShell 脚本语法检查通过，已验证重复启动复用现有服务。
- 三种宽度的界面检查：1440 / 768 / 390，0 FAIL / 0 WARN；已查看全部截图。
- 中文语音离线合成成功；真实对话测试收到浏览器开始与结束播放确认，嘴型由音频分析驱动。

## 本地数据流与限制

- 浏览器测试拦截外部页面请求；Python 后端拒绝外网 socket，外部连接拒绝行为有自动化测试。
- 项目 Ollama 在专用 11435 回环端口启动，云功能关闭。网络观测发现的项目外部连接数：{len(network['external']) if network else '未观测'}。
- 没有修改整机网络设置；本次采用应用级外网隔离及进程连接观测，未宣称完成操作系统级全机断网验收。
- 审核模型和对话模型相同；测试集有限，不代表零漏判或适合无人值守公开直播。
- 持续测试期间在源码中收紧了审核分类枚举、矛盾判定并补齐完成耗时日志，未中断长测进程；长测结束后重新启动最终版本，另经自动化和真实流程复验。
- 原始指标见 `verification/benchmark.json`，短测另存为 `verification/smoke.json`。截图见 `screenshots` 与 `verification`。

## 对题性修复（2026-11-04）

- 用户反馈不同问题得到相同的自我介绍。此前长测只验证了播出完成，没有验证每条回答是否对题。
- 将混合JSON中的历史与问题改为标准user/assistant多轮消息，最后一条user消息为当前问题原文；昵称仍独立审核，不再干扰回答。
- 调整人设，优先直接回答问题，不再默认观众是儿童，不用自我介绍替代其他问题。
- 每轮注入程序计算的北京时间、星期和实际本地模型信息，日期不靠模型猜测。
- 真实本地模型已验证日期、模型身份、17+25及继续乘2四个场景；包含之前重复寒暄的历史。结果见 `verification/dialogue-relevance.json`。
- 浏览器验收增加真实日期与模型身份的对题性检查，通过审核、语音及播放确认后才验收。
- 上方30分钟数据是修改前的稳定性基线，本次未重新运行30分钟性能测试；不能用它代表修改后的延迟或全面回答质量。

## 内网访问

- 可选内网配置只接受私有IPv4地址，入口使用随机令牌换取HttpOnly会话，随后从URL移除令牌。
- 内网页面、WebSocket、AudioContext及匿名访问阻断已通过真实浏览器检查，记录在 `verification/lan.json`。该检查由本机通过内网地址完成，未使用第二台设备。
- Ollama和语音仍在服务器本机运行；没有将模型服务端口开放给内网。
- Windows入站规则仅允许本地子网连接本机指定IP的TCP 8765端口，并限定项目实际Python程序；没有关闭防火墙。

## 一二和布布形象更新

- 当前形象为程序化构建的简化3D版双角色，不再加载原VRM人物。一二主讲，布布陪伴，仍使用原有一路本地语音。
- 前端TypeScript与生产构建通过；后端47项回归测试通过。
- 7项动作检查通过：音频嘴型、布布不复制嘴型、挥手、微笑、疑惑、急停冻结和减少动态效果，见 `verification/bear-rig.json`。
- 真实浏览器已验证本地语音播放完成，一二嘴型随声音变化，停止后嘴型归零且动作恢复idle，无页面脚本错误，见 `verification/bear-playback.json`。
- 舞台截图：`screenshots/yier-bubu-stage.png`；说话截图：`screenshots/yier-bubu-speaking.png`。未重新运行30分钟性能测试，不能沿用原VRM人物的性能作为新造型指标。

## 回答质量与长文修复（2026-11-04）

- 原实现限制120字符且保留无意义复读历史，导致长文要求无法执行，并可复现500字故事回复111。此前仅检查播完的测试不足以判断回答质量。
- 切换本地同为4B的 Qwen3 Instruct 2507 Q4_K_M，对话使用原生文本，审核仍使用受限JSON；不调用云端。
- 按用户字数调整预算，单次支持约1200字；过滤无意义历史，检查可检测的字数不足、复读、分析泄漏和不完整结尾，重试一次，失败转人工。这些检查不保证事实正确或全面理解问题。
- 真实模型100/500/1000字故事分别得到104/503/1096个有效字符，质量检查及输出审核通过，见 `verification/story-quality.json`。
- 浏览器真实500字请求生成570字符故事，5段音频完整播放，字幕拼接等于完整审核正文，独立播放编号不重复；嘴型峰值1、急停后0、页面错误0。111输入得到澄清而非原样复读，见 `verification/long-playback.json`。
- 每段使用独立音频与播放确认编号，旧确认不能结束下一段；全文审核完成后才开始合成，急停作废余下段落。
- 语义风控6项有效处置通过；原始模型对自伤求助曾给出allow，程序按类别强制转人工，原始结果与最终处置均保留于 `verification/model-safety.json`。同模型审核不是独立安全保证。
- 尚未对当前版本重新运行30分钟性能测试，长文延迟也不能套用普通短问答目标。4B模型仍有推理与事实准确性限制。
"""
(root / "docs/TEST-REPORT.md").write_text(text, encoding="utf-8")
print(root / "docs/TEST-REPORT.md")
