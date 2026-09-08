PYTEST?=pytest

.PHONY: test test-unit test-cli test-e2e test-real cov

# The default: everything that runs offline, across every core. The marker
# expression is spelled out because a -m on the command line REPLACES the
# one in pytest.ini rather than adding to it — leaving `not network` off put
# 21 browser-stealth runs back in (real Chrome against third-party
# fingerprinting sites). Same mechanism as #578 and #444.
test:
	$(PYTEST) -n auto -m "not real_api and not network"

test-unit:
	$(PYTEST) -n auto -m "unit and not real_api and not network"

test-cli:
	$(PYTEST) -n auto -m "cli and not real_api and not network"

# End-to-end against our own system. Not the paid-provider tests under
# tests/e2e/real_api/ — those need four funded accounts and answer a different
# question, so they are opt-in via `make test-real`. A release gate that turns
# red because a laptop is unfunded teaches people to ignore red.
# `network` is deliberately NOT excluded here: it marks the relay end-to-end
# tests, which talk to our own relay and are the most valuable eight in this
# gate, as well as the browser-stealth runs. Separating them needs a marker
# they do not share yet.
test-e2e:
	$(PYTEST) -m "e2e and not real_api"

# Paid providers, real accounts, real money. Needs keys in the environment.
test-real:
	$(PYTEST) -m real_api

# Same selection as `make test`, with the report CI gates on.
cov:
	$(PYTEST) -n auto -m "not real_api and not network" \
		--cov=connectonion --cov-report=term-missing:skip-covered --cov-report=html
