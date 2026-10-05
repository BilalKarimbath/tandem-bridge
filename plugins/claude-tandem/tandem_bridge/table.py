"""Compact presentation only: no discovery, state mutation or model calls."""
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from .directory import endpoint, stamp


def ascii_text(value):
    return ''.join(c if 32 <= ord(c) < 127 else '?' for c in str(value))


def clip(value, width):
    value = ascii_text(value)
    return value if len(value) <= width else value[:width - 1] + '~'


def elapsed(value, now):
    at = stamp(value)
    return max(0, (now - at).total_seconds()) if at else None


def age(value, now):
    seconds = elapsed(value, now)
    if seconds is None:
        return '-'
    if seconds < 60:
        return 'now'
    if seconds < 3600:
        return f'{int(seconds // 60)} min'
    if seconds < 86400:
        return f'{int(seconds // 3600)} h'
    return f'{int(seconds // 86400)} d'


def unique_prefixes(session_ids):
    """Shortest unique hexadecimal UUID prefix, with an eight-digit floor."""
    ids = sorted({session.replace('-', '') for session in session_ids})
    def common(a, b):
        return next((i for i, (left, right) in enumerate(zip(a, b)) if left != right), min(len(a), len(b)))
    result = {}
    for index, session in enumerate(ids):
        left = common(session, ids[index - 1]) if index else 0
        right = common(session, ids[index + 1]) if index + 1 < len(ids) else 0
        result[session] = session[:max(8, left + 1, right + 1)]
    return result


def short(key, prefixes):
    agent, session = key.split(':', 1)
    return agent + ' ' + prefixes[session.replace('-', '')]


def escape(value):
    """Readable code spans; exact labels remain in rows JSON.

    Backticks become typographic apostrophes in this presentation only. GFM
    requires escaped pipes even in code spans. Controls become spaces.
    """
    value = ''.join(c if c.isprintable() else ' ' for c in str(value))
    return '`' + value.replace('`', '\u2019').replace('|', '\\|') + '`'


