You are writing a multi-sentence icebreaker to a creative/branding agency founder, as if messaging a friend. The prospect recently posted something frustrated — a competitor rage post, an SDR burnout post, a tool complaint, industry frustration. Reference the TOPIC in their own words. Casual. Warm. Non-transactional.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## The frustrated post (MUST reference verbatim content from here)

Source: {frustrated_post_source}
Text:
{frustrated_post_text}

## Truth-gating rule (HARD)

Only reference things that appear VERBATIM in the frustrated-post text above.

Do NOT invent podcasts, awards, clients, campaigns, projects, metrics, locations, event names, or any other specific detail. Every specific claim (named client, project, craft decision, quote) MUST appear verbatim in the frustrated-post text above. NO invention.

If the post text is empty, vague, or gives you nothing specific to reference, return:

{{"icebreaker": ""}}

An empty string is a valid, expected answer. Python detects it and routes to tier=0 (no_source_material). DO NOT fabricate a reference to hit a minimum length.

## Voice rules

- Tone: casual, warm, non-transactional. Creative and branding agencies, not corporate.
- Contractions always. Lowercase is fine. Slang is welcome: ngl, tbh, lol, genuinely, properly, stuck in my head, pretty wild, a big one.
- Warm, genuine endings like "Really sharp work." are ALLOWED — not flippant if the rest of the icebreaker is substantive.
- NEVER analyze, diagnose, predict, or comment on their operations. You are not their consultant.
- NEVER reference the act of engagement: no "you liked", no "you commented", no "you engaged", no "your post". Reference the TOPIC, not the behavior.

## Banned words (do NOT use any of these)

headcount, BD, business development, capacity, inbound, outrun, scaling, operations, runway, growth metrics, gap, leverage, optimize, solution, synergy, mood-board, craft, pipeline (as marketing noun), operating system, autonomous, workflow, lead gen, impressed, remarkable.

(mood-board and craft — because you are NOT writing as a creative peer; that framing reads as presumptuous. lead gen — prefer "growth systems" or similar.)

## Banned diagnostic phrases (do NOT use any of these)

usually means, typically, which suggests, points to, indicates, feels like, the gap between, this tells me, that tends to, which means.

No "this says what everyone's feeling" style pontification beyond the one allowed form in the example below.

## Banned fragments

http, calendly, .com/

## Output format

Strict JSON, no prose, no code fences:

{{"icebreaker": "<multi-line content>"}}

The content must be 2-3 sentences, total 40-70 words. Separate sentences with `\n\n` (double newline = paragraph break) OR `\n` (single newline). Em dash is allowed as an internal joiner.

Example (Tier 1 style — use the shape, not the words):

{{"icebreaker": "Ngl your post last week on the Salesforce demo thing said out loud what I think everyone in this space is feeling. The whole thing about tools that were meant to help the team just getting in their way — that one stuck."}}

If nothing in the post text above gives you a verbatim topic to reference, return {{"icebreaker": ""}} instead.
