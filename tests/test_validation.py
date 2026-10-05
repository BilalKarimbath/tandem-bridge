import copy
from datetime import datetime, timezone
from importlib.resources import files
import json
import uuid
import unittest

from tandem_bridge.validation import ValidationError, validate

try:
    import jsonschema
    import rfc3339_validator
except ImportError:
    jsonschema = None


UUID = str(uuid.UUID(int=0x12345678123442348234123456789abc))
ENVELOPE = {'v': 1, 'id': UUID, 'kind': 'task', 'tag': 'review',
    'created_at': '2026-09-22T12:00:00Z',
    'from': {'agent': 'codex', 'session_id': UUID},
    'to': {'agent': 'claude', 'session_id': UUID}, 'in_reply_to': None,
    'mode': 'read-only', 'scope': {'allowed': [], 'protected': []},
    'done_when': ['review'], 'mutation_key': None, 'body': 'hello', 'result': None}
GRANT = {'grant_id': 'one', 'sender': ENVELOPE['from'], 'receiver': ENVELOPE['to'],
    'sender_project': '/project', 'receiver_project': '/project', 'ledger': '/project/state',
    'bookkeeping': ['/project/state'], 'modes': ['read-only'], 'purposes': ['review'],
    'readable_scope': ['/project'], 'exclusions': [], 'expires': '2026-10-22T00:00:00Z',
    'enrolled_by': 'user', 'note': 'review only'}
POLICY = {'version': 1, 'grants': [GRANT]}
DATES = ['2026-09-22T12:00:00Z', '2024-02-29t00:00:00z', '2026-01-01T00:00:00.123456789+23:59',
    '2026-01-01T00:00:00-00:00', '0001-01-01T00:00:00Z', '9999-12-31T23:59:59Z',
    '2026-01-01T00:00:00.1Z', '2026-01-01T00:00:00.12345Z',
    '2025-02-29T00:00:00Z', '0000-01-01T00:00:00Z', '2026-01-01T24:00:00Z',
    '2026-01-01T00:60:00Z', '2026-01-01T00:00:60Z', '2026-01-01T00:00:00+24:00',
    '2026-01-01T00:00:00+00:60', '2026-01-01 00:00:00Z', '2026-01-01T00:00:00',
    '2026-01-01T00:00:00.Z', '2026-01-01T00:00:00Z\n', 'not a date']


def schema(name):
    return json.loads(files('tandem_bridge').joinpath(name).read_text(encoding='utf-8'))


