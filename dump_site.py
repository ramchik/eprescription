"""
Run this script ONCE to dump the HTML of every page in the site.
It will open a real browser window — log in manually, then it
saves the HTML of each page to the /dumps/ folder.

Usage:
    pip install playwright
    playwright install chromium
    python dump_site.py
"""

import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

DUMP_DIR = Path("dumps")
DUMP_DIR.mkdir(exist_ok=True)

BASE = "https://eprescription.moh.gov.ge"

async def save(page, name: str):
    path = DUMP_DIR / f"{name}.html"
    content = await page.content()
    path.write_text(content, encoding="utf-8")
    print(f"  saved → {path}  ({len(content):,} bytes)")

async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        # ── Step 1: Login page ──────────────────────────────────────────
        print("\n[1] Opening login page — LOG IN MANUALLY, then press Enter here.")
        await page.goto(BASE)
        await save(page, "01_home")
        input("     >>> Press Enter after you have logged in ...")

        await save(page, "02_after_login")
        print(f"     URL after login: {page.url}")

        # ── Step 2: Dump every link found on the dashboard ─────────────
        links = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        links = sorted(set(l for l in links if BASE in l))
        print(f"\n[2] Found {len(links)} internal links — visiting each one.")

        for i, url in enumerate(links, 1):
            try:
                await page.goto(url, timeout=15000)
                slug = url.replace(BASE, "").strip("/").replace("/", "_") or "root"
                await save(page, f"{i+2:02d}_{slug}")
                # Also dump any forms on the page
                forms = await page.query_selector_all("form")
                if forms:
                    print(f"     ^ {len(forms)} form(s) on this page")
            except Exception as e:
                print(f"  skip {url}: {e}")

        # ── Step 3: Dump network requests log ──────────────────────────
        print("\n[3] Navigate to the NEW PRESCRIPTION page, then press Enter.")
        input("     >>> Press Enter when you are on the new-prescription form ...")
        await save(page, "ZZ_prescription_form")
        print(f"     URL: {page.url}")

        await browser.close()
        print(f"\nAll dumps saved to ./{DUMP_DIR}/")
        print("Share the contents of that folder and I will build the automation.")

asyncio.run(main())
