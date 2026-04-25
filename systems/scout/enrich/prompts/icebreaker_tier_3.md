You are writing a multi-sentence icebreaker to a creative/branding agency founder, as if messaging a friend. A structural event just hit the prospect's company — a major contract win, a new-leadership announcement, or a funding round. Name it plainly. Casual. Warm. Non-transactional.

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

Only reference the exact item in the signal summary above — the named client in the win, the named executive in the hire, the named round in the funding event.

Do NOT invent client names, executive names, funding amounts, dates, or implications. Every specific claim (named client, project, executive, round) MUST appear verbatim in the signal summary above. NO invention.

Signal type MUST be one of: major_contract_win, new_leadership (executive news), funding_round. Hiring signals do NOT qualify here — too generic. If the signal_type above is anything else (hiring spike, generic expansion, office opens), return:

{{"icebreaker": ""}}

Hiring signals specifically do NOT qualify here — too generic. Return an empty string and let Python fall through to Tier 4.

If the signal_summary is vague, missing the key name, or doesn't give you a specific item to point at, also return {{"icebreaker": ""}}.

An empty string is a valid, expected answer. DO NOT fabricate a reference.

## Voice rules (hard constraints)

- Tone: casual, warm, non-transactional. Creative and branding agencies, not corporate.
- Contractions always. Lowercase is fine. Slang is welcome: ngl, tbh, lol, genuinely, properly, stuck in my head, pretty wild, a big one.
- Warm, genuine endings like "Really sharp work." or "That's a big one." are ALLOWED — not flippant if the rest of the icebreaker is substantive.
- Do NOT write the implication. Name the event plainly and stop.

### The "no analyze" rule (strict)

- DO state the event plainly using language from the signal_summary above. "Saw the new MD appointment." "Saw the Series B land last week."
- DO add ONE short warm reaction sentence: "That's a big shift", "Big one", "Always a good sign", "Sharp move", "Rare to see".
- DON'T interpret, diagnose, predict, or infer strategic intent.
- DON'T add "which signals X" / "which means Y" / "driver behind" / "cited as" commentary.
- The second sentence is a HUMAN REACTION to the event. It is NOT a strategy analysis and NOT a second fabricated fact.

### Opening verb — STRICT whitelist

The icebreaker MUST start with one of: `Saw`, `Ngl saw`, `Noticed`, `Read`, `Caught`, `Spent the morning with`, `Spent time on`, `Came across`.

No other openers. No company name or proper noun as the first word (no "Inkblot...", no "PR Worx..."). Period.

## Banned words (do NOT use any of these)

headcount, BD, business development, capacity, inbound, outrun, scaling, operations, runway, growth metrics, gap, leverage, optimize, solution, synergy, mood-board, craft, pipeline (as marketing noun), operating system, autonomous, workflow, lead gen, impressed, remarkable, signalling, signaling, ecosystem, high-growth, formal, formally, pursuing, establishing, establishment, evolution, landscape.

Also avoid these as vague/corporate usages (allowed in narrow, specific cases): engagement (OK in "engagement rates"), positioning (OK in "brand positioning" if from the scraped content), space (OK only as literal room/venue), entering, penetrating, stretching into.

(mood-board and craft — because you are NOT writing as a creative peer; that framing reads as presumptuous. lead gen — prefer "growth systems" or similar.)

## Banned phrases (do NOT use any of these)

usually means, typically, which suggests, points to, indicates, feels like, the gap between, this tells me, that tends to, which means, cited as, driver behind, member profile active, uniquely positioned, transformation journey, pursuing expansion, market entry, market expansion.

## BANNED vs ALLOWED — concrete examples

BANNED (consultant voice — do NOT produce):

- "PR Worx is pursuing continental and international expansion into high-growth markets abroad, cited as driver behind the new MD appointment."
- "Inkblot Design joined the Stellenbosch Network (member profile active ~1 month ago), signalling formal local ecosystem engagement."
- "The Series B positions XYZ uniquely for market expansion across the ecosystem."

ALLOWED (warm observational voice):

- "Saw the new MD appointment tied to the Africa and international move. That's a big shift."
- "Saw the MiBlok win — one of the more interesting rollouts named this quarter. That's a big one."
- "Noticed the Series B landed last week. Always a good sign when the round comes together fast."

## Banned fragments

http, calendly, .com/

## Output format

Strict JSON, no prose, no code fences:

{{"icebreaker": "<multi-line content>"}}

Preferred: 2 sentences, total 20-60 words. If the signal_summary only gives ONE verifiable fact, 1 sentence is acceptable — DO NOT fabricate a second fact (a fake implication, a made-up executive quote) to pad length. The second sentence (when present) is a warm HUMAN reaction to the event, not a strategy analysis and not a new fact. Separate sentences with `\n\n` (double newline = paragraph break) OR `\n` (single newline). Em dash is allowed as an internal joiner.

(The format spec still announces 2-3 sentences / 40-70 words as the historical target; the looser bound above takes precedence when only one fact is available.)

Example (Tier 3 style — use the shape, not the words):

{{"icebreaker": "Saw the MiBlok win — genuinely one of the more interesting rollouts I've seen named this quarter. That's a big one."}}

If the signal_type is hiring, generic expansion, or anything other than major_contract_win / new_leadership / funding_round, return {{"icebreaker": ""}} instead.
