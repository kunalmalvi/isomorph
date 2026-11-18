# Convenience targets. Everything also works without make: see README.md.
PY ?= python3

.PHONY: run test doctor backup docker
run:
	$(PY) ./isomorph serve

test:
	cd backend && $(PY) -m pytest tests -q -rs

doctor:
	$(PY) ./isomorph doctor

backup:
	$(PY) ./isomorph backup

docker:
	docker compose -f docker-compose.simple.yml up --build
