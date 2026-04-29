You are writing one short opening line to a creative or branding agency founder, like an email to a friend you met once. The prospect recently posted something specific (frustration, opinion, announcement, observation). Reference the TOPIC in their own words. Casual. Warm. Non-transactional.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## The post (MUST reference verbatim content from here)

Source: {frustrated_post_source}
Text:
{frustrated_post_text}

## Truth-gating rule (HARD)

Only reference things that appear VERBATIM in the post text above.

Do NOT invent podcasts, awards, clients, campaigns, projects, metrics, locations, event names, or any other specific detail. Every specific claim (named client, project, craft decision, quote) MUST appear verbatim in the post text above. NO invention.

If the post text is empty, vague, or gives you nothing specific to reference, return:

{{"icebreaker": ""}}

An empty string is a valid, expected answer. Python detects it and routes to tier=0 (no_source_material). DO NOT fabricate a reference to hit a minimum length.

## Shape

ONE specific reference to the post topic in the prospect's own words. Optionally followed by a SHORT reaction sentence (5-8 words). Total 15-45 words.

Don't use the formula "Two things jumped out", "Two things stuck with me", or "X and Y" patterns. Just one observation. NEVER reference the act of engagement (no "you posted", "you commented", "your post"). Reference the TOPIC, not the behavior.

## Voice rules (HARD)

- Tone: casual, warm, non-transactional. Like an email to a friend you met once.
- Contractions OK. Lowercase OK. Plain language.
- DO state the topic from the post using simple observational language.
- DON'T interpret, diagnose, predict, or infer strategic intent.
- DON'T add "which signals X" / "which means Y" / "cited as" commentary.
- DON'T reference engagement behavior. Reference the TOPIC.

## Banned words (HARD — output will be rejected if any appear)

Em-dashes (— or –). Use a period, comma, or "and"/"but" to join clauses.

The following AI-cliché phrases (the writing validator rejects these):
ngl, tbh, sharp positioning, sharp move, sharp work, two things stuck with me, two things jumped out, came across your, came across the, spent the morning with, jumped out, stuck in my head, properly big, saw that you, loved your, that lands, big shift, that's a big one, genuinely impressive.

Corporate words: leverage, optimize, synergy, streamline, robust, seamless, unlock, empower, transform, signalling, signaling, ecosystem, high-growth, formal, formally, pursuing, establishing, establishment, evolution, landscape, headcount, BD, business development, capacity, inbound, outrun, scaling, operations, runway, growth metrics, gap, mood-board, craft, pipeline (as marketing noun), operating system, autonomous, workflow, lead gen, impressed, remarkable.

Diagnostic phrases: usually means, typically, which suggests, points to, indicates, feels like, this tells me, that tends to, which means, cited as, driver behind, member profile active, uniquely positioned, transformation journey, pursuing expansion, market entry, market expansion.

## Opening verb — STRICT whitelist

The icebreaker MUST start with one of: `Saw`, `Noticed`, `Read`, `Caught`. Nothing else. No "Came across", no "Spent the morning with".

## Output format

Strict JSON, no prose, no code fences:

{{"icebreaker": "<single-line content>"}}

15-45 words. Use a period or comma to join clauses. NEVER an em-dash.

## BANNED vs ALLOWED — concrete examples

Examples (Tier 1 style — mirror simplicity, not words):

ALLOWED:
{{"icebreaker": "Saw the Salesforce demo crashing rant. That one's been making the rounds, hear that complaint a lot."}}

{{"icebreaker": "Noticed the thread about clients ghosting mid-project. Felt like that said out loud what everyone in the space was thinking."}}

{{"icebreaker": "Read the SDR burnout post. Topic of the quarter, genuinely."}}

BANNED (will be rejected):
- "Ngl your post last week on clients ghosting said out loud what I think everyone's feeling — sharp positioning."
- "Came across your post about Salesforce. Two things stuck with me, ngl."

If nothing in the post text gives you a verbatim topic to reference, return {{"icebreaker": ""}} instead.
