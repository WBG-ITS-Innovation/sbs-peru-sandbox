---
description: Append a dated one-line entry to docs/DECISIONS.md.
argument-hint: <free-text decision summary>
---

Append a decision log entry to [docs/DECISIONS.md](docs/DECISIONS.md).

Steps:

1. Read the current [docs/DECISIONS.md](docs/DECISIONS.md) so the format matches existing entries.
2. Identify the active Part from [docs/PLAN.md](docs/PLAN.md).
3. Use today's date (the system date — not a guess).
4. Append a single line at the end of the file in the format:

   ```
   YYYY-MM-DD | [PartN] <decision> | <one-line rationale>
   ```

   Use `$1` as the decision summary. If `$1` does not include a rationale (separated by ` | ` or similar), ask the human for one before writing.
5. Echo the line you wrote back to the human.

A decision log entry is a one-line summary, not an ADR. If the decision is architectural (locked, hard to reverse, affects the public contract), advise the human to run `/adr-new` instead of (or in addition to) the log entry.
