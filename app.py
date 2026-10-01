from __future__ import annotations

import csv
import io
import os
import re
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, make_response, render_template, request

from database import init_app as init_database
from database import list_attendance, record_attendance
from recognizer import FaceRecognitionService, ImageInputError

load_dotenv()


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "local-development-only-change-me"),
        DATABASE=os.environ.get("DATABASE", str(Path(app.instance_path) / "attendance.sqlite3")),
        FACE_DIR=os.environ.get("FACE_DIR", str(Path(app.instance_path) / "faces")),
        FACE_DISTANCE_THRESHOLD=float(os.environ.get("FACE_DISTANCE_THRESHOLD", "75")),
        MAX_CONTENT_LENGTH=24 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["FACE_DIR"]).mkdir(parents=True, exist_ok=True)
    init_database(app)
    face_service = FaceRecognitionService(
        app.config["DATABASE"],
        app.config["FACE_DIR"],
        app.config["FACE_DISTANCE_THRESHOLD"],
    )
    app.extensions["face_service"] = face_service

    @app.get("/")
    def index():
        return render_template("index.html", today=date.today().isoformat())

    @app.get("/enroll")
    def enroll_page():
        return render_template("enroll.html")

    @app.get("/records")
    def records_page():
        return render_template("records.html", today=date.today().isoformat())

    @app.post("/api/enroll")
    def enroll():
        payload = request.get_json(silent=True) or {}
        employee_code = str(payload.get("employee_code", "")).strip()
        name = str(payload.get("name", "")).strip()
        frames = payload.get("frames")

        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", employee_code):
            return jsonify(error="Use 1-32 letters, numbers, underscores, or hyphens for the ID."), 400
        if not 2 <= len(name) <= 100:
            return jsonify(error="Name must be between 2 and 100 characters."), 400
        if not isinstance(frames, list) or not 3 <= len(frames) <= 8:
            return jsonify(error="Capture between 3 and 8 face samples."), 400

        try:
            sample_count = face_service.enroll(employee_code, name, frames)
        except ImageInputError as exc:
            return jsonify(error=str(exc)), 400
        except RuntimeError as exc:
            app.logger.exception("Face enrollment failed")
            return jsonify(error=str(exc)), 500

        return jsonify(message=f"{name} enrolled with {sample_count} face samples.", sample_count=sample_count), 201

    @app.post("/api/recognize")
    def recognize():
        payload = request.get_json(silent=True) or {}
        try:
            result = face_service.recognize(payload.get("frame", ""))
        except ImageInputError as exc:
            return jsonify(error=str(exc)), 400
        except RuntimeError as exc:
            app.logger.exception("Face recognition failed")
            return jsonify(error=str(exc)), 500

        if not result:
            return jsonify(recognized=False, message="No registered face matched. Enroll the person or try again."), 200

        employee_id, employee_code, name = result
        inserted = record_attendance(employee_id)
        return jsonify(
            recognized=True,
            checked_in=inserted,
            employee_code=employee_code,
            name=name,
            message=("Attendance recorded." if inserted else "Attendance was already recorded today."),
        )

    @app.get("/api/attendance")
    def attendance():
        selected_date = request.args.get("date", date.today().isoformat())
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", selected_date):
            return jsonify(error="Date must use YYYY-MM-DD format."), 400
        try:
            date.fromisoformat(selected_date)
        except ValueError:
            return jsonify(error="Enter a valid calendar date."), 400
        return jsonify(date=selected_date, records=list_attendance(selected_date))

    @app.get("/api/attendance/export.csv")
    def export_attendance():
        selected_date = request.args.get("date", date.today().isoformat())
        try:
            date.fromisoformat(selected_date)
        except ValueError:
            return jsonify(error="Enter a valid date using YYYY-MM-DD format."), 400
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(["Employee ID", "Name", "Attendance Date", "Check-in Time"])
        for record in list_attendance(selected_date):
            writer.writerow([record["employee_code"], record["name"], record["attendance_date"], record["checked_in_at"]])
        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "text/csv; charset=utf-8"
        response.headers["Content-Disposition"] = f'attachment; filename="attendance-{selected_date}.csv"'
        return response

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
