# KPI Sentinel — entry point for the project commands.
# `make help` lists the targets: a target is documented by a `##` comment on its line,
# a section by a `##@ Title` line.
# Targets delegate to the tools (Maven Wrapper, uv, pnpm) and cleanly skip components
# that do not exist yet.

SHELL := /usr/bin/env bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help
# Recipes start with `>` instead of a tab: readable, and impossible to break while editing.
.RECIPEPREFIX := >

MVN  ?= ./mvnw --quiet --no-transfer-progress
UV   ?= uv
PNPM ?= pnpm

# Optional components: a target only runs if its marker file exists.
DBT_PROJECT := pipelines/dbt/dbt_project.yml
WEB_PROJECT := services/web/package.json

# Local stack. PROFILE accepts one or several profiles: `make up PROFILE="core lake"`.
COMPOSE_DIR := infra/compose
COMPOSE_ENV := $(COMPOSE_DIR)/.env
COMPOSE     := docker compose --project-directory $(COMPOSE_DIR) -f $(COMPOSE_DIR)/docker-compose.yml
PROFILE     ?= core
# `docker compose exec` needs -T when stdin is not a terminal (e.g. `make psql-source <<< "..."`).
EXEC        := $(COMPOSE) exec $$([ -t 0 ] || echo -T)

.PHONY: help lint test fmt \
        lint-java lint-python lint-dbt lint-web \
        test-java test-python test-web test-integration \
        fmt-java fmt-python \
        up down ps logs reset psql-source psql-platform check-env

help: ## List the available targets
> @awk 'BEGIN { FS = ":.*## "; printf "\nUsage: make <target>\n" } \
>       /^##@/ { printf "\n%s\n", substr($$0, 5) } \
>       /^[a-zA-Z0-9_-]+:.*## / { printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
> @echo

##@ Quality

lint: lint-java lint-python lint-dbt lint-web ## Check formatting and quality of the whole repository

lint-java: ## Spotless (google-java-format) and Maven validation
> $(MVN) spotless:check validate

lint-python: ## ruff: lint, then format --check
> $(UV) run ruff check .
> $(UV) run ruff format --check .

lint-dbt: ## sqlfluff on pipelines/dbt (skipped while the dbt project does not exist)
> @if [ -f $(DBT_PROJECT) ]; then $(UV) run sqlfluff lint pipelines/dbt; \
>   else echo "lint-dbt: skipped, $(DBT_PROJECT) not found"; fi

lint-web: ## ESLint and Prettier on services/web (skipped while the web app does not exist)
> @if [ -f $(WEB_PROJECT) ]; then $(PNPM) -C services/web lint; \
>   else echo "lint-web: skipped, $(WEB_PROJECT) not found"; fi

##@ Tests

test: test-java test-python test-web ## Run all tests

test-java: ## Maven verify: unit tests, integration tests, JaCoCo report
> $(MVN) verify

test-python: ## pytest without integration tests (exit code 5 = no tests, accepted)
> @rc=0; $(UV) run pytest -q -m "not integration" || rc=$$?; \
>   if [ "$$rc" = 5 ]; then echo "test-python: no unit tests to run"; else exit "$$rc"; fi

test-integration: ## pytest integration tests, against the running local stack
> $(UV) run pytest -q -m integration

test-web: ## services/web tests (skipped while the web app does not exist)
> @if [ -f $(WEB_PROJECT) ]; then $(PNPM) -C services/web test; \
>   else echo "test-web: skipped, $(WEB_PROJECT) not found"; fi

##@ Formatting

fmt: fmt-java fmt-python ## Reformat the code (Spotless, ruff)

fmt-java: ## Apply google-java-format through Spotless
> $(MVN) spotless:apply

fmt-python: ## ruff format, then automatic lint fixes
> $(UV) run ruff format .
> $(UV) run ruff check --fix .

##@ Local stack

check-env:
> @if [ ! -f $(COMPOSE_ENV) ]; then \
>   echo "Missing $(COMPOSE_ENV). Create it with: cp $(COMPOSE_DIR)/.env.example $(COMPOSE_ENV)"; \
>   exit 1; fi

up: check-env ## Start the PROFILE services and wait until they are ready (default: core)
> $(COMPOSE) $(foreach p,$(PROFILE),--profile $(p)) up -d --build
> $(COMPOSE_DIR)/wait-until-ready.sh 240 $(COMPOSE) $(foreach p,$(PROFILE),--profile $(p))

down: check-env ## Stop every service of the stack, keeping the data volumes
> $(COMPOSE) --profile all down

ps: check-env ## List the stack's containers and their health
> $(COMPOSE) --profile all ps

logs: check-env ## Follow the logs of all services, or of one with S=<service>
> $(COMPOSE) --profile all logs -f --tail=200 $(S)

reset: check-env ## Stop the stack and DELETE its data volumes, after confirmation
> @printf "This stops the stack and deletes all its data volumes. Type 'yes' to continue: "; \
>   read -r answer; \
>   if [ "$$answer" = "yes" ]; then $(COMPOSE) --profile all down --volumes --remove-orphans; \
>   else echo "Aborted: nothing was deleted."; fi

psql-source: check-env ## Open psql on the source ERP database (atlas)
> $(EXEC) postgres-source psql -U postgres -d atlas

psql-platform: check-env ## Open psql on the platform Postgres server
> $(EXEC) postgres-platform psql -U postgres
