"""
Υπολογιστής Σύνταξης Κύπρου
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Η ηλικία του ασφαλισμένου διαβάζεται ΑΠΟΚΛΕΙΣΤΙΚΑ από το PDF.
✅ Ηλικία >= 63  →  Υπολογισμός ΤΡΕΧΟΥΣΑΣ σύνταξης
✅ Ηλικία <  63  →  ΠΡΟΒΛΕΨΗ μελλοντικής σύνταξης (4 σενάρια)

ΕΓΚΑΤΑΣΤΑΣΗ:   pip install streamlit pdfplumber pandas plotly
ΕΚΤΕΛΕΣΗ:      streamlit run pension_forecast.py
"""

import streamlit as st
import pdfplumber
import pandas as pd
import plotly.graph_objects as go
import re
from dataclasses import dataclass, field

# ─── Σταθερές 2025 ────────────────────────────────────────────────────────────
WEEKLY_UNIT_VALUE = 201.57
MONTHLY_FACTOR    = 4
SUPP_RATE         = 0.015
ANNUAL_BASE_LIMIT = 10_482
BASE_LIMIT_GROWTH = 0.02
CURRENT_YEAR      = 2025

BASE_RATE_MAP = {0: 0.60, 1: 0.80, 2: 0.90, 3: 1.00}
MIN_PENSIONS  = {0: 411.20, 1: 548.27, 2: 616.80, 3: 685.34}
EARLY_REDUCT  = {65: 0.00, 64: 0.06, 63: 0.12}

SCENARIOS = [
    {"key": "stable", "label": "📌 Σταθερή (€201,57)", "rate": 0.000, "color": "#888780"},
    {"key": "cons",   "label": "📉 Συντηρητικό +1,5%", "rate": 0.015, "color": "#BA7517"},
    {"key": "med",    "label": "📊 Μεσαίο +2,5%",      "rate": 0.025, "color": "#185FA5"},
    {"key": "opt",    "label": "📈 Αισιόδοξο +3,5%",   "rate": 0.035, "color": "#1D9E75"},
]


# ─── Dataclasses ──────────────────────────────────────────────────────────────
@dataclass
class ExtractedData:
    basic_pre_1981:   float = 0.0
    basic_post_1980:  float = 0.0
    supp_units:       float = 0.0
    ref_years_so_far: float = 0.0
    last_earnings:    float = 0.0
    birth_year:       int   = 0      # ← Διαβάζεται από το PDF
    parse_notes:      list  = field(default_factory=list)

    @property
    def total_basic(self) -> float:
        return self.basic_pre_1981 + self.basic_post_1980

    @property
    def current_age(self) -> int:
        """Ηλικία υπολογισμένη από το έτος γέννησης του PDF."""
        if self.birth_year > 0:
            return CURRENT_YEAR - self.birth_year
        return 0


@dataclass
class PensionResult:
    total_basic:      float = 0.0
    total_supp:       float = 0.0
    ref_years:        float = 0.0
    avg_basic:        float = 0.0
    unit_value:       float = 0.0
    basic_pension:    float = 0.0
    supp_pension:     float = 0.0
    total_before_red: float = 0.0
    reduction_pct:    float = 0.0
    reduction_amt:    float = 0.0
    final_pension:    float = 0.0
    scenario_label:   str   = ""
    scenario_color:   str   = ""
    future_basic:     float = 0.0
    future_supp:      float = 0.0
    chart_labels:     list  = field(default_factory=list)
    chart_basic:      list  = field(default_factory=list)
    chart_supp:       list  = field(default_factory=list)


