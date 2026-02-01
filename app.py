import json
import os
import re
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

import pandas as pd
import streamlit as st

try:
    import gspread
    from google.oauth2.service_account import Credentials
    from gspread.exceptions import SpreadsheetNotFound
except Exception as exc:  # pragma: no cover - runtime dependency
    gspread = None
    Credentials = None
    SpreadsheetNotFound = Exception

try:
    import firebase_admin
    from firebase_admin import credentials as fb_credentials
    from firebase_admin import firestore as fb_firestore
except Exception:
    firebase_admin = None
    fb_credentials = None
    fb_firestore = None

# Optional OCR (works only if tesseract is installed on the host)
try:
    import pytesseract
    from PIL import Image
except Exception:
    pytesseract = None
    Image = None

APP_TITLE = "PryPalScanner"

SHEET_TEMPLATES = {
    "materials": [
        "material_code",
        "description",
        "max_qty",
        "prefix",
        "allow_incomplete",
        "active",
    ],
    "settings": ["key", "value"],
    "drums": [
        "timestamp",
        "material_code",
        "drum_number",
        "drum_type",
        "standard_qty",
        "pallet_id",
        "status",
        "device_id",
        "operator",
    ],
    "pallets": [
        "pallet_id",
        "material_code",
        "created_at",
        "count",
        "complete_type",
    ],
}


# -------------------- Utilities --------------------

def get_secret(key: str, default: str | None = None) -> str | None:
    if key in st.secrets:
        return st.secrets[key]
    return os.getenv(key, default)

def parse_service_account_json(sa_json: str) -> dict:
    try:
        return json.loads(sa_json)
    except json.JSONDecodeError:
        if "private_key" not in sa_json:
            raise
        def repl(match):
            key = match.group(1)
            key = key.replace("\n", "\\n")
            return f"\"private_key\": \"{key}\""
        fixed = re.sub(r'"private_key"\s*:\s*"(.+?)"', repl, sa_json, flags=re.S)
        return json.loads(fixed)


def now_ts() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

def today_date() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")


def parse_qr(raw: str) -> dict:
    # Example: "DWP1500_LV 15518289"
    raw = raw.strip()
    drum_number = None
    match = re.search(r"(\d{5,})", raw)
    if match:
        drum_number = match.group(1)
    return {
        "raw": raw,
        "drum_type": raw,
        "drum_number": drum_number,
    }


def extract_ocr_fields(image_bytes: bytes, drum_number: str | None) -> dict:
    if pytesseract is None or Image is None:
        return {"material_code": None, "standard_qty": None, "raw_text": None}
    try:
        img = Image.open(image_bytes)
        text = pytesseract.image_to_string(img)
    except Exception:
        return {"material_code": None, "standard_qty": None, "raw_text": None}

    numbers = re.findall(r"\d+", text)
    numbers = [n for n in numbers if n != (drum_number or "")]

    material_code = None
    standard_qty = None

    # Heuristic: material code often 8 digits (e.g., 60115949)
    for n in numbers:
        if len(n) == 8:
            material_code = n
            break

    # Standard quantity: first remaining numeric value not 8 digits
    for n in numbers:
        if n != material_code and len(n) < 8:
            standard_qty = n
            break

    return {
        "material_code": material_code,
        "standard_qty": standard_qty,
        "raw_text": text,
    }

def normalize_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().upper() in {"TRUE", "1", "YES", "Y"}

def build_email_subject(material_code: str, pallet_id: str) -> str:
    return f"{today_date()} - Rebobinari \"Material {material_code}\" - {pallet_id}"

def build_email_body(material_code: str, description: str, pallet_id: str, drums_df: pd.DataFrame) -> str:
    header = f"Material {material_code} - Pallet {pallet_id}"
    lines = [header]
    if description:
        lines.append(f"Description: {description}")
    lines.append("Drum Number | Standard Quantity")
    if drums_df is not None and not drums_df.empty:
        for _, row in drums_df.iterrows():
            lines.append(f"{row.get('drum_number','')} | {row.get('standard_qty','')}")
    return "\n".join(lines)


# -------------------- Google Sheets --------------------

