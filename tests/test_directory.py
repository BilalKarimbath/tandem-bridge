import json
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import uuid
from contextlib import redirect_stdout
from unittest.mock import patch

from tandem_bridge import directory as d, tandem as t


class DirectoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger = self.root / 'ledger'
        self.a, self.b, self.c = [str(uuid.uuid4()) for _ in range(3)]
        self.args = SimpleNamespace(claude_home=str(self.root / 'claude'), codex_home=str(self.root / 'codex'),
            session=None, agent=None, project_root=None, all_projects=False, card=None,
            purpose='review', legacy_helper_dir=self.root)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value), encoding='utf-8')

    def registry(self):
        self.write(self.root / 'claude/sessions/123.json', {'sessionId': self.b, 'name': 'peer',
            'cwd': str(self.root), 'status': 'idle', 'statusUpdatedAt': '2026-09-23T00:00:00Z',
            'messagingSocketPath': 'PRIVATE SOCKET', 'secret': 'PRIVATE SECRET'})
        (self.root / 'claude/sessions/123.key').write_text('PRIVATE KEY')

    def test_claude_whoami_resolves_only_ancestor_pid_registry(self):
        home = self.root / 'claude'
        self.write(home / 'sessions/300.json', {'pid': 300, 'sessionId': self.b,
            'name': 'peer', 'cwd': str(self.root), 'status': 'idle'})
        self.write(home / 'sessions/999.json', {'pid': 999, 'sessionId': self.c,
            'name': 'newer', 'cwd': str(self.root), 'status': 'idle'})
        parents = {700: 600, 600: 300, 300: 1}
        self.assertEqual(d.caller_claude_session(home, start_pid=700, get_parent=parents.get), self.b)
        with self.assertRaisesRegex(ValueError, 'Cannot resolve calling Claude session'):
            d.caller_claude_session(home, start_pid=800, get_parent={800: 1}.get)
        self.args.agent, self.args.whoami = 'claude', True
        with patch.object(d, 'caller_claude_session', return_value=self.b), patch.dict(os.environ, {'CODEX_THREAD_ID': self.a}):
            result = d.discover(self.args, self.ledger)
        self.assertIn(f'Session ID: {self.b}', d.whoami({**result, 'state_dir': str(self.ledger)}))
        self.assertNotIn(f'Session ID: {self.a}', d.whoami({**result, 'state_dir': str(self.ledger)}))

    def test_duplicate_live_claude_windows_warn_by_pid(self):
        home = self.root / 'claude'
        for pid in (300, 301, 999):
            self.write(home / 'sessions' / f'{pid}.json',
                       {'pid': pid, 'sessionId': self.b if pid != 999 else self.c,
                        'name': 'same', 'cwd': str(self.root), 'status': 'idle'})
        self.assertEqual(d.duplicate_claude_pids(home, self.b, alive=lambda pid: pid != 301), [])
        self.assertEqual(d.duplicate_claude_pids(home, self.b, alive=lambda pid: True), [300, 301])
        self.args.agent, self.args.session, self.args.whoami = 'claude', self.b, True
        with patch.object(d, 'process_alive', side_effect=lambda pid: pid in (300, 301)):
            result = d.discover(self.args, self.ledger)
        self.assertEqual(result['duplicate_claude_pids'], [300, 301])
        with self.assertRaisesRegex(ValueError, 'multiple live windows .*300, 301'):
            d.whoami({**result, 'state_dir': str(self.ledger)})

    def test_cli_whoami_uses_claude_config_dir(self):
        home = self.root / 'isolated-claude'
        self.write(home / 'sessions/300.json', {'pid': 300, 'sessionId': self.b,
                   'name': 'cold-test', 'cwd': str(self.root), 'status': 'idle'})
        argv = ['tandem.py', '--state-dir', str(self.ledger), 'discover', '--whoami', '--agent', 'claude']
        with patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': str(home),
                                    'CODEX_HOME': str(self.root / 'isolated-codex')}), \
             patch.object(d, 'caller_claude_session', return_value=self.b), \
             patch.object(sys, 'argv', argv), redirect_stdout(io.StringIO()) as output:
            t.main()
        self.assertIn('This Claude session is named cold-test.', output.getvalue())
        self.assertIn('Session ID: ' + self.b, output.getvalue())

    def codex(self, bad_tail=False):
        path = self.root / 'codex/session_index.jsonl'
        self.write(path, {'id': self.a, 'thread_name': 'worker', 'updated_at': '2026-09-23T00:00:00Z'})
        rollout = self.root / f'codex/sessions/2026/09/23/rollout-date-{self.a}.jsonl'
        rollout.parent.mkdir(parents=True)
        records = [
            {'type': 'session_meta', 'payload': {'id': self.a, 'cwd': str(self.root)}},
            {'type': 'turn_context', 'timestamp': '2026-09-22T00:00:00Z', 'payload': {'model': 'old', 'effort': 'low'}},
            {'type': 'response_item', 'payload': {'body': 'PRIVATE TRANSCRIPT'}},
            {'type': 'turn_context', 'timestamp': '2026-09-23T00:00:00Z', 'payload': {'model': 'observed', 'effort': 'high', 'extra': 'PRIVATE FIELD'}},
        ]
        rollout.write_text('\n'.join(json.dumps(x) for x in records) + ('\n{' if bad_tail else '\n'))
        (self.root / 'codex/history.jsonl').write_text('PRIVATE HISTORY')
        return rollout

    def roundtrip(self, a=None, b=None, completed=True):
        sender = {'agent': 'codex', 'session_id': a or self.a}
        receiver = {'agent': 'claude', 'session_id': b or self.b}
        task_id, reply_id = str(uuid.uuid4()), str(uuid.uuid4())
        task = {'id': task_id, 'kind': 'task', 'from': sender, 'to': receiver, 'tag': 'example',
                'body': 'PRIVATE BODY', 'created_at': '2026-09-23T00:00:00Z', 'in_reply_to': None}
        reply = {**task, 'id': reply_id, 'kind': 'reply', 'from': receiver, 'to': sender,
                 'in_reply_to': task_id, 'result': {'status': 'completed' if completed else 'blocked'}}
        for msg in (task, reply):
            self.write(self.ledger / 'messages' / (msg['id'] + '.json'), msg)
            self.write(self.ledger / 'claims' / msg['id'] / 'claimed.json', {'receiver': msg['to']})
        return task, reply

    def discover(self):
        with patch.dict(os.environ, {'CODEX_THREAD_ID': ''}):
            return d.discover(self.args, self.ledger)

    def test_whitelisted_metadata_last_turn_and_no_sensitive_file_open(self):
        self.registry()
        self.codex()
        original = Path.open
        opened = []
        def guarded(path, *args, **kwargs):
            opened.append(str(path))
            self.assertNotEqual(path.suffix, '.key')
            self.assertNotEqual(path.name, 'history.jsonl')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded):
            result = self.discover()
        encoded = json.dumps(result)
        self.assertNotIn('PRIVATE', encoded)
        codex = next(x for x in result['rows'] if x['agent'] == 'codex')
        self.assertEqual((codex['model'], codex['effort']), ('observed', 'high'))
        self.assertIn('consumer unknown', codex['status'])
        self.assertIsNone(next(x for x in result['rows'] if x['agent'] == 'claude')['model'])
        self.assertFalse(self.ledger.exists())

    def test_malformed_tail_and_bounded_scan_do_not_guess_model(self):
        path = self.codex(bad_tail=True)
        result = self.discover()
        self.assertIsNone(result['rows'][0]['model'])
        self.assertTrue(result['issues'])
        with path.open('a') as stream:
            stream.write('\n' + json.dumps({'type': 'response_item', 'payload': 'x' * (d.TAIL_BYTES + 1)}))
        self.assertIsNone(self.discover()['rows'][0]['model'])

    def test_registry_epoch_ms_and_long_fraction_timestamp(self):
        self.assertEqual(d.stamp(1790000600000).year, 2026)
        self.assertEqual(d.stamp('2026-09-22T13:28:06.9328298Z').microsecond, 932829)
        self.assertIsNone(d.stamp(True))

    def test_blank_tail_lines_keep_model_and_times_are_normalized(self):
        path = self.codex()
        with path.open('a') as stream:
            stream.write('\n  \n\n')
        item = self.discover()['rows'][0]
        self.assertEqual(item['model'], 'observed')
        self.assertEqual(item['model_as_of'], '2026-09-23T00:00:00+00:00')
        self.assertEqual(item['last_seen'], item['model_as_of'])
        path.unlink()
        self.assertEqual(self.discover()['rows'][0]['last_seen'], '2026-09-23T00:00:00+00:00')

    def test_recent_index_entry_gets_tail_budget_first(self):
        original = self.codex()
        other = original.with_name('rollout-date-' + self.c + '.jsonl')
        other.write_text(original.read_text().replace(self.a, self.c))
        index = self.root / 'codex/session_index.jsonl'
        with index.open('a') as stream:
            stream.write('\n' + json.dumps({'id': self.c, 'thread_name': 'newer', 'updated_at': '2026-09-24T00:00:00Z'}))
        calls = []
        real = d.rollout_metadata
        def inspect(path, session, issues, budget):
            calls.append(session)
            return real(path, session, issues, budget)
        with patch.object(d, 'rollout_metadata', inspect), patch.object(d, 'TAIL_BUDGET', other.stat().st_size):
            result = self.discover()
        self.assertEqual(calls[0], self.c)
        self.assertEqual(next(r for r in result['rows'] if r['session_id'] == self.c)['model'], 'observed')
        self.assertIsNone(next(r for r in result['rows'] if r['session_id'] == self.a)['model'])

    def test_rollout_only_is_in_inventory(self):
        self.codex()
        (self.root / 'codex/session_index.jsonl').unlink()
        result = self.discover()
        self.assertEqual(result['rows'][0]['session_id'], self.a)
        self.assertIsNone(result['rows'][0]['name'])
        self.assertEqual(result['rows'][0]['model'], 'observed')

    def test_total_tail_budget_is_enforced(self):
        path = self.codex()
        issues = []
        project, context, originator = d.rollout_metadata(path, self.a, issues, [0])
        self.assertEqual(project, str(self.root))
        self.assertIsNone(context)
        self.assertTrue(issues)

    def test_worker_role_is_from_metadata_not_name(self):
        path = self.codex()
        data = path.read_text().splitlines()
        meta = json.loads(data[0])
        meta['payload']['originator'] = 'codex_exec'
        data[0] = json.dumps(meta)
        path.write_text('\n'.join(data))
        item = self.discover()['rows'][0]
        self.assertEqual(item['role'], 'worker')
        self.assertIn('session_meta.originator', item['sources']['role'])
        self.assertEqual(item['model'], 'observed')

    def test_relay_heuristic_requires_derived_name_and_checkout(self):
        self.registry()
        path = self.root / 'claude/sessions/123.json'
        data = json.loads(path.read_text())
        data.update(name='bridge-05', nameSource='derived')
        self.write(path, data)
        item = self.discover()['rows'][0]
        self.assertEqual(item['role'], 'relay')
        self.assertIn('heuristic', item['sources']['role'])
        data['nameSource'] = 'user'
        self.write(path, data)
        self.assertEqual(self.discover()['rows'][0]['role'], 'peer')
        data.update(nameSource='derived', cwd=str(self.root / 'other'))
        self.write(path, data)
        self.assertEqual(self.discover()['rows'][0]['role'], 'peer')

    def test_self_project_default_and_explicit_card_exception(self):
        self.registry()
        self.codex()
        path = self.root / 'claude/sessions/123.json'
        data = json.loads(path.read_text())
        data['cwd'] = str(self.root.parent / 'other-project')
        self.write(path, data)
        self.assertEqual(len(self.discover()['rows']), 2)
        self.args.session, self.args.agent = self.a, 'codex'
        result = self.discover()
        self.assertEqual(len(result['rows']), 1)
        self.assertEqual(result['total'], 2)
        self.args.all_projects = True
        self.assertEqual(len(self.discover()['rows']), 2)
        self.args.all_projects = False
        self.args.card = self.b
        self.assertEqual(self.discover()['card']['peer']['session_id'], self.b)

    def test_cli_markdown_and_color_flags(self):
        self.registry()
        result = subprocess.run([sys.executable, '-S', str(Path(t.__file__).parents[1] / 'tandem.py'),
            '--state-dir', str(self.ledger), 'discover', '--format', 'markdown', '--color', 'always',
            '--internal', '--all', '--all-projects', '--claude-home', self.args.claude_home,
            '--codex-home', self.args.codex_home], capture_output=True, text=True, encoding='utf-8',
            env={**os.environ, 'CODEX_THREAD_ID': ''})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('| Pair | Session |', result.stdout)
        self.assertIn('| Word | Meaning |', result.stdout)
        self.assertNotIn('\x1b', result.stdout)
        self.assertFalse(self.ledger.exists())

    def test_link_requires_both_finalized_claims_and_correlation(self):
        task, reply = self.roundtrip()
        self.assertEqual(len(self.discover()['links']), 1)
        claim = self.ledger / 'claims' / reply['id'] / 'claimed.json'
        claim.unlink()
        self.assertEqual(self.discover()['links'], [])  # Directory alone is not a claim.
        self.write(claim, {'receiver': task['to']})
        self.assertEqual(self.discover()['links'], [])
        self.write(claim, {'receiver': reply['to']})
        reply['tag'] = 'wrong'
        self.write(self.ledger / 'messages' / (reply['id'] + '.json'), reply)
        self.assertEqual(self.discover()['links'], [])

    def test_blocked_is_not_completed_exchange(self):
        self.roundtrip(completed=False)
        self.assertEqual(self.discover()['links'], [])

    def test_pair_sections_do_not_imply_transitive_partnership(self):
        self.roundtrip()
        self.roundtrip(a=self.c)
        result = self.discover()
        self.assertEqual(len(result['links']), 2)
        a = next(r for r in result['rows'] if r['session_id'] == self.a)
        self.assertEqual(a['linked_to'], ['claude:' + self.b])
        self.assertNotIn('PRIVATE', json.dumps(result))
        result['state_dir'] = str(self.ledger)
        text = d.display(result)
        self.assertEqual(text.count('PAIR  '), 2)
        self.assertEqual(text.count('+1 pairs'), 2)
        self.assertNotIn('Observed peer group', text)

    def test_pairs_sort_by_latest_reply_then_stable_identity(self):
        _, older = self.roundtrip()
        _, newer = self.roundtrip(a=self.c)
        newer['created_at'] = '2026-09-24T00:00:00Z'
        self.write(self.ledger / 'messages' / (newer['id'] + '.json'), newer)
        links = self.discover()['links']
        self.assertIn('codex:' + self.c, links[0]['endpoints'])
        self.assertEqual(links[0]['pair_id'], '|'.join(sorted(links[0]['endpoints'])))

    def test_project_filter_does_not_relabel_peer_project(self):
        self.registry()
        self.args.project_root = str(self.root / 'different')
        result = self.discover()
        self.assertEqual((result['shown'], result['total']), (0, 1))
        self.args.all_projects = True
        self.assertEqual(self.discover()['rows'][0]['project'], str(self.root))

    def test_card_full_ids_and_explicit_hint_no_mutation(self):
        self.registry()
        self.args.session, self.args.agent, self.args.card = self.a, 'codex', self.b
        result = self.discover()
        result['state_dir'] = str(self.ledger)
        text = d.display(result)
        self.assertIn(self.a, text)
        self.assertIn(self.b, text)
        self.assertIn('authorizes nothing', text)
        self.assertEqual(result['card']['invocation_argv'], [sys.executable, str(self.root / 'tandem.py')])
        self.assertFalse(self.ledger.exists())

    def test_whoami_labels_session_name_and_fields(self):
        self.codex()
        self.args.session, self.args.agent = self.a, 'codex'
        result = self.discover()
        result['state_dir'] = str(self.ledger)
        self.assertEqual(d.whoami(result),
            f'This Codex session is named worker.\nSession ID: {self.a}\n'
            f'Project: {self.root.name}\nLedger: {self.ledger.as_posix()}\n'
            f'To connect another session, paste this into it: tandem: connect to codex {self.a} '
            f'on {self.root.name} (ledger {self.ledger.as_posix()})')
        self.write(self.root / 'codex/session_index.jsonl', {'id': self.a})
        result = self.discover()
        result['state_dir'] = str(self.ledger)
        self.assertTrue(d.whoami(result).startswith('This Codex session is named (unnamed).\n'))
        self.assertEqual(len(d.whoami(result).splitlines()), 5)

    def test_whoami_requires_recorded_project(self):
        self.args.session, self.args.agent = self.a, 'codex'
        result = self.discover()
        result['state_dir'] = str(self.ledger)
        with self.assertRaisesRegex(ValueError, 'Cannot resolve'):
            d.whoami(result)

    def test_whoami_explicit_claude_identity(self):
        self.registry()
        self.args.session, self.args.agent = self.b, 'claude'
        result = self.discover()
        result['state_dir'] = str(self.ledger)
        self.assertEqual(d.whoami(result),
            f'This Claude session is named peer.\nSession ID: {self.b}\n'
            f'Project: {self.root.name}\nLedger: {self.ledger.as_posix()}\n'
            f'To connect another session, paste this into it: tandem: connect to claude {self.b} '
            f'on {self.root.name} (ledger {self.ledger.as_posix()})')

    def test_whoami_cli_fields_or_one_error_line(self):
        self.codex()
        root = Path(__file__).resolve().parents[1]
        argv = [sys.executable, '-S', str(root / 'tandem.py'), '--state-dir', str(self.ledger),
                'discover', '--whoami', '--agent', 'codex', '--session', self.a,
                '--claude-home', self.args.claude_home, '--codex-home', self.args.codex_home]
        run = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8',
                             env={**os.environ, 'CODEX_THREAD_ID': ''})
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(run.stdout.splitlines()), 5)
        self.assertTrue(run.stdout.startswith('This Codex session is named worker.\nSession ID: '))
        argv[argv.index(self.a)] = self.c
        run = subprocess.run(argv, capture_output=True, text=True, encoding='utf-8',
                             env={**os.environ, 'CODEX_THREAD_ID': ''})
        self.assertEqual(run.returncode, 1)
        self.assertEqual(len(run.stderr.splitlines()), 1)

    def test_connect_fixed_hello_sends_once_and_refuses_absent_or_ambiguous(self):
        self.codex()
        self.registry()
        self.args.session, self.args.agent = self.a, 'codex'
        self.args.target, self.args.to_agent = self.b, None
        self.args.executable, self.args.timeout = None, None
        with patch.object(t, 'executable', return_value='claude'), patch.object(t, 'send') as send:
            send.side_effect = lambda msg, *unused, **options: {'id': msg['id'], 'state': 'relay_reported_queued'}
            result = t.connect(self.args, t.Ledger(self.ledger))
            self.assertEqual(result['peer_agent'], 'claude')
            self.assertEqual(result['peer_short'], self.b.replace('-', '')[:8])
            send.assert_called_once()
            msg = send.call_args.args[0]
            self.assertEqual(msg['mode'], 'read-only')
            self.assertEqual(msg['done_when'], ['Receiver replies with its ID and name, or declines'])
            self.assertEqual(msg['body'],
                f'Peer codex {self.a} (worker) in {self.root.name} asks to peer-program read-only through '
                f'{self.ledger.resolve()}. If you accept, reply with your ID and name. '
                'This is a hello, not a task; nothing else is requested.')
            self.assertRegex(msg['tag'], rf'^hello-{self.a[:8]}-[0-9]{{8}}$')
            self.assertTrue((self.root / 'outbox' / (msg['id'] + '.json')).is_file())
        self.assertFalse(self.ledger.exists())
        self.args.target = self.c
        with self.assertRaisesRegex(ValueError, 'candidates:'):
            t.connect(self.args, t.Ledger(self.ledger))
        self.args.target = self.b
        self.write(self.root / 'claude/sessions/124.json', {'sessionId': self.b, 'name': 'duplicate',
                   'cwd': str(self.root)})
        with self.assertRaisesRegex(ValueError, 'ambiguous'):
            t.connect(self.args, t.Ledger(self.ledger))

    def test_connect_cli_reports_one_line_with_transport_state(self):
        output = io.StringIO()
        argv = ['tandem.py', '--state-dir', str(self.ledger), 'connect', self.b]
        response = {'id': self.a, 'state': 'relay_reported_queued',
                    'peer_agent': 'claude', 'peer_short': self.b[:8]}
        with patch.object(sys, 'argv', argv), patch.object(t, 'connect', return_value=response), redirect_stdout(output):
            self.assertIsNone(t.main(legacy_helper_dir=self.root))
        self.assertEqual(output.getvalue().splitlines(),
            [f'Hello sent to claude {self.b[:8]} (envelope {self.a}). '
             'Waiting for it to accept. [state: relay_reported_queued]'])

    def test_connect_adds_only_sender_declared_image_capabilities_to_hello(self):
        self.codex()
        self.registry()
        self.args.session, self.args.agent = self.a, 'codex'
        self.args.target, self.args.to_agent = self.b, None
        self.args.executable, self.args.timeout = None, None
        self.args.capability = ['image-analysis', 'image-generation', 'image-analysis']
        with patch.object(t, 'executable', return_value='claude'), patch.object(t, 'send') as send:
            send.side_effect = lambda msg, *unused, **options: {'id': msg['id'], 'state': 'relay_reported_queued'}
            t.connect(self.args, t.Ledger(self.ledger))
        msg = send.call_args.args[0]
        self.assertEqual(send.call_args.kwargs['codex_home'], self.args.codex_home)
        self.assertEqual(msg['mode'], 'read-only')
        self.assertEqual(msg['scope'], {'allowed': [], 'protected': []})
        self.assertEqual(msg['done_when'], ['Receiver replies with its ID and name, or declines'])
        self.assertIn('Sender-reported capabilities available in this session: '
                      'image analysis, image generation. Confirm tool access before assigning image work.', msg['body'])
        self.assertEqual(msg['body'].count('image analysis'), 1)
        self.assertTrue(msg['body'].endswith('This is a hello, not a task; nothing else is requested.'))
        self.assertNotIn('capabilities', set(msg) - {'body'})

    def test_duplicate_registry_identity_refuses_card(self):
        self.registry()
        self.write(self.root / 'claude/sessions/124.json', {'sessionId': self.b})
        self.args.card = self.b
        with self.assertRaisesRegex(ValueError, 'unambiguous'):
            self.discover()

    def test_legacy_json_unchanged(self):
        self.registry()
        args = SimpleNamespace(command='discover', claude_home=self.args.claude_home)
        with patch.dict(os.environ, {'CODEX_THREAD_ID': self.a}):
            result = t.execute(args, t.Ledger(self.ledger))
        self.assertEqual(result, {'claude_registry_entries': t.discover_claude(self.args.claude_home),
            'codex_current_session': self.a,
            'note': 'Registry discovery is not a liveness guarantee; use codex agents for other Codex sessions.'})

    def test_real_cli_table_no_state_created(self):
        self.registry()
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, '-S', str(root / 'tandem.py'), '--state-dir', str(self.ledger),
            'discover', '--format', 'table', '--claude-home', self.args.claude_home, '--codex-home', self.args.codex_home],
            capture_output=True, text=True, encoding='utf-8', env={**os.environ, 'CODEX_THREAD_ID': ''})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('tandem - sessions', result.stdout)
        self.assertNotIn('PRIVATE', result.stdout)
        self.assertFalse(self.ledger.exists())
