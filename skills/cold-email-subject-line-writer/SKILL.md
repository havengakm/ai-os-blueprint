---
name: cold-email-subject-line-writer
description: Write cold email subject lines that maximize open rates without triggering spam filters or pattern-matching as automated outreach. Generate single subject lines or variant sets for A/B testing. Use this skill whenever the user wants to write a cold email subject line, generate subject line variants for testing, improve open rates on a cold email campaign, fix subject lines that are getting filtered to spam, or build subject lines for tools like Instantly, Smartlead, or Lemlist. Trigger on phrases like "subject line," "cold email subject," "open rate," "what should I put in the subject," "subject line variants," "A/B test subject lines," or whenever the user asks for help with the subject of an outbound email.
---

# Cold Email Subject Line Writer

Write subject lines that get opened. Open rate is the gate; everything else in the email is irrelevant if the subject fails. This skill produces subject lines that look human, signal relevance, and avoid the patterns that trigger spam filters or instant deletion.

## When to use this skill

Trigger this skill when the user wants to:

- Write a subject line for a cold email
- Generate 3-5 variants for A/B testing
- Improve open rates on an existing campaign
- Fix subject lines that are landing in spam
- Build subject lines that match the offer in the CTA
- Generate subject lines at scale for tools like Instantly, Smartlead, or Lemlist

This skill works alongside `cold-email-body-writer` and `intent-opener-writer`. Together they produce a complete cold email. This skill specifically owns the subject line.

## The core principle

A cold email subject line in 2026 has two jobs only: get opened, and not get filtered. It is not a hook. It is not a teaser. It is not a sales pitch. The body does selling. The subject does access.

The strongest subject lines look exactly like an email a colleague would send. Lowercase. Specific to the recipient. Short. Slightly mundane. The mundane quality is the feature, not a bug — promotional-sounding subjects get deleted in 0.5 seconds.

If a subject line could appear in a marketing email, it will fail. If it could only appear in a personal email, it will win.

## The 10 winning subject line patterns

Pick one pattern based on what fits the email body and offer. Each works for different reasons.

### Pattern 1: Quick question

Format: `quick question`

When to use: When the email body genuinely contains a question (the closing question after the CTA). Most universal pattern. Works across industries. The pattern peaked in 2019 but still works because it sounds human.

Risk: Some recipients pattern-match this as a sales tactic. Use sparingly in the same campaign. Mix with other patterns.

### Pattern 2: Their company name + asset

Format: `{{company}}'s website` / `{{company}}'s site` / `{{company}}'s blog` / `{{company}}'s ads`

When to use: When the email references something about their specific business asset. The company name in the subject is the strongest curiosity trigger because it implies you actually looked.

Risk: If the email body does not actually reference what you mentioned in the subject, the recipient feels deceived. Match the subject to the body content.

### Pattern 3: Question for them

Format: `question for {{firstName}}`

When to use: When the email is a single, direct, focused message (not a complex pitch). Implies you have a specific question, not a sales script.

Risk: Slightly more formal than `quick question`. Works better for senior buyers (VPs, founders) than junior contacts.

### Pattern 4: Number + deliverable + name

Format: `5 [deliverable] for {{firstName}}` / `3 [deliverable] for {{firstName}}`

When to use: When the CTA in the body offers a specific tangible deliverable with a number. This is the strongest pattern when the offer itself is strong.

Examples:
- `5 videos for Sarah`
- `3 ads for Mike`
- `200 leads for Jordan`

Risk: Only works if the body delivers what the subject promises. Mismatch destroys trust.

### Pattern 5: City + vertical

Format: `[city] [vertical]`

When to use: When the campaign targets a specific geo + niche segment. Implies relevance immediately.

Examples:
- `phoenix property management`
- `denver med spa`
- `austin restaurants`

Risk: Only works for geo-targeted campaigns. Useless for national or broad-segment outreach.

### Pattern 6: Their name + comma + topic

