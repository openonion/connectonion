PYTEST?=pytest

.PHONY: test test-unit test-integration test-cli test-e2e test-real cov

test:
	$(PYTEST) -m "not real_api"

test-unit:
	$(PYTEST) -m unit

test-integration:
	$(PYTEST) -m integration

test-cli:
	$(PYTEST) -m cli

test-e2e:
	$(PYTEST) -m e2e

test-real:
	$(PYTEST) -m real_api

cov:
	$(PYTEST) --cov=connectonion --cov-report=term-missing -m "not real_api"
