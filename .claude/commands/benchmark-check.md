---
description: Run the benchmark-checker subagent on a file to verify it cites a comparator from a research file under docs/research/.
argument-hint: <path>
---

Run the `benchmark-checker` subagent on `$1`.

Steps:

1. Read `$1`.
2. Read [docs/research/README.md](docs/research/README.md) to see which research files exist and what each covers.
3. Read the research file(s) the document cites. Typically that means [market-comparators.md](docs/research/market-comparators.md) for regulator-domain ADRs or [supply-chain-precedents.md](docs/research/supply-chain-precedents.md) for operational supply-chain ADRs. Read any other file under `docs/research/` if the citation points there.
4. Invoke the `benchmark-checker` subagent. It returns one of:
   - `APPROVE` — all citations valid.
   - `APPROVE WITH NITS` — citations present but weak.
   - `BLOCK` — citation missing, stale, or contradicted.
5. If the verdict is `BLOCK`, report the suggested sections to cite, drawn from the research index.

The benchmark-checker is not a style enforcer. The bar is: would this design choice warrant an ADR? If yes, it needs a comparator citation. The rule is *specificity of section and comparator*, not filename — any research file under `docs/research/` is a valid citation target as long as the cited section is specific.