Format: `{{firstName}}, [topic]?` / `{{firstName}}, [topic]`

When to use: When you want to invoke a specific topic without being too obvious. The comma break makes it look like a real personal email.

Examples:
- `Sarah, owner acquisition?`
- `Mike, weekend response`
- `Jordan, the hiring search`

Risk: Slightly more casual. Works better for warmer tier 1 prospects than cold tier 3.

### Pattern 7: Their last action / signal

Format: References something they recently did. Short. Specific.

Examples:
- `your phoenix expansion`
- `the growth lead role`
- `your narpm panel`

When to use: Strongest pattern when you have a real signal-based opener in the body. The subject and personalization opener should share the same anchor.

Risk: Requires a real signal. Inventing one breaks credibility instantly.

### Pattern 8: Specific observation about their business

Format: References something concrete about their business in plain language.

Examples:
- `your zillow listings`
- `your top product page`
- `your weekend response time`

When to use: When the body opens with a specific observation about their work. Tees up the problem section.

Risk: Walks the line near "surveillance creep." Stick to publicly visible things.

### Pattern 9: Mutual context

Format: References shared context, mutual connection, or shared event.

Examples:
- `[Mutual Name] suggested I reach out`
- `narpm broker/owner conference`
- `bigger pockets thread`

When to use: When you have any shared context, even tenuous. This is the closest thing to a warm intro you can fake. Open rates spike when this is real.

Risk: Lying about a mutual connection is a deal-breaker. Only use if the connection is real (even if loose).

### Pattern 10: Industry-specific shorthand

Format: Uses insider language only their industry would recognize.

Examples (PM industry):
- `door count question`
- `narpm 2026`
- `appfolio gap`

Examples (ecom):
- `aov question`
- `klaviyo flow`
- `shopify checkout`

When to use: When you are confident the recipient is deeply in the industry. Insider language signals "this is from someone in our world." Risky for outsiders to attempt.

Risk: If you use it wrong, you sound like an outsider trying to sound insider. Worse than not trying at all.

## Length rules

Hard rules:

- **Word count: 2-6 words.** Anything longer feels like a marketing email.
- **Character count: under 40 characters preferred, under 50 absolute max.** Mobile preview truncates at 30-40 characters depending on client. Long subjects get cut off.
- **Lowercase only** (with rare exception of names and brand names that are properly capitalized).

The lowercase rule is not optional. Capitalized titles ("Quick Question About Your Business") are pattern-matched as marketing emails. Lowercase looks like a colleague typed it on their phone.

## Banned patterns (deliverability risk + open rate killers)

These trigger spam filters or get deleted instantly. Avoid all of them.

### Words that trigger spam filters

Sales / marketing words:
- boost, supercharge, unlock, transform, 10x, double, triple, scale, grow
- amazing, incredible, ultimate, exclusive, special offer, limited time
- save, discount, free trial, free consultation, free audit
- guaranteed, proven, results

Money / urgency words:
- $$$, $, money, cash, profit, earnings, ROI
- act now, urgent, hurry, deadline, expires, last chance
- don't miss, opportunity, breakthrough

### Formatting that triggers filters

- ALL CAPS subject lines
- Multiple exclamation points (!!!)
- Multiple question marks (???)
- Emojis (some clients filter these aggressively)
- Special characters: $, %, *, =, +
- "Re:" or "Fwd:" fakes (deliverability poison + trust killer)

### Patterns that get deleted instantly

- "Hope you're well" (in subject — body usage is also bad but subject is worse)
- "Following up on..."
- "Touching base"
- "Checking in"
- "Just wanted to..."
- Anything that mentions sales, partnership, or "opportunity"
- Anything ending with "!"
- Subject lines that are full sentences (a real person types a fragment)

## Match-to-offer logic

The subject line should tee up what the body delivers. Mismatch breaks trust.

### Strong matches