@st.cache_resource
def get_gs_client():
    if gspread is None or Credentials is None:
        return None

    sa_json = get_secret("GOOGLE_SERVICE_ACCOUNT_JSON")
    sa_file = get_secret("GOOGLE_SERVICE_ACCOUNT_FILE")

    if sa_json:
        info = json.loads(sa_json)
    elif sa_file:
        with open(sa_file, "r", encoding="utf-8") as f:
            info = json.load(f)
    elif "gcp_service_account" in st.secrets:
        info = st.secrets["gcp_service_account"]
    else:
        return None

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)

@st.cache_resource
def get_fs_client():
    sa_json = get_secret("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not sa_json or firebase_admin is None or fb_credentials is None or fb_firestore is None:
        return None
    info = parse_service_account_json(sa_json)
    if not firebase_admin._apps:
        cred = fb_credentials.Certificate(info)
        firebase_admin.initialize_app(cred)
    return fb_firestore.client()

def apps_script_call(url: str, payload: dict) -> dict:
    api_key = get_secret("GOOGLE_APPS_SCRIPT_KEY")
    if api_key and "apiKey" not in payload:
        payload["apiKey"] = api_key
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"Apps Script error: {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("Apps Script unreachable") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Apps Script invalid response") from exc

class AppsScriptSpreadsheet:
    def __init__(self, url: str, sheet_id: str | None = None):
        self.url = url
        self.sheet_id = sheet_id

    def worksheet(self, name: str):
        return AppsScriptWorksheet(self, name)

class AppsScriptWorksheet:
    def __init__(self, spreadsheet: AppsScriptSpreadsheet, name: str):
        self.spreadsheet = spreadsheet
        self.name = name

    def _call(self, action: str, **extra):
        payload = {
            "action": action,
            "sheet": self.name,
            "sheetId": self.spreadsheet.sheet_id,
        }
        payload.update(extra)
        return apps_script_call(self.spreadsheet.url, payload)

    def get_all_values(self):
        res = self._call("get")
        return res.get("values", [])

    def row_values(self, row: int):
        res = self._call("row", row=row)
        return res.get("values", [])

    def append_row(self, values: list):
        return self._call("append", values=values)

    def update_cell(self, row: int, col: int, value):
        return self._call("update", row=row, col=col, value=value)

    def delete_rows(self, row: int):
        return self._call("delete", row=row)

class FirestoreDatabase:
    def __init__(self, client):
        self.client = client

    def worksheet(self, name: str):
        return FirestoreCollection(self.client, name)

class FirestoreCollection:
    def __init__(self, client, name: str):
        self.client = client
        self.name = name
        self._is_firestore = True

    def _col(self):
        return self.client.collection(self.name)

    def get_doc(self, doc_id: str):
        return self._col().document(doc_id).get()

    def set_doc(self, doc_id: str, data: dict):
        return self._col().document(doc_id).set(data, merge=True)

    def add_doc(self, data: dict):
        return self._col().add(data)

    def update_doc(self, doc_id: str, updates: dict):
        return self._col().document(doc_id).set(updates, merge=True)

    def delete_doc(self, doc_id: str):
        return self._col().document(doc_id).delete()

    def stream(self):
        return list(self._col().stream())

    def query(self, filters: list[tuple]):
        q = self._col()
        for field, op, value in filters:
            q = q.where(field, op, value)
        return list(q.stream())

def get_or_create_spreadsheet(client, sheet_id: str | None, title: str | None):
    if sheet_id:
        try:
            return client.open_by_key(sheet_id), False
        except SpreadsheetNotFound:
            pass
        except Exception as exc:
            raise RuntimeError(
                f"Cannot access sheet id {sheet_id}. Check permissions or ID."
            ) from exc

    title = title or "PryPalScanner_Data"
    spreadsheet = client.create(title)
    return spreadsheet, True


def ensure_worksheet(spreadsheet, name: str, headers: list[str]):
    # Firestore backend
    if isinstance(spreadsheet, FirestoreDatabase):
        return spreadsheet.worksheet(name)
    # Apps Script backend
    if isinstance(spreadsheet, AppsScriptSpreadsheet):
        ws = spreadsheet.worksheet(name)
        ws._call("ensure", headers=headers)
        return ws

    # gspread backend
    try:
        ws = spreadsheet.worksheet(name)
    except Exception:
        ws = spreadsheet.add_worksheet(title=name, rows="1000", cols=str(len(headers)))
        ws.append_row(headers)
        return ws

    existing = ws.row_values(1)
    if existing != headers:
        if not existing:
            ws.append_row(headers)
    return ws


