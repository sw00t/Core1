# Core1: thin shim over ./core1 for muscle memory. ./core1 --help lists everything.
SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help doctor up status endpoints smoke nuke nuke-all test

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-10s %s\n", $$1, $$2}'

doctor: ## Host checks
	@./core1 doctor

up: ## Bring up registry and three clusters to green (idempotent)
	@./core1 up

status: ## Clusters, nodes, system pods, registry
	@./core1 status

endpoints: ## Regenerate .work/endpoints.json
	@./core1 endpoints

smoke: ## Green checks plus a registry pull in every cluster
	@./core1 test smoke

nuke: ## Delete clusters, registry, network and local state (asks first)
	@./core1 nuke

nuke-all: ## nuke plus .bin, .venv and pulled images (asks first)
	@./core1 nuke --all

test: ## CLI unit tests
	@./core1 --dev-python -m pytest -q cli/tests
