# Expert Knowledge Base

Named domain authorities whose frameworks the AIOS borrows. One folder per expert. Each expert folder holds one file per sub-topic so frameworks grow without cluttering a flat directory.

## Current experts

- `hormozi/`: offers, delivery, pricing (planned)
- `brunson/`: funnels, hook-story-offer, dream-100 (planned)
- `saraev/`: AI positioning, cold email (populated)
- `sapp/`: high-ticket sales, objection handling (populated)
- `general/`: unattributed frameworks (AIDA, PAS, MEDDIC, etc.)

## Planned experts (per memory: feedback_expert_knowledge_library)

- `acosta/`: LinkedIn outbound patterns
- `walsh/`: LinkedIn content strategy

## Rule

Each expert folder:
- has its own README listing the topic files inside and which skills read from them
- uses one file per distinct sub-topic (hormozi/offers.md, hormozi/delivery.md): never one giant file
- is referenced from skill files in the `references:` frontmatter field, not imported whole
