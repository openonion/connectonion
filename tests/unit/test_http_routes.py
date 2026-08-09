"""Audience-scoped publisher HTTP routes (#772)."""

import pytest


def test_groups_own_the_audience_and_visible_prefix():
    from connectonion import HTTPRouter

    http = HTTPRouter()

    @http.public.get("/events/{category}.ics")
    def events(category):
        return category

    @http.contacts.post("/preferences")
    def preferences(request):
        return request.json()

    @http.admin.post("/refresh")
    def refresh():
        return {"started": True}

    assert [(route.method, route.path, route.audience) for route in http.routes] == [
        ("GET", "/public/events/{category}.ics", "public"),
        ("POST", "/contacts/preferences", "contacts"),
        ("POST", "/admin/refresh", "admin"),
    ]


def test_same_effective_path_cannot_be_registered_twice():
    from connectonion import HTTPRouter

    http = HTTPRouter()

    @http.public.get("/events/{category}")
    def first(category):
        return category

    with pytest.raises(ValueError, match="duplicate HTTP route"):
        @http.public.get("/events/{name}")
        def second(name):
            return name


@pytest.mark.parametrize("path", ["events", "//events", "/../_co/info", "/events?city=sydney"])
def test_relative_route_paths_fail_loudly(path):
    from connectonion import HTTPRouter

    http = HTTPRouter()
    with pytest.raises(ValueError):
        http.public.get(path)(lambda: None)


def test_framework_routes_cannot_be_shadowed():
    from connectonion import HTTPRouter

    http = HTTPRouter()
    with pytest.raises(ValueError, match="reserved by Connectonion"):
        http.admin.get("/logs")(lambda: None)


def test_static_route_wins_over_a_parameter_route():
    from connectonion import HTTPRouter

    http = HTTPRouter()
    http.public.get("/people/{name}")(lambda name: name)
    http.public.get("/people/me")(lambda: "me")

    route, params = http.match("GET", "/public/people/me")

    assert route.relative_path == "/people/me"
    assert params == {}


def test_method_mismatch_is_not_a_route_match():
    from connectonion import HTTPRouter

    http = HTTPRouter()
    http.public.get("/feed")(lambda: "feed")

    assert http.match("POST", "/public/feed") is None


def test_http_response_rejects_header_injection():
    from connectonion import HTTPResponse

    with pytest.raises(ValueError, match="header"):
        HTTPResponse("no", headers={"x-test": "ok\r\nx-admin: yes"})

    with pytest.raises(ValueError, match="media type"):
        HTTPResponse("no", media_type="text/plain\r\nx-admin: yes")

    with pytest.raises(TypeError, match="body"):
        HTTPResponse({"use": "a plain dict return for JSON"})


def test_create_app_rejects_an_object_that_is_not_an_http_router(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    from connectonion.network.host import SessionStorage, create_app

    monkeypatch.chdir(tmp_path)
    agent = MagicMock(name="agent")
    agent.name = "test"
    agent.tools.names.return_value = []

    with pytest.raises(TypeError, match="HTTPRouter"):
        create_app(
            lambda: agent,
            storage=SessionStorage(tmp_path / ".co" / "sessions.jsonl"),
            trust="open",
            http={},
        )


def test_handler_must_accept_every_path_parameter():
    from connectonion import HTTPRouter

    http = HTTPRouter()
    with pytest.raises(ValueError, match="does not accept path parameters"):
        http.public.get("/events/{category}")(lambda: "all")
