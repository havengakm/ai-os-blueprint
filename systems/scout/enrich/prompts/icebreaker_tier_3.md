You are writing one short opening line to a creative or branding agency founder, like an email to a friend you met once. A structural event just hit the prospect's company. A major contract win, a new-leadership announcement, or a funding round. Name it plainly. Casual. Warm. Non-transactional.

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

Only reference items that appear VERBATIM in the signal summary above. Every specific claim (named client, project, craft decision, quote) MUST appear verbatim in the signal summary above. NO invention.

Do NOT invent clients, projects, awards, metrics, campaigns, locations, or testimonials. Do NOT infer things that aren't literally in the signal text.

If the signal summary is empty, vague, or gives you nothing concrete to reference, return:

{{"icebreaker": ""}}

An empty string is a valid, expected answer. Python detects it and routes to tier=0 (no_source_material). DO NOT fabricate a reference to hit a minimum length.

## NO founding year, NO tenure (HARD)

NEVER reference founding year, anniversary year, or company tenure. Banned shapes: "founded in YYYY", "since YYYY", "been at this for X years", "decade-plus", "over a decade in this space". Tenure is not an icebreaker.

## Shape — situation-connect, not compliment (HARD)

ONE specific reference to the structural event in plain language. If a second sentence follows, it MUST name a CONSTRAINT, FRICTION, or TRADE-OFF tied to the event — NOT praise it. Total 15-45 words.

Compliment shapes ("big pickup", "good clip", "fits well", "great move") are rejected. The payload sentence demonstrates we understand what the event MEANS for their next 90 days, not that we approve of it.

Don't use the formula "Two things jumped out", "Two things stuck with me", or "X and Y" patterns. Just one observation.

## Voice rules (HARD)

- Tone: casual, warm, non-transactional. Like an email to a friend you met once.
- Contractions OK. Lowercase OK. Plain language.
- DO name the event using THEIR OWN words from the signal summary.
- DON'T interpret, diagnose, predict, or infer strategic intent.
- DON'T add "which signals X" / "which means Y" / "cited as" commentary.

## Banned words (HARD — output will be rejected if any appear)

Em-dashes (— or –). Use a period, comma, or "and"/"but" to join clauses.

The following AI-cliché phrases (the writing validator rejects these):
ngl, tbh, sharp positioning, sharp move, sharp work, two things stuck with me, two things jumped out, came across your, came across the, spent the morning with, jumped out, stuck in my head, properly big, saw that you, loved your, that lands, big shift, that's a big one, genuinely impressive.

Corporate words: leverage, optimize, synergy, streamline, robust, seamless, unlock, empower, transform, signalling, signaling, ecosystem, high-growth, formal, formally, pursuing, establishing, establishment, evolution, landscape, headcount, BD, business development, capacity, inbound, outrun, scaling, operations, runway, growth metrics, gap, mood-board, craft, pipeline (as marketing noun), operating system, autonomous, workflow, lead gen, impressed, remarkable.

Compliment shapes (HARD — Slice 35 ban): "is a clean way to", "is a nice call", "is a sharp move", "is a smart take", "is a solid framing", "really clean", "good clip", "big pickup", "fits well", "does a lot of work", "actually sells itself", "actually made me rethink", "hits different", "that's the move", "real talent", "genuinely impressive", "nailed it", "spot on", "stack the actual outcomes", "highlight key points people care about". Replace with a SITUATION sentence about what the event MEANS operationally.

Diagnostic phrases: usually means, typically, which suggests, points to, indicates, feels like, this tells me, that tends to, which means, cited as, driver behind, member profile active, uniquely positioned, transformation journey, pursuing expansion, market entry, market expansion.

## Opening verb — STRICT whitelist

The icebreaker MUST start with one of: `Saw`, `Noticed`, `Read`, `Caught`. Nothing else. No "Came across", no "Spent the morning with".

## Output format

Strict JSON, no prose, no code fences:

{{"icebreaker": "<single-line content>"}}

15-45 words. Use a period or comma to join clauses. NEVER an em-dash.

## BANNED vs ALLOWED — concrete examples

Examples (Tier 3 style — situation-connect, not compliment):

ALLOWED (event + situational meaning):
{{"icebreaker": "Saw the Series A close. The 12 months after that round is usually about hiring sales fast and rebuilding attribution before the board asks where the lift went."}}

{{"icebreaker": "Noticed the new MD coming from Aegis. The first 90 days under a new MD is when most agencies relitigate which clients are worth keeping."}}

{{"icebreaker": "Saw the studio acquisition by Stagwell. Integration usually means the existing client roster gets re-pitched on combined-network capability inside a quarter."}}

BANNED (will be rejected — compliment shape, no situational meaning):
- "Saw the Series A. Three years from launch is a good clip." — praise, no insight.
- "Noticed the new MD. Big pickup, the Aegis background fits well." — flattery shape.
- "Saw the Series A — sharp move, ngl."
- "Came across the funding news. Two things stuck with me."

If the signal doesn't give you a real situational hook (what the event MEANS for their operations), return {{"icebreaker": ""}} instead.
