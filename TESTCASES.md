# PryPalScanner - Test Cases (Manual QA)

Aceste teste sunt pentru varianta curenta cu Firestore ca backend.

## Preconditii
- Aplicatia ruleaza in browser (Streamlit).
- Date test in Firestore:
  - `materials/60115949`:
    - `active: true`
    - `allow_incomplete: true`
    - `description: "DWP1500_LV"`
    - `max_qty: 20`
    - `prefix: "SL-5959"`
- Admin password: `PryAdmin2026`
- Operator password: `PryPass2026`
- (Optional pentru export email) SMTP configurat:
  - `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`
  - In Admin: `Reports email` setat.

## Date test (exemple)
- QR valid: `DWP1500_LV 15518289`
- Material code corect: `60115949`
- Standard qty: `20`
- Drum numar duplicat: `15518289`
- Material code gresit: `99999999`

## Teste autentificare
TC-LOGIN-01: Operator login
- Steps: Introdu parola `PryPass2026` -> Login
- Expected: Acces la ecranul principal cu Materiale.

TC-LOGIN-02: Admin login
- Steps: Introdu parola `PryAdmin2026` -> Login
- Expected: Acces la Admin screen.

TC-LOGIN-03: Parola gresita
- Steps: Introdu parola invalida -> Login
- Expected: Mesaj eroare.

## Teste UI si limba
TC-UI-01: Schimbare limba RO/EN
- Steps: In footer, schimba Limba din RO in EN si invers
- Expected: Texte cheie se schimba (ex: Admin login/Password, Scanned drums, Cancel Last Drum).

TC-UI-02: Status butoane materiale
- Steps: Cu 0 scanari -> vezi status Empty/verde; cu 1..max-1 -> galben; cu max -> full.
- Expected: Culorile si label-urile se schimba corect.

## Teste scanare
TC-SCAN-01: Scan valid
- Steps: Selecteaza Material 60115949 -> scaneaza `DWP1500_LV 15518289` -> completeaza Material code = 60115949, Standard qty = 20 -> Salveaza
- Expected: Drum apare in lista curenta; count creste.

TC-SCAN-02: Material gresit
- Steps: Scaneaza QR valid -> Material code = 99999999 -> Salveaza
- Expected: Eroare “Material gresit...” si NU salveaza.

TC-SCAN-03: Drum duplicat pe acelasi palet
- Steps: Scaneaza de 2 ori acelasi drum number in paletul curent
- Expected: Eroare “Tambur dublat...” si NU salveaza a doua oara.

TC-SCAN-04: Drum duplicat istoric
- Steps: Drum deja in DB pe un alt palet -> scaneaza din nou
- Expected: Eroare “Tamburul a existat si pe Palletul ... din data de ...”.

TC-SCAN-05: Lipsa material code
- Steps: Scaneaza QR valid -> lasi Material code gol -> Salveaza
- Expected: Eroare “Material lipsa...”.

TC-SCAN-06: Undo last drum
- Steps: Adauga 2 drumuri -> apasa “Anuleaza Ultimul Tambur”
- Expected: Ultimul drum se sterge din lista.

TC-SCAN-07: OCR optional
- Steps: Bifeaza “Foloseste camera” si foloseste OCR (daca e disponibil)
- Expected: Material code / Standard qty sunt populate (daca OCR reuseste).

## Teste palet
TC-PALLET-01: Genereaza palet activ doar la Max
- Steps: Cu count < max, verifica buton “Genereaza palet”
- Expected: Buton disabled.

TC-PALLET-02: Genereaza palet la Max
- Steps: Ajungi la max_qty -> apasa “Genereaza palet” -> confirmare DA
- Expected: Palet creat cu id `prefix + counter`, drumurile trec in COMPLETED, lista curenta se goleste.

TC-PALLET-03: Confirmare NU la generare
- Steps: Apasa “Genereaza palet” -> confirmare NU
- Expected: Nu se genereaza palet, ramane in lista.

TC-PALLET-04: Palet incomplet (allow_incomplete = true)
- Steps: count > 0 si count < max -> apasa “Palet incomplet” -> confirmare DA
- Expected: Palet creat cu complete_type=INCOMPLETE si lista curenta se goleste.

TC-PALLET-05: Palet incomplet disabled la 0 sau full
- Steps: count=0 sau count=max
- Expected: Buton Palet incomplet disabled.

## Teste Admin
TC-ADMIN-01: Update global counter
- Steps: Admin -> Global pallet counter -> salveaza
- Expected: Noul counter se foloseste la urmatorul palet.

TC-ADMIN-02: Adauga / update material
- Steps: Admin -> Materiale -> completeaza campuri -> Adauga/Update
- Expected: Document `materials/<material_code>` se actualizeaza.

## History & Reports
TC-HIST-01: Filtru dupa data
- Steps: Selecteaza Astazi/Luna/An/Interval
- Expected: Lista se filtreaza corect.

TC-HIST-02: Filtru Material Code
- Steps: Introdu Material Code
- Expected: Pallets + Drums se filtreaza.

TC-HIST-03: Cautare drum number
- Steps: Cauta un drum existent
- Expected: Rezultat returnat.

TC-REPORT-01: Export CSV prin email
- Steps: Seteaza Reports email + SMTP -> apasa Export CSV
- Expected: Email cu attachment ZIP (pallets.csv, drums.csv).

TC-REPORT-02: Export Excel prin email
- Steps: Seteaza Reports email + SMTP -> apasa Export Excel
- Expected: Email cu attachment XLSX (pallets, drums).

TC-REPORT-03: Lipsa SMTP
- Steps: Fara SMTP -> apasa Export
- Expected: Eroare “SMTP not configured...”.

TC-REPORT-04: Lipsa Reports email
- Steps: Reports email gol -> apasa Export
- Expected: Warning “Seteaza Reports email in Admin.”.

