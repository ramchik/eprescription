"""
Prescription automation module.

Drives Chrome via Selenium to:
  1. Search a patient by personal number + birth year.
  2. Open the new-prescription flow.
  3. Add one or more medications.
  4. Submit the prescription.
  5. Return the generated prescription number (e.g. D3E0020498041).
"""

import time
from dataclasses import dataclass, field
from typing import List, Optional

import yaml
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementNotInteractableException,
)


def _load_cfg(path: str = "config.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class Medication:
    """One medication to add to the prescription."""
    search_term: str          # text typed into the medication search box
    quantity: int             # unit count (1–500)
    duration_days: int        # validity period in days
    instructions: str         # dosage instructions (DS field)
    recipe_type: str = "მხოლოდ გენერიკი"   # or "მხოლოდ სავაჭრო"
    substitution_allowed: bool = True


@dataclass
class PrescriptionJob:
    """Holds the input and result of one prescription submission."""
    id: str
    patient_pn: str           # 11-digit personal number
    birth_year: str           # 4-digit birth year
    phone: str                # 9-digit Georgian mobile (5xxxxxxxx), or ""
    email: str
    medications: List[Medication]
    status: str = "pending"   # pending | running | done | error
    prescription_number: Optional[str] = None
    error: Optional[str] = None
    progress: int = 0         # 0–100


# ── Automator ────────────────────────────────────────────────────────────────

class Automator:
    """Selenium-based automator for the ePrescription portal."""

    def __init__(self, headless: bool = False, config_path: str = "config.yaml"):
        self._cfg = _load_cfg(config_path)
        self._base = self._cfg["site"]["base_url"]
        self._headless = headless
        self.driver: Optional[webdriver.Chrome] = None

    # ── Driver lifecycle ──────────────────────────────────────────────────

    def start(self) -> "Automator":
        opts = Options()
        if self._headless:
            opts.add_argument("--headless=new")
        opts.add_argument("--start-maximized")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        self.driver = webdriver.Chrome(options=opts)
        return self

    def quit(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    # ── Wait helpers ──────────────────────────────────────────────────────

    def _w(self, t: int = None) -> WebDriverWait:
        return WebDriverWait(self.driver, t or self._cfg["timeouts"]["ajax_wait"])

    def _el(self, sel: str):
        return self.driver.find_element(By.CSS_SELECTOR, sel)

    def _visible(self, sel: str, t: int = None):
        return self._w(t).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, sel))
        )

    def _clickable(self, sel: str, t: int = None):
        return self._w(t).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
        )

    def _modal_open(self, modal_id: str, t: int = None):
        """Wait for Bootstrap 3 modal to become visible."""
        self._w(t or self._cfg["timeouts"]["modal_wait"]).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, f"#{modal_id}"))
        )
        time.sleep(0.4)  # let CSS transition finish

    def _modal_closed(self, modal_id: str, t: int = None):
        """Wait for a Bootstrap 3 modal to disappear."""
        self._w(t or self._cfg["timeouts"]["modal_wait"]).until_not(
            EC.visibility_of_element_located((By.CSS_SELECTOR, f"#{modal_id}"))
        )

    def _dismiss_swal(self, t: int = 5):
        """Click the confirm button on a SweetAlert dialog, if one appears."""
        try:
            btn = self._w(t).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, ".sweet-alert.showSweetAlert .confirm")
                )
            )
            btn.click()
            time.sleep(0.3)
        except TimeoutException:
            pass  # no alert appeared

    # ── Login ─────────────────────────────────────────────────────────────

    def wait_for_manual_login(self):
        """Open the portal and block until the prescriptions table is visible."""
        self.driver.get(self._base)
        print("\nPlease log in manually in the Chrome window, then press Enter here.")
        input("Press Enter after logging in ...")
        self._visible("#prescriptions_table", t=30)
        print("Login confirmed. Starting automation.")

    # ── Patient search ────────────────────────────────────────────────────

    def search_patient(self, pn: str, birth_year: str) -> bool:
        """
        Fill the patient PN + birth-year fields and click Search.
        Returns True when the patient name is populated automatically.
        """
        s = self._cfg["selectors"]

        pn_field = self._clickable(s["patient_pn"])
        pn_field.clear()
        pn_field.send_keys(pn)

        year_field = self._el(s["patient_birth_year"])
        year_field.clear()
        year_field.send_keys(birth_year)

        self._clickable(s["search_button"]).click()

        try:
            self._w().until(
                lambda d: d.find_element(
                    By.CSS_SELECTOR, s["patient_name"]
                ).get_attribute("value") not in (None, "")
            )
            return True
        except TimeoutException:
            return False

    # ── Add one medication ────────────────────────────────────────────────

    def _add_one_med(self, med: Medication):
        s = self._cfg["selectors"]

        # Open the medications search modal
        self._clickable(s["modal2_add_med"]).click()
        self._modal_open("new_prescription_meds_modal")

        # Type search term and trigger the DataTables fetch
        inp = self._visible(s["meds_search"])
        inp.clear()
        inp.send_keys(med.search_term)
        time.sleep(0.3)
        self._clickable(s["meds_search_btn"]).click()
        time.sleep(2)  # wait for server-side DataTables response

        # Select the first matching row (enables the Confirm button)
        first_row = self._clickable(s["meds_first_row"])
        first_row.click()

        # Confirm the selection
        self._clickable(s["meds_confirm"]).click()
        self._modal_open("new_prescription_new_recipe_modal")

        # Fill quantity
        qty = self._visible(s["med_quantity"])
        qty.clear()
        qty.send_keys(str(med.quantity))

        # Fill duration in days (the JS auto-calculates the date)
        dur = self._el(s["med_duration_days"])
        dur.clear()
        dur.send_keys(str(med.duration_days))
        time.sleep(0.5)  # let the date field update

        # Fill dosage instructions
        ds = self._el(s["med_ds"])
        ds.clear()
        ds.send_keys(med.instructions)

        # Set recipe type dropdown
        try:
            Select(self._el(s["med_recipe_type"])).select_by_visible_text(
                med.recipe_type
            )
        except Exception:
            pass

        # Toggle substitution checkbox if needed
        doze_cb = self._el(s["med_doze"])
        if med.substitution_allowed != doze_cb.is_selected():
            doze_cb.click()

        # Add medication to the list
        self._clickable(s["med_confirm"]).click()
        self._modal_closed("new_prescription_new_recipe_modal")

    # ── Full prescription flow ────────────────────────────────────────────

    def run_job(self, job: PrescriptionJob) -> PrescriptionJob:
        """
        Execute the complete prescription creation flow for one job.
        Updates job.status, job.progress, job.prescription_number, job.error.
        """
        s = self._cfg["selectors"]
        job.status = "running"

        try:
            # 1. Search patient
            job.progress = 10
            if not self.search_patient(job.patient_pn, job.birth_year):
                job.status = "error"
                job.error = "Patient not found for PN/birth year combination"
                return job

            # 2. Click Add prescription
            job.progress = 20
            self._clickable(s["add_prescription_btn"]).click()
            time.sleep(1)
            self._dismiss_swal(t=3)  # handle isAlive check alerts

            # 3. Fill Modal 1 (patient contact info)
            self._modal_open("new_prescription_modal_1")
            job.progress = 30

            if job.phone:
                try:
                    tel = self._el(s["modal1_phone"])
                    tel.clear()
                    tel.send_keys(job.phone)
                except ElementNotInteractableException:
                    pass
            else:
                cb = self._el(s["modal1_no_phone"])
                if not cb.is_selected():
                    cb.click()

            if job.email:
                try:
                    mail = self._el(s["modal1_email"])
                    mail.clear()
                    mail.send_keys(job.email)
                except ElementNotInteractableException:
                    pass

            self._clickable(s["modal1_next"]).click()
            time.sleep(0.5)
            self._dismiss_swal(t=8)  # new-patient confirmation

            # 4. Add medications in Modal 2
            self._modal_open("new_prescription_modal_2", t=20)
            job.progress = 40

            before = self._read_numbers()

            total = len(job.medications)
            for i, med in enumerate(job.medications):
                self._add_one_med(med)
                job.progress = 40 + int(40 * (i + 1) / total)
                time.sleep(0.3)

            # 5. Submit the prescription
            job.progress = 85
            self._clickable(s["modal2_submit"]).click()
            time.sleep(1)
            self._dismiss_swal(t=15)  # "prescription issued" success alert

            # 6. Read the new prescription number from the refreshed table
            time.sleep(2)
            after = self._read_numbers()
            new = [n for n in after if n not in before]

            job.progress = 100
            job.status = "done"
            job.prescription_number = (
                new[0] if new else (after[0] if after else None)
            )

        except Exception as exc:
            job.status = "error"
            job.error = str(exc)

        return job

    def _read_numbers(self) -> list:
        """Return all prescription numbers currently visible in the table."""
        rows = self.driver.find_elements(
            By.CSS_SELECTOR, "#prescriptions_table tbody tr"
        )
        numbers = []
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if len(cells) >= 2:
                text = cells[1].text.strip()
                if text:
                    numbers.append(text)
        return numbers
