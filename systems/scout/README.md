# Scout — Outbound Prospecting System

## What it does

Finds ideal clients, writes personalised outreach in the founder's voice, sends across multiple channels, handles follow-ups, and books qualified meetings into the calendar.

## How it connects to the foundation

- **Context:** Reads ICP, avatars, voice, brand, case studies from context_registry
- **Knowledge:** Queries Nick Saraev frameworks, copywriting frameworks for email generation
- **Decisions:** Logs copy_variant, icp_threshold, template_choice, send_timing decisions
- **Autonomy:** Checks autonomy level before sending outreach
- **Learning:** Past decision outcomes inform future copy and targeting choices

## Pipeline

```
pull_leads → score_contacts → screen_contacts → enrich_contacts → generate_outreach → send_outreach → track_replies
```

## Files (to migrate from base-camp-agents)

```
systems/scout/
├── README.md                — This file
├── skill.py                 — ScoutSystem(BaseSystem) entry point
├── __init__.py
├── config.py                — Scout-specific settings
├── pipeline/
│   ├── pull_leads.py        — Apollo + custom scraping
│   ├── score_contacts.py    — ICP scoring 0-100 + avatar classification
│   ├── screen_contacts.py   — Secondary ICP screen (Haiku + homepage)
│   ├── enrich_contacts.py   — Web research + signals + icebreaker
│   ├── generate_outreach.py — Template fill + AI subject/icebreaker/bridge
│   ├── send_outreach.py     — Approved drafts → Smartlead
│   └── recycle_contacts.py  — 90-day cooling-off re-entry
├── outreach/
│   ├── copywriting.py       — Copy generation instructions
│   ├── quality_gate.py      — 14-point QA check
│   └── templates.py         — Template management
└── icp.py                   — ICP definitions, avatars, scoring weights
```

## Status

Sprint 1: COMPLETE (in base-camp-agents repo)
Migration: PENDING (code exists, needs to be restructured to use BaseSystem)

## Tier

min_tier = "self_drive" (available to all tiers)
