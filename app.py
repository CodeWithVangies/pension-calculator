import streamlit as st
import pandas as pd
from datetime import date
import plotly.graph_objects as go
from pdf_parser import parse_ka_pdf
from calculator import (
    build_projections,
    calculate_pension,
    calculate_scenario,
    REF_UNIT_VALUE,
)
from report_generator import generate_report

st.set_page_config(
    page_title="Υπολογιστής Σύνταξης ΚΑ",
    page_icon="🏦",
    layout="centered",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .main .block-container { max-width: 800px; padding-top: 2rem; }
    .step-header { font-size: 12px; font-weight: 600; color: #888;
                   text-transform: uppercase; letter-spacing: .06em;
                   border-bottom: 1px solid #eee; padding-bottom: 6px;
                   margin-bottom: 16px; margin-top: 24px; }
    .result-box  { background: #f8f9fa; border-radius: 10px;
                   padding: 1rem 1.25rem; border: 1px solid #e0e0e0;
                   margin-bottom: 12px; }
    .big-number  { font-size: 2rem; font-weight: 700; }
    .note-text   { font-size: 11px; color: #999; line-height: 1.6; margin-top: 8px; }
    .dep-box     { background: #fff8ec; border-radius: 8px;
                   padding: .75rem 1rem; border: 1px solid #f0d080;
                   margin-bottom: 10px; font-size: 13px; }
</style>
""", unsafe_allow_html=True)

# ── Title ────────────────────────────────────────────────────────────────────
st.title("🏦 Υπολογιστής Σύνταξης Κοινωνικών Ασφαλίσεων")
st.caption("Κυπριακό Σχέδιο Κοινωνικών Ασφαλίσεων — βασισμένο στους Νόμους 2010–2024")
st.divider()

# ════════════════════════════════════════════════════════════════════════════
# ΒΗΜΑ 1 — Στοιχεία χρήστη
# ════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="step-header">📋 Βήμα 1 — Στοιχεία & Ανέβασμα PDF</div>',
            unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    full_name = st.text_input("Ονοματεπώνυμο (προαιρετικό)",
                              placeholder="π.χ. Ιωάννης Παπαδόπουλος")
    dob = st.date_input("Ημερομηνία γέννησης",
                        value=date(1975, 11, 12),
                        min_value=date(1940, 1, 1),
                        max_value=date(2005, 12, 31),
                        format="DD/MM/YYYY")
with col2:
    ret_age = st.radio(
        "Ηλικία συνταξιοδότησης",
        options=[63, 65],
        format_func=lambda x: f"{x} ετών {'(−12% μείωση)' if x==63 else '(κανονική)'}",
        horizontal=True)

    st.markdown("**Εξαρτώμενα πρόσωπα** *(αύξηση στο βασικό μέρος)*")
    dep_spouse = st.checkbox("Σύζυγος χωρίς ασφαλιστέα απασχόληση (+20%)")
    dep_children = st.selectbox(
        "Εξαρτώμενα παιδιά",
        options=[0, 1, 2],
        format_func=lambda x: {0:"Κανένα", 1:"1 παιδί (+10%)", 2:"2+ παιδιά (+20%)"}[x])

uploaded_pdf = st.file_uploader(
    "📄 Ανεβάστε την Κατάσταση Ασφαλιστικού Λογαριασμού (PDF)",
    type=["pdf"],
    help="Κατεβάστε το PDF από: eforms.eservices.cyprus.gov.cy",
)

# ════════════════════════════════════════════════════════════════════════════
# ΒΗΜΑ 2 — Επαλήθευση & επεξεργασία δεδομένων
# ════════════════════════════════════════════════════════════════════════════
if uploaded_pdf is not None:
    st.divider()
    st.markdown('<div class="step-header">✏️ Βήμα 2 — Επαλήθευση & Επεξεργασία Δεδομένων</div>',
                unsafe_allow_html=True)

    with st.spinner("Διαβάζω το PDF..."):
        df_parsed, parse_msg = parse_ka_pdf(uploaded_pdf)

    if df_parsed is None:
        st.error(f"Πρόβλημα ανάγνωσης PDF: {parse_msg}")
        st.stop()

    st.success(f"✓ {parse_msg}")

    retire_date  = date(dob.year + ret_age, dob.month, dob.day)
    ref_start    = date(dob.year + 16, 1, 1)
    ref_start_yr = ref_start.year

    # Συμπλήρωση 0-μονάδων από έτος 16ου γενεθλίου αν το PDF ξεκινά αργότερα
    pdf_start_yr = int(df_parsed["Έτος"].min())
    if pdf_start_yr > ref_start_yr:
        zero_rows = pd.DataFrame({
            "Έτος":     range(ref_start_yr, pdf_start_yr),
            "Μονάδες":  0.0,
            "Πρόβλεψη": False,
        })
        df_parsed_padded = pd.concat([zero_rows, df_parsed], ignore_index=True)
    else:
        df_parsed_padded = df_parsed.copy()

    df_full = build_projections(df_parsed_padded, retire_date)

    st.markdown("**Ελέγξτε και διορθώστε τις μονάδες αν χρειαστεί.**  \n"
                "*Τα έτη με ✓ στη στήλη Πρόβλεψη είναι εκτιμώμενα.*")

    df_edit = df_full[["Έτος", "Μονάδες", "Πρόβλεψη"]].copy()
    edited = st.data_editor(
        df_edit,
        column_config={
            "Έτος":     st.column_config.NumberColumn("Έτος", disabled=True),
            "Μονάδες":  st.column_config.NumberColumn(
                            "Ασφ. Μονάδες", min_value=0.0, max_value=20.0,
                            step=0.001, format="%.3f"),
            "Πρόβλεψη": st.column_config.CheckboxColumn("Πρόβλεψη", disabled=True),
        },
        width='stretch',
        hide_index=True,
        num_rows="fixed",
    )

    df_full["Μονάδες"] = edited["Μονάδες"].values
    df_full["Βασική"]  = df_full["Μονάδες"].clip(upper=1.0)
    df_full["Συμπλ."]  = (df_full["Μονάδες"] - 1.0).clip(lower=0)

    # ════════════════════════════════════════════════════════════════════════
    # ΒΗΜΑ 3 — Αποτελέσματα
    # ════════════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown('<div class="step-header">📊 Βήμα 3 — Αποτελέσματα</div>',
                unsafe_allow_html=True)

    base = calculate_pension(df_full, ref_start, retire_date, ret_age)

    # ── Συντελεστής εξαρτωμένων (μόνο στο βασικό μέρος) ────────────────────
    dep_pct   = 0.0
    dep_lines = []
    if dep_spouse:
        dep_pct += 0.20
        dep_lines.append("Σύζυγος: +20%")
    if dep_children == 1:
        dep_pct += 0.10
        dep_lines.append("1 παιδί: +10%")
    elif dep_children == 2:
        dep_pct += 0.20
        dep_lines.append("2 παιδιά: +20%")
    dep_pct = min(dep_pct, 0.40)

    basic_with_dep = base["monthly_basic"] * (1 + dep_pct)
    total_with_dep = basic_with_dep + base["monthly_suppl"]
    final_with_dep = total_with_dep * (1 - base["reduction"])

    # ── KPI ─────────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Περίοδος αναφοράς",  f"{base['ref_years']:.2f} χρ.")
    c2.metric("Βασικές μονάδες",    f"{base['basic_total']:.2f}")
    c3.metric("Συμπλ. μονάδες",     f"{base['suppl_total']:.2f}")
    c4.metric("Μέσος όρος βασικής", f"{base['avg_basic']:.4f}")

    st.divider()

    # ── Εξαρτώμενα info box ─────────────────────────────────────────────────
    if dep_pct > 0:
        dep_text = " | ".join(dep_lines)
        basic_increase = basic_with_dep - base["monthly_basic"]
        st.markdown(
            f'<div class="dep-box">👨‍👩‍👧 <b>Αύξηση λόγω εξαρτωμένων ({dep_pct*100:.0f}%):</b> '
            f'{dep_text} — '
            f'Βασική σύνταξη: €{base["monthly_basic"]:.2f} → <b>€{basic_with_dep:.2f}</b> '
            f'(+€{basic_increase:.2f}/μήνα)</div>',
            unsafe_allow_html=True)

    # ── Κύρια αποτελέσματα ──────────────────────────────────────────────────
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown(
            '<div class="result-box">'
            '<div style="color:#555;font-size:12px;">Βασική σύνταξη/μήνα</div>'
            f'<div class="big-number" style="color:#378ADD;">€{basic_with_dep:.2f}</div>'
            f'<div style="font-size:11px;color:#999;">{"με εξαρτ." if dep_pct>0 else "χωρίς εξαρτ."}</div>'
            '</div>', unsafe_allow_html=True)
    with col_b:
        st.markdown(
            '<div class="result-box">'
            '<div style="color:#555;font-size:12px;">Συμπλ. σύνταξη/μήνα</div>'
            f'<div class="big-number" style="color:#1D9E75;">€{base["monthly_suppl"]:.2f}</div>'
            '</div>', unsafe_allow_html=True)
    with col_c:
        color = "#BA7517" if ret_age == 63 else "#1D9E75"
        label = f"Τελική ({ret_age} ετών)" + (" −12%" if ret_age == 63 else "")
        st.markdown(
            f'<div class="result-box">'
            f'<div style="color:#555;font-size:12px;">{label}</div>'
            f'<div class="big-number" style="color:{color};">€{final_with_dep:.2f}</div>'
            f'<div style="font-size:11px;color:#999;">Ετήσια: €{final_with_dep*13:.2f}</div>'
            f'</div>', unsafe_allow_html=True)

    # ── Σενάρια ─────────────────────────────────────────────────────────────
    st.markdown("#### Σενάρια ανάπτυξης μονάδων")
    scenarios = [
        {"label": "Σενάριο Α  +1,5%/έτος", "rate": 0.015, "color": "#378ADD"},
        {"label": "Σενάριο Β  +2,5%/έτος", "rate": 0.025, "color": "#1D9E75"},
        {"label": "Σενάριο Γ  +3,5%/έτος", "rate": 0.035, "color": "#BA7517"},
    ]

    sc_results = []
    for sc in scenarios:
        r = calculate_scenario(df_parsed_padded, ref_start, retire_date, ret_age, sc["rate"])
        r["monthly_basic_dep"] = r["monthly_basic"] * (1 + dep_pct)
        r["final_total_dep"]   = (r["monthly_basic_dep"] + r["monthly_suppl"]) * (1 - base["reduction"])
        r["label"] = sc["label"]
        r["color"] = sc["color"]
        sc_results.append(r)

    tabs = st.tabs([s["label"] for s in sc_results])
    for i, tab in enumerate(tabs):
        s = sc_results[i]
        with tab:
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Βασική/μήνα",  f"€{s['monthly_basic_dep']:.2f}")
            col2.metric("Συμπλ./μήνα",  f"€{s['monthly_suppl']:.2f}")
            col3.metric("Τελική/μήνα",  f"€{s['final_total_dep']:.2f}",
                        delta=f"{s['final_total_dep']-final_with_dep:+.2f} vs flat")
            col4.metric("Ετήσια (×13)", f"€{s['final_total_dep']*13:.2f}")

    # ── Bar chart ────────────────────────────────────────────────────────────
    categories = ["Βασική", "Συμπλ.", "Σύνολο", f"Τελική ({ret_age} ετών)"]
    fig = go.Figure()
    for s in sc_results:
        total = s["monthly_basic_dep"] + s["monthly_suppl"]
        fig.add_bar(
            name=s["label"],
            x=categories,
            y=[round(s["monthly_basic_dep"], 2), round(s["monthly_suppl"], 2),
               round(total, 2), round(s["final_total_dep"], 2)],
            marker_color=s["color"], marker_line_width=0,
        )
    fig.update_layout(
        barmode="group", plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        yaxis=dict(tickprefix="€", gridcolor="#eee"),
        xaxis=dict(gridcolor="#eee"),
        margin=dict(l=10, r=10, t=40, b=10), height=360,
    )
    st.plotly_chart(fig, width='stretch')

    st.markdown(
        f'<div class="note-text">⚠ Αξία μονάδας: €{REF_UNIT_VALUE:.2f} (2026). '
        f'Η πραγματική σύνταξη το {retire_date.year} θα είναι υψηλότερη. '
        f'Κατώτατο όριο (χωρίς εξαρτώμενα): €411,20/μήνα. '
        f'Η αύξηση εξαρτωμένων εφαρμόζεται μόνο στο βασικό μέρος.</div>',
        unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════════════════════
    # ΕΚΤΥΠΩΣΗ PDF
    # ════════════════════════════════════════════════════════════════════════
    st.divider()
    st.markdown('<div class="step-header">🖨️ Εκτύπωση αποτελεσμάτων</div>',
                unsafe_allow_html=True)

    col_pdf1, col_pdf2 = st.columns([3, 1])
    with col_pdf1:
        st.markdown("Κατεβάστε πλήρη αναφορά PDF με όλα τα αποτελέσματα, "
                    "τα σενάρια και τον αναλυτικό πίνακα μονάδων ανά έτος.")
    with col_pdf2:
        if st.button("📥 Δημιουργία PDF", width='stretch'):
            with st.spinner("Δημιουργώ την αναφορά..."):
                try:
                    sc_for_report = [
                        {"monthly_basic": s["monthly_basic_dep"],
                         "monthly_suppl": s["monthly_suppl"],
                         "final_total":   s["final_total_dep"]}
                        for s in sc_results
                    ]
                    pdf_bytes = generate_report(
                        name        = full_name or "—",
                        dob         = dob,
                        ret_age     = ret_age,
                        base        = {**base,
                                       "monthly_basic": basic_with_dep,
                                       "total_monthly": total_with_dep,
                                       "final_total":   final_with_dep},
                        sc_results  = sc_for_report,
                        df_full     = df_full,
                        retire_date = retire_date,
                    )
                    fname = (f"Συνταξη_"
                             f"{(full_name or 'αποτελεσματα').replace(' ','_')}"
                             f"_{date.today()}.pdf")
                    st.download_button(
                        label="⬇️ Κατεβάστε το PDF",
                        data=pdf_bytes,
                        file_name=fname,
                        mime="application/pdf",
                        width='stretch',
                    )
                except Exception as e:
                    st.error(f"Σφάλμα δημιουργίας PDF: {e}")
                    st.info("Βεβαιωθείτε ότι το reportlab είναι εγκατεστημένο: "
                            "`pip install reportlab`")

else:
    st.info("⬆️ Ανεβάστε το PDF της Κατάστασης Ασφαλιστικού Λογαριασμού για να συνεχίσετε.")
