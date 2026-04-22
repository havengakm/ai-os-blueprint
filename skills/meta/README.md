# Meta skills

Cross-cutting skills that operate on the output of other skills. They don't produce business artifacts; they gate them.

## Skills

- `validate-writing.md`: enforces `rules/global-writing-guardrails.md` against any written output. Invoked by every content-producing skill before output is returned.

## Principle

Meta skills are invisible in department manifests unless a department explicitly enables them. They should be universal by default: every deployment, every department, every content-producing skill routes through `validate-writing` on the way out.
