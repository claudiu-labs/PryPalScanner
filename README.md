# PryPalScanner (Streamlit + Google Sheets)

Browser-based version designed for Zebra TC21. Data is stored in Google Sheets.

## 1) Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## 2) Google Sheets setup

Create a Google Sheet and share it with your Service Account email (Editor).

Set one of these:

- `GOOGLE_SERVICE_ACCOUNT_JSON` (JSON string)
- `GOOGLE_SERVICE_ACCOUNT_FILE` (path to json file)

Also set (one of the two):

- `GOOGLE_SHEET_ID`
- `GOOGLE_SHEET_TITLE` (optional, used to create sheet if ID missing)
- `ADMIN_PASSWORD`

Example (Linux/macOS):

```bash
export GOOGLE_SHEET_ID="your_sheet_id"
export GOOGLE_SERVICE_ACCOUNT_FILE="/path/to/service_account.json"
export ADMIN_PASSWORD="your_password"
```

Streamlit Cloud alternative: use `.streamlit/secrets.toml` with `gcp_service_account`.

## 3) Zebra DataWedge (Browser mode)

Because this is a web app, configure DataWedge to send **keystrokes**.

Recommended profile:
- Profile name: `PryPalScanner`
- Associated app: your browser (Chrome)
- Barcode input: ON (QR enabled)
- Keystroke output: ON
- Send ENTER suffix: ON (so Streamlit captures the scan)
- Intent output: OFF

## 4) Notes about OCR

OCR uses pytesseract if available on the host. If Tesseract is not installed, OCR will be disabled automatically and you will enter values manually.

## 5) Sheets created automatically

The app will create these worksheets if missing:
- `materials`
- `settings`
- `drums`
- `pallets`

## 6) Operator flow

- Select material
- Scan drum QR
- Enter Material Code and Standard Quantity (or use camera OCR)
- Save
- When max qty reached, generate pallet

## 7) Admin

- Manage materials
- Set global pallet counter
- View history / search by drum number

---

If you want email sending, we can add SMTP queue + retry in a later step.
