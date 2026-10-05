"""Standard-library validation for the keyword subset in Tandem's two schemas.

Not a general JSON Schema implementation. Unsupported schema keywords fail closed.
The published schemas remain the contract; development tests compare with jsonschema.
Errors describe declared fields and constraints, never the submitted content.
"""
from datetime import datetime
import math
import re
import uuid


class ValidationError(ValueError):
    pass


KEYWORDS = {'$schema', 'title', '$defs', '$ref', 'type', 'const', 'enum',
            'anyOf', 'properties', 'required', 'additionalProperties', 'items',
            'minItems', 'uniqueItems', 'minLength', 'maxLength', 'format', 'pattern'}
TYPES = {'object', 'array', 'string', 'null', 'boolean', 'number', 'integer'}
DATE_TIME = re.compile(
    r'(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})T'
    r'(?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})'
    r'(?:\.[0-9]+)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])', re.IGNORECASE)


def equal(a, b):
    # Python considers True == 1; JSON Schema does not.
    if isinstance(a, bool) or isinstance(b, bool):
        return type(a) is type(b) and a == b
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    return a == b


def check_schema(schema, root=None):
    """Reject unsupported contract changes even in an unused anyOf branch."""
    root = schema if root is None else root
    if not isinstance(schema, dict) or set(schema) - KEYWORDS:
        raise ValueError('Unsupported schema keyword or schema shape')
    types = schema.get('type', [])
    types = [types] if isinstance(types, str) else types
    if not isinstance(types, list) or any(t not in TYPES for t in types):
        raise ValueError('Unsupported schema type')
    if 'additionalProperties' in schema and schema['additionalProperties'] is not False:
        raise ValueError('Unsupported additionalProperties rule')
    if 'format' in schema and schema['format'] not in ('uuid', 'date-time'):
        raise ValueError('Unsupported schema format')
    if 'pattern' in schema and schema['pattern'] != '^[0-9a-f]{64}$':
        raise ValueError('Unsupported schema pattern')
    if '$ref' in schema:
        ref = schema['$ref']
        if not isinstance(ref, str) or not ref.startswith('#/$defs/') or ref[8:] not in root.get('$defs', {}):
            raise ValueError('Unsupported schema reference')
    for group in ('properties', '$defs'):
        for child in schema.get(group, {}).values():
            check_schema(child, root)
    for child in schema.get('anyOf', []):
        check_schema(child, root)
    if 'items' in schema:
        check_schema(schema['items'], root)


def matches_type(value, kind):
    return {
        'object': lambda: isinstance(value, dict),
        'array': lambda: isinstance(value, list),
        'string': lambda: isinstance(value, str),
        'null': lambda: value is None,
        'boolean': lambda: isinstance(value, bool),
        'number': lambda: type(value) in (int, float) and math.isfinite(value),
        'integer': lambda: type(value) in (int, float) and math.isfinite(value) and int(value) == value,
    }[kind]()


def validate(value, schema):
    check_schema(schema)

    def reject(path, reason):
        raise ValidationError(f'Invalid value at {path}: {reason}')

    def visit(item, rule, path):
        if '$ref' in rule:
            visit(item, schema['$defs'][rule['$ref'][8:]], path)
        if 'type' in rule:
            kinds = rule['type'] if isinstance(rule['type'], list) else [rule['type']]
            if not any(matches_type(item, kind) for kind in kinds):
                reject(path, 'wrong type')
        if 'const' in rule and not equal(item, rule['const']):
            reject(path, 'constant mismatch')
        if 'enum' in rule and not any(equal(item, candidate) for candidate in rule['enum']):
            reject(path, 'not an allowed enum value')
        if 'anyOf' in rule:
            for branch in rule['anyOf']:
                try:
                    visit(item, branch, path)
                    break
                except ValidationError:
                    pass
            else:
                reject(path, 'no allowed shape matched')
        if isinstance(item, dict):
            properties = rule.get('properties', {})
            if any(key not in item for key in rule.get('required', [])):
                reject(path, 'required field missing')
            if rule.get('additionalProperties') is False and set(item) - set(properties):
                reject(path, 'unknown field')
            for key, child in properties.items():
                if key in item:
                    visit(item[key], child, path + '.' + key)
        if isinstance(item, list):
            if len(item) < rule.get('minItems', 0):
                reject(path, 'too few items')
            if rule.get('uniqueItems') and any(equal(x, y) for i, x in enumerate(item) for y in item[:i]):
                reject(path, 'duplicate items')
            if 'items' in rule:
                for i, child in enumerate(item):
                    visit(child, rule['items'], f'{path}[{i}]')
        if isinstance(item, str):
            if 'pattern' in rule and re.fullmatch(rule['pattern'], item) is None:
                reject(path, 'pattern mismatch')
            if len(item) < rule.get('minLength', 0):
                reject(path, 'string too short')
            if 'maxLength' in rule and len(item) > rule['maxLength']:
                reject(path, f'maxLength exceeded (observed={len(item)}, limit={rule["maxLength"]})')
            if rule.get('format') == 'uuid':
                try:
                    uuid.UUID(item)
                    if any(item[i] != '-' for i in (8, 13, 18, 23)):
                        raise ValueError()
                except (ValueError, IndexError):
                    reject(path, 'invalid UUID format')
            if rule.get('format') == 'date-time':
                try:
                    match = DATE_TIME.fullmatch(item)
                    if not match:
                        raise ValueError()
                    # RFC3339 permits any fraction length; fromisoformat differs on Python 3.10.
                    datetime(**{key: int(value) for key, value in match.groupdict().items()})
                except ValueError:
                    reject(path, 'invalid RFC3339 date-time')

    visit(value, schema, '$')
    return value
