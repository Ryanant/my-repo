"""The shared FM-project rating model, adapted for FM24 memory field names."""
from __future__ import annotations

import numpy as np
import pandas as pd

OUTFIELD_IDEALS = {"pace": 18, "acceleration": 18, "jumping_reach": 10, "dribbling": 10, "balance": 10, "work_rate": 10, "anticipation": 10, "agility": 6, "concentration": 6, "stamina": 6}
GK_WEIGHTS = {"agility": .014640, "reflexes": .012837, "aerial_reach": .011812, "communication": .007436, "handling": .006255, "decisions": .005089}
OUTFIELD_POSITIONS = ("SW", "DL", "DC", "DR", "DM", "ML", "MC", "MR", "WBL", "WBR", "AML", "AMC", "AMR", "ST")


def _values(df: pd.DataFrame, name: str) -> pd.Series:
    return pd.to_numeric(df[name], errors="coerce").fillna(0) if name in df else pd.Series(0.0, index=df.index)


def add_ratings(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    positions = out["Positions"]
    gk = pd.Series(0.0, index=out.index)
    max_gk = sum(abs(weight) * 20 for weight in GK_WEIGHTS.values())
    for attr, weight in GK_WEIGHTS.items():
        gk += _values(out, attr).clip(0, 20) * weight
    gk = (gk / max_gk * 100).round(2)
    out["GK_rating"] = gk.where(positions.map(lambda value: "GK" in (value if isinstance(value, list) else [])))

    outfield = pd.Series(0.0, index=out.index)
    deficits = pd.Series(0.0, index=out.index)
    for attr, ideal in OUTFIELD_IDEALS.items():
        delta = _values(out, attr) - ideal
        deficits += (-delta).clip(lower=0)
        outfield += delta.clip(lower=0)
    outfield = outfield.where(deficits.eq(0), -deficits).round(2)
    for position in OUTFIELD_POSITIONS:
        out[f"{position}_rating"] = outfield.where(positions.map(lambda value, p=position: p in (value if isinstance(value, list) else [])))

    rating_cols = ["GK_rating", *[f"{position}_rating" for position in OUTFIELD_POSITIONS]]
    numeric = out[rating_cols].apply(pd.to_numeric, errors="coerce")
    valid = numeric.notna().any(axis=1)
    out["Best Position"] = "N/A"
    out.loc[valid, "Best Position"] = numeric.loc[valid].idxmax(axis=1).str.replace("_rating", "", regex=False)
    out["Current Rating"] = numeric.max(axis=1).round(2).fillna(0)
    out["Best Roles"] = numeric.apply(lambda row: ", ".join(row.dropna().sort_values(ascending=False).head(3).index.str.replace("_rating", "")), axis=1)
    return out


def add_prediction_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Estimate rating potential from the CA-to-PA headroom.

    Use the live snapshot age when available. Half of the CA-to-PA gap is used
    as conservative rating headroom, with a stronger age penalty after peak
    development years.
    """
    out = df.copy()
    def numeric_column(name: str) -> pd.Series:
        value = out[name] if name in out else pd.Series(0.0, index=out.index)
        return pd.to_numeric(value, errors="coerce")

    current = numeric_column("Current Rating").fillna(0)
    ca = numeric_column("Current Ability")
    pa = numeric_column("Potential Ability")
    age = numeric_column("Age")
    age_factor = pd.Series(np.select(
        [age.isna(), age < 20, age < 24, age < 28, age < 32],
        [1.0, 1.0, 0.85, 0.60, 0.25],
        default=0.05,
    ), index=out.index)
    headroom = ((pa - ca).clip(lower=0) / 2.0 * age_factor).fillna(0)
    out["Potential Rating"] = (current + headroom).clip(upper=100).round(2)
    out["Potential Increase"] = (out["Potential Rating"] - current).round(2)
    out["Potential Gap"] = (out["Potential Rating"] - current).round(2)
    return out
