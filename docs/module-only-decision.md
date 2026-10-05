# Module-only distribution

The user rejected a Tandem executable. Python is an existing prerequisite, not
bundled or installed by Tandem. The checkout runs with the selected interpreter:

```text
python tandem.py --state-dir <absolute-ledger> summary
python -m tandem_bridge --state-dir <absolute-ledger> summary
```

Use `python3` or `py -3` where that selects the intended Python. The module form
works from the checkout, or from another directory after optional wheel installation.
Do not use `-I` for the uninstalled checkout module: isolated mode removes the
current directory from imports. Wheel smoke uses `-I` only for an installed copy.
The root wrapper preserves legacy ledger fallback; the module requires an explicit,
environment, or project ledger. No migration is performed.

The package declares no runtime dependencies, console scripts or GUI scripts.
It contains readable Python and JSON schemas. Python itself and development tools
are separate software; this is not a claim that the user's machine has no binaries.
No standalone executable is distributed. The previously generated test launcher
is not part of the supported module-only path and is not rerun.

## Validation contract

`tandem_bridge.validation` implements only the schema keywords used in the two
published contracts. Unknown schema keywords and formats fail closed. The schemas
remain unchanged; domain checks (canonical UUIDs, endpoint matching, scope,
expiry, claim ownership) remain separate. No general-purpose JSON Schema support
is claimed. Validation errors omit submitted content.

`jsonschema` and its date-format checker are development-only oracles. Tests mutate
envelope and policy fields, missing/extra keys, types, constants, arrays, format
boundaries and length boundaries. Runtime tests run with site-packages disabled.

One intentional oracle difference: `rfc3339-validator==0.1.4` accepts a final newline
in a date-time because its regular expression uses `$`. Tandem requires the entire
string to match RFC3339 and rejects it; this difference is asserted explicitly.
Date checking now always runs. The prior jsonschema configuration could silently
omit date-format validation when its optional format dependency was absent.
Calendar fields are validated directly, preserving arbitrary fractional-second
precision without relying on version-dependent `datetime.fromisoformat` parsing.

The unchanged message body cap is 12,000 Unicode characters; the separate transport
limit is 22,000 UTF-16 units. A reported 20,604-byte reply failure is not enough
evidence to establish its character count or exact cause. It remains a separate
incident; the validator replacement naturally avoids echoing oversized content.

## Operational incident and limits

The user reported antivirus interference during executable creation and a system
freeze. Product, detection and cause are not independently established. No claim
of false positive, no exclusions and no security changes. The design change follows
the user's source-only preference; it is not a renamed/retried flagged launcher.

Windows source/module checks use the existing Python interpreter. Linux/macOS and
Python 3.10 require their own CI results; do not infer support from Windows tests.
No claim that module-only software cannot trigger antivirus. CLI availability and
permissions remain independent transport prerequisites.
