import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import uuid

from test_tandem import t, message

a = t.extension("authorization")
o = t.extension("opinions")


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / "alpha"
        self.project.mkdir()
        self.other = self.root / "alpha-other"
        self.other.mkdir()
        self.ledger = t.Ledger(self.project / "state")
        self.ledger.root.mkdir()
        self.msg = message()
        self.path = self.root / "message.json"
        self.path.write_text(json.dumps(self.msg), encoding="utf-8")
        self.policy = self.root / "policy.json"
        self.grant = {"grant_id": "example", "sender": self.msg["from"], "receiver": self.msg["to"],
            "sender_project": str(self.project), "receiver_project": str(self.project),
            "ledger": str(self.ledger.root), "bookkeeping": [str(self.ledger.root)],
            "modes": ["read-only"], "purposes": ["review"], "readable_scope": [str(self.project)],
            "exclusions": [], "expires": "2099-01-01T00:00:00+00:00"}
        self.args = SimpleNamespace(authorization_action="check", policy_file=str(self.policy),
            agent=self.msg["to"]["agent"], session=self.msg["to"]["session_id"],
            project_root=str(self.project), sender_project=str(self.project), message=str(self.path),
            purpose="review", read_path=[], bookkeeping_path=[])
        self.save()

    def save(self, grants=None):
        self.policy.write_text(json.dumps({"version": 1, "grants": grants if grants is not None else [self.grant]}), encoding="utf-8")

    def run_check(self):
        return a.run(self.args, self.ledger, t.read_message)

    def test_covered_has_semantic_boundary_and_no_writes(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = self.run_check()
        self.assertEqual(result["state"], "covered")
        self.assertTrue(result["semantic_scope_review_required"])
        self.assertTrue(result["runtime_approval_separate"])
        self.assertFalse(result["identity_authenticated"])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})

    def test_expiry_wrong_uuid_and_exact_ledger(self):
        for key, value in (("expires", "2000-01-01T00:00:00Z"),
                           ("receiver", {"agent": "codex", "session_id": str(uuid.uuid4())}),
                           ("ledger", str(self.project))):
            g = copy.deepcopy(self.grant)
            g[key] = value
            if key == "ledger":
                g["bookkeeping"].append(value)
            self.save([g])
            self.assertEqual(self.run_check()["state"], "needs_user_authorization", key)

    def test_malformed_unknown_duplicate_expiry_and_wildcard(self):
        for key, value in (("unknown", True), ("expires", "2099-01-01"),
                           ("receiver", {"agent": "codex", "session_id": "*"})):
            g = copy.deepcopy(self.grant)
            g[key] = value
            self.save([g])
            self.assertEqual(self.run_check()["state"], "invalid_policy", key)
        self.save([self.grant, self.grant])
        self.assertEqual(self.run_check()["state"], "invalid_policy")
        self.policy.write_text('{"version":1,"version":1,"grants":[]}', encoding="utf-8")
        self.assertEqual(self.run_check()["state"], "invalid_policy")

    def test_missing_policy_and_ambiguity(self):
        g = {**self.grant, "grant_id": "second"}
        self.save([self.grant, g])
        self.assertEqual(self.run_check()["reason"], "Ambiguous grants")
        self.policy.unlink()
        self.assertEqual(self.run_check()["state"], "needs_user_authorization")

    def test_read_scope_exclusions_and_bookkeeping_separate(self):
        self.args.read_path = [str(self.other)]
        self.assertEqual(self.run_check()["state"], "needs_user_authorization")
        self.args.read_path = [str(self.project)]
        self.grant["exclusions"] = [str(self.project)]
        self.save()
        self.assertEqual(self.run_check()["state"], "needs_user_authorization")
        self.args.read_path = []
        self.args.bookkeeping_path = [str(self.project)]
        self.assertEqual(self.run_check()["state"], "needs_user_authorization")

    def test_cross_project_requires_explicit_directed_grant(self):
        self.args.sender_project = str(self.other)
        self.assertEqual(self.run_check()["state"], "needs_user_authorization")
        self.grant["sender_project"] = str(self.other)
        self.save()
        self.assertEqual(self.run_check()["state"], "covered")

    def test_template_and_status_do_not_grant_or_probe_writes(self):
        (self.project / "outbox").mkdir()
        self.args.authorization_action = "template"
        result = self.run_check()
        self.assertEqual(result["policy"]["grants"], [])
        self.assertEqual(len(result["candidates"]["bookkeeping"]), 2)
        self.args.authorization_action = "status"
        self.assertEqual(self.run_check()["effective_writability"], "unknown")
        self.policy.unlink()
        self.assertEqual(self.run_check()["state"], "policy_status")
        self.assertFalse(self.run_check()["policy_present"])

    def test_relative_unc_and_mode_mismatch(self):
        for value in ("relative", "//server/share"):
            with self.assertRaises(ValueError):
                a.local_path(value)
        self.msg.update(mode="edit-in-place", mutation_key="test")
        self.msg["scope"]["allowed"] = [str(self.project)]
        self.path.write_text(json.dumps(self.msg), encoding="utf-8")
        self.assertEqual(self.run_check()["state"], "needs_user_authorization")

    def test_cli_exit_codes_and_template_is_json(self):
        cmd = [sys.executable, str(Path(__file__).resolve().parents[1] / "tandem.py"), "--state-dir", str(self.ledger.root),
               "authorization", "check", str(self.path), "--agent", self.args.agent,
               "--session", self.args.session, "--project-root", str(self.project),
               "--sender-project", str(self.project), "--purpose", "review", "--policy-file", str(self.policy)]
        for expiry, expected in (("2099-01-01T00:00:00Z", 0), ("2000-01-01T00:00:00Z", 2), ("bad", 1)):
            self.grant["expires"] = expiry
            self.save()
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(proc.returncode, expected, proc.stderr)
            json.loads(proc.stdout)


class OpinionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = t.Ledger(self.root / "state")
        self.args = SimpleNamespace(action="probe", model="claude-sonnet-5", question_file=None,
            context=[], agent="codex", session=str(uuid.uuid4()), out=str(self.root / "answer.txt"),
            effort=None, timeout=10, dry_run=False, executable="claude.exe", max_budget_usd=0.5)
        self.helper = SimpleNamespace(executable=lambda *args: "claude.exe", now=t.now,
            immutable_write=t.immutable_write, relay_usage=t.relay_usage)

    def stream(self, session, **changes):
        init = {"type": "system", "subtype": "init", "tools": [], "mcp_servers": [],
                "model": self.args.model, "session_id": session}
        result = {"type": "result", "subtype": "success", "is_error": False,
            "modelUsage": {self.args.model: {}}, "result": o.PROBE, "permission_denials": [],
            "session_id": session, "usage": {"input_tokens": 12, "output_tokens": 4}, "total_cost_usd": 0.01}
        init.update(changes.get("init", {}))
        result.update(changes.get("result", {}))
        return "\n".join(map(json.dumps, [init, result]))

    def fake_run(self, argv, **kwargs):
        if "--version" in argv:
            return subprocess.CompletedProcess(argv, 0, "2.1.278", "")
        self.assertEqual(argv[argv.index("--tools") + 1], "")
        self.assertIn("--safe-mode", argv)
        self.assertIn("--strict-mcp-config", argv)
        self.assertEqual(kwargs["shell"], False)
        self.assertTrue(Path(kwargs["cwd"]).is_dir())
        return subprocess.CompletedProcess(argv, 0, self.stream(argv[argv.index("--session-id") + 1]), "")

    def test_probe_success_and_normal_opinion_requires_it(self):
        with patch.object(o.subprocess, "run", side_effect=self.fake_run):
            result = o.run(self.args, self.ledger, self.helper)
            self.assertEqual(result["status"], "completed")
            self.assertEqual(Path(self.args.out).read_text(), o.PROBE)
            self.assertTrue(o.compatible_probe(self.ledger, self.args.model, "2.1.278"))
            self.assertFalse(o.compatible_probe(self.ledger, self.args.model, "different"))
            question = self.root / "question.txt"
            question.write_text("Review this design.")
            self.args.action, self.args.question_file, self.args.out = None, str(question), str(self.root / "normal.txt")
            self.assertEqual(o.run(self.args, self.ledger, self.helper)["status"], "completed")

    def test_runtime_missing_tools_models_denials_refusal_fail(self):
        for changes in ({"init": {"tools": ["Bash"]}}, {"init": {"tools": None}},
                        {"init": {"mcp_servers": [{}]}}, {"result": {"modelUsage": {"wrong": {}}}},
                        {"result": {"permission_denials": [{}]}}, {"result": {"result": "I refuse"}}):
            with self.assertRaises(ValueError):
                o.parse_stream(self.stream("id", **changes), self.args.model, True)

    def test_failed_probe_preserves_raw_without_answer(self):
        def failed(argv, **kwargs):
            proc = self.fake_run(argv, **kwargs)
            if "--version" not in argv:
                proc.stdout = self.stream(argv[argv.index("--session-id") + 1], init={"tools": ["Read"]})
            return proc
        with patch.object(o.subprocess, "run", side_effect=failed):
            result = o.run(self.args, self.ledger, self.helper)
        self.assertEqual(result["status"], "failed")
        self.assertFalse(Path(self.args.out).exists())
        self.assertTrue(Path(result["raw_report"]).is_file())
        self.assertEqual(result["usage"]["tokens_in"], 12)

    def test_codex_gate_blocks_without_any_subprocess(self):
        self.args.model = "gpt-5.6-luna"
        with patch.object(o.subprocess, "run") as run:
            result = o.run(self.args, self.ledger, self.helper)
            run.assert_not_called()
        self.assertTrue(result["not_probed"])
        self.assertFalse(Path(self.args.out).exists())

    def test_policy_key_is_bound_to_flags(self):
        self.assertTrue(o.POLICY.endswith(o.sha(json.dumps(o.FIXED_FLAGS, separators=(",", ":")).encode())))
        cmd = o.command("exe", "model", "session", .5)
        self.assertEqual(cmd[cmd.index("--safe-mode"):cmd.index("--max-budget-usd")], o.FIXED_FLAGS)

    def test_no_probe_blocks_normal_and_dry_run_creates_nothing(self):
        self.args.dry_run = True
        with patch.object(o.subprocess, "run", side_effect=self.fake_run):
            self.assertEqual(o.run(self.args, self.ledger, self.helper)["state"], "opinion_dry_run")
        self.assertFalse(self.ledger.root.exists())
        self.args.dry_run, self.args.action = False, None
        q = self.root / "q.txt"
        q.write_text("Question")
        self.args.question_file = str(q)
        with patch.object(o.subprocess, "run", side_effect=self.fake_run), self.assertRaises(ValueError):
            o.run(self.args, self.ledger, self.helper)
        self.assertFalse(self.ledger.root.exists())

    def test_size_overwrite_and_effort_rejection(self):
        q = self.root / "q.txt"
        q.write_text("x" * 22001)
        self.args.action, self.args.question_file = None, str(q)
        with self.assertRaises(ValueError):
            o.prepare(self.args)
        q.write_text("hello")
        self.args.context = [str(q)] * 3000
        with self.assertRaises(ValueError):
            o.prepare(self.args)
        self.args.context = []
        self.args.effort = "low"
        with patch.object(o.subprocess, "run") as run, self.assertRaises(ValueError):
            o.run(self.args, self.ledger, self.helper)
        run.assert_not_called()
        self.args.effort = None
        Path(self.args.out).write_text("keep")
        with self.assertRaises(ValueError):
            o.prepare(self.args)
        self.assertEqual(Path(self.args.out).read_text(), "keep")

    def test_timeout_retains_unknown_and_started(self):
        def timeout(argv, **kwargs):
            if "--version" in argv:
                return self.fake_run(argv, **kwargs)
            raise subprocess.TimeoutExpired(argv, 10, output=b'partial')
        with patch.object(o.subprocess, "run", side_effect=timeout):
            result = o.run(self.args, self.ledger, self.helper)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(o.records(self.ledger)[0]["status"], "unknown")
        self.assertFalse(Path(self.args.out).exists())

    def test_new_failed_probe_invalidates_success_and_incomplete_visible(self):
        with patch.object(o.subprocess, "run", side_effect=self.fake_run):
            result = o.run(self.args, self.ledger, self.helper)
        row = {**result, "id": str(uuid.uuid4()), "created_at": "2099-01-01T00:00:00Z", "status": "started"}
        t.immutable_write(self.ledger.root / "opinions" / (row["id"] + ".started.json"), row)
        self.assertFalse(o.compatible_probe(self.ledger, self.args.model, "2.1.278"))
        self.assertEqual(o.records(self.ledger)[-1]["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
