---
name: validate-writing
description: Machine-check any written output against rules/global-writing-guardrails.md. Returns pass/fail with specific rule violations and a rewritten version. Invoked by every content-producing skill before its output is returned.
tier: capability
category: meta
tags: [meta, quality-gate, writing]
input: text (string), context (optional: "cold_email" | "blog" | "linkedin_post" | "generic")
output: {pass: bool, violations: [{rule, offending_text, suggested_fix}], rewrite: string}
requires_skills: []
requires_tools: []
references:
  - rules/global-writing-guardrails.md
when-to-use: Always, before any content-producing skill returns output. Also on-demand when reviewing existing content.
---

# validate-writing

Follow rules/global-writing-guardrails.md.

## Purpose

Enforce the global writing guardrails at machine speed. Any content-producing skill calls this before returning output. If validation fails, the caller rewrites and re-validates.

## Inputs

- `text` (required): the writing to validate.
- `context` (optional): one of `cold_email`, `blog`, `linkedin_post`, `generic`. Triggers context-specific rule sections. Default = `generic`.

## Steps

1. **Tokenise and scan.** Walk the text paragraph by paragraph.

2. **Hard-rule checks.** Flag each match and quote the offending text:
   - Em dashes (Unicode U+2014, U+2013, or two hyphens acting as a dash)
   - Superfluous adjectives (adjective chains of 2+ before nouns; single adjectives that add no information)
   - Filler phrases (`just checking in`, `I hope this finds you well`, `at the end of the day`, `needless to say`, `in order to`)
   - Buzzwords (`leverage`, `synergy`, `streamline`, `best-in-class`, `game-changer`, `cutting-edge`, `robust`, `seamless`, `transform`, `unlock`, `empower`, `actionable insights`)
   - Clichés (`moving the needle`, `low-hanging fruit`, `boil the ocean`, `circle back`, `touch base`, `deep dive`, `think outside the box`)
   - Metaphors and analogies (any phrase where X is compared to Y that isn't literal)
   - Generic statements (`this can help improve results`, `it's important to`, `there are many benefits`)

3. **Language checks.**
   - Sentence length: flag sentences > 25 words
   - Passive voice: flag any `was/were/is/are/been + past participle` construction where the subject is not the actor
   - Complex word swap list: `utilise → use`, `commence → start`, `assist → help`, `facilitate → help`, `endeavour → try`, `furthermore → also`, `nevertheless → but`, `subsequently → then`

4. **Structure checks.**
   - Paragraphs over 3 lines: flag
   - No list where list would help: flag any paragraph with 3+ comma-separated items that should be a list

5. **Clarity checks.**
   - Vague quantifiers: `many`, `some`, `several`, `a lot`, `various`, `numerous`, `significant`: flag each and demand a number or specific noun
   - Vague comparatives: `better`, `more`, `less`, `improved`: flag and require "better/more than what"

6. **Outbound-specific checks.** Run only if `context = cold_email`:
   - Word count > 75: fail
   - More than one idea: fail (detect via topic-sentence count)
   - More than one ask: fail (detect via imperative/interrogative sentence count)
   - Any match against filler phrase list in section 2: fail

7. **Compile violations.** For each flagged item, build `{rule: "<section>.<number>", offending_text: "...", suggested_fix: "..."}`.

8. **Compute pass.** `pass = len(violations) == 0`.

9. **Generate rewrite.** If `pass == false`, produce a rewrite that applies every `suggested_fix`. Apply outbound rules first if applicable, then hard rules, then language, then structure, then clarity. Keep the original intent and concrete details; only change language and structure.

10. **Re-validate the rewrite.** Run steps 2 through 8 on the rewrite. If it still fails, return both the original violations and the residual violations; mark `rewrite_quality: partial`.

11. **Return the result.**

## Output

```json
{
  "pass": false,
  "violations": [
    {
      "rule": "2.4 (buzzwords)",
      "offending_text": "we leverage cutting-edge AI to unlock insights",
      "suggested_fix": "we use Claude to extract insights from transcripts"
    }
  ],
  "rewrite": "<the full rewritten text>",
  "rewrite_quality": "clean"
}
```

## Quality gate

This skill is itself exempt from running itself on its own output (would cause infinite recursion). Its own prose is reviewed by humans quarterly.

## Escalation

If the same piece of text fails validation three times after rewrite, escalate to a human. Three QA failures = flag for review, per CLAUDE.md hard rules.
