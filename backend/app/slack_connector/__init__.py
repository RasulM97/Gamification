"""WS1 Slack connector: explicit structured People intake (Decision B).

Boundary: provider-specific verification/parsing lives here; resolved,
provider-agnostic actions call the existing Collaboration services unchanged.
Only explicit slash commands are supported — no inference, no scraping, no AI.
"""
