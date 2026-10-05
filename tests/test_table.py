"""Presentation fixtures: folds account for every pair and every session."""
from copy import deepcopy
from datetime import datetime, timezone
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from tandem_bridge.table import table, escape, unique_prefixes

NOW = datetime(2026, 9, 23, 12, tzinfo=timezone.utc)


def fixture():
    rows = []
    for n in range(11):
        agent = 'claude' if n in (0, 7) else 'codex'
        rows.append(dict(agent=agent, session_id=f'{n:08x}-0000-4000-8000-000000000001',
                         name=f'peer-{n}', project='/work/alpha', model=None if agent == 'claude' else 'gpt-test',
                         effort=None if agent == 'claude' else 'low', last_seen='2026-09-23T11:55:00+00:00',
                         status='registry: idle' if agent == 'claude' else 'saved thread; consumer unknown',
                         self_hint='env' if n == 1 else None, linked_to=[]))
    links = []
    def key(n):
        return rows[n]['agent'] + ':' + rows[n]['session_id']
    for n in range(1, 7):
        links.append(dict(endpoints=[key(0), key(n)], exchanges=20 if n == 1 else 1,
                          latest_reply_at=f'2026-09-23T11:{60-n:02d}:00+00:00'))
        rows[0]['linked_to'].append(key(n))
        rows[n]['linked_to'].append(key(0))
    rows[8]['model'] = 'codex-auto-review-test'
    rows[9]['last_seen'] = '2026-07-01T00:00:00+00:00'
    rows[10]['last_seen'] = None
    return dict(rows=rows, links=links, issues=[], shown=11, total=11,
                refreshed_at=NOW.isoformat(), state_dir='/work/alpha/.tandem/state')


