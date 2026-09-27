import os

from synmon_executor import journey, login

BASE = os.environ.get("MOCKSITE_URL", "http://localhost:8080")


@login(target_host="mock", name="login", max_age_s=300, interval_s=300)
async def do_login(page, ctx):
    async with ctx.step("sign in"):
        await page.goto(f"{BASE}/login")
        await page.click("#synmon-login-btn")
        await page.wait_for_url("**/protected")


@journey(name="home", target_host="mock", max_age_s=300, interval_s=300)
async def home(page, ctx):
    async with ctx.step("open home"):
        resp = await page.goto(BASE + "/")
        assert resp.ok
    async with ctx.step("interact"):
        await page.click("#synmon-inp-btn")
        await page.wait_for_timeout(300)


@journey(name="protected", target_host="mock", max_age_s=300, interval_s=300)
async def protected(page, ctx):
    async with ctx.step("open protected"):
        resp = await page.goto(f"{BASE}/protected")
        assert resp.ok
        await page.wait_for_selector("h1")


@journey(name="flaky", target_host="mock", max_age_s=300, interval_s=300, retries=2)
async def flaky(page, ctx):
    async with ctx.step("hit flaky"):
        resp = await page.goto(f"{BASE}/flaky")
        assert resp.ok, f"flaky returned {resp.status}"


@journey(name="slow", target_host="mock", max_age_s=300, interval_s=300, timeout_s=0.5)
async def slow(page, ctx):
    async with ctx.step("hang"):
        await page.goto(BASE + "/")
        await page.wait_for_timeout(5000)
