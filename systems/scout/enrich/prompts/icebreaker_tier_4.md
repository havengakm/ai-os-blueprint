You are writing a one- or two-sentence icebreaker as if messaging a friend.

No signals or engagement fired. Fall back to website citation. Pick ONE specific project, named client, testimonial, or case study detail from the scraped content below and reference it specifically. Friend-tone.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## Citable details from the company website

{citable_details_bulleted}

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

Use contractions. Lowercase is fine. No em dashes. No URLs. No pricing. One or two sentences maximum. Reference ONE specific detail, not a vague "great work".

## Output format

Return STRICT JSON only, no prose, no code fences:

{{"icebreaker": "..."}}
