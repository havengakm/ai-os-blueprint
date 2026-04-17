# AI Operating System Blueprint

Foundation for building AI-powered business systems. Same OS, deployed per instance. Each builds its own intelligence over time.

## Structure

```
ai-os-blueprint/
│
├── CLAUDE.md                              ── Master AI instructions
│
├── .claude/commands/                      ── HOW THE AI THINKS
│   ├── build-context.md                      Gather and structure context
│   ├── create-plan.md                        Always plan before executing
│   ├── decide.md                             Decision framework + learning engine
│   ├── implement.md                          Build workflow
│   └── prime.md                              Continuous improvement loop
│
├── context/                               ── WHO WE ARE (private per instance)
│   ├── personal.md                           The person
│   ├── personal-operating.md                 Cognitive profile, energy, productivity
│   ├── voice.md                              Writing style, copy rules, guardrails
│   ├── business-frameworks.md                Decision principles, red lines
│   ├── integrations.md                       Connected tools, data flows
│   ├── brand/                                Visual identity
│   └── projects/{name}/                      Per-project context
│       ├── company.md                           Business overview
│       ├── team.md, strategy.md                 People, goals
│       ├── icp.md, metrics.md                   Targeting, KPIs
│       ├── business-plan.md, financials.md      Planning, numbers
│       ├── operations.md, current-data.md       Delivery, state
│       └── research/                            Customer, competitor, market
│
├── data/                                  ── WHAT WE KNOW
│   ├── knowledge/                            Expert brains (RAG retrieval)
│   ├── captures/                             Raw data (calls, Slack, meetings)
│   ├── plans/                                Plans from /create-plan
│   ├── outputs/                              Reports, analyses, briefs
│   └── reference/                            SOPs, specs, process docs
│
├── os/                                    ── THE BRAIN
│   ├── foundation/                           Decision engine, pattern matcher,
│   │                                         autonomy gates, knowledge retrieval
│   ├── memory/                               Unified retrieval (MemoryStore)
│   └── registry.py                           System registry
│
├── systems/                               ── THE LIMBS (pluggable modules)
│   ├── base.py                               BaseSystem contract
│   └── {system-name}/                        One directory per system
│
├── scripts/sql/                           ── Database migrations
├── api/                                   ── Endpoints
└── config/                                ── Settings
```

## Conventions

- **context/** is private per instance. Committed in template, gitignored in client forks.
- **data/knowledge/** has expert frameworks shared via template.
- **data/reference/** has universal SOPs.
- **os/** is identical across all instances.
- **systems/** are self-contained. Each extends BaseSystem and connects to the foundation.

## Deployment

One template repo, forked per client. See `data/reference/client-deployment-sop.md`.
