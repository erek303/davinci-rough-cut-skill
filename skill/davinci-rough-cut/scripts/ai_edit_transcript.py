#!/usr/bin/env python3
"""
AI-powered transcript editor for rough cut workflow.
Processes each sentence with project context, decides keep/delete.
Outputs per-sentence decisions with reasons.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys
import time
from datetime import timedelta
from pathlib import Path


def _preferred_backend_order() -> list[str]:
    preferred = os.environ.get("AI_EDIT_BACKEND", "").strip().lower()
    order = ["glm", "deepseek", "mimo", "anthropic"]
    aliases = {
        "xiaomi": "mimo",
        "claude": "anthropic",
    }
    preferred = aliases.get(preferred, preferred)
    if preferred and preferred in order:
        return [preferred] + [backend for backend in order if backend != preferred]
    return order


def _extract_openai_content(resp) -> str:
    message = resp.choices[0].message
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if text:
                    parts.append(text)
            elif hasattr(item, "text"):
                parts.append(item.text)
        return "\n".join(parts)
    return str(content)


def _call_openai_compatible(
    *,
    prompt: str,
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int = 8192,
    default_headers: dict | None = None,
) -> str:
    from openai import OpenAI

    kwargs = {"api_key": api_key, "base_url": base_url}
    if default_headers:
        kwargs["default_headers"] = default_headers
    client = OpenAI(**kwargs)
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return _extract_openai_content(resp)


def format_time(seconds: float) -> str:
    return str(timedelta(seconds=int(seconds))).zfill(8)


def call_llm(prompt: str, model: str | None = None) -> str:
    errors = []

    for backend in _preferred_backend_order():
        if backend == "glm" and os.environ.get("GLM_API_KEY"):
            try:
                import anthropic
                client = anthropic.Anthropic(
                    api_key=os.environ["GLM_API_KEY"],
                    base_url=os.environ.get("GLM_BASE_URL", "https://open.bigmodel.cn/api/anthropic"),
                )
                resp = client.messages.create(
                    model=model or os.environ.get("GLM_MODEL", "glm-4.7"),
                    max_tokens=8192,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text
            except Exception as e:
                errors.append(f"GLM error: {e}")

        if backend == "deepseek" and os.environ.get("DEEPSEEK_API_KEY"):
            try:
                return _call_openai_compatible(
                    prompt=prompt,
                    api_key=os.environ["DEEPSEEK_API_KEY"],
                    base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
                    model=model or os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
                )
            except Exception as e:
                errors.append(f"DeepSeek error: {e}")

        mimo_key = os.environ.get("MIMO_API_KEY") or os.environ.get("XIAOMI_API_KEY")
        if backend == "mimo" and mimo_key:
            try:
                return _call_openai_compatible(
                    prompt=prompt,
                    api_key=mimo_key,
                    base_url=os.environ.get("MIMO_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1"),
                    model=model or os.environ.get("MIMO_MODEL", "mimo-v2.5-pro"),
                    default_headers={"api-key": mimo_key},
                )
            except Exception as e:
                errors.append(f"MiMo error: {e}")

        if backend == "anthropic" and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                client = anthropic.Anthropic()
                resp = client.messages.create(
                    model=model or os.environ.get("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
                    max_tokens=8192,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text
            except Exception as e:
                errors.append(f"Anthropic error: {e}")

    raise RuntimeError(
        "No LLM backend available. Set one of GLM_API_KEY, DEEPSEEK_API_KEY, "
        "MIMO_API_KEY/XIAOMI_API_KEY, or ANTHROPIC_API_KEY.\n" + "\n".join(errors)
    )


def load_context(context_arg: str | None) -> str:
    """Load project context from file path or inline text."""
    if not context_arg:
        return ""
    if os.path.isfile(context_arg):
        with open(context_arg, "r", encoding="utf-8") as f:
            return f.read().strip()
    return context_arg.strip()


def group_segments_into_clips(segments: list, gap_threshold: float = 3.0) -> list:
    """Group ASR segments into clips based on silence gaps."""
    if not segments:
        return []

    clips = []
    current = {"id": 0, "segments": [segments[0]]}

    for i in range(1, len(segments)):
        gap = segments[i]["start"] - segments[i-1]["end"]
        if gap >= gap_threshold:
            clips.append(current)
            current = {"id": len(clips), "segments": [segments[i]]}
        else:
            current["segments"].append(segments[i])

    clips.append(current)
    return clips


def edit_clip_with_ai(clip: dict, context: str, model: str | None) -> list:
    """Send one clip to LLM for per-sentence keep/delete decisions."""

    # Format clip text with indexed sentences
    lines = []
    for i, seg in enumerate(clip["segments"]):
        speaker = seg.get("speaker", "unknown")
        start = format_time(seg["start"])
        end = format_time(seg["end"])
        lines.append(f"[{i}] [{start}-{end}] {speaker}: {seg['text']}")

    clip_text = "\n".join(lines)

    context_block = ""
    if context:
        context_block = f"""
## 项目背景
这是以下视频项目的拍摄素材，请根据项目主题判断每一句话的价值：

{context}
"""

    prompt = f"""你是一位资深视频剪辑师，正在对一段长视频、多素材口播或对话类素材做粗剪筛选。
{context_block}

## 你的工作方法（两步走）

### 第一步：理解叙事整体
先通读全部内容，判断这段素材的叙事结构：
- 这段在讲什么故事/什么观点？
- 叙事主线是什么？有哪些关键转折点？
- 哪些内容是叙事骨架（主线推进、核心观点、关键转折），哪些是血肉（补充细节、案例、情感），哪些是噪音（完全无关、重复、空洞应答）？

