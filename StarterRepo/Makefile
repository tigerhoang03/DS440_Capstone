.PHONY: fmt lint test run-api run-ingest

fmt:
	python -m ruff format .

lint:
	python -m ruff check .

test:
	pytest -q

run-api:
	uvicorn newssentinel.api.main:app --reload

run-ingest:
	python -m newssentinel.worker.ingest
