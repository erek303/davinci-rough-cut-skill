# DaVinci Rough Cut 中文快速上手

这个 skill 用来把长视频、多素材口播、播客、纪录片素材或其他以声音内容为主的素材，先做成一个可进达芬奇的粗剪时间线。它不会生成新声音，也不会替你做最终精剪；它做的是：识别原素材里的语音文字，让 AI 建议保留 / 删除，让你在浏览器面板里审核，最后导出达芬奇可导入的 XML。

## 1. 先准备什么

共同需要：

- DaVinci Resolve
- Python 3.10+
- FFmpeg / ffprobe

文稿辅助粗剪需要：

- 从达芬奇原始时间线导出的 `audio.wav` / `audio.mp3`
- 从同一条时间线导出的 `reference.xml`
- 火山引擎 ASR key：`VOLCENGINE_API_KEY`
- 任意一个大模型 key：GLM、DeepSeek、小米 MiMo、Anthropic 四选一

音视频对齐需要：

- 相机 MP4 目录
- 独立录音 WAV 目录
- `matches.csv`
- `timecodes.csv`

音视频对齐不需要 ASR，也不需要大模型。

## 2. 首次安装

还没安装时，把这段发给能操作本机终端的 Agent：

```text
请从这个仓库安装 DaVinci Rough Cut skill：
https://github.com/erek303/davinci-rough-cut-skill

要求：
1. git clone 仓库。
2. 把 skill 安装到你这个 Agent 自己实际会读取的 skill 目录，不要默认使用 Codex 路径。
3. 如果你能确定自己的 skill root，就运行：bash install.sh --target "<你的 Agent skill root>"
4. 如果你不能确定自己的 skill root，就运行：bash install.sh --target auto
5. 在安装脚本打印出来的 davinci-rough-cut 目录里创建 Python venv。
6. 用这个 venv 安装 requirements-core.txt。
7. 检查 ffmpeg 和 ffprobe 是否可用。
8. 不要读取、打印、提交、上传真实 API key，也不要让我把真实 key 粘贴到聊天里。
9. 安装后告诉我最终安装路径、当前 commit，以及还缺哪些 ASR / LLM 环境变量。
```

手动安装：

```bash
git clone https://github.com/erek303/davinci-rough-cut-skill.git
cd davinci-rough-cut-skill
bash install.sh --target auto
cd /安装脚本打印出来的路径/davinci-rough-cut
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements-core.txt
```

安装只做一次。已经安装后，不需要再走首次安装流程。

## 3. 已安装后的常用指令

```text
/davinci-rough-cut
```

总入口，让 Agent 自己判断走哪条流程。

```text
/davinci-rough-cut rough-cut
```

文稿辅助粗剪：音频 + 参考 XML → ASR → AI 判断 → Web 审核面板 → 达芬奇粗剪时间线。

```text
/davinci-rough-cut align
```

音视频对齐：相机 MP4 + 外录 WAV + 匹配 CSV + timecode CSV → sample XML → full XML。

```text
/davinci-rough-cut update
```

更新已安装的 skill。安装过一次后，更新不需要重新复制仓库地址。

如果终端里有稳定更新命令，也可以运行：

```bash
davinci-rough-cut-update
```

## 4. 配置 Key

### ASR：火山引擎

默认推荐火山引擎录音文件识别极速版。它直接上传本地音频数据，不需要创建 TOS 私有 bucket。

```bash
export VOLCENGINE_API_KEY="your-volcengine-api-key"
```

旧版控制台如果给的是 App ID + Access Token：

```bash
export VOLCENGINE_APP_ID="your-volcengine-app-id"
export VOLCENGINE_ACCESS_TOKEN="your-volcengine-access-token"
```

只有明确走旧 URL/TOS 模式时才需要：

```bash
export VOLCENGINE_ASR_MODE="standard-url"
export VOLCENGINE_ACCESS_KEY="your-volcengine-iam-access-key"
export VOLCENGINE_SECRET_KEY="your-volcengine-iam-secret-key"
export VOLCENGINE_TOS_BUCKET="your-tos-bucket"
export VOLCENGINE_TOS_REGION="cn-shanghai"
```

### 大模型：留删判断

任选一个：

```bash
export GLM_API_KEY="your-glm-api-key"
export DEEPSEEK_API_KEY="your-deepseek-api-key"
export MIMO_API_KEY="your-xiaomi-mimo-api-key"
# 或 export XIAOMI_API_KEY="your-xiaomi-mimo-api-key"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

可选指定后端：

```bash
export AI_EDIT_BACKEND="deepseek"  # glm / deepseek / mimo / anthropic
```

## 5. 文稿辅助粗剪

不能只给一个视频素材目录。必须先从达芬奇导出：

- `audio.wav` 或 `audio.mp3`
- `reference.xml`

给 Agent 的标准说法：

```text
/davinci-rough-cut rough-cut

帮我做文稿辅助粗剪。
音频: /path/to/my-project/audio.wav
达芬奇参考 XML: /path/to/my-project/reference.xml
项目背景: /path/to/my-project/context.md
工作目录: /path/to/my-project/work
帧率: 50
目标: 保留最有价值的内容，导出可导入达芬奇的粗剪时间线。
```

流程：

1. ASR 生成 `transcript.json`。
2. AI 生成 `edited.json`。
3. Agent 启动 `web_editor.py`。
4. 你打开 `http://localhost:5001` 审核留 / 删。
5. 从面板导出达芬奇 XML。

硬规则：除非你明确说“跳过人工审核，直接生成 XML”，否则没有打开 Web 审核面板，就不算完成文稿辅助粗剪。

## 6. 音视频对齐

如果你要做“碎片 MP4 + 独立 WAV”的精确匹配，需要准备：

- `matches.csv`：每个 MP4 在 WAV 时间线上的位置
- `timecodes.csv`：每个 MP4 的真实源 timecode
- 相机 MP4 目录
- 外录 WAV 目录

这条路线必须先生成 sample XML，导入达芬奇确认同步和素材链接都正常，再生成 full XML。
