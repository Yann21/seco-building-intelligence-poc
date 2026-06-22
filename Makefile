.DEFAULT_GOAL := help

.PHONY: app2 doc deploy help

BACKEND  = app2-conflict-resolver/backend
FRONTEND = app2-conflict-resolver/frontend
REMOTE   = hetzner:/home/yann/apps/seco2/frontend/dist/

help: ## Show available commands
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

app2: ## Run app2 backend (uvicorn :8000) + frontend dev server (:5173)
	@trap 'kill 0' INT; \
	(cd $(BACKEND) && uvicorn main:app --reload --port 8002) & \
	(cd $(FRONTEND) && npm run dev) & \
	wait

doc: ## Start documentation server at http://localhost:8888
	@cd $(BACKEND) && python ../../documentation/serve.py

deploy: ## Build frontend and rsync to hetzner (yannhoffmann.com/seco2)
	@echo "Building frontend..."
	@cd $(FRONTEND) && npm run build
	@echo "Deploying to hetzner..."
	@rsync -av --delete $(FRONTEND)/dist/ $(REMOTE)
	@echo "Done → https://yannhoffmann.com/seco2"