# ─── PDF Parsing ──────────────────────────────────────────────────────────────
def parse_pdf(uploaded_file) -> ExtractedData:
    """
    Εξάγει ΟΛΑ τα δεδομένα από το PDF συμπεριλαμβανομένου
    του έτους γέννησης από το οποίο υπολογίζεται η ηλικία.
    """
    data  = ExtractedData()
    notes = []

    try:
        with pdfplumber.open(uploaded_file) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += (page.extract_text() or "") + "\n"

        # ── 1. ΈΤΟΣ ΓΕΝΝΗΣΗΣ (κρίσιμο για τη λειτουργία) ────────────────────
        birth_patterns = [
            # "γεννήθηκε την 1η Ιανουαρίου 1961"
            r"γεννήθηκε[^0-9]*\d{1,2}[η\s]+(?:Ιανουαρίου|Φεβρουαρίου|Μαρτίου|Απριλίου|Μαΐου|Ιουνίου|Ιουλίου|Αυγούστου|Σεπτεμβρίου|Οκτωβρίου|Νοεμβρίου|Δεκεμβρίου)[^0-9]*(\d{4})",
            # "γεννήθηκε 1/1/1961" ή "γεννήθηκε 1.1.1961"
            r"γεννήθηκε[^0-9]*\d{1,2}[/\.]\d{1,2}[/\.](\d{4})",
            # "γεννήθηκε ... 1961"
            r"γεννήθηκε[^0-9]*(\d{4})",
            # Απλά αναζήτηση για 4ψήφιο έτος που ξεκινά με 19
            r"\b(19[4-9]\d)\b",
        ]
        for pat in birth_patterns:
            m = re.search(pat, full_text, re.IGNORECASE)
            if m:
                yr = int(m.group(1))
                if 1940 <= yr <= 2002:
                    data.birth_year = yr
                    age = CURRENT_YEAR - yr
                    notes.append(f"✅ Έτος γέννησης: **{yr}** → Ηλικία: **{age} ετών**")
                    break

        if data.birth_year == 0:
            notes.append("⚠️ Έτος γέννησης δεν βρέθηκε στο PDF — παρακαλώ εισάγετε χειροκίνητα")

        # ── 2. Σύνολα μονάδων ─────────────────────────────────────────────────
        for pat in [
            r"[Μμ]ον[αά]δες\s+([\d,\.]+)\s+([\d,\.]+)",
            r"[Ββ]ασικ[όο]\s+([\d,\.]+).*?[Σσ]υμπλ\w*\s+([\d,\.]+)",
            r"[Σσ]ύνολο.*?([\d,\.]+)\s+([\d,\.]+)\s*$",
        ]:
            m = re.search(pat, full_text, re.MULTILINE)
            if m:
                v1 = float(m.group(1).replace(",", "."))
                v2 = float(m.group(2).replace(",", "."))
                if 1 < v1 < 60 and 1 < v2 < 250:
                    data.basic_post_1980 = v1
                    data.supp_units      = v2
                    notes.append(f"✅ Βασικές μονάδες 1980+: **{v1}**")
                    notes.append(f"✅ Συμπλ. μονάδες: **{v2}**")
                    break

        # ── 3. Μονάδες πριν 1981 ──────────────────────────────────────────────
        for pat in [
            r"[Σσ]ύνολο\s+([\d,\.]+)\s*εβδομάδες",
            r"1980.*?[Σσ]ύνολο\s+([\d,\.]+)",
        ]:
            m = re.search(pat, full_text, re.IGNORECASE | re.DOTALL)
            if m:
                val = float(m.group(1).replace(",", "."))
                data.basic_pre_1981 = round(val / 50, 2) if val > 10 else val
                notes.append(f"✅ Μονάδες πριν 1981: **{data.basic_pre_1981}**")
                break

        if data.basic_pre_1981 == 0:
            m = re.search(r"\b([3-6]\.[0-9]{2})\b", full_text)
            if m:
                v = float(m.group(1))
                if 2.0 < v < 8.0:
                    data.basic_pre_1981 = v
                    notes.append(f"⚠️ Μονάδες πριν 1981 (εκτίμηση): {v}")

        # ── 4. Τελευταίες αποδοχές ────────────────────────────────────────────
        recent = []
        for year in range(2024, 2018, -1):
            m = re.search(rf"{year}[^0-9]*([\d\s\.]+)", full_text)
            if m:
                raw = m.group(1).replace(" ", "").replace(".", "")
                try:
                    v = float(raw[:8])
                    if 5_000 < v < 200_000:
                        recent.append((year, v))
                except:
                    pass

        if recent:
            recent.sort(key=lambda x: x[0], reverse=True)
            data.last_earnings = recent[0][1]
            notes.append(f"✅ Τελευταίες αποδοχές ({recent[0][0]}): **€{data.last_earnings:,.0f}**")
        else:
            vals = [int(v) for v in re.findall(r"\b(\d{4,6})\b", full_text) if 10_000 < int(v) < 150_000]
            data.last_earnings = float(max(vals)) if vals else 30_000
            notes.append(f"⚠️ Αποδοχές (εκτίμηση): **€{data.last_earnings:,.0f}**")

        # ── 5. Χρόνια περιόδου αναφοράς ───────────────────────────────────────
        for pat in [r"(\d+)[,\.](\d+)\s*χρόν", r"(\d+)\s*χρόνια"]:
            m = re.search(pat, full_text, re.IGNORECASE)
            if m:
                if len(m.groups()) == 2:
                    data.ref_years_so_far = float(f"{m.group(1)}.{m.group(2)}")
                else:
                    data.ref_years_so_far = float(m.group(1))
                notes.append(f"✅ Χρόνια αναφοράς: **{data.ref_years_so_far}**")
                break

    except Exception as e:
        notes.append(f"❌ Σφάλμα ανάγνωσης PDF: {str(e)}")

    data.parse_notes = notes
    return data


