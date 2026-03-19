"""
Flask web interface for the e-prescription automation tool.

Run with:
    python app.py
Then open http://localhost:5000 in your browser.
"""

import os
import threading
from flask import Flask, render_template, request, jsonify, session

from parser import parse_prescription
from automation import run_automation, PrescriptionResult
import asyncio

app = Flask(__name__)
app.secret_key = os.urandom(24)

# In-memory job store (fine for single-user local use)
jobs: dict[str, dict] = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/parse", methods=["POST"])
def parse():
    """Parse prescription text and return medication list as JSON."""
    data = request.get_json()
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"error": "Empty prescription text"}), 400

    meds = parse_prescription(text)
    if not meds:
        return jsonify({"error": "Could not parse any medications from the text"}), 400

    return jsonify({
        "medications": [
            {
                "number": m.number,
                "name": m.name,
                "dosage": m.dosage,
                "instructions": m.instructions,
            }
            for m in meds
        ]
    })


@app.route("/submit", methods=["POST"])
def submit():
    """Start automated prescription submission in a background thread."""
    data = request.get_json()
    text = data.get("text", "").strip()
    patient_id = data.get("patient_id", "").strip()
    headless = data.get("headless", True)

    if not text or not patient_id:
        return jsonify({"error": "prescription text and patient_id are required"}), 400

    if not os.environ.get("EPRESCRIPTION_USERNAME") or not os.environ.get("EPRESCRIPTION_PASSWORD"):
        return jsonify({
            "error": "Credentials not set. Copy .env.example to .env and fill in your username/password."
        }), 400

    meds = parse_prescription(text)
    if not meds:
        return jsonify({"error": "Could not parse medications"}), 400

    job_id = os.urandom(8).hex()
    jobs[job_id] = {
        "status": "running",
        "total": len(meds),
        "completed": 0,
        "results": [],
        "error": None,
    }

    def _run():
        results: list[PrescriptionResult] = []

        def on_progress(idx, total, result):
            jobs[job_id]["completed"] = idx
            jobs[job_id]["results"].append({
                "number": result.medication.number,
                "name": result.medication.name,
                "dosage": result.medication.dosage,
                "receipt_number": result.receipt_number,
                "success": result.success,
                "error": result.error,
            })

        try:
            asyncio.run(run_automation(
                meds,
                patient_id,
                headless=headless,
                progress_callback=on_progress,
            ))
            jobs[job_id]["status"] = "done"
        except Exception as exc:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = str(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    return jsonify({"job_id": job_id, "total": len(meds)})


@app.route("/status/<job_id>")
def status(job_id: str):
    """Poll job status."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify(job)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    app.run(debug=True, port=5000)
