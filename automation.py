"""
Playwright-based automation for eprescription.moh.gov.ge.

Logs in and submits one prescription per medication, collecting receipt numbers.
"""

import asyncio
import os
import time
from dataclasses import dataclass

import yaml
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, BrowserContext

from parser import Medication

load_dotenv()


@dataclass
class PrescriptionResult:
    medication: Medication
    receipt_number: str | None
    success: bool
    error: str | None = None


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


async def login(page: Page, cfg: dict) -> bool:
    """Log in to the e-prescription portal."""
    username = os.environ["EPRESCRIPTION_USERNAME"]
    password = os.environ["EPRESCRIPTION_PASSWORD"]
    login_cfg = cfg["login"]
    timing = cfg["timing"]

    await page.goto(cfg["site"]["login_url"], timeout=timing["page_load_timeout"])

    await page.wait_for_selector(login_cfg["username_selector"], timeout=timing["element_timeout"])
    await page.fill(login_cfg["username_selector"], username)
    await page.fill(login_cfg["password_selector"], password)
    await page.click(login_cfg["submit_selector"])

    # Wait for navigation after login
    await page.wait_for_load_state("networkidle", timeout=timing["page_load_timeout"])

    # Check we are no longer on the login page
    return page.url != cfg["site"]["login_url"]


async def submit_prescription(
    page: Page,
    medication: Medication,
    patient_id: str,
    cfg: dict,
) -> PrescriptionResult:
    """Navigate to the new-prescription form and submit one medication."""
    form_cfg = cfg["prescription_form"]
    timing = cfg["timing"]

    try:
        await page.goto(cfg["site"]["prescription_url"], timeout=timing["page_load_timeout"])
        await page.wait_for_load_state("networkidle", timeout=timing["page_load_timeout"])

        # Fill patient ID
        await page.wait_for_selector(form_cfg["patient_id_selector"], timeout=timing["element_timeout"])
        await page.fill(form_cfg["patient_id_selector"], patient_id)

        # Fill drug name
        await page.fill(form_cfg["drug_name_selector"], medication.name)

        # Fill dosage
        await page.fill(form_cfg["dosage_selector"], medication.dosage)

        # Fill instructions
        await page.fill(form_cfg["instructions_selector"], medication.instructions)

        # Submit
        await page.click(form_cfg["submit_selector"])
        await page.wait_for_load_state("networkidle", timeout=timing["page_load_timeout"])

        # Extract receipt number
        receipt_el = await page.query_selector(form_cfg["receipt_number_selector"])
        receipt_number = (await receipt_el.inner_text()).strip() if receipt_el else None

        return PrescriptionResult(
            medication=medication,
            receipt_number=receipt_number,
            success=receipt_number is not None,
        )

    except Exception as exc:
        return PrescriptionResult(
            medication=medication,
            receipt_number=None,
            success=False,
            error=str(exc),
        )


async def run_automation(
    medications: list[Medication],
    patient_id: str,
    headless: bool = True,
    config_path: str = "config.yaml",
    progress_callback=None,
) -> list[PrescriptionResult]:
    """
    Main entry point: log in and submit all medications as separate prescriptions.

    Args:
        medications:       Parsed medication list.
        patient_id:        The patient's personal/ID number.
        headless:          Run browser without visible window when True.
        config_path:       Path to config.yaml.
        progress_callback: Optional callable(index, total, result) for live updates.

    Returns:
        List of PrescriptionResult, one per medication.
    """
    cfg = load_config(config_path)
    results: list[PrescriptionResult] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context: BrowserContext = await browser.new_context()
        page = await context.new_page()

        logged_in = await login(page, cfg)
        if not logged_in:
            raise RuntimeError(
                "Login failed. Check your EPRESCRIPTION_USERNAME / EPRESCRIPTION_PASSWORD "
                "in the .env file."
            )

        delay_ms = cfg["timing"]["between_prescriptions_delay"]

        for i, med in enumerate(medications):
            result = await submit_prescription(page, med, patient_id, cfg)
            results.append(result)

            if progress_callback:
                progress_callback(i + 1, len(medications), result)

            if i < len(medications) - 1:
                await asyncio.sleep(delay_ms / 1000)

        await browser.close()

    return results


def run(medications: list[Medication], patient_id: str, headless: bool = True) -> list[PrescriptionResult]:
    """Synchronous wrapper around run_automation."""
    return asyncio.run(run_automation(medications, patient_id, headless=headless))
