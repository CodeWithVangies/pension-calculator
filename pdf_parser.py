"""
pdf_parser.py
Διαβάζει την Κατάσταση Ασφαλιστικού Λογαριασμού των Κυπριακών
Υπηρεσιών Κοινωνικών Ασφαλίσεων και επιστρέφει DataFrame με:
  Έτος | Μονάδες | Πηγή
"""

import re
import io
import pandas as pd

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False


# ── Fallback demo data (Ευάγγελος Ευαγγέλου) ────────────────────────────────
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
    df = pd.DataFrame(DEMO_DATA, columns=["Έτος", "Μονάδες"])
    df["Πηγή"] = "demo"
    return df


def parse_ka_pdf(uploaded_file) -> tuple[pd.DataFrame | None, str]:
    """
    Παράμετρος : uploaded_file  (Streamlit UploadedFile ή file-like object)
    Επιστρέφει : (DataFrame, μήνυμα)
    """
    if not HAS_PDFPLUMBER:
        df = _demo_df()
        return df, (f"Το pdfplumber δεν είναι εγκατεστημένο — "
                    f"φορτώθηκαν demo δεδομένα ({len(df)} έτη).")

    raw = uploaded_file.read() if hasattr(uploaded_file, "read") else uploaded_file
    rows = []

    try:
        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                # Ψάχνουμε γραμμές της μορφής:  1991   1,00   1.976
                # ή                              2008   2,80   22.434
                pattern = re.compile(
                    r'\b(19[89]\d|20[012]\d)\b'   # έτος 1980-2029
                    r'[\s\t]+'
                    r'(\d+[,\.]\d+)'               # μονάδες  π.χ. 2,80 ή 2.80
                )
                for m in pattern.finditer(text):
                    yr  = int(m.group(1))
                    raw_u = m.group(2).replace(",", ".")
                    try:
                        units = float(raw_u)
                        if 0 < units < 15:          # εύλογο εύρος μονάδων
                            rows.append((yr, units))
                    except ValueError:
                        pass

    except Exception as exc:
        # Αν αποτύχει η ανάγνωση, γυρνάμε demo data
        df = _demo_df()
        return df, f"Αδυναμία ανάγνωσης PDF ({exc}) — φορτώθηκαν demo δεδομένα."

    if not rows:
        df = _demo_df()
        return df, "Δεν βρέθηκαν δεδομένα στο PDF — φορτώθηκαν demo δεδομένα."

    # Κρατάμε μοναδικά έτη (τελευταία εμφάνιση αν υπάρχουν διπλά)
    seen = {}
    for yr, u in rows:
        seen[yr] = u
    df = pd.DataFrame(sorted(seen.items()), columns=["Έτος", "Μονάδες"])
    df["Πηγή"] = "pdf"
    return df, f"Επιτυχής ανάγνωση PDF — βρέθηκαν {len(df)} έτη ({df['Έτος'].min()}–{df['Έτος'].max()})."
