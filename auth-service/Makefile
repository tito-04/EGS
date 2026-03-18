PYTHON ?= $(shell if [ -x ../.venv/bin/python ]; then echo ../.venv/bin/python; elif [ -x .venv/bin/python ]; then echo .venv/bin/python; elif [ -x venv/bin/python ]; then echo venv/bin/python; else echo python3; fi)
PYTEST ?= $(PYTHON) -m pytest

.PHONY: test-security
.PHONY: test-web-flow

test-security:
	$(PYTEST) -q tests/test_security_flows.py tests/test_rate_limits.py tests/test_production_config.py tests/test_observability.py

test-web-flow:
	$(PYTHON) scripts/test_web_flow.py
