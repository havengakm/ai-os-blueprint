---
name: configure-trigify-monitors
description: Provision Trigify social-listening monitors for an AIOS client. Reads per-client YAML at context/{client-id}/sourcing/trigify_monitors.yaml, dry-runs the Trigify API, prompts for confirmation, provisions monitors. Persists search IDs to client_config.trigify_search_ids. Run ONCE at client onboarding, or when adding new competitors / thought leaders. Do NOT run on every pipeline cycle — monitors persist. Canonical AIOS skill at skills/playbooks/configure-trigify-monitors.md (this file delegates).
argument-hint: "<client-id> [--dry-run] [--no-confirm]"
allowed-tools: "Bash(uv run python scripts/configure_trigify_monitors.py:*) Read(context/**) Read(data/reference/sops/trigify-monitor-authoring.md)"
---

# Configure Trigify Monitors

Provisions Trigify monitors for a client by delegating to
`scripts/configure_trigify_monitors.py`. The Python CLI owns the argparse,
YAML parsing, dry-run/confirm flow, Trigify API calls and the Supabase
write. This skill is the operator-ergonomic entry point.

When the user invokes this skill:

1. Confirm the `client-id` with the user. Verify the YAML exists at
   `context/{client-id}/sourcing/trigify_monitors.yaml` via Read. If
   missing, point the user at `data/reference/sops/trigify-monitor-authoring.md`
   for the schema and stop — do NOT attempt to provision.

2. Run the dry-run first:

   ```
   uv run python scripts/configure_trigify_monitors.py --client-id=<client-id> --dry-run
   ```

   Report the preview (count + sample names per monitor type) to the user.

3. Ask the user to confirm. If confirmed, run the live command:

   ```
   uv run python scripts/configure_trigify_monitors.py --client-id=<client-id>
   ```

   The CLI will prompt `[y/N]` again for a second safety gate. Pass
   `--no-confirm` only when running under automation.

4. Summarise the output: N created, M skipped (idempotent), K failed. If
   any failed, surface the error details from stderr so the operator can
   fix the YAML or the API key and retry.

5. After success, verify by reading `client_config.trigify_search_ids`
   from Supabase to confirm the count matches
   `created + skipped_existing`.

## Failure modes

- YAML not found → pointer to the authoring SOP.
- YAML malformed → the CLI prints the offending section/index; fix and re-run.
- `TRIGIFY_API_KEY` unset → add to `.env`, then re-run.
- Individual monitor POSTs fail → CLI exits 1 and lists each failure.
  Idempotency means a retry only attempts the failed ones.
