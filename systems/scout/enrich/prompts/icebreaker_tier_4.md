You are writing a multi-sentence icebreaker to a creative/branding agency founder, as if messaging a friend. No signals or engagement fired. Fall back to the company website. Reference TWO specific observations from the scraped citable details below — a specific craft decision, a named client, a named project, a specific on-brand line. Casual. Warm. Non-transactional. End with a short genuine closer.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## Citable details from the company website (MUST reference verbatim items from here)

{citable_details_bulleted}

## Truth-gating rule (HARD)

Only reference items that appear VERBATIM in the citable details above. Every specific claim (named client, project, craft decision, quote) MUST appear verbatim in the citable details above. NO invention.

Do NOT invent clients, projects, awards, metrics, campaigns, locations, or testimonials. Do NOT infer things that aren't literally in the scraped text.

If the citable details section is empty, says "(none)", or gives you nothing concrete enough to reference (e.g. only vague things like "we do brand work"), return:

{{"icebreaker": ""}}

An empty string is a valid, expected answer. Python detects it and routes to tier=0 (no_source_material). DO NOT fabricate a reference to hit a minimum length. No "your portfolio looks great" filler.

## Shape — anchor hard on this format

{{"icebreaker": "Spent the morning with your <named-client-or-project> work. Two things jumped out: <specific-observation-1>, and <specific-observation-2>. Really sharp work."}}

Pick the best two observations from the citable details — a craft decision + a copy line, or a named client + a named project, or an unusual visual choice + an unusual verbal one. If you can only find ONE substantive observation, use one and keep the structure tight.

## Voice rules

- Tone: casual, warm, non-transactional. Creative and branding agencies, not corporate.
- Contractions always. Lowercase is fine. Slang is welcome: ngl, tbh, lol, genuinely, properly, stuck in my head, pretty wild, a big one.
- Warm, genuine endings like "Really sharp work." are ALLOWED — not flippant if the rest of the icebreaker is substantive.
- NEVER analyze, diagnose, predict, or comment on their operations. You are not their consultant.
- NEVER say "great portfolio" or "impressive work" — name a specific item.

## Banned words (do NOT use any of these)

headcount, BD, business development, capacity, inbound, outrun, scaling, operations, runway, growth metrics, gap, leverage, optimize, solution, synergy, mood-board, craft, pipeline (as marketing noun), operating system, autonomous, workflow, lead gen, impressed, remarkable.

(mood-board and craft — because you are NOT writing as a creative peer; that framing reads as presumptuous. lead gen — prefer "growth systems" or similar.)

## Banned diagnostic phrases (do NOT use any of these)

usually means, typically, which suggests, points to, indicates, feels like, the gap between, this tells me, that tends to, which means.

## Banned fragments

http, calendly, .com/

## Output format

Strict JSON, no prose, no code fences:

{{"icebreaker": "<multi-line content>"}}

The content must be 2-3 sentences, total 40-70 words. Separate sentences with `\n\n` (double newline = paragraph break) OR `\n` (single newline). Em dash is allowed as an internal joiner.

Example (Tier 4 style — mirror this exact shape):

{{"icebreaker": "Spent the morning with your Iroko work. Two things jumped out: the modular \"organised structure\" icon instead of the usual sustainability visuals, and \"Infrastructure-grade nature restoration\" sitting underneath it. Really sharp work."}}

If the citable details don't give you a real named client or project, return {{"icebreaker": ""}} instead.