def load_sheet(ws) -> pd.DataFrame:
    if isinstance(ws, FirestoreCollection):
        docs = ws.stream()
        rows = []
        for doc in docs:
            data = doc.to_dict() or {}
            data["__doc_id"] = doc.id
            rows.append(data)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    values = ws.get_all_values()
    if not values:
        return pd.DataFrame()
    headers = values[0]
    rows = values[1:]
    df = pd.DataFrame(rows, columns=headers)
    df["__row"] = range(2, len(rows) + 2)
    return df


def get_header_map(ws) -> dict:
    if isinstance(ws, FirestoreCollection):
        return {}
    headers = ws.row_values(1)
    return {h: i + 1 for i, h in enumerate(headers)}


def update_row(ws, row_idx: int, updates: dict):
    if isinstance(ws, FirestoreCollection):
        ws.update_doc(str(row_idx), updates)
        return
    header_map = get_header_map(ws)
    for key, val in updates.items():
        col = header_map.get(key)
        if col:
            ws.update_cell(row_idx, col, val)


# -------------------- Data Helpers --------------------

def get_settings(ws_settings) -> dict:
    if isinstance(ws_settings, FirestoreCollection):
        doc = ws_settings.get_doc("global")
        if not doc.exists:
            return {}
        data = doc.to_dict() or {}
        return {k: str(v) for k, v in data.items()}
    df = load_sheet(ws_settings)
    if df.empty:
        return {}
    return {row["key"]: row["value"] for _, row in df.iterrows()}


def set_setting(ws_settings, key: str, value: str):
    if isinstance(ws_settings, FirestoreCollection):
        try:
            value_cast = int(value)
        except Exception:
            value_cast = value
        ws_settings.update_doc("global", {key: value_cast})
        return
    df = load_sheet(ws_settings)
    if df.empty:
        ws_settings.append_row([key, value])
        return
    row = df[df["key"] == key]
    if row.empty:
        ws_settings.append_row([key, value])
    else:
        row_idx = int(row.iloc[0]["__row"])
        update_row(ws_settings, row_idx, {"value": value})


def get_materials(ws_materials) -> pd.DataFrame:
    df = load_sheet(ws_materials)
    if df.empty:
        return df
    if "material_code" not in df.columns and "__doc_id" in df.columns:
        df["material_code"] = df["__doc_id"]
    if "active" in df.columns:
        df["active"] = df["active"].apply(normalize_bool)
    else:
        df["active"] = True
    return df


def get_active_drums(ws_drums, material_code: str) -> pd.DataFrame:
    if isinstance(ws_drums, FirestoreCollection):
        docs = ws_drums.query([
            ("material_code", "==", material_code),
            ("status", "==", "ACTIVE"),
        ])
        rows = []
        for doc in docs:
            data = doc.to_dict() or {}
            data["__doc_id"] = doc.id
            rows.append(data)
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)
    df = load_sheet(ws_drums)
    if df.empty:
        return df
    return df[
        (df["material_code"] == material_code)
        & (df["status"] == "ACTIVE")
    ]


def find_drum(ws_drums, drum_number: str) -> pd.DataFrame:
    if isinstance(ws_drums, FirestoreCollection):
        doc = ws_drums.get_doc(drum_number)
        if not doc.exists:
            return pd.DataFrame()
        data = doc.to_dict() or {}
        data["__doc_id"] = doc.id
        return pd.DataFrame([data])
    df = load_sheet(ws_drums)
    if df.empty:
        return df
    return df[df["drum_number"] == drum_number]

def get_pallet_date(ws_pallets, pallet_id: str) -> str | None:
    if not pallet_id:
        return None
    if isinstance(ws_pallets, FirestoreCollection):
        doc = ws_pallets.get_doc(pallet_id)
        if not doc.exists:
            return None
        data = doc.to_dict() or {}
        return data.get("created_at")
    df = load_sheet(ws_pallets)
    if df.empty:
        return None
    row = df[df["pallet_id"] == pallet_id]
    if row.empty:
        return None
    return row.iloc[0].get("created_at")


