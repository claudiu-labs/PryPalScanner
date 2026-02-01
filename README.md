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
- OR `GOOGLE_APPS_SCRIPT_URL` (Apps Script Web App URL)
- OR `FIREBASE_SERVICE_ACCOUNT_JSON` (Firestore, recommended for DB)
- `GOOGLE_APPS_SCRIPT_KEY` (optional, if you enable API key check)

Also set:

- `GOOGLE_SHEET_ID`
- `GOOGLE_SHEET_TITLE` (optional, used to create sheet if ID missing)
 - `ADMIN_PASSWORD` (admin login)
 - `OPERATOR_PASSWORD` (operator login)

Example (Linux/macOS):

```bash
export GOOGLE_SHEET_ID="your_sheet_id"
export GOOGLE_SERVICE_ACCOUNT_FILE="/path/to/service_account.json"
export ADMIN_PASSWORD="your_password"
```

Streamlit Cloud alternative: use `.streamlit/secrets.toml` with `gcp_service_account`.

## 2c) Firestore alternative (recommended for DB)

1) Firebase Console -> Project Settings -> Service Accounts
2) Generate new private key (JSON)
3) Put JSON in `.streamlit/secrets.toml`:

```
FIREBASE_SERVICE_ACCOUNT_JSON = """{ ... full json ... }"""
```

The app will automatically use Firestore if this secret is present.

## 2b) Apps Script alternative (no Service Account)

Use this if you don't want Google Cloud credentials. Create a bound Apps Script:

1) Open your Google Sheet
2) Extensions -> Apps Script
3) Paste this script and deploy as Web App (Execute as: Me, Access: Anyone)

```
var API_KEY = "CHANGE_ME"; // optional

function doPost(e) {
  var body = JSON.parse(e.postData.contents || '{}');
  if (API_KEY && body.apiKey !== API_KEY) {
    return ContentService.createTextOutput(JSON.stringify({ok:false, error:"unauthorized"}))
      .setMimeType(ContentService.MimeType.JSON);
  }
  var action = body.action;
  var sheetName = body.sheet;
  var ss = body.sheetId ? SpreadsheetApp.openById(body.sheetId) : SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(sheetName);

  function out(obj) {
    return ContentService.createTextOutput(JSON.stringify(obj))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (action === 'ensure') {
    if (!sh) sh = ss.insertSheet(sheetName);
    var headers = body.headers || [];
    if (sh.getLastRow() === 0 && headers.length) {
      sh.appendRow(headers);
    }
    return out({ok: true});
  }

  if (!sh) return out({ok: false, error: 'Sheet not found'});

  if (action === 'get') {
    return out({ok: true, values: sh.getDataRange().getValues()});
  }
  if (action === 'row') {
    var row = body.row || 1;
    var values = sh.getRange(row, 1, 1, sh.getLastColumn()).getValues()[0];
    return out({ok: true, values: values});
  }
  if (action === 'append') {
    sh.appendRow(body.values || []);
    return out({ok: true});
  }
  if (action === 'update') {
    sh.getRange(body.row, body.col).setValue(body.value);
    return out({ok: true});
  }
  if (action === 'delete') {
    sh.deleteRow(body.row);
    return out({ok: true});
  }

  return out({ok: false, error: 'Unknown action'});
}
```

Then set:
```
GOOGLE_APPS_SCRIPT_URL = "https://script.google.com/macros/s/XXXX/exec"
```

## 3) Zebra DataWedge (Browser mode)

Because this is a web app, configure DataWedge to send **keystrokes**.

Recommended profile:
- Profile name: `PryPalScanner`
- Associated app: your browser (Chrome)
- Barcode input: ON (QR enabled)
- Keystroke output: ON
- Send ENTER suffix: ON (so Streamlit captures the scan)
- Intent output: OFF

## 4) QR format

Expected scan format (DataWedge sends keystrokes):

```
<DRUM_TYPE> <DRUM_NUMBER>
```

Example:

```
DWP1500_LV 15518289
```

Material Code and Standard Quantity are captured separately (manual input or OCR).

## 5) Notes about OCR

OCR uses pytesseract if available on the host. If Tesseract is not installed, OCR will be disabled automatically and you will enter values manually.

## 6) Sheets created automatically

The app will create these worksheets if missing:
- `materials`
- `settings`
- `drums`
- `pallets`

## 7) Operator flow

- Select material
- Scan drum QR
- Enter Material Code and Standard Quantity (or use camera OCR)
- Save
- When max qty reached, generate pallet

## 8) Admin

- Manage materials
- Set global pallet counter
- Set reports email (used for CSV/XLSX exports)
- View history / search by drum number

## 9) Database schema (Firestore)

Collections:

- `materials` (doc id = `material_code`)
  - `material_code` (string)
  - `description` (string)
  - `max_qty` (number)
  - `prefix` (string)
  - `allow_incomplete` (boolean)
  - `active` (boolean)
- `settings` (doc id = `global`)
  - `global_pallet_counter` (number)
  - `report_email` (string)
- `drums` (doc id = `drum_number`)
  - `timestamp` (string)
  - `material_code` (string)
  - `drum_number` (string)
  - `drum_type` (string)
  - `standard_qty` (string)
  - `pallet_id` (string)
  - `status` (ACTIVE/COMPLETED)
  - `device_id` (string)
  - `operator` (string)
- `pallets` (doc id = `pallet_id`)
  - `pallet_id` (string)
  - `material_code` (string)
  - `description` (string)
  - `created_at` (string)
  - `count` (number)
  - `complete_type` (FULL/INCOMPLETE)
  - `email_subject` (string)
  - `email_body` (string)

---

If you want email sending, we can add SMTP queue + retry in a later step.

## 10) Android APK (WebView wrapper)

There is a minimal Android app in `android-app/` that opens the Streamlit URL in a WebView.

How it works:
- On first run, the app asks for the Streamlit URL and stores it locally.
- You can change the URL later via the menu.

Build (via GitHub Actions):
- Push any change in `android-app/` to trigger the workflow.
- Download the artifact `PryPalScanner-debug-apk` from the Actions run.

Quick download (QR):

![APK QR](android-app/apk-download-qr.png)

If you want the direct URL, it's the `apk-latest` release asset:

```
https://github.com/claudiu-labs/PryPalScanner/releases/download/apk-latest/app-debug.apk
```
