PYTEST?=pytest

.PHONY: test test-unit test-integration test-cli test-e2e test-real cov

# A -m on the command line REPLACES the one in pytest.ini's addopts rather than
# adding to it, so every target here has to spell the project's defaults out.
# Leaving `not network` off put 21 browser-stealth runs back in — real Chrome
# against a dozen third-party fingerprinting sites, slow and dependent on
# nobody's servers but theirs. Same mechanism as #578 and #444.
test:
	$(PYTEST) -m "not real_api and not network"

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
# `network` is deliberately NOT excluded here. It marks two different things:
# the relay end-to-end tests, which talk to our own relay and are the most
# valuable eight in this gate, and the browser-stealth runs, which drive a real
# Chrome against a dozen third-party fingerprinting sites. Excluding the marker
# drops both — I tried it and it removed the relay tests from the release gate,
# which is the gate answering a smaller question while looking the same size.
# Separating them needs a marker they do not share yet.
test-e2e:
	$(PYTEST) -m "e2e and not real_api"

test-real:
	$(PYTEST) -m real_api

cov:
	$(PYTEST) --cov=connectonion --cov-report=term-missing -m "not real_api and not network"
