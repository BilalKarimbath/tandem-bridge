Sessions: 11 / 11; pairs: 6.

| Pair | Session | Project | Status | Last seen | Model | Exchanges |
| --- | --- | --- | --- | --- | --- | --- |
| **1** | claude `00000000` `peer-0` | `alpha` | `idle` | 5 min | `-` | **20** / 1 min |
| - | ★ codex `00000001` `peer-1` | `alpha` | `saved` | 5 min | `gpt-test / low` |  |
| **2** | claude `00000000` `peer-0` (also in pair 1) | `alpha` | `idle` | 5 min | `-` | **1** / 2 min |
| - | codex `00000002` `peer-2` | `alpha` | `saved` | 5 min | `gpt-test / low` |  |
| **3** | claude `00000000` `peer-0` (also in pair 1) | `alpha` | `idle` | 5 min | `-` | **1** / 3 min |
| - | codex `00000003` `peer-3` | `alpha` | `saved` | 5 min | `gpt-test / low` |  |
| ... | 3 more one-off pairs with `claude 00000000` |  |  |  |  | `--history` |
| - | claude `00000007` `peer-7` | `alpha` | `idle` | 5 min | `-` |  |
| - | 1 folded: `1 auto-review` |  |  |  |  | `--internal` |
| - | `1 codex threads older than 30 d` folded |  |  |  |  | `--all` |
| - | `1 other codex threads (1 known projects)` folded |  |  |  |  | `--all` |

| Word | Meaning |
| --- | --- |
| busy / idle | Claude registry-reported state; Last seen is the report age. Process presence is not checked. |
| saved | Codex thread on disk; consumer unknown. A queued message may wait until a consumer runs. |
| gone | Seen only in this ledger; registry/index absent. Process exit is not established. |
| hint | Caller-supplied identity; no registry or index row confirms it. |
| relay | Derived-name and checkout-cwd heuristic for a temporary Claude relay; not a peer-selection rule. |
| worker | Rollout originator is codex_exec; last observed model/effort retained. |
| auto-review | Last observed model has the codex-auto-review prefix. |
| pair | Completed claimed round trip in this ledger; history, not authorization or liveness. |

*Links describe past exchanges in `/work/alpha/.tandem/state`; refresh before sending.*
*Model/effort is last observed; roles and self stars are hints. Review paths and names before sharing.*
