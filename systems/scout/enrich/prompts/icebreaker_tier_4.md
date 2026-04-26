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

## Voice rules (hard constraints)

- Tone: casual, warm, non-transactional. Creative and branding agencies, not corporate.
- Contractions always. Lowercase is fine. Slang is welcome: ngl, tbh, lol, genuinely, properly, stuck in my head, pretty wild, a big one.
- Warm, genuine endings like "Really sharp work." are ALLOWED — not flippant if the rest of the icebreaker is substantive.
- NEVER say "great portfolio" or "impressive work" — name a specific item.

### The "no analyze" rule (strict)

- DO state the observations from the citable details using simple, admiring language. Use THEIR OWN words where possible (quoted copy lines, named projects, named clients).
- DO add ONE short warm reaction sentence like "Really sharp work" or "Sharp move".
- DON'T interpret, diagnose, predict, or infer strategic intent.
- DON'T add "which signals X" / "which means Y" / "driver behind" / "cited as" / "positioning" commentary.
- Observational + admiring is the mode. Consultant is not.

### Opening verb — STRICT whitelist

The icebreaker MUST start with one of: `Saw`, `Ngl saw`, `Noticed`, `Read`, `Caught`, `Spent the morning with`, `Spent time on`, `Came across`.

No other openers. No company name or proper noun as the first word. Period.

## Banned words (do NOT use any of these)

headcount, BD, business development, capacity, inbound, outrun, scaling, operations, runway, growth metrics, gap, leverage, optimize, solution, synergy, mood-board, craft, pipeline (as marketing noun), operating system, autonomous, workflow, lead gen, impressed, remarkable, signalling, signaling, ecosystem, high-growth, formal, formally, pursuing, establishing, establishment, evolution, landscape.

Also avoid these as vague/corporate usages (allowed in narrow, specific cases): engagement (OK in "engagement rates"), positioning (OK in "brand positioning" if from the scraped content), space (OK only as literal room/venue), entering, penetrating, stretching into.

(mood-board and craft — because you are NOT writing as a creative peer; that framing reads as presumptuous. lead gen — prefer "growth systems" or similar.)

## Banned phrases (do NOT use any of these)

usually means, typically, which suggests, points to, indicates, feels like, the gap between, this tells me, that tends to, which means, cited as, driver behind, member profile active, uniquely positioned, transformation journey, pursuing expansion, market entry, market expansion.

## BANNED vs ALLOWED — concrete examples

BANNED (consultant voice — do NOT produce):

- "Inkblot Design joined the Stellenbosch Network (member profile active ~1 month ago), signalling formal local ecosystem engagement."
- "XYZ's positioning in the premium segment indicates strong brand equity."
- "The portfolio signals a pursuing-expansion posture."

ALLOWED (warm observational voice):

- "Spent the morning with your Iroko work. The modular 'organised structure' icon instead of the usual sustainability visuals — sharp move."
- "Saw Inkblot joined the Stellenbosch Network about a month ago. Always a good sign when a design shop starts showing up in local rooms."
- "Came across the Ravenna case study. Two things jumped out: the '3x pipeline' framing and the client quote underneath. Really sharp work."

## Banned fragments

http, calendly, .com/

## Output format

Strict JSON, no prose, no code fences:

{{"icebreaker": "<multi-line content>"}}

Preferred: 2 sentences, total 20-60 words. If the citable details give only ONE strong observation, 1 sentence is acceptable — DO NOT fabricate a second observation to pad length. The second sentence (when present) is a warm HUMAN reaction to the first, not a strategy analysis and not a new fact. Separate sentences with `\n\n` (double newline = paragraph break) OR `\n` (single newline). DO NOT use em dashes (—). Use a comma, period, or "and"/"but" to join clauses.

(The format spec still announces 2-3 sentences / 40-70 words as the historical target; the looser bound above takes precedence when only one observation is available.)

Example (Tier 4 style — mirror this exact shape):

{{"icebreaker": "Spent the morning with your Iroko work. Two things jumped out: the modular \"organised structure\" icon instead of the usual sustainability visuals, and \"Infrastructure-grade nature restoration\" sitting underneath it. Really sharp work."}}

If the citable details don't give you a real named client or project, return {{"icebreaker": ""}} instead.
