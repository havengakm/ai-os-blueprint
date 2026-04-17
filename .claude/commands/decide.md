# Decision Framework

Every significant decision gets logged, tracked, and learned from. This is what makes the OS smarter over time.

## Decision process

1. **Gather context** — Load relevant context from the foundation. What do we know about this situation?
2. **Check past decisions** — Has a similar decision been made before? What was the outcome? Query decision_log via vector similarity.
3. **Evaluate options** — What are the choices? What are the trade-offs?
4. **Check autonomy level** — Am I allowed to decide this, or does the human need to?
5. **Decide** — Make the call (or recommend to human based on autonomy level)
6. **Log** — Record the decision with: context snapshot, reasoning, confidence score
7. **Track** — Outcome gets backfilled when results come in

## Decision types

| Type | Example | What gets logged |
|---|---|---|
| copy_variant | Which template, subject line, icebreaker angle | Template chosen, contact context, avatar |
| icp_threshold | Score this contact, include or exclude | Score, breakdown, rationale |
| template_choice | Which framework to use (AIDA, PAS, etc.) | Framework, avatar, signals available |
| signal_weight | How to prioritise competing signals | Signals present, weights applied, top signal chosen |
| send_timing | When to send, which timezone logic | Time chosen, timezone, day of week |
| channel_selection | Email vs SMS vs voicemail vs letter | Channel chosen, contact score, available channels |
| meeting_booking | Which times to suggest, how to handle | Times offered, prospect timezone, calendar state |
| reply_handling | Classify reply intent, choose response | Reply text, classification, response macro used |
| manual_override | Human overrode system recommendation | Original recommendation, override decision, reason |

## Autonomy levels

| Level | What happens | Default for |
|---|---|---|
| suggest | System recommends, human decides | Everything (starting state) |
| draft | System prepares action, human approves | After 50+ decisions, 80% success rate |
| act_notify | System acts immediately, notifies after | After 50+ at draft, 85% success rate |
| autonomous | System acts, logs only | After 50+ at act_notify, 90% success, human approves promotion |

Promotion is NEVER automatic. The system surfaces evidence and asks for permission.

## Escalation triggers (always involve human)

- Confidence below 0.6
- No similar past decisions found
- High stakes (sending to 100+ contacts, changing templates, new channel)
- First time encountering this decision type
- Three consecutive negative outcomes on this decision type
- Any action that's hard to reverse

## Learning loop

```
Decision made → Outcome observed (hours/days later) → Outcome logged
    ↓
Next similar decision → Past outcomes retrieved → Better decision
    ↓
Pattern emerges → Confidence increases → Autonomy promotion considered
```

The system doesn't just make decisions — it learns WHICH decisions lead to good outcomes and applies that knowledge to future decisions.
