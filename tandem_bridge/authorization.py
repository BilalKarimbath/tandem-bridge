"""Read-only matching of declared intent. Never a runtime permission grant."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from importlib.resources import files
import os
from pathlib import Path
import uuid

from .validation import validate as validate_schema

SCHEMA_PATH = files("tandem_bridge").joinpath("SCHEMA-authorizations.json")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def local_path(value):
    """Existing local paths only: avoid speculative junction resolution."""
    path = Path(value)
    if not path.is_absolute() or str(value).startswith(("\\\\", "//")):
        raise ValueError("Policy paths must be absolute local paths, not UNC")
    resolved = path.resolve(strict=True)
    if str(resolved).startswith(("\\\\", "//")):
        raise ValueError("Resolved path must be local")
    # Windows alternate data streams and device aliases are not policy paths.
    if os.name == "nt" and ":" in str(resolved)[2:]:
        raise ValueError("Alternate data stream paths are not supported")
    return os.path.normcase(str(resolved))


def within(path, root):
    return Path(path).is_relative_to(Path(root))


def timestamp(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Expiry requires a timezone")
    return result


def endpoint(agent, session):
    if agent not in ("codex", "claude") or str(uuid.UUID(session)) != session:
        raise ValueError("Endpoint requires agent kind and canonical UUID")
    return {"agent": agent, "session_id": session}


def load_policy(path):
    raw = Path(path).read_bytes()
    policy = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_object)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validate_schema(policy, schema)
    seen = set()
    for grant in policy["grants"]:
        if grant["grant_id"] in seen:
            raise ValueError("Duplicate grant_id")
        seen.add(grant["grant_id"])
        for side in ("sender", "receiver"):
            endpoint(grant[side]["agent"], grant[side]["session_id"])
        timestamp(grant["expires"])
        for key in ("sender_project", "receiver_project", "ledger"):
            grant[key] = local_path(grant[key])
            if not Path(grant[key]).is_dir():
                raise ValueError(f"{key} must be a directory")
        for key in ("bookkeeping", "readable_scope", "exclusions"):
            grant[key] = [local_path(p) for p in grant[key]]
        if grant["ledger"] not in grant["bookkeeping"]:
            raise ValueError("Bookkeeping must explicitly include the exact ledger")
        roots = [grant["sender_project"], grant["receiver_project"]]
        if any(not any(within(p, r) for r in roots) for p in grant["readable_scope"]):
            raise ValueError("Readable scope must be inside a named project")
    return policy, hashlib.sha256(raw).hexdigest()


def add_parser(sub):
    parser = sub.add_parser("authorization", help=__doc__)
    actions = parser.add_subparsers(dest="authorization_action", required=True)
    for name in ("status", "template", "check"):
        child = actions.add_parser(name)
        child.add_argument("--policy-file", default=str(Path.home() / ".tandem/authorizations.json"))
        child.add_argument("--format", choices=["json", "text"], default="json")
        if name != "status":
            child.add_argument("--agent", choices=["codex", "claude"], required=True)
            child.add_argument("--session", required=True)
            child.add_argument("--project-root", required=True)
        if name == "check":
            child.add_argument("message")
            child.add_argument("--sender-project", required=True,
                               help="Caller-declared sender project, not authentication")
            child.add_argument("--purpose", choices=["status", "review"], required=True)
            child.add_argument("--read-path", action="append", default=[],
                               help="Actual planned inputs; every one must fit readable scope")
            child.add_argument("--bookkeeping-path", action="append", default=[])


def run(args, ledger, read_message):
    at = datetime.now(timezone.utc)
    base = {"policy_path": str(Path(args.policy_file).expanduser().resolve()),
            "evaluated_at": at.isoformat(), "semantic_scope_review_required": True,
            "runtime_approval_separate": True, "identity_authenticated": False}
    if args.authorization_action == "template":
        receiver = endpoint(args.agent, args.session)
        books = [str(ledger.root)]
        sibling_outbox = ledger.root.parent / "outbox"
        if sibling_outbox.is_dir():
            books.append(str(sibling_outbox.resolve()))
        return {**base, "state": "template", "policy": {"version": 1, "grants": []},
                "candidates": {"receiver": receiver, "receiver_project": local_path(args.project_root),
                    "ledger": str(ledger.root), "bookkeeping": books,
                    "expires": (at + timedelta(days=30)).isoformat()},
                "note": "No grant created. User must review sender, projects, scopes and expiry; see schema."}
    try:
        policy, digest = load_policy(base["policy_path"])
    except FileNotFoundError as error:
        # A missing path inside a present policy is invalid, not an absent policy.
        if Path(base["policy_path"]).exists():
            return {**base, "state": "invalid_policy", "reason": f"A declared policy path does not exist: {error.filename}"}
        if args.authorization_action == "status":
            return {**base, "state": "policy_status", "policy_present": False, "entry_count": 0,
                    "grants": [], "effective_writability": "unknown", "acl_owner": None}
        return {**base, "state": "needs_user_authorization", "reason": "Policy file missing"}
    except (ValueError, OSError) as error:
        return {**base, "state": "invalid_policy", "reason": str(error)}
    base.update(policy_sha256=digest)
    if args.authorization_action == "status":
        return {**base, "state": "policy_status", "policy_present": True, "entry_count": len(policy["grants"]),
                "effective_writability": "unknown", "acl_owner": None,
                "access_evidence": "No write probe or ACL query performed; location/ownership is not protection",
                "grants": [{**g, "expired": timestamp(g["expires"]) <= at,
                            "expires_within_7_days": at < timestamp(g["expires"]) <= at + timedelta(days=7)}
                           for g in policy["grants"]]}
    msg = read_message(args.message)
    receiver = endpoint(args.agent, args.session)
    project = local_path(args.project_root)
    sender_project = local_path(args.sender_project)
    reads = [local_path(p) for p in args.read_path]
    books = [local_path(p) for p in args.bookkeeping_path]
    ledger_path = local_path(str(ledger.root))
    base.update(envelope_id=msg["id"], sender=msg["from"], receiver=receiver,
                project=project, sender_project=sender_project, ledger=ledger_path,
                declared_purpose=args.purpose, read_paths=reads, bookkeeping_paths=books)
    if msg["to"] != receiver or msg["kind"] != "task" or msg["scope"]["allowed"]:
        return {**base, "state": "needs_user_authorization", "reason": "Wrong receiver, non-task or declared writes"}
    matches = []
    for g in policy["grants"]:
        if (g["sender"] != msg["from"] or g["receiver"] != receiver
                or g["sender_project"] != sender_project or g["receiver_project"] != project
                or g["ledger"] != ledger_path or msg["mode"] not in g["modes"]
                or args.purpose not in g["purposes"] or timestamp(g["expires"]) <= at):
            continue
        if any(not any(within(p, root) for root in g["readable_scope"])
               or any(within(p, x) for x in g["exclusions"]) for p in reads):
            continue
        if any(not any(within(p, root) for root in g["bookkeeping"]) for p in books):
            continue
        matches.append(g)
    if len(matches) != 1:
        return {**base, "state": "needs_user_authorization",
                "reason": "No covering grant" if not matches else "Ambiguous grants"}
    g = matches[0]
    return {**base, "state": "covered", "grant_id": g["grant_id"], "expires": g["expires"],
            "bookkeeping": g["bookkeeping"], "readable_scope": g["readable_scope"],
            "exclusions": g["exclusions"], "note": "Declared-policy match only; review actual task and runtime permissions"}
