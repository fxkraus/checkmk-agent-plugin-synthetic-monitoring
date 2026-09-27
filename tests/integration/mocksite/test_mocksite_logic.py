from tests.integration.mocksite import mocksite


def test_flaky_fails_first_then_succeeds():
    state = {"flaky_hits": 0}
    s1, _, _ = mocksite.handle("GET", "/flaky", {}, state)
    s2, _, _ = mocksite.handle("GET", "/flaky", {}, state)
    assert s1 == 500 and s2 == 200


def test_protected_requires_cookie():
    state = {"flaky_hits": 0}
    s_noauth, headers, _ = mocksite.handle("GET", "/protected", {}, state)
    assert s_noauth == 302 and headers["Location"] == "/login"
    s_auth, _, body = mocksite.handle("GET", "/protected", {"sid": "ok"}, state)
    assert s_auth == 200 and b"protected" in body.lower()


def test_login_sets_cookie():
    state = {"flaky_hits": 0}
    status, headers, _ = mocksite.handle("POST", "/login", {}, state)
    assert status == 302 and "sid=" in headers.get("Set-Cookie", "")


def test_home_has_vitals_hooks():
    state = {"flaky_hits": 0}
    status, _, body = mocksite.handle("GET", "/", {}, state)
    text = body.decode()
    assert status == 200
    assert "synmon-hero" in text and "synmon-inp-btn" in text and "synmon-shift" in text
