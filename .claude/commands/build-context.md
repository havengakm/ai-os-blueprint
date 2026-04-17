# Build Context

When gathering context for any task, follow this process. More context = better performance. The AI OS is only as good as its understanding of who you are and what you want.

## What to gather

### 1. Personal context
- Who is this person? Background, experience, expertise
- Communication style, preferences, timezone
- Decision-making patterns, values, red lines
- What they care about, what they ignore

### 2. Company context
- What does the company do? Core offering, positioning
- Size, revenue, team structure
- Market position, competitors, differentiators
- Current state: growth stage, challenges, momentum

### 3. Brand context
- Visual identity: logo, colours (hex/RGB), fonts, design style
- Voice: how they write, speak, present themselves
- Mood: professional vs casual, bold vs understated
- Brand guide: do's and don'ts, positioning statements

### 4. Strategy context
- Current goals and OKRs
- GTM strategy, target market, pricing
- Timeline and constraints
- What's working, what's not

### 5. Project context
- Active projects, status, blockers, dependencies
- Priorities and deadlines
- Who's responsible for what

### 6. Integration context
- Tools in use (CRM, email, ads, analytics, project management)
- API connections, data flows
- What's connected vs manual

### 7. Historical context
- Past decisions and outcomes (from decision_log)
- What worked, what didn't, lessons learned
- Previous campaigns, strategies, pivots

## Where context lives

```
context/
├── personal.md           — Who you are
├── brand/
│   ├── brand-guide.md    — Logo, positioning, do's and don'ts
│   ├── color-palette.md  — Primary, secondary, accent (hex/RGB)
│   ├── typography.md     — Font pairings, sizes, usage
│   ├── design-preferences.md — Look and feel, aesthetic direction
│   └── mood-board.md     — Visual references, inspiration
├── projects/
│   └── {project-name}/
│       ├── company.md    — Business context
│       ├── team.md       — People and roles
│       ├── strategy.md   — Goals and approach
│       └── current-data.md — Real-time state
```

## How to structure context documents

Each document should be:
- **Specific** — not "they're a marketing agency" but "15-person branding agency in Cape Town focused on luxury DTC brands doing R2M/month"
- **Actionable** — helps make better decisions
- **Current** — reflects today's reality
- **Sourced** — from conversation, document, or system (not assumed)

Use `## Section` headings for each topic. Keep sections focused and scannable.

## When to update context

- After every major decision or strategy change
- When new information surfaces in conversation
- When a project status changes
- When integration configurations change
- Weekly: review and flag any stale context

## Context quality checklist

Before saving any context, verify:
- [ ] Is it specific enough to act on?
- [ ] Is it current (not outdated)?
- [ ] Is it sourced (not assumed)?
- [ ] Would it change how the AI responds?
- [ ] Is it stored in the right location?
