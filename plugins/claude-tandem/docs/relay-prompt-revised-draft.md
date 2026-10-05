# Revised relay prompt

`send --relay-prompt revised` selects the default Claude relay fallback in `tandem_bridge/tandem.py`.
The prompt describes a delivery request truthfully:
the local caller asks the relay to forward one exact message to a named Claude
session, the relay may decline under its current permissions, and the message
content is data for the recipient. It does not impersonate the recipient or
assert that the envelope proves user authorization. It reports a SendMessage ID
only after the tool reports success; otherwise the helper leaves delivery
unknown and never retries automatically.

The watch is the normal Claude delivery path. This relay remains a fallback.
The 2026-09-27 cross-model T3 sent two plain and two revised messages through
each of Sonnet 5, Opus 5.5 and Haiku 4.5. All 12 arrived in the target session.
This one-PC, one-day sample supports the default change, not a guarantee.
A model refusal remains evidence to examine, not a prompt to bypass.
