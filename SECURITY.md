# Security

This is a research/evaluation prototype, not production software. See
the README's "MCP scope" and "Threat model" sections for what it does and
doesn't cover. Don't use it to protect a real system: it has no signing,
no authentication, and (per its own threat model) no defense against
compromise of its own trusted baseline.

If you find an actual security issue (it executes untrusted input, touches
the filesystem outside `fixtures/`/`results/`, or opens a network
connection, all of which are contrary to intent), open a GitHub issue.
