---
name: intent-opener-writer
description: Write personalized cold email opening lines for B2B outreach using buying signals, social signals, and intent data. Use this skill whenever the user wants to write a cold email opener, generate personalized outreach lines, build prompts for tools like Clay/Instantly/Smartlead, A/B test cold email openers, or improve reply rates on outbound campaigns. Especially relevant for B2B service businesses targeting decision-makers via LinkedIn or cold email. Trigger this skill on phrases like "cold email opener," "personalization line," "intent-based outreach," "Clay prompt," "outbound opener," "cold email first line," or whenever a user asks for help writing personalized outreach openers based on profile data, signals, or activity.
---

# Intent Opener Writer

Generate cold email opening lines that reference real buying signals, social signals, or specific profile details, in a way that proves authentic timing and earns the recipient's next 5 seconds of attention.

## When to use this skill

Trigger this skill when the user wants to:

- Write opening lines for a cold email campaign
- Build a Clay/Instantly/Smartlead prompt for personalized openers at scale
- Generate multiple variants for A/B testing
- Improve reply rates on existing outbound
- Convert intent signals (hiring posts, expansion announcements, content engagement, conference attendance, forum questions) into openers

The skill works for any B2B vertical. Examples in this skill use property management as the worked vertical, but the framework applies broadly. The user can specify their own vertical and target persona.

## The core principle

The strongest cold email opener references a real, recent, time-stamped intent signal (something the prospect did or said in the last 30 days) and bridges to value with peer-to-peer language. Profile-based personalization (door count, geography, role) is fallback-tier. Signal-based personalization is the actual goal.

The opener earns the right to the rest of the email. If the signal is weak or invented, no clever bridge or framing recovers it.

## Signal hierarchy (use the strongest available)

Prioritize signals in this order. Always reach for Tier 1 first. Only fall back to lower tiers when stronger signals are not detectable in the input.

**Tier 1: Active buying intent (strongest)**
1. Hiring post for a related role (growth, marketing, ops, business development)
2. Public post about specific operational pain or frustration
3. Forum question on the user's topic (BiggerPockets, NARPM, Reddit, industry forums)
4. Market expansion or acquisition announcement
5. Recent download or registration tracked via partnership data

**Tier 2: Behavioral intent (strong)**
6. Engagement with content from competitors in the user's space
7. Conference or industry event attendance
8. Recent follow of relevant thought leaders
9. Posts about tech stack frustrations or tool changes
10. New hires into operations or growth roles (visible on company page)

**Tier 3: Topical intent (moderate)**
11. Likes or comments on relevant content within last 14 days
12. Posts about the industry within last 30 days
13. Joined a relevant LinkedIn or Slack group recently

**Tier 4: Profile-based (weakest, use only as fallback)**
14. Stated specialization, niche, or expertise area
15. Concrete scale marker (revenue, headcount, footprint, years operating)
16. Geographic market or specific role title

If none of the above are detectable in the input, output the literal string `SKIP`. Do not invent details.

## Two length variants

The skill supports two different opener styles. Pick based on the user's stated goal or campaign style.

### Variant A: 15-20 word "Bridge" Style

Structure: `[Specific anchor] + [bridge phrase] + [forward-looking framing]`

Best for: Mid-market B2B, less email-saturated audiences, formal industries (legal, finance, professional services), warmer-style outreach.

Example: "Given your deep NYC real estate expertise, thought this could be of interest for you to scale your high-volume business even further."

### Variant B: 8-14 word "Pattern Interrupt" Style

Structure: `[Specific signal observation] + [fragment reaction OR direct value statement]`

Best for: Senior buyers receiving 30+ cold emails per week, sophisticated industries (tech, AI, marketing), pattern-interrupt campaigns.

Example: "Saw the growth lead role you posted three weeks back. Different angle worth flagging."

When the user does not specify, ask which they want. If they want both, generate both for A/B testing.

## Required structure

Every opener must contain these three things:

1. **A specific time-stamped signal anchor.** Words like "Saw," "Caught," "Noticed," "With," "Given" + the specific signal. Subject must be explicit (use "you," "your," "the [specific thing]") to avoid ambiguity. Never write "Posted that role" — reads as if the writer posted it. Always write "Saw you posted that role" or "Your recent role opening."

2. **A bridge.** Variant A uses one of the bridge phrases (rotate across campaigns). Variant B may skip the bridge entirely if the structure flows naturally.

3. **A forward-looking framing.** Implies the recipient is already winning and the message adds to that trajectory. Never implies problems, gaps, or pain.

## Bridge phrases (Variant A only — rotate across campaign)

- "thought this could be of interest"
- "thought this might be relevant"
- "thought you would find this interesting"
- "figured this would be relevant"
- "wanted to flag this"

The bridge must be grammatically integrated, not bolted on as a separate sentence. Wrong: "Your portfolio is impressive. Thought this might interest you." Right: "Given your portfolio, thought this might be relevant as you keep scaling."

## Forward-looking framings (use one)

- "as you scale [further/your portfolio/your footprint]"
- "as you keep expanding"
- "for compounding what is already working"
- "as that market keeps heating up"
- "given the trajectory you are on"
- "as you build out [the new market/the next phase]"

Never use frames that imply pain: "given the challenges you face," "to help you fix," "since you are struggling."

## Banned words and patterns

These words and phrases are pattern-matched as automated outreach by sophisticated B2B buyers in 2026. Avoid all of them:

**Banned words:** noticed, impressive, leverage, synergy, navigate, landscape, delve, ecosystem, journey, space (as in "your space"), cutting-edge, transformative, unlock, amplify, supercharge, game-changer

