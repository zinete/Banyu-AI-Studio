# 素材与模型来源

## 当前形象：一二和布布

- 当前页面使用 `frontend/src/bears.ts` 中程序化构建的3D演示形象，不使用下载的官方3D模型或表情包图片。
- 一二：白色主体、深色圆耳、粉色腮红；布布：棕色主体、圆耳、暖黄色腮红。圆头、豆豆眼、小嘴与短四肢参照角色的公开插画特征重建。
- 角色/IP参考：https://www.chinalicensingexpo.com/cn/product/1962 。造型观察参考：https://www.duitang.com/blog/?id=1374639043 。参考图片仅用于本地观察，没有打包进页面。
- 几何和动画代码为本项目实现；角色设定与IP归原权利人，代码实现不等于取得角色的独占或商业授权。
- 一二随当前本地Kokoro语音动嘴，布布为陪伴角色，未新增第二路语音或声音克隆。
- 无需在运行时下载图片、模型或远程纹理；支持待机、点头、挥手、微笑、疑惑，急停时关闭嘴型和动作。

## 先前的 VRM 人物（保留文件，当前未启用）

- 名称：VRM1_Constraint_Twist_Sample，v1.0.1。
- 作者与版权：pixiv Inc.，© 2022 pixiv Inc.
- 来源：https://github.com/pixiv/three-vrm/tree/dev/packages/three-vrm/examples/models
- 模型内嵌许可：https://vrm.dev/licenses/1.0/
- 内嵌字段：`avatarPermission=everyone`、`commercialUsage=corporation`、`modification=allowModificationRedistribution`、`allowRedistribution=true`、`creditNotation=unnecessary`。
- 禁止反社会或仇恨使用；其余完整字段和文件 SHA-256 见 `avatar-license.json`。不能将模型解释为本站原创人物或独占 IP。
- 使用位置：角色预览和独立展示页；运行程序控制姿态和标准表情。

## 对话与语音

- 当前模型：Qwen3 4B Instruct 2507，Q4_K_M，Ollama 官方 `qwen3:4b-instruct-2507-q4_K_M`，Apache-2.0；官方清单见 `qwen-4b-instruct-2507-q4_K_M-manifest.json`，下载后校验官方 SHA256 摘要。此前 `qwen3:4b` 及 `qwen-manifest.json` 保留用于初版基线复现。
- Kokoro-82M v1.0，Apache-2.0，预置声音 `zf_xiaobei`；模型卡：https://huggingface.co/hexgrad/Kokoro-82M ，下载模型卡保存在 `models/kokoro/README.md`。不使用用户或公众人物的克隆声音。
- Kokoro 软件：https://github.com/hexgrad/kokoro ，Misaki：https://github.com/hexgrad/misaki 。它们的许可证与模型许可需分别保留。

## 渲染、字体与其他依赖

- Three.js 与 three-vrm 为 MIT；渲染器授权不替代人物模型授权。
- Inter 字体通过 `@fontsource/inter` 本地打包，SIL Open Font License 1.1；中文使用系统字体。
- React、Vite、FastAPI、Ollama 等依赖分别保留发行包内的许可证。npm 锁文件与 Python 环境记录可用于核对版本。
- 本项目没有外部照片、生成图片、在线字体或远程视频素材。
