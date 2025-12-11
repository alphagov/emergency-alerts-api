.DEFAULT_GOAL := help
SHELL := /bin/bash
TIME = $(shell date +%Y-%m-%dT%H:%M:%S%z)

# Passed through by Dockerfile/buildspec
APP_VERSION ?= unknown

GIT_BRANCH ?= $(shell git symbolic-ref --short HEAD 2> /dev/null || echo "detached")
GIT_COMMIT ?= $(shell git rev-parse HEAD)

VIRTUALENV_ROOT := $(shell [ -z $$VIRTUAL_ENV ] && echo $$(pwd)/venv || echo $$VIRTUAL_ENV)
PYTHON_EXECUTABLE_PREFIX := $(shell test -d "$${VIRTUALENV_ROOT}" && echo "$${VIRTUALENV_ROOT}/bin/" || echo "")

## DEVELOPMENT

.PHONY: legacy-bootstrap
legacy-bootstrap: generate-version-file ## Bootstrap, apply migrations and run the app
	pip3 install -r requirements_local_utils.txt
	createdb emergency_alerts || true
	(. environment.sh && flask db upgrade) || true

.PHONY: bootstrap
bootstrap: generate-version-file ## Set up everything to run the app
	pip3 install -r requirements_local_utils.txt

.PHONY: bootstrap-for-tests
bootstrap-for-tests: generate-version-file ## Set up everything to run the tests
	pip3 install -r requirements_github_utils.txt

.PHONY: run-flask
run-flask: ## Run flask
	. environment.sh && flask run -p 6011

.PHONY: run-flask-debug
run-flask-debug: ## Run flask in debug mode
	. environment.sh && flask --debug run -p 6011

.PHONY: run-celery
run-celery: ## Run Celery workers for periodic tasks
	. environment.sh && celery \
		-A run_celery.notify_celery worker \
		--pidfile=/tmp/api_celery_worker.pid \
		--prefetch-multiplier=1 \
		--loglevel=INFO \
		--autoscale=8,1 \
		--hostname='$(SERVICE)@%h' &

.PHONY: run-celery-api
run-celery-api: ## Run Celery workers for tasks executed by the API; high-priority ones first, then lower-priority ones
	. environment.sh && celery \
		-A run_celery.notify_celery worker \
		-Q high-priority-tasks \
		--pidfile=/tmp/api_celery_worker_hp.pid \
		--prefetch-multiplier=1 \
		--loglevel=INFO \
		--autoscale=8,1 \
		--hostname='$(SERVICE)_hp@%h' &

	. environment.sh && celery \
		-A run_celery.notify_celery worker \
		-Q broadcast-tasks \
		--pidfile=/tmp/api_celery_worker.pid \
		--prefetch-multiplier=1 \
		--loglevel=INFO \
		--autoscale=8,1 \
		--hostname='$(SERVICE)@%h' &

.PHONY: run-celery-beat
run-celery-beat: ## Run celery beat
	. environment.sh && celery \
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