def add_drum(ws_drums, row: dict):
    if isinstance(ws_drums, FirestoreCollection):
        doc_id = row.get("drum_number")
        if not doc_id:
            raise RuntimeError("Missing drum_number for Firestore document id.")
        ws_drums.set_doc(doc_id, row)
        return
    headers = ws_drums.row_values(1)
    ws_drums.append_row([row.get(h, "") for h in headers])

def add_pallet(ws_pallets, pallet_id: str, row: dict):
    if isinstance(ws_pallets, FirestoreCollection):
        ws_pallets.set_doc(pallet_id, row)
        return
    headers = ws_pallets.row_values(1)
    ws_pallets.append_row([row.get(h, "") for h in headers])

def get_operator_name() -> str:
    return st.session_state.get("username") or get_secret("OPERATOR", "") or ""


def delete_row(ws, row_idx: int):
    if isinstance(ws, FirestoreCollection):
        ws.delete_doc(str(row_idx))
        return
    ws.delete_rows(row_idx)


# -------------------- UI Helpers --------------------

def inject_css():
    st.markdown(
        """
<style>
:root {
  --bg: #f6f2ea;
  --card: #ffffff;
  --primary: #1f6f8b;
  --accent: #f2a365;
  --ok: #2a9d8f;
  --warn: #e9c46a;
  --danger: #e76f51;
  --text: #1f2937;
}
html, body, [class*="st-"] { font-family: 'Rubik', 'Segoe UI', sans-serif; }
body { background: linear-gradient(180deg, var(--bg) 0%, #ffffff 100%); }
section.main > div { padding-top: 0.75rem; }
.stButton > button {
  width: 100%;
  padding: 1.2rem 1rem;
  border-radius: 16px;
  border: 0;
  background: var(--primary);
  color: white;
  font-size: 1.1rem;
  font-weight: 600;
}
.stButton > button:hover { background: #165a72; }
.status-pill {
  display: inline-block;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 700;
  color: #1f2937;
  background: var(--warn);
}
.status-green { background: var(--ok); color: white; }
.status-yellow { background: var(--warn); }
.status-full { background: var(--accent); color: #1f2937; }
.card {
  background: var(--card);
  border-radius: 16px;
  padding: 1rem;
  box-shadow: 0 8px 24px rgba(31,41,55,0.08);
}
input[type="text"], input[type="number"] {
  font-size: 1.05rem !important;
}
@media (max-width: 768px) {
  .stButton > button { font-size: 1.05rem; padding: 1.1rem; }
}
</style>
""",
        unsafe_allow_html=True,
    )


def wake_lock_script():
    st.components.v1.html(
        """
<script>
(async () => {
  try {
    if ('wakeLock' in navigator) {
      await navigator.wakeLock.request('screen');
    }
  } catch (e) {}
})();
</script>
""",
        height=0,
    )


# -------------------- Main App --------------------

