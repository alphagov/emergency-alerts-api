.DEFAULT_GOAL := help
SHELL := /bin/bash
DATE = $(shell date +%Y-%m-%d:%H:%M:%S)

APP_VERSION_FILE = app/version.py

GIT_BRANCH ?= $(shell git symbolic-ref --short HEAD 2> /dev/null || echo "detached")
GIT_COMMIT ?= $(shell git rev-parse HEAD)

CF_API ?= api.cloud.service.gov.uk
CF_ORG ?= govuk-notify
CF_SPACE ?= ${DEPLOY_ENV}
CF_HOME ?= ${HOME}
$(eval export CF_HOME)

CF_MANIFEST_PATH ?= /tmp/manifest.yml


NOTIFY_CREDENTIALS ?= ~/.notify-credentials

VIRTUALENV_ROOT := $(shell [ -z $$VIRTUAL_ENV ] && echo $$(pwd)/venv || echo $$VIRTUAL_ENV)
PYTHON_EXECUTABLE_PREFIX := $(shell test -d "$${VIRTUALENV_ROOT}" && echo "$${VIRTUALENV_ROOT}/bin/" || echo "")

NVM_VERSION := 0.39.7
NODE_VERSION := 16.14.0

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

.PHONY: run-celery-api
run-celery-api: ## Run celery
	. environment.sh && celery \
		-A run_celery.notify_celery worker \
		--uid=$(shell id -u easuser) \
		--pidfile=/tmp/celery_worker.pid \
		--queues=broadcast-tasks \
		--prefetch-multiplier=1 \
		--loglevel=DEBUG \
		--autoscale=8,1 \
		--hostname='celery@%h'

.PHONY: run-celery
run-celery: ## Run celery
	. environment.sh && celery \
		-A run_celery.notify_celery worker \
		--uid=$(shell id -u easuser) \
		--pidfile=/tmp/celery_worker.pid \
		--queues=periodic-tasks \
		--prefetch-multiplier=1 \
		--loglevel=DEBUG \
		--autoscale=8,1 \
		--hostname='celery@%h'

.PHONY: run-celery-beat
run-celery-beat: ## Run celery beat
	. environment.sh && celery \
		-A run_celery.notify_celery beat \
		--pidfile=/tmp/celery_beat.pid \
		--loglevel=DEBUG

.PHONY: help
help:
	@cat $(MAKEFILE_LIST) | grep -E '^[a-zA-Z_-]+:.*?## .*$$' | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: generate-version-file
generate-version-file: ## Generates the app version file
	@echo -e "__git_commit__ = \"${GIT_COMMIT}\"\n__time__ = \"${DATE}\"" > ${APP_VERSION_FILE}

.PHONY: test
test: ## Run tests
	flake8 .
	isort --check-only ./app ./tests
	black --check .
	pytest -n auto --maxfail=10

.PHONY: pytests
pytests: ## Run python tests only
	pytest -n auto --maxfail=5

.PHONY: freeze-requirements
freeze-requirements: ## create static requirements.txt
	${PYTHON_EXECUTABLE_PREFIX}pip3 install --upgrade setuptools pip-tools
	${PYTHON_EXECUTABLE_PREFIX}pip-compile --strip-extras requirements.in

.PHONY: fix-imports
fix-imports:
	isort ./app ./tests

.PHONY: bump-utils
bump-utils:  # Bump emergency-alerts-utils package to latest version
	${PYTHON_EXECUTABLE_PREFIX}python -c "from emergency_alerts_utils.version_tools import upgrade_version; upgrade_version()"

.PHONY: clean
clean:
	rm -rf node_modules cache target venv .coverage build tests/.cache ${CF_MANIFEST_PATH}

.PHONY: uninstall-packages
uninstall-packages:
	python -m pip uninstall emergency-alerts-utils -y
	python -m pip uninstall gds-metrics -y
	python -m pip freeze | xargs python -m pip uninstall -y
