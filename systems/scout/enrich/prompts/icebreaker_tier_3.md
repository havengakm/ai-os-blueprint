Write a personalised cold-email opener based on the prospect's recent structural event (funding round, leadership change, contract win, acquisition, expansion) below. Lead with VALUE, make it feel timely and written specifically for them.

ONE SENTENCE. 15-20 words max.

Don't make it AI-sounding. Make it sound extremely relevant. Tie the value-bridge into the sentence naturally.

It's meant to help them scale.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## The structural signal (MUST reference verbatim content from here)

Category: {signal_category}
Type: {signal_type}
Summary:
{signal_summary}

## Truth-gating rule (HARD)

Only reference items that appear VERBATIM in the signal summary above. NO invention. NO speculation about clients, projects, or financial details not literally in the signal text.

If the signal summary is empty, vague, or doesn't give you something concrete for a 15-20 word opener, return:

{{"icebreaker": ""}}

## What to AVOID at all costs (HARD)

- `Saw you're a [job title]` / `Noticed you're a [job title]` — fake personalization
- `Saw you're in [city]` / `Noticed you're in [city]` — fake personalization
- `I noticed you're the founder of a [agency type]` — LinkedIn-headline reference
- `I'm reaching out because` / `My name is X and I work at Y`
- `Came across` / `Spent the morning with` / `I hope this finds you well`

## NO founding year, NO tenure / NO critique, NO diagnosis / NO empty compliments (HARD)

Banned diagnostic shapes: "the hard part is", "the trick is", "usually means", "is usually [verbing]", "most agencies (can't|don't|won't)", "where most teams fail", "you might want to consider", "have you tried", "the (real|actual) question is".

Banned compliment shapes: "is a clean way to", "is a nice call", "stack the actual outcomes", "highlight key points people care about", "does a lot of work", "actually sells itself", "real talent", "hits different", "that lands", "nailed it", "spot on", "genuinely impressive".

Banned words: impressed, remarkable, exceptional, incredible, amazing, leverage, utilise, optimise, synergy, alignment, strategic, "just wanted to", "quick question" (as opener), headcount, BD, business development, capacity, runway, gap, signalling, ecosystem, mood-board, lead gen, craft (as positive marketing noun).

NEVER em-dashes (— or – or --). Use a comma or period.

## Output format — ONE sentence, value-led

ONE sentence. 15-20 words max. Lead with VALUE. Include "thought this could be of interest" or natural equivalent.

The opener MUST:

1. **Reference the structural event** plainly (verbatim — proves timing-aware research)
2. **Bridge into value** ("thought this could be of interest", "this might be well-timed", or natural equivalent)
3. **Frame in their terms** for the next-90-days context ("to scale", "to keep up with", "to handle the next phase")

Strict JSON, no prose, no code fences:

{{"icebreaker": "<single sentence, 15-20 words>"}}

## ALLOWED full examples (Saraev shape)

{{"icebreaker": "Given the Series A close, thought this might be well-timed for you to scale outbound through the next phase."}}

{{"icebreaker": "Given the new MD coming from Aegis, thought this could be of interest for you to align new business under fresh leadership."}}

{{"icebreaker": "Given the studio acquisition by Stagwell, thought this might be useful for you to keep pipeline pace with the wider network."}}

## BANNED full examples (will be rejected)

- "Saw you're a CEO at an agency that just raised a Series A." — fake personalization + LinkedIn-headline reference.
- "Saw the Series A. Big pickup, the Aegis background fits well." — flat-affect compliment, no value bridge.
- "Saw the funding news. The hard part is usually scaling sales fast enough." — DIAGNOSIS shape.
- "Came across the funding news this morning." — banned opener.

If the signal doesn't give you a concrete event to ground a value-led 15-20 word opener, return {{"icebreaker": ""}} instead.
