# Atalhos do projeto efs-api-project.
# Uso:  make <alvo>    ·   make help    para listar
# IMPORTANTE: rodar a partir da raiz do repositorio (efs-api-project/)

TF_DIR := terraform
PY     := /usr/local/bin/python3.13

.DEFAULT_GOAL := help
.PHONY: help fmt validate check checkov refs preflight \
        build-api diagrams view view-stop clean-diagrams

help: ## Lista os alvos disponiveis
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

fmt: ## terraform fmt em todas as stacks
	@for d in $(TF_DIR)/*/; do (cd "$$d" && terraform fmt -recursive); done

validate: ## terraform fmt -check em todas as stacks
	@for d in $(TF_DIR)/*/; do \
		echo "=== $$d ==="; \
		(cd "$$d" && terraform fmt -check) || exit 1; \
	done

refs: ## Valida refs HCL e contrato SSM (sem AWS)
	@$(PY) tests/check_refs.py

checkov: ## Roda Checkov
	@checkov --config-file tests/.checkov.yml -d $(TF_DIR)

check: fmt validate refs checkov ## Roda todos os checks locais

preflight: ## Pre-flight completo (inclui validate por stack)
	@tests/preflight.sh

build-api: ## Build + push da imagem da API pro ECR
	@api/build_and_push.sh

diagrams: ## Gera o .drawio e valida sobreposicoes
	@$(PY) diagrams/build_diagrams.py
	@$(PY) diagrams/check_overlap.py

view: diagrams ## Serve o viewer e abre no Chrome
	@pkill -f "http.server 8765" 2>/dev/null || true
	@cd diagrams && $(PY) -m http.server 8765 > /tmp/drawio-server.log 2>&1 &
	@sleep 1 && open -a "Google Chrome" "http://localhost:8765/view.html?v=$$(date +%s)"

view-stop: ## Para o servidor do viewer
	@pkill -f "http.server 8765" 2>/dev/null || true
	@echo "server parado"

clean-diagrams: ## Remove artefatos gerados pelos diagramas
	@rm -f diagrams/*.drawio.bak
	@rm -rf diagrams/.drawio-backup
