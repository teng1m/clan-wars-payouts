.PHONY: install dev prod

install:
	uv sync

dev:
	uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

prod:
	uv run uvicorn app.main:app --host 0.0.0.0 --port $${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'
