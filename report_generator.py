"""
report_generator.py
Δημιουργεί PDF αναφορά αποτελεσμάτων σύνταξης με reportlab.
"""

import io
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Χρώματα ─────────────────────────────────────────────────────────────────
BLUE   = colors.HexColor("#378ADD")
GREEN  = colors.HexColor("#1D9E75")
AMBER  = colors.HexColor("#BA7517")
GRAY   = colors.HexColor("#888780")
LGRAY  = colors.HexColor("#F1EFE8")
DGRAY  = colors.HexColor("#444441")
WHITE  = colors.white
BLACK  = colors.black

SC_COLORS = [BLUE, GREEN, AMBER]


def _styles():
    base = getSampleStyleSheet()
    custom = {
        "title": ParagraphStyle("title", parent=base["Normal"],
                                fontSize=18, textColor=DGRAY,
                                spaceAfter=4, fontName="Helvetica-Bold"),
        "subtitle": ParagraphStyle("subtitle", parent=base["Normal"],
                                   fontSize=10, textColor=GRAY,
                                   spaceAfter=12, fontName="Helvetica"),
        "section": ParagraphStyle("section", parent=base["Normal"],
                                  fontSize=10, textColor=GRAY,
                                  fontName="Helvetica-Bold",
                                  spaceBefore=14, spaceAfter=6,
                                  textTransform="uppercase"),
        "body": ParagraphStyle("body", parent=base["Normal"],
                               fontSize=9, textColor=DGRAY,
                               fontName="Helvetica", leading=14),
        "note": ParagraphStyle("note", parent=base["Normal"],
                               fontSize=7.5, textColor=GRAY,
                               fontName="Helvetica", leading=11),
        "big": ParagraphStyle("big", parent=base["Normal"],
                              fontSize=22, fontName="Helvetica-Bold",
                              textColor=DGRAY),
    }
    return custom