class TableTests(unittest.TestCase):
    def test_short_ids_expand_on_eight_hex_collision_everywhere(self):
        first = '01a0cd54-b5d9-' + '7170-b2c4-b724d1874c78'
        second = '01a0cd54-b62c-' + '7ac1-a525-61f9211fe634'
        prefixes = unique_prefixes([first, second])
        self.assertEqual(prefixes[first.replace('-', '')], '01a0cd54b5')
        self.assertEqual(prefixes[second.replace('-', '')], '01a0cd54b6')
        result = fixture()
        old = [result['rows'][1]['session_id'], result['rows'][2]['session_id']]
        for item, replacement in zip(result['rows'][1:3], (first, second)):
            item['session_id'] = replacement
        for link in result['links']:
            link['endpoints'] = [key.replace(old[0], first).replace(old[1], second)
                                 for key in link['endpoints']]
        markdown = table(result, now=NOW, markdown=True)
        terminal = table(result, now=NOW)
        self.assertIn('`01a0cd54b5`', markdown)
        self.assertIn('`01a0cd54b6`', markdown)
        self.assertIn('codex 01a0cd54b5', terminal)
        self.assertIn('codex 01a0cd54b6', terminal)

    def test_golden_and_disjoint_receipts(self):
        result = fixture()
        before = deepcopy(result)
        text = table(result, now=NOW, tty=False)
        expected = Path(__file__).with_name('fixtures').joinpath('directory-table.txt').read_text(encoding='ascii')
        self.assertEqual(text + '\n', expected)
        self.assertEqual(result, before)
        self.assertIn('3 more pairs', text)
        self.assertEqual(text.count('+5 pairs'), 3)
        self.assertNotIn('\x1b', text)
        self.assertTrue(all(len(line) <= 100 for line in text.splitlines()))
        self.assertTrue(text.isascii())
        self.assertNotIn('2026-', text)
        self.assertNotIn('-0000-4000-', text)

    def test_expansion_flags_are_independent(self):
        result = fixture()
        history = table(result, history=True, now=NOW, tty=False)
        self.assertEqual(history.count('PAIR  '), 6)
        self.assertNotIn('more pairs', history)
        self.assertIn('--all to list', history)
        expanded = table(result, all_rows=True, now=NOW, tty=False)
        self.assertIn('3 more pairs', expanded)
        self.assertNotIn('--all to list', expanded)
        self.assertIn('--internal to list', expanded)
        self.assertNotIn('peer-8', expanded)
        for n in (7, 9, 10):
            self.assertIn(f'peer-{n}', expanded)
        self.assertIn('peer-8', table(result, internal=True, now=NOW, tty=False))

    def test_color_requires_tty_and_no_opt_out(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIn('\x1b[', table(fixture(), now=NOW, tty=True))
            self.assertNotIn('\x1b[', table(fixture(), now=NOW, tty=False))
            self.assertNotIn('\x1b[', table(fixture(), now=NOW, tty=True, no_color=True))
        with patch.dict(os.environ, {'NO_COLOR': ''}):
            self.assertNotIn('\x1b[', table(fixture(), now=NOW, tty=True))

    def test_long_private_labels_are_bounded_and_escaped(self):
        result = fixture()
        result['state_dir'] = 'x' * 1000
        result['rows'][0]['name'] = '\x1b[31m' + 'long' * 30
        result['issues'] = [{'source': 'x' * 200, 'status': 'unreadable'}]
        text = table(result, now=NOW, tty=False)
        self.assertNotIn('\x1b', text)
        self.assertTrue(all(len(line) <= 100 for line in text.splitlines()))

    def test_ledger_path_preserves_distinguishing_tail(self):
        result = fixture()
        path = 'C:/GitHub/example/bridge/state'
        result['state_dir'] = path
        self.assertEqual(table(result, now=NOW, tty=False).splitlines()[1], 'ledger ' + path)
        result['state_dir'] = 'C:/' + 'parent/' * 30 + 'bridge/state'
        line = table(result, now=NOW, tty=False).splitlines()[1]
        self.assertTrue(line.startswith('ledger ~'))
        self.assertTrue(line.endswith('bridge/state'))
        self.assertEqual(len(line), 100)

    def test_markdown_golden_escape_and_legend(self):
        result = fixture()
        text = table(result, now=NOW, markdown=True, color='always', tty=True)
        expected = Path(__file__).with_name('fixtures').joinpath('directory-markdown.md').read_text(encoding='utf-8')
        self.assertEqual(text + '\n', expected)
        self.assertIn('\u2605 codex', text)
        self.assertIn('(also in pair 1)', text)
        self.assertIn('| Word | Meaning |', text)
        self.assertNotIn('\x1b', text)
        result['rows'][0]['name'] = '[click](https://bad) | <script> *fake* `code`'
        text = table(result, now=NOW, markdown=True)
        self.assertIn('`[click](https://bad) \\| <script> *fake* \u2019code\u2019`', text)
        self.assertNotIn('&#', text)
        self.assertEqual(escape('x_y|z'), '`x_y\\|z`')
        self.assertEqual(escape('a\nb'), '`a b`')
        for line in text.splitlines():
            if line.startswith('|') and not line.startswith('| Word') and '| Meaning' not in line:
                self.assertIn(line.replace('\\|', '').count('|'), (3, 8))

    def test_internal_overrides_only_internal_fold(self):
        result = fixture()
        result['rows'][7]['role'] = 'relay'
        result['rows'][10]['role'] = 'worker'
        text = table(result, now=NOW, all_rows=True)
        for n in (7, 8, 10):
            self.assertNotIn(f'peer-{n}', text)
        text = table(result, now=NOW, internal=True)
        for n in (7, 8, 10):
            self.assertIn(f'peer-{n}', text)
        self.assertIn('older than 30 d', text)

    def test_color_override_and_no_color_precedence(self):
        with patch.dict(os.environ, {'NO_COLOR': '1'}):
            self.assertIn('\x1b', table(fixture(), now=NOW, color='always', tty=False))
            self.assertNotIn('\x1b', table(fixture(), now=NOW, color='never', tty=True))
            self.assertNotIn('\x1b', table(fixture(), now=NOW, color='always', no_color=True, tty=True))
