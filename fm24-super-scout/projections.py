"""Conservative potential-rating estimates based on the original FM project."""
from __future__ import annotations

import numpy as np
import pandas as pd

POSITIONS = ["GK", "SW", "DL", "DC", "DR", "DM", "ML", "MC", "MR", "WBL", "WBR", "AML", "AMC", "AMR", "ST"]

PEAK_AGE = {"GK": 33.0}
DEFAULT_PEAK_AGE = 28.5
PACE_ACC_BOOST = {15: 7, 16: 6, 17: 4, 18: 3, 19: 1}
OUTFIELD_IDEALS = {
    "pace": 18, "acceleration": 18, "jumping_reach": 10, "dribbling": 10,
    "balance": 10, "work_rate": 10, "anticipation": 10, "agility": 6,
    "concentration": 6, "stamina": 6,
}


def _number(row: pd.Series, name: str, default=np.nan) -> float:
    value = pd.to_numeric(row.get(name, default), errors="coerce")
    return float(value) if pd.notna(value) else default


def _ideal_score(row: pd.Series) -> float:
    deficits = 0.0
    surplus = 0.0
    for attr, ideal in OUTFIELD_IDEALS.items():
        delta = _number(row, attr, 0.0) - ideal
        if delta < 0:
            deficits -= delta
        else:
            surplus += delta
    return -deficits if deficits else surplus


def _attribute_peak(row: pd.Series, current: float) -> float:
    age = _number(row, "Age")
    if not np.isfinite(age):
        return current
    boosted = row.copy()
    year = int(age)
    for attr in ("pace", "acceleration"):
        boosted[attr] = _number(boosted, attr, 0.0) + PACE_ACC_BOOST.get(year, 0)
    if year in {15, 16}:
        for attr in OUTFIELD_IDEALS:
            if attr not in {"pace", "acceleration"}:
                boosted[attr] = _number(boosted, attr, 0.0) + 1
    return max(current, _ideal_score(boosted))


def _age_multiplier(age: float) -> float:
    if not np.isfinite(age):
        return 1.0
    if age < 19:
        return 1.20
    if age < 23:
        return 1.00
    if age < 27:
        return 0.72
    if age < 31:
        return 0.35
    return 0.15


def _historical_slope(uid, position: str, history: list[pd.DataFrame]) -> float | None:
    points = []
    column = f"{position}_rating"
    for frame in history:
        if column not in frame or "ID" not in frame:
            continue
        matches = frame[frame["ID"].astype(str) == str(uid)]
        for _, row in matches.iterrows():
            age = _number(row, "Age")
            rating = _number(row, column)
            if np.isfinite(age) and np.isfinite(rating):
                points.append((age, rating))
    if len(points) < 2:
        return None
    x = np.asarray([p[0] for p in points])
    y = np.asarray([p[1] for p in points])
    slope = float(np.polyfit(x, y, 1)[0])
    return float(np.clip(slope, -2.0, 4.0))


def _club_development_effects(history: list[pd.DataFrame], prior_strength: float = 5.0) -> dict[str, float]:
    """Estimate a shrunken club effect from observed rating changes.

    This is deliberately a pooled effect, not a separate model per club. A
    club with few player-period observations is pulled toward the overall
    development rate, which prevents small clubs from producing extreme
    projections.
    """
    dated = []
    for frame in history:
        if not {"ID", "Club", "Current Rating", "Date"}.issubset(frame.columns):
            continue
        date_value = pd.to_datetime(frame["Date"], errors="coerce").dropna()
        if date_value.empty:
            continue
        dated.append((date_value.min(), frame[["ID", "Club", "Current Rating"]].copy()))
    dated.sort(key=lambda item: item[0])
    observations = []
    for (old_date, old), (new_date, new) in zip(dated, dated[1:]):
        years = (new_date - old_date).days / 365.25
        if years <= 0:
            continue
        old = old.drop_duplicates("ID").rename(columns={"Current Rating": "old_rating", "Club": "old_club"})
        new = new.drop_duplicates("ID").rename(columns={"Current Rating": "new_rating"})
        merged = old.merge(new[["ID", "new_rating"]], on="ID", how="inner")
        merged["old_rating"] = pd.to_numeric(merged["old_rating"], errors="coerce")
        merged["new_rating"] = pd.to_numeric(merged["new_rating"], errors="coerce")
        merged["rate"] = (merged["new_rating"] - merged["old_rating"]) / years
        observations.append(merged[["old_club", "rate"]].rename(columns={"old_club": "Club"}))
    if not observations:
        return {}
    points = pd.concat(observations, ignore_index=True)
    points = points[points["Club"].notna() & points["Club"].astype(str).ne("") & points["rate"].between(-10, 10)]
    if points.empty:
        return {}
    global_rate = float(points["rate"].mean())
    grouped = points.groupby("Club")["rate"].agg(["mean", "count"])
    effects = ((grouped["mean"] - global_rate) * grouped["count"] / (grouped["count"] + prior_strength)).clip(-1.0, 1.0)
    return {str(club): float(effect) for club, effect in effects.items()}


