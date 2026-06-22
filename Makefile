.PHONY: doc deploy help

BACKEND  = app2-conflict-resolver/backend
FRONTEND = app2-conflict-resolver/frontend
REMOTE   = hetzner:/home/yann/apps/seco2/frontend/dist/

help:
	@echo "make doc        Start documentation server at http://localhost:8888"
	@echo "make deploy     Build frontend and rsync to hetzner"

doc:
	@cd $(BACKEND) && python ../../documentation/serve.py

deploy:
	@echo "Building frontend..."
	@cd $(FRONTEND) && npm run build
	@echo "Deploying to hetzner..."
	@rsync -av --delete $(FRONTEND)/dist/ $(REMOTE)
	@echo "Done → https://yannhoffmann.com/seco2"
