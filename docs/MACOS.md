# macOS（Apple Silicon）

支持入口面向 M 系列芯片、macOS 14 Sonoma 及以上，使用原生 arm64 Python 3.12、Node.js 22+ 和原生 Ollama。当前未支持 Intel / Rosetta 运行完整语音链路：现有 PyTorch 2.9.1 依赖没有 Intel Mac 发行包。不要复制 Windows 虚拟环境或便携 Ollama 到 Mac。

## 安装

先安装 [Ollama macOS 版本](https://ollama.com/download/mac)，放入 Applications。安装 Python、Node 和语音系统库（已安装 Homebrew 时）：

```bash
brew install python@3.12 node libsndfile espeak-ng
git clone https://github.com/zinete/Banyu-AI-Studio.git
cd Banyu-AI-Studio
python3.12 -c 'import platform; print(platform.machine())'
bash Setup-macOS.sh
```

架构检查应输出 `arm64`。若为 `x86_64`，请使用原生终端和 arm64 Python，关闭终端的 Rosetta 模式。无需 CUDA 或 NVIDIA 驱动。安装器只创建项目 `.venv-macos`，下载 Kokoro 及 Qwen3 模型，构建前端并进行一次实际中文语音合成。首次安装需要网络和数 GB 下载空间，不会下载 Windows Ollama 压缩包。

## 启动与停止

```bash
bash Start-Studio-macOS.sh
# 不自动打开浏览器：
bash Start-Studio-macOS.sh --no-browser
```

访问 http://127.0.0.1:8765 ，点击「启用声音与角色」，再点「恢复回答」。保持终端打开，Ctrl+C 停止本次启动的服务；不会终止单独运行的 Ollama.app 或系统默认 11434 服务。日志在 `.runtime/api-macos.log` 和 `.runtime/ollama-macos.log`，不含默认关闭的对话原文调试记录。

项目模型目录为 `models/ollama`，项目 Ollama 使用独立本机端口 11435；与 Ollama.app 默认模型目录相互独立。安装器结束时会关闭自己启动的 Ollama 服务，启动器重新启动它。启动只使用本地模型，不自动下载缺失模型；缺失时需重新运行安装脚本。

Ollama 可使用 Apple Metal 加速；实际卸载到 GPU 的情况以 Ollama 日志为准。Kokoro 固定使用 CPU，3D 画面由浏览器渲染，输入审核、输出审核、人工接管与急停保持一致。安装完成后可断网手动验收对话。机器首次合成会比预热后慢，不保证所有 Mac 达到原性能目标。

## 内网与浏览器检查

默认只监听本机。可复用 README 的 `.runtime/lan.json` 格式，但 `host` 必须更换为此 Mac 的内网 IPv4；不要直接复制 Windows 的旧地址。启动时打印令牌入口。macOS 防火墙若提示允许 Python 接收入站连接，按实际内网访问需求设置；项目不会修改系统防火墙。

建议先用 Chrome 验收。浏览器音频播放仍需要手动点击启用；移动设备的内网 Web Audio 测试需在实际设备另行验证。

安装 Google Chrome 后，在项目根目录运行：

```bash
.venv-macos/bin/python -m pytest tests -q
node --test scripts/browser-runtime.test.mjs
node scripts/browser-check.mjs
.venv-macos/bin/python scripts/check_dialogue.py
node scripts/check_long_playback.mjs
```

自动定位 `/Applications/Google Chrome.app` 或用户 Applications 目录，可用 `CHROME_PATH` 指定其他 Chrome 可执行路径。真实播出检查需要先启动服务，会接管展示页并在结束时急停。长测会覆盖 `docs/verification/benchmark.json` 等本地报告，请保留需要的旧结果。Mac 没有 NVIDIA 显存指标，报告明确记为不可用，不能把统一内存等同于独立显存。

## 验证范围

macOS 入口已加入平台、离线环境、子进程回收、内网配置和浏览器路径测试；现阶段开发机器为 Windows，尚无 M 系列 Mac 上首次安装、Metal 推理、中文发声、断网运行或30分钟性能实测。Windows 历史报告不代表 Mac 验收结果。

官方平台依据：[Ollama 系统要求](https://github.com/ollama/ollama/blob/main/docs/macos.mdx)、[PyTorch 对 Intel Mac 的支持范围](https://pytorch.org/blog/pytorch2-2/)。