**Banned opening phrases:** "Hope this finds you well," "Hope you are well," "Just wanted to reach out," "Quick question for you," "I came across your profile"

**Banned structures:**
- Em dashes (use commas or periods)
- Questions in the opening line (move questions to line 2 if needed)
- Greetings like "Hi," "Hello," "Hi there"
- Generic compliments without a specific anchor ("impressive work," "great firm")
- Quoting the prospect's exact post words verbatim (sounds surveillance-y)
- Mentioning the prospect's clients, customers, tenants, or specific business relationships

## Subject-line clarity rule

When the verb describes an action the prospect took, the subject must be explicit.

- Wrong: "Posted that growth lead role recently."
- Right: "Saw you posted that growth lead role recently."
- Right: "Your growth lead opening has been live a few weeks."

The leading verb ("Saw," "Caught," "Noticed") works only when followed by "you" or "your." Otherwise the reader's brain auto-fills the subject as the writer.

## Output format

When generating openers, produce them in this format:

```
[Signal type detected]
[Length variant]: [opener]
[Word count]: [N]
```

If generating multiple variants, label each by signal pattern and explain in one sentence what each one optimizes for.

If the input is too thin to identify any concrete signal or detail, output exactly:
```
SKIP
```

This lets the calling tool (Clay, Instantly, Smartlead) fall back to a non-personalized template line, which is far safer than a hallucinated specific.

## Worked examples

### Example 1: Hiring signal (Variant A)

**Input:**
- LinkedIn: linkedin.com/in/sarah-johnson-pm
- Headline: "President | 400-door PM company in Phoenix"
- Recent activity: Posted job opening for Growth Lead role 14 days ago

**Output:**
```
Signal: hiring_post
Variant A (15-20 words): "With the growth lead role you posted recently, thought this would be relevant as you scale Phoenix operations further."
Word count: 19
```

### Example 2: Hiring signal (Variant B)

Same input as Example 1.

**Output:**
```
Signal: hiring_post
Variant B (8-14 words): "Saw the growth lead role you posted three weeks back. Different angle worth flagging."
Word count: 14
```

### Example 3: Expansion announcement (Variant A)

**Input:**
- Headline: "CEO | Multi-state property management"
- Recent activity: Announced expansion into Charlotte market last week

**Output:**
```
Signal: expansion_announcement
Variant A: "With the Charlotte expansion you announced, thought this would be of interest as you build out the new market."
Word count: 18
```

### Example 4: Forum question (Variant A)

**Input:**
- Headline: "Owner @ Riverside Property Management"
- Recent activity: Posted BiggerPockets question on owner acquisition strategies last week

**Output:**
```
Signal: forum_question
Variant A: "Saw your BiggerPockets question on owner acquisition lately, thought this would be of interest given the angle you raised."
Word count: 19
```

### Example 5: Conference attendance (Variant A)

**Input:**
- Headline: "Director of Operations | Boutique PM firm"
- Recent activity: Posted from NARPM Broker/Owner conference last month

**Output:**
```
Signal: conference_attendance
Variant A: "Caught that you were at NARPM Broker/Owner, thought this would be of interest given the growth themes from the event."
Word count: 20
```

### Example 6: Thin profile (SKIP fallback)

**Input:**
- Headline: "President"
- Profile summary: empty
- No recent activity detected

**Output:**
```
SKIP
```

## Bridge variants by signal type

For deeper guidance on which bridge to use for which signal, and 25+ specific bridge variants, see `references/bridges-by-signal.md`.

## Production prompt templates

For ready-to-use prompts that can be copy-pasted directly into Clay, Instantly, Smartlead, or other outbound tools, see `assets/prompt-templates.md`.

## A/B testing recommendation

When the user is launching a new campaign, suggest generating 3-5 openers across different signal types and variants. Send each to 100-200 prospects. Measure reply rate, positive reply rate, and meeting booked rate. The best opener pattern for one ICP rarely generalizes to another, so test before scaling.

If the user has not run signal-based outbound before, also recommend generating a non-personalized control variant (same line for everyone in the segment) to confirm the personalization layer is earning its complexity. Sometimes simple direct lines outperform clever AI-personalized ones.

## Common failure patterns to avoid

When reviewing AI-generated openers, watch for these failures:

1. **Missing subject.** "Posted that role" instead of "Saw you posted that role." Fix by always including "you" or "your" near the verb.

2. **Bolted-on bridge.** Two sentences instead of one integrated sentence. Fix by rewriting as a single grammatical unit.

3. **Vague specificity.** "Your work in real estate" instead of "Your focus on Smoky Mountain vacation rentals." Fix by demanding one concrete detail from the input.

4. **Backhanded compliments.** "Impressive growth despite limited resources" implies a problem. Fix by removing any framing that suggests they should be worried.

5. **Quoted post text.** "Your post said 'we are losing 30% of leads'" sounds creepy. Fix by referencing the topic without quoting words.

6. **AI tells.** "I noticed," "delve into," em dashes. Fix by checking against the banned list.

7. **Forward-looking failure.** "as you fix this issue" instead of "as you scale this further." Fix by enforcing the success-implying framing.

## Quality checklist

Before finalizing any opener, verify:

- [ ] Word count within bounds (15-20 for Variant A, 8-14 for Variant B)
- [ ] One specific concrete detail referenced (not generic)
- [ ] Subject is explicit (not ambiguous)
- [ ] Bridge integrated grammatically (Variant A only)
- [ ] Forward-looking framing implies success
- [ ] Zero banned words present
- [ ] Single sentence (no questions in opener)
- [ ] Sounds like a peer wrote it, not a vendor
