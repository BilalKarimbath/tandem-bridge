import json
import io
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
import uuid

from tandem_bridge import tandem as t


def task(agent="claude"):
    return {"v": 1, "id": str(uuid.uuid4()), "kind": "task", "tag": "watch-test",
            "created_at": t.now(), "from": {"agent": "codex", "session_id": str(uuid.uuid4())},
            "to": {"agent": agent, "session_id": str(uuid.uuid4())}, "in_reply_to": None,
            "mode": "read-only", "scope": {"allowed": [], "protected": []},
            "done_when": ["Reply"], "mutation_key": None, "body": "Status?", "result": None}


class WatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = t.Ledger(self.root / "state")
        self.msg = task()
        registry = self.root / "sessions"
        registry.mkdir()
        (registry / "peer.json").write_text(json.dumps({
            "sessionId": self.msg["to"]["session_id"], "name": "peer"
        }), encoding="utf-8")

        self.args = SimpleNamespace(agent="claude", session=self.msg["to"]["session_id"],
                                    minutes=29, stop=False)

    def heartbeat_path(self):
        return self.ledger.root / "watch" / (self.args.session + ".json")

    def test_watch_refresh_stop_and_no_ledger_messages_or_events(self):
        first = t.watch(self.args, self.ledger)
        path = self.heartbeat_path()
        entry = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(first["state"], "watch_armed")
        self.assertEqual(set(entry), {"agent", "session_id", "until", "written_at"})
        self.assertEqual(entry["agent"], "claude")
        self.assertEqual(entry["session_id"], self.args.session)
        self.assertGreater(datetime.fromisoformat(entry["until"]), datetime.fromisoformat(entry["written_at"]))
        self.assertEqual(list((self.ledger.root / "messages").glob("*.json")), [])
        self.assertEqual(list((self.ledger.root / "events").glob("*/*.json")), [])
        self.assertEqual(len(list((self.ledger.root / "watch").glob("*.json"))), 1)
        self.args.minutes = 1
        second = t.watch(self.args, self.ledger)
        self.assertLess(datetime.fromisoformat(second["until"]), datetime.fromisoformat(first["until"]))
        self.args.stop = True
        self.assertEqual(t.watch(self.args, self.ledger)["state"], "watch_stopped")
        self.assertFalse(path.exists())
        self.assertFalse((self.ledger.root / "messages").exists())
        self.assertFalse((self.ledger.root / "events").exists())

    def test_watch_duration_and_identity_rejected(self):
        for minutes in (0, 31, float("nan")):
            self.args.minutes = minutes
            with self.assertRaises(ValueError):
                t.watch(self.args, self.ledger)
        self.args.minutes = 29
        self.args.session = "invalid"
        with self.assertRaises(ValueError):
            t.watch(self.args, self.ledger)
        self.assertFalse((self.ledger.root / "watch").exists())

    def test_fresh_watch_skips_relay_and_records_expected_event(self):
        t.watch(self.args, self.ledger)
        with patch.object(t.subprocess, "run") as runner:
            result = t.send(self.msg, self.ledger, "claude.exe", self.root, 1)
        runner.assert_not_called()
        self.assertEqual(result["state"], "written_for_watcher")
        self.assertIn("receipt is proven only by its claim", result["note"])
        self.assertTrue((self.ledger.root / "messages" / (self.msg["id"] + ".json")).is_file())
        self.assertEqual([e["state"] for e in self.ledger.events(self.msg["id"])], ["watch_delivery_expected"])
        self.assertEqual(t.summary(self.ledger)["tasks"][0]["state"], "dispatched_unclaimed")

    def relay(self, msg, **options):
        raw = json.dumps({"result": "TANDEM_RELAY_RESULT " + json.dumps(
            {"delivered": True, "message_id": str(uuid.uuid4())})})
        with patch.object(t, "recipient_name", return_value="peer"), patch.object(
                t.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, raw, "")) as runner:
            result = t.send(msg, self.ledger, "claude.exe", self.root, 1, **options)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(result["state"], "relay_reported_queued")

    def test_stale_missing_malformed_heartbeat_relay(self):
        self.relay(self.msg)
        for payload in (
            "{bad",
            json.dumps({"agent": "claude", "session_id": self.args.session, "until": "bad"}),
            json.dumps({"agent": "claude", "session_id": self.args.session,
                        "until": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()}),
            json.dumps({"agent": "claude", "session_id": self.args.session,
                        "until": (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()}),
        ):
            msg = task()
            msg["to"] = self.msg["to"]
            self.heartbeat_path().parent.mkdir(parents=True, exist_ok=True)
            self.heartbeat_path().write_text(payload, encoding="utf-8")
            self.relay(msg)

    def test_relay_never_and_always(self):
        t.watch(self.args, self.ledger)
        with patch.object(t.subprocess, "run") as runner:
            result = t.send(self.msg, self.ledger, "claude.exe", self.root, 1, relay="never")
        runner.assert_not_called()
        self.assertEqual(result["state"], "written_without_relay")
        self.assertEqual([e["state"] for e in self.ledger.events(self.msg["id"])], ["relay_skipped"])
        msg = task()
        self.relay(msg, relay="always")

    def test_codex_target_queues_despite_heartbeat_and_never(self):
        msg = task("codex")
        self.args.agent = "codex"
        self.args.session = msg["to"]["session_id"]
        t.watch(self.args, self.ledger)
        with patch.object(t.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, "queued", "")) as runner:
            result = t.send(msg, self.ledger, "codex.exe", self.root, 1, relay="never")
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(result["state"], "transport_returned")


    def test_skipped_relay_never_resolves_executable(self):
        t.watch(self.args, self.ledger)
        def denied():
            raise AssertionError("executable resolution must be skipped")
        with patch.object(t.subprocess, "run") as runner:
            result = t.send(self.msg, self.ledger, denied, self.root, 1)
        runner.assert_not_called()
        self.assertEqual(result["state"], "written_for_watcher")


    def test_source_cli_watch_and_auto_send_need_no_vendor_executable(self):
        import sys
        helper = Path(__file__).resolve().parents[1] / "tandem.py"
        base = [sys.executable, "-B", str(helper), "--state-dir", str(self.ledger.root)]
        armed = subprocess.run(base + ["watch", "--agent", "claude", "--session", self.args.session],
                               capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(armed.returncode, 0, armed.stderr)
        self.assertEqual(json.loads(armed.stdout)["state"], "watch_armed")
        envelope = self.root / "task.json"
        envelope.write_text(json.dumps(self.msg), encoding="utf-8")
        sent = subprocess.run(base + ["send", str(envelope), "--executable", str(self.root / "missing.exe"), "--claude-home", str(self.root)], capture_output=True,
                              text=True, encoding="utf-8")
        self.assertEqual(sent.returncode, 0, sent.stderr)
        self.assertEqual(json.loads(sent.stdout)["state"], "written_for_watcher")


    def test_fresh_heartbeat_without_registered_peer_relays(self):
        t.watch(self.args, self.ledger)
        (self.root / "sessions" / "peer.json").unlink()
        self.relay(self.msg)

    def write_message(self, msg):
        path = self.ledger.root / "messages" / (msg["id"] + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(msg), encoding="utf-8")

    def test_follow_backlog_exact_recipient_once_and_later_file(self):
        self.write_message(self.msg)
        outgoing = task()
        outgoing["from"], outgoing["to"] = self.msg["to"], self.msg["from"]
        self.write_message(outgoing)
        other = task()
        other["to"]["session_id"] = str(uuid.uuid4())
        self.write_message(other)
        claimed = task()
        claimed["to"] = self.msg["to"]
        self.write_message(claimed)
        (self.ledger.root / "claims" / claimed["id"]).mkdir(parents=True)
        later = task()
        later["to"] = self.msg["to"]
        lines = []
        ticks = [0]
        def sleep(_):
            ticks[0] += 1
            if ticks[0] == 2:
                self.write_message(later)
        args = SimpleNamespace(agent="claude", session=self.args.session, claude_home=str(self.root))
        t.follow_watch(args, self.ledger, emit=lines.append, sleep=sleep, clock=lambda: ticks[0],
                       parent_alive=lambda _pid: True, stopping=lambda: ticks[0] >= 4)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith(f'TANDEM_NEW {self.msg["id"]} task "watch-test" from codex '))
        self.assertIn(later["id"], lines[1])
        self.assertFalse(self.heartbeat_path().exists())

    def test_follow_renews_then_stops_when_parent_dies(self):
        ticks = [0]
        arms = []
        real_watch = t.watch
        def watch_spy(args, ledger):
            result = real_watch(args, ledger)
            if result["state"] == "watch_armed":
                arms.append(result["until"])
                self.assertTrue(self.heartbeat_path().exists())
            return result
        args = SimpleNamespace(agent="claude", session=self.args.session, claude_home=str(self.root))
        with patch.object(t, "watch", side_effect=watch_spy):
            t.follow_watch(args, self.ledger, emit=lambda _: None,
                           sleep=lambda _: ticks.__setitem__(0, ticks[0] + 1),
                           clock=lambda: ticks[0], parent_alive=lambda _pid: ticks[0] < 125)
        self.assertEqual(len(arms), 3)  # initial, 60 seconds, 120 seconds
        self.assertFalse(self.heartbeat_path().exists())

    def test_expired_follow_heartbeat_resumes_relay(self):
        args = SimpleNamespace(agent="claude", session=self.args.session, minutes=2, stop=False)
        t.watch(args, self.ledger)
        entry = json.loads(self.heartbeat_path().read_text(encoding="utf-8"))
        entry["until"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        self.heartbeat_path().write_text(json.dumps(entry), encoding="utf-8")
        self.relay(self.msg)

    def test_follow_warns_about_duplicate_live_windows(self):
        args = SimpleNamespace(agent="claude", session=self.args.session, claude_home=str(self.root))
        errors = io.StringIO()
        with patch("tandem_bridge.directory.duplicate_claude_pids", return_value=[123, 456]), redirect_stderr(errors):
            t.follow_watch(args, self.ledger, emit=lambda _: None,
                           parent_alive=lambda _pid: True, stopping=lambda: True)
        self.assertIn("multiple live windows (PIDs 123, 456)", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
