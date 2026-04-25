---
name: global-writing-guardrails
description: Global writing rules every skill must enforce before returning output. If a rule is violated, rewrite.
applies-to: every skill that produces written output
owner: Kirsten
---

# Global Writing Guardrails

## 1. Core Principle

All outputs must:

- sound like a real person wrote them
- be clear on first read
- be easy to scan

If it sounds like AI, it fails.

## 2. Hard Rules (Non-Negotiable)

- No em dashes
- No superfluous adjectives
- No filler phrases
- No generic statements
- No buzzwords
- No clichés
- No metaphors or analogies
- No overexplaining
- No repetition
- No fluff

## 3. Language Rules

- Use short sentences
- Use active voice
- Use plain English
- Prefer simple words over complex ones
- One idea per sentence
- Cut unnecessary transitions

## 4. Structure Rules

- Start with the point
- Remove long intros
- Break lines often
- Keep paragraphs under 3 lines
- Use lists when possible

## 5. Clarity Rules

Every output must:

- answer the question directly
- be specific, not vague
- include concrete details where possible

Bad:
> "This can help improve results"

Good:
> "This increases reply rates by making the message specific"

## 6. Constraint Rules

- Remove any word that does not add meaning
- Replace vague terms:
  - "better" → specify how
  - "optimize" → state the action
  - "leverage" → say what you are doing

## 7. Humanity Rules

- Write like you speak
- Avoid robotic phrasing
- Avoid overly formal tone
- Do not sound like a blog post

## 8. Output Quality Check (Mandatory)

Before returning any output, validate:

- Can this be shorter?
- Is any sentence vague?
- Is any word unnecessary?
- Would a real operator say this?

If yes to any, rewrite.

## 9. Outbound-Specific Rules

For cold outreach:

- Aim for ~75 words. Short and punchy is the goal. Going over is acceptable when the body needs the room (rich icebreaker, multi-component template). If you're past ~150 words, trim.
- One clear idea
- One clear ask
- No long setup
- No "just checking in"
- No forced personalisation

## 10. Failure Conditions

Output is invalid if:

- sounds generic
- reads like AI
- contains fluff
- takes effort to understand
- has no clear action

## 11. Implementation Rule

Every skill file must include this line near the top, inside the body:

> Follow rules/global-writing-guardrails.md

No exceptions.

## 12. Validation Contract

Every content-producing skill must run `skills/meta/validate-writing.md` on its output before returning. That skill is the machine-check for the rules above. If validation fails, the skill rewrites and re-validates before returning.