- Body offers "5 video scripts" → Subject: `5 videos for {{firstName}}`
- Body references their website conversion → Subject: `{{company}}'s site`
- Body opens with a question → Subject: `quick question` or `question for {{firstName}}`
- Body references their NARPM panel → Subject: `your narpm panel`
- Body targets med spas in Miami → Subject: `miami med spa`

### Weak matches

- Body offers "3 ad creatives" → Subject: `quick question` (does not match offer)
- Body opens with industry insight → Subject: `{{company}}'s website` (off-topic)

The body writer skill (`cold-email-body-writer`) generates the body and the offer. This skill should generate a subject that matches both.

## Output format

When generating subject lines, produce them in this format:

### Single subject line request

```
Subject: [subject line]

Pattern: [pattern name]
Word count: [N]
Character count: [N]
Why it fits: [1 sentence explanation]
```

### Multiple variants for A/B testing

```
## Subject Line Variants for [DESCRIPTION OF EMAIL]

Variant 1 — [pattern name]:
"[subject]"
- Strength: [why this might win]

Variant 2 — [different pattern]:
"[subject]"
- Strength: [why this might win]

Variant 3 — [different pattern]:
"[subject]"
- Strength: [why this might win]

Recommended starting variant: [N]
Reason: [brief justification]
```

Always vary across DIFFERENT patterns when generating variants. Three different wordings of the same pattern is not a real A/B test.

## Worked examples

### Example 1: AI growth infrastructure for PM companies

**Input:** Body offers "free target list of 200 absentee landlords." Recipient is owner of 400-door PM company in Phoenix.

**Output:**

```
## Subject Line Variants

Variant 1 — Number + deliverable + name:
"200 landlords for {{firstName}}"
- Strength: Directly tees up the offer in the CTA. Curiosity trigger ("they have 200 landlords for me?")
- Word count: 4 / Char count: ~30

Variant 2 — City + vertical:
"phoenix property management"
- Strength: Implies relevance through geo + niche match. Mundane and human.
- Word count: 3 / Char count: 27

Variant 3 — Quick question:
"quick question"
- Strength: Universal pattern. Works as a baseline control to compare against more specific variants.
- Word count: 2 / Char count: 14

Recommended starting variant: Variant 1
Reason: When the offer is strong (200 leads is a tangible high-value deliverable), naming it in the subject increases open rate AND aligns the subject to the body promise. This is the highest-leverage pattern when the offer can carry it.
```

### Example 2: CRO agency for ecommerce brand

**Input:** Body offers "free landing page mockup for one of your top products." Recipient is DTC ecom founder.

**Output:**

```
## Subject Line Variants

Variant 1 — Their company name + asset:
"{{company}}'s site"
- Strength: Personalized. Hints at site review without being threatening. Strong curiosity trigger.
- Word count: 2 / Char count: variable

Variant 2 — Specific observation:
"your top product page"
- Strength: Specific to a real asset they have. Tees up the offer (mockup of top product).
- Word count: 4 / Char count: 21

Variant 3 — Number + deliverable + name:
"a mockup for {{firstName}}"
- Strength: Names the deliverable directly. Less common pattern, stands out.
- Word count: 4 / Char count: ~22

Recommended starting variant: Variant 1
Reason: For ecom DTC founders, "{{company}}'s site" performs consistently well because the recipient's identity is tied to their site. Implies you reviewed something specific. Strong open rate without sounding sales-y.
```

### Example 3: Outbound services for B2B SaaS

**Input:** Body offers "free target list of 200 ICP accounts plus a sample sequence." Recipient is VP Sales at Series A SaaS.

**Output:**

