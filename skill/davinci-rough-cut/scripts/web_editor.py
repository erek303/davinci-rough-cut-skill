#!/usr/bin/env python3
"""
粗剪工作台 Web 面板
左侧：原始文案 + AI 编辑标记（保留/删除）
右侧：优化后文案预览
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, request, render_template_string, send_file

app = Flask(__name__)

TRANSCRIPT_PATH = "transcription.json"
EDITED_PATH = "edited_transcript.json"
SELECTIONS_PATH = "selections.json"
AUDIO_PATH = None
MEDIA_PATH = ""
MEDIA_MANIFEST_PATH = None
PROJECT_CONTEXT = ""
DAVINCI_REF_PATH = ""
SCRIPT_DIR = Path(__file__).parent

HTML = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <title>粗剪工作台</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    /* 说话人颜色 */
    .spk0 { color: #1e40af; } .spk0bg { background: #dbeafe; }
    .spk1 { color: #166534; } .spk1bg { background: #dcfce7; }
    .spk2 { color: #9d174d; } .spk2bg { background: #fce7f3; }
    .spk3 { color: #92400e; } .spk3bg { background: #fef3c7; }
    /* 句子状态 */
    .s { cursor: pointer; border-radius: 2px; padding: 0 1px; transition: all 0.1s; }
    .s:hover { background: #e2e8f0 !important; }
    .s.keep { background: #dcfce780; }
    .s.del { background: #fecaca; text-decoration: line-through; color: #9ca3af; }
    .s.del:hover { background: #fde68a !important; text-decoration: none; color: #000; }
    .s.restored { background: #bfdbfe; border-bottom: 2px solid #3b82f6; }
    .s.playing { background: #fef3c7 !important; box-shadow: 0 0 0 1px #f59e0b; text-decoration: none !important; color: #000 !important; }
    /* 片段 */
    .clip { transition: all 0.15s ease; }
    .clip.del-all .clip-body { opacity: 0.7; }
    .clip.del-all .clip-body .s { text-decoration: line-through; color: #9ca3af; }
    /* 音频条 */
    #audioBar { transition: opacity 0.3s; }
    /* tooltip */
    .reason-tip { position: absolute; background: #1e293b; color: #fff; padding: 4px 8px; border-radius: 4px; font-size: 11px; z-index: 100; pointer-events: none; white-space: nowrap; display: none; }
    .s:hover .reason-tip { display: block; }
    /* 说话人段落标签 */
    .spk-block { margin-bottom: 4px; }
    .spk-block:last-child { margin-bottom: 0; }
    .spk-label { display: inline-block; font-size: 10px; font-weight: 700; padding: 0 4px; border-radius: 2px; margin-right: 2px; }
    /* 左右连线高亮 */
    .clip-linked { box-shadow: 0 0 0 2px #3b82f6 !important; transition: box-shadow 0.15s; }
    /* 右侧已删片段 */
    .clip-right-del { opacity: 0.5; }
    .clip-right-del .spk-block { text-decoration: line-through; color: #9ca3af; }
    .clip-right-del .clip-hdr-del { background: #fef2f2 !important; }
    /* AI 思路折叠 */
    .ai-thinking { background: #f0f9ff; border-left: 3px solid #3b82f6; padding: 6px 10px; font-size: 11px; color: #475569; margin: 0 0 4px 0; border-radius: 0 4px 4px 0; }
    .ai-thinking summary { cursor: pointer; font-weight: 600; color: #1e40af; font-size: 11px; }
    .ai-thinking ul { margin: 4px 0 0 14px; padding: 0; }
    .ai-thinking li { margin: 1px 0; }
  </style>
</head>
<body class="bg-gray-100 h-screen flex flex-col text-sm">

  <!-- 顶部栏 -->
  <header class="bg-slate-900 text-white px-5 py-2.5 flex items-center justify-between shrink-0">
    <div class="flex items-center gap-3">
      <h1 class="font-bold text-base">粗剪工作台</h1>
      <span id="contextBadge" class="hidden bg-slate-700 text-slate-300 text-xs px-2 py-0.5 rounded max-w-xs truncate"></span>
    </div>
    <div class="flex items-center gap-3">
      <span id="stats" class="text-slate-400 text-xs"></span>
      <button onclick="restoreAll()" class="text-xs bg-slate-700 hover:bg-slate-600 px-3 py-1 rounded">恢复全部</button>
      <input id="mediaPath" type="text" placeholder="素材路径（导出用）" class="px-2 py-1 rounded text-black w-48 text-xs" value="">
      <button onclick="confirmExport('fcpxml')" class="bg-emerald-600 hover:bg-emerald-700 px-3 py-1.5 rounded text-xs font-medium">导出 FCPXML</button>
      <button onclick="confirmExport('resolve')" class="bg-blue-600 hover:bg-blue-700 px-3 py-1.5 rounded text-xs font-medium">导出达芬奇 XML</button>
    </div>
  </header>

  <!-- 音频条 -->
  <div id="audioBar" class="bg-slate-800 px-5 py-1.5 flex items-center gap-3 shrink-0" style="opacity:0.4">
    <button onclick="togglePlay()" id="playBtn" class="text-white w-7 h-7 flex items-center justify-center rounded hover:bg-slate-700 text-base">&#9654;</button>
    <span id="curTime" class="text-slate-400 text-xs font-mono w-12">0:00</span>
    <div class="flex-1 h-1.5 bg-slate-700 rounded cursor-pointer" onclick="seekAudio(event)">
      <div id="progBar" class="h-full bg-emerald-500 rounded" style="width:0%"></div>
    </div>
    <span id="totTime" class="text-slate-400 text-xs font-mono w-12">0:00</span>
    <span class="text-slate-500 text-[11px]">左键播放 · 右键删除/恢复 · <span class="text-emerald-400">绿色=保留</span> · <span class="text-red-400">红色=已删</span></span>
  </div>

  <!-- 主体：左右两栏 -->
  <main class="flex-1 flex overflow-hidden">
    <!-- 左侧：原始文案 + AI标记 -->
    <section class="w-1/2 flex flex-col border-r bg-white">
      <div class="px-4 py-2 border-b bg-gray-50 flex justify-between items-center shrink-0">
        <div>
          <span class="font-semibold text-gray-700 text-xs">原始文案</span>
          <span class="text-gray-400 text-[11px] ml-2">绿色=AI建议保留 | 红色删除线=AI建议删除（点击可恢复）</span>
        </div>
        <span id="clipMeta" class="text-gray-400 text-[11px]"></span>
      </div>
      <div id="leftPanel" class="flex-1 overflow-y-auto px-5 py-3 space-y-4"></div>
    </section>

    <!-- 右侧：优化后文案 -->
    <section class="w-1/2 flex flex-col bg-white">
      <div class="px-4 py-2 border-b bg-gray-50 flex justify-between items-center shrink-0">
        <div>
          <span class="font-semibold text-gray-700 text-xs">优化后文案</span>
          <span class="text-gray-400 text-[11px] ml-2">最终导出的内容 · 灰色=已删片段（可右键恢复）</span>
        </div>
        <span id="rightMeta" class="text-gray-400 text-[11px]"></span>
      </div>
      <div id="rightPanel" class="flex-1 overflow-y-auto px-5 py-3 space-y-4"></div>
    </section>
  </main>

  <audio id="ap" preload="auto"></audio>
  <div id="toast" class="fixed bottom-4 right-4 bg-slate-800 text-white px-4 py-2 rounded shadow-lg hidden z-50 text-xs"></div>

  <script>
    // ---- State ----
    let segs = [];       // all segments with ai_action
    let clips = [];      // grouped clips
    let audioEl = document.getElementById('ap');
    let hasAudio = false;
    let playingKey = null;
    let saveTimer = null;

    // ---- Init ----
    async function init() {
      const res = await fetch('/api/data');
      const d = await res.json();
      segs = d.transcript || [];

      // If edited transcript has ai_action, use it; otherwise all "keep"
      segs.forEach((s, i) => {
        if (!s.ai_action) s.ai_action = 'keep';
        if (!s.ai_reason) s.ai_reason = '';
        // user override: undefined means follow AI
        if (s.user_action === undefined) s.user_action = null;
      });

      // Restore saved state from localStorage
      const saved = localStorage.getItem('roughcut_state');
      if (saved) {
        try {
          const st = JSON.parse(saved);
          st.forEach((ua, i) => { if (i < segs.length && ua !== null) segs[i].user_action = ua; });
        } catch(e) {}
      }

      groupClips();
      render();

      if (d.audio_url) { audioEl.src = d.audio_url; hasAudio = true; document.getElementById('audioBar').style.opacity = '1'; }
      if (d.context) { const b = document.getElementById('contextBadge'); b.textContent = d.context; b.classList.remove('hidden'); }
      if (d.media_path) document.getElementById('mediaPath').value = d.media_path;
    }

    // ---- Auto-save ----
    function scheduleSave() {
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        // Save to localStorage (instant restore on refresh)
        const st = segs.map(s => s.user_action);
        localStorage.setItem('roughcut_state', JSON.stringify(st));
        // Save to server (persist across sessions)
        fetch('/api/save_state', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(segs.map(s => ({user_action: s.user_action, ai_action: s.ai_action, ai_reason: s.ai_reason})))
        }).catch(() => {});
      }, 500);
    }

    // ---- Group clips ----
    function groupClips() {
      clips = [];
      if (!segs.length) return;
      let cur = { id: 0, segs: [], start: segs[0].start, end: 0 };
      clips.push(cur);
      for (let i = 0; i < segs.length; i++) {
        const s = segs[i];
        const gap = (i < segs.length - 1) ? segs[i+1].start - s.end : 999;
        cur.segs.push(i);
        cur.end = s.end;
        if (gap >= 3.0 && i < segs.length - 1) {
          cur = { id: clips.length, segs: [], start: segs[i+1].start, end: 0 };
          clips.push(cur);
        }
      }
    }

    // ---- Effective action ----
    function action(idx) {
      const s = segs[idx];
      if (s.user_action !== null) return s.user_action;
      return s.ai_action;
    }

    // ---- Audio ----
    audioEl.addEventListener('timeupdate', () => {
      const ct = audioEl.currentTime;
      document.getElementById('curTime').textContent = fmtShort(ct);
      if (audioEl.duration) document.getElementById('progBar').style.width = (ct/audioEl.duration*100)+'%';
      if (playingKey !== null) {
        const s = segs[playingKey];
        if (s && ct >= s.end) { audioEl.pause(); clearPlaying(); }
      }
    });
    audioEl.addEventListener('loadedmetadata', () => { document.getElementById('totTime').textContent = fmtShort(audioEl.duration); });
    audioEl.addEventListener('play', () => { document.getElementById('playBtn').innerHTML = '&#9646;&#9646;'; });
    audioEl.addEventListener('pause', () => { document.getElementById('playBtn').innerHTML = '&#9654;'; });

    function playSeg(idx) {
      if (!hasAudio) return;
      audioEl.currentTime = segs[idx].start;
      audioEl.play();
      clearPlaying();
      playingKey = idx;
      const el = document.querySelector(`[data-i="${idx}"]`);
      if (el) el.classList.add('playing');
    }
    function togglePlay() { if (audioEl.paused) audioEl.play(); else audioEl.pause(); }
    function seekAudio(e) { if (!hasAudio||!audioEl.duration) return; const r=e.currentTarget.getBoundingClientRect(); audioEl.currentTime=((e.clientX-r.left)/r.width)*audioEl.duration; }
    function clearPlaying() { document.querySelectorAll('.s.playing').forEach(e=>e.classList.remove('playing')); playingKey=null; }

    // ---- Utilities ----
    function spkN(speaker) { return parseInt((speaker||'0').replace(/\\D/g,'')) % 4; }
    function fmtShort(s) { if(typeof s!=='number') return s||''; return Math.floor(s/60)+':'+String(Math.floor(s%60)).padStart(2,'0'); }
    function fmtFull(s) { if(typeof s!=='number') return s||''; const h=Math.floor(s/3600),m=Math.floor(s%3600/60),sc=Math.floor(s%60); return String(h).padStart(2,'0')+':'+String(m).padStart(2,'0')+':'+String(sc).padStart(2,'0'); }

    // ---- Render ----
    function render() {
      renderLeft();
      renderRight();
      updateStats();
      scheduleSave();
    }

    function renderLeft() {
      const box = document.getElementById('leftPanel');
      box.innerHTML = '';
      document.getElementById('clipMeta').textContent = clips.length + ' 个片段';

      clips.forEach(clip => {
        const div = document.createElement('div');
        div.className = 'clip rounded-lg border bg-white overflow-hidden';
        div.id = 'clip-' + clip.id;
        div.dataset.clipId = clip.id;

        // Check if all deleted
        const allDel = clip.segs.every(i => action(i) === 'delete');
        if (allDel) div.classList.add('del-all');

        // Clip header
        const dur = clip.end - clip.start;
        const speakers = [...new Set(clip.segs.map(i => segs[i].speaker))];
        const spkHtml = speakers.map(s => `<span class="inline-block px-1 rounded text-[10px] font-bold spk${spkN(s)}bg spk${spkN(s)}">${s}</span>`).join(' ');
        const kept = clip.segs.filter(i => action(i) === 'keep').length;

        const hdr = document.createElement('div');
        hdr.className = 'flex items-center justify-between px-3 py-1 bg-gray-50 border-b text-[11px] text-gray-500';
        hdr.innerHTML = `
          <div class="flex items-center gap-2">
            <span class="font-medium text-gray-700">片段 ${clip.id+1}</span>
            ${spkHtml}
            <span>${fmtShort(clip.start)} - ${fmtShort(clip.end)}</span>
            <span class="text-gray-400">${dur.toFixed(0)}s</span>
            <span class="${kept === 0 ? 'text-red-400' : 'text-emerald-500'}">保留 ${kept}/${clip.segs.length}</span>
          </div>
          <div class="flex gap-1">
            <button onclick="playClip(${clip.id})" class="hover:text-blue-600 px-1" title="播放整段">&#9654;</button>
            <button onclick="deleteClip(${clip.id})" class="hover:text-red-500 px-1 ${allDel ? 'text-red-400' : ''}" title="整段删除">✕</button>
          </div>
        `;
        div.appendChild(hdr);

        // Clip body: group by speaker
        const body = document.createElement('div');
        body.className = 'clip-body px-3 py-2 leading-relaxed';

        let curSpeaker = null;
        let spkBlock = null;
        clip.segs.forEach(idx => {
          const seg = segs[idx];
          const act = action(idx);

          // Start new speaker block if speaker changed
          if (seg.speaker !== curSpeaker) {
            curSpeaker = seg.speaker;
            spkBlock = document.createElement('div');
            spkBlock.className = 'spk-block';
            const label = document.createElement('span');
            label.className = `spk-label spk${spkN(curSpeaker)}bg spk${spkN(curSpeaker)}`;
            label.textContent = curSpeaker + '：';
            spkBlock.appendChild(label);
            body.appendChild(spkBlock);
          }

          const span = document.createElement('span');
          span.className = 's';
          span.dataset.i = idx;

          if (act === 'keep') {
            span.classList.add('keep');
          } else {
            span.classList.add('del');
          }

          span.textContent = seg.text;
          span.title = fmtShort(seg.start) + ' - ' + fmtShort(seg.end);

          // Left click: always play audio
          span.onclick = (e) => {
            e.stopPropagation();
            playSeg(idx);
          };

          // Right click: toggle keep/delete
          span.oncontextmenu = (e) => {
            e.preventDefault();
            seg.user_action = (act === 'keep') ? 'delete' : 'keep';
            render();
          };

          // Hover reason tooltip
          if (seg.ai_reason) {
            const tip = document.createElement('span');
            tip.className = 'reason-tip';
            tip.textContent = seg.ai_reason;
            tip.style.top = '-24px';
            tip.style.left = '0';
            span.style.position = 'relative';
            span.appendChild(tip);
          }

          spkBlock.appendChild(span);
          spkBlock.appendChild(document.createTextNode(' '));
        });

        div.appendChild(body);

        // Hover link: highlight + auto-scroll right panel
        div.onmouseenter = () => {
          document.querySelectorAll(`[data-clip-id="${clip.id}"]`).forEach(el => el.classList.add('clip-linked'));
          // Auto-scroll right panel to matching clip
          const rightEl = document.querySelector(`#rightPanel [data-clip-id="${clip.id}"]`);
          if (rightEl) rightEl.scrollIntoView({behavior: 'smooth', block: 'nearest'});
        };
        div.onmouseleave = () => {
          document.querySelectorAll('.clip-linked').forEach(el => el.classList.remove('clip-linked'));
        };

        box.appendChild(div);
      });
    }

    function renderRight() {
      const box = document.getElementById('rightPanel');
      box.innerHTML = '';

      let totalKept = 0, totalDur = 0, keptDur = 0;
      segs.forEach(s => { totalDur += s.end - s.start; });

      clips.forEach(clip => {
        const keptSegs = clip.segs.filter(i => action(i) === 'keep');
        // Skip fully deleted clips — visible on left side already
        if (!keptSegs.length) return;

        totalKept += keptSegs.length;
        keptSegs.forEach(i => keptDur += segs[i].end - segs[i].start);

        const div = document.createElement('div');
        div.className = 'clip rounded-lg border bg-white overflow-hidden';
        div.dataset.clipId = clip.id;

        // Mini header
        const dur = keptSegs.reduce((a, i) => a + (segs[i].end - segs[i].start), 0);
        const speakers = [...new Set(keptSegs.map(i => segs[i].speaker))];
        const spkHtml = speakers.map(s => `<span class="inline-block px-1 rounded text-[10px] font-bold spk${spkN(s)}bg spk${spkN(s)}">${s}</span>`).join(' ');

        const hdr = document.createElement('div');
        hdr.className = 'flex items-center gap-2 px-3 py-1 bg-emerald-50 border-b text-[11px] text-gray-500';
        hdr.innerHTML = `
          <span class="font-medium text-emerald-700">片段 ${clip.id+1}</span>
          ${spkHtml}
          <span>${dur.toFixed(0)}s</span>
        `;
        div.appendChild(hdr);

        // AI optimization reasoning (collapsible)
        const reasons = clip.segs
          .filter(i => segs[i].ai_reason)
          .map(i => ({idx: i, act: segs[i].ai_action, reason: segs[i].ai_reason, text: segs[i].text.substring(0, 30)}));
        const delReasons = reasons.filter(r => r.act === 'delete');
        const keepReasons = reasons.filter(r => r.act === 'keep');

        if (delReasons.length > 0 || keepReasons.length > 0) {
          const think = document.createElement('details');
          think.className = 'ai-thinking';
          think.innerHTML = `
            <summary>AI 优化思路（删 ${delReasons.length} 句，留 ${keepReasons.length} 句）</summary>
            <ul>
              ${delReasons.map(r => `<li><span style="color:#dc2626">删</span> 「${r.text}…」— ${r.reason}</li>`).join('')}
              ${keepReasons.slice(0, 5).map(r => `<li><span style="color:#16a34a">留</span> 「${r.text}…」— ${r.reason}</li>`).join('')}
              ${keepReasons.length > 5 ? `<li style="color:#9ca3af">…另 ${keepReasons.length - 5} 句保留</li>` : ''}
            </ul>
          `;
          div.appendChild(think);
        }

        // Body with speaker grouping — only kept segments
        const body = document.createElement('div');
        body.className = 'px-3 py-2 leading-relaxed text-gray-800';

        let curSpeaker = null;
        let spkBlock = null;
        keptSegs.forEach(idx => {
          const seg = segs[idx];
          if (seg.speaker !== curSpeaker) {
            curSpeaker = seg.speaker;
            spkBlock = document.createElement('div');
            spkBlock.className = 'spk-block';
            const label = document.createElement('span');
            label.className = `spk-label spk${spkN(curSpeaker)}bg spk${spkN(curSpeaker)}`;
            label.textContent = curSpeaker + '：';
            spkBlock.appendChild(label);
            body.appendChild(spkBlock);
          }
          const span = document.createElement('span');
          span.textContent = seg.text;
          spkBlock.appendChild(span);
          spkBlock.appendChild(document.createTextNode(' '));
        });

        div.appendChild(body);

        // Hover link: highlight corresponding left panel clip
        div.onmouseenter = () => {
          document.querySelectorAll(`[data-clip-id="${clip.id}"]`).forEach(el => el.classList.add('clip-linked'));
        };
        div.onmouseleave = () => {
          document.querySelectorAll('.clip-linked').forEach(el => el.classList.remove('clip-linked'));
        };

        box.appendChild(div);
      });

      if (!totalKept) {
        box.innerHTML = '<div class="text-gray-400 text-center mt-8">所有片段已删除</div>';
      }

      const pct = totalDur > 0 ? Math.round(keptDur / totalDur * 100) : 0;
      document.getElementById('rightMeta').textContent = `${keptDur.toFixed(0)}s / ${totalDur.toFixed(0)}s（${pct}%）`;
    }

    function updateStats() {
      const total = segs.length;
      const kept = segs.filter((_, i) => action(i) === 'keep').length;
      document.getElementById('stats').textContent = `保留 ${kept}/${total} 句`;
    }

    // ---- Actions ----
    function deleteClip(clipId) {
      const clip = clips[clipId];
      const allDel = clip.segs.every(i => action(i) === 'delete');
      clip.segs.forEach(i => { segs[i].user_action = allDel ? null : 'delete'; });
      render();
    }

    function playClip(clipId) {
      if (!hasAudio) return;
      audioEl.currentTime = clips[clipId].start;
      audioEl.play();
    }

    function restoreAll() {
      segs.forEach(s => { s.user_action = null; });
      render();
    }

    // ---- Export ----
    async function confirmExport(format) {
      const kept = segs.filter((_, i) => action(i) === 'keep');
      if (!kept.length) { showToast('没有保留的片段', true); return; }

      const mediaPath = document.getElementById('mediaPath').value.trim();
      if (!mediaPath && format === 'fcpxml') { showToast('请先填写素材路径', true); return; }

      // 1. 保存选中片段
      const saveRes = await fetch('/api/selections', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(kept)
      });
      if (!saveRes.ok) { showToast('保存失败', true); return; }

      // 2. 在服务端生成
      const genRes = await fetch('/api/generate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({media_path: mediaPath, format: format})
      });
      const genData = await genRes.json();
      if (!genRes.ok) { showToast('生成失败: ' + (genData.error || ''), true); return; }

      // 3. 下载
      const dlRes = await fetch('/api/download?format=' + format);
      if (!dlRes.ok) { showToast('下载失败', true); return; }
      const blob = await dlRes.blob();
      const ext = format === 'resolve' ? '.xml' : '.fcpxml';
      const defaultName = '粗剪时间线' + ext;

      if (window.showSaveFilePicker) {
        try {
          const handle = await window.showSaveFilePicker({
            suggestedName: defaultName,
            types: [{ description: 'Timeline', accept: {'application/xml': [ext]} }]
          });
          const writable = await handle.createWritable();
          await writable.write(blob);
          await writable.close();
          showToast('已保存：' + handle.name + '（' + kept.length + ' 句）');
          return;
        } catch (e) {
          if (e.name === 'AbortError') return;
        }
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = defaultName;
      a.click();
      URL.revokeObjectURL(url);
      showToast('已下载 ' + defaultName + '（' + kept.length + ' 句）');
    }

    function showToast(msg, err=false) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.className = 'fixed bottom-4 right-4 px-4 py-2 rounded shadow-lg text-white z-50 text-xs ' + (err ? 'bg-red-600' : 'bg-slate-800');
      t.classList.remove('hidden');
      setTimeout(() => t.classList.add('hidden'), 4000);
    }

    init();
  </script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

def load_json_file(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_segments(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        segments = payload.get("segments", [])
        if isinstance(segments, list):
            return segments
    return []

def merge_user_state(payload, state_rows):
    if isinstance(payload, dict):
        segments = extract_segments(payload)
        payload["segments"] = segments
        output = payload
    elif isinstance(payload, list):
        segments = payload
        output = segments
    else:
        segments = []
        output = []

    for i, state in enumerate(state_rows):
        if i >= len(segments):
            break
        if state.get("user_action") is not None:
            segments[i]["user_action"] = state["user_action"]
        if "ai_action" in state:
            segments[i]["ai_action"] = state["ai_action"]
        if "ai_reason" in state:
            segments[i]["ai_reason"] = state["ai_reason"]
    return output

@app.route("/api/data")
def api_data():
    transcript = []
    # Prefer edited transcript (with ai_action) over raw transcript
    if os.path.exists(EDITED_PATH):
        transcript = extract_segments(load_json_file(EDITED_PATH))
    elif os.path.exists(TRANSCRIPT_PATH):
        transcript = extract_segments(load_json_file(TRANSCRIPT_PATH))

    audio_url = None
    if AUDIO_PATH and os.path.exists(AUDIO_PATH):
        audio_url = "/api/audio"

    return jsonify({
        "transcript": transcript,
        "audio_url": audio_url,
        "context": PROJECT_CONTEXT,
        "media_path": MEDIA_PATH,
    })

@app.route("/api/audio")
def api_audio():
    if AUDIO_PATH and os.path.exists(AUDIO_PATH):
        return send_file(AUDIO_PATH, mimetype="audio/mpeg")
    return jsonify({"error": "No audio"}), 404

@app.route("/api/selections", methods=["GET", "POST"])
def api_selections():
    if request.method == "POST":
        data = request.get_json()
        with open(SELECTIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"ok": True})
    else:
        if os.path.exists(SELECTIONS_PATH):
            with open(SELECTIONS_PATH, "r", encoding="utf-8") as f:
                return jsonify(json.load(f))
        return jsonify([])

@app.route("/api/generate", methods=["POST"])
def api_generate():
    data = request.get_json() or {}
    media_path = data.get("media_path", "")
    fmt = data.get("format", "resolve")

    if not os.path.exists(SELECTIONS_PATH):
        return jsonify({"error": "没有选中的片段"}), 400

    try:
        if fmt == "resolve":
            # Generate DaVinci Resolve XML (xmeml 5)
            tmp_output = "/tmp/roughcut_export.xml"
            cmd = [
                sys.executable, str(SCRIPT_DIR / "generate_davinci_xml.py"),
                SELECTIONS_PATH, "-o", tmp_output,
                "--fps", str(FPS),
            ]
            env = os.environ.copy()
            if DAVINCI_REF_PATH:
                env["DAVINCI_REF_PATH"] = DAVINCI_REF_PATH
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env)
        else:
            # Generate FCPXML
            tmp_output = "/tmp/roughcut_export.fcpxml"
            cmd = [sys.executable, str(SCRIPT_DIR / "generate_fcpxml.py"), SELECTIONS_PATH, "-o", tmp_output]
            if MEDIA_MANIFEST_PATH:
                cmd.extend(["--media-manifest", MEDIA_MANIFEST_PATH])
            elif media_path:
                cmd.extend(["--media", media_path])
            subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        return jsonify({"output": tmp_output})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/download")
def api_download():
    fmt = request.args.get("format", "fcpxml")
    if fmt == "resolve":
        path = "/tmp/roughcut_export.xml"
        name = "粗剪时间线.xml"
    else:
        path = "/tmp/roughcut_export.fcpxml"
        name = "粗剪时间线.fcpxml"

    if not os.path.exists(path):
        return jsonify({"error": "请先生成文件"}), 404
    return send_file(path, as_attachment=True, download_name=name)


@app.route("/api/save_state", methods=["POST"])
def api_save_state():
    """Save user edits back to edited_transcript.json for persistence."""
    data = request.get_json()
    if not data:
        return jsonify({"ok": False}), 400
    # Read current edited transcript and merge user_action
    target = EDITED_PATH if os.path.exists(EDITED_PATH) else TRANSCRIPT_PATH
    if os.path.exists(target):
        payload = merge_user_state(load_json_file(target), data)
        with open(EDITED_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return jsonify({"ok": True})
    return jsonify({"ok": False}), 404


def load_project_context(project_dir: str) -> str:
    """Load optional project context from a user-provided directory."""
    if not project_dir or not os.path.isdir(project_dir):
        return ""
    parts = []
    candidates = [
        ("Editor Brief", "context.md", None),
        ("Editor Brief", "brief.md", None),
        ("Project Brief", "00-选题简报.md", None),
        ("Project Notes", "notes.md", None),
        ("Project Notes", "03-对话沉淀.md", None),
        ("Account / Channel Guide", "account.md", 80),
        ("Account / Channel Guide", "账号手册.md", 80),
    ]
    for title, filename, max_lines in candidates:
        path = os.path.join(project_dir, filename)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            continue
        if max_lines:
            content = "\n".join(content.splitlines()[:max_lines])
        parts.append(f"## {title}: {filename}\n{content}")
    return "\n\n".join(parts)


def main():
    parser = argparse.ArgumentParser(description="粗剪工作台")
    parser.add_argument("--transcript", default="transcription.json")
    parser.add_argument("--edited", default="edited_transcript.json")
    parser.add_argument("--selections", default="selections.json")
    parser.add_argument("--audio", default=None, help="音频文件路径")
    parser.add_argument("--media", default="", help="FCPXML 导出用素材路径")
    parser.add_argument("--media-manifest", default=None)
    parser.add_argument("--context", default="", help="项目背景描述")
    parser.add_argument("--project-dir", default="", help="项目上下文目录（可包含 context.md、brief.md、account.md 等）")
    parser.add_argument("--davinci-ref", default="", help="达芬奇导出的参考 XML 路径")
    parser.add_argument("--fps", type=int, default=50, help="帧率 (默认50)")
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()

    global TRANSCRIPT_PATH, EDITED_PATH, SELECTIONS_PATH, AUDIO_PATH, MEDIA_PATH, MEDIA_MANIFEST_PATH, PROJECT_CONTEXT, DAVINCI_REF_PATH, FPS
    TRANSCRIPT_PATH = args.transcript
    EDITED_PATH = args.edited
    SELECTIONS_PATH = args.selections
    AUDIO_PATH = os.path.abspath(args.audio) if args.audio else None
    MEDIA_PATH = args.media
    MEDIA_MANIFEST_PATH = args.media_manifest
    DAVINCI_REF_PATH = args.davinci_ref
    FPS = args.fps

    # Context: --project-dir takes precedence, then --context
    if args.project_dir:
        PROJECT_CONTEXT = load_project_context(args.project_dir)
        if not PROJECT_CONTEXT:
            PROJECT_CONTEXT = args.context
    else:
        PROJECT_CONTEXT = args.context

    print(f"粗剪工作台: http://localhost:{args.port}")
    if AUDIO_PATH:
        print(f"音频: {AUDIO_PATH}")
    if PROJECT_CONTEXT:
        print(f"项目上下文: {len(PROJECT_CONTEXT)} 字")
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()
