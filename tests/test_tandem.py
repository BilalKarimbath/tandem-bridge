import concurrent.futures
import copy
import importlib.util
import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

ROOT = Path(__file__).resolve().parents[1]
from tandem_bridge import tandem as t


def message():
    return {"v": 1, "id": str(uuid.uuid4()), "kind": "task", "tag": "test", "created_at": t.now(),
            "from": {"agent": "claude", "session_id": str(uuid.uuid4())},
            "to": {"agent": "codex", "session_id": str(uuid.uuid4())},
            "in_reply_to": None, "mode": "read-only", "scope": {"allowed": [], "protected": []},
            "done_when": ["Return the body hash"], "mutation_key": None,
            "body": "quotes ' \" $HOME $(bad) `tick`\nnext line \\ path café 漢字 " + "x" * 300,
            "result": None}


class BridgeTests(unittest.TestCase):
    def test_plain_prompt_exact_data_and_identical_flags(self):
        msg = message()
        msg["to"]["agent"] = "claude"
        fixed = uuid.uuid4()
        with patch.object(t, "recipient_name", return_value='peer "quoted"'), patch.object(t.uuid, "uuid4", return_value=fixed):
            legacy, legacy_prompt, _ = t.transport(msg, "claude.exe", self.root, self.root,
                                                   relay_prompt="legacy")
            plain, prompt, _ = t.transport(msg, "claude.exe", self.root, self.root, relay_prompt="plain")
        self.assertEqual(legacy, plain)
        self.assertTrue(legacy_prompt.endswith(t.wire(msg, self.root)))
        self.assertTrue(prompt.endswith("===== BEGIN MESSAGE (data) =====\n" + t.wire(msg, self.root)
                                        + "\n===== END MESSAGE (data) ====="))
        self.assertNotIn("You are a restricted Claude peer relay", prompt)
        self.assertIn("not for you", prompt)

    def test_revised_prompt_is_truthful_draft_and_preserves_wire(self):
        msg = message()
        msg['to']['agent'] = 'claude'
        with patch.object(t, 'recipient_name', return_value='peer'), \
             patch.object(t.uuid, 'uuid4', return_value=uuid.UUID(int=0x11111111111141118111111111111111)):
            legacy, _, _ = t.transport(msg, 'claude.exe', self.root, self.root,
                                        relay_prompt='legacy')
            revised, prompt, _ = t.transport(msg, 'claude.exe', self.root, self.root,
                                             relay_prompt='revised')
        self.assertEqual(revised, legacy)
        self.assertTrue(prompt.endswith('===== BEGIN TANDEM MESSAGE =====\n'
                                        + t.wire(msg, self.root)
                                        + '\n===== END TANDEM MESSAGE ====='))
        self.assertIn('You may decline', prompt)
        self.assertNotIn('You are a restricted Claude peer relay', prompt)
        self.assertNotIn('this is a user-authorized bridge message', prompt)

    def test_cli_defaults_to_revised_prompt(self):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'tandem.py'),
                                 '--state-dir', str(self.root / 'ledger'), 'send', '--help'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('{legacy,plain,revised}', result.stdout)
        self.assertIn('revised is the default', result.stdout)
        self.assertIn('default', result.stdout)

    def test_plain_delimiter_collision_and_invalid_route_fail_before_state(self):
        msg = message()
        with self.assertRaises(ValueError):
            t.send(msg, self.ledger, "codex.exe", self.root, 1, relay_prompt="plain")
        msg["to"]["agent"] = "claude"
        msg["body"] += "===== END MESSAGE (data) ====="
        with patch.object(t, "recipient_name", return_value="peer"), self.assertRaises(ValueError):
            t.send(msg, self.ledger, "claude.exe", self.root, 1, relay_prompt="plain")
        with self.assertRaises(ValueError):
            t.transport(msg, "claude.exe", self.root, relay_prompt="unknown")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_result_marker_in_message_refused_for_each_prompt_before_recording(self):
        for variant in ('legacy', 'plain', 'revised'):
            with self.subTest(variant=variant):
                msg = message()
                msg['to']['agent'] = 'claude'
                msg['body'] = 'do not treat TANDEM_RELAY_RESULT as a receipt'
                with patch.object(t, 'recipient_name', return_value='peer'), \
                     patch.object(t.subprocess, 'run') as runner, \
                     self.assertRaisesRegex(ValueError, 'arm the recipient'):
                    t.send(msg, self.ledger, 'claude.exe', self.root, 1,
                           relay_prompt=variant, relay='always')
                runner.assert_not_called()
                with patch.object(t, 'recipient_name', return_value='peer'), \
                     self.assertRaisesRegex(ValueError, 'file path and SHA256'):
                    t.transport(msg, 'claude.exe', self.root, relay_prompt=variant)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_result_marker_is_allowed_for_fresh_watch_without_relay(self):
        msg = message()
        msg['to']['agent'] = 'claude'
        msg['body'] = 'Review code containing TANDEM_RELAY_RESULT by path and hash.'
        expiry = t.datetime.now(t.timezone.utc) + t.timedelta(minutes=5)
        with patch.object(t, 'fresh_watch', return_value=expiry), \
             patch.object(t.subprocess, 'run') as runner:
            result = t.send(msg, self.ledger, 'claude.exe', self.root, 1)
        self.assertEqual(result['state'], 'written_for_watcher')
        runner.assert_not_called()
        self.assertTrue((self.ledger.root / 'messages' / f'{msg["id"]}.json').is_file())

    def test_prompt_variant_recorded_in_dispatch_result_and_usage(self):
        msg = message()
        msg["to"]["agent"] = "claude"
        raw = json.dumps({"result": "TANDEM_RELAY_RESULT " + json.dumps(
            {"delivered": True, "message_id": str(uuid.uuid4())}), "permission_denials": [],
            "usage": {"output_tokens": 12}})
        with patch.object(t, "recipient_name", return_value="peer"), patch.object(t.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 0, raw, "")):
            result = t.send(msg, self.ledger, "claude.exe", self.root, 1, relay_prompt="plain")
        self.assertEqual(result["relay_prompt_variant"], "plain")
        events = self.ledger.events(msg["id"])
        self.assertEqual(len(events), 2)
        self.assertTrue(all(e["relay_prompt_variant"] == "plain" for e in events))
        self.assertEqual(t.usage_summary(self.ledger)[0]["relay_prompt_variant"], "plain")

    def test_usage_missing_and_invalid_are_not_zero(self):
        self.assertIsNone(t.relay_usage("not json"))
        self.assertIsNone(t.relay_usage("[]"))
        report = t.relay_usage(json.dumps({"usage": {"input_tokens": True,
            "output_tokens": -1, "cache_read_input_tokens": 0}, "total_cost_usd": "0.01"}))
        self.assertIsNone(report["tokens_in"])
        self.assertIsNone(report["tokens_out"])
        self.assertIsNone(report["tokens_cache_create"])
        self.assertIsNone(report["cost_usd_list"])
        self.assertEqual(report["tokens_cached"], 0)

    def test_usage_extracts_actual_report_and_backfills_read_only(self):
        msg = message()
        raw = json.dumps({"usage": {"input_tokens": 34, "cache_read_input_tokens": 12830,
            "cache_creation_input_tokens": 3732, "output_tokens": 1675},
            "modelUsage": {"claude-fable-5-1": {}}, "total_cost_usd": 0.1619375,
            "duration_ms": 29488, "permission_denials": []})
        self.ledger.event(msg, "relay_reported_queued", relay_session_id=str(uuid.uuid4()),
                          transport_report={"stdout": raw})
        before = {p: p.read_bytes() for p in self.root.rglob("*.json")}
        rows = t.usage_summary(self.ledger)
        self.assertEqual(rows[0]["tokens_out"], 1675)
        self.assertEqual(rows[0]["models"], ["claude-fable-5-1"])
        self.assertEqual(rows[0]["cost_usd_list"], 0.1619375)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*.json")})

    def test_relay_options_preserve_safety_and_default(self):
        msg = message()
        msg["to"]["agent"] = "claude"
        with patch.object(t, "recipient_name", return_value="peer"):
            default, _, _ = t.transport(msg, "claude.exe", self.root)
            selected, _, _ = t.transport(msg, "claude.exe", self.root, relay_model="haiku")
            self.assertNotIn("--model", default)
            self.assertEqual(selected[selected.index("--model") + 1], "haiku")
            for flag in ["--safe-mode", "--strict-mcp-config", "--tools", "--allowedTools", "--permission-mode"]:
                self.assertIn(flag, selected)
            self.assertEqual(selected[selected.index("--tools") + 1], "SendMessage")
            self.assertEqual(selected[selected.index("--permission-mode") + 1], "dontAsk")
            dry = t.send(msg, self.ledger, "claude.exe", self.root, 1, True, "haiku", self.root)
            self.assertEqual(dry["cwd"], str(self.root.resolve()))
            self.assertEqual(list(self.root.iterdir()), [])

    def test_relay_options_rejected_for_codex_or_missing_cwd(self):
        msg = message()
        with self.assertRaises(ValueError):
            t.send(msg, self.ledger, "codex.exe", self.root, 1, relay_model="haiku")
        with self.assertRaises(ValueError):
            t.send(msg, self.ledger, "codex.exe", self.root, 1, relay_cwd=self.root)
        msg["to"]["agent"] = "claude"
        with patch.object(t, "recipient_name", return_value="peer"), self.assertRaises(ValueError):
            t.send(msg, self.ledger, "claude.exe", self.root, 1, relay_cwd=self.root / "missing")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_denial_stops_even_with_success_receipt_and_records_usage(self):
        msg = message()
        msg["to"]["agent"] = "claude"
        raw = json.dumps({"result": "TANDEM_RELAY_RESULT " + json.dumps(
            {"delivered": True, "message_id": str(uuid.uuid4())}),
            "usage": {"output_tokens": 10}, "permission_denials": [{"tool_name": "Bash"}]})
        with patch.object(t, "recipient_name", return_value="peer"), patch.object(t.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 0, raw, "")) as runner:
            result = t.send(msg, self.ledger, "claude.exe", self.root, 1, relay_cwd=self.root)
        self.assertEqual(result["state"], "delivery_unknown")
        self.assertEqual(result["relay_usage"]["tokens_out"], 10)
        self.assertEqual(runner.call_args.kwargs["cwd"], str(self.root.resolve()))
        self.assertIsNotNone(t.previous_relay_gap(self.ledger))

    def test_logged_out_relay_names_cause_without_claiming_nondelivery(self):
        msg = message()
        msg['to']['agent'] = 'claude'
        raw = json.dumps({'is_error': True, 'result': 'Not logged in · Please run /login'})
        with patch.object(t, 'recipient_name', return_value='peer'), patch.object(t.subprocess, 'run',
                return_value=subprocess.CompletedProcess([], 1, raw, '')):
            result = t.send(msg, self.ledger, 'claude.exe', self.root, 1)
        self.assertEqual(result['state'], 'delivery_unknown')
        self.assertEqual(result['cause'], 'claude_not_logged_in')
        self.assertIn('run /login', result['note'])
        self.assertTrue(any(e.get('cause') == 'claude_not_logged_in'
                            for e in self.ledger.events(msg['id'])))

    def test_end_turn_without_result_names_cause_and_transcript(self):
        msg = message()
        msg['to']['agent'] = 'claude'
        relay_id = uuid.uuid4()
        transcript = self.root / 'projects' / 'scratch' / f'{relay_id}.jsonl'
        transcript.parent.mkdir(parents=True)
        transcript.write_text('not inspected', encoding='utf-8')
        raw = json.dumps({'result': 'I declined to forward this request.',
                          'stop_reason': 'end_turn', 'permission_denials': []})
        self.assertEqual(t.relay_transcript(self.root, str(relay_id)), str(transcript))
        with patch.object(t, 'recipient_name', return_value='peer'), \
             patch.object(t, 'relay_transcript', return_value=str(transcript)), \
             patch.object(t.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, raw, '')):
            result = t.send(msg, self.ledger, 'claude.exe', self.root, 1)
        self.assertEqual(result['state'], 'delivery_unknown')
        self.assertEqual(result['cause'], 'relay_no_result')
        self.assertEqual(result['relay_transcript'], str(transcript))
        self.assertIn(str(transcript), result['note'])
        self.assertIn('do not resend', result['note'])
        self.assertTrue(any(e.get('cause') == 'relay_no_result'
                            for e in self.ledger.events(msg['id'])))

    def test_false_result_or_permission_denial_not_labeled_no_result(self):
        for report in ({'result': 'TANDEM_RELAY_RESULT {"delivered":false,"message_id":null}',
                        'stop_reason': 'end_turn', 'permission_denials': []},
                       {'result': 'declined', 'stop_reason': 'end_turn',
                        'permission_denials': [{'tool_name': 'SendMessage'}]}):
            with self.subTest(report=report):
                self.assertFalse(t.relay_no_result(json.dumps(report), t.relay_usage(json.dumps(report))))

    def test_unparseable_relay_result_names_cause_without_retry(self):
        msg = message()
        msg['to']['agent'] = 'claude'
        raw = json.dumps({'result': 'The send may have happened.\n\n'
                          'TANDEM_RELAY_RESULT {"delivered":true,"message_id":"bad"}',
                          'stop_reason': 'end_turn', 'permission_denials': []})
        with patch.object(t, 'recipient_name', return_value='peer'), \
             patch.object(t.subprocess, 'run',
                          return_value=subprocess.CompletedProcess([], 0, raw, '')) as runner:
            result = t.send(msg, self.ledger, 'claude.exe', self.root, 1)
        self.assertEqual(runner.call_count, 1)
        self.assertEqual(result['state'], 'delivery_unknown')
        self.assertEqual(result['cause'], 'relay_result_unparsed')
        self.assertIn('do not resend', result['note'])
        self.assertTrue(any(e.get('cause') == 'relay_result_unparsed'
                            for e in self.ledger.events(msg['id'])))
        valid = 'TANDEM_RELAY_RESULT ' + json.dumps({'delivered': True, 'message_id': str(uuid.UUID(int=0x11111111111141118111111111111111))}, separators=(',', ':'))
        self.assertIsNone(t.relay_result(json.dumps({'result': valid + '\nmore prose'})))
        self.assertTrue(t.relay_result_unparsed(json.dumps({'result': valid + '\nmore prose'})))

    def test_two_sanitized_opus_revised_t3_outputs_parse(self):
        # Captured T3 result shapes, with peer names and UUIDs replaced for the public test fixture.
        outputs = (
            'I forwarded the message word for word. It is queued in the other session.\n\n'
            'TANDEM_RELAY_RESULT ' + json.dumps({'delivered': True, 'message_id': str(uuid.UUID(int=0x11111111111141118111111111111111))}, separators=(',', ':')),
            'SendMessage succeeded: the message is in the queue at the peer session.\n\n'
            'TANDEM_RELAY_RESULT ' + json.dumps({'delivered': True, 'message_id': str(uuid.UUID(int=0x22222222222242228222222222222222))}, separators=(',', ':')),
        )
        for output in outputs:
            with self.subTest(output=output[:25]):
                raw = json.dumps({'result': output, 'stop_reason': 'end_turn', 'permission_denials': []})
                self.assertTrue(t.relay_result(raw)['delivered'])
                self.assertFalse(t.relay_result_unparsed(raw))
                msg = message()
                msg['to']['agent'] = 'claude'
                with patch.object(t, 'recipient_name', return_value='peer'), \
                     patch.object(t.subprocess, 'run',
                                  return_value=subprocess.CompletedProcess([], 0, raw, '')):
                    sent = t.send(msg, self.ledger, 'claude.exe', self.root, 1)
                self.assertEqual(sent['state'], 'relay_reported_queued')
                self.assertIsNone(sent['cause'])
        self.assertFalse(t.relay_result_unparsed('"ordinary JSON string"'))
        self.assertIsNone(t.relay_result(json.dumps({'result': '  '})))

    def test_summary_absent_ledger_is_read_only(self):
        missing = self.root / "absent"
        self.assertEqual(t.summary(t.Ledger(missing))["tasks"], [])
        self.assertFalse(missing.exists())

    def test_summary_completed_reply_requires_review_and_joins_task(self):
        msg = message()
        self.ledger.claim(msg, msg["to"])
        self.ledger.event(msg, "receiver_reported_blocked")
        self.assertEqual(t.summary(self.ledger)["tasks"][0]["state"], "blocked")
        self.ledger.event(msg, "receiver_reported_completed", reply_id=str(uuid.uuid4()))
        reply = copy.deepcopy(msg)
        reply.update(id=str(uuid.uuid4()), kind="reply", in_reply_to=msg["id"],
                     result={"status": "completed", "evidence_paths": [], "limitations": []})
        self.ledger.record(reply)
        rows = t.summary(self.ledger)["tasks"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["state"], "awaiting_review")
        args = t.argparse.Namespace(command="accept", id=msg["id"], agent=msg["from"]["agent"],
                                    session=msg["from"]["session_id"], evidence="Reviewed output against criteria")
        t.execute(args, self.ledger)
        self.assertEqual(t.summary(self.ledger)["tasks"][0]["state"], "review_accepted")
        with self.assertRaises(ValueError):
            t.execute(args, self.ledger)

    def test_accept_requires_completion_and_original_coordinator(self):
        msg = message()
        self.ledger.record(msg)
        args = t.argparse.Namespace(command="accept", id=msg["id"], agent=msg["from"]["agent"],
                                    session=msg["from"]["session_id"], evidence="checked")
        with self.assertRaises(ValueError):
            t.execute(args, self.ledger)
        self.ledger.event(msg, "receiver_reported_completed")
        args.session = str(uuid.uuid4())
        with self.assertRaises(ValueError):
            t.execute(args, self.ledger)

    def test_summary_reservations_unknown_and_claim_evidence(self):
        msg = message()
        self.ledger.record(msg)
        self.ledger.reserve("dispatch", msg["id"])
        self.assertEqual(t.summary(self.ledger)["tasks"][0]["state"], "dispatch_unresolved")
        self.ledger.event(msg, "delivery_unknown")
        self.assertEqual(t.summary(self.ledger)["tasks"][0]["state"], "delivery_unknown")
        self.ledger.reserve("claims", msg["id"])
        self.assertEqual(t.summary(self.ledger)["tasks"][0]["state"], "claim_incomplete")
        t.immutable_write(self.root / "claims" / msg["id"] / "claimed.json", {"receiver": msg["to"]})
        row = t.summary(self.ledger)["tasks"][0]
        self.assertEqual(row["state"], "claimed_without_result")
        self.assertTrue(row["delivery_unknown_recorded"])

    def test_summary_project_isolation_and_wrong_ledger(self):
        msg = message()
        self.ledger.record(msg)
        t.immutable_write(self.root / "events" / msg["id"] / "wrong.json",
                          {"at": t.now(), "state": "claimed", "state_dir": str(self.root / "other")})
        self.assertEqual(t.summary(self.ledger)["tasks"][0]["state"], "state_dir_mismatch")
        self.assertEqual(t.summary(t.Ledger(self.root / "other"))["tasks"], [])

    def test_coordinator_preserves_authored_sections_and_rejects_unmarked(self):
        project = self.root / "project"
        project.mkdir()
        result = t.coordinator_note(self.ledger, project, str(uuid.uuid4()))
        path = Path(result["path"])
        original = path.read_text(encoding="utf-8") + "\nA decision: café 漢字\n"
        path.write_text(original, encoding="utf-8")
        t.coordinator_note(self.ledger, project, str(uuid.uuid4()))
        self.assertEqual(path.read_text(encoding="utf-8").split("<!-- TANDEM STATUS END -->")[1],
                         original.split("<!-- TANDEM STATUS END -->")[1])
        path.write_text("User note without markers", encoding="utf-8")
        with self.assertRaises(ValueError):
            t.coordinator_note(self.ledger, project, str(uuid.uuid4()))
        self.assertEqual(path.read_text(encoding="utf-8"), "User note without markers")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.ledger = t.Ledger(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_schema_rejects_missing_identity_and_unscoped_edit(self):
        msg = message()
        t.validate(msg)
        del msg["from"]["session_id"]
        with self.assertRaises(t.ValidationError):
            t.validate(msg)
        msg = message()
        msg["mode"] = "edit-in-place"
        with self.assertRaises(ValueError):
            t.validate(msg)

    def test_immutable_publish_race_has_one_winner(self):
        path = self.root / "message.json"
        def publish(i):
            try:
                t.immutable_write(path, {"value": i})
                return i
            except FileExistsError:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(publish, range(16)))
        winners = [v for v in results if v is not None]
        self.assertEqual(len(winners), 1)
        self.assertEqual(json.loads(path.read_text())["value"], winners[0])

    def test_claim_race_has_one_winner(self):
        msg = message()
        def claim(_):
            try:
                self.ledger.claim(msg, msg["to"])
                return True
            except ValueError:
                return False
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(claim, range(16))), 1)

    def test_wrong_recipient_cannot_claim(self):
        msg = message()
        with self.assertRaises(ValueError):
            self.ledger.claim(msg, msg["from"])
        self.assertFalse((self.root / "claims").exists())

    def test_duplicate_mutation_blocked_across_message_ids(self):
        msg = message()
        msg.update(mode="additive-only", mutation_key="same-intended-edit")
        msg["scope"]["allowed"] = ["experiment/"]
        self.ledger.claim(msg, msg["to"])
        duplicate = copy.deepcopy(msg)
        duplicate["id"] = str(uuid.uuid4())
        with self.assertRaises(ValueError):
            self.ledger.claim(duplicate, duplicate["to"])
        self.assertFalse((self.root / "claims" / duplicate["id"]).exists())

    def test_changed_content_cannot_reuse_id(self):
        msg = message()
        self.ledger.record(msg)
        msg["body"] = "different"
        with self.assertRaises(ValueError):
            self.ledger.record(msg)

    def test_timeout_prevents_automatic_redispatch(self):
        msg = message()
        with patch.object(t.subprocess, "run", side_effect=subprocess.TimeoutExpired("codex", 1)) as runner:
            with self.assertRaises(ValueError):
                t.send(msg, self.ledger, "codex.exe", self.root, 1)
            with self.assertRaises(ValueError):
                t.send(msg, self.ledger, "codex.exe", self.root, 1)
            self.assertEqual(runner.call_count, 1)

    def test_real_process_preserves_queue_argument(self):
        msg = message()
        argv, stdin, relay = t.transport(msg, "codex.exe", self.root)
        self.assertIsNone(stdin)
        self.assertIsNone(relay)
        result = subprocess.run([sys.executable, "-c", "import json,sys; print(json.dumps(sys.argv[1:]))", *argv],
                                shell=False, capture_output=True, text=True, check=True)
        received = json.loads(result.stdout)
        self.assertEqual(received, argv)
        self.assertEqual(json.loads(received[-1].split("\n", 1)[1]), msg)

    def test_claude_discovery_and_stdin_prompt(self):
        msg = message()
        msg["to"]["agent"] = "claude"
        sessions = self.root / "sessions"
        sessions.mkdir()
        (sessions / "123.json").write_text(json.dumps({"sessionId": msg["to"]["session_id"], "name": "live-peer"}))
        argv, stdin, relay = t.transport(msg, "claude.exe", self.root,
                                          relay_prompt="legacy")
        self.assertNotIn(msg["body"], " ".join(argv))
        self.assertTrue(stdin.endswith(t.wire(msg)))
        self.assertIn(relay, argv)
        self.assertIn("live-peer", stdin)
        (sessions / "456.json").write_text(json.dumps({"sessionId": str(uuid.uuid4()), "name": "live-peer"}))
        with self.assertRaises(ValueError):
            t.transport(msg, "claude.exe", self.root)

    def test_dry_run_has_no_state_side_effects(self):
        msg = message()
        result = t.send(msg, self.ledger, "codex.exe", self.root, 1, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(list(self.root.iterdir()), [])

    def command(self, *args):
        with patch.object(sys, "argv", ["tandem.py", "--state-dir", str(self.root), *args]):
            return t.main()

    def make_from_body(self, body, out, tag="body-guard"):
        msg = message()
        return self.command("make", "--from-agent", msg["from"]["agent"],
                            "--from-session", msg["from"]["session_id"],
                            "--to-agent", msg["to"]["agent"],
                            "--to-session", msg["to"]["session_id"],
                            "--body-file", str(body), "--out", str(out),
                            "--tag", tag, "--done", "Return findings")

    def test_make_records_local_provenance_and_refuses_body_source_reuse(self):
        body = self.root / "task.txt"
        body.write_text("Review this file", encoding="utf-8")
        first = self.make_from_body(body, self.root / "first.json")
        saved = t.read_message(first["path"])
        provenance = self.root / "provenance" / (first["id"] + ".json")
        self.assertEqual(json.loads(provenance.read_text(encoding="utf-8")),
                         {"body_source_path": str(body.resolve()),
                          "body_sha256": t.body_hash("Review this file")})
        self.assertNotIn("body_source_path", saved)
        self.assertNotIn(str(body.resolve()), json.dumps(saved))
        with self.assertRaisesRegex(ValueError, first["id"]):
            self.make_from_body(body, self.root / "second.json")
        self.assertFalse((self.root / "second.json").exists())

    def test_reply_refuses_original_body_path_and_copy(self):
        body = self.root / "task.txt"
        body.write_text("Review this file", encoding="utf-8")
        first = self.make_from_body(body, self.root / "task.json")
        task = t.read_message(first["path"])
        self.command("receive", first["path"], "--agent", task["to"]["agent"],
                     "--session", task["to"]["session_id"])
        common = [first["path"], "--agent", task["to"]["agent"],
                  "--session", task["to"]["session_id"], "--status", "completed",
                  "--out", str(self.root / "reply.json")]
        body.write_text("My findings replaced the source", encoding="utf-8")
        copied = self.root / "copied.txt"
        copied.write_text("Review this file", encoding="utf-8")
        for source in (body, copied):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, "task's own body file"):
                self.command("reply", *common, "--body-file", str(source))
        self.assertFalse((self.root / "replies").exists())
        self.assertFalse((self.root / "reply.json").exists())

    def test_older_task_without_provenance_rejects_copied_body(self):
        task = message()
        source = self.root / "old.json"
        t.immutable_write(source, task)
        self.command("receive", str(source), "--agent", task["to"]["agent"],
                     "--session", task["to"]["session_id"])
        copied = self.root / "copy.txt"
        copied.write_text(task["body"], encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "task's own body file"):
            self.command("reply", str(source), "--agent", task["to"]["agent"],
                         "--session", task["to"]["session_id"], "--body-file", str(copied),
                         "--status", "completed", "--out", str(self.root / "reply.json"))

    def test_brief_status_distinguishes_no_reply_prepared_sent_and_claimed(self):
        task = message()
        self.ledger.event(task, "dispatch_started")
        self.ledger.claim(task, task["to"])
        body = self.root / "answer.txt"
        body.write_text("Findings", encoding="utf-8")
        source = self.root / "task.json"
        t.immutable_write(source, task)
        def brief():
            with patch.object(sys, "argv", ["tandem.py", "--state-dir", str(self.root),
                                           "status", task["id"], "--brief"]), patch("sys.stdout", new_callable=io.StringIO) as output:
                t.main()
                return output.getvalue().strip()
        self.assertIn("reply none", brief())
        prepared = self.command("reply", str(source), "--agent", task["to"]["agent"],
                                "--session", task["to"]["session_id"], "--body-file", str(body),
                                "--status", "completed", "--out", str(self.root / "reply.json"))
        self.assertIn(f'reply {prepared["id"][:8]} prepared', brief())
        reply = t.read_message(prepared["path"])
        self.ledger.event(reply, "dispatch_started")
        self.assertIn(f'reply {prepared["id"][:8]} sent', brief())
        self.ledger.claim(reply, reply["to"])
        self.assertIn(f'reply {prepared["id"][:8]} claimed', brief())
        self.assertIn("completed", brief())

    def test_reply_routes_back_and_updates_original_only_on_receipt(self):
        msg = message()
        source = self.root / "request.json"
        t.immutable_write(source, msg)
        body = self.root / "result.txt"
        body.write_text("Reviewed, no changes", encoding="utf-8")
        reply_path = self.root / "reply.json"
        common = [str(source), "--agent", msg["to"]["agent"], "--session", msg["to"]["session_id"]]
        with self.assertRaises(ValueError):
            self.command("reply", *common, "--body-file", str(body), "--out", str(reply_path), "--status", "completed")
        self.command("receive", *common)
        self.command("reply", *common, "--body-file", str(body), "--out", str(reply_path), "--status", "completed")
        reply = t.read_message(reply_path)
        self.assertEqual(reply["to"], msg["from"])
        self.assertEqual(reply["in_reply_to"], msg["id"])
        states = [e["state"] for e in self.command("status", msg["id"])["events"]]
        self.assertNotIn("receiver_reported_completed", states)
        self.command("receive", str(reply_path), "--agent", msg["from"]["agent"], "--session", msg["from"]["session_id"])
        states = [e["state"] for e in self.command("status", msg["id"])["events"]]
        self.assertIn("receiver_reported_completed", states)
        with self.assertRaises(ValueError):
            self.command("reply", str(reply_path), "--agent", reply["to"]["agent"], "--session", reply["to"]["session_id"],
                         "--body-file", str(body), "--out", str(self.root / "loop.json"), "--status", "completed")

    def test_mismatched_reply_does_not_claim_or_complete_original(self):
        msg = message()
        self.ledger.record(msg)
        reply = copy.deepcopy(msg)
        reply.update(id=str(uuid.uuid4()), kind="reply", in_reply_to=msg["id"],
                     result={"status": "completed", "evidence_paths": [], "limitations": []})
        reply["from"], reply["to"] = msg["to"], msg["from"]
        reply["tag"] = "wrong-task-tag"
        path = self.root / "wrong.json"
        t.immutable_write(path, reply)
        with self.assertRaises(ValueError):
            self.command("receive", str(path), "--agent", reply["to"]["agent"], "--session", reply["to"]["session_id"])
        self.assertFalse((self.root / "claims" / reply["id"]).exists())

    def test_relay_failure_is_not_success(self):
        good_id = str(uuid.uuid4())
        for response in ["Success!", 'TANDEM_RELAY_RESULT {"delivered":false,"message_id":null}',
                         'TANDEM_RELAY_RESULT {"delivered":true,"message_id":"invented"}']:
            self.assertIsNone(t.relay_result(json.dumps({"is_error": False, "result": response})))
        good = {"delivered": True, "message_id": good_id}
        self.assertEqual(t.relay_result(json.dumps({"result": "TANDEM_RELAY_RESULT " + json.dumps(good)})), good)

    def test_cli_outputs_utf8_under_cp1252_environment(self):
        msg = message()
        source = self.root / "unicode.json"
        t.immutable_write(source, msg)
        env = {**os.environ, "PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0"}
        result = subprocess.run([sys.executable, str(ROOT / "tandem.py"), "--state-dir", str(self.root),
                                 "receive", str(source), "--agent", msg["to"]["agent"],
                                 "--session", msg["to"]["session_id"]], env=env, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(report["state"], "claimed")
        self.assertEqual(report["body_sha256"], t.hashlib.sha256(msg["body"].encode()).hexdigest())

    def test_second_completed_reply_is_refused(self):
        msg = message()
        self.ledger.claim(msg, msg["to"])
        source = self.root / "request.json"
        t.immutable_write(source, msg)
        body = self.root / "body.txt"
        body.write_text("done")
        args = [str(source), "--agent", msg["to"]["agent"], "--session", msg["to"]["session_id"],
                "--body-file", str(body), "--status", "completed"]
        self.command("reply", *args, "--out", str(self.root / "first.json"))
        with self.assertRaises(ValueError):
            self.command("reply", *args, "--out", str(self.root / "second.json"))

    def test_changed_claimant_cannot_reply(self):
        msg = message()
        self.ledger.claim(msg, msg["to"])
        source = self.root / "request.json"
        t.immutable_write(source, msg)
        marker = self.root / "claims" / msg["id"] / "claimed.json"
        marker.write_text(json.dumps({"receiver": msg["from"]}))
        with self.assertRaises(ValueError):
            self.command("reply", str(source), "--agent", msg["to"]["agent"], "--session", msg["to"]["session_id"],
                         "--body-file", str(source), "--status", "completed", "--out", str(self.root / "bad.json"))

    def test_state_resolution_precedence_and_relative_paths(self):
        project = self.root / "project"
        child = project / "src"
        child.mkdir(parents=True)
        (project / ".git").mkdir()
        options = {"cwd": child, "environ": {"TANDEM_STATE_DIR": "environment"}, "helper_dir": self.root / "helper"}
        self.assertEqual(t.resolve_state_dir("explicit", **options), ((child / "explicit").resolve(), "flag"))
        self.assertEqual(t.resolve_state_dir(**options), ((child / "environment").resolve(), "environment"))
        options["environ"] = {}
        self.assertEqual(t.resolve_state_dir(**options), ((project / ".tandem/state").resolve(), "project"))
        (child / ".tandem").mkdir()
        self.assertEqual(t.resolve_state_dir(**options), ((child / ".tandem/state").resolve(), "project"))

    def test_worktree_git_file_is_project_marker(self):
        project = self.root / "worktree"
        project.mkdir()
        (project / ".git").write_text("gitdir: somewhere")
        self.assertEqual(t.resolve_state_dir(cwd=project, environ={}), ((project / ".tandem/state").resolve(), "project"))

    def test_home_configuration_is_not_a_project_marker(self):
        home = self.root / "home"
        config = home / ".tandem"
        config.mkdir(parents=True)
        (config / "authorizations.json").write_text("{}")
        bare = home / "Downloads" / "x"
        bare.mkdir(parents=True)
        project = home / "proj"
        (project / ".tandem").mkdir(parents=True)
        helper = self.root / "helper"
        with patch.object(t.Path, "home", return_value=home):
            self.assertEqual(t.resolve_state_dir(cwd=bare, environ={}, helper_dir=helper),
                             ((helper / "state").resolve(), "fallback"))
            with self.assertRaisesRegex(ValueError, "No project marker"):
                t.resolve_state_dir(cwd=bare, environ={})
            self.assertEqual(t.resolve_state_dir(cwd=project, environ={}),
                             ((project / ".tandem/state").resolve(), "project"))

    def test_fallback_warns_without_creating_or_migrating_state(self):
        # Anchor at the filesystem root so host/repo ancestors cannot affect the test.
        bare_root = Path(self.root.anchor)
        helper = self.root / "helper"
        with patch.object(t, "HERE", helper), patch.object(t.Path, "cwd", return_value=bare_root), \
             patch.dict(os.environ, {"TANDEM_STATE_DIR": ""}), patch.object(sys, "stderr", io.StringIO()) as err, \
             patch.object(sys, "argv", ["tandem.py", "discover", "--claude-home", str(self.root / "empty")]):
            result = t.main(legacy_helper_dir=helper)
        self.assertEqual(result["state_dir_source"], "fallback")
        self.assertEqual(result["state_dir"], str((helper / "state").resolve()))
        self.assertIn(result["state_dir"], err.getvalue())
        self.assertFalse(helper.exists())

    def test_recorded_ledger_mismatch_is_visible_and_blocks_claim(self):
        msg = message()
        self.ledger.event(msg, "dispatch_started")
        source_event = next((self.root / "events" / msg["id"]).glob("*.json"))
        recorded = json.loads(source_event.read_text())
        self.assertEqual(recorded["state_dir"], str(self.root.resolve()))
        recorded["state_dir"] = str(self.root / "different-ledger")
        source_event.write_text(json.dumps(recorded))
        status = self.command("status", msg["id"])
        self.assertEqual(status["state_dir_mismatches"], [recorded["state_dir"]])
        with self.assertRaisesRegex(ValueError, "State directory mismatch"):
            self.ledger.claim(msg, msg["to"])
        self.assertFalse((self.root / "claims").exists())

    def test_legacy_events_remain_usable(self):
        msg = message()
        event = {"id": msg["id"], "at": t.now(), "state": "dispatch_started"}
        t.immutable_write(self.root / "events" / msg["id"] / "old.json", event)
        self.ledger.claim(msg, msg["to"])
        status = self.command("status", msg["id"])
        self.assertEqual(status["legacy_events_without_state_dir"], 1)
        self.assertEqual(status["state_dir_mismatches"], [])
        self.assertEqual(json.loads((self.root / "events" / msg["id"] / "old.json").read_text()), event)

    def test_receive_rejects_message_from_another_ledger_before_writing(self):
        msg = message()
        other = self.root / "another-ledger" / "messages" / (msg["id"] + ".json")
        t.immutable_write(other, msg)
        with self.assertRaisesRegex(ValueError, "Message belongs to ledger"):
            self.command("receive", str(other), "--agent", msg["to"]["agent"], "--session", msg["to"]["session_id"])
        self.assertFalse((self.root / "claims").exists())

    def test_both_transports_preserve_ledger_header_and_envelope(self):
        msg = message()
        ledger = self.root / "a project" / ".tandem/state"
        argv, _, _ = t.transport(msg, "codex.exe", self.root, ledger)
        header, marker, body = argv[-1].split("\n", 2)
        self.assertEqual(json.loads(header.removeprefix("TANDEM_STATE_DIR ")), str(ledger.resolve()))
        self.assertEqual(marker, "TANDEM/1")
        self.assertEqual(json.loads(body), msg)
        msg["to"]["agent"] = "claude"
        (self.root / "sessions").mkdir()
        (self.root / "sessions/1.json").write_text(json.dumps({"name": "peer", "sessionId": msg["to"]["session_id"]}))
        _, prompt, _ = t.transport(msg, "claude.exe", self.root, ledger,
                                   relay_prompt="legacy")
        self.assertTrue(prompt.endswith(t.wire(msg, ledger)))
        self.assertIn("explicit --state-dir", prompt)


if __name__ == "__main__":
    unittest.main()
