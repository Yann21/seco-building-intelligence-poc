.DEFAULT_GOAL := help

.PHONY: app2 analyze eval doc explore deploy deploy-doc help

BACKEND  = app2-conflict-resolver/backend
FRONTEND = app2-conflict-resolver/frontend
REMOTE   = hetzner:/home/yann/apps/seco2/frontend/dist/
DOC_DIST = documentation/dist
DOC_REMOTE = hetzner:/home/yann/apps/secodoc/dist/

help: ## Show available commands
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

app2: ## Run app2 backend (uvicorn :8000) + frontend dev server (:5173)
	@trap 'kill 0' INT; \
	(cd $(BACKEND) && uvicorn main:app --reload --port 8002) & \
	(cd $(FRONTEND) && npm run dev) & \
	wait

analyze: ## Rebuild conflict analysis from PDFs (python -m pipeline.run [ARGS=--force])
	@cd $(BACKEND) && python -m pipeline.run $(ARGS)

eval: ## Run the golden-set regression eval against the current analysis
	@cd $(BACKEND) && python -m eval.run_eval

doc: ## Start documentation server at http://localhost:8889
	@cd $(BACKEND) && python ../../documentation/serve.py --port 8889

explore: ## Download all ITMs, embed, UMAP → app3-itm-explorer/report.html
	cd app3-itm-explorer && python explore.py

deploy: ## Build frontend, sync backend, rebuild Docker image, deploy to hetzner (yannhoffmann.com/seco2)
	@echo "Building frontend..."
	@cd $(FRONTEND) && npm run build
	@echo "Syncing frontend..."
	@rsync -av --delete $(FRONTEND)/dist/ $(REMOTE)
	@echo "Syncing backend..."
	@rsync -av $(BACKEND)/ hetzner:/home/yann/apps/seco2/backend/
	@echo "Rebuilding backend container..."
	@ssh hetzner "cd /home/yann/apps/seco2 && docker compose build backend && docker compose up -d backend"
	@echo "Done → https://yannhoffmann.com/seco2"

deploy-doc: ## Build static docs and rsync to hetzner (yannhoffmann.com/secodoc)
	@echo "Building static docs..."
	@python documentation/serve.py --build $(DOC_DIST)
	@echo "Deploying to hetzner..."
	@rsync -av --delete $(DOC_DIST)/ $(DOC_REMOTE)
	@echo "Done → https://yannhoffmann.com/secodoc"
