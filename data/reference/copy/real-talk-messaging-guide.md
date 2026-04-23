# AIOS: The "Real Talk" Messaging Guide for Founders

This guide is built from the actual words, frustrations, and "yelling into the void" moments of real business owners. It replaces corporate jargon with the raw language of the "starving crowd" and explains how the AI Operating System (AIOS) fixes their exact situation.

## Scope (productised — shared across all deployments)

This is a **global voice layer**, not a per-client or per-niche document. Every AIOS deployment — Client Zero, future clients, every niche — inherits this guide as the source of truth for outbound tone. Client-specific details (operator name, offer promise, price, risk reversal) live in `client_facts` and are injected via template placeholders at compose-time.

**Inputs that override this guide for a specific deployment:** none. Clients can *add* niche-specific pain language in their `context/{client_id}/icp.md`, but they do not override the voice rules below.

**Where this guide is enforced:**
- Every tier of the icebreaker adapter prompt (`systems/scout/enrich/icebreaker_adapter.py`) quotes the banned-word list and anti-stalker guardrail from this file.
- Every component YAML under `data/reference/sequences/{niche}/components/` is grep-checked against the banned-word list before commit.
- Every draft emitted by `systems/scout/outreach/composer.py` is post-checked against these rules in the render_draft verification step.

---

## 1. The "Mental Load" & Burnout
**The Raw Saying:** *"I'm so tired of having to constantly remind everyone about everything."*

*   **The Situation:** You're the bottleneck. Every decision, every follow-up, and every "did you send that email?" goes through you. You feel like you're "getting your ass handed to you" by the sheer volume of small things.
*   **The Frustration:** You didn't start a business to be a professional reminder-bot. You're "mega burnt out" because your brain is full of 1,000 tiny details that your current tools keep dropping.
*   **How AIOS Helps:** **The System Remembers So You Don't Have To.** The AIOS acts as the "shared brain" for your business. It watches every conversation and task, automatically following up and keeping the context alive. You stop being the "reminder-bot" because the system already knows what needs to happen next and just does it.

---

## 2. The "Broken" Growth Engine
**The Raw Saying:** *"We have revenue, but we aren't growing fast 'enough'—it feels like we're stuck."*

*   **The Situation:** You've hit a plateau. You're doing "a few thousand a month," but your CAC (cost to get a customer) is high, and your "overnight success" feels like a myth.
*   **The Frustration:** You're "tired of hearing trash advice" about just working harder. You've tried the "one weird trick" and the "AI whatever" tools, but nothing moves the needle. You feel like you're "financing projects for free" because your leads aren't high-quality.
*   **How AIOS Helps:** **Predictable Growth, Not Referral Luck.** The AIOS replaces "guessing" with "alignment." It identifies the exact moments when your best possible clients are ready to buy and starts the conversation for you. It moves you from "hoping for a referral" to having a productized engine that delivers consistent, high-ticket leads every single month.

---

## 3. The "SDR Disaster" & Hiring Fear
**The Raw Saying:** *"I hired a rep, they burned through my leads, and then they quit. I'm done with it."*

*   **The Situation:** You tried to hire your way out of the problem. You paid $5k/month for a "Junior SDR" who spent 3 months "ramping up" only to deliver zero results and leave you with a "messy CRM."
*   **The Frustration:** You feel like you're "renting" employees who don't care about your business as much as you do. You're "tired of dealing with everything that comes up" when a human rep drops the ball.
*   **How AIOS Helps:** **An Asset You Own, Not a Rep You Rent.** Instead of hiring a human who might quit, you build a "pipeline asset." The AIOS handles the volume of 10 human reps but with the judgment and "taste" of a founder. It doesn't get emotional, it doesn't need "ramping up," and it never leaves for a better offer.

---

## 4. The "Operational Chaos"
**The Raw Saying:** *"I'm too dumb to start a business—I didn't understand the 'office side' of things."*

*   **The Situation:** You're great at the "work" (the glass glazing, the coding, the consulting), but the "office side"—the CRMs, the follow-ups, the data—is "crushing you."
*   **The Frustration:** You feel like you're "not built for this" because you're drowning in admin. You wish you could "just give up" and go back to your old job where someone else handled the "messy data."
*   **How AIOS Helps:** **The 'Clean Slate' for Your Business.** The AIOS handles the "office side" automatically. It unifies your "messy CRM," your "fragmented tools," and your "slow follow-ups" into one autonomous workflow. You get to go back to doing the work you love, while the system handles the "boring stuff" that was making you want to quit.

---

## 5. The "Tire-Kicker" Trap
**The Raw Saying:** *"Some clients cost more in mental peace than the cheque is worth."*

*   **The Situation:** You're taking on "bottom-dollar tire-kickers" because you're scared of a "bad month." These clients have "no clarity," they "refuse to pay advances," and they "disappear during approvals."
*   **The Frustration:** You're "mega burnt out" from dealing with "committee clients" who want 10 rounds of revisions for a tiny fee. You need "fewer, better clients" who actually value your time.
*   **How AIOS Helps:** **The 'No-Tire-Kicker' Filter.** The AIOS uses your "best client" history to automatically qualify every lead. It filters out the "future promise" fakers and the "zero advance" red flags before they ever get on your calendar. You only talk to people who are ready to pay your full rate and respect your "sweat equity."

---

## Hard copy rules (derived from this guide + Kirsten's direct instruction)

These rules apply to every component variant, every generated icebreaker, every subject line:

1. **Their language, not ours.** Use the raw sayings above. Never "AI," "operating system," "autonomous," "workflow," "pipeline" (as marketing noun), "leverage," "solution," "scale," "optimize," "synergy," "cutting-edge," "AI-powered."
2. **Benefits in plain words, tied to desire.** "Fewer, better clients" beats "qualified pipeline." "The system remembers so you don't have to" beats "automated follow-ups."
3. **Casual — like writing to a friend.** Contractions always. Lowercase subject lines OK. No salutation fluff ("Hope you're well"). No signoff fluff ("Looking forward to hearing from you").
4. **No pricing.** Not the setup fee, not the retainer, not "custom quote." Pricing happens on the call.
5. **Goal = book the call.** Every CTA ends in asking for time, not information.
6. **No links in first email.** No Calendly, no portfolio, no case study. Links are for follow-ups.
7. **Offer phrased as commitment.** Use the placeholder pattern `{{offer_promise}} in {{offer_period}}. {{offer_risk_reversal}}.` — the actual promise/period/reversal come from per-client `client_facts` at compose-time. Never "we help agencies do X." Example filled-in (for Client Zero): "10 qualified conversations with your ideal client in 60 days. If we don't hit it, you don't pay the retainer — just the setup." A different client with a different offer will produce different copy from the same templates.

## Banned-word list (fail-closed in icebreaker adapter)

Regex-enforced rejection, retry once:

- `impressed`, `remarkable`, `leverage`, `solution`, `optimize`, `scale`, `synergy`, `cutting-edge`, `AI-powered`, `AI whatever`
- `operating system`, `autonomous`, `workflow`, `pipeline` (as noun)
- em dash `—`
- any URL fragment: `http`, `calendly`, `.com/`

## Anti-stalker guardrail (Tier 1–2 icebreakers only)

When referencing a Trigify signal, reference the **topic** the prospect posted about or engaged with — never the act of engagement itself. Regex reject: `you liked`, `you commented`, `you engaged`, `your post`.
