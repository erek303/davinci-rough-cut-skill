# DaVinci Rough Cut Skill 中文说明

DaVinci Rough Cut 是一个给本地 Agent 使用的达芬奇粗剪 skill。它帮助剪辑师把长视频、多素材口播、播客、纪录片素材或其他以声音内容为主的素材，先做成可审核、可导入 DaVinci Resolve 的粗剪时间线。

它不替你做最终精剪。它做的是粗剪前最耗时间的两件事：

1. 把长素材的语音转成带时间码的文字，让 AI 先给出保留 / 删除建议，再让人通过浏览器面板确认，最后导出达芬奇粗剪时间线。
2. 把一堆零散相机视频片段，精确匹配到一条连续录制的独立 WAV 音频上，生成达芬奇同步时间线。

## 两个核心能力

### 1. 文稿辅助粗剪

输入：

- 从达芬奇原始时间线导出的音频：`audio.wav` / `audio.mp3`
- 从同一条达芬奇时间线导出的参考 XML：`reference.xml`
- 可选：项目背景、保留标准、目标时长等 `context.md`

流程：

1. 火山引擎 ASR 极速版识别语音，生成 `transcript.json`。
2. 大模型判断每句话建议保留还是删除，生成 `edited.json`。
3. 打开本地 Web 审核面板，看原稿、看 AI 保留稿、手动切换留 / 删。
4. 从面板导出达芬奇可导入的粗剪时间线 XML。

![文稿辅助粗剪：长音频和原始时间线进入粗剪裁切机，经过 AI 建议与人工留删后导出达芬奇粗剪时间线](docs/assets/01-transcript-rough-cut.png)

### 2. 音视频精确匹配

输入：

- 相机 MP4 文件夹：视频自带相机同期声
- 独立录音 WAV 文件夹：通常是一条或几条从头录到尾的麦克风音频
- `matches.csv`：每个 MP4 在 WAV 时间线上的匹配位置
- `timecodes.csv`：每个 MP4 的源时间码

流程：

1. 先生成少量片段的 `sample XML`。
2. 导入达芬奇确认素材链接和同步都正确。
3. 再生成完整的 `full XML` 同步时间线。

这条路径不需要 ASR，也不需要大模型。它解决的是“碎片视频素材和独立录音如何对齐”的问题。

![音视频对齐：视频碎片按相机同期声匹配到独立 WAV，先生成 sample 时间线验证，再导出 full 同步时间线](docs/assets/02-audio-video-alignment.png)

## 首次安装

如果你还没有安装这个 skill，把下面这段发给 Codex、Claude Code、NewMax 或其他能操作本机终端的 Agent：

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

如果你自己在终端安装：

```bash
git clone https://github.com/erek303/davinci-rough-cut-skill.git
cd davinci-rough-cut-skill
bash install.sh --target auto
```

`install.sh` 会打印最终安装路径。进入那个安装目录后创建 venv：

```bash
cd /path/printed/by/install.sh/davinci-rough-cut
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements-core.txt
```

安装只需要做一次。安装完成后，日常只需要使用和更新指令，不需要再走首次安装流程。

## 已安装后的指令

把这些指令发给已经安装了本 skill 的 Agent：

```text
/davinci-rough-cut
```

总入口。Agent 根据你给的文件和目标，判断走文稿辅助粗剪还是音视频对齐。

```text
/davinci-rough-cut rough-cut
```

明确走文稿辅助粗剪：达芬奇音频 + 参考 XML → ASR → AI 留删建议 → Web 审核面板 → 达芬奇粗剪时间线。

```text
/davinci-rough-cut align
```

明确走音视频对齐：`matches.csv` + `timecodes.csv` + 相机 MP4 + 独立 WAV → 先 sample XML → 达芬奇验证后再 full XML。

```text
/davinci-rough-cut update
```

更新已安装的 skill。安装过一次后，后续更新不需要重新复制仓库地址。

如果终端里已经有稳定更新命令，也可以直接运行：

```bash
davinci-rough-cut-update
```

## Key 怎么配置

配置分两类：一类是 ASR，用来把音频转成文字；另一类是大模型，用来判断哪些内容值得保留。

### A. ASR：火山引擎语音识别

默认推荐用火山引擎“录音文件识别极速版 / 大模型录音文件极速版识别 API”。这条路径用本地音频直传，不需要先开 TOS 对象存储，也不需要创建私有 bucket。

最低需要：

```bash
export VOLCENGINE_API_KEY="your-volcengine-api-key"
```

旧版控制台如果给的是 App ID + Access Token，可以改用：

```bash
export VOLCENGINE_APP_ID="your-volcengine-app-id"
export VOLCENGINE_ACCESS_TOKEN="your-volcengine-access-token"
```

火山引擎开通路径建议：

