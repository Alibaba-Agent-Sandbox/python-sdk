.PHONY: install dev test test-cov lint format format-check typecheck build dist-check hygiene ci hooks clean help e2e e2e-all e2e-cleanup

CLIENT := client-sdk
SERVER := server-sdk

help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install both packages (easy-sandbox-server + easy-sandbox)
	pip install -e ./$(SERVER) -e ./$(CLIENT)

dev:  ## Install both packages with all dev dependencies
	pip install -e "./$(SERVER)[dev]" -e "./$(CLIENT)[dev]" hatchling build twine

test:  ## Run tests (client-sdk and server-sdk)
	cd $(SERVER) && pytest tests/ -v --tb=short
	cd $(CLIENT) && pytest tests/ -v --tb=short

test-cov:  ## Run tests with coverage
	cd $(SERVER) && pytest tests/ -v --tb=short --cov=easy_sandbox.server --cov-report=term-missing
	cd $(CLIENT) && pytest tests/ -v --tb=short --cov=easy_sandbox --cov-report=term-missing

lint:  ## Run linter
	cd $(SERVER) && ruff check src/ tests/
	cd $(CLIENT) && ruff check src/ tests/

format:  ## Format code
	cd $(SERVER) && ruff format src/ tests/
	cd $(CLIENT) && ruff format src/ tests/

typecheck:  ## Run type checker
	cd $(SERVER) && mypy src/easy_sandbox/server/
	cd $(CLIENT) && mypy src/easy_sandbox/

format-check:  ## Verify code is formatted (CI equivalent)
	cd $(SERVER) && ruff format --check src/ tests/
	cd $(CLIENT) && ruff format --check src/ tests/

build:  ## Build sdist and wheel for both packages into dist/<package>/
	rm -rf dist/
	python -m build --outdir dist/$(SERVER) $(SERVER)
	python -m build --outdir dist/$(CLIENT) $(CLIENT)

dist-check:  ## Verify distributions (twine check + py.typed in both wheels + combined install, CI equivalent)
	twine check dist/*/*
	python scripts/check_dists.py all

hygiene:  ## Fail on committed local paths / credential-like strings (CI equivalent)
	bash scripts/check-no-local-paths.sh

ci:  ## Run local CI equivalent (single interpreter; NOT a full substitute for the 3.10/3.11/3.12 matrix in GitHub Actions)
	$(MAKE) hygiene
	cd $(SERVER) && ruff check src/ tests/
	cd $(SERVER) && ruff format --check src/ tests/
	cd $(SERVER) && mypy src/easy_sandbox/server/
	cd $(SERVER) && pytest tests/ -m "not integration"
	cd $(CLIENT) && ruff check src/ tests/
	cd $(CLIENT) && ruff format --check src/ tests/
	cd $(CLIENT) && mypy src/easy_sandbox/
	cd $(CLIENT) && pytest tests/ -m "not integration"
	$(MAKE) build
	$(MAKE) dist-check
	@echo "Note: this runs on a single Python interpreter; the Python 3.10/3.11/3.12 matrix can only be fully covered by GitHub Actions CI."

hooks:  ## Install pre-commit (called automatically via .githooks/pre-commit)
	pip install pre-commit
	@echo "pre-commit installed. It will be called automatically via .githooks/pre-commit."

clean:  ## Clean build artifacts
	rm -rf dist/ build/
	rm -rf $(CLIENT)/build $(CLIENT)/dist $(CLIENT)/*.egg-info $(CLIENT)/src/*.egg-info $(CLIENT)/.pytest_cache $(CLIENT)/.mypy_cache $(CLIENT)/.ruff_cache
	rm -rf $(SERVER)/build $(SERVER)/dist $(SERVER)/*.egg-info $(SERVER)/src/*.egg-info $(SERVER)/.pytest_cache $(SERVER)/.mypy_cache $(SERVER)/.ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

e2e:  ## Real-cloud E2E suite (needs credentials in .env; sandbox cases only, Docker/ACR cases excluded)
	cd e2e && python -m pytest -m "e2e and not e2e_docker and not e2e_slow" -ra
	python scripts/e2e-cleanup.py --all-tagged

e2e-all:  ## Real-cloud E2E suite incl. slow and Docker/ACR cases (creates and deletes real cloud resources)
	cd e2e && python -m pytest -m "e2e" -ra
	python scripts/e2e-cleanup.py --all-tagged

e2e-cleanup:  ## Delete sandboxes/templates leaked by interrupted E2E runs (dry-run; add ARGS=--yes to delete)
	python scripts/e2e-cleanup.py --all-tagged $(ARGS)