def add_projection_metrics(df: pd.DataFrame, history: list[pd.DataFrame] | None = None) -> pd.DataFrame:
    out = df.copy()
    history = history or []
    historical_ids = {str(value) for frame in history if "ID" in frame for value in frame["ID"].dropna().unique()}
    current = pd.to_numeric(out.get("Current Rating", pd.Series(0.0, index=out.index)), errors="coerce").fillna(0)
    age = pd.to_numeric(out.get("Age", pd.Series(np.nan, index=out.index)), errors="coerce")
    ca = pd.to_numeric(out.get("Current Ability", pd.Series(np.nan, index=out.index)), errors="coerce")
    pa = pd.to_numeric(out.get("Potential Ability", pd.Series(np.nan, index=out.index)), errors="coerce")
    multiplier = pd.Series(np.select([age < 19, age < 23, age < 27, age < 31], [1.20, 1.00, 0.72, 0.35], default=0.15), index=out.index)
    years = (28.5 - age).clip(lower=0).fillna(0)
    default_slope = pd.Series(np.select([age < 23, age < 28], [1.0, 0.5], default=0.1), index=out.index)
    club_effects = _club_development_effects(history)
    club_effect = out["Club"].astype(str).map(club_effects).fillna(0.0) if "Club" in out else pd.Series(0.0, index=out.index)
    slopes = {}
    if history and "ID" in out:
        frames = [frame[[c for c in ["ID", "Age", "Current Rating"] if c in frame]] for frame in history if {"ID", "Age", "Current Rating"}.issubset(frame.columns)]
        if frames:
            points = pd.concat(frames, ignore_index=True)
            points["Age"] = pd.to_numeric(points["Age"], errors="coerce")
            points["Current Rating"] = pd.to_numeric(points["Current Rating"], errors="coerce")
            for uid, group in points.dropna().groupby("ID"):
                if len(group) >= 2 and group["Age"].nunique() >= 2:
                    slopes[str(uid)] = float(np.clip(np.polyfit(group["Age"], group["Current Rating"], 1)[0], -2.0, 4.0))
    observed = out["ID"].astype(str).map(slopes) if "ID" in out else pd.Series(np.nan, index=out.index)
    # Use the club effect for players without an individual history. Once a
    # player has enough observations, their own slope is stronger evidence.
    slope = observed.where(observed.notna(), default_slope + club_effect)
    trend = current + (slope * multiplier * years)
    pa_ceiling = current + ((pa - ca).clip(lower=0) / 2.0).fillna(0)
    potential = pd.concat([trend, pa_ceiling], axis=1).min(axis=1).clip(lower=current, upper=100).round(2)
    for position in POSITIONS:
        column = f"{position}_rating"
        if column in out:
            out[f"{position}_proj_peak"] = potential.where(pd.to_numeric(out[column], errors="coerce").notna())
    out["Potential Rating"] = potential
    out["Potential Gap"] = (potential - current).round(2)
    out["Club Development Effect"] = club_effect.round(3)
    return out
    for position in ["GK", "SW", "DL", "DC", "DR", "DM", "ML", "MC", "MR", "WBL", "WBR", "AML", "AMC", "AMR", "ST"]:
        column = f"{position}_rating"
        if column not in out:
            continue
        current = pd.to_numeric(out[column], errors="coerce")
        if position == "GK":
            potential = current.copy()
        else:
            potential = current.copy()
            for index, row in out.iterrows():
                value = current.loc[index]
                if pd.isna(value):
                    continue
                age = _number(row, "Age")
                peak_age = PEAK_AGE.get(position, DEFAULT_PEAK_AGE)
                slope = _historical_slope(row.get("ID"), position, history) if str(row.get("ID")) in historical_ids else None
                if slope is None:
                    slope = 1.0 if np.isfinite(age) and age < 23 else (0.5 if np.isfinite(age) and age < 28 else 0.1)
                years = max(0.0, peak_age - age) if np.isfinite(age) else 0.0
                trend = float(value) + (slope * _age_multiplier(age) * years)
                attr_peak = _attribute_peak(row, float(value))
                ca = _number(row, "Current Ability")
                pa = _number(row, "Potential Ability")
                if np.isfinite(ca) and np.isfinite(pa) and pa > ca:
                    pa_ceiling = float(value) + ((pa - ca) / 2.0)
                    trend = min(trend, pa_ceiling)
                potential.loc[index] = max(float(value), min(100.0, trend, max(attr_peak, float(value))))
        out[f"{position}_proj_peak"] = potential.round(2)
    potential_cols = [f"{p}_proj_peak" for p in ["GK", "SW", "DL", "DC", "DR", "DM", "ML", "MC", "MR", "WBL", "WBR", "AML", "AMC", "AMR", "ST"] if f"{p}_proj_peak" in out]
    current_cols = [f"{p}_rating" for p in ["GK", "SW", "DL", "DC", "DR", "DM", "ML", "MC", "MR", "WBL", "WBR", "AML", "AMC", "AMR", "ST"] if f"{p}_rating" in out]
    out["Potential Rating"] = out[potential_cols].apply(pd.to_numeric, errors="coerce").max(axis=1).fillna(out[current_cols].apply(pd.to_numeric, errors="coerce").max(axis=1)).round(2)
    out["Potential Gap"] = (out["Potential Rating"] - out["Current Rating"]).round(2)
    return out
