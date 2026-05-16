---
description: Run the benchmark-checker subagent on a file to verify it cites a comparator from docs/research/market-comparators.md.
argument-hint: <path>
---

Run the `benchmark-checker` subagent on `$1`.

Steps:

1. Read `$1`.
2. Read [docs/research/market-comparators.md](docs/research/market-comparators.md) and [docs/research/README.md](docs/research/README.md).
3. Invoke the `benchmark-checker` subagent. It returns one of:
   - `APPROVE` — all citations valid.
   - `APPROVE WITH NITS` — citations present but weak.
   - `BLOCK` — citation missing, stale, or contradicted.
4. If the verdict is `BLOCK`, report the suggested sections to cite, drawn from the research document index.

The benchmark-checker is not a style enforcer. The bar is: would this design choice warrant an ADR? If yes, it needs a comparator citation.
