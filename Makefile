# Core1: a small simulated enterprise on a local Kubernetes cluster.
# Every target is a thin wrapper around a script in scripts/. GNU make 3.81+ (macOS default) is enough.
SHELL := /bin/bash
.DEFAULT_GOAL := help
N ?= 1

.PHONY: help doctor bootstrap up down reset status verify verify-quick disk endpoints \
        images cluster obs secrets config-repo deploy loadgen agent-kubeconfig wait-green \
        scenario scenarios scenario-1 scenario-2 scenario-3 scenario-4 scenario-5 diag runner test clean

help: ## Show this help
	@grep -E '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

doctor: ## Preflight checks (docker, ports, python, disk)
	@scripts/doctor.sh

bootstrap: ## Download pinned k3d, kubectl, helm into .bin
	@scripts/bootstrap.sh

up: bootstrap doctor cluster images obs secrets config-repo deploy loadgen agent-kubeconfig endpoints wait-green ## Build everything from nothing
	@scripts/status.sh
	@echo; echo "Core1 is up. Endpoints: .work/endpoints.env"

down: ## Delete the cluster and everything in it (keeps .bin and the config repo)
	@scripts/cluster-down.sh

reset: ## Return config repo and cluster to the known-good baseline
	@scripts/reset.sh

status: ## One-screen health summary
	@scripts/status.sh

verify: ## Full acceptance run, including every scenario (30 to 45 min)
	@$(PYTHON) tests/verify.py --scenarios

verify-quick: ## Acceptance checks without scenarios (about 2 min)
	@$(PYTHON) tests/verify.py

disk: ## Report lab disk usage against the ceiling
	@$(PYTHON) scripts/disk_check.py --report

endpoints: ## Write .work/endpoints.env and .work/endpoints.json
	@scripts/endpoints.sh

cluster: ## Create the k3d cluster (idempotent)
	@scripts/cluster-up.sh

images: ## Build the sample service images and import them into the cluster
	@scripts/build-images.sh

obs: ## Install or upgrade the observability stack
	@scripts/obs-install.sh

secrets: ## Create the app namespace and its secrets (platform-owned, not in the config repo)
	@scripts/app-secrets.sh

config-repo: ## Initialize the config repo from the template with seeded history (idempotent)
	@scripts/config-repo-init.sh

deploy: ## Deploy the config repo's current HEAD to the cluster
	@scripts/deploy.sh --wait

loadgen: ## Deploy the synthetic load generator and alert sink
	@scripts/loadgen.sh

agent-kubeconfig: ## Create or refresh the read-only kubeconfig for the agent
	@scripts/agent-kubeconfig.sh

wait-green: ## Wait until workloads are ready and no lab alerts are firing
	@scripts/wait-green.sh

scenario: ## Inject scenario N (make scenario N=3)
	@$(PYTHON) scripts/scenario.py inject $(N)

scenarios: ## List scenarios
	@$(PYTHON) scripts/scenario.py list

scenario-1: ; @$(PYTHON) scripts/scenario.py inject 1
scenario-2: ; @$(PYTHON) scripts/scenario.py inject 2
scenario-3: ; @$(PYTHON) scripts/scenario.py inject 3
scenario-4: ; @$(PYTHON) scripts/scenario.py inject 4
scenario-5: ; @$(PYTHON) scripts/scenario.py inject 5

diag: ## Collect diagnostics into logs/diag-<timestamp>/
	@scripts/diag.sh

runner: ## Start the unattended runner (executes queued make targets, logs to .runner/)
	@scripts/runner.sh

test: ## Unit tests for the sample services (needs a python venv, see docs/DEVELOPING.md)
	@cd services/app && $(PYTHON) -m pytest -q

clean: down ## Down, plus remove built images and downloaded tools
	@scripts/clean.sh

PYTHON ?= python3
