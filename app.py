"""
Flask web UI for prescription automation.

Start with:
    python app.py

Then open http://localhost:5000 in your browser.
The first request that submits a job will open a Chrome window and ask
you to log in once. All subsequent jobs reuse the same browser session.
"""

import threading
import uuid

from flask import Flask, jsonify, render_template, request

from automation import Automator, Medication, PrescriptionJob

app = Flask(__name__)

# ── Global automator (one browser session for the lifetime of the server) ──

_automator: Automator | None = None
_automator_lock = threading.Lock()


def _get_automator() -> Automator:
    global _automator
    with _automator_lock:
        if _automator is None:
            _automator = Automator(headless=False)
            _automator.start()
            _automator.wait_for_manual_login()
    return _automator


# ── In-memory job store ─────────────────────────────────────────────────────

_jobs: dict[str, PrescriptionJob] = {}
_jobs_lock = threading.Lock()


# ── Routes ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/submit", methods=["POST"])
def submit():
    data = request.get_json(force=True)

    medications = [
        Medication(
            search_term=m["search_term"],
            quantity=int(m["quantity"]),
            duration_days=int(m["duration_days"]),
            instructions=m["instructions"],
            recipe_type=m.get("recipe_type", "მხოლოდ გენერიკი"),
            substitution_allowed=bool(m.get("substitution_allowed", True)),
        )
        for m in data["medications"]
    ]

    job = PrescriptionJob(
        id=str(uuid.uuid4()),
        patient_pn=data["patient_pn"],
        birth_year=data["birth_year"],
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        medications=medications,
    )

    with _jobs_lock:
        _jobs[job.id] = job

    def _run():
        auto = _get_automator()
        auto.run_job(job)

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"job_id": job.id})


@app.route("/status/<job_id>")
def status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"error": "job not found"}), 404
    return jsonify(
        {
            "status": job.status,
            "progress": job.progress,
            "prescription_number": job.prescription_number,
            "error": job.error,
        }
    )


if __name__ == "__main__":
    app.run(debug=False, port=5000)
