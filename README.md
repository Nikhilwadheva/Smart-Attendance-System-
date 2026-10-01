# Face Recognition Smart Attendance System

A local Flask application for face enrollment, camera-based attendance check-in, attendance history, and CSV export. Face matching uses OpenCV's LBPH recognizer. The database and face samples are stored on the computer running the app.

This is a learning/local-use starter, not a production biometric identity or security system. Face recognition can make mistakes and should not be used as the sole basis for employment, access, or disciplinary decisions. Obtain informed permission, provide a non-biometric alternative, restrict access to the machine, and follow local privacy and employment laws.

## Requirements

- Windows 10/11
- Python 3.10 or later
- A webcam

## Setup in PowerShell

```powershell
cd "$HOME\OneDrive\Desktop\Smart Attendace System"
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

Open <http://127.0.0.1:5000>. Camera access is available on localhost in modern browsers. If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` in that terminal, then activate the environment again.

The `.env.example` file documents the supported environment variables. To override defaults in PowerShell, set them in the current terminal before starting the app, for example:

```powershell
$env:FACE_DISTANCE_THRESHOLD = "75"
python app.py
```

## Use

1. Open **Enroll person**, enter a unique employee ID and name, and confirm the consent notice.
2. Start the camera, face it in even lighting, and capture five samples.
3. Open **Check in**, start the camera, and choose **Verify & check in**. Only one check-in per person per local calendar day is recorded.
4. Open **Records** to filter by date and export the selected date as CSV.

Re-enrolling an existing employee ID replaces that person's old face samples. Attendance history is retained.

## Data locations

- SQLite database: `instance/attendance.sqlite3`
- Face samples: `instance/faces/`

Back up these files only when you have a lawful reason and a retention policy. To remove biometric data, stop the app and remove the stored samples and database. Removing the database also removes attendance history.

## Tests

```powershell
python -m pytest
```

## Configuration

- `SECRET_KEY`: Flask session key. Set a random value if enabling session features.
- `DATABASE`: SQLite file path.
- `FACE_DIR`: directory for enrolled face images.
- `FACE_DISTANCE_THRESHOLD`: LBPH confidence-distance limit; lower is stricter. Tune only against representative, consented test data.
- `PORT`: local server port (default `5000`).

The app binds to `127.0.0.1` by default. Do not expose it to a network without adding authentication, authorization, transport security, CSRF protections, secure biometric-data handling, and a reviewed deployment design.
