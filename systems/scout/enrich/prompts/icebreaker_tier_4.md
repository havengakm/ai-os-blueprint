Write a personalised cold-email opener based on the company-website citable details below. NO social signals fired — this is the fallback tier. Lead with VALUE, make it feel like it was written specifically for them.

ONE SENTENCE. 15-20 words max.

Don't make it AI-sounding. Make it sound extremely relevant. Tie the value-bridge into the sentence naturally.

It's meant to help them scale.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## Citable details from the company website (MUST reference verbatim items from here)

{citable_details_bulleted}

## Truth-gating rule (HARD)

Only reference items that appear VERBATIM in the citable details above. NO invention. NO speculation about clients, projects, or results not literally in the scraped text.

If the citable details are empty, say "(none)", or only contain generic items (taglines, headlines, follower counts, founding year, "we do brand work"), return:

{{"icebreaker": ""}}

Empty is the correct, expected answer when the source is thin. NEVER compensate for thin material with vague compliments or filler.

## What to AVOID at all costs (HARD)

- `Saw you're a [job title]` / `Noticed you're a [job title]` — fake personalization, treats them as a generic role
- `Saw you're in [city]` / `Noticed you're in [city]` — fake personalization
- `I noticed you're the founder of a [agency type]` — LinkedIn-headline reference
- `I'm reaching out because` / `My name is X and I work at Y` — vendor-y opener
- `Came across` / `Spent the morning with` / `I hope this finds you well`

## NO founding year, NO tenure (HARD)

Banned: "founded in YYYY", "since YYYY", "been at this for X years", "decade-plus".

If the only specific thing in citable details is a tenure reference, return {{"icebreaker": ""}}.

## NO critique, NO diagnosis, NO unsolicited advice (HARD)

Banned diagnostic shapes: "the hard part is", "the trick is", "usually means", "is usually [verbing]", "most agencies (can't|don't|won't)", "where most teams fail", "you might want to consider", "have you tried", "the (real|actual) question is", "stops at the [X] boundary".

## NO empty compliments (HARD)

Banned exact shapes: "is a clean way to", "is a nice call", "stack the actual outcomes", "highlight key points people care about", "does a lot of work", "actually sells itself", "real talent", "hits different", "that lands", "nailed it", "spot on", "genuinely impressive", "actually made me rethink".

## Banned words

impressed, remarkable, exceptional, incredible, amazing (without specifics), leverage, utilise, optimise, synergy, alignment, strategic, "just wanted to", "quick question" (as opener), headcount, BD, business development, capacity, runway, gap, signalling, ecosystem, mood-board, lead gen, craft (as positive marketing noun).

NEVER em-dashes (— or – or --). Use a comma or period.

## Output format — ONE sentence, value-led

ONE sentence. 15-20 words max. Lead with VALUE. Include "thought this could be of interest" or natural equivalent.

The opener MUST:

1. **Reference something specific from the citable details** (verbatim — proves research, named client / named project / specific craft choice)
2. **Bridge into value** ("thought this could be of interest" or natural equivalent)
3. **Frame in their terms** ("to scale", "to free up", "to handle [their constraint]")

Strict JSON, no prose, no code fences:

{{"icebreaker": "<single sentence, 15-20 words>"}}

## ALLOWED full examples (Saraev shape)

{{"icebreaker": "Given the Iroko work in your portfolio, thought this could be of interest for you to scale similar regulated-industry briefs."}}

{{"icebreaker": "Given the Bishop Studios identity work, thought this might be useful for you to free up capacity for more client work."}}

{{"icebreaker": "Given the Glow Wellness rebrand on your site, thought this could be of interest to you for scaling beauty-sector work."}}

## BANNED full examples (will be rejected)

- "Saw you're a creative director in San Diego." — fake personalization, AI-tell.
- "Saw the Iroko work. The modular icon is a nice call." — flat-affect compliment, no value bridge.
- "Noticed the followers-to-leads framing. The hard part is usually proving attribution." — DIAGNOSIS shape.
- "Noticed LYFE Marketing was founded in 2011. Decade-plus run says something." — tenure reference.
- "Saw the Iroko work — really clean." — em-dash + bare praise.
- "I noticed you're the founder of a branding agency." — LinkedIn-headline reference.
- "Came across LYFE Marketing's site this morning." — banned opener.

If the citable details don't give you something concrete to ground a value-led 15-20 word opener (a named client, named project, specific craft decision, or quoted line), return {{"icebreaker": ""}} instead. Empty is better than fake.