1. 登录火山引擎控制台。
2. 开通语音技术里的录音文件识别极速版 / 大模型录音文件识别能力。
3. 创建或复制 ASR API Key。
4. 在本机终端设置 `VOLCENGINE_API_KEY`。
5. 先用 1-2 分钟音频测试，再跑完整素材。

只有在你明确要走旧的 URL / TOS 模式时，才需要额外配置：

```bash
export VOLCENGINE_ASR_MODE="standard-url"
export VOLCENGINE_ACCESS_KEY="your-volcengine-iam-access-key"
export VOLCENGINE_SECRET_KEY="your-volcengine-iam-secret-key"
export VOLCENGINE_TOS_BUCKET="your-tos-bucket"
export VOLCENGINE_TOS_REGION="cn-shanghai"
```

普通用户不用先看这一段高级配置。

### B. 大模型：内容留删判断

下面任选一个即可：

```bash
export GLM_API_KEY="your-glm-api-key"
export DEEPSEEK_API_KEY="your-deepseek-api-key"
export MIMO_API_KEY="your-xiaomi-mimo-api-key"
# 或 export XIAOMI_API_KEY="your-xiaomi-mimo-api-key"
export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

可选指定优先使用哪个模型后端：

```bash
export AI_EDIT_BACKEND="deepseek"  # glm / deepseek / mimo / anthropic
```

常用模型配置：

```bash
export DEEPSEEK_MODEL="deepseek-v4-flash"
export MIMO_BASE_URL="https://token-plan-cn.xiaomimimo.com/v1"
export MIMO_MODEL="mimo-v2.5-pro"
```

小米 MiMo 的 `mimo-v2.5-asr` 可以作为短音频转录测试入口，但不建议作为长素材主路径。长素材粗剪仍建议用火山 ASR 极速版。

## 文稿辅助粗剪输入要求

不能只给一个视频素材目录。必须先从达芬奇导出两样东西：

- `audio.wav` 或 `audio.mp3`：从原始达芬奇时间线导出的音频
- `reference.xml`：从同一条时间线导出的 `FCP 7 XML`

原因是：ASR 只能知道“第几秒说了什么”，但不知道“这一秒来自哪个原始视频文件”。`reference.xml` 提供 clip 边界和源素材映射，最终导出的粗剪时间线才能正确引用原始素材。

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

## 审核面板是硬规则

文稿辅助粗剪里，浏览器审核面板不是附加功能，而是核心流程。

ASR 转录和 AI 留删判断完成后，Agent 必须启动 `web_editor.py`，给用户本地地址，通常是：

```text
http://localhost:5001
```

用户需要在这个面板里看原稿、看 AI 保留稿、播放音频、手动切换保留 / 删除，然后再导出达芬奇 XML。

除非用户明确说“跳过人工审核，直接生成 XML”，否则 Agent 不要从 `transcript.json` / `edited.json` 直接跳到 `rough_cut.xml`。如果面板启动失败，要把实际命令和错误报出来，不要静默生成 XML。

## 手动运行示例

```bash
SKILL="${DAVINCI_ROUGH_CUT_SKILL_DIR:-/path/to/installed/davinci-rough-cut}"
PY="$SKILL/.venv/bin/python"

"$PY" "$SKILL/scripts/volcengine_asr.py" \
  /path/to/my-project/audio.wav \
  -o /path/to/my-project/work/transcript.json

"$PY" "$SKILL/scripts/ai_edit_transcript.py" \
  /path/to/my-project/work/transcript.json \
  -o /path/to/my-project/work/edited.json \
  --context /path/to/my-project/context.md

"$PY" "$SKILL/scripts/web_editor.py" \
  --transcript /path/to/my-project/work/transcript.json \
  --edited /path/to/my-project/work/edited.json \
  --audio /path/to/my-project/audio.wav \
  --davinci-ref /path/to/my-project/reference.xml \
  --fps 50 \
  --port 5001
```

打开 `http://localhost:5001`，审核保留 / 删除结果，然后从面板导出 DaVinci XML。

## 安全说明

公开仓库不包含任何真实 key、已开通账号、本地素材、转录中间文件或私有项目文件。真实 key 请只放在你自己的本机环境变量、shell profile、系统密钥管理器或未提交的 `.env` 里，不要粘贴到聊天窗口，也不要提交到 GitHub。

仓库里有 `.env.example`，它只放占位符。你可以复制成本地 `.env` 参考：

```bash
cp .env.example .env
```

脚本不会自动读取 `.env`。如果你只想在当前终端临时加载：

```bash
set -a
source .env
set +a
```

## 更多文档

- [中文快速上手](docs/quickstart.zh.md)
- [完整用户手册](docs/user-manual.md)
- [示例剪辑上下文](examples/context.example.md)
