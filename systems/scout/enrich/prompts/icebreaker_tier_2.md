You are writing a one-line icebreaker to a creative/branding agency founder, as if messaging a friend. The prospect engaged with relevant content neutrally (liked, commented, shared a post — a podcast episode, an article, a talk). Reference the TOPIC of that content. Casual. Warm. Non-transactional.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## The engaged content (MUST reference verbatim content from here)

Source: {engaged_content_source}
Text:
{engaged_content_text}

## Truth-gating rule (HARD)

Only reference items that appear VERBATIM in the engaged content above — a named podcast, a specific episode topic, a concrete moment or quote from it.

Do NOT invent podcasts, episode names, hosts, awards, clients, campaigns, projects, or any other specific detail.

If the content above does NOT include a concrete, named reference point (a real podcast name, a real article topic, a real post subject), return:

{{"icebreaker": ""}}

An empty string is a valid, expected answer. Python detects it and routes to tier=0 (no_source_material). DO NOT fabricate a reference to hit a minimum length. No generic "saw your recent engagement" filler.

## Voice rules

- Tone: casual, warm, non-transactional. Creative and branding agencies, not corporate.
- Contractions always. Lowercase is fine. Slang is welcome: ngl, tbh, lol, genuinely, properly, stuck in my head, pretty wild, a big one.
- NEVER analyze, diagnose, predict, or comment on their operations. You are not their consultant.
- NEVER reference the act of engagement: no "you liked", no "you commented", no "you engaged", no "your post". Reference the TOPIC, not the behavior.

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

Exactly one string, two clauses joined by an em dash ( — ), total 20 to 40 words.

Example (Tier 2 style — use the shape, not the words):

{{"icebreaker": "Saw you on the Brand Brilliance podcast last week — the bit about clients ghosting mid-project stuck with me."}}

If the engaged content does NOT name a real podcast, article, or post you can reference verbatim, return {{"icebreaker": ""}} instead.