```
## Subject Line Variants

Variant 1 — Their company name + asset:
"{{company}}'s pipeline"
- Strength: Implies you have something specific about their pipeline. Strong for senior buyers.

Variant 2 — Number + deliverable + name:
"200 accounts for {{firstName}}"
- Strength: Names the offer. Works because VPs of Sales recognize the value of 200 ICP-matched accounts immediately.

Variant 3 — Industry shorthand:
"icp question"
- Strength: Insider language. Signals you understand their world. Curious but specific.

Recommended starting variant: Variant 2
Reason: VPs of Sales are highly metric-driven. Naming a specific number in the subject (200 accounts) creates immediate value perception and matches their decision-making style. Higher signal than vague pattern-interrupts.
```

## A/B testing recommendations

Subject lines are the highest-leverage A/B test in cold email. Always test.

### What to test

Test across DIFFERENT patterns, not different wordings of the same pattern. Examples of real A/B tests:

- Pattern 4 (Number + deliverable) vs. Pattern 5 (City + vertical)
- Pattern 1 (Quick question) vs. Pattern 7 (Recent signal reference)
- Pattern 2 (Company name + asset) vs. Pattern 4 (Number + deliverable)

### Sample size

Minimum 100 sends per variant before drawing any conclusion. Statistical significance requires 200-500 per variant for confident decisions. Smaller samples produce noise, not signal.

### What to measure

- **Open rate** (primary metric for subject line tests)
- **Reply rate** (secondary — sometimes a high open rate subject leads to lower replies because it overpromises)
- **Positive reply rate** (most important long-term metric — opens and replies do not matter if nobody books)

A subject that gets 60% opens and 1% replies is worse than one that gets 40% opens and 4% replies. Always look at downstream metrics.

### Avoid testing too many variables

Test ONE thing at a time. If you change subject line AND opening line AND CTA, you cannot tell which change moved the needle. Subject line tests should keep body identical across variants.

## Common failure patterns to avoid

When reviewing AI-generated subject lines, watch for these failures:

1. **Title case capitalization.** "Quick Question About Your Property Business" reads as marketing email. Fix: lowercase everything.

2. **Length creep.** "A Few Quick Thoughts About Growing Your Phoenix Property Management Company." Fix: cut to 2-6 words.

3. **Promotional words.** "Boost Your Property Management Growth!" Fix: remove all sales words; use plain descriptive language.

4. **Mismatched to body.** Subject says "5 videos for Sarah" but body offers "free strategy call." Fix: align subject to actual offer.

5. **Generic curiosity bait.** "You won't believe this..." Fix: never use vague intrigue. Use specific personalization instead.

6. **Question marks where they don't belong.** "Free audit?" feels needy. Fix: only use question marks when the subject genuinely poses a question (e.g., "icp question").

7. **All-caps for emphasis.** "PHOENIX PM OPPORTUNITY" triggers spam filters. Fix: lowercase only.

8. **Emojis for personality.** "🚀 Growing your business" filters to spam. Fix: zero emojis in cold email subjects.

9. **Multiple punctuation marks.** "Quick question!!!" or "??" Fix: zero exclamation points; single question marks only when warranted.

10. **Fake threading.** "Re: Your inquiry" when there was no prior inquiry. Fix: never use Re: or Fwd: unless the thread is real.

## Quality checklist

Before finalizing any subject line, verify:

- [ ] 2-6 words
- [ ] Under 50 characters (preferably under 40)
- [ ] Lowercase (with exception only for proper names/brands)
- [ ] No banned spam-trigger words
- [ ] No exclamation points
- [ ] No emojis
- [ ] No fake "Re:" or "Fwd:"
- [ ] Matches the offer in the body
- [ ] Sounds like a personal email, not a marketing email
- [ ] Could pass for a real subject line a colleague would send

## Companion skills

For the email body that follows the subject, use `cold-email-body-writer`.

For the personalization line that opens the body, use `intent-opener-writer`.

For brainstorming the offer the subject should match, use `cold-email-offer-brainstormer`.

The four skills together produce a complete cold email: subject (this skill) + opener (intent-opener-writer) + body (cold-email-body-writer) + offer (cold-email-offer-brainstormer).