def nodes(value, path=()):
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from nodes(child, (*path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from nodes(child, (*path, index))


def replace(value, path, replacement):
    result = copy.deepcopy(value)
    if not path:
        return replacement
    target = result
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    return result


def corpus(baseline):
    yield baseline
    for path, old in nodes(baseline):
        for replacement in [None, True, False, 0, 1, 1.0, 2, '', 'x', [], {}, [''], [1], ['review', 'review']]:
            yield replace(baseline, path, replacement)
        if isinstance(old, dict):
            for key in old:
                missing = copy.deepcopy(old)
                del missing[key]
                yield replace(baseline, path, missing)
            yield replace(baseline, path, {**old, 'unexpected': 'sensitive sentinel'})
        if isinstance(old, str):
            for candidate in [UUID, UUID.upper(), UUID.replace('-', ''), '{' + UUID + '}',
                              'urn:uuid:' + UUID, '🙂', *DATES]:
                yield replace(baseline, path, candidate)


class ValidationTests(unittest.TestCase):
    def test_body_boundary_and_non_content_error(self):
        contract = schema('SCHEMA.json')
        validate({**ENVELOPE, 'body': '🙂' * 12000}, contract)
        secret = 'private-content-' * 1000
        with self.assertRaises(ValidationError) as caught:
            validate({**ENVELOPE, 'body': secret}, contract)
        self.assertNotIn('private-content', str(caught.exception))
        self.assertIn('$.body', str(caught.exception))
        self.assertIn('limit=12000', str(caught.exception))

    def test_booleans_are_not_version_numbers(self):
        for filename, base, key in [('SCHEMA.json', ENVELOPE, 'v'),
                                    ('SCHEMA-authorizations.json', POLICY, 'version')]:
            validate({**base, key: 1.0}, schema(filename))
            with self.assertRaises(ValidationError):
                validate({**base, key: True}, schema(filename))

    def test_date_validation_is_always_available_without_optional_packages(self):
        contract = {'type': 'string', 'format': 'date-time'}
        for value in DATES[:8]:
            validate(value, contract)
        for value in DATES[8:]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate(value, contract)

    def test_unknown_contract_keywords_and_formats_fail_closed(self):
        for contract in [{'type': 'string', 'pattern': '.*'},
                         {'anyOf': [{'type': 'string'}, {'format': 'email'}]},
                         {'$ref': 'https://example.invalid/schema'}]:
            with self.assertRaises(ValueError):
                validate('anything', contract)

    def test_policy_uniqueness_and_reply_variants(self):
        contract = schema('SCHEMA-authorizations.json')
        for field in ('bookkeeping', 'readable_scope', 'exclusions', 'purposes'):
            value = 'review' if field == 'purposes' else '/project'
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validate({'version': 1, 'grants': [{**GRANT, field: [value, value]}]}, contract)
        for status in ('completed', 'blocked'):
            validate({**ENVELOPE, 'kind': 'reply', 'in_reply_to': UUID,
                      'result': {'status': status, 'evidence_paths': [], 'limitations': []}}, schema('SCHEMA.json'))


@unittest.skipIf(jsonschema is None, 'Install test-only requirements for the independent schema parity oracle')
class SchemaParityTests(unittest.TestCase):
    def test_mutated_corpus_matches_reference(self):
        checked = 0
        for filename, baseline in [('SCHEMA.json', ENVELOPE), ('SCHEMA-authorizations.json', POLICY),
            ('SCHEMA.json', {**ENVELOPE, 'kind': 'reply', 'in_reply_to': UUID,
                'result': {'status': 'blocked', 'evidence_paths': ['/evidence'], 'limitations': ['blocked']}})]:
            contract = schema(filename)
            checker = jsonschema.FormatChecker()
            # jsonschema silently ignores unavailable format implementations; ensure the oracle checks dates.
            self.assertFalse(checker.conforms('invalid', 'date-time'))
            reference = jsonschema.Draft202012Validator(contract, format_checker=checker)
            for index, candidate in enumerate(corpus(baseline)):
                try:
                    validate(candidate, contract)
                    actual = True
                except ValidationError:
                    actual = False
                expected = reference.is_valid(candidate)
                # rfc3339-validator 0.1.4 uses regex '$', which accepts a final newline.
                # Keep strict RFC3339 strings; this is the one documented oracle deviation.
                dates = ([candidate.get('created_at')] if isinstance(candidate, dict) and filename == 'SCHEMA.json'
                         else [g.get('expires') for g in candidate.get('grants', []) if isinstance(g, dict)]
                         if isinstance(candidate, dict) and isinstance(candidate.get('grants'), list) else [])
                if any(isinstance(d, str) and d.endswith('\n') for d in dates):
                    self.assertFalse(actual, (filename, index))
                    self.assertTrue(expected, (filename, index))
                else:
                    self.assertEqual(actual, expected, (filename, index))
                checked += 1
        self.assertGreater(checked, 2000)

    def test_length_boundaries_match_reference(self):
        contract = schema('SCHEMA.json')
        reference = jsonschema.Draft202012Validator(contract, format_checker=jsonschema.FormatChecker())
        for field, limit in [('tag', 100), ('mutation_key', 200), ('body', 12000)]:
            for n in (0, 1, limit - 1, limit, limit + 1):
                value = {**ENVELOPE, field: '🙂' * n}
                try:
                    validate(value, contract)
                    actual = True
                except ValidationError:
                    actual = False
                self.assertEqual(actual, reference.is_valid(value), (field, n))
