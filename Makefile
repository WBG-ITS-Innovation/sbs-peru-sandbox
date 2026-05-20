# SBS SupTech sandbox — convenience Make targets.
#
# Wraps the most-frequently-invoked uv / docker / scripts commands so
# new contributors can discover the workflow via `make help` instead
# of reading README + DEPLOY + the scripts/ directory.

.PHONY: help dev-up dev-down test smoke corpus corpus-golden serve-devportal

help:
	@echo "Targets:"
	@echo "  dev-up         — bring up Postgres + Redis + migrations + seed"
	@echo "  dev-down       — stop docker compose (preserves volumes)"
	@echo "  test           — run the pytest suite"
	@echo "  smoke          — run scripts/smoke-test-batch.sh stage-g-full"
	@echo "  corpus         — regenerate the full ~10k synthetic corpus"
	@echo "  corpus-golden  — regenerate the 200-row golden sample (committed)"
	@echo "  serve-devportal — render the OpenAPI spec via Stoplight Elements"

dev-up:
	bash scripts/dev-up.sh

dev-down:
	bash scripts/dev-down.sh

test:
	uv run pytest -q

smoke:
	bash scripts/smoke-test-batch.sh stage-g-full

corpus:
	uv run python scripts/generate-synthetic-corpus.py \
		--out data/synthetic-corpus \
		--rows-per-institution 3333 \
		--seed 2026

corpus-golden:
	uv run python scripts/generate-synthetic-corpus.py --golden

serve-devportal:
	bash scripts/serve-devportal.sh
