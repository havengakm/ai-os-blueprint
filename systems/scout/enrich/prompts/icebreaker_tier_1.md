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

## NO founding year, NO tenure (HARD)

NEVER reference founding year, anniversary year, or company tenure. Banned shapes: "founded in YYYY", "since YYYY", "been at this for X years", "decade-plus", "over a decade in this space". Tenure is not an icebreaker.

## Shape — situation-connect, not compliment (HARD)

ONE specific reference to the post topic in the prospect's own words. If a second sentence follows, it MUST extend the topic with a real-world CONSTRAINT, FRICTION, or shared OBSERVATION — NOT praise the post or speaker. Total 15-45 words.

Compliment shapes ("genuinely sharp", "topic of the quarter", "really hit", "stands out") are rejected. The payload sentence should sound like another founder's reply, not a fan's. Showing we live the same problem, not that we admired the post.

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

Compliment shapes (HARD — Slice 35 ban): "is a clean way to", "is a nice call", "is a sharp move", "really clean", "actually made me rethink", "hits different", "that lands", "does a lot of work", "actually sells itself", "real talent", "genuinely impressive", "stands out", "spot on", "nailed it", "topic of the quarter". The second sentence (when present) sounds like another founder's reply, not a fan's reaction.

Diagnostic phrases: usually means, typically, which suggests, points to, indicates, feels like, this tells me, that tends to, which means, cited as, driver behind, member profile active, uniquely positioned, transformation journey, pursuing expansion, market entry, market expansion.

## Opening verb — STRICT whitelist

The icebreaker MUST start with one of: `Saw`, `Noticed`, `Read`, `Caught`. Nothing else. No "Came across", no "Spent the morning with".

## Output format

Strict JSON, no prose, no code fences:

{{"icebreaker": "<single-line content>"}}

15-45 words. Use a period or comma to join clauses. NEVER an em-dash.

## BANNED vs ALLOWED — concrete examples

Examples (Tier 1 style — situation-connect, not compliment):

ALLOWED (topic + shared friction or counter-observation):
{{"icebreaker": "Saw the Salesforce demo-crashing rant. The CRM demo failure usually isn't the seat count — it's the integration list growing past what the SE can hold in their head."}}

{{"icebreaker": "Noticed the thread about clients ghosting mid-project. Mid-project ghosting almost always traces back to the original scope being signed off the wrong stakeholder, not anything on the agency side."}}

{{"icebreaker": "Read the post about SDR burnout. The burnout cycle usually accelerates when activity targets get raised before the lead source ROI gets re-tested."}}

BANNED (will be rejected — compliment shape):
- "Saw the Salesforce rant. Topic of the quarter, genuinely." — fan reaction.
- "Noticed the post about clients ghosting. Said out loud what everyone was thinking." — flattery.
- "Read the SDR burnout post. Hits different." — empty praise.
- "Ngl your post last week on clients ghosting said out loud what I think everyone's feeling — sharp positioning."
- "Came across your post about Salesforce. Two things stuck with me, ngl."

If you can't extend the topic with a real friction or counter-observation (just react to it), return {{"icebreaker": ""}} instead.
