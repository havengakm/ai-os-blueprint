"""Plan 1 pipeline demo — exercises scoring + screening on 5 realistic contacts.

Hand-built fractional-CFO targeting scenario. Runs pure functions only — no
database, no API calls. Shows the decisions Plan 1 code would make on real
data, so you can inspect behavior without infrastructure.

Run with:
    uv run python scripts/demo_pipeline.py
"""
from __future__ import annotations

from aios.scout.pipeline.score import (
    DEFAULT_TIER_THRESHOLDS,
    DEFAULT_WEIGHTS,
    assign_tier,
    score_v1,
)
from aios.scout.pipeline.screen import screen_contact


# ---------------------------------------------------------------------------
# Client config — the kind of thing that lives in client_config + icp_definitions
# ---------------------------------------------------------------------------

CLYMB_CONFIG = {
    "weights": DEFAULT_WEIGHTS,                 # {fit: 40, intent: 30, reach: 20, recency: 10}
    "tier_thresholds": DEFAULT_TIER_THRESHOLDS, # {A: 80, B: 65, C: 50, D: 35, archive_floor: 35}
    "icp": {
        "industries": ["fractional cfo", "financial consulting", "CFO services"],
        "titles": ["Fractional CFO", "CEO", "Founder", "Managing Partner", "Managing Director"],
        "employee_min": 2,
        "employee_max": 30,
        "geographies": ["United States", "United Kingdom"],
        "blacklist_companies": ["Banned Holdings"],
        "blacklist_domains": ["spam-example.com"],
    },
}


# ---------------------------------------------------------------------------
# 5 realistic contacts — the mix you'd see in a real pull batch
# ---------------------------------------------------------------------------

CONTACTS = [
    {
        "label": "Brad Martyn @ FocusCFO",
        "contact": {
            "first_name": "Brad",
            "last_name": "Martyn",
            "company": "FocusCFO",
            "company_domain": "focuscfo.com",
            "industry": "fractional CFO",
            "title": "Founder & CEO",
            "employees": 25,
            "geography": "United States",
            "email": "brad@focuscfo.com",
            "email_verified": True,
            "linkedin_url": "https://linkedin.com/in/bradmartyn",
            "phone": "+1-555-0100",
            "raw_data": {"funding_event_last_180d": False, "recent_hiring": True},
            "research_data": {},
        },
    },
    {
        "label": "Jack Perkins @ CFO Hub",
        "contact": {
            "first_name": "Jack",
            "last_name": "Perkins",
            "company": "CFO Hub",
            "company_domain": "cfohub.com",
            "industry": "fractional CFO",
            "title": "CEO",
            "employees": 12,
            "geography": "United Kingdom",
            "email": "jack@cfohub.com",
            "email_verified": False,
            "linkedin_url": "https://linkedin.com/in/jackperkins",
            "phone": None,
            "raw_data": {"funding_event_last_180d": False, "recent_hiring": False},
            "research_data": {},
        },
    },
    {
        "label": "Sarah Chen @ Agency-on-Demand (wrong fit)",
        "contact": {
            "first_name": "Sarah",
            "last_name": "Chen",
            "company": "Agency-on-Demand",
            "company_domain": "agencyondemand.com",
            "industry": "digital marketing agency",
            "title": "Account Manager",
            "employees": 80,
            "geography": "United States",
            "email": "sarah@agencyondemand.com",
            "email_verified": True,
            "linkedin_url": "https://linkedin.com/in/sarahchen",
            "phone": None,
            "raw_data": {},
            "research_data": {},
        },
    },
    {
        "label": "Incomplete @ SomeCo (missing name)",
        "contact": {
            "first_name": None,
            "last_name": None,
            "company": "SomeCo",
            "company_domain": "someco.com",
            "industry": "financial consulting",
            "title": "Managing Director",
            "employees": 15,
            "geography": "United States",
            "email": "info@someco.com",
            "email_verified": True,
            "linkedin_url": None,
            "phone": None,
            "raw_data": {},
            "research_data": {},
        },
    },
    {
        "label": "Jane Doe @ Banned Holdings (blacklisted)",
        "contact": {
            "first_name": "Jane",
            "last_name": "Doe",
            "company": "Banned Holdings",
            "company_domain": "banned.com",
            "industry": "fractional CFO",
            "title": "Founder",
            "employees": 10,
            "geography": "United States",
            "email": "jane@banned.com",
            "email_verified": True,
            "linkedin_url": "https://linkedin.com/in/janedoe",
            "phone": "+1-555-0200",
            "raw_data": {},
            "research_data": {},
        },
    },
]


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------

def run_demo() -> None:
    print("=" * 78)
    print("Plan 1 Pipeline Demo — Scout stages 1-3 (pull, score_v1, screen)")
    print("=" * 78)
    print(f"\nClient config: CLYMB targeting fractional-CFO shops")
    print(f"  Weights: {CLYMB_CONFIG['weights']}")
    print(f"  Tier thresholds: A>=80, B>=65, C>=50, D>=35, <35=archive")
    print(f"  ICP titles: {CLYMB_CONFIG['icp']['titles']}")
    print(f"  Blacklist companies: {CLYMB_CONFIG['icp']['blacklist_companies']}")
    print(f"  Blacklist domains: {CLYMB_CONFIG['icp']['blacklist_domains']}")

    print(f"\n{'Contact':<50} {'Score':>7} {'Tier':>6} {'Screen':>18} {'Final status'}")
    print("-" * 120)

    for fixture in CONTACTS:
        contact = fixture["contact"]
        label = fixture["label"]

        # Stage 1 (pull): contacts already exist in this demo
        # Stage 2 (score_v1): run on every contact
        score = score_v1(contact, CLYMB_CONFIG)
        tier = assign_tier(score, CLYMB_CONFIG)

        # Stage 3 (screen): run only on contacts that didn't archive from scoring
        if tier == "archive":
            screen_result = "(skipped)"
            final = "ARCHIVED below archive_floor"
        else:
            passed, reason = screen_contact(contact, CLYMB_CONFIG)
            if passed:
                screen_result = "PASS"
                final = "ready for identity + enrichment"
            else:
                screen_result = f"REJECT: {reason.split(':')[0]}"
                final = f"DEAD — {reason}"

        print(f"{label:<50} {score:>7} {tier:>6} {screen_result:>18} {final}")

    print()
    print("What happens next (not exercised in this demo — requires infrastructure):")
    print("  Stage 4 (identity): Apollo/Hunter/Claude-scraper waterfall fills in person fields")
    print("  Stage 5 (enrich):   Tier-gated vendor calls for phones / research / email-verify")
    print("  Stage 6 (score_v2): re-score with intent signals from research + activity")
    print("  Stage 7 (render):   template + placeholder fill → outbound drafts (QA-gated)")
    print("  Stage 8 (send):     Beacon scheduler + reply classifier (Plan 2)")


if __name__ == "__main__":
    run_demo()
