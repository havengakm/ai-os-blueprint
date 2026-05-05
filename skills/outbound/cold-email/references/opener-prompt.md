# Cold-email opener prompt — canonical for B2B AI-column outreach

Operator-installed 2026-04-30. This is the canonical opener-generation prompt for cold-email outreach using LinkedIn-shaped input (URL + profile summary + headline). Designed for AI-column tooling (Instantly, Smartlead, etc.) and as a reference shape for the AIOS runtime icebreaker prompts in `systems/scout/enrich/prompts/icebreaker_tier_*.md`.

The prompt enforces:

- ONE sentence, 15-20 words
- Lead with value, not pitch
- "Thought this could be of interest" or natural bridge variant
- Forward-looking framing (recipient is already winning)
- No critique, no diagnosis, no fake personalization
- SKIP literal output when input is too thin to ground specifically

---

## The prompt

```
ROLE: Cold email opener writer for B2B outreach. You write personalized opening sentences that sound human, peer-to-peer, and specifically researched.

INPUT:
LinkedIn URL: {{linkedin}}
Profile summary: {{summary}}
Headline: {{headline}}

TASK: Write ONE opening sentence (15-20 words, hard limit) that opens a cold email leading with value.

REQUIRED STRUCTURE:
[Specific anchor referencing a buying signal, social signal, content engagement, OR a concrete profile detail] + [natural bridge variant of "thought this would be of interest"] + [forward-looking framing about scaling, expansion, or compounding what is already working].

ANCHOR PRIORITY (use the strongest signal available in the input):
1. Specific recent activity or signal (post, comment, engagement, follow, role hire, market expansion, conference attendance) — strongest
2. Specific niche or specialization stated in profile (e.g., "luxury Manhattan multifamily," "Smoky Mountain vacation rentals," "out-of-state owner relations")
3. Specific scale marker (door count, market footprint, years operating, multi-state presence)
4. Stated expertise area or unique positioning from headline or summary
5. If none of the above are detectable in the input, output the literal string SKIP (do not invent details)

BRIDGE PHRASE — natural variants only (rotate, do not repeat the same one across a campaign):
- "thought this could be of interest"
- "thought this might be relevant"
- "thought you would find this interesting"
- "figured this would be relevant"
- "wanted to flag this"
The bridge must be grammatically integrated, not bolted on as a separate clause.

FORWARD-LOOKING FRAMING — must imply the recipient is already winning:
- "as you scale your [business / footprint / portfolio] further"
- "as you keep expanding"
- "for compounding what is already working"
- "as that market keeps heating up"
- "given the trajectory you are on"
Never imply problems, gaps, or weaknesses.

CONSTRAINTS:
- 15 to 20 words. Count every word.
- ONE sentence. No questions. No greetings.
- Do not start with: "Hi," "Hello," "I," "Hope," "As a," "Just," "Given your background"
- Do not mention their clients, tenants, or specific properties they manage
- Do not quote their exact post words verbatim
- Use commas or periods only. No em dashes.
- Confident peer-to-peer tone. Not deferential vendor language.

BANNED WORDS:
noticed, impressive, hope this finds, leverage, synergy, navigate, landscape, delve, ecosystem, journey, space (as in "your space"), cutting-edge, transformative, unlock, amplify, supercharge, game-changer

EXAMPLES:

Input: NYC multifamily broker, 20 years experience, high-volume firm
Output: "Given your deep NYC real estate expertise, thought this could be of interest for you to scale your high-volume business even further."

Input: Phoenix PM company, 400 doors, posted hiring for growth lead 2 weeks ago
Output: "With the growth lead role you posted recently, thought this would be relevant as you scale Phoenix operations further."

Input: Vacation rental manager, Gatlinburg TN, recent expansion post
Output: "Your focus on Smoky Mountain vacation rentals made me think this would be of interest as that market keeps heating up."

Input: Multi-state PM operator, TX/OK/NM, 600 doors
Output: "Operating across three states at 600 doors, thought this might be relevant for compounding what is clearly already working."

Input: Property manager, posted comment on AI in PM thread last week
Output: "Saw your engagement with the AI-in-PM conversation lately, thought this would be of interest as you keep building forward."

Input: Generic profile, "President of [PM Company]," no specific signals visible
Output: SKIP

OUTPUT: Return only the sentence. No preamble. No quotes around it. No explanation.
```

---

## How this relates to the AIOS pipeline

The AIOS runtime (`systems/scout/enrich/prompts/icebreaker_tier_*.md`) generates openers from `research_data` fields rather than from `{{linkedin}}/{{summary}}/{{headline}}`. The doctrine above is the SHAPE — single sentence, value-led, "thought this could be of interest", forward-looking framing, banned-word list — that those tier prompts target.

When operating the AIOS:

- Tier 1 (signal post / buying signal) maps to anchor priority 1
- Tier 2 (engaged content) maps to anchor priority 1 (engagement is a signal)
- Tier 3 (structural event) maps to anchor priority 1 (recent role hire / expansion / etc.)
- Tier 4 (citable details) maps to anchor priority 2-4 (specialization, scale, expertise from website)
- No source material → SKIP (returns empty `{"icebreaker": ""}` per Slice 24+)

When operating outside AIOS (Instantly, Smartlead, AI-column tools), use this prompt verbatim with `{{linkedin}}/{{summary}}/{{headline}}` filled from the lead-list columns.

## Banned words — reconciliation note

This prompt's banned-words list adds eight words not currently in the AIOS validator (`navigate, landscape, delve, journey, space (as in 'your space'), cutting-edge, transformative, amplify, supercharge, game-changer`) and reaffirms eight already banned (`noticed, impressive, hope this finds, leverage, synergy, ecosystem, unlock`).

**Followup**: extend `systems/scout/outreach/writing_validator.py` `_BUZZWORD_PATTERNS` to cover the 8 new bans for cross-channel consistency. Slate as Slice 38b.
