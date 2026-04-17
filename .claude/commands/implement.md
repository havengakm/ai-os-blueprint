# Implementation Workflow

From plan to working system. Follow this every time.

## Pre-implementation checklist

- [ ] Plan exists and is approved (per `/create-plan`)
- [ ] Read ALL files that will be modified
- [ ] Understand existing patterns before changing anything
- [ ] Identified existing functions/utilities to reuse
- [ ] Dry-run flags prepared for anything that writes data or calls APIs

## Implementation order

Always build bottom-up:

1. **Schema first** — database migrations, new tables, new columns
2. **Foundation modules** — decision logger, pattern matcher, autonomy gates
3. **Integration points** — wire foundation into existing code
4. **System logic** — the actual feature/automation
5. **Tests** — verify it works
6. **Documentation** — update SOPs, READMEs

## Code rules

- Match existing patterns in the codebase
- Haiku for pipeline/batch scripts (cost: ~$0.0003/contact)
- Sonnet for agent runtime/conversations
- NEVER use Opus
- No API calls until prompt direction is confirmed by human
- Use `--limit 2` when API calls are needed to validate format
- `--dry-run` before any write to database or external system
- Never re-process data that's already been processed (check before acting)

## Safety rules

- Never commit `.env` or credentials
- `grep -r "sk-ant" .` before committing
- Never send outreach without verified buying signal + leverage match
- Never send before human review on a new deployment
- Three QA failures = flag for human review, do not retry
- Check `opted_out` status before every send, every channel
- Every outreach fact must exist in verified data (no hallucination)

## Commit workflow

1. Stage specific files (not `git add -A`)
2. Write descriptive commit message (what and why)
3. Include `Co-Authored-By` tag
4. Never amend previous commits unless explicitly asked
5. Never force push to main

## Post-implementation

1. Run tests and verify
2. Dry-run the full flow end-to-end
3. Log the implementation as a decision (per `/decide`)
4. Update context if architecture changed (per `/build-context`)
5. Update the plan file with completion status
6. Update client deployment SOP if this affects deployment steps
