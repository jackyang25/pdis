# The one definition of how this project is installed, checked, and built.
#
# `.drone.yml` calls these targets rather than restating the commands, so there
# is a single place a check is added or changed. CI still splits the work across
# two container images - Python tooling and Node tooling are not in the same
# image - which is why the targets below are scoped by toolchain: each one runs
# in an image that has what it needs, and `check` is the local convenience that
# runs all of them.

UV ?= uv

.DEFAULT_GOAL := help
.PHONY: help dev install install-python install-web check lint test test-web fmt build clean

help: ## List targets
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install-python: ## Create the Python env from uv.lock
	$(UV) sync --frozen --all-groups

install-web: ## Install web packages from package-lock.json
	npm --prefix web ci

install: install-python install-web ## Both toolchains

dev: install ## First-time setup: env files, dependencies, next steps
	@test -f .env || cp .env.example .env
	@test -f .env.tooluniverse || cp .env.tooluniverse.example .env.tooluniverse
	@test -f web/.env.local || cp web/.env.local.example web/.env.local
	@echo
	@echo "Set OPENAI_API_KEY, ANTHROPIC_API_KEY, and TOOLUNIVERSE_API_TOKEN in .env,"
	@echo "then: docker compose up --build"

check: lint test test-web ## Everything CI runs, in one command

lint: ## Ruff, on the rules that catch defects rather than style
	$(UV) run ruff check .

test: ## Backend suite
	$(UV) run pytest tests -q

test-web: ## Web tests, types, and the production build
	npm --prefix web test
	npm --prefix web run typecheck
	@# The production build is part of the gate because Next.js inlines
	@# NEXT_PUBLIC_* at build time: a build-only failure is a runtime failure in
	@# the browser, with nothing in a server log to explain it.
	npm --prefix web run build

fmt: ## Apply ruff's formatter. Not part of `check`: it rewrites 150 files,
	@# and that belongs in its own reviewable commit.
	$(UV) run ruff format .

build: ## Build all three images the way compose does
	docker compose build

clean:
	rm -rf .venv .pytest_cache .ruff_cache web/.next web/tsconfig.tsbuildinfo
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
