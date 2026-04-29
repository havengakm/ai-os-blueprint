# Tools — concrete instruments

Tools are the physical instruments Skills wield to produce outputs. Skills define WHAT to do; Tools define HOW to talk to a specific external system or run a specific local operation.

This directory extracts integration helpers from `systems/` (which currently has them scattered across `systems/scout/sources/`, `systems/scout/supabase_backends/`, etc.).

## Layout

```
tools/
├── scrapers/
│   ├── clutch.py              Cloudflare-bypass Playwright scraper for clutch.co
│   ├── designrush.py          (future)
│   ├── goodfirms.py           (future)
│   └── ...
├── api_clients/
│   ├── anthropic.py           Claude API client wrapper
│   ├── trigify.py             Trigify monitor pull client
│   ├── instantly.py           Instantly send + webhook client
│   ├── supabase.py            Shared Supabase client factory
│   ├── apollo.py              Apollo enrichment client
│   ├── zerobounce.py          ZeroBounce email validation client
│   └── ...
├── validators/
│   ├── writing_validator.py   Em-dash + AI-cliché + buzzword + founding-year checks (currently in systems/scout/outreach/writing_validator.py)
│   └── json_parser.py         Strict JSON parsing with code-fence stripping (currently inlined in claude_research.py + claude_deep_research.py + icebreaker_adapter.py)
└── README.md (this file)
```

## Skills vs Tools

- **Skill** = a single capability with a clear input/output contract. May be domain-specific (Facebook ad copywriting) or atomic (em-dash detection).
- **Tool** = a specific external system / process the Skill talks to. Tools are reusable across many Skills.

A Skill can use multiple Tools. A Tool is used by many Skills.

## Status

Empty scaffold today. Tools migrate in over Phase 4+ as employees migrate. Existing helper modules in `systems/` keep working until their owning system migrates.
