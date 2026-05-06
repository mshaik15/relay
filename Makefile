.PHONY: test test-filters test-plc test-safety test-config

test:
	uv run pytest tests/ -v

test-filters:
	uv run pytest tests/test_filters.py -v

test-plc:
	uv run pytest tests/test_plc.py -v

test-safety:
	uv run pytest tests/test_safety.py -v

test-config:
	uv run pytest tests/test_config.py -v