You are writing the {{icebreaker + bridge}} block of a cold email to a creative or branding agency founder. Follow the canonical doctrine in skills/cold-email/references/icebreaker-framework.md verbatim. The output is two paragraphs that flow naturally into the body's pitch.

The prospect recently posted something specific (a frustration, opinion, observation, or announcement). Reference the TOPIC in their own words with a grounded reaction. Connect to a SHARED-EXPERIENCE bridge.

Per the framework: this is the STRONGEST tier. The signal does most of the work — paragraph 1 can be ONE sentence. Paragraph 2 answers "why now" not "why you." No compliment needed.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## The post (MUST reference verbatim content from here)

Source: {frustrated_post_source}
Text:
{frustrated_post_text}

## Truth-gating rule (HARD)

Only reference things that appear VERBATIM in the post text above. Every specific claim MUST appear verbatim. NO invention.

If the post text is empty, vague, or gives you nothing specific to reference, return:

{{"icebreaker": ""}}

Empty is the correct, expected answer.

NEVER reference the act of posting (no "you posted", "you commented", "your post"). Reference the TOPIC, not the behavior.

## NO founding year, NO tenure (HARD)

Banned: "founded in YYYY", "since YYYY", "been at this for X years".

## NO critique, NO diagnosis, NO unsolicited advice (HARD)

Even though the prospect named a problem in their post, do NOT diagnose THEM further. Match their statement; don't extend it into critique.

Banned shapes:

- "the hard part is" / "the trick is" / "usually means" / "is usually [verbing]"
- "most (agencies|founders) (can't|don't|won't|miss)"
- "where most teams (fail|struggle|stop)"
- "you might want to (try|consider)"
- "have you (tried|considered)"
- "the (real|actual) (question|issue) is"

## NO empty compliments (HARD)

Banned exact shapes: "is a clean way to", "is a nice call", "stack the actual outcomes", "highlight key points people care about", "does a lot of work", "actually sells itself", "real talent", "hits different", "that lands", "nailed it", "spot on", "topic of the quarter".

## Banned words (per framework)

impressed, remarkable, exceptional, incredible, amazing (without specifics), "I came across", "I stumbled upon", "I wanted to reach out", "I hope this finds you well", "I'd love to connect", leverage, utilise, optimise, synergy, alignment, strategic, "just wanted to", "quick question", headcount, BD, business development, capacity, runway, gap, signalling, ecosystem, mood-board, lead gen, craft (as positive marketing noun) (as opener).

NEVER em-dashes (— or – or --). Restructure into two short sentences.

## ALLOWED reaction words (sparingly)

saw / noticed / read / loved / really liked / stuck with me / stuck in my head / got me thinking / hit close to home / could have written that myself / I've caught myself [doing X] / sharp / clean / solid / honest / refreshingly honest / hard to argue with / annoyingly accurate.

## Opening — vary the structure

Most openers start with: `Saw`, `Noticed`, `Read`, `Caught`. Variations from the framework: open with the reaction ("Could have written that myself"), open with the moment ("The line about [phrase] hit close to home"). Vary across batches.

NEVER open with: `Came across`, `Spent the morning with`, `Saw your post` (act-of-engagement reference), `I'm reaching out`, the company name itself.

## Output format — TWO paragraphs (icebreaker + bridge)

**Paragraph 1 (topic from post, in their words)**: ONE specific reference to the post topic, often one sentence. Optional 5-15 word reaction. 15-45 words total.

**Paragraph 2 (bridge)**: ONE sentence connecting the topic to why we're reaching out, via SHARED-EXPERIENCE framing. 8-20 words.

Strict JSON, no prose, no code fences:

{{"icebreaker": "<paragraph 1>\\n\\n<paragraph 2 / bridge>"}}

## Bridge templates (shared-experience, pick one that fits)

When the post named a problem we recognize:
- "That's exactly why I built this."
- "That's the problem I'm solving now."

When the post matches our own past experience:
- "I could have written that myself when I was running my agency."
- "Honestly that's the same conversation we keep having with the founders we work with."

When the post calls out a frustration we share:
- "That kind of thing is exactly what we ended up building around."

The bridge MUST flow from the topic. Banned bridges:
- "Anyway, the reason I'm reaching out..."
- "Speaking of which..."
- "On a different note..."

## ALLOWED full examples

{{"icebreaker": "Saw your post about the pipeline rollercoaster. The line about 'best month ever followed by two months of nothing' hit close to home.\\n\\nThat's exactly why I built this."}}

{{"icebreaker": "Saw your post about clients ghosting mid-project.\\n\\nHonestly that's the same conversation we keep having with the founders we work with."}}

{{"icebreaker": "Read your thread on the SDR-burnout cycle. Annoyingly accurate.\\n\\nThat's the problem I'm solving now."}}

## BANNED full examples (will be rejected)

- "Ngl your post last week on clients ghosting said out loud what I think everyone's feeling. Sharp positioning." — AI-cliche shape, formulaic.
- "Saw the post about Salesforce demo crashes. Topic of the quarter, genuinely." — empty reaction shape.
- "Read the SDR burnout post. Hits different." — empty praise shape.
- "Saw the post about clients ghosting. The hard part is usually getting the original scope signed off the right stakeholder." — DIAGNOSIS shape. Even though the prospect raised the topic, lecturing extends it the wrong way.
- "Saw your post — really hit close to home." — em-dash slip.
- "Came across your post about Salesforce." — banned opener.

If the post doesn't give you a verbatim topic plus a sensible shared-experience bridge, return {{"icebreaker": ""}} instead.
