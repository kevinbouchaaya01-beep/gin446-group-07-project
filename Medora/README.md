# Medora — clinic booking prototype

## Run on Mac
Open this folder in VS Code. Stop any previous Flask server with Control+C.
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```
Open http://127.0.0.1:5000. All demo accounts use the password configured in the DEMO_PASSWORD environment variable.
- patient@medora.test
- doctor@medora.test (Cardiology)
- assistant@medora.test
- admin@medora.test

Use separate browser profiles/private windows for simultaneous roles. Patient books Sarah Haddad, assistant confirms then checks in, doctor starts then completes consultation. Dashboard polls every 8 seconds. Admin can create staff. Demo slots are seeded for the next seven days on startup. All times are server-local. SQLite persists in medora.db. Do not use real patient information.

## AI
Optional: `export GEMINI_API_KEY='your-key'` before starting. Model can be set with GEMINI_MODEL. AI extracts explicitly requested specialty, exact date and morning/afternoon, then server filters actual slots. No diagnosis, no automatic booking. Without key, manual booking works. Do not submit sensitive information.

## Architecture
Flask/Jinja HTML, CSS, vanilla JS Fetch, SQLite. Users 1:N slots (doctor), slots 1:N appointments (only one non-cancelled booking), users 1:N appointments (patient). Password hashes, session cookies, CSRF tokens, parameterized SQL, server-side role and ownership checks, unique partial index preventing double booking. GET /api/slots and /api/appointments; POST /api/smart, /book, /appointment/<id>/status, /availability, /staff.

## Limitations and course alignment
Local prototype only; PostgreSQL migration and Render deployment not implemented. No real clinical records, email, payments, rescheduling (cancel and rebook), or consultation notes. Demo credentials are public; do not deploy this database publicly. DEMO_MODE=0 prevents new demo seeding but does not remove existing accounts; production provisioning, persistent SECRET_KEY, HTTPS, rate limiting and security review required. AI calls and runtime tests need verification. Syllabus specifies GitHub Copilot as approved coding assistant; obtain instructor permission for ChatGPT-generated code and disclose/verify contributions. Both teammates should understand and test every component.

## Tests
Run `python -m pytest -q` after installation. Tests use a temporary database.