# ─── Υπολογισμός Τρέχουσας Σύνταξης (>= 63) ──────────────────────────────────
def calc_current_pension(data: ExtractedData, retirement_age: int,
                         dependents: int) -> PensionResult:
    r = PensionResult()
    r.total_basic = data.total_basic
    r.total_supp  = data.supp_units
    r.unit_value  = WEEKLY_UNIT_VALUE

    if data.ref_years_so_far > 0:
        r.ref_years = data.ref_years_so_far
    else:
        # Περίοδος αναφοράς: από Οκτώβριο έτους (birth_year+15) έως 31/12 τελευταίου έτους
        # Π.χ. γέννηση 1961 → Οκτ.1976 έως 31/12/2023 = 47.25 χρόνια
        ref_start = data.birth_year + 15.75  # Οκτ. = +9/12 = +0.75
        ref_end   = float(CURRENT_YEAR - 1)    # 31/12 τελευταίου έτους λογαριασμού (2023)
        r.ref_years = round(ref_end - ref_start, 2)

    base_rate          = BASE_RATE_MAP[min(dependents, 3)]
    r.avg_basic        = r.total_basic / r.ref_years if r.ref_years > 0 else 0
    r.basic_pension    = r.avg_basic * WEEKLY_UNIT_VALUE * base_rate * MONTHLY_FACTOR
    r.supp_pension     = r.total_supp * WEEKLY_UNIT_VALUE * SUPP_RATE * MONTHLY_FACTOR
    r.total_before_red = r.basic_pension + r.supp_pension
    r.reduction_pct    = EARLY_REDUCT.get(retirement_age, 0.0)
    r.reduction_amt    = r.total_before_red * r.reduction_pct
    r.final_pension    = r.total_before_red - r.reduction_amt
    min_p = MIN_PENSIONS[min(dependents, 3)]
    if r.final_pension < min_p:
        r.final_pension = min_p
    return r


