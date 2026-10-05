import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

from tandem_bridge import handoff
from tandem_bridge import tandem as t


ROOT = Path(__file__).resolve().parents[1]


class VersionSixTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = t.Ledger(self.root / "state")
        self.sender = {"agent": "claude", "session_id": str(uuid.uuid4())}
        self.receiver = {"agent": "codex", "session_id": str(uuid.uuid4())}

    def tearDown(self):
        self.temp.cleanup()

    def command(self, *args):
        with patch.object(sys, "argv", ["tandem.py", "--state-dir", str(self.ledger.root), *args]):
            return t.main()

    def make(self, *, fyi=False, tag="v060"):
        body = self.root / f"{uuid.uuid4()}.txt"
        body.write_text("Review café and return findings.", encoding="utf-8")
        argv = ["make", "--from-agent", self.sender["agent"], "--from-session", self.sender["session_id"],
                "--to-agent", self.receiver["agent"], "--to-session", self.receiver["session_id"],
                "--body-file", str(body), "--out", str(self.root / f"{uuid.uuid4()}.json"),
                "--tag", tag, "--done", "Report findings"]
        if fyi:
            argv.append("--fyi")
        result = self.command(*argv)
        return t.read_message(result["path"]), result

    def test_fyi_claim_closes_and_open_text_filters_but_json_keeps_rows(self):
        fyi, _ = self.make(fyi=True)
        normal, _ = self.make()
        self.ledger.record(fyi)
        self.ledger.record(normal)
        self.ledger.event(fyi, "transport_returned")
        self.ledger.event(normal, "transport_returned")
        self.assertTrue(fyi["fyi"])
        self.command("receive", fyi["id"], "--agent", "codex", "--session", self.receiver["session_id"])
        rows = t.summary(self.ledger)["tasks"]
        self.assertEqual({row["id"]: row["state"] for row in rows}[fyi["id"]], "fyi_claimed")
        text = t.summary_text({**t.summary(self.ledger), "state_dir": str(self.ledger.root)}, open_only=True)
        self.assertNotIn(fyi["id"][:8], text)
        self.assertIn(normal["id"][:8], text)
        self.assertEqual(len(self.command("summary", "--open", "--format", "json")["tasks"]), 2)

    def test_show_and_bare_receive_with_utf8(self):
        msg, _ = self.make()
        self.ledger.record(msg)
        shown = self.command("show", msg["id"])
        self.assertIn("café", shown["body"])
        self.assertEqual(shown["state"], "recorded_not_dispatched")
        self.assertEqual(shown["done_when"], ["Report findings"])
        self.assertEqual(self.command("receive", msg["id"], "--agent", "codex",
                                      "--session", self.receiver["session_id"])["state"], "claimed")
        result = subprocess.run([sys.executable, "-B", str(ROOT / "tandem.py"),
                                 "--state-dir", str(self.ledger.root), "show", msg["id"]],
                                capture_output=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("café", result.stdout)

    def test_completed_reply_hashes_and_receive_accept(self):
        task, _ = self.make()
        self.ledger.claim(task, self.receiver)
        response = self.root / "response.txt"
        response.write_text("Done", encoding="utf-8")
        evidence = self.root / "evidence.txt"
        evidence.write_text("verified", encoding="utf-8")
        made = self.command("reply", task["id"], "--agent", "codex", "--session",
                            self.receiver["session_id"], "--body-file", str(response),
                            "--status", "completed", "--evidence", str(evidence))
        reply = t.read_message(made["path"])
        self.assertEqual(reply["result"]["evidence_sha256"][0]["sha256"], t.file_hash(evidence))
        self.assertEqual(self.command("receive", reply["id"], "--agent", "claude", "--session",
                                      self.sender["session_id"], "--accept")["state"], "review_accepted")
        self.assertEqual(t.summary(self.ledger)["tasks"][0]["state"], "review_accepted")
        self.assertTrue(any(event.get("evidence") == str(self.ledger.root / "messages" / (reply["id"] + ".json"))
                            for event in self.ledger.events(task["id"])))

    def test_missing_evidence_reports_mismatch_and_blocks_accept(self):
        task, _ = self.make()
        self.ledger.claim(task, self.receiver)
        response = self.root / "response.txt"
        response.write_text("Done", encoding="utf-8")
        evidence = self.root / "evidence.txt"
        evidence.write_text("verified", encoding="utf-8")
        made = self.command("reply", task["id"], "--agent", "codex", "--session",
                            self.receiver["session_id"], "--body-file", str(response),
                            "--status", "completed", "--evidence", str(evidence))
        evidence.unlink()
        with self.assertRaisesRegex(ValueError, "Evidence hash mismatch"):
            self.command("receive", made["id"], "--agent", "claude", "--session",
                         self.sender["session_id"], "--accept")
        self.assertFalse((self.ledger.root / "claims" / made["id"]).exists())
        receipt = self.command("receive", made["id"], "--agent", "claude", "--session",
                               self.sender["session_id"])
        self.assertEqual(receipt["evidence_checks"][0]["actual_sha256"], None)
        self.assertFalse(receipt["evidence_checks"][0]["match"])

    def test_generated_reply_files_refuse_collisions(self):
        task, _ = self.make(tag="tag.with.dot")
        self.ledger.claim(task, self.receiver)
        with patch.object(sys, "stdin", io.StringIO("Here is my answer")):
            made = self.command("reply", task["id"], "--agent", "codex", "--session",
                                self.receiver["session_id"], "--body-stdin", "--status", "completed")
        self.assertTrue(Path(made["body_path"]).name.endswith("tag.with.dot-reply-codex.txt"))
        self.assertTrue(Path(made["path"]).is_file())
        self.assertEqual(Path(made["body_path"]).read_text(encoding="utf-8"), "Here is my answer")
        with patch.object(sys, "stdin", io.StringIO("Another answer")):
            with self.assertRaisesRegex(ValueError, "already exists"):
                self.command("reply", task["id"], "--agent", "codex", "--session",
                             self.receiver["session_id"], "--body-stdin", "--status", "blocked")

    def test_generated_envelope_with_explicit_new_body(self):
        task, _ = self.make(tag="next-step")
        self.ledger.claim(task, self.receiver)
        body = self.root / "new-body.txt"
        body.write_text("New result", encoding="utf-8")
        made = self.command("reply", task["id"], "--agent", "codex", "--session",
                            self.receiver["session_id"], "--body-file", str(body),
                            "--status", "completed")
        self.assertEqual(Path(made["path"]).name, "next-step-reply-codex.json")
        self.assertEqual(t.read_message(made["path"])["body"], "New result")

    def test_claude_send_reports_absent_watch_without_blocking(self):
        task, _ = self.make()
        task["to"] = {"agent": "claude", "session_id": str(uuid.uuid4())}
        with patch.object(t, "fresh_watch", return_value=None), \
             patch.object(t, "transport", return_value=(["relay"], "request", str(uuid.uuid4()))):
            preview = t.send(task, self.ledger, "claude.exe", self.root, 5, dry_run=True)
        self.assertIn("watch not running for", preview["watch_note"])
        self.assertFalse((self.ledger.root / "messages").exists())

    def test_close_dry_run_preserves_messages_then_records_actor(self):
        task, _ = self.make()
        task["created_at"] = "2026-09-30T00:00:00Z"
        self.ledger.record(task)
        original = (self.ledger.root / "messages" / (task["id"] + ".json")).read_bytes()
        flags = ["--before", "2026-10-01", "--reason", "Reviewed old backlog",
                 "--agent", "codex", "--session", self.receiver["session_id"]]
        preview = self.command("close", *flags, "--dry-run")
        self.assertEqual(preview["count"], 1)
        self.assertFalse((self.ledger.root / "closures").exists())
        result = self.command("close", *flags)
        self.assertEqual(result["count"], 1)
        self.assertEqual((self.ledger.root / "messages" / (task["id"] + ".json")).read_bytes(), original)
        self.assertEqual(t.summary(self.ledger)["tasks"][0]["state"], "administratively_closed")
        self.assertEqual(self.command("close", *flags, "--dry-run")["count"], 0)

    def test_per_session_handoff_preserves_legacy_and_lists_other(self):
        project = self.root / "project"
        project.mkdir()
        body = self.root / "checkpoint.md"
        body.write_text("First", encoding="utf-8")
        first = handoff.checkpoint(project, body)
        body.write_text("Second", encoding="utf-8")
        second = handoff.checkpoint(project, body, "codex", self.receiver["session_id"])
        self.assertNotEqual(first["pointer"], second["pointer"])
        recap = handoff.recap(project)
        self.assertEqual(recap["snapshot"], "Second")
        self.assertEqual(len(recap["other_sessions"]), 1)
        self.assertTrue((project / ".tandem/handoff/INDEX.json").is_file())


if __name__ == "__main__":
    unittest.main()
