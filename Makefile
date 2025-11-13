.DEFAULT_GOAL := help
SHELL := /bin/bash
TIME = $(shell date +%Y-%m-%dT%H:%M:%S%z)

# Passed through by Dockerfile/buildspec
APP_VERSION ?= unknown

GIT_BRANCH ?= $(shell git symbolic-ref --short HEAD 2> /dev/null || echo "detached")
GIT_COMMIT ?= $(shell git rev-parse HEAD)

VIRTUALENV_ROOT := $(shell [ -z $$VIRTUAL_ENV ] && echo $$(pwd)/venv || echo $$VIRTUAL_ENV)
PYTHON_EXECUTABLE_PREFIX := $(shell test -d "$${VIRTUALENV_ROOT}" && echo "$${VIRTUALENV_ROOT}/bin/" || echo "")

NVM_VERSION := 0.40.3
NODE_VERSION := 22.21.0

write-source-file:
	@if [ -f ~/.zshrc ]; then \
		if [[ $$(cat ~/.zshrc | grep "export NVM") ]]; then \
			cat ~/.zshrc | grep "export NVM" | sed "s/export//" > ~/.nvm-source; \
		else \
			cat ~/.bashrc | grep "export NVM" | sed "s/export//" > ~/.nvm-source; \
		fi \
	else \
		cat ~/.bashrc | grep "export NVM" | sed "s/export//" > ~/.nvm-source; \
	fi

read-source-file: write-source-file
	@if [ ! -f ~/.nvm-source ]; then \
		echo "Source file could not be read"; \
		exit 1; \
	fi

	@for line in $$(cat ~/.nvm-source); do \
		export $$line; \
	done; \
	echo '. "$$NVM_DIR/nvm.sh"' >> ~/.nvm-source;

	@if [[ "$(NVM_DIR)" == "" || ! -f "$(NVM_DIR)/nvm.sh" ]]; then \
		mkdir -p $(HOME)/.nvm; \
		export NVM_DIR=$(HOME)/.nvm; \
		curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v$(NVM_VERSION)/install.sh | bash; \
		echo ""; \
		$(MAKE) write-source-file; \
		for line in $$(cat ~/.nvm-source); do \
			export $$line; \
		done; \
		echo '. "$$NVM_DIR/nvm.sh"' >> ~/.nvm-source; \
	fi

	@current_nvm_version=$$(. ~/.nvm-source && nvm --version); \
	echo "NVM Versions (current/expected): $$current_nvm_version/$(NVM_VERSION)";

upgrade-node:
	@TEMPDIR=/tmp/node-upgrade; \
	if [[ -d $(NVM_DIR)/versions ]]; then \
		rm -rf $$TEMPDIR; \
		mkdir $$TEMPDIR; \
		cp -rf $(NVM_DIR)/versions $$TEMPDIR; \
		echo "Node versions temporarily backed up to: $$TEMPDIR"; \
	fi; \
	rm -rf $(NVM_DIR); \
	$(MAKE) read-source-file; \
	if [[ -d $$TEMPDIR/versions ]]; then \
		cp -rf $$TEMPDIR/versions $(NVM_DIR); \
		echo "Restored node versions from: $$TEMPDIR"; \
	fi;

.PHONY: install-nvm
install-nvm:
	@echo ""
	@echo "[Install Node Version Manager]"
	@echo ""

	@if [[ "$(NVM_VERSION)" == "" ]]; then \
		echo "NVM_VERSION cannot be empty."; \
		exit 1; \
	fi

	@$(MAKE) read-source-file

	@current_nvm_version=$$(. ~/.nvm-source && nvm --version); \
	if [[ "$(NVM_VERSION)" != "$$current_nvm_version" ]]; then \
		$(MAKE) upgrade-node; \
	fi

.PHONY: install-node
install-node: install-nvm
	@echo ""
	@echo "[Install Node]"
	@echo ""

	@. ~/.nvm-source && nvm install $(NODE_VERSION) \
		&& nvm use $(NODE_VERSION) \
		&& nvm alias default $(NODE_VERSION);


## DEVELOPMENT

.PHONY: legacy-bootstrap
legacy-bootstrap: generate-version-file ## Bootstrap, apply migrations and run the app
	pip3 install -r requirements_local_utils.txt
	createdb emergency_alerts || true
	(. environment.sh && flask db upgrade) || true

.PHONY: bootstrap
bootstrap: generate-version-file install-node ## Set up everything to run the app
	pip3 install -r requirements_local_utils.txt

.PHONY: bootstrap-for-tests
bootstrap-for-tests: generate-version-file install-node ## Set up everything to run the tests
	pip3 install -r requirements_github_utils.txt

.PHONY: run-flask
run-flask: ## Run flask
	. environment.sh && flask run -p 6011

.PHONY: run-flask-debug
run-flask-debug: ## Run flask in debug mode
	. environment.sh && flask --debug run -p 6011

.PHONY: run-celery
run-celery: ## Run celery
	. environment.sh && opentelemetry-instrument celery \
		-A run_celery.notify_celery worker \
		--pool=threads \
		--uid=$(shell id -u easuser) \
		--pidfile=/tmp/api_celery_worker.pid \
		--prefetch-multiplier=1 \
		--loglevel=INFO \
		--autoscale=16,1 \
		--hostname='$(SERVICE)@%h'

.PHONY: run-celery-beat
run-celery-beat: ## Run celery beat
	. environment.sh && opentelemetry-instrument celery \
		-A run_celery.notify_celery beat \
		--pidfile=/tmp/celery_beat.pid \
		--loglevel=INFO

.PHONY: help
help:
	@cat $(MAKEFILE_LIST) | grep -E '^[a-zA-Z_-]+:.*?## .*$$' | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: generate-version-file
generate-version-file: ## Generate the app/version.py file
	@ GIT_COMMIT=${GIT_COMMIT} TIME=${TIME} APP_VERSION=${APP_VERSION} envsubst < app/version.dist.py > app/version.py

.PHONY: test
test: ## Run tests
	flake8 .
	isort --check-only ./app ./tests
	black --check .
	pytest -n auto --maxfail=10

.PHONY: pytests
pytests: ## Run python tests only
	pytest -n auto

.PHONY: freeze-requirements
freeze-requirements: ## create static requirements.txt
	${PYTHON_EXECUTABLE_PREFIX}pip3 install --upgrade setuptools pip-tools
	${PYTHON_EXECUTABLE_PREFIX}pip-compile requirements.in

.PHONY: fix-imports
fix-imports:
	isort ./app ./tests

.PHONY: bump-utils
bump-utils:  # Bump emergency-alerts-utils package to latest version
	${PYTHON_EXECUTABLE_PREFIX}python -c "from emergency_alerts_utils.version_tools import upgrade_version; upgrade_version()"

.PHONY: clean
clean:
	rm -rf node_modules cache target venv .coverage build tests/.cache

.PHONY: uninstall-packages
uninstall-packages:
	python -m pip uninstall emergency-alerts-utils -y
	python -m pip freeze | xargs python -m pip uninstall -y
