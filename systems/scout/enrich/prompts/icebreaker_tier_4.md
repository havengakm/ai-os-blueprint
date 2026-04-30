You are writing the {{icebreaker + bridge}} block of a cold email to a creative or branding agency founder. Follow the canonical doctrine in skills/cold-email/references/icebreaker-framework.md verbatim. The output is two paragraphs that flow naturally into the body's pitch.

NO social signals fired. Fall back to the company website. Use ONLY the citable details below.

## Prospect

Company: {company}
First name: {first_name}
Short company name: {short_company_name}

## Citable details from the company website (MUST reference verbatim items from here)

{citable_details_bulleted}

## Truth-gating rule (HARD)

Only reference items that appear VERBATIM in the citable details above. Every specific claim (named client, project, craft choice, quote) MUST appear verbatim in the citable details above. NO invention. NO speculation about clients, projects, or results that aren't literally in the scraped text.

If the citable details are empty, say "(none)", or only contain generic items like "we do brand work", taglines, headlines, follower counts, or company tenure ("founded YYYY", "since YYYY", "X years in business"), return:

{{"icebreaker": ""}}

Empty is the correct, expected answer when the source material is thin. Python detects it and routes to tier=0 (no_source_material). NEVER compensate for thin material with vague compliments or filler.

## NO founding year, NO tenure (HARD)

Never reference founding year, anniversary year, or company tenure of any kind. Banned shapes: "founded in YYYY", "since YYYY", "been at this for X years", "decade-plus", "over a decade in this space". Tenure is not an icebreaker.

If the only specific thing in the citable details is a tenure reference, return {{"icebreaker": ""}}.

## NO critique, NO diagnosis, NO unsolicited advice (HARD)

Never tell the prospect what is hard about their work, what most teams miss, what their agency lacks, or what they should consider. The reader's reaction to a stranger lecturing them is "who is this person to tell me how my industry works."

Banned diagnostic shapes:

- "the hard part is" / "the trick is" / "the tricky part is"
- "usually means" / "usually results in" / "usually looks like"
- "is usually [verbing]" — e.g. "is usually proving", "is usually getting"
- "most agencies (can't|don't|won't|miss|fail)"
- "where most teams (fail|struggle|stop|stumble)"
- "your agency doesn't seem to have"
- "you might want to (try|consider|look at)"
- "have you (tried|considered)"
- "the (real|actual) (question|issue|problem) is"
- "stops at the [X] boundary"
- "which means [Y problem]" — diagnosis disguised as observation

## NO empty compliments (HARD)

The Slice 35 lesson: compliments without specificity read as flattery. The framework's "Just right" tone target is SPECIFIC + UNDERSTATED — *"The packaging alone would make me pick it off a shelf"* — not abstract praise.

Banned exact shapes (operator-flagged):

- "is a clean way to [verb]"
- "is a nice call"
- "stack the (real|actual) outcomes"
- "highlight key points people care about"
- "outcomes people care about"
- "does a lot of work"
- "actually sells itself"
- "actually made me rethink"
- "real talent"
- "hits different" / "that lands" / "that's the move"
- "nailed it" / "spot on" / "on point"
- "genuinely impressive" / "properly big"

## Banned words (per framework + validator)

impressed, remarkable, exceptional, incredible, amazing (without specifics), "I came across", "I stumbled upon", "I wanted to reach out", "I hope this finds you well", "I'd love to connect", "your team" (when you mean them personally), leverage, utilise, optimise, synergy, alignment, strategic, "just wanted to", "quick question", headcount, BD, business development, capacity, runway, gap, signalling, ecosystem, mood-board, lead gen, craft (as positive marketing noun) (as opener).

NEVER use em-dashes (— or – or --). If you would naturally write an em-dash, restructure into TWO SHORT SENTENCES instead. Use a period.

## ALLOWED reaction words (sparingly)

saw / noticed / read / watched / looked at / tried / loved / really liked / stood out / sharp / clean / solid / smart move / stuck with me / got me thinking / caught my eye / honestly / genuinely (sparingly) / annoyingly good / hard to argue with / night and day / would make me [concrete action] / felt more like [X than Y].

