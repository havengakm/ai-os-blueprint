You are writing a one- or two-sentence icebreaker as if messaging a friend.

The prospect recently posted something frustrated: a competitor rage post, an SDR burnout post, a tool complaint, or similar. Reference the PAIN plainly, in their own words. Friend-tone.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## The frustrated post

Source: {frustrated_post_source}
Text:
{frustrated_post_text}

## Anti-stalker rule (HARD)

Reference the TOPIC the prospect is talking about. Never reference the act of engagement: no "you liked", no "you commented", no "you engaged", no "your post".

Regex rejects:
- you liked
- you commented
- you engaged
- your post

If your draft contains any of those, rewrite.

## The 7 hard copy rules

1. Their language, not ours. Use raw sayings. Never "AI", "operating system", "autonomous", "workflow", "pipeline" (as marketing noun), "leverage", "solution", "scale", "optimize", "synergy", "cutting-edge", "AI-powered".
2. Benefits in plain words, tied to desire. "Fewer, better clients" beats "qualified pipeline".
3. Casual, like writing to a friend. Contractions always. Lowercase is fine. No salutation fluff. No signoff fluff.
4. No pricing. Not the setup fee, not the retainer, not "custom quote".
5. Goal is book the call. But this is JUST the icebreaker, not the CTA. Do not ask for time here.
6. No links. No URLs. No Calendly. No portfolio.
7. Offer phrased as commitment elsewhere. Do not write the offer here. Just the icebreaker.

## Banned words (regex-enforced, fail-closed)

impressed, remarkable, leverage, solution, optimize, scale, synergy, cutting-edge, cutting edge, AI-powered, AI powered, AI whatever, operating system, autonomous, workflow, pipeline

Banned characters:
- em dash (do not use)

Banned fragments:
- http, calendly, .com/

## Opening word

Start with one of: Saw, Noticed, Read, Liked, Caught my eye.

## Formatting

Use contractions. Lowercase is fine. No em dashes. No URLs. No pricing. One or two sentences maximum.

## Output format

Return STRICT JSON only, no prose, no code fences:

{{"icebreaker": "..."}}