### 第二步：基于叙事判断每一句
有了整体理解后，再逐句判断保留或删除。判断的优先级：

1. **叙事价值**（最重要）：这句话是否推进了主线？是否在关键叙事节点上？是否提供了不可替代的信息？
2. **内容密度**：这句话传递了多少有效信息？是干货还是水话？
3. **语流自然度**（次要）：如果删掉这句话，上下文是否还能自然衔接？

## 判断标准
- **保留**：叙事推进、核心观点、关键细节/案例、情感高点、过渡衔接句、有价值的具体描述
- **删除**：完全跑题、空洞应答（"嗯""啊""对对对"）、大段重复同一观点、明显废话

## 注意
- 口癖词（"然后""就是""那个"等）不需要单独删除，它们是语流的一部分
- 不要过度扣字眼——一段话即使表达不够精炼，只要在叙事上有价值就保留
- 宁可多保留也不要误删有价值的内容
- reason 要从叙事角度说明（"推进了XX主线"/"补充了XX背景"），而不是抠字眼（"有口头禅"/"表达不够简洁"）

## 输出格式
只返回 JSON 数组，每个元素对应一句话的决策：

[
  {{"id": 0, "action": "keep", "reason": "引出核心话题，叙事起点"}},
  {{"id": 1, "action": "delete", "reason": "纯应答，不承载叙事功能"}},
  ...
]

不要输出任何其他内容。

## 片段内容
{clip_text}
"""

    response = call_llm(prompt, model)

    # Parse JSON
    json_match = re.search(r"\[.*\]", response, re.DOTALL)
    if json_match:
        try:
            decisions = json.loads(json_match.group(0))
            return decisions
        except json.JSONDecodeError:
            pass

    # Fallback: try to extract individual actions
    decisions = []
    for line in response.split("\n"):
        match = re.search(r'"id"\s*:\s*(\d+).*?"action"\s*:\s*"(keep|delete)"', line)
        if match:
            decisions.append({"id": int(match.group(1)), "action": match.group(2)})

    return decisions


def write_progress(path: str, data: dict):
    """Write progress state to JSON for UI monitoring."""
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def process_transcript(transcript_path: str, output_path: str,
                       context: str | None, model: str | None,
                       gap_threshold: float = 3.0):
    """Main processing: load transcript → group into clips → AI edit → output."""

    progress_path = str(Path(output_path).parent / "progress.json")
    start_time = time.time()

    with open(transcript_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Support both formats: raw list or dict with 'segments' key
    segments = data["segments"] if isinstance(data, dict) and "segments" in data else data
    audio_duration = data.get("duration", 0) if isinstance(data, dict) else 0

    project_context = load_context(context)

    # Group into clips
    clips = group_segments_into_clips(segments, gap_threshold)
    print(f"转录文本共 {len(segments)} 句，分为 {len(clips)} 个片段")

    total_keep = 0
    total_delete = 0

    for clip in clips:
        seg_count = len(clip["segments"])
        print(f"  处理片段 {clip['id']+1}/{len(clips)}（{seg_count} 句）...", end=" ", flush=True)

        elapsed = int(time.time() - start_time)
        estimated = int(len(clips) * 5 + 120)
        percent = min(99, int((clip['id'] + 1) / len(clips) * 100))
        write_progress(progress_path, {
            "status": "processing",
            "stage": "ai_editing",
            "filename": Path(transcript_path).with_suffix('.mp3').name,
            "audio_duration": audio_duration,
            "elapsed_seconds": elapsed,
            "estimated_total_seconds": estimated,
            "percent": percent,
            "current_clip": clip['id'] + 1,
            "total_clips": len(clips),
            "updated_at": datetime.datetime.now().isoformat(),
        })

        decisions = edit_clip_with_ai(clip, project_context, model)

        # Map decisions to segments
        decision_map = {d["id"]: d for d in decisions}

        for i, seg in enumerate(clip["segments"]):
            d = decision_map.get(i, {"action": "keep", "reason": "未判定"})
            seg["ai_action"] = d.get("action", "keep")
            seg["ai_reason"] = d.get("reason", "")
            if seg["ai_action"] == "keep":
                total_keep += 1
            else:
                total_delete += 1

        kept = sum(1 for s in clip["segments"] if s.get("ai_action") == "keep")
        print(f"保留 {kept}/{seg_count}")

    # Save
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)

    write_progress(progress_path, {
        "status": "completed",
        "stage": "done",
        "filename": Path(transcript_path).with_suffix('.mp3').name,
        "audio_duration": audio_duration,
        "elapsed_seconds": int(time.time() - start_time),
        "estimated_total_seconds": int(time.time() - start_time),
        "percent": 100,
        "output_file": output_path,
        "updated_at": datetime.datetime.now().isoformat(),
    })

    print(f"\n完成！保留 {total_keep} 句，删除 {total_delete} 句")
    print(f"已保存到 {output_path}")


def main():
    parser = argparse.ArgumentParser(description="AI transcript editor for rough cut")
    parser.add_argument("transcript", help="转录 JSON 文件路径")
    parser.add_argument("-o", "--output", default="edited_transcript.json", help="输出路径")
    parser.add_argument("--context", default=None,
                        help="项目背景：文件路径或文字描述（选题/主题/受众）")
    parser.add_argument("--model", default=None, help="LLM 模型名")
    parser.add_argument("--gap", type=float, default=3.0,
                        help="片段分组间隔阈值（秒），默认 3.0")
    args = parser.parse_args()

    process_transcript(args.transcript, args.output, args.context, args.model, args.gap)


if __name__ == "__main__":
    main()
