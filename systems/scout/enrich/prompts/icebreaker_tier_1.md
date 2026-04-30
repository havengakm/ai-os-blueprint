Write a personalised cold-email opener based on the prospect's recent post or buying/social signal below. This is Tier 1 — the strongest tier — because the prospect just said something specific and timely. Lead with VALUE, make it feel like it was written specifically for them.

ONE SENTENCE. 15-20 words max.

Don't make it AI-sounding. Make it sound extremely relevant and as if it was written specifically for them. Tie the value-bridge into the sentence naturally.

It's meant to help them scale.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## The post / buying signal (MUST reference verbatim content from here)

Source: {frustrated_post_source}
Text:
{frustrated_post_text}

## Truth-gating rule (HARD)

Only reference things that appear VERBATIM in the post text above. NO invention. NO speculation about clients, projects, or details that aren't literally in the post.

If the post text is empty or doesn't give you something concrete enough to ground a 15-20 word opener, return:

{{"icebreaker": ""}}

Empty is the correct answer when the source is thin. Python detects it and routes to tier=0 (no_source_material).

NEVER reference the act of posting (no "you posted", "you commented", "your post"). Reference the TOPIC or the SUBSTANCE, not the engagement behavior.

## What to AVOID at all costs (HARD)

These are AI-tells that scream "mass blast":

- `Saw you're a [job title]` / `Noticed you're a [job title]` — fake personalization, treats them as a generic role
- `Saw you're in [city]` / `Noticed you're in [city]` — fake personalization
- `I noticed you're the founder of a [agency type]` — they know what they are
- `I'm reaching out because` / `My name is X and I work at Y` — vendor-y opener
- `Came across your post` / `Spent the morning with` / `I hope this finds you well`
- The company name as the first word

## NO founding year, NO tenure (HARD)

Banned: "founded in YYYY", "since YYYY", "been at this for X years", "decade-plus".

## NO critique, NO diagnosis, NO unsolicited advice (HARD)

Even though the prospect named a problem in their post, do NOT diagnose them further or extend it into a lecture.

Banned shapes:

- "the hard part is" / "the trick is" / "usually means" / "is usually [verbing]"
- "most agencies (can't|don't|won't|miss)" / "where most teams fail"
- "your agency doesn't seem to have"
- "you might want to (try|consider|look at)" / "have you (tried|considered)"
- "the (real|actual) (question|issue) is"
- "stops at the [X] boundary"

## NO empty compliments (HARD)

Banned exact shapes: "is a clean way to", "is a nice call", "stack the actual outcomes", "highlight key points people care about", "does a lot of work", "actually sells itself", "real talent", "hits different", "that lands", "nailed it", "spot on", "topic of the quarter", "actually made me rethink".

## Banned words (per framework + validator)

impressed, remarkable, exceptional, incredible, amazing (without specifics), leverage, utilise, optimise, synergy, alignment, strategic, "just wanted to", "quick question" (as opener), headcount, BD, business development, capacity, runway, gap, signalling, ecosystem, mood-board, lead gen, craft (as positive marketing noun).

NEVER em-dashes (— or – or --). If you would naturally write an em-dash, restructure into a comma or period. Use a single fluid sentence.

## Output format — ONE sentence, value-led, with built-in bridge

ONE sentence. 15-20 words max. Lead with VALUE. Include "thought this could be of interest for you to [scale / improve / handle X]" or an equivalent natural value-bridge that flows directly into "to [help them with their thing]".

The opener MUST do three things in one sentence:

1. **Reference something specific from the post** (verbatim — proves research, not mass-blast)
2. **Bridge into value** ("thought this could be of interest" or natural equivalent)
3. **Frame the value in their terms** ("to scale your [thing]", "to handle [their problem]", "to free up [their constraint]")

Strict JSON, no prose, no code fences:

{{"icebreaker": "<single sentence, 15-20 words>"}}

## ALLOWED full examples (Saraev shape)

{{"icebreaker": "Given the post about clients ghosting mid-project, thought this could be of interest to help you stabilise pipeline."}}

{{"icebreaker": "Given the take on the SDR-burnout cycle, thought this might land for you when scaling outbound without burning the team."}}

{{"icebreaker": "Given the thread on feast-or-famine pipeline, thought this might be useful for you to flatten the spike-and-dip cycle."}}

## BANNED full examples (will be rejected)

- "Saw you're a creative director in San Francisco." — fake personalization, AI-tell.
- "Noticed you're in NYC and posting about pipeline." — fake personalization.
- "I noticed you're the founder of a branding agency. Sharp positioning." — LinkedIn-headline reference + AI-cliche.
- "Saw your post about clients ghosting. The hard part is usually the original scope being signed off the wrong stakeholder." — DIAGNOSIS shape, lecturing.
- "Saw your post — really hit close to home." — em-dash slip + empty reaction.
- "Saw your post about the rollercoaster. Hits different." — empty AI-cliche reaction.

If the post doesn't give you a concrete enough hook to ground a 15-20 word value-led opener, return {{"icebreaker": ""}} instead.