def operator_screen(spreadsheet):
    ws_materials = ensure_worksheet(spreadsheet, "materials", SHEET_TEMPLATES["materials"])
    ws_settings = ensure_worksheet(spreadsheet, "settings", SHEET_TEMPLATES["settings"])
    ws_drums = ensure_worksheet(spreadsheet, "drums", SHEET_TEMPLATES["drums"])
    ws_pallets = ensure_worksheet(spreadsheet, "pallets", SHEET_TEMPLATES["pallets"])

    materials_df = get_materials(ws_materials)
    active_materials = materials_df[materials_df["active"]] if not materials_df.empty else pd.DataFrame()

    wake_lock_script()

    if "selected_material" not in st.session_state:
        st.session_state.selected_material = None

    if st.session_state.selected_material is None:
        st.markdown(f"## {APP_TITLE}")
        st.markdown("Selecteaza materialul pentru palet.")

        if active_materials.empty:
            st.warning("Nu exista materiale active. Contacteaza admin.")
            return

        cols = st.columns(2)
        for idx, (_, row) in enumerate(active_materials.iterrows()):
            code = row["material_code"]
            description = row.get("description", "")
            try:
                max_qty = int(row.get("max_qty") or 0)
            except Exception:
                max_qty = 0
            active_drums = get_active_drums(ws_drums, code)
            count = len(active_drums)

            if count == 0:
                status = "GREEN"
                status_label = "Empty"
            elif count < max_qty:
                status = "YELLOW"
                status_label = "In progress"
            else:
                status = "FULL"
                status_label = "Full"

            pill_class = "status-green" if status == "GREEN" else "status-yellow" if status == "YELLOW" else "status-full"

            with cols[idx % 2]:
                st.markdown(f"<div class='card'>", unsafe_allow_html=True)
                st.markdown(f"<span class='status-pill {pill_class}'>{status_label}</span>", unsafe_allow_html=True)
                st.markdown(f"### Material {code}")
                if description:
                    st.markdown(f"_{description}_")
                st.markdown(f"**{count} / {max_qty}**")
                if st.button(f"Deschide {code}", key=f"open_{code}"):
                    st.session_state.selected_material = code
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
        return

    # Material screen
    selected = st.session_state.selected_material
    row = materials_df[materials_df["material_code"] == selected]
    if row.empty:
        st.error("Material invalid.")
        st.session_state.selected_material = None
        return

    mat = row.iloc[0]
    try:
        max_qty = int(mat.get("max_qty") or 0)
    except Exception:
        max_qty = 0
    prefix = mat.get("prefix", "") or ""
    allow_incomplete = normalize_bool(mat.get("allow_incomplete", False))

    active_drums = get_active_drums(ws_drums, selected)
    count = len(active_drums)

    st.markdown(f"## Material {selected}")
    st.markdown(f"**{count} / {max_qty}**")

    if st.button("Inapoi la lista", key="back_to_list"):
        st.session_state.selected_material = None
        st.rerun()

    st.markdown("---")

    # List of scanned drums
    st.markdown("### Tamburi scanati (palet curent)")
    if active_drums.empty:
        st.info("Palet gol.")
    else:
        st.dataframe(active_drums[["drum_number"]], use_container_width=True)

    # Scan input
    st.markdown("### Scanare")
    st.caption("Foloseste scanerul Zebra sau introdu manual codul scanat.")

    if "pending_scan" not in st.session_state:
        st.session_state.pending_scan = None

    def process_scan(raw_value: str):
        raw_value = (raw_value or "").strip()
        if not raw_value:
            return
        parsed = parse_qr(raw_value)
        st.session_state.pending_scan = parsed
        st.session_state.scan_input = ""
        st.session_state.manual_scan_input = ""
        st.rerun()

    scan_raw = st.text_input(
        "Scaneaza / Introdu cod QR (Drum Type + Drum Number)",
        key="scan_input",
        placeholder="Ex: DWP1500_LV 15518289",
    )

    if scan_raw:
        process_scan(scan_raw)

    with st.expander("Introdu manual codul scanat"):
        manual_raw = st.text_input(
            "Cod scanat (manual)",
            key="manual_scan_input",
            placeholder="Ex: DWP1500_LV 15518289",
        )
        if st.button("Proceseaza manual"):
            process_scan(manual_raw)

    pending = st.session_state.get("pending_scan")

    if pending:
        st.markdown("### Confirmare eticheta")

        with st.form("confirm_scan"):
            st.markdown(f"**Drum Number:** {pending.get('drum_number') or 'N/A'}")
            std_qty = st.text_input("Standard Quantity (editabil)", key="std_qty")
            material_input = st.text_input("Material code (din eticheta)", key="material_code_input")

            use_camera = st.checkbox("Foloseste camera pentru OCR (optional)")
            ocr_material = None
            ocr_qty = None
            if use_camera:
                photo = st.camera_input("Foto eticheta")
                if photo is not None:
                    ocr = extract_ocr_fields(photo, pending.get("drum_number"))
                    ocr_material = ocr.get("material_code")
                    ocr_qty = ocr.get("standard_qty")
                    st.caption("OCR rezultat (verifica manual):")
                    st.write({"material_code": ocr_material, "standard_qty": ocr_qty})

            submit = st.form_submit_button("Salveaza")

        if submit:
            drum_number = pending.get("drum_number")
            if not drum_number:
                st.error("Nu pot extrage Drum Number din QR.")
                return

            # Use OCR fallback if inputs empty
            if not material_input and ocr_material:
                material_input = ocr_material
            if not std_qty and ocr_qty:
                std_qty = ocr_qty

            if not material_input:
                st.error("Material lipsa. Scaneaza materialul sau foloseste OCR.")
                return

            if material_input != selected:
                st.error(
                    f"Material gresit pe eticheta. Nu se poate inregistra pe paletul cu \"{selected}\"."
                )
                return

            # Duplicate checks
            if not active_drums.empty and drum_number in active_drums["drum_number"].tolist():
                st.error("Tambur dublat pe acest palet. Va rugam verificati.")
                return

            existing = find_drum(ws_drums, drum_number)
            if not existing.empty:
                prior = existing.iloc[0]
                pallet_id = prior.get("pallet_id", "")
                pallet_date = get_pallet_date(ws_pallets, pallet_id)
                if pallet_date:
                    msg = f"Tamburul a existat si pe Palletul {pallet_id or '(necunoscut)'} din data de {pallet_date}."
                else:
                    msg = f"Tamburul a existat si pe Palletul {pallet_id or '(necunoscut)'} in trecut."
                st.error(msg)
                return

            # Save
            add_drum(
                ws_drums,
                {
                    "timestamp": now_ts(),
                    "material_code": selected,
                    "drum_number": drum_number,
                    "drum_type": pending.get("drum_type"),
                    "standard_qty": std_qty,
                    "pallet_id": "",
                    "status": "ACTIVE",
                    "device_id": get_secret("DEVICE_ID", ""),
                    "operator": get_operator_name(),
                },
            )
            st.session_state.pending_scan = None
            st.success("Scan salvat.")
            st.rerun()

    # Undo last scan
    if st.button("Undo last scan", key="undo_scan"):
        active_drums = get_active_drums(ws_drums, selected)
        if active_drums.empty:
            st.info("Nu exista scanari active.")
        else:
            if "__doc_id" in active_drums.columns:
                last_doc = active_drums.sort_values("timestamp").iloc[-1]["__doc_id"]
                delete_row(ws_drums, last_doc)
            else:
                last_row = int(active_drums["__row"].max())
                delete_row(ws_drums, last_row)
            st.success("Ultimul tambur a fost sters.")
            st.rerun()

    st.markdown("---")

    # Pallet generation (with confirmation)
    if "confirm_generate" not in st.session_state:
        st.session_state.confirm_generate = False
    if "confirm_incomplete" not in st.session_state:
        st.session_state.confirm_incomplete = False

    if count >= max_qty and max_qty > 0:
        if st.button("Genereaza palet", key="generate_pallet"):
            st.session_state.confirm_generate = True

        if st.session_state.confirm_generate:
            st.warning("Aveti pe palet Max Qty / Pallet tamburi?")
            col_yes, col_no = st.columns(2)
            if col_yes.button("Da", key="confirm_gen_yes"):
                settings = get_settings(ws_settings)
                counter = int(settings.get("global_pallet_counter", "0"))
                pallet_id = f"{prefix}{counter}"

                active_drums = get_active_drums(ws_drums, selected)
                for _, row in active_drums.iterrows():
                    row_id = row["__doc_id"] if "__doc_id" in row else int(row["__row"])
                    update_row(ws_drums, row_id, {"pallet_id": pallet_id, "status": "COMPLETED"})

                description = mat.get("description", "") or ""
                email_subject = build_email_subject(selected, pallet_id)
                email_body = build_email_body(selected, description, pallet_id, active_drums)

                add_pallet(
                    ws_pallets,
                    pallet_id,
                    {
                        "pallet_id": pallet_id,
                        "material_code": selected,
                        "description": description,
                        "created_at": now_ts(),
                        "count": len(active_drums),
                        "complete_type": "FULL",
                        "email_subject": email_subject,
                        "email_body": email_body,
                    },
                )

                set_setting(ws_settings, "global_pallet_counter", str(counter + 1))
                st.session_state.confirm_generate = False
                st.success("Palet generat cu succes.")
                st.session_state.selected_material = None
                st.rerun()
            if col_no.button("Nu", key="confirm_gen_no"):
                st.session_state.confirm_generate = False
                st.info("Continuati scanarea sau folositi Palet incomplet.")

    if allow_incomplete and count > 0:
        if st.button("Palet incomplet", key="incomplete_pallet"):
            st.session_state.confirm_incomplete = True

        if st.session_state.confirm_incomplete:
            st.warning("Confirmati finalizare palet incomplet?")
            col_yes, col_no = st.columns(2)
            if col_yes.button("Da", key="confirm_inc_yes"):
                settings = get_settings(ws_settings)
                counter = int(settings.get("global_pallet_counter", "0"))
                pallet_id = f"{prefix}{counter}"

                active_drums = get_active_drums(ws_drums, selected)
                for _, row in active_drums.iterrows():
                    row_id = row["__doc_id"] if "__doc_id" in row else int(row["__row"])
                    update_row(ws_drums, row_id, {"pallet_id": pallet_id, "status": "COMPLETED"})

                description = mat.get("description", "") or ""
                email_subject = build_email_subject(selected, pallet_id)
                email_body = build_email_body(selected, description, pallet_id, active_drums)

                add_pallet(
                    ws_pallets,
                    pallet_id,
                    {
                        "pallet_id": pallet_id,
                        "material_code": selected,
                        "description": description,
                        "created_at": now_ts(),
                        "count": len(active_drums),
                        "complete_type": "INCOMPLETE",
                        "email_subject": email_subject,
                        "email_body": email_body,
                    },
                )

                set_setting(ws_settings, "global_pallet_counter", str(counter + 1))
                st.session_state.confirm_incomplete = False
                st.success("Palet incomplet generat.")
                st.session_state.selected_material = None
                st.rerun()
            if col_no.button("Nu", key="confirm_inc_no"):
                st.session_state.confirm_incomplete = False


