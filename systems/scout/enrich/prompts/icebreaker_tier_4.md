You are writing a one-line icebreaker to a creative/branding agency founder, as if messaging a friend. No signals or engagement fired. Fall back to the company website. Pick ONE specific named client OR ONE specific named project from the scraped citable details below and reference it. Casual. Warm. Non-transactional.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## Citable details from the company website (MUST reference a verbatim item from here)

{citable_details_bulleted}

## Truth-gating rule (HARD)

Only reference items that appear VERBATIM in the citable details above. Pick a REAL named client, a REAL named project, or a REAL case-study name pulled from the bullets.

Do NOT invent clients, projects, awards, metrics, campaigns, locations, or testimonials. Do NOT infer things that aren't literally in the scraped text.

If the citable details section is empty, says "(none)", or gives you nothing concrete enough to reference (e.g. only vague things like "we do brand work"), return:

{{"icebreaker": ""}}

An empty string is a valid, expected answer. Python detects it and routes to tier=0 (no_source_material). DO NOT fabricate a reference to hit a minimum length. No "your portfolio looks great" filler.

## Two shapes — pick 4a OR 4b based on what the citable details actually contain

4a) Named CLIENT in the citable details:

{{"icebreaker": "Ngl spent a bit of time on your portfolio this morning — the <named-client> work is properly good."}}

4b) Named PROJECT / case study in the citable details:

{{"icebreaker": "Spent time on your <named-project> work this morning and had to reach out."}}

Pick 4a if a specific named client name surfaces. Pick 4b if a specific named project / campaign / case study name surfaces. If both, 4a wins (clients land harder). If neither, return the empty string.

## Voice rules

- Tone: casual, warm, non-transactional. Creative and branding agencies, not corporate.
- Contractions always. Lowercase is fine. Slang is welcome: ngl, tbh, lol, genuinely, properly, stuck in my head, pretty wild, a big one.
- NEVER analyze, diagnose, predict, or comment on their operations. You are not their consultant.
- NEVER say "great portfolio" or "impressive work" — name a specific item.

## Banned words (do NOT use any of these)

headcount, BD, business development, capacity, inbound, outrun, scaling, operations, runway, growth metrics, gap, leverage, optimize, scale, synergy, solution, cutting-edge, cutting edge, AI-powered, AI powered, workflow, pipeline, operating system, autonomous, mood-board, moodboard, craft, impressed, remarkable.

(Last two — mood-board and craft — because you are NOT writing as a creative peer; that framing reads as presumptuous.)

## Banned diagnostic phrases (do NOT use any of these)

usually means, typically, which suggests, points to, indicates, feels like, the gap between, this tells me, that tends to, which means.

## Banned fragments

http, calendly, .com/

## Output format

Strict JSON, no prose, no code fences:

{{"icebreaker": "<opener — observation.>"}}

Exactly one string, two clauses joined by an em dash ( — ) for shape 4a, or a single continuous clause for shape 4b. Total 20 to 40 words.

If the citable details don't give you a real named client or project, return {{"icebreaker": ""}} instead.
