Write a personalised cold-email opener based on the prospect's recent content engagement (podcast, article, talk, thread) below. Lead with VALUE, make it feel like it was written specifically for them.

ONE SENTENCE. 15-20 words max.

Don't make it AI-sounding. Make it sound extremely relevant. Tie the value-bridge into the sentence naturally.

It's meant to help them scale.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## The engaged content (MUST reference verbatim content from here)

Source: {engaged_content_source}
Text:
{engaged_content_text}

## Truth-gating rule (HARD)

Only reference items that appear VERBATIM in the engaged-content text above. NO invention. NO speculation about hosts, episodes, or quotes that aren't literally in the text.

If the engaged content is empty or doesn't give you something concrete enough for a 15-20 word opener, return:

{{"icebreaker": ""}}

NEVER reference the act of engagement (no "you liked", "you commented", "saw your engagement"). Reference the TOPIC, not the behavior.

## What to AVOID at all costs (HARD)

- `Saw you're a [job title]` / `Noticed you're a [job title]` — fake personalization
- `Saw you're in [city]` / `Noticed you're in [city]` — fake personalization
- `I noticed you're the founder of a [agency type]` — LinkedIn-headline reference
- `I'm reaching out because` / `My name is X and I work at Y`
- `Came across` / `Spent the morning with` / `I hope this finds you well`

## NO founding year, NO tenure / NO critique, NO diagnosis / NO empty compliments (HARD)

Banned diagnostic shapes: "the hard part is", "the trick is", "usually means", "is usually [verbing]", "most agencies (can't|don't|won't)", "where most teams fail", "you might want to consider", "have you tried", "the (real|actual) question is".

Banned compliment shapes: "is a clean way to", "is a nice call", "stack the actual outcomes", "highlight key points people care about", "does a lot of work", "actually sells itself", "real talent", "hits different", "that lands", "nailed it", "actually made me rethink".

Banned words: impressed, remarkable, exceptional, incredible, amazing, leverage, utilise, optimise, synergy, alignment, strategic, "just wanted to", "quick question" (as opener), headcount, BD, business development, capacity, runway, gap, signalling, ecosystem, mood-board, lead gen, craft (as positive marketing noun).

NEVER em-dashes (— or – or --). Use a comma or period.

## Output format — ONE sentence, value-led

ONE sentence. 15-20 words max. Lead with VALUE. Include "thought this could be of interest" or natural equivalent.

The opener MUST:

1. **Reference the topic from the engaged content** (verbatim — proves research)
2. **Bridge into value** ("thought this could be of interest" or natural equivalent)
3. **Frame in their terms** ("to scale", "to handle", "to free up")

Strict JSON, no prose, no code fences:

{{"icebreaker": "<single sentence, 15-20 words>"}}

## ALLOWED full examples (Saraev shape)

{{"icebreaker": "Given the agency-pricing episode you tuned into, thought this could be of interest for you to lock in margin."}}

{{"icebreaker": "Given the take on creative-director burnout, thought this might be useful for you to free up CD bandwidth."}}

{{"icebreaker": "Given the AI-tooling piece you read, thought this could land for you when re-allocating the time saved on first drafts."}}

## BANNED full examples (will be rejected)

- "Saw you're a creative director, really resonated with the episode." — fake personalization + empty reaction.
- "Caught the podcast on agency pricing. The 'value-based' framing actually made me rethink my approach." — over-used reaction shape.
- "Caught the episode. The hard part is usually convincing partners that pricing needs to change." — DIAGNOSIS shape.
- "Read the article on burnout. Hits different." — empty AI-cliche reaction.
- "I noticed you're the founder of a branding agency and listened to the pricing episode." — LinkedIn-headline reference.

If the engaged content doesn't give you a concrete topic to ground a value-led 15-20 word opener, return {{"icebreaker": ""}} instead.