# -------------------- Admin Screen --------------------

def admin_screen(spreadsheet):
    ws_materials = ensure_worksheet(spreadsheet, "materials", SHEET_TEMPLATES["materials"])
    ws_settings = ensure_worksheet(spreadsheet, "settings", SHEET_TEMPLATES["settings"])
    ws_drums = ensure_worksheet(spreadsheet, "drums", SHEET_TEMPLATES["drums"])
    ws_pallets = ensure_worksheet(spreadsheet, "pallets", SHEET_TEMPLATES["pallets"])

    st.markdown(f"## {APP_TITLE} - Admin")

    # Settings
    settings = get_settings(ws_settings)
    current_counter = settings.get("global_pallet_counter", "0")
    with st.form("settings_form"):
        new_counter = st.text_input("Global pallet counter", value=current_counter)
        save_settings = st.form_submit_button("Salveaza setari")
    if save_settings:
        set_setting(ws_settings, "global_pallet_counter", new_counter)
        st.success("Setari salvate.")

    st.markdown("---")

    # Materials management
    st.markdown("### Materiale")
    materials_df = get_materials(ws_materials)
    if not materials_df.empty:
        st.dataframe(materials_df.drop(columns=["__row"], errors="ignore"), use_container_width=True)

    with st.form("material_form"):
        material_code = st.text_input("Material code")
        description = st.text_input("Description")
        max_qty = st.number_input("Max qty / pallet", min_value=1, step=1)
        prefix = st.text_input("Prefix (optional)")
        allow_incomplete = st.checkbox("Finalize early (Palet incomplet)")
        active = st.checkbox("Active", value=True)
        save_material = st.form_submit_button("Adauga / Update")

    if save_material:
        df = get_materials(ws_materials)
        existing = df[df["material_code"] == material_code] if not df.empty else pd.DataFrame()
        if isinstance(ws_materials, FirestoreCollection):
            row_data = {
                "material_code": material_code,
                "description": description,
                "max_qty": int(max_qty),
                "prefix": prefix,
                "allow_incomplete": bool(allow_incomplete),
                "active": bool(active),
            }
            ws_materials.set_doc(material_code, row_data)
            st.success("Material salvat.")
        else:
            row_data = {
                "material_code": material_code,
                "description": description,
                "max_qty": str(int(max_qty)),
                "prefix": prefix,
                "allow_incomplete": "TRUE" if allow_incomplete else "FALSE",
                "active": "TRUE" if active else "FALSE",
            }
            if existing.empty:
                ws_materials.append_row([row_data[h] for h in SHEET_TEMPLATES["materials"]])
                st.success("Material adaugat.")
            else:
                row_idx = int(existing.iloc[0]["__row"])
                update_row(ws_materials, row_idx, row_data)
                st.success("Material actualizat.")

    st.markdown("---")

    # History / Search
    st.markdown("### History & Search")
    pallets_df = load_sheet(ws_pallets)
    drums_df = load_sheet(ws_drums)

    # Date filters
    date_filter = st.selectbox("Filtru data", ["Toate", "Astazi", "Luna curenta", "An curent", "Interval"])
    start_date = None
    end_date = None
    if date_filter == "Interval":
        cols = st.columns(2)
        start_date = cols[0].date_input("De la")
        end_date = cols[1].date_input("Pana la")

    def apply_date_filter(df: pd.DataFrame, col: str):
        if df.empty or col not in df.columns:
            return df
        df = df.copy()
        df[col] = pd.to_datetime(df[col], errors="coerce")
        if date_filter == "Astazi":
            return df[df[col].dt.date == datetime.utcnow().date()]
        if date_filter == "Luna curenta":
            now = datetime.utcnow()
            return df[(df[col].dt.year == now.year) & (df[col].dt.month == now.month)]
        if date_filter == "An curent":
            now = datetime.utcnow()
            return df[df[col].dt.year == now.year]
        if date_filter == "Interval" and start_date and end_date:
            return df[(df[col].dt.date >= start_date) & (df[col].dt.date <= end_date)]
        return df

    pallets_view = apply_date_filter(pallets_df, "created_at") if not pallets_df.empty else pallets_df
    drums_view = apply_date_filter(drums_df, "timestamp") if not drums_df.empty else drums_df

    if not pallets_view.empty:
        st.dataframe(pallets_view.drop(columns=["__row"], errors="ignore"), use_container_width=True)

    st.markdown("### Toate scanarile")
    if not drums_view.empty:
        st.dataframe(drums_view.drop(columns=["__row"], errors="ignore"), use_container_width=True)

    search_drum = st.text_input("Cauta drum number")
    if search_drum:
        result = drums_df[drums_df["drum_number"] == search_drum] if not drums_df.empty else pd.DataFrame()
        if result.empty:
            st.info("Nu exista acest drum number.")
        else:
            st.dataframe(result.drop(columns=["__row"], errors="ignore"), use_container_width=True)


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    inject_css()

    st.markdown(f"# {APP_TITLE}")

    fs_client = get_fs_client()
    apps_script_url = get_secret("GOOGLE_APPS_SCRIPT_URL")
    client = None if apps_script_url else get_gs_client()
    sheet_id = get_secret("GOOGLE_SHEET_ID")
    sheet_title = get_secret("GOOGLE_SHEET_TITLE", "PryPalScanner_Data")

    if fs_client:
        spreadsheet = FirestoreDatabase(fs_client)
        created = False
    elif apps_script_url:
        spreadsheet = AppsScriptSpreadsheet(apps_script_url, sheet_id)
        created = False
    elif client:
        spreadsheet, created = get_or_create_spreadsheet(client, sheet_id, sheet_title)
    else:
        st.error(
            "Nu exista backend configurat. Seteaza FIREBASE_SERVICE_ACCOUNT_JSON "
            "sau GOOGLE_APPS_SCRIPT_URL sau GOOGLE_SERVICE_ACCOUNT_JSON / FILE."
        )
        st.stop()

    if created:
        st.warning(
            f"Am creat un nou Google Sheet: {spreadsheet.title}. "
            f"ID: {spreadsheet.id}. Actualizeaza GOOGLE_SHEET_ID cu acest ID."
        )

    if "auth_role" not in st.session_state:
        st.session_state.auth_role = None
    if "username" not in st.session_state:
        st.session_state.username = ""

    if not st.session_state.auth_role:
        st.markdown("## Conectare")
        password = st.text_input("Parola", type="password")
        if st.button("Login"):
            operator_pw = get_secret("OPERATOR_PASSWORD", "PryPass2026")
            admin_pw = get_secret("ADMIN_PASSWORD", "PryAdmin2026")
            if password == admin_pw:
                st.session_state.auth_role = "admin"
                st.session_state.username = "admin"
                st.rerun()
            elif password == operator_pw:
                st.session_state.auth_role = "operator"
                st.session_state.username = "operator"
                st.rerun()
            else:
                st.error("Parola gresita.")
        return

    if st.session_state.auth_role == "admin":
        if st.button("Logout"):
            st.session_state.auth_role = None
            st.session_state.username = ""
            st.rerun()
        admin_screen(spreadsheet)
        return

    if st.session_state.auth_role == "operator":
        if st.button("Logout"):
            st.session_state.auth_role = None
            st.session_state.username = ""
            st.rerun()
        operator_screen(spreadsheet)
        return


if __name__ == "__main__":
    main()
