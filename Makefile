.PHONY: up down restart logs ps test check rebuild

up:
	docker compose up -d --build

down:
	docker compose down

restart:
	docker compose down
	docker compose up -d --build

logs:
	docker compose logs --tail=100 backend frontend

ps:
	docker compose ps

test:
	docker compose exec -T backend pytest -q /app/tests

check:
	bash scripts/check.sh

rebuild:
	docker compose build
