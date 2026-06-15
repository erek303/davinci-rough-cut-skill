#!/usr/bin/env python3
from __future__ import annotations

import csv
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.dont_write_bytecode = True


REPO = Path(__file__).resolve().parents[1]
SKILL = REPO / "skill" / "davinci-rough-cut"
SCRIPTS = SKILL / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class OfflineWorkflowTests(unittest.TestCase):
    def test_skill_frontmatter_is_valid_enough_for_distribution(self):
        content = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        self.assertIsNotNone(match)
        frontmatter = match.group(1)
        self.assertIn("name: davinci-rough-cut", frontmatter)
        self.assertIn("description:", frontmatter)
        self.assertLess(len(frontmatter), 1200)

    def test_generate_davinci_xml_from_kept_segments(self):
        module = load_module("generate_davinci_xml", SCRIPTS / "generate_davinci_xml.py")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / "camera_a.mp4"
            media.write_bytes(b"")
            selections = root / "selections.json"
            output = root / "rough_cut.xml"
            selections.write_text(
                json.dumps(
                    [
                        {
                            "start": 0.0,
                            "end": 2.0,
                            "text": "This is the opening idea.",
                            "speaker": "spk1",
                            "source_path": str(media),
                        },
                        {
                            "start": 5.0,
                            "end": 7.5,
                            "text": "Here is the concrete example.",
                            "speaker": "spk1",
                            "source_path": str(media),
                        },
                    ]
                ),
                encoding="utf-8",
            )
            module.generate_davinci_xml(str(selections), str(output), fps=50, timeline_name="test")
            tree = ET.parse(output)
            self.assertEqual(tree.getroot().tag, "xmeml")
            self.assertIn("camera_a.mp4", output.read_text(encoding="utf-8"))

    def test_generate_alignment_xml_and_audit_without_ffprobe(self):
        module = load_module("generate_alignment_xml", SCRIPTS / "generate_alignment_xml.py")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video_dir = root / "video"
            audio_dir = root / "audio"
            video_dir.mkdir()
            audio_dir.mkdir()
            for filename in ("C0001.MP4", "C0002.MP4"):
                (video_dir / filename).write_bytes(b"")
            wav = audio_dir / "REC001.WAV"
            wav.write_bytes(b"")

            matches = root / "matches.csv"
            with matches.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["filename", "duration", "wav_time_sec", "ncc"])
                writer.writeheader()
                writer.writerow({"filename": "C0001.MP4", "duration": "1.0", "wav_time_sec": "0.5", "ncc": "0.99"})
                writer.writerow({"filename": "C0002.MP4", "duration": "1.0", "wav_time_sec": "2.0", "ncc": "0.98"})

            timecodes = root / "timecodes.csv"
            with timecodes.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["filename", "timecode"])
                writer.writeheader()
                writer.writerow({"filename": "C0001.MP4", "timecode": "01:00:00:00"})
                writer.writerow({"filename": "C0002.MP4", "timecode": "01:00:02:00"})

            output = root / "alignment.xml"
            audit = root / "audit.csv"
            module.generate_xml(
                matches_csv=matches,
                timecodes_csv=timecodes,
                video_dir=video_dir,
                audio_dir=audio_dir,
                output_xml=output,
                audit_csv=audit,
                project_name="test_alignment",
                min_ncc=0.5,
                selected_names={"C0001.MP4", "C0002.MP4"},
                fps=50,
                wav_durations={"REC001.WAV": 4.0},
            )

            tree = ET.parse(output)
            self.assertEqual(tree.getroot().tag, "xmeml")
            with audit.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(row["status"] == "included" for row in rows))

    def test_install_script_copies_valid_skill_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "skills"
            bin_dir = Path(tmp) / "bin"
            env = os.environ.copy()
            env["DAVINCI_ROUGH_CUT_BIN_DIR"] = str(bin_dir)
            subprocess.check_call(["bash", str(REPO / "install.sh"), "--target", str(target)], env=env)
            installed = target / "davinci-rough-cut"
            self.assertTrue((installed / "SKILL.md").exists())
            self.assertTrue((installed / "scripts" / "web_editor.py").exists())
            self.assertTrue((installed / "scripts" / "mimo_asr.py").exists())
            self.assertTrue((installed / "update.sh").exists())
            launcher = bin_dir / "davinci-rough-cut-update"
            self.assertTrue(launcher.exists())
            self.assertIn(str(installed / "update.sh"), launcher.read_text(encoding="utf-8"))
            self.assertFalse((installed / ".venv").exists())

    def test_install_script_auto_target_uses_explicit_env_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "agent-skills"
            bin_dir = Path(tmp) / "bin"
            env = os.environ.copy()
            env["DAVINCI_ROUGH_CUT_SKILL_ROOT"] = str(target)
            env["DAVINCI_ROUGH_CUT_BIN_DIR"] = str(bin_dir)

            subprocess.check_call(["bash", str(REPO / "install.sh"), "--target", "auto"], env=env)

            installed = target / "davinci-rough-cut"
            self.assertTrue((installed / "SKILL.md").exists())
            self.assertIn(str(installed / "update.sh"), (bin_dir / "davinci-rough-cut-update").read_text(encoding="utf-8"))

    def test_install_script_agent_hint_uses_agent_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            env = os.environ.copy()
            env["HOME"] = str(home)

            subprocess.check_call(
                ["bash", str(REPO / "install.sh"), "--agent", "claude", "--no-launcher"],
                env=env,
            )

            self.assertTrue((home / ".claude" / "skills" / "davinci-rough-cut" / "SKILL.md").exists())

    def test_install_script_help_documents_agent_neutral_install(self):
        result = subprocess.run(
            ["bash", str(REPO / "install.sh"), "--help"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        self.assertIn("--target DIR|auto", result.stdout)
        self.assertIn("--agent NAME", result.stdout)
        self.assertIn("--print-targets", result.stdout)
        self.assertIn("DAVINCI_ROUGH_CUT_SKILL_ROOT", result.stdout)
        self.assertIn("instead of assuming", result.stdout)

    def test_update_script_help_is_available_offline(self):
        result = subprocess.run(
            ["bash", str(SKILL / "update.sh"), "--help"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        self.assertIn("Update the installed DaVinci Rough Cut skill", result.stdout)
        self.assertIn("bash /path/to/installed/davinci-rough-cut/update.sh", result.stdout)
        self.assertIn("--no-prune", result.stdout)
        self.assertIn("davinci-rough-cut-update", result.stdout)
        self.assertIn("DAVINCI_ROUGH_CUT_BIN_DIR", result.stdout)

    def test_update_script_prunes_stale_packaged_files_and_preserves_local_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            source_repo = Path(tmp) / "source-repo"
            shutil.copytree(
                REPO,
                source_repo,
                ignore=shutil.ignore_patterns(".git", ".venv", "__pycache__", "*.pyc"),
            )
            subprocess.check_call(
                ["git", "-c", "init.defaultBranch=main", "init"],
                cwd=source_repo,
                stdout=subprocess.DEVNULL,
            )
            subprocess.check_call(["git", "add", "."], cwd=source_repo, stdout=subprocess.DEVNULL)
            subprocess.check_call(
                [
                    "git",
                    "-c",
                    "user.name=DaVinci Rough Cut Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "commit",
                    "-m",
                    "test package source",
                ],
                cwd=source_repo,
                stdout=subprocess.DEVNULL,
            )

            target = Path(tmp) / "skills"
            bin_dir = Path(tmp) / "bin"
            subprocess.check_call(["bash", str(REPO / "install.sh"), "--target", str(target), "--no-launcher"])
            installed = target / "davinci-rough-cut"

            stale = installed / "scripts" / "workflow_server.py"
            stale.write_text("stale dashboard file", encoding="utf-8")
            (installed / ".env").write_text("LOCAL_SECRET=do-not-delete", encoding="utf-8")
            venv = installed / ".venv"
            work = installed / "work"
            venv.mkdir()
            work.mkdir()
            (venv / "keep.txt").write_text("venv", encoding="utf-8")
            (work / "keep.txt").write_text("work", encoding="utf-8")
            env = os.environ.copy()
            env["DAVINCI_ROUGH_CUT_BIN_DIR"] = str(bin_dir)

            subprocess.check_call(
                [
                    "bash",
                    str(installed / "update.sh"),
                    "--repo",
                    str(source_repo),
                    "--skip-tests",
                ],
                env=env,
            )

            self.assertFalse(stale.exists())
            self.assertTrue((installed / ".env").exists())
            self.assertTrue((venv / "keep.txt").exists())
            self.assertTrue((work / "keep.txt").exists())
            launcher = bin_dir / "davinci-rough-cut-update"
            self.assertTrue(launcher.exists())
            self.assertIn(str(installed / "update.sh"), launcher.read_text(encoding="utf-8"))

    def test_canonical_update_chat_command_is_documented(self):
        expected = "/davinci-rough-cut update"
        for rel in ("README.md", "README.zh.md", "docs/quickstart.zh.md", "skill/davinci-rough-cut/SKILL.md"):
            content = (REPO / rel).read_text(encoding="utf-8")
            self.assertIn(expected, content, rel)

    def test_agent_neutral_install_and_workflow_commands_are_documented(self):
        docs = "\n".join(
            (REPO / rel).read_text(encoding="utf-8")
            for rel in (
                "README.md",
                "README.zh.md",
                "docs/quickstart.zh.md",
                "docs/user-manual.md",
                "skill/davinci-rough-cut/SKILL.md",
            )
        )
        self.assertNotIn("/davinci-rough-cut install", docs)
        self.assertNotIn("/davinci-rough-cut interview", docs)
        self.assertIn("/davinci-rough-cut rough-cut", docs)
        self.assertIn("/davinci-rough-cut align", docs)
        self.assertIn("bash install.sh --target auto", docs)
        self.assertIn("Do not default to Codex paths", docs)
        self.assertIn("不要默认使用 Codex 路径", docs)
        self.assertNotIn("Create a Python venv inside ~/.codex/skills/davinci-rough-cut", docs)
        self.assertNotIn("在 ~/.codex/skills/davinci-rough-cut 下创建 Python venv", docs)

    def test_volcengine_fast_mode_is_default_without_tos(self):
        module = load_module("volcengine_asr", SCRIPTS / "volcengine_asr.py")
        body = module.build_asr_body({"data": "abc", "format": "mp3"})
        self.assertEqual(body["audio"]["data"], "abc")
        self.assertEqual(body["request"]["model_name"], "bigmodel")
        self.assertTrue(body["request"]["enable_speaker_info"])

        docs = "\n".join(
            (REPO / rel).read_text(encoding="utf-8")
            for rel in ("README.md", "README.zh.md", "docs/quickstart.zh.md", "docs/user-manual.md", ".env.example")
        )
        self.assertIn("fast mode", docs)
        self.assertIn("极速版", docs)
        self.assertIn("standard-url", docs)
        self.assertIn("普通用户不需要先开 TOS", docs)

    def test_cross_agent_paths_and_review_panel_rule_are_documented(self):
        docs = "\n".join(
            (REPO / rel).read_text(encoding="utf-8")
            for rel in (
                "README.md",
                "README.zh.md",
                "docs/quickstart.zh.md",
                "docs/user-manual.md",
                "skill/davinci-rough-cut/SKILL.md",
            )
        )
        self.assertIn("~/.newmax/skills", docs)
        self.assertIn("DAVINCI_ROUGH_CUT_SKILL_DIR", docs)
        self.assertIn("Mandatory Review Panel Rule", docs)
        self.assertIn("web_editor.py", docs)
        self.assertIn("Do not jump directly from `transcript.json` / `edited.json` to `rough_cut.xml`", docs)

    def test_web_editor_accepts_standard_transcript_dict_shape(self):
        module = load_module("web_editor", SCRIPTS / "web_editor.py")
        payload = json.loads((REPO / "tests" / "fixtures" / "transcript.sample.json").read_text(encoding="utf-8"))

        rows = module.extract_segments(payload)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["text"], "This is the opening idea.")

        saved = module.merge_user_state(
            payload,
            [{"user_action": "delete", "ai_action": "delete", "ai_reason": "Manual override."}],
        )
        self.assertIn("segments", saved)
        self.assertEqual(saved["segments"][0]["user_action"], "delete")

    def test_no_generated_or_private_files_are_packaged(self):
        forbidden_parts = {".venv", "__pycache__"}
        forbidden_suffixes = {".pyc", ".asr.json", ".edited.json"}
        forbidden_tokens = [
            "/" + "Users/",
            "/" + "Volumes/",
            "~/.Co" + "dex",
        ]
        for path in REPO.rglob("*"):
            rel = path.relative_to(REPO)
            self.assertFalse(any(part in forbidden_parts for part in rel.parts), rel)
            self.assertNotIn(path.suffix, forbidden_suffixes, rel)
            if path.is_file():
                text = path.read_text(encoding="utf-8", errors="ignore")
                for token in forbidden_tokens:
                    self.assertNotIn(token, text, rel)


if __name__ == "__main__":
    unittest.main()
