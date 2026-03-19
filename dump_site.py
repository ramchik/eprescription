"""
Run this script ONCE to dump the HTML of every page in the site.
It opens a real Chrome window — log in manually, then it saves
the HTML of each page to the dumps/ folder.

Usage:
    pip install selenium
    python dump_site.py
"""

import time
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

DUMP_DIR = Path("dumps")
DUMP_DIR.mkdir(exist_ok=True)

BASE = "https://eprescription.moh.gov.ge"


def save(driver, name: str):
    path = DUMP_DIR / f"{name}.html"
    content = driver.page_source
    path.write_text(content, encoding="utf-8")
    print(f"  saved → {path}  ({len(content):,} bytes)")


def main():
    options = Options()
    options.add_experimental_option("detach", False)
    # Use your installed Chrome — no separate driver download needed
    options.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=options)

    # ── Step 1: Login page ──────────────────────────────────────────────
    print("\n[1] Opening the site — LOG IN MANUALLY in the browser window.")
    driver.get(BASE)
    save(driver, "01_home")

    input("\n     >>> Log in, then press Enter here to continue ...")

    save(driver, "02_after_login")
    print(f"     URL after login: {driver.current_url}")

    # ── Step 2: Dump every internal link on the dashboard ──────────────
    anchors = driver.find_elements(By.TAG_NAME, "a")
    links = sorted(set(
        a.get_attribute("href") for a in anchors
        if a.get_attribute("href") and BASE in a.get_attribute("href")
    ))
    print(f"\n[2] Found {len(links)} internal links — visiting each one.")

    for i, url in enumerate(links, 1):
        try:
            driver.get(url)
            time.sleep(1)
            slug = url.replace(BASE, "").strip("/").replace("/", "_") or "root"
            save(driver, f"{i+2:02d}_{slug}")
            forms = driver.find_elements(By.TAG_NAME, "form")
            if forms:
                print(f"     ^ {len(forms)} form(s) on this page")
        except Exception as e:
            print(f"  skip {url}: {e}")

    # ── Step 3: Prescription form ───────────────────────────────────────
    print("\n[3] Navigate to the NEW PRESCRIPTION page in the browser.")
    input("     >>> Press Enter when you are on the prescription form ...")
    save(driver, "ZZ_prescription_form")
    print(f"     URL: {driver.current_url}")

    driver.quit()
    print(f"\nAll dumps saved to ./{DUMP_DIR}/")
    print("Share the dumps/ folder and I will build the automation.")


main()
