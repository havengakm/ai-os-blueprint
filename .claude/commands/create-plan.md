# Create Plan

NEVER execute without a plan. Always plan first, execute second.

## When to create a plan

- Any task with 3+ steps
- Any new system or feature
- Any architecture change
- Any change touching multiple files
- Any task involving API calls or external systems
- Any task where getting it wrong has consequences

## Plan structure

Every plan follows this format:

### 1. Context
Why are we doing this? What problem does it solve? What triggered it?

### 2. Requirements
What exactly needs to happen? What are the constraints? What's out of scope?

### 3. Research
What exists already? What can we reuse? Read the code before proposing changes.
- Search for existing functions and utilities
- Check how similar things are done elsewhere in the codebase
- NEVER rebuild what already works

### 4. Approach
How will we do it? Step by step. Include:
- Files to create or modify
- Dependencies on other work
- Order of operations

### 5. Risks
What could go wrong? What's irreversible? What needs human approval?

### 6. Verification
How do we test it? What does success look like?
- Specific commands to run
- Expected outputs
- Edge cases to check

## Process

1. Research the codebase first — read existing code, understand patterns
2. Write the plan to `data/plans/{date}-{name}.md`
3. Present to the user for review
4. Get explicit approval before executing
5. Execute per `/implement`
6. If the plan changes during execution, update the plan file FIRST

## Rules

- Plans are concise — scannable in 2 minutes
- Plans reference specific file paths
- Plans include dry-run steps before live runs
- Plans NEVER include API calls during planning (no credits burned on planning)
- When asked "does this work?" — show a manually written example, not a generated one
- If unsure about direction, ask before planning further