# ─── Υπολογισμός Πρόβλεψης (< 63) ───────────────────────────────────────────
def calc_forecast(data: ExtractedData, retirement_age: int, dependents: int,
                  salary_growth_pct: float, unit_growth_rate: float,
                  scenario_label: str, scenario_color: str) -> PensionResult:

    r = PensionResult(scenario_label=scenario_label, scenario_color=scenario_color)
    current_age = data.current_age
    years_left  = retirement_age - current_age

    if years_left <= 0:
        return r

    salary_growth = salary_growth_pct / 100.0
    base_rate     = BASE_RATE_MAP[min(dependents, 3)]

    if data.ref_years_so_far > 0:
        ref_so_far = data.ref_years_so_far
    else:
        # Περίοδος αναφοράς: από Οκτώβριο έτους (birth_year+15) έως σήμερα
        ref_start  = data.birth_year + 15.75
        ref_end    = float(CURRENT_YEAR - 1)    # 31/12 τελευταίου έτους λογαριασμού
        ref_so_far = round(ref_end - ref_start, 2)

    r.ref_years = ref_so_far + years_left

    cur_basic = data.total_basic
    cur_supp  = data.supp_units
    cur_earn  = data.last_earnings
    tot_basic = cur_basic
    tot_supp  = cur_supp

    labels = [f"Σήμερα ({current_age})"]
    b_arr  = [round(cur_basic, 2)]
    s_arr  = [round(cur_supp,  2)]

    for y in range(1, int(years_left) + 2):
        frac = min(1.0, years_left - (y - 1))
        if frac <= 0:
            break
        earnings          = cur_earn * ((1 + salary_growth) ** (y - 1)) * frac
        future_base_limit = ANNUAL_BASE_LIMIT * ((1 + BASE_LIMIT_GROWTH) ** y)
        units_yr          = earnings / future_base_limit
        tot_basic        += min(units_yr, 1.0) * frac
        tot_supp         += max(units_yr - 1.0, 0.0) * frac
        if y % 2 == 0 or frac < 1.0:
            labels.append(str(current_age + y))
            b_arr.append(round(tot_basic, 2))
            s_arr.append(round(tot_supp,  2))

    r.total_basic   = tot_basic
    r.total_supp    = tot_supp
    r.future_basic  = tot_basic - cur_basic
    r.future_supp   = tot_supp - cur_supp
    r.chart_labels  = labels
    r.chart_basic   = b_arr
    r.chart_supp    = s_arr
    r.avg_basic     = tot_basic / r.ref_years if r.ref_years > 0 else 0
    r.unit_value    = WEEKLY_UNIT_VALUE * ((1 + unit_growth_rate) ** years_left)
    r.basic_pension    = r.avg_basic * r.unit_value * base_rate * MONTHLY_FACTOR
    r.supp_pension     = tot_supp * r.unit_value * SUPP_RATE * MONTHLY_FACTOR
    r.total_before_red = r.basic_pension + r.supp_pension
    r.reduction_pct    = EARLY_REDUCT.get(retirement_age, 0.0)
    r.reduction_amt    = r.total_before_red * r.reduction_pct
    r.final_pension    = r.total_before_red - r.reduction_amt
    min_p = MIN_PENSIONS[min(dependents, 3)]
    if r.final_pension < min_p:
        r.final_pension = min_p
    return r


def eur(n: float) -> str:
    return f"€{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ─── Streamlit UI ─────────────────────────────────────────────────────────────
