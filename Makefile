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

# End-to-end against our own system. Not the paid-provider tests under
# tests/e2e/real_api/ — those need four funded accounts and answer a different
# question, so they are opt-in via `make test-real`. A release gate that turns
# red because a laptop is unfunded teaches people to ignore red.
test-e2e:
	$(PYTEST) -m "e2e and not real_api"

test-real:
	$(PYTEST) -m real_api

cov:
	$(PYTEST) --cov=connectonion --cov-report=term-missing -m "not real_api"
