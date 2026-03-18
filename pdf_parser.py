"""
pdf_parser.py  —  v2
Διαβάζει την Κατάσταση Ασφαλιστικού Λογαριασμού ΚΑ Κύπρου.
Το PDF έχει 3 στήλες δεδομένων:
  Α) Πριν το 1981 : Έτος | Ασφ.Μονάδες | Ετήσιες Εισφορές
  Β) 1981-2007    : Έτος | Ασφ.Μονάδες | Ασφαλιστέες Αποδοχές (£)
  Γ) 2008+        : Έτος | Ασφ.Μονάδες | Ασφαλιστέες Αποδοχές (€)
"""

import io
import re
import pandas as pd

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

# ── Demo data (Ευάγγελος Ευαγγέλου) ────────────────────────────────────────
DEMO_DATA = [
    (1991,1.00),(1992,1.00),(1993,1.00),(1994,1.00),(1995,1.00),
    (1996,1.00),(1997,1.00),(1998,1.00),(1999,1.00),(2000,1.00),
    (2001,1.18),(2002,0.95),(2003,1.73),(2004,2.32),(2005,2.47),
    (2006,2.62),(2007,3.32),(2008,2.80),(2009,2.50),(2010,2.43),
    (2011,2.47),(2012,2.95),(2013,3.04),(2014,3.18),(2015,3.15),
    (2016,3.10),(2017,3.22),(2018,3.44),(2019,3.62),(2020,3.13),
    (2021,3.64),(2022,3.69),(2023,3.82),(2024,3.78),(2025,3.87),
]

def _demo_df():
    df = pd.DataFrame(DEMO_DATA, columns=["Έτος","Μονάδες"])
    df["Πρόβλεψη"] = False
    return df

def _parse_number(s: str) -> float | None:
    """Μετατρέπει '1,23' ή '1.23' ή '1.234' (χιλιάδες) σε float."""
    s = s.strip()
    if not s or s == "—":
        return None
    # Αφαίρεση χιλιαδικών τελειών/κομμάτων
    # Αν έχει κόμμα → ευρωπαϊκή μορφή: 1.234,56 ή 1,23
    if "," in s:
        # αφαίρεσε τελείες (χιλιάδες) και κόμμα → τελεία
        s = s.replace(".", "").replace(",", ".")
    else:
        # μόνο τελεία: μπορεί να είναι δεκαδικό ή χιλιάδες
        # αν μετά την τελεία > 2 ψηφία → χιλιάδες, αφαίρεσε
        parts = s.split(".")
        if len(parts) == 2 and len(parts[1]) >= 3:
            s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None

def _extract_year_units(text: str) -> dict[int, float]:
    """
    Εξάγει ζεύγη (έτος, μονάδες) από το κείμενο του PDF.
    Η λογική: βρίσκει έτη 19xx/20xx και παίρνει τον αμέσως
    επόμενο αριθμό ως μονάδες (0.00 – 9.99).
    """
    result = {}

    # Κανονικοποίηση: αντικατάσταση κόμματος δεκαδικών με τελεία
    # ώστε "1,23" → "1.23" για ευκολότερο regex
    text_norm = re.sub(r'(\d),(\d)', r'\1.\2', text)

    # Pattern: έτος ακολουθούμενο από μονάδες (0.00 – 9.99)
    # Τα έτη είναι 19xx ή 20xx
    # Οι μονάδες είναι συνήθως μεταξύ 0.00 και 9.99
    pattern = re.compile(
        r'\b(19[6-9]\d|20[0-3]\d)\b'   # έτος
        r'[\s\t]+'
        r'(\d{1,2}[.,]\d{2})'           # μονάδες π.χ. 1.23 ή 0.20
    )

    for m in pattern.finditer(text_norm):
        yr = int(m.group(1))
        raw = m.group(2).replace(",", ".")
        try:
            units = float(raw)
            if 0.0 <= units <= 15.0:  # εύλογο εύρος
                if yr not in result:   # κράτα πρώτη εμφάνιση
                    result[yr] = units
        except ValueError:
            pass

    return result

def parse_ka_pdf(uploaded_file) -> tuple:
    """
    Κύρια συνάρτηση parsing.
    Επιστρέφει (DataFrame, μήνυμα).
    DataFrame έχει στήλες: Έτος, Μονάδες, Πρόβλεψη
    """
    if not HAS_PDFPLUMBER:
        df = _demo_df()
        return df, "pdfplumber μη εγκατεστημένο — φορτώθηκαν demo δεδομένα."

    raw = uploaded_file.read() if hasattr(uploaded_file, "read") else uploaded_file

    all_years = {}

    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                # ── Μέθοδος 1: extract_text ──────────────────────────────
                text = page.extract_text() or ""
                found = _extract_year_units(text)
                for yr, u in found.items():
                    if yr not in all_years:
                        all_years[yr] = u

                # ── Μέθοδος 2: extract_tables ────────────────────────────
                tables = page.extract_tables() or []
                for table in tables:
                    for row in table:
                        if not row:
                            continue
                        # Ψάχνουμε κελιά που μοιάζουν με έτος
                        for i, cell in enumerate(row):
                            if cell is None:
                                continue
                            cell_str = str(cell).strip()
                            yr_m = re.match(r'^(19[6-9]\d|20[0-3]\d)$', cell_str)
                            if yr_m and i + 1 < len(row):
                                yr = int(yr_m.group(1))
                                next_cell = str(row[i+1] or "").strip()
                                u = _parse_number(next_cell)
                                if u is not None and 0.0 <= u <= 15.0:
                                    if yr not in all_years:
                                        all_years[yr] = u

    except Exception as exc:
        df = _demo_df()
        return df, f"Σφάλμα ανάγνωσης PDF ({exc}) — φορτώθηκαν demo δεδομένα."

    if not all_years:
        df = _demo_df()
        return df, "Δεν βρέθηκαν δεδομένα — φορτώθηκαν demo δεδομένα."

    # ── Συμπλήρωση ΟΛΩ Ν των ετών μεταξύ min και max ────────────────────────
    # Τα έτη με 0 μονάδες (π.χ. 1998-2004) πρέπει να υπάρχουν με 0.0
    yr_min = min(all_years.keys())
    yr_max = max(all_years.keys())

    complete = {}
    for y in range(yr_min, yr_max + 1):
        complete[y] = all_years.get(y, 0.0)  # 0.0 για χρόνια χωρίς εισφορές

    df = pd.DataFrame(
        sorted(complete.items()),
        columns=["Έτος", "Μονάδες"]
    )
    df["Πρόβλεψη"] = False

    yr_start = df["Έτος"].min()
    yr_end   = df["Έτος"].max()
    n        = len(df)

    return df, (f"Επιτυχής ανάγνωση PDF — βρέθηκαν {n} έτη "
                f"({yr_start}–{yr_end}).")
