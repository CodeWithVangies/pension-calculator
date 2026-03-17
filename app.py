"""
calculator.py
Λογική υπολογισμού θεσμοθετημένης σύνταξης
Κυπριακό Σχέδιο Κοινωνικών Ασφαλίσεων (Νόμοι 2010–2024)
"""

from datetime import date
import pandas as pd

# Εβδομαδιαία αξία βασικής ασφαλιστικής μονάδας (2024)
REF_UNIT_VALUE = 201.57

# Αναλογιστική μείωση ανά μήνα πρόωρης συνταξιοδότησης
EARLY_REDUCTION_PER_MONTH = 0.005   # 0,5% / μήνα → 12% για 24 μήνες (63→65)


def _ref_years(ref_start: date, retire_date: date) -> float:
    """Περίοδος αναφοράς σε κλάσμα έτους."""
    delta_days = (retire_date - ref_start).days
    return delta_days / 365.25


def _reduction_factor(ret_age: int) -> float:
    """
    Αναλογιστική μείωση:
      63 ετών → 24 μήνες νωρίτερα → 12%
      65 ετών → 0%
    """
    months_early = (65 - ret_age) * 12
    return 1.0 - EARLY_REDUCTION_PER_MONTH * months_early


def build_projections(df_hist: pd.DataFrame,
                      retire_date: date,
                      rate: float = 0.0) -> pd.DataFrame:
    """
    Προσθέτει προβλεπόμενα έτη από το τελευταίο ιστορικό έτος
    μέχρι το έτος συνταξιοδότησης.

    rate=0.0  → flat (τελευταία μονάδα σταθερή)
    rate>0    → σύνθετη αύξηση ανά έτος
    """
    df = df_hist.copy()
    last_year  = int(df["Έτος"].max())
    last_units = float(df.loc[df["Έτος"] == last_year, "Μονάδες"].iloc[0])
    retire_year = retire_date.year
    rows = []

    for y in range(last_year + 1, retire_year + 1):
        years_ahead = y - last_year
        u = last_units * ((1 + rate) ** years_ahead)

        # Μερικό έτος συνταξιοδότησης
        if y == retire_year:
            days_in_year = (retire_date - date(y, 1, 1)).days
            u = u * days_in_year / 365.0

        rows.append({"Έτος": y, "Μονάδες": round(u, 4),
                     "Πηγή": "projection", "Πρόβλεψη": True})

    if rows:
        df_proj = pd.DataFrame(rows)
        df["Πρόβλεψη"] = False
        df = pd.concat([df, df_proj], ignore_index=True)
    else:
        df["Πρόβλεψη"] = False

    # Βασική & συμπληρωματική μονάδα ανά έτος
    df["Βασική"] = df["Μονάδες"].clip(upper=1.0)
    df["Συμπλ."] = (df["Μονάδες"] - 1.0).clip(lower=0)
    return df


def calculate_pension(df_full: pd.DataFrame,
                      ref_start: date,
                      retire_date: date,
                      ret_age: int) -> dict:
    """
    Υπολογίζει βασική + συμπληρωματική σύνταξη.
    Επιστρέφει dict με όλα τα ενδιάμεσα μεγέθη.
    """
    ref_yrs     = _ref_years(ref_start, retire_date)
    basic_total = float(df_full["Βασική"].sum())
    suppl_total = float(df_full["Συμπλ."].sum())

    # Βασική σύνταξη
    avg_basic       = min(basic_total / ref_yrs, 1.0)
    weekly_basic    = REF_UNIT_VALUE * avg_basic * 0.60
    monthly_basic   = weekly_basic * (52 / 13)

    # Συμπληρωματική σύνταξη
    weekly_suppl    = REF_UNIT_VALUE * 0.015 * suppl_total
    monthly_suppl   = weekly_suppl * (52 / 13)

    total_monthly   = monthly_basic + monthly_suppl
    factor          = _reduction_factor(ret_age)
    final_total     = total_monthly * factor

    return {
        "ref_years":     round(ref_yrs, 4),
        "basic_total":   round(basic_total, 4),
        "suppl_total":   round(suppl_total, 4),
        "avg_basic":     round(avg_basic, 6),
        "monthly_basic": round(monthly_basic, 2),
        "monthly_suppl": round(monthly_suppl, 2),
        "total_monthly": round(total_monthly, 2),
        "reduction":     round(1 - factor, 4),
        "final_total":   round(final_total, 2),
    }


def calculate_scenario(df_hist: pd.DataFrame,
                       ref_start: date,
                       retire_date: date,
                       ret_age: int,
                       rate: float) -> dict:
    """
    Υπολογίζει σύνταξη για δεδομένο ρυθμό αύξησης μονάδων.
    """
    df_full = build_projections(df_hist, retire_date, rate=rate)
    return calculate_pension(df_full, ref_start, retire_date, ret_age)
