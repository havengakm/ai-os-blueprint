You are writing the {{icebreaker + bridge}} block of a cold email to a creative or branding agency founder. Follow the canonical doctrine in skills/cold-email/references/icebreaker-framework.md verbatim. The output is two paragraphs that flow naturally into the body's pitch.

A structural event just hit the prospect's company (a major contract win, new-leadership announcement, funding round, acquisition, expansion). Name it plainly. Connect to a TIMING-based bridge.

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

Only reference items that appear VERBATIM in the signal summary above. NO invention. NO speculation about clients, projects, or financial details that aren't literally in the signal text.

If the signal summary is empty, vague, or doesn't give you something concrete to reference, return:

{{"icebreaker": ""}}

Empty is the correct, expected answer. Python detects it and routes to tier=0 (no_source_material).

## NO founding year, NO tenure (HARD)

Never reference founding year, anniversary year, or company tenure of any kind. Tenure is not an icebreaker.

## NO critique, NO diagnosis, NO unsolicited advice (HARD)

Never tell the prospect what is hard about their work, what most teams miss, what their agency lacks, or what they should consider. Banned shapes:

- "the hard part is" / "the trick is" / "usually means" / "is usually [verbing]"
- "most agencies (can't|don't|won't|miss)"
- "where most teams (fail|struggle|stop)"
- "your agency doesn't seem to have"
- "you might want to (try|consider)"
- "have you (tried|considered)"
- "the (real|actual) (question|issue) is"

## NO empty compliments (HARD)

Banned exact shapes: "is a clean way to", "is a nice call", "stack the actual outcomes", "highlight key points people care about", "does a lot of work", "actually sells itself", "real talent", "hits different", "that lands", "nailed it", "spot on", "genuinely impressive".

## Banned words (per framework)

impressed, remarkable, exceptional, incredible, amazing, "I came across", "I stumbled upon", "I wanted to reach out", "I hope this finds you well", "I'd love to connect", leverage, utilise, optimise, synergy, alignment, strategic, "just wanted to", "quick question", headcount, BD, business development, capacity, runway, gap, signalling, ecosystem, mood-board, lead gen, craft (as positive marketing noun) (as opener).

NEVER em-dashes (— or – or --). Restructure into two short sentences if you would.

## ALLOWED reaction words (sparingly)

saw / noticed / read / heard / saw the news / sharp / clean / solid / smart move / stood out / caught my eye / honestly / genuinely (sparingly) / hard to argue with / not easy.

## Opening — vary the structure

Most openers start with: `Saw`, `Noticed`, `Read`, `Heard`, `Caught`. Variations from the framework: open with a fact ("Series A close announced last Tuesday"), open with the reaction ("Not an easy hire to land"), open with a question ("How did you land [client]? Not easy in that space"). Vary across batches.

NEVER open with: `Came across`, `Spent the morning with`, `I'm reaching out`, `I'm reaching out because`, the company name itself.

## Output format — TWO paragraphs (icebreaker + bridge)

**Paragraph 1 (event + light reaction)**: ONE specific reference to the structural event in plain language. Optional 5-15 word reaction sentence. 15-45 words total.

**Paragraph 2 (bridge)**: ONE sentence connecting the event to why we're reaching out, using a TIMING-based bridge. 8-20 words. The bridge MUST extend the same thread.

Strict JSON, no prose, no code fences:

{{"icebreaker": "<paragraph 1>\\n\\n<paragraph 2 / bridge>"}}

## Bridge templates (timing-based, pick one that fits)

For a funding round:
- "If pipeline is part of that plan, this might be well timed."
- "That's usually when sales infrastructure becomes the bottleneck."

For a leadership change:
- "Usually a moment to look at how new business is coming in."
- "That kind of move tends to put pipeline-build under fresh review."

For a contract win or expansion:
- "Pipeline usually needs to keep up with a move like that."
- "Looks like the kind of growth that's worth backing with the right outbound."

The bridge MUST extend the event. Don't pivot to an unrelated topic. Banned bridges:
- "Anyway, the reason I'm reaching out..."
- "Speaking of which..."
- "On a different note..."

## Formula (per framework)

[Saw/Noticed/Read/Heard] + [specific event] + [light reaction] + paragraph break + [timing-based bridge]

## ALLOWED full examples

{{"icebreaker": "Saw the Series A close last month. Three years from launch to that round is a good clip.\\n\\nIf pipeline is part of that plan, this might be well timed."}}

{{"icebreaker": "Saw the new MD coming from Aegis. Not an easy hire to land.\\n\\nUsually a moment to look at how new business is coming in."}}

{{"icebreaker": "Heard about the studio acquisition by Stagwell.\\n\\nPipeline usually needs to keep up with a move like that."}}

## BANNED full examples (will be rejected)

- "Saw the Series A. Sharp move, ngl." — formulaic AI-cliche shape.
- "Saw the new MD. Big pickup, the Aegis background fits well." — flat-affect compliment, no bridge.
- "Saw the funding news. The hard part is usually scaling sales fast enough." — DIAGNOSIS DISGUISED AS RESEARCH. Tells them what's hard about their next phase.
- "Saw the Series A — three years from launch is a good clip." — em-dash slip.
- "Came across the funding news this morning." — banned opener verb.

If the signal doesn't give you a verbatim event to reference plus a sensible timing bridge, return {{"icebreaker": ""}} instead.
