import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

from tandem_bridge import tandem as t
from tandem_bridge import handoff


ROOT = Path(__file__).resolve().parents[1]


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name) / "project"
        self.project.mkdir()
        self.body = Path(self.temp.name) / "body.md"
        self.body.write_text("# Snapshot\n\nState: review pending.\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_checkpoint_collision_and_read_only_recap(self):
        first = handoff.checkpoint(self.project, self.body)
        second = handoff.checkpoint(self.project, self.body)
        self.assertNotEqual(first["path"], second["path"])
        self.assertTrue(Path(first["path"]).is_file())
        pointer = self.project / ".tandem/handoff/LATEST.md"
        self.assertEqual(pointer.read_text(encoding="utf-8"), second["relative_path"] + "\n")
        before = {p: p.read_bytes() for p in self.project.rglob("*.md")}
        result = handoff.recap(self.project)
        self.assertEqual(result["snapshot"], self.body.read_text(encoding="utf-8"))
        self.assertEqual(before, {p: p.read_bytes() for p in self.project.rglob("*.md")})

    def test_bad_pointer_is_preserved(self):
        latest = self.project / ".tandem/handoff/LATEST.md"
        latest.parent.mkdir(parents=True)
        for text in ("../outside.md\n", "two\nlines\n", "authored prose\n", "history/x.md",
                     ".tandem/handoff/history/2026-09-27T060000Z.md\n"):
            with self.subTest(text=text):
                latest.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    handoff.checkpoint(self.project, self.body)
                self.assertEqual(latest.read_text(encoding="utf-8"), text)
        self.assertFalse((latest.parent / "history").exists())

    def test_symlink_pointer_refused(self):
        latest = self.project / ".tandem/handoff/LATEST.md"
        latest.parent.mkdir(parents=True)
        try:
            latest.symlink_to(self.body)
        except OSError:
            self.skipTest("Symlinks unavailable on this host")
        with self.assertRaises(ValueError):
            handoff.checkpoint(self.project, self.body)

    def test_system_style_ancestor_alias_is_allowed(self):
        alias = Path(self.temp.name) / "alias"
        try:
            alias.symlink_to(Path(self.temp.name), target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable on this host")
        result = handoff.checkpoint(alias / "project", self.body)
        self.assertEqual(Path(result["path"]).parent, self.project.resolve() / ".tandem/handoff/history")

    def test_project_root_alias_resolves_into_project(self):
        alias = Path(self.temp.name) / "project-alias"
        try:
            alias.symlink_to(self.project, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable on this host")
        result = handoff.checkpoint(alias, self.body)
        self.assertEqual(Path(result["path"]).parent, self.project.resolve() / ".tandem/handoff/history")
        self.assertEqual(handoff.recap(alias)["snapshot"], self.body.read_text(encoding="utf-8"))

    def test_handoff_directory_symlink_is_refused(self):
        outside = Path(self.temp.name) / "outside"
        outside.mkdir()
        tandem = self.project / ".tandem"
        try:
            tandem.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable on this host")
        with self.assertRaises(ValueError):
            handoff.checkpoint(self.project, self.body)
        self.assertEqual(list(outside.iterdir()), [])

    def test_cli_checkpoint_and_recap(self):
        helper = ROOT / "tandem.py"
        ledger = self.project / ".tandem/state"
        base = [sys.executable, "-B", str(helper), "--state-dir", str(ledger)]
        made = subprocess.run(base + ["checkpoint", "--project-root", str(self.project),
                                      "--body-file", str(self.body)], capture_output=True, text=True)
        self.assertEqual(made.returncode, 0, made.stderr)
        read = subprocess.run(base + ["recap", "--project-root", str(self.project)],
                              capture_output=True, text=True)
        self.assertEqual(read.returncode, 0, read.stderr)
        self.assertEqual(json.loads(read.stdout)["snapshot"], self.body.read_text(encoding="utf-8"))

    def test_make_budget_evidence_and_old_envelope(self):
        helper = ROOT / "tandem.py"
        ledger = self.project / ".tandem/state"
        out = Path(self.temp.name) / "task.json"
        from_id, to_id = str(uuid.uuid4()), str(uuid.uuid4())
        base = [sys.executable, "-B", str(helper), "--state-dir", str(ledger)]
        cmd = base + ["make", "--from-agent", "codex", "--from-session", from_id,
                      "--to-agent", "claude", "--to-session", to_id,
                      "--body-file", str(self.body), "--out", str(out), "--tag", "review",
                      "--done", "Check result", "--budget", "3 review rounds",
                      "--evidence-required", "test output", "--evidence-required", "SHA256"]
        made = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(made.returncode, 0, made.stderr)
        msg = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(msg["budget"], "3 review rounds")
        self.assertEqual(msg["evidence_required"], ["test output", "SHA256"])
        t.validate(msg)
        old = {k: v for k, v in msg.items() if k not in ("budget", "evidence_required")}
        t.validate(old)
        old["evidence_required"] = [""]
        with self.assertRaises(t.ValidationError):
            t.validate(old)
        t.Ledger(ledger).record(msg)
        status = subprocess.run(base + ["status", msg["id"]], capture_output=True, text=True)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertEqual(json.loads(status.stdout)["budget"], "3 review rounds")
        summary = subprocess.run(base + ["summary"], capture_output=True, text=True)
        self.assertEqual(summary.returncode, 0, summary.stderr)
        self.assertIn("3 review rounds", summary.stdout)
        self.assertIn("test output", summary.stdout)


if __name__ == "__main__":
    unittest.main()
