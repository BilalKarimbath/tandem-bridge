"""Read-only, bounded metadata discovery. Registry/index rows are not live agents."""
from datetime import datetime, timezone
from itertools import islice
import json
import os
import re
import ctypes
from pathlib import Path
import subprocess
import sys
import uuid

MAX_FILES = 10000
MAX_JSON = 128 * 1024
MAX_INDEX = 4 * 1024 * 1024
TAIL_BYTES = 2 * 1024 * 1024
TAIL_BUDGET = 64 * 1024 * 1024
TAIL_LINES = 2048
NOTICE = ('Links describe completed claimed exchanges in this ledger, not authorization or liveness. '
          'Refresh before sending. Review paths and names before sharing.')


def identity(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError('Noncanonical session/message UUID')
    return value


def endpoint(value):
    if not isinstance(value, dict) or value.get('agent') not in ('codex', 'claude'):
        raise ValueError('Invalid endpoint')
    return value['agent'] + ':' + identity(value.get('session_id'))


def stamp(value):
    if isinstance(value, int) and not isinstance(value, bool) and 10**12 <= value < 10**13:
        try:
            return datetime.fromtimestamp(value / 1000, timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    if not isinstance(value, str):
        return None
    try:
        # Normalize arbitrary fractional precision for Python 3.10 compatibility.
        value = re.sub(r'\.(\d+)', lambda m: '.' + (m[1] + '000000')[:6], value)
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result if result.tzinfo else None
    except ValueError:
        return None


def issue(issues, path, reason):
    issues.append({'source': str(path), 'status': reason})


def read_json(path, limit=MAX_JSON):
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('size limit exceeded')
    value = json.loads(raw.decode('utf-8-sig'))
    if not isinstance(value, dict):
        raise ValueError('expected object')
    return value


def paths(root, pattern, issues, recursive=False):
    try:
        if not root.exists():
            issue(issues, root, 'missing')
            return []
        iterator = root.rglob(pattern) if recursive else root.glob(pattern)
        found = list(islice(iterator, MAX_FILES + 1))
        if len(found) > MAX_FILES:
            issue(issues, root, 'file count limit reached; inventory incomplete')
        return sorted(found[:MAX_FILES])
    except OSError:
        issue(issues, root, 'unreadable')
        return []


def row(agent, session, source):
    identity(session)
    return {'agent': agent, 'session_id': session, 'name': None, 'project': None,
            'model': None, 'effort': None, 'last_seen': None, 'model_as_of': None,
            'status': 'unobserved', 'process_state': 'unknown', 'self_hint': None,
            'sources': {'identity': source, 'role': 'default; no internal-role evidence'},
            'role': 'peer', 'linked_to': []}


def parent_pid(pid):
    """Read one process parent without relying on folder/name identity."""
    if os.name == 'nt':
        command = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
                   f'(Get-CimInstance Win32_Process -Filter "ProcessId={pid}").ParentProcessId']
    else:
        command = ['ps', '-o', 'ppid=', '-p', str(pid)]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3, check=True)
        return int(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def process_alive(pid):
    """Check process existence without signalling or changing the process."""
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        handle = kernel.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied still means it exists
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def duplicate_claude_pids(home, session_id, *, alive=None):
    """Return distinct live registry PIDs sharing this exact Claude UUID."""
    alive = process_alive if alive is None else alive
    pids = set()
    for path in (Path(home) / 'sessions').glob('*.json'):
        try:
            data = read_json(path)
            pid = data.get('pid')
            if data.get('sessionId') == session_id and isinstance(pid, int) and pid > 0 and alive(pid):
                pids.add(pid)
        except (OSError, ValueError, TypeError):
            continue
    return sorted(pids) if len(pids) > 1 else []


def caller_claude_session(home, *, start_pid=None, get_parent=None):
    """Match the calling process's ancestors to Claude's PID-named registry."""
    pid = os.getppid() if start_pid is None else start_pid
    get_parent = parent_pid if get_parent is None else get_parent
    visited = set()
    for _ in range(64):
        if not isinstance(pid, int) or pid <= 1 or pid in visited:
            break
        visited.add(pid)
        path = Path(home) / 'sessions' / f'{pid}.json'
        if path.is_file():
            try:
                data = read_json(path)
                if str(data.get('pid', pid)) != str(pid):
                    raise ValueError('PID does not match registry filename')
                return identity(data.get('sessionId'))
            except (OSError, ValueError, TypeError) as exc:
                raise ValueError(f'Cannot resolve calling Claude session from {path}: {exc}') from exc
        pid = get_parent(pid)
    raise ValueError('Cannot resolve calling Claude session from parent PID registry; supply --session')


def claude_rows(home, issues, checkout=None):
    result = []
    for path in paths(Path(home) / 'sessions', '*.json', issues):
        try:
            data = read_json(path)
            item = row('claude', data.get('sessionId'), str(path))
            for dest, src in (('name', 'name'), ('project', 'cwd'), ('status', 'status'), ('kind', 'kind')):
                value = data.get(src)
                if isinstance(value, str):
                    item[dest] = value
                    item['sources'][dest] = f'{path}#{src}'
            item['last_seen'] = data.get('statusUpdatedAt') or data.get('updatedAt')
            if not stamp(item['last_seen']):
                item['last_seen'] = None
            else:
                item['last_seen'] = stamp(item['last_seen']).isoformat()
            item['sources']['last_seen'] = f'{path}#statusUpdatedAt|updatedAt'
            item['status'] = 'registry: ' + item['status']
            # This is a display heuristic, never identity or routing evidence.
            if (data.get('nameSource') == 'derived' and checkout and isinstance(data.get('cwd'), str)
                    and isinstance(data.get('name'), str)
                    and Path(data['cwd']).resolve() == Path(checkout).resolve()
                    and re.fullmatch(r'bridge-[0-9a-z]+', data.get('name', ''))):
                item['role'] = 'relay'
                item['sources']['role'] = f'{path}#nameSource+name+cwd (relay heuristic)'
            result.append(item)
        except (ValueError, OSError):
            issue(issues, path, 'unreadable, malformed or unsupported registry')
    return result


def rollout_metadata(path, session, issues, budget=None):
    with path.open('rb') as stream:
        first = stream.readline(MAX_JSON + 1)
        if len(first) > MAX_JSON:
            raise ValueError('metadata line exceeds limit')
        meta = json.loads(first)
        if meta.get('type') != 'session_meta' or (meta.get('payload', {}).get('id') or meta.get('payload', {}).get('session_id')) != session:
            raise ValueError('unknown rollout identity/format')
        stream.seek(0, 2)
        size = stream.tell()
        amount = min(size, TAIL_BYTES, budget[0] if budget is not None else TAIL_BYTES)
        if budget is not None:
            budget[0] -= amount
        start = size - amount
        stream.seek(start)
        tail = stream.read(amount)
    lines = tail.splitlines()
    if start:
        lines = lines[1:]  # Discard a potentially partial leading record.
    context = None
    for line in reversed(lines[-TAIL_LINES:]):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            if not isinstance(record, dict):
                raise ValueError('unknown record')
        except ValueError:
            issue(issues, path, 'malformed tail; latest model unknown')
            break
        if record.get('type') == 'turn_context':
            payload = record.get('payload')
            if isinstance(payload, dict):
                context = {k: payload.get(k) for k in ('model', 'effort')}
                context['at'] = record.get('timestamp')
            break
    if context is None:
        issue(issues, path, 'no usable turn context in bounded tail')
    # Other record payloads are discarded, never returned or displayed.
    payload = meta['payload']
    return payload.get('cwd'), context, payload.get('originator')


def codex_rows(home, issues):
    home = Path(home)
    index = home / 'session_index.jsonl'
    entries = {}
    try:
        with index.open('rb') as stream:
            raw = stream.read(MAX_INDEX + 1)
        if len(raw) > MAX_INDEX:
            raise ValueError('index size limit')
        for line in raw.splitlines():
            try:
                data = json.loads(line)
                session = identity(data.get('id'))
                entries[session] = {k: data.get(k) for k in ('thread_name', 'updated_at')}
            except (ValueError, AttributeError):
                issue(issues, index, 'malformed index record skipped')
    except (ValueError, OSError):
        issue(issues, index, 'unreadable, missing or over size limit')
    rollouts = {}
    for path in paths(home / 'sessions', 'rollout-*.jsonl', issues, recursive=True):
        session = path.stem[-36:]
        try:
            identity(session)
        except ValueError:
            issue(issues, path, 'unrecognized rollout filename')
            continue
        rollouts.setdefault(session, []).append(path)
        entries.setdefault(session, {'thread_name': None, 'updated_at': None, 'identity_source': str(path)})
    result = []
    budget = [TAIL_BUDGET]
    def recent(item):
        at = stamp(item[1]['updated_at'])
        return (at.timestamp() if at else float('-inf'), item[0])
    # Spend the bounded tail budget on recently indexed threads first; remaining
    # IDs descend (creation-order hint for v7), never a liveness assertion.
    for session, data in sorted(entries.items(), key=recent, reverse=True):
        item = row('codex', session, data.get('identity_source', str(index)))
        item.update(name=data['thread_name'] if isinstance(data['thread_name'], str) else None,
                    last_seen=stamp(data['updated_at']).isoformat() if stamp(data['updated_at']) else None,
                    status='saved thread; consumer unknown')
        if 'identity_source' not in data:
            item['sources'].update(name=f'{index}#thread_name', last_seen=f'{index}#updated_at')
        candidates = rollouts.get(session, [])
        if len(candidates) != 1:
            issue(issues, index, f'{session}: rollout missing or ambiguous')
        else:
            path = candidates[0]
            try:
                project, context, originator = rollout_metadata(path, session, issues, budget)
                item['project'] = project if isinstance(project, str) else None
                item['sources']['project'] = f'{path}#session_meta.cwd'
                if originator == 'codex_exec':
                    item['role'] = 'worker'
                    item['sources']['role'] = f'{path}#session_meta.originator'
                if context:
                    for key in ('model', 'effort'):
                        item[key] = context[key] if isinstance(context[key], str) else None
                        item['sources'][key] = f'{path}#last-observed-turn_context.{key}'
                    item['model_as_of'] = stamp(context['at']).isoformat() if stamp(context['at']) else None
                    if stamp(context['at']):
                        item['last_seen'] = stamp(context['at']).isoformat()
                        item['sources']['last_seen'] = f'{path}#turn_context.timestamp'
            except (ValueError, OSError, AttributeError, TypeError):
                issue(issues, path, 'unreadable, malformed or unsupported rollout')
        if (item['model'] or '').startswith('codex-auto-review'):
            item['role'] = 'auto-review'
            item['sources']['role'] = item['sources'].get('model', 'model') + ' (prefix)'
        result.append(item)
    return result


def observed_links(ledger, issues):
    """Parse bounded JSON, discard bodies, require finalized correlated claims."""
    messages = {}
    for path in paths(ledger / 'messages', '*.json', issues):
        try:
            data = read_json(path)
            mid = identity(data.get('id'))
            if path.name != mid + '.json':
                raise ValueError('message filename mismatch')
            endpoint(data.get('from'))
            endpoint(data.get('to'))
            messages[mid] = {k: data.get(k) for k in ('id', 'kind', 'from', 'to', 'tag', 'in_reply_to', 'created_at')}
            messages[mid]['status'] = data.get('result', {}).get('status') if isinstance(data.get('result'), dict) else None
        except (ValueError, OSError):
            issue(issues, path, 'unreadable or malformed ledger message')
    pairs = {}
    counted = set()
    for reply in messages.values():
        if reply['kind'] != 'reply' or reply['status'] != 'completed':
            continue
        task = messages.get(reply['in_reply_to']) if isinstance(reply['in_reply_to'], str) else None
        if not task or task['kind'] != 'task' or task['id'] in counted:
            continue
        if reply['from'] != task['to'] or reply['to'] != task['from'] or reply['tag'] != task['tag']:
            issue(issues, ledger, 'uncorrelated reply ignored')
            continue
        try:
            for msg in (task, reply):
                claim = read_json(ledger / 'claims' / msg['id'] / 'claimed.json')
                if claim.get('receiver') != msg['to']:
                    raise ValueError('claimant mismatch')
        except FileNotFoundError:
            continue
        except (ValueError, OSError):
            issue(issues, ledger, 'invalid or unreadable claim ignored')
            continue
        keys = tuple(sorted((endpoint(task['from']), endpoint(task['to']))))
        if keys[0] == keys[1]:
            continue
        counted.add(task['id'])
        link = pairs.setdefault(keys, {'endpoints': list(keys), 'exchanges': 0, 'latest_reply_at': None,
                                       'ledger': str(ledger), 'source': 'finalized claimed round trips'})
        link['exchanges'] += 1
        at = reply['created_at']
        if stamp(at) and (not link['latest_reply_at'] or stamp(at) > stamp(link['latest_reply_at'])):
            link['latest_reply_at'] = at
    return list(pairs.values())


def discover(args, ledger):
    issues = []
    rows = claude_rows(args.claude_home, issues, args.legacy_helper_dir or Path(__file__).resolve().parent.parent) + codex_rows(args.codex_home, issues)
    explicit = args.session
    claude_parent = args.agent == 'claude' and getattr(args, 'whoami', False) and not explicit
    if explicit:
        current = explicit
    elif claude_parent:
        current = caller_claude_session(args.claude_home)
    else:
        current = os.environ.get('CODEX_THREAD_ID')
    hint_source = 'user-supplied' if explicit else ('Claude ancestor PID' if claude_parent else 'CODEX_THREAD_ID')
    self_key = None
    if current:
        try:
            self_key = (args.agent if explicit or claude_parent else 'codex') + ':' + identity(current)
        except (ValueError, TypeError):
            issue(issues, 'self', 'invalid identity hint')
    if explicit and not args.agent:
        raise ValueError('--session requires --agent')
    mapped = {}
    for item in rows:
        key = endpoint(item)
        if key in mapped:
            issue(issues, key, 'duplicate identity; metadata ambiguous')
            mapped[key]['ambiguous'] = True
        else:
            mapped[key] = item
    if self_key and self_key not in mapped:
        agent, session = self_key.split(':', 1)
        mapped[self_key] = row(agent, session, hint_source)
        mapped[self_key]['status'] = 'identity hint only; registry/index absent'
    duplicate_pids = (duplicate_claude_pids(args.claude_home, current)
                      if self_key and self_key.startswith('claude:') and getattr(args, 'whoami', False) else [])
    links = observed_links(ledger, issues)
    adjacency = {}
    for link in links:
        a, b = link['endpoints']
        for key in (a, b):
            if key not in mapped:
                agent, session = key.split(':', 1)
                mapped[key] = row(agent, session, 'selected ledger')
                mapped[key]['status'] = 'historical endpoint; registry/index absent'
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    for key, peers in adjacency.items():
        mapped[key]['linked_to'] = sorted(peers)
    for link in links:
        link['pair_id'] = '|'.join(link['endpoints'])
    links.sort(key=lambda link: (-(stamp(link['latest_reply_at']).timestamp() if stamp(link['latest_reply_at']) else float('-inf')), link['pair_id']))
    rows = list(mapped.values())
    for item in rows:
        if endpoint(item) == self_key:
            item['self_hint'] = hint_source
    total = len(rows)
    self_row = mapped.get(self_key, {})
    project_root = args.project_root
    if not project_root and not self_row.get('ambiguous') and args.card is None:
        project_root = self_row.get('project')
    if project_root and not Path(project_root).is_absolute():
        project_root = None
    if project_root and not args.all_projects:
        root = Path(project_root).expanduser().resolve()
        def included(item):
            try:
                return bool(item['project']) and Path(item['project']).is_absolute() and Path(item['project']).resolve().is_relative_to(root)
            except (ValueError, OSError):
                return False
        rows = [r for r in rows if included(r)]
    rows.sort(key=lambda r: (not r['linked_to'], r['agent'], r['session_id']))
    visible = {endpoint(r) for r in rows}
    links = [link for link in links if any(key in visible for key in link['endpoints'])]
    result = {'rows_version': 1, 'rows': rows, 'links': links, 'issues': issues,
              'total': total, 'shown': len(rows), 'filter': str(project_root) if project_root and not args.all_projects else 'all discovered sessions; no age cutoff',
              'refreshed_at': datetime.now(timezone.utc).isoformat(), 'notice': NOTICE}
    if duplicate_pids:
        result['duplicate_claude_pids'] = duplicate_pids
    if args.card is not None:
        target = identity(args.card) if args.card else current
        candidates = [r for r in rows if r['session_id'] == target]
        if len(candidates) != 1 or candidates[0].get('ambiguous'):
            raise ValueError('Card requires one unambiguous discovered UUID; supply full --card UUID')
        result['card'] = {'peer': candidates[0], 'sender_hint': self_key, 'purpose': args.purpose,
                          'invocation_argv': ([sys.executable, str(Path(args.legacy_helper_dir) / 'tandem.py')]
                                              if args.legacy_helper_dir else [sys.executable, '-m', 'tandem_bridge']),
                          'ledger': str(ledger), 'note': 'No URL. Printing this card sends nothing and authorizes nothing.'}
    return result


def clean(value):
    text = 'unobserved' if value is None else str(value)
    return ''.join(c if c.isprintable() else '?' for c in text)


def whoami(result):
    """Render the caller's recorded identity without exposing a directory."""
    matches = [item for item in result['rows'] if item['self_hint']]
    if result.get('duplicate_claude_pids'):
        raise ValueError('Warning: this Claude session ID has multiple live windows (PIDs '
                         + ', '.join(map(str, result['duplicate_claude_pids']))
                         + '). Close one before coordinating.')
    if len(matches) != 1 or matches[0].get('ambiguous') or not matches[0].get('project'):
        raise ValueError('Cannot resolve this session and its project; '
                         'supply --agent and --session or inspect local metadata')
    item = matches[0]
    name = item['name'] or '(unnamed)'
    project = Path(item['project']).name
    ledger = Path(result['state_dir']).as_posix()
    if not project:
        raise ValueError('Cannot resolve this session project')
    def safe(value):
        # One physical field per line, even when registry labels contain controls or Markdown.
        return ''.join(c if c.isprintable() and c not in '<>`' else ' ' for c in str(value))
    return (f"This {item['agent'].capitalize()} session is named {safe(name)}.\n"
            f"Session ID: {item['session_id']}\nProject: {safe(project)}\nLedger: {safe(ledger)}\n"
            f"To connect another session, paste this into it: tandem: connect to {item['agent']} {item['session_id']} "
            f"on {safe(project)} (ledger {safe(ledger)})")


def display(result, *, history=False, all_rows=False, no_color=False, color='auto', internal=False, markdown=False):
    if 'card' not in result:
        from .table import table
        return table(result, history=history, all_rows=all_rows, no_color=no_color, color=color, internal=internal, markdown=markdown)
    lines = [f"Tandem sessions | ledger {clean(result['state_dir'])}",
             f"Showing {result['shown']} of {result['total']} | {clean(result['filter'])}"]
    if 'card' in result:
        card = result['card']
        peer = card['peer']
        lines += [f"From hint: {clean(card['sender_hint'])}", f"To: {peer['agent']} {peer['session_id']}",
                  f"Project: {clean(peer['project'])}", f"Status: {clean(peer['status'])}",
                  'Invocation argv: ' + json.dumps(card['invocation_argv']),
                  'Pass --state-dir ' + json.dumps(card['ledger']) + ' before each subcommand.',
                  'User authorization TEMPLATE (review and complete, do not send automatically):',
                  f"I authorize read-only {card['purpose']} exchanges with {peer['agent']} session {peer['session_id']} "
                  f"through ledger {clean(card['ledger'])}, limited to <named project and inputs>, including relevant findings returned to <sender UUID>.",
                  'Exclude credentials and unrelated project data; no project edits. Helper ledger/outbox bookkeeping only.',
                  'Templates: receive <envelope.json> --agent <receiver-kind> --session <receiver-UUID>',
                  'reply <task.json> --agent <receiver-kind> --session <receiver-UUID> --status completed --body-file <body> --out <new-reply.json>',
                  card['note']]
    lines += [NOTICE]
    for problem in result['issues']:
        lines.append('Source warning: ' + clean(problem['source']) + ': ' + clean(problem['status']))
    return '\n'.join(lines)
