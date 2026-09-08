# Convenience commands. `make up` is the one-command start; `make load` runs the
# idempotent data load (added in the data-foundation block).

.PHONY: up down logs load test

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f backend

# Runs the idempotent loader inside the backend image (added in docs/01).
load:
	docker compose run --rm backend python -m scripts.load_data

test:
	docker compose run --rm backend pytest -q