def _kv_table(rows, col_widths=(10*cm, 5*cm)):
    """Δημιουργεί απλό πίνακα key-value."""
    data = [[Paragraph(f"<font color='#{GRAY.hexval()[2:]}' size='8'>{k}</font>",
                       getSampleStyleSheet()["Normal"]),
             Paragraph(f"<b>{v}</b>", getSampleStyleSheet()["Normal"])]
            for k, v in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTSIZE",    (0, 0), (-1, -1), 9),
        ("TEXTCOLOR",   (0, 0), (0, -1), GRAY),
        ("TEXTCOLOR",   (1, 0), (1, -1), DGRAY),
        ("ALIGN",       (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW",   (0, 0), (-1, -2), 0.3, colors.HexColor("#E0E0E0")),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    return t


def generate_report(
    name: str,
    dob: date,
    ret_age: int,
    base: dict,
    sc_results: list[dict],
    df_full,
    retire_date: date,
) -> bytes:
    """
    Παράγει PDF αναφορά και επιστρέφει bytes.

    Παράμετροι:
      name        : όνομα ασφαλισμένου
      dob         : ημερομηνία γέννησης
      ret_age     : ηλικία συνταξιοδότησης (63 ή 65)
      base        : dict από calculate_pension() (flat projection)
      sc_results  : list of dicts από calculate_scenario()
      df_full     : DataFrame με όλες τις μονάδες
      retire_date : ημερομηνία συνταξιοδότησης
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    S = _styles()
    W = A4[0] - 4*cm   # ωφέλιμο πλάτος
    story = []

    # ── Επικεφαλίδα ─────────────────────────────────────────────────────────
    story.append(Paragraph("Εκτίμηση Θεσμοθετημένης Σύνταξης", S["title"]))
    story.append(Paragraph(
        "Κυπριακό Σχέδιο Κοινωνικών Ασφαλίσεων &nbsp;|&nbsp; "
        f"Ημερομηνία έκδοσης: {date.today().strftime('%d/%m/%Y')}",
        S["subtitle"]))
    story.append(HRFlowable(width=W, thickness=1, color=BLUE, spaceAfter=12))

    # ── Στοιχεία ασφαλισμένου ───────────────────────────────────────────────
    story.append(Paragraph("Στοιχεία ασφαλισμένου", S["section"]))
    reduction_lbl = "−12% (πρόωρη)" if ret_age == 63 else "Χωρίς μείωση"
    story.append(_kv_table([
        ("Ονοματεπώνυμο",         name or "—"),
        ("Ημερομηνία γέννησης",   dob.strftime("%d/%m/%Y")),
        ("Ηλικία συνταξιοδότησης", f"{ret_age} ετών  ({reduction_lbl})"),
        ("Εκτιμώμενη ημ. σύνταξης", retire_date.strftime("%d/%m/%Y")),
        ("Περίοδος αναφοράς",     f"{base['ref_years']:.2f} χρόνια"),
    ]))
    story.append(Spacer(1, 0.4*cm))

    # ── Βασικά μεγέθη ────────────────────────────────────────────────────────
    story.append(Paragraph("Ασφαλιστικές μονάδες", S["section"]))
    story.append(_kv_table([
        ("Σύνολο βασικών μονάδων",         f"{base['basic_total']:.2f}"),
        ("Σύνολο συμπληρωματικών μονάδων", f"{base['suppl_total']:.2f}"),
        ("Ετήσιος μέσος όρος βασικών",     f"{base['avg_basic']:.4f}"),
    ]))
    story.append(Spacer(1, 0.4*cm))

    # ── Αποτέλεσμα (flat) ────────────────────────────────────────────────────
    story.append(Paragraph("Αποτέλεσμα — σταθερές μονάδες (χωρίς αύξηση)", S["section"]))
    story.append(_kv_table([
        ("Βασική σύνταξη/μήνα",          f"€{base['monthly_basic']:.2f}"),
        ("Συμπληρωματική σύνταξη/μήνα",  f"€{base['monthly_suppl']:.2f}"),
        ("Σύνολο πριν αναλογιστική μείωση", f"€{base['total_monthly']:.2f}"),
        (f"Αναλογιστική μείωση ({base['reduction']*100:.0f}%)",
         f"−€{base['total_monthly']*base['reduction']:.2f}"),
        ("Τελική μηνιαία σύνταξη",       f"€{base['final_total']:.2f}"),
        ("Ετήσια σύνταξη (×13)",         f"€{base['final_total']*13:.2f}"),
    ]))
    story.append(Spacer(1, 0.5*cm))

    # ── Σενάρια ──────────────────────────────────────────────────────────────
    story.append(Paragraph("Σενάρια ανάπτυξης μονάδων", S["section"]))

    sc_labels = ["Σενάριο Α  +1,5%/έτος",
                 "Σενάριο Β  +2,5%/έτος",
                 "Σενάριο Γ  +3,5%/έτος"]

    # Πίνακας σύγκρισης σεναρίων
    hdr = ["", "Βασική/μήνα", "Συμπλ./μήνα", "Σύνολο/μήνα",
           f"Τελική ({ret_age} ετών)", "Ετήσια (×13)"]
    rows = [hdr]
    for i, s in enumerate(sc_results):
        total = s["monthly_basic"] + s["monthly_suppl"]
        rows.append([
            sc_labels[i],
            f"€{s['monthly_basic']:.2f}",
            f"€{s['monthly_suppl']:.2f}",
            f"€{total:.2f}",
            f"€{s['final_total']:.2f}",
            f"€{s['final_total']*13:.2f}",
        ])

    col_w = [4.5*cm, 2.2*cm, 2.2*cm, 2.4*cm, 2.8*cm, 2.8*cm]
    sc_tbl = Table(rows, colWidths=col_w, repeatRows=1)
    sc_tbl.setStyle(TableStyle([
        # Header
        ("BACKGROUND",    (0, 0), (-1, 0), LGRAY),
        ("TEXTCOLOR",     (0, 0), (-1, 0), GRAY),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("ALIGN",         (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN",         (0, 0), (0, -1), "LEFT"),
        # Row colors
        ("BACKGROUND",    (0, 1), (-1, 1), colors.HexColor("#EBF4FC")),
        ("BACKGROUND",    (0, 2), (-1, 2), colors.HexColor("#E8F6F2")),
        ("BACKGROUND",    (0, 3), (-1, 3), colors.HexColor("#FDF3E3")),
        # Borders
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, colors.HexColor("#DDDDDD")),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        # Final column bold
        ("FONTNAME",      (4, 1), (4, -1), "Helvetica-Bold"),
        ("TEXTCOLOR",     (4, 1), (4, 1), BLUE),
        ("TEXTCOLOR",     (4, 2), (4, 2), GREEN),
        ("TEXTCOLOR",     (4, 3), (4, 3), AMBER),
    ]))
    story.append(sc_tbl)
    story.append(Spacer(1, 0.5*cm))

    # ── Πίνακας μονάδων ──────────────────────────────────────────────────────
    story.append(Paragraph("Αναλυτικές ασφαλιστικές μονάδες ανά έτος", S["section"]))

    unit_hdr = ["Έτος", "Ασφ. Μονάδες", "Βασική (max 1)", "Συμπλ.", "Πρόβλεψη"]
    unit_rows = [unit_hdr]
    for _, row in df_full.iterrows():
        suppl = max(0, row["Μονάδες"] - 1.0)
        unit_rows.append([
            str(int(row["Έτος"])),
            f"{row['Μονάδες']:.3f}",
            f"{min(row['Μονάδες'], 1.0):.3f}",
            f"{suppl:.3f}" if suppl > 0 else "—",
            "✓" if row.get("Πρόβλεψη", False) else "",
        ])

    # Split σε 2 στήλες για εξοικονόμηση χώρου
    half = len(unit_rows) // 2 + 1
    left_rows  = unit_rows[:half]
    right_rows = unit_rows[half:]
    # Pad right side if needed
    while len(right_rows) < len(left_rows):
        right_rows.append(["", "", "", "", ""])

    cw_half = [1.4*cm, 2.2*cm, 2.4*cm, 1.6*cm, 1.6*cm]
    sep = [[""] * 1]  # separator column
    combined = []
    for l, r in zip(left_rows, right_rows):
        combined.append(l + [""] + r)

    cw_combined = cw_half + [0.3*cm] + cw_half
    u_tbl = Table(combined, colWidths=cw_combined, repeatRows=1)
    u_tbl.setStyle(TableStyle([
        ("FONTSIZE",      (0, 0), (-1, -1), 7.5),
        ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("BACKGROUND",    (0, 0), (4, 0),   LGRAY),
        ("BACKGROUND",    (6, 0), (-1, 0),  LGRAY),
        ("TEXTCOLOR",     (0, 0), (-1, 0),  GRAY),
        ("ALIGN",         (1, 0), (3, -1),  "RIGHT"),
        ("ALIGN",         (7, 0), (9, -1),  "RIGHT"),
        ("LINEBELOW",     (0, 0), (4, -1),  0.2, colors.HexColor("#EEEEEE")),
        ("LINEBELOW",     (6, 0), (-1, -1), 0.2, colors.HexColor("#EEEEEE")),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 3),
        # Projected rows italic color
        ("TEXTCOLOR",     (4, 1), (4, -1),  AMBER),
        ("TEXTCOLOR",     (10, 1), (10, -1), AMBER),
    ]))
    story.append(u_tbl)
    story.append(Spacer(1, 0.5*cm))

    # ── Υποσημείωση ──────────────────────────────────────────────────────────
    story.append(HRFlowable(width=W, thickness=0.5, color=GRAY, spaceBefore=8, spaceAfter=6))
    story.append(Paragraph(
        f"⚠ Η παρούσα εκτίμηση βασίζεται στην αξία εβδομαδιαίας ασφαλιστικής μονάδας "
        f"€{201.57:.2f} (2024). Η πραγματική σύνταξη το {retire_date.year} θα είναι "
        f"υψηλότερη λόγω ετήσιων αναπροσαρμογών. Κατώτατο όριο για δικαιούχο χωρίς "
        f"εξαρτώμενα: €411,20/μήνα (01/01/2024). Το έγγραφο αυτό είναι εκτίμηση "
        f"και δεν αποτελεί επίσημο έγγραφο των Υπηρεσιών Κοινωνικών Ασφαλίσεων.",
        S["note"]))

    doc.build(story)
    return buf.getvalue()