def table(result, *, history=False, all_rows=False, no_color=False, tty=None, now=None,
          color='auto', internal=False, markdown=False):
    now = now or datetime.now(timezone.utc)
    color = not markdown and not no_color and (color == 'always' or (
        color == 'auto' and (sys.stdout.isatty() if tty is None else tty) and 'NO_COLOR' not in os.environ))
    lines = []
    md = ['| Pair | Session | Project | Status | Last seen | Model | Exchanges |',
          '| --- | --- | --- | --- | --- | --- | --- |']
    def mdrow(cells):
        md.append('| ' + ' | '.join(cells) + ' |')
    def emit(text, style=None):
        text = clip(text, 100)
        lines.append(f'\x1b[{style}m{text}\x1b[0m' if color and style else text)
    refreshed = stamp(result['refreshed_at'])
    clock = refreshed.astimezone(timezone.utc).strftime('%H:%M') if refreshed else '--:--'
    emit(f"tandem - sessions  refreshed {clock} UTC  {result['shown']} sessions / {len(result['links'])} pairs")
    ledger = ascii_text(result['state_dir'])
    emit('ledger ' + (ledger if len(ledger) <= 93 else '~' + ledger[-92:]))
    if result['shown'] != result['total']:
        emit(f"Filter: {result['shown']} of {result['total']} sessions; --all-projects clears the project filter", '2')
    by_key = {endpoint(r): r for r in result['rows']}
    prefixes = unique_prefixes([r['session_id'] for r in result['rows']] +
                               [key.split(':', 1)[1] for link in result['links'] for key in link['endpoints']])
    def brief(key):
        return short(key, prefixes)

    seen_pairs = {}
    def session(item, pair=None, exchange=''):
        state = item['status']
        if state.startswith('registry: '):
            state = state[len('registry: '):]
            if state == 'unobserved':
                state = '-'
        elif state.startswith('saved thread'):
            state = 'saved'
        elif state.startswith('historical endpoint'):
            state = 'history'
        else:
            state = 'hint'
        if item.get('role') in ('worker', 'relay'):
            state = item['role']
        name = item['name'] or ('(session gone)' if state == 'history' else '(unnamed)')
        model = item['model'] or '-'
        if item['effort']:
            model += ' / ' + item['effort']
        other = max(0, len(item['linked_to']) - 1)
        tail = f' +{other} pairs' if other else ''
        start = ('* ' if item['self_hint'] else '  ') + item['agent'].ljust(6) + ' '
        project = Path(item['project']).name if item['project'] else '-'
        key = endpoint(item)
        label = escape(item['name']) if item['name'] else ('*(session gone)*' if state == 'history' else '(unnamed)')
        label = ('\u2605 ' if item['self_hint'] else '') + item['agent'] + ' `' + prefixes[item['session_id'].replace('-', '')] + '` ' + label
        if pair and key in seen_pairs and seen_pairs[key] != pair:
            label += f' (also in pair {seen_pairs[key]})'
        if pair:
            seen_pairs.setdefault(key, pair)
        mdrow([f'**{pair}**' if exchange else '-', label, escape(project),
               escape('gone' if state == 'history' else state), age(item['last_seen'], now), escape(model), exchange])
        fixed = (start + clip(name, 22).ljust(22) + ' ' + clip(project, 14).ljust(14) + ' '
                 + clip(state, 9).ljust(9) + ' ' + age(item['last_seen'], now).ljust(6) + ' ')
        emit(fixed + clip(model, max(1, 100 - len(fixed) - len(tail))) + tail,
             '1;33' if item['self_hint'] else ('2' if state == 'history' else ('36' if item['agent'] == 'claude' else '33')))

    links = result['links']
    full = links if history else links[:3]
    for number, link in enumerate(full, 1):
        emit(f"PAIR  {brief(link['endpoints'][0])} <-> {brief(link['endpoints'][1])}"
             f"  {link['exchanges']} {'exchange' if link['exchanges'] == 1 else 'exchanges'} - last {age(link['latest_reply_at'], now)}", '1;32')
        for position, key in enumerate(link['endpoints']):
            exchange = f"**{link['exchanges']}** / {age(link['latest_reply_at'], now)}" if position == 0 else ''
            if key in by_key:
                session(by_key[key], number, exchange)
            else:
                emit('  ' + brief(key) + ' (outside project filter)', '2')
                mdrow([f'**{number}**' if position == 0 else '-', escape(brief(key)) + ' (outside project filter)', '', '', '', '', exchange])
    # Greedy deterministic clusters among remaining one-off pairs only. The first
    # three sections always remain fully visible; --history expands every pair.
    remaining = [] if history else list(links[3:])
    while remaining:
        first = remaining[0]
        clusters = []
        for key in first['endpoints']:
            at = stamp(first['latest_reply_at'])
            matches = [link for link in remaining if link['exchanges'] == 1 and key in link['endpoints']
                       and at and stamp(link['latest_reply_at'])
                       and abs((at - stamp(link['latest_reply_at'])).total_seconds()) < 86400]
            clusters.append((key, matches))
        key, matches = max(clusters, key=lambda x: len(x[1]))
        if first['exchanges'] == 1 and first in matches and len(matches) >= 2:
            emit(f"... {len(matches)} more pairs with {brief(key)}, 1 exchange each, last "
                 f"{age(first['latest_reply_at'], now)}  --history to expand", '2')
            mdrow(['...', f'{len(matches)} more one-off pairs with {escape(brief(key))}', '', '', '', '', '`--history`'])
            remaining = [link for link in remaining if link not in matches]
        else:
            emit(f"PAIR  {brief(first['endpoints'][0])} <-> {brief(first['endpoints'][1])}"
                 f"  {first['exchanges']} {'exchange' if first['exchanges'] == 1 else 'exchanges'}, last {age(first['latest_reply_at'], now)}  --history", '2')
            mdrow(['...', escape(' <-> '.join(brief(k) for k in first['endpoints'])), '', '', '', '',
                   f"**{first['exchanges']}** / {age(first['latest_reply_at'], now)}; `--history`"])
            remaining.pop(0)
    unlinked = [r for r in result['rows'] if not r['linked_to']]
    if unlinked:
        emit(f'NO KNOWN LINK  {len(unlinked)} sessions')
        auto, old, other = [], [], []
        for item in unlinked:
            since = elapsed(item['last_seen'], now)
            review = (item['model'] or '').startswith('codex-auto-review')
            is_internal = item.get('role') in ('worker', 'relay', 'auto-review') or review
            if is_internal and not internal:
                auto.append(item)
            elif is_internal or all_rows or item['agent'] != 'codex' or item['self_hint'] or (since is not None and since <= 86400):
                session(item)
            elif since is not None and since > 30 * 86400:
                old.append(item)
            else:
                other.append(item)
        if auto or old or other:
            # Disjoint categories prevent double counting. No ledger->project inference.
            labels = []
            if auto:
                counts = {}
                for item in auto:
                    role = item.get('role', 'auto-review')
                    if role == 'peer':
                        role = 'auto-review'
                    counts[role] = counts.get(role, 0) + 1
                label = ', '.join(f'{count} {role}' for role, count in sorted(counts.items()))
                emit(f'  {len(auto)} internal sessions folded: {label}  --internal to list', '2')
                mdrow(['-', f'{len(auto)} folded: {escape(label)}', '', '', '', '', '`--internal`'])
            if old:
                labels.append(f'{len(old)} codex threads older than 30 d')
            if other:
                projects = len({r['project'] for r in other if r['project']})
                labels.append(f'{len(other)} other codex threads ({projects} known projects)')
            for label in labels:
                emit('  ' + label + '  --all to list', '2')
                mdrow(['-', escape(label) + ' folded', '', '', '', '', '`--all`'])
    hint = sorted({r['self_hint'] for r in result['rows'] if r['self_hint']})
    emit('links = claimed round trips here; not authorization or liveness; refresh before sending', '2')
    emit('status: registry busy/idle; saved = consumer unknown; history = ledger only; * = ' + (','.join(hint) or 'self hint'), '2')
    emit('--rows full fields; --card <UUID>; --history / --all / --internal expand; model = last observed', '2')
    if any(r.get('ambiguous') for r in result['rows']):
        emit('Ambiguous identities present: inspect --rows; cards refuse ambiguous targets.', '2')
    for warning in result['issues']:
        emit('Source warning: ' + str(warning['status']) + ' (' + str(warning['source']) + ')', '2')
    if markdown:
        header = f"Sessions: {result['shown']} / {result['total']}; pairs: {len(links)}."
        if result['shown'] != result['total']:
            header += ' Filter: ' + escape(result.get('filter', 'project')) + '; `--all-projects` clears.'
        legend = [
            '', '| Word | Meaning |', '| --- | --- |',
            '| busy / idle | Claude registry-reported state; Last seen is the report age. Process presence is not checked. |',
            '| saved | Codex thread on disk; consumer unknown. A queued message may wait until a consumer runs. |',
            '| gone | Seen only in this ledger; registry/index absent. Process exit is not established. |',
            '| hint | Caller-supplied identity; no registry or index row confirms it. |',
            '| relay | Derived-name and checkout-cwd heuristic for a temporary Claude relay; not a peer-selection rule. |',
            '| worker | Rollout originator is codex_exec; last observed model/effort retained. |',
            '| auto-review | Last observed model has the codex-auto-review prefix. |',
            '| pair | Completed claimed round trip in this ledger; history, not authorization or liveness. |',
            '', '*Links describe past exchanges in ' + escape(result['state_dir']) + '; refresh before sending.*',
            '*Model/effort is last observed; roles and self stars are hints. Review paths and names before sharing.*']
        warnings = ['Source warning: ' + escape(w['status']) + ' (' + escape(w['source']) + ')' for w in result['issues']]
        return '\n'.join([header, ''] + md + legend + warnings)
    return '\n'.join(lines)