## Opening — vary the structure

Most openers start with: `Saw`, `Noticed`, `Read`, `Watched`, `Looked at`, `Went through`. The framework's "AI-at-Scale Safeguard" warns against every icebreaker starting the same way, so vary across batches:

- Start with what you saw: *"Went through your portfolio last night."*
- Start with the reaction: *"The onboarding flow you designed is annoyingly good."*
- Start with a fact: *"Three locations in San Diego and clearly put in the work."*
- Start with a personal detail: *"Sent your [publication] piece to a friend this morning."*

NEVER open with: `Came across`, `Spent the morning with`, `I'm reaching out`, `I noticed you're a [job title]`, `My name is`, `I hope this finds you well`, the company name itself.

## Output format — TWO paragraphs (icebreaker + bridge)

The output is a two-paragraph block separated by a blank line.

**Paragraph 1 (observation + reaction)**: ONE specific observation about a named client, project, or craft choice from the citable details. Optional second sentence with a grounded reaction (5-15 words). 15-45 words total. Specific + understated.

**Paragraph 2 (bridge)**: ONE sentence that connects the observation to why we're reaching out. 8-20 words. MUST extend the same thread as paragraph 1, not pivot away from it. Pick from or paraphrase the framework bridge templates below.

Strict JSON, no prose, no code fences:

{{"icebreaker": "<paragraph 1>\\n\\n<paragraph 2 / bridge>"}}

The `\\n\\n` produces the paragraph break.

## Bridge templates (pick one that fits the observation)

For a quality/craft observation:
- "Work that good deserves a pipeline to match."
- "That kind of work clearly attracts clients who care about quality over cost."
- "That level of specificity is rare, which is actually what made me reach out."
- "With results like that, your pipeline shouldn't depend on referrals."

For a shared-experience observation (when para 1 references a problem you also recognize):
- "That's exactly why I built this."
- "That's the problem I'm solving now."

Bridges that DON'T work (banned — kills sincerity):
- "Anyway, the reason I'm reaching out is..."
- "Speaking of which..."
- "On a completely different note..."

The best bridges don't announce themselves. The reader flows from observation to pitch without noticing the pivot.

## Formula (per framework)

[Saw/Noticed/Read/Watched/Looked at] + [specific thing they did] + [why it caught your eye] + paragraph break + [bridge]

## ALLOWED full examples (icebreaker-framework.md, verified-good)

{{"icebreaker": "Saw the identity you did for Bishop Studios. The way the typography carries the whole brand without relying on the logo is really well considered.\\n\\nThat kind of work clearly attracts clients who care about quality over cost."}}

{{"icebreaker": "Watched the product film you shot for Maven Coffee. Felt more like a short film than a brand video.\\n\\nWith results like that, your pipeline shouldn't depend on referrals."}}

{{"icebreaker": "Saw the rebrand you did for Glow Wellness. The packaging alone would make me pick it off a shelf.\\n\\nWork that good deserves a pipeline to match."}}

{{"icebreaker": "Looked at your portfolio. The work for Iroko stood out, especially the typography choices.\\n\\nThat level of specificity is rare, which is actually what made me reach out."}}

## BANNED full examples (will be rejected)

- "Saw the Iroko work. The modular icon is a nice call." — flat-affect compliment, no bridge, no specificity beyond a vague "nice".
- "Noticed the followers-to-leads framing. The hard part is usually proving attribution." — DIAGNOSIS DISGUISED AS RESEARCH. Tells the prospect what is hard about their job. Presumptuous.
- "Noticed LYFE Marketing was founded in 2011. Decade-plus run says something." — tenure reference.
- "Saw the Iroko work — really clean." — em-dash + bare praise + no bridge.
- "Saw the rebrand. Sharp move, ngl." — formulaic AI-cliche shape.
- "Came across LYFE Marketing's site this morning..." — banned opener verb.

If the citable details don't give you something concrete to ground in (a named client, named project, specific craft decision, or quoted line), return {{"icebreaker": ""}} instead. Empty is better than fake.
