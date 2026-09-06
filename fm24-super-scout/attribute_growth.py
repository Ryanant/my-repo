"""Dated, per-attribute development forecasts.

The model predicts annual change in each attribute separately. It uses a
small ridge regression implemented with NumPy so the app remains lightweight.
Club development is included as a pooled, shrinkage-adjusted feature so a
player's forecast can benefit from the club's observed development record
without requiring a separate model for every club.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from projections import _club_development_effects

TECHNICAL = ("corners", "crossing", "dribbling", "finishing", "first_touch", "free_kick_taking", "heading", "long_shots", "long_throws", "marking", "passing", "penalty_taking", "tackling", "technique")
MENTAL = ("aggression", "anticipation", "bravery", "composure", "concentration", "decisions", "determination", "flair", "leadership", "off_the_ball", "positioning", "teamwork", "vision", "work_rate")
PHYSICAL = ("acceleration", "agility", "balance", "jumping_reach", "natural_fitness", "pace", "stamina", "strength")
GOALKEEPING = ("aerial_reach", "command_of_area", "communication", "eccentricity", "handling", "kicking", "one_on_ones", "punching", "reflexes", "rushing_out", "throwing")
PREDICTED_ATTRIBUTES = TECHNICAL + MENTAL + PHYSICAL + GOALKEEPING

MIN_TRAINING_ROWS = 20
FEATURE_NAMES = ("age", "age_squared", "professionalism", "headroom", "current_attribute", "current_rating", "is_goalkeeper", "club_effect")


def _numeric(row: pd.Series, name: str, default: float = 0.0) -> float:
    value = pd.to_numeric(row.get(name, default), errors="coerce")
    return float(value) if pd.notna(value) else default


def _features(row: pd.Series) -> list[float]:
    age = _numeric(row, "Age", 25.0)
    positions = row.get("Positions", [])
    if not isinstance(positions, (list, tuple, set)):
        positions = str(positions or "").split(",")
    return [
        age / 25.0,
        (age / 25.0) ** 2,
        _numeric(row, "Professionalism", 10.0) / 20.0,
        max(0.0, _numeric(row, "Potential Ability") - _numeric(row, "Current Ability")) / 200.0,
        0.0,
        _numeric(row, "Current Rating", 0.0) / 100.0,
        1.0 if "GK" in positions else 0.0,
        _numeric(row, "Club Development Effect", 0.0),
    ]


def _transition_rows(history: list[pd.DataFrame]) -> list[tuple[pd.Series, pd.Series, float]]:
    dated = []
    for frame in history:
        if "Date" not in frame or "ID" not in frame:
            continue
        dates = pd.to_datetime(frame["Date"], errors="coerce").dropna()
        if dates.empty:
            continue
        dated.append((dates.min(), frame.copy()))
    dated.sort(key=lambda item: item[0])
    transitions = []
    for (old_date, old), (new_date, new) in zip(dated, dated[1:]):
        years = (new_date - old_date).days / 365.25
        if years <= 0:
            continue
        old = old.drop_duplicates("ID").set_index("ID")
        new = new.drop_duplicates("ID").set_index("ID")
        for uid in old.index.intersection(new.index):
            transitions.append((old.loc[uid], new.loc[uid], years))
    return transitions


def _fit_models(history: list[pd.DataFrame]) -> dict[str, np.ndarray]:
    rows = _transition_rows(history)
    club_effects = _club_development_effects(history)
    models = {}
    for attribute in PREDICTED_ATTRIBUTES:
        design, target = [], []
        for old, new, years in rows:
            old_value = _numeric(old, attribute, np.nan)
            new_value = _numeric(new, attribute, np.nan)
            if not np.isfinite(old_value) or not np.isfinite(new_value):
                continue
            old = old.copy()
            old["Club Development Effect"] = club_effects.get(str(old.get("Club", "")), 0.0)
            features = _features(old)
            features[4] = old_value / 20.0
            design.append([1.0, *features])
            target.append((new_value - old_value) / years)
        if len(target) < MIN_TRAINING_ROWS:
            continue
        x = np.asarray(design, dtype=float)
        y = np.asarray(target, dtype=float)
        penalty = np.eye(x.shape[1], dtype=float) * 2.0
        penalty[0, 0] = 0.0
        beta = np.linalg.solve(x.T @ x + penalty, x.T @ y)
        models[attribute] = beta
    return models


def add_attribute_predictions(df: pd.DataFrame, history: list[pd.DataFrame] | None = None, horizon_years: float = 1.0) -> pd.DataFrame:
    """Add one-year predicted value and change for every visible attribute."""
    out = df.copy()
    history = history or []
    models = _fit_models(history)
    club_effects = _club_development_effects(history)
    trained = len(models)
    for attribute in PREDICTED_ATTRIBUTES:
        current = pd.to_numeric(out.get(attribute, pd.Series(np.nan, index=out.index)), errors="coerce")
        growth = pd.Series(0.0, index=out.index)
        if attribute in models:
            design = []
            for index, row in out.iterrows():
                row = row.copy()
                row["Club Development Effect"] = club_effects.get(str(row.get("Club", "")), 0.0)
                features = _features(row)
                features[4] = (current.loc[index] / 20.0) if pd.notna(current.loc[index]) else 0.0
                design.append([1.0, *features])
            growth = pd.Series(np.asarray(design) @ models[attribute] * horizon_years, index=out.index).clip(-3.0, 3.0).round(2)
        out[f"{attribute}_1y_growth"] = growth.where(current.notna())
        out[f"{attribute}_1y_pred"] = (current + growth).clip(1, 20).round(2)
    out["Attribute Models Trained"] = trained
    out["Attribute Forecast Status"] = "Trained" if trained else "Collecting dated history"
    return out
