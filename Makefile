APP_NAME=pigbot
APP_ROOT=app
VERSION=$(shell grep '^version' pyproject.toml | sed 's/.*= "\(.*\)"/\1/')

.PHONY: setup
setup:
	uv sync --extra dev

.PHONY: upgrade
upgrade:
	uv lock --upgrade
	uv sync --extra dev

.PHONY: lint
lint:
	uv run black $(APP_ROOT)/.

.PHONY: test
test:
	uv run pytest tests/ -v

.PHONY: build
build:
	docker build -t $(APP_NAME):$(VERSION) .

.PHONY: run
run:
	docker run --rm --name $(APP_NAME) -v /tmp:/app/downloads -p 443:8443 --env-file $(ENV).env $(APP_NAME):$(VERSION) --log-level debug

.PHONY: dev
dev: build run

.PHONY: stop
stop:
	docker kill $(APP_NAME)

.PHONY: clean
clean:
	docker rm $(APP_NAME) || true