def main():
    st.set_page_config(page_title="Υπολογιστής Σύνταξης ΚΑΣ", page_icon="🏛️", layout="wide")

    st.markdown("""
    <style>
    .big-title{font-size:26px;font-weight:600;margin-bottom:4px;}
    .subtitle{font-size:13px;color:#666;margin-bottom:1.5rem;}
    .mode-badge{display:inline-block;padding:6px 16px;border-radius:20px;font-size:13px;font-weight:600;margin-bottom:1.5rem;}
    .mbox{border-radius:10px;padding:14px;text-align:center;margin-bottom:4px;}
    .mval{font-size:24px;font-weight:700;}
    .mlbl{font-size:11px;color:#888;margin-top:3px;}
    .blue-box{background:#E6F1FB;border:1px solid #B5D4F4;border-radius:8px;padding:12px 14px;font-size:13px;color:#0C447C;margin-bottom:1rem;line-height:1.7;}
    .orange-box{background:#FAEEDA;border:1px solid #FAC775;border-radius:8px;padding:12px 14px;font-size:13px;color:#633806;margin-top:1rem;line-height:1.7;}
    .parse-box{background:#F1EFE8;border:1px solid #D3D1C7;border-radius:8px;padding:12px 14px;font-size:13px;color:#444441;margin-bottom:1rem;line-height:1.9;}
    </style>
    """, unsafe_allow_html=True)

    # ── Sidebar ───────────────────────────────────────────────────────────────
    with st.sidebar:
        st.header("⚙️ Στοιχεία Ασφαλισμένου")

        # Το PDF ανεβαίνει ΠΡΩΤΟ — από αυτό διαβάζεται η ηλικία
        uploaded = st.file_uploader(
            "📄 Ανεβάστε τον Ασφαλιστικό Λογαριασμό (PDF)",
            type=["pdf"],
            help="Το έτος γέννησης και τα στοιχεία εξάγονται αυτόματα από το PDF"
        )

        st.markdown("---")

        dependents = st.selectbox(
            "Εξαρτώμενα πρόσωπα",
            options=[0, 1, 2, 3],
            format_func=lambda x: {0:"Κανένα (60%)", 1:"1 (80%)", 2:"2 (90%)", 3:"3+ (100%)"}[x]
        )

        retirement_age = st.selectbox(
            "Ηλικία συνταξιοδότησης",
            options=[65, 64, 63],
            format_func=lambda x: {65:"65 (κανονική)", 64:"64 (−6%)", 63:"63 (−12%)"}[x]
        )

        # Οι παραδοχές εμφανίζονται πάντα (θα χρησιμοποιηθούν μόνο αν < 63)
        st.markdown("---")
        st.subheader("📈 Παραδοχές (για πρόβλεψη)")
        salary_growth = st.slider(
            "Ετήσια αύξηση αποδοχών %",
            min_value=0.0, max_value=8.0, value=2.0, step=0.5,
            help="Χρησιμοποιείται μόνο αν η ηλικία < 63"
        )
        st.caption("📌 Σταθερή · 📉 +1,5% · 📊 +2,5% · 📈 +3,5%")

        calc_btn = st.button("🧮 Υπολογισμός", type="primary", use_container_width=True)

    # ── Αρχική οθόνη (χωρίς PDF) ─────────────────────────────────────────────
    if not uploaded:
        st.markdown('<div class="big-title">🏛️ Υπολογιστής Σύνταξης Κοινωνικών Ασφαλίσεων</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Κύπρος · Νόμοι 2010–2024 · Μέθοδος Μ. Χρίστου</div>', unsafe_allow_html=True)
        st.markdown("""
        <div class="blue-box">
        <strong>Πώς λειτουργεί:</strong><br>
        1. Ανεβάστε το PDF του ασφαλιστικού σας λογαριασμού<br>
        2. Το σύστημα διαβάζει αυτόματα το <strong>έτος γέννησης</strong> από το PDF<br>
        3. Αν η ηλικία είναι <strong>≥ 63</strong> → υπολογίζει την <strong>τρέχουσα σύνταξη</strong><br>
        4. Αν η ηλικία είναι <strong>&lt; 63</strong> → κάνει <strong>πρόβλεψη</strong> με 4 σενάρια
        </div>
        """, unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("""
            **📋 Τρέχουσα Σύνταξη (≥ 63 ετών)**
            - Υπολογισμός με τρέχουσα αξία μονάδας €201,57
            - Αναλυτικός υπολογισμός βασικής + συμπλ.
            - Σύγκριση σεναρίων 63/64/65 ετών
            """)
        with col2:
            st.markdown("""
            **🔮 Πρόβλεψη (< 63 ετών)**
            - Εκτίμηση μελλοντικών μονάδων
            - 4 σενάρια αξίας μονάδας
            - Γράφημα εξέλιξης έως συνταξιοδότηση
            """)
        return

    if not calc_btn:
        st.info("✅ PDF φορτώθηκε. Επιλέξτε τις παραμέτρους στα αριστερά και πατήστε **Υπολογισμός**.")
        return

    # ── Εξαγωγή δεδομένων από PDF ─────────────────────────────────────────────
    with st.spinner("Ανάγνωση PDF και εξαγωγή δεδομένων..."):
        extracted = parse_pdf(uploaded)

    # ── Εμφάνιση δεδομένων PDF ────────────────────────────────────────────────
    st.markdown("### 📋 Δεδομένα από το PDF")
    notes_html = "<br>".join(extracted.parse_notes) if extracted.parse_notes else "—"
    st.markdown(f'<div class="parse-box">{notes_html}</div>', unsafe_allow_html=True)

    # ── Αν δεν βρέθηκε έτος γέννησης → χειροκίνητη εισαγωγή ─────────────────
    if extracted.birth_year == 0:
        st.warning("⚠️ Το έτος γέννησης δεν βρέθηκε στο PDF. Εισάγετε το χειροκίνητα:")
        manual_year = st.number_input("Έτος γέννησης", min_value=1940, max_value=2002, value=1970, step=1)
        if st.button("Εφαρμογή"):
            extracted.birth_year = manual_year
        else:
            return

    # ── Αν δεν βρέθηκαν μονάδες → χειροκίνητη εισαγωγή ──────────────────────
    if extracted.total_basic == 0 and extracted.supp_units == 0:
        st.warning("⚠️ Δεν βρέθηκαν μονάδες στο PDF. Εισάγετε χειροκίνητα:")
        c1, c2, c3 = st.columns(3)
        extracted.basic_pre_1981  = c1.number_input("Μονάδες πριν 1981",    0.0, 10.0,  4.16,  0.01)
        extracted.basic_post_1980 = c2.number_input("Βασικές μονάδες 1980+",0.0, 60.0,  41.98, 0.01)
        extracted.supp_units      = c3.number_input("Συμπλ. μονάδες",       0.0, 300.0, 63.25, 0.01)
        c4, c5 = st.columns(2)
        extracted.last_earnings    = c4.number_input("Ετήσιες αποδοχές €",    0.0, 200000.0, 30000.0, 500.0)
        extracted.ref_years_so_far = c5.number_input("Χρόνια αναφοράς μέχρι σήμερα", 0.0, 50.0, 18.0, 0.25)

    # ══════════════════════════════════════════════════════════════════════════
    # ΚΕΝΤΡΙΚΗ ΔΙΑΚΛΑΔΩΣΗ βάσει ηλικίας ΑΠΟ ΤΟ PDF
    # ══════════════════════════════════════════════════════════════════════════
    current_age = extracted.current_age

    if current_age >= 63:
        # ────────────────────────────────────────────────────────────────────
        # ΛΕΙΤΟΥΡΓΙΑ Α: ΤΡΕΧΟΥΣΑ ΣΥΝΤΑΞΗ
        # ────────────────────────────────────────────────────────────────────
        st.markdown('<div class="big-title">🏛️ Υπολογισμός Τρέχουσας Σύνταξης</div>', unsafe_allow_html=True)
        st.markdown(f'<span class="mode-badge" style="background:#EAF3DE;color:#27500A;">📋 Ηλικία: {current_age} ετών — Τρέχουσα Σύνταξη</span>', unsafe_allow_html=True)

        r = calc_current_pension(extracted, retirement_age, dependents)

        c1, c2, c3, c4 = st.columns(4)
        for col, (val, lbl, color, bg) in zip([c1,c2,c3,c4], [
            (eur(r.final_pension),      "Μηνιαία σύνταξη",   "#185FA5","#E6F1FB"),
            (f"{r.total_basic:.2f}",    "Βασικές μονάδες",   "#27500A","#EAF3DE"),
            (f"{r.total_supp:.2f}",     "Συμπλ. μονάδες",    "#633806","#FAEEDA"),
            (f"{r.ref_years:.2f} χρ.",  "Περίοδος αναφοράς", "#888780","#F1EFE8"),
        ]):
            with col:
                st.markdown(f'<div class="mbox" style="background:{bg};border:1px solid {color}44;"><div class="mval" style="color:{color};">{val}</div><div class="mlbl">{lbl}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        cl, cr = st.columns(2)
        pct = int(BASE_RATE_MAP[min(dependents, 3)] * 100)

        with cl:
            st.markdown("#### Βασική σύνταξη")
            for lbl, val in [
                ("Μονάδες πριν 1/10/1980",             f"{extracted.basic_pre_1981:.2f}"),
                ("Βασικές μονάδες 1980+",              f"{extracted.basic_post_1980:.2f}"),
                ("**Σύνολο βασικών**",                 f"**{r.total_basic:.2f}**"),
                ("Περίοδος αναφοράς",                  f"{r.ref_years:.2f} χρόνια"),
                ("Μέσος όρος μονάδων",                 f"{r.avg_basic:.4f}"),
                (f"× €{WEEKLY_UNIT_VALUE} × {pct}% × 4",""),
                (f"**Μηνιαία βασική ({pct}%)**",       f"**{eur(r.basic_pension)}**"),
            ]:
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"<span style='font-size:13px;color:#555;'>{lbl}</span>", unsafe_allow_html=True)
                c2.markdown(f"<span style='font-size:13px;'>{val}</span>", unsafe_allow_html=True)

            st.markdown("#### Συμπληρωματική σύνταξη")
            for lbl, val in [
                ("Συμπλ. μονάδες",        f"{r.total_supp:.2f}"),
                ("× €201,57 × 1,5% × 4", "= €12,094/μονάδα"),
                ("**Μηνιαία συμπλ.**",     f"**{eur(r.supp_pension)}**"),
            ]:
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"<span style='font-size:13px;color:#555;'>{lbl}</span>", unsafe_allow_html=True)
                c2.markdown(f"<span style='font-size:13px;'>{val}</span>", unsafe_allow_html=True)

        with cr:
            st.markdown("#### Τελικό αποτέλεσμα")
            rows = [
                ("Βασική σύνταξη",         eur(r.basic_pension)),
                ("Συμπλ. σύνταξη",          eur(r.supp_pension)),
                ("**Σύνολο πριν μείωση**",  f"**{eur(r.total_before_red)}**"),
            ]
            if r.reduction_pct > 0:
                rows.append((f"Μείωση −{int(r.reduction_pct*100)}%", f"−{eur(r.reduction_amt)}"))
            rows.append(("**Καθαρή μηνιαία σύνταξη**", f"**{eur(r.final_pension)}**"))
            for lbl, val in rows:
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"<span style='font-size:13px;color:#555;'>{lbl}</span>", unsafe_allow_html=True)
                c2.markdown(f"<span style='font-size:13px;'>{val}</span>", unsafe_allow_html=True)

            st.markdown("#### Σενάρια ηλικίας")
            sc_rows = []
            for age, red in sorted(EARLY_REDUCT.items()):
                amt = max(r.total_before_red * (1 - red), MIN_PENSIONS[min(dependents, 3)])
                sc_rows.append({
                    "Ηλικία": str(age),
                    "Μείωση": f"−{int(red*100)}%" if red > 0 else "πλήρης",
                    "Μηνιαία σύνταξη": eur(amt),
                    "": "◀" if age == retirement_age else ""
                })
            st.dataframe(pd.DataFrame(sc_rows), hide_index=True, use_container_width=True)

    else:
        # ────────────────────────────────────────────────────────────────────
        # ΛΕΙΤΟΥΡΓΙΑ Β: ΠΡΟΒΛΕΨΗ
        # ────────────────────────────────────────────────────────────────────
        st.markdown('<div class="big-title">🔮 Πρόβλεψη Μελλοντικής Σύνταξης</div>', unsafe_allow_html=True)
        st.markdown(f'<span class="mode-badge" style="background:#E6F1FB;color:#185FA5;">🔮 Ηλικία: {current_age} ετών — Πρόβλεψη σε {retirement_age - current_age} χρόνια</span>', unsafe_allow_html=True)

        with st.spinner("Υπολογισμός 4 σεναρίων..."):
            results = [
                calc_forecast(extracted, retirement_age, dependents, salary_growth,
                              s["rate"], s["label"], s["color"])
                for s in SCENARIOS
            ]

        # Σύγκριση 4 σεναρίων
        cols = st.columns(4)
        for col, r in zip(cols, results):
            with col:
                st.markdown(f"""
                <div class="mbox" style="background:{r.scenario_color}18;border:1.5px solid {r.scenario_color}66;">
                    <div style="font-size:12px;font-weight:600;color:{r.scenario_color};margin-bottom:5px;">{r.scenario_label}</div>
                    <div class="mval" style="color:{r.scenario_color};">{eur(r.final_pension)}</div>
                    <div class="mlbl">μηνιαία σύνταξη</div>
                    <div style="font-size:11px;color:#888;margin-top:3px;">Αξία μον.: {eur(r.unit_value)}</div>
                </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 📊 Αναλυτικά ανά Σενάριο")
        tabs = st.tabs([s["label"] for s in SCENARIOS])

        for tab, r in zip(tabs, results):
            with tab:
                col_l, col_r = st.columns(2)
                pct = int(BASE_RATE_MAP[min(dependents, 3)] * 100)

                with col_l:
                    st.markdown("#### Υπολογισμός")
                    for lbl, val in [
                        ("Βασικές μονάδες σήμερα",           f"{extracted.total_basic:.2f}"),
                        ("+ Εκτιμώμενες μελλοντικές βασικές",f"{r.future_basic:.2f}"),
                        ("= Σύνολο βασικών",                 f"**{r.total_basic:.2f}**"),
                        ("Περίοδος αναφοράς (σύνολο)",       f"{r.ref_years:.2f} χρόνια"),
                        ("Μέσος όρος μονάδων",               f"{r.avg_basic:.4f}"),
                        ("Αξία μονάδας (εκτιμώμενη)",        eur(r.unit_value)),
                        (f"Μηνιαία βασική ({pct}%)",         f"**{eur(r.basic_pension)}**"),
                        ("Συμπλ. μονάδες σήμερα",            f"{extracted.supp_units:.2f}"),
                        ("+ Εκτιμώμενες μελλοντικές συμπλ.", f"{r.future_supp:.2f}"),
                        ("Μηνιαία συμπλ.",                   f"**{eur(r.supp_pension)}**"),
                        (f"Μείωση −{int(r.reduction_pct*100)}%" if r.reduction_pct > 0 else "Χωρίς μείωση",
                         f"−{eur(r.reduction_amt)}" if r.reduction_pct > 0 else "—"),
                        ("**Τελική μηνιαία σύνταξη**",       f"**{eur(r.final_pension)}**"),
                    ]:
                        c1, c2 = st.columns([3, 1])
                        c1.markdown(f"<span style='font-size:13px;color:#555;'>{lbl}</span>", unsafe_allow_html=True)
                        c2.markdown(f"<span style='font-size:13px;'>{val}</span>", unsafe_allow_html=True)

                with col_r:
                    st.markdown("#### Εξέλιξη μονάδων")
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=r.chart_labels, y=r.chart_basic,
                        mode="lines+markers", name="Βασικές",
                        line=dict(color="#185FA5", width=2),
                        fill="tozeroy", fillcolor="rgba(24,95,165,0.08)"))
                    fig.add_trace(go.Scatter(x=r.chart_labels, y=r.chart_supp,
                        mode="lines+markers", name="Συμπλ.",
                        line=dict(color="#1D9E75", width=2),
                        fill="tozeroy", fillcolor="rgba(29,158,117,0.08)"))
                    fig.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=0),
                        legend=dict(orientation="h", y=-0.2),
                        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                        xaxis=dict(showgrid=False),
                        yaxis=dict(gridcolor="rgba(128,128,128,0.1)"))
                    st.plotly_chart(fig, use_container_width=True)

        # Γράφημα σύγκρισης
        st.markdown("### 📊 Σύγκριση Σεναρίων")
        fig_bar = go.Figure(data=[
            go.Bar(name="Βασική", x=[r.scenario_label for r in results],
                   y=[round(r.basic_pension,2) for r in results],
                   marker_color=["#B4B2A9","#FAC775","#85B7EB","#97C459"]),
            go.Bar(name="Συμπλ.", x=[r.scenario_label for r in results],
                   y=[round(r.supp_pension,2) for r in results],
                   marker_color=["#888780","#EF9F27","#378ADD","#639922"]),
        ])
        fig_bar.update_layout(barmode="stack", height=300,
            margin=dict(l=0,r=0,t=10,b=0), legend=dict(orientation="h",y=-0.15),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(tickprefix="€", gridcolor="rgba(128,128,128,0.1)"),
            xaxis=dict(showgrid=False))
        st.plotly_chart(fig_bar, use_container_width=True)

        # Πίνακας σύγκρισης
        df = pd.DataFrame([{
            "Σενάριο":       r.scenario_label,
            "Αξία μονάδας":  eur(r.unit_value),
            "Βασική":        eur(r.basic_pension),
            "Συμπλ.":        eur(r.supp_pension),
            "Μηνιαία":       eur(r.final_pension),
            "Ετήσια (×13)":  eur(r.final_pension * 13),
        } for r in results])
        st.dataframe(df, hide_index=True, use_container_width=True)

    # ── Κοινές σημειώσεις ─────────────────────────────────────────────────────
    st.markdown("""
    <div class="orange-box">
    📌 <strong>Παρατηρήσεις:</strong>
    13η σύνταξη κάθε Δεκέμβριο ·
    Αναβολή μετά τα 65: +0,5%/μήνα ·
    Αύξηση 1/1 και 1/7 κάθε χρόνο ·
    Από 1/1/2024: +3,89% βασική, +1,68% συμπλ.
    </div>
    """, unsafe_allow_html=True)
    st.caption("Μέθοδος: Μ. Χρίστου · Περί Κοινωνικών Ασφαλίσεων Νόμοι 2010–2024 · €201,57/μονάδα")


if __name__ == "__main__":
    main()
