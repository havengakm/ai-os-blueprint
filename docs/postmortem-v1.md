# AIOS v1 Post-Mortem

Written 2026-05-06 immediately before archiving `ai-os-blueprint` and restarting in a fresh project folder.

The point of this doc is not blame. It's to bank the learnings while they're fresh so v2 doesn't repeat the same mistakes. Read this on day one of the new project.

---

## What v1 actually delivered (the real assets)

These survive into v2 — none of this work is lost.

1. **`aios-foundation` v0.3.0** (https://github.com/aios-kit/aios-foundation) — stable, tested, pip-installable. 11 modules: autonomy, base_system, decision_logger, embedder, employee_memory, feedback_loop, knowledge, pattern_matcher, storage, writing_rules, plus `aios.memory.store`. 107 tests pass. Public API documented. v2 should pin this on day one.
2. **`aios-scout` v0.2.0** (https://github.com/aios-kit/aios-scout) — outbound prospecting system. 57 modules across 9 subdirs. 767 tests pass. Cleanly separated from monorepo. v2 may pin this, fork it, or rebuild it — but the modules themselves are good reference for "what the right shape looks like."
3. **`docs/architecture/agent-deployment-lifecycle.md`** — the "two homes" + 6-stage lifecycle doc. Mental model still right. Read first when planning v2's first cloud routine.
4. **`docs/architecture/scaffolding-new-projects.md`** — 3-layer model (pip / deployment / vault) + decision tree + Recipe A (Python AIOS-connected) + Recipe B (JS/TS reading AIOS). Designed for exactly this restart moment.
5. **39 memory entries** under `memory/` — operator preferences, vendor decisions, voice rules, vendor stack choices. These travel with the operator, not with the project. Most are still load-bearing.

Everything below is what didn't work, why, and what to do differently.

---

## The patterns that worked — keep these in v2

### 1. Pip-package extraction with semver tags
Foundation v0.1.0 → v0.2.0 → v0.3.0 and scout v0.1.0 → v0.2.0 each landed cleanly with a code-review-then-merge gate. Pinning by tag in `pyproject.toml` made coordination across repos trivial. Phase 2.2 prep proved the pattern scales: one PR, three repos, zero drama.

**Keep:** the pip-from-git-tag distribution model, the semver discipline, the GitHub-release-per-tag practice, and the cross-repo code-review-before-merge gate.

### 2. The 3-layer separation (pip / deployment / vault)
Once articulated, every "where does this go?" question got easy. Layer 1 = library code, Layer 2 = wiring + identity, Layer 3 = knowledge. They cross-reference, never copy. The `feedback_per_company_aios_silo.md` rule fits inside this naturally.

**Keep:** the 3-layer model, the silo rule, and the "if I onboarded a second client tomorrow, would this need to be edited?" decision question.

### 3. Foundation as the home for cross-cutting primitives
`BaseSystem`, `AutonomyGate`, `DecisionLogger`, `KnowledgeStore`, `SupabaseLike`, `BANNED_*` — every shared thing belongs in foundation. Phase 2.2 prep proved that *not* doing this from day one creates cross-system import edges that have to be untangled later.

**Keep:** put cross-cutting primitives in foundation **on the same day they're needed by a second system**, never in scout-private paths.

### 4. Daemon smoke test as the verification gate
Running `scripts/run_daemon_once.py --client-id=... --dry-run` and checking for `cycle ok=True` + N `decision_log 201 Created` writes was the single most load-bearing test we had. It exercised pipeline shape end-to-end through real Supabase. Caught nothing twice (Phase 2 + Phase 2.2 prep), which is exactly the right outcome.

**Keep:** a similar end-to-end smoke test that hits real (or staged) infrastructure, not just unit-test mocks.

### 5. Code-review subagent before merge
Both Phase 2 and Phase 2.2 prep got useful, specific findings from `superpowers:code-reviewer`. Each found one or two real issues neither I nor the operator caught (missing export, stale comment).

**Keep:** an automated reviewer pass before merging cross-repo changes.

---

## What went wrong (the actual mess)

### 1. Plan churn outpaced execution
Running tally of plans named in the repo:
- Plan 1 (foundation + scout, original)
- Plan 1.5 (cost discipline + acceptance hardening + body template + Path B)
- Plan 2 Phase 0 (hardening + copy grader + ICP sub-agent + 90% enrichment + Plan 4 reservation)
- Plan 2 Phases 1-6 (Beacon + reply + cost + Optimizer v1 + productisation)
- Phase 2 (scout extraction)
- Phase 2.2 prep (foundation promotion)

Six "plans" in roughly six weeks. Each one revised what an earlier plan said. The pattern: build → discover thing not anticipated → write a new plan that assumes the discovery → repeat. Memory grew past 39 entries — a lagging indicator of decisions still being relitigated.

**Lesson for v2:** Cap initial scope to "foundation + one system + one client" and *resist* writing the next plan until that ships to a real user. The next plan writes itself once you have feedback.

### 2. Multiple half-built systems
Beacon and Optimizer were imported into the monorepo but never reached a shipped state. Their tests ran, their storage backends existed, but no daemon stage exercised the full beacon-reply-handler loop or the Optimizer's weekly review against real data. They were *almost* extracted in Phase 2.2/2.3 — but those phases never ran because v1 archived first.

**Lesson for v2:** One system at a time, end-to-end (code → storage → tests → daemon → operator-watching). Don't start system #2 until system #1 has run unattended for 7 days without operator intervention. The "5 employees / 5 systems" topology was correct; rolling out 5 in parallel was not.

### 3. Cross-cutting things grew in scout, not foundation
`SupabaseLike`, `insert_decision_log_row`, `_BANNED_*` constants — all started life as scout-private helpers, all got reached into by beacon/optimizer via leading-underscore module paths. By the time anyone said "wait, this is cross-cutting," six monorepo files imported the private path. Phase 2.2 prep had to promote them. Cost: one whole coordinated 3-repo PR that wouldn't have existed if the names had been put in foundation on day one.

**Lesson for v2:** When a second system needs a thing, **stop and put it in foundation immediately**. Do not let the leading-underscore-import precedent take hold. The cost of "promote it now" is always smaller than "promote it later when N callers depend on the private path."

### 4. The "private path" fiction
A leading-underscore module like `aios.scout.supabase_backends._base` doesn't actually prevent imports — it just signals "don't import this." The signal was ignored five times by beacon and once by optimizer. Python's privacy model is by convention; the convention was load-bearing and got load-bored.

**Lesson for v2:** If you don't want it imported by another system, raise a `RuntimeError` if `__name__` doesn't match expected, or move it to a `_internal` package and add a CI lint that fails on cross-system imports of `_internal`. Conventions without enforcement become technical debt.

### 5. Test count growth signals
The monorepo had **1,312 tests** at peak. After Phase 2 split out scout's 767 and Phase 2.2 prep promoted shared primitives, the monorepo settled to 545 + 1 skipped. So **~58% of the tests were scout's**, even though scout was theoretically just one system. The monorepo grew tests faster than it grew shipped behaviour.

**Lesson for v2:** Tests should track shipped behaviour, not planned behaviour. If a system has 600 tests but no decision_log writes from a real run yet, the test count is a lie about completeness. Pin test count growth to "stages that have run unattended in production for 24h."

### 6. Two-tier autonomy model never got exercised
The `suggest / draft / act_notify / autonomous` ladder was articulated and a few systems started at `suggest`. None ever earned promotion to `act_notify` because no system ran long enough at one level to accumulate the 50 decisions × 80% success × 30 days needed. Result: every system stayed at `suggest`, which means every decision was a human approval, which means the operator was the bottleneck — which is the opposite of what AIOS was supposed to deliver.

**Lesson for v2:** Pick ONE system, run it at `suggest` for 30 days against real traffic, demonstrate the autonomy ladder works *once*, then generalize. Don't ship 5 systems all parked at `suggest`.

### 7. Branch / planning-folder names got long
`feat/phase2-2-prep-foundation-promotion`, `feat/plan-1.5-completion`, `feat/scout-extraction`, etc. Branch names embedded plan numbers that themselves had revision history. When a plan number changes meaning, the branch name lies.

**Lesson for v2:** Branch names should describe the change, not the plan it came from. `feat/promote-supabase-protocol-to-foundation` ages better than `feat/phase2-2-prep`.

### 8. CI runner-availability was never solved
GitHub Actions runners didn't acquire jobs for the `aios-kit` org reliably. Both Phase 2 and Phase 2.2 prep tagged on green-local evidence rather than green-CI, which means the CI gate was effectively bypassed. That's a slippery slope.

**Lesson for v2:** Either use a self-hosted runner, or move CI to GitLab / CircleCI / something that doesn't have org-level runner allocation issues. Don't let "infra problem" become a permanent excuse for skipping CI.

---

## What I would do differently in v2

In rough priority order:

1. **Foundation first, one client, one system, end-to-end.** Don't write Plan 2 until Plan 1 is unattended for a week. Don't extract a system until it's stable AND another system needs to share it.

2. **Cross-cutting goes in foundation immediately.** Day one. The moment a second system needs `SupabaseLike` or the writing rules or anything similar, it lives in foundation, not in the first system.

3. **Cap the system count at 1 → 2 → 3, with a 7-day gap between each promotion.** The "5 employees" topology can be the *target*, but only one system runs in production at a time during the build-up. AIOS topology in v1 was 5 simultaneous half-built systems; v2 should be 1 fully-shipped system per epoch.

4. **Pick a real customer for system #1 before writing line one of code.** Decide who, what they pay, what success looks like. The CLYMB Co context is real but the operator wore both "operator" and "client" hats simultaneously, which made it easy to keep adding scope.

5. **Pip packages from day one.** Don't put new code in a monorepo unless you're sure it's deployment-specific. The instinct in v1 was "build it in the monorepo and extract later"; the cost of late extraction is high (Phase 2 took most of a day). v2 should reverse: build the package first, wire it into the deployment last.

6. **Skip the `_private` convention.** If something's not meant to be imported across systems, put it in a `_internal` subpackage and add a lint rule. Or raise a `RuntimeError` on import. Conventions without enforcement decay.

7. **Test count cap until 24h-unattended.** A system has at most N tests until it has run for 24 hours unattended in production. Then test cap doubles. This forces test investment to follow shipped behaviour, not planned behaviour.

8. **Keep the v1 architecture docs.** The 3-layer model, the agent-deployment-lifecycle, the scaffolding-new-projects guide — these survive into v2 unmodified. Read them on day one.

9. **Keep `aios-foundation` and `aios-scout`.** v2 should pin them at their current tags. If v2's first system isn't outbound prospecting, scout stays unpinned. But the foundation is right.

10. **Resist the urge to "plan everything."** v1's planning instinct was thorough but generated drift. v2's planning instinct should be "plan the current step, ship it, then plan the next step from feedback." Memory should grow ~5–10 entries before it stabilizes, not 39.

---

## Specific assets to bring forward (or rebuild) on day 1 of v2

Carry these directly:
- `aios-foundation@v0.3.0` (pip-pin)
- `aios-scout@v0.2.0` (pip-pin, IF v2's first system is outbound prospecting; otherwise defer)
- `docs/architecture/agent-deployment-lifecycle.md`
- `docs/architecture/scaffolding-new-projects.md`
- `data/reference/sops/claude-code-workflow.md` (if it still applies)
- `rules/global-writing-guardrails.md`
- The `memory/` entries that capture user-level preferences (voice, vendor stack, autonomy boundaries)

Drop or rebuild from scratch:
- All the multi-plan PROJECT.md / ROADMAP.md / Plan 1.5 / Plan 2 Phase X.Y artifacts
- Beacon, Optimizer, Content systems (rebuild in v2 only when a client needs them)
- The current `tests/` directory (rebuild as v2 systems ship)
- Most of `data/captures/`, `data/plans/`, `data/outputs/` (per-client artefacts, not shared)
- The 39 memory entries' implementation specifics (preferences stay; specific Plan-X decisions become noise)

---

## Final note

The work in v1 wasn't wasted — every learning above came from doing the thing. The mess is the cost of figuring out what the right shape is. v2 starts with that shape already known, which is a meaningful head start.

Archive cleanly. Don't relitigate v1 in v2. Read this once on day one, then let v1 rest.
