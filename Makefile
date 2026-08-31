.PHONY: help setup up down run demo load reset

VENV ?= .venv
PY   := $(VENV)/bin/python
PORT ?= 8000

# Use Doppler only if it is configured for this directory, not merely installed;
# otherwise `doppler run` fails for anyone using a plain .env file.
DOPPLER := $(shell doppler configure get config --plain 2>/dev/null)
RUNNER  := $(if $(DOPPLER),doppler run --silent --,)

help:
	@echo "make setup    Create the virtualenv and install dependencies"
	@echo "make up       Start Redis Stack"
	@echo "make run      Run the gateway on :$(PORT)"
	@echo "make demo     Verified walkthrough of the caching behaviour"
	@echo "make load     Benchmark the cache-hit path (~\$$0.0001)"
	@echo "make reset    Clear cached entries"
	@echo "make down     Stop Redis Stack"
	@echo ""
	@echo "secrets:      $(if $(DOPPLER),Doppler config '$(DOPPLER)',.env file)"

setup:
	python3 -m venv $(VENV)
	$(PY) -m pip install -q --upgrade pip
	$(PY) -m pip install -q -r requirements.txt
	@test -f .env || cp .env.example .env
	@echo "Ready. Add your OpenAI key to .env, then: make up && make run"

up:
	docker compose up -d
	@until docker exec llm-gateway-redis redis-cli ping >/dev/null 2>&1; do sleep 1; done
	@echo "Redis ready on :6379"

run:
	$(RUNNER) $(PY) -m uvicorn app.main:app --host 0.0.0.0 --port $(PORT) \
		--workers 4 --loop uvloop --http httptools

demo:
	@$(RUNNER) $(PY) demo.py

load:
	@$(RUNNER) $(PY) load_test.py

reset:
	@docker exec llm-gateway-redis redis-cli FLUSHALL >/dev/null
	@echo "Cache cleared"

down:
	docker compose down
