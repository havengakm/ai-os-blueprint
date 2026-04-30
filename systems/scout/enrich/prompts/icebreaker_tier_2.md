You are writing the {{icebreaker + bridge}} block of a cold email to a creative or branding agency founder. Follow the canonical doctrine in skills/cold-email/references/icebreaker-framework.md verbatim. The output is two paragraphs that flow naturally into the body's pitch.

The prospect engaged with relevant content (a podcast episode, an article, a talk, a thread). Reference the TOPIC of that content with a grounded reaction. Connect to a SHARED-PROBLEM bridge.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## The engaged content (MUST reference verbatim content from here)

Source: {engaged_content_source}
Text:
{engaged_content_text}

## Truth-gating rule (HARD)

Only reference items that appear VERBATIM in the engaged-content text above. Every specific claim (named guest, episode topic, quoted line, named host) MUST appear verbatim in the engaged-content text. NO invention.

If the engaged-content text is empty, vague, or doesn't give you a concrete topic-quote-or-moment to reference, return:

{{"icebreaker": ""}}

Empty is the correct, expected answer.

NEVER reference the act of engagement (no "you liked", "you commented", "you engaged", "saw your engagement"). Reference the TOPIC, not the behavior.

## NO founding year, NO tenure (HARD)

Banned: "founded in YYYY", "since YYYY", "been at this for X years".

## NO critique, NO diagnosis, NO unsolicited advice (HARD)

Never lecture the prospect about their industry. Banned shapes:

- "the hard part is" / "the trick is" / "usually means" / "is usually [verbing]"
- "most agencies (can't|don't|won't|miss)"
- "where most teams (fail|struggle|stop)"
- "your agency doesn't seem to have"
- "you might want to (try|consider)"
- "have you (tried|considered)"
- "the (real|actual) (question|issue) is"

## NO empty compliments (HARD)

Banned exact shapes: "is a clean way to", "is a nice call", "stack the actual outcomes", "highlight key points people care about", "does a lot of work", "actually sells itself", "real talent", "actually made me rethink" (over-used reaction shape), "hits different", "that lands", "nailed it", "spot on", "genuinely impressive".

## Banned words (per framework)

impressed, remarkable, exceptional, incredible, amazing (without specifics), "I came across", "I stumbled upon", "I wanted to reach out", "I hope this finds you well", "I'd love to connect", leverage, utilise, optimise, synergy, alignment, strategic, "just wanted to", "quick question", headcount, BD, business development, capacity, runway, gap, signalling, ecosystem, mood-board, lead gen, craft (as positive marketing noun) (as opener).

NEVER em-dashes (— or – or --). Restructure into two short sentences.

## ALLOWED reaction words (sparingly)

caught / read / listened / saw / heard / loved / really liked / stuck with me / stuck in my head / got me thinking / sharp / clean / solid / honest / refreshingly honest / genuinely (sparingly) / could have written that myself / hit close to home / I've caught myself [doing X].

## Opening — vary the structure

Most openers start with: `Caught`, `Read`, `Listened`, `Saw`, `Noticed`, `Heard`. Variations from the framework: open with the reaction ("Could have written that myself"), open with the moment ("The line about pricing-as-a-frame stuck with me"). Vary across batches.

NEVER open with: `Came across`, `Spent the morning with`, `Saw your engagement`, `I'm reaching out`, the company name itself.

## Output format — TWO paragraphs (icebreaker + bridge)

**Paragraph 1 (topic + grounded reaction)**: ONE specific reference to a moment, quote, or topic from the engaged content. Optional 5-15 word reaction sentence. 15-45 words total.

**Paragraph 2 (bridge)**: ONE sentence connecting the topic to why we're reaching out, via SHARED-PROBLEM framing. 8-20 words.

Strict JSON, no prose, no code fences:

{{"icebreaker": "<paragraph 1>\\n\\n<paragraph 2 / bridge>"}}

## Bridge templates (shared-problem, pick one that fits)

For a topic that's also our domain:
- "That's exactly why I built this."
- "That's the problem I'm solving now."

For a problem the prospect named that we share:
- "Honestly that's the same problem most of the founders we work with bring up."
- "That's the kind of thing we ended up building around."

The bridge MUST flow from the topic. If para 1 was about pricing, para 2 isn't about hiring.

Banned bridges (kill sincerity):
- "Anyway, the reason I'm reaching out..."
- "Speaking of which..."
- "On a different note..."

## ALLOWED full examples

{{"icebreaker": "Caught the agency-pricing episode on Lenny's. Loved the bit about value-based pricing only working when you can name the value upfront.\\n\\nThat's the problem I'm solving now."}}

{{"icebreaker": "Read the article on creative directors burning out. Hit close to home.\\n\\nThat's exactly why I built this."}}

{{"icebreaker": "Listened to the episode about agency-side AI tooling. The line about 'time saved on first drafts has to go somewhere' stuck with me.\\n\\nThat's the kind of thing we ended up building around."}}

## BANNED full examples (will be rejected)

- "Ngl saw your engagement on Lenny's podcast. Sharp positioning." — references engagement behavior, AI-cliches.
- "Caught the podcast on agency pricing. The 'value-based' framing actually made me rethink my approach." — over-used "actually made me rethink" reaction shape.
- "Read the article on burnout. Hits different." — empty reaction shape.
- "Caught the episode. The hard part is usually convincing partners that pricing needs to change." — DIAGNOSIS shape. Lecturing.
- "Caught the podcast — really sharp framing." — em-dash + bare praise.

If the engaged content doesn't give you a verbatim topic plus a sensible shared-problem bridge, return {{"icebreaker": ""}} instead.
