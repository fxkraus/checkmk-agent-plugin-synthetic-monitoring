"""Example journey. Real journeys are baked per worker; secrets come from env, never inline."""

import os

from synmon_executor import journey


@journey(name="example-login", target_host="app.example.com", max_age_s=900, interval_s=300)
async def run(page, ctx):
    async with ctx.step("open login page"):
        await page.goto("https://app.example.com/login", wait_until="networkidle")
    async with ctx.step("submit credentials"):
        await page.fill("#username", os.environ["SYNMON_DEMO_USER"])
        await page.fill("#password", os.environ["SYNMON_DEMO_PASSWORD"])
        await page.click("button[type=submit]")
    async with ctx.step("verify dashboard"):
        await page.wait_for_selector("text=Dashboard")
