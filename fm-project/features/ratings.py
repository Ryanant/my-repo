import numpy as np
import pandas as pd

# FM attributes are typically 1-20. GK ratings are normalized to 0-100.
ATTRIBUTE_MAX = 20

# Outfield ratings are scored as raw deltas against this ideal profile.
# Any missing threshold points produce a negative score. Surplus only counts
# once every threshold has been met.
OUTFIELD_IDEAL_ATTRIBUTES = {
    "Pac": 18,
    "Acc": 18,
    "Jum": 10,
    "Dri": 10,
    "Bal": 10,
    "Wor": 10,
    "Ant": 10,
    "Agi": 6,
    "Cnt": 6,
    "Sta": 6,
}

# ------------------------------------------------------------------
# FM-Arena coefficients (thread 14201, page 1)
# Source positions are mapped to this app's position codes:
# DLR -> DL/DR, WBLR -> DML/DMR, MLR -> ML/MR, AMLR -> AML/AMR, STC -> ST
# ------------------------------------------------------------------

GK_WEIGHTS = {
    "Agi": 0.014640,
    "Ref": 0.012837,
    "Aer": 0.011812,
    "Thr": 0.007465,
    "Com": 0.007436,
    "Han": 0.006255,
    "Dec": 0.005089,
    "TRO": -0.003310,
}

DLR_WEIGHTS = {
    "Pac": 0.018991,
    "Jum": 0.014582,
    "Acc": 0.012670,
    "Ant": 0.012269,
    "Cnt": 0.009911,
    "Dri": 0.008246,
    "Cmp": 0.007720,
    "Cro": 0.006812,
}

DC_WEIGHTS = {
    "Jum": 0.022608,
    "Pac": 0.015882,
    "Acc": 0.013536,
    "Wor": 0.010819,
    "Ant": 0.010326,
    "Pos_x": 0.008864,
    "Pas": 0.008826,
    "Cnt": 0.008358,
}

WBLR_WEIGHTS = {
    "Pac": 0.019196,
    "Acc": 0.018585,
    "Jum": 0.013761,
    "Cmp": 0.011762,
    "Vis": 0.010025,
    "Cro": 0.009596,
    "Wor": 0.008166,
    "Det": 0.005121,
}

DMC_WEIGHTS = {
    "Acc": 0.020572,
    "Ant": 0.013047,
    "Sta": 0.010352,
    "Jum": 0.009796,
    "Cmp": 0.009470,
    "Pas": 0.009114,
    "Lon": 0.007952,
    "Dri": 0.007338,
}

MLR_WEIGHTS = {
    "Pac": 0.020497,
    "Dri": 0.014018,
    "Acc": 0.012883,
    "Cmp": 0.012072,
    "Vis": 0.011542,
    "Jum": 0.011150,
    "Cro": 0.010598,
    "Sta": 0.009658,
}

MC_WEIGHTS = {
    "Ant": 0.014011,
    "Acc": 0.012595,
    "Cmp": 0.012589,
    "Pac": 0.012156,
    "Cro": 0.010100,
    "Dri": 0.008134,
    "Jum": 0.007918,
    "Str": 0.006528,
}

AMLR_WEIGHTS = {
    "Pac": 0.023458,
    "Acc": 0.019640,
    "Ant": 0.015160,
    "Cro": 0.014857,
    "Dri": 0.013533,
    "Jum": 0.013029,
    "Tec": 0.012662,
    "Cmp": 0.012295,
}

AMC_WEIGHTS = {
    "Pac": 0.016763,
    "Acc": 0.016348,
    "Cnt": 0.013697,
    "Cmp": 0.012813,
    "Tec": 0.011647,
    "Lon": 0.009914,
    "Jum": 0.009524,
    "Dri": 0.008679,
}

STC_WEIGHTS = {
    "Jum": 0.020557,
    "Pac": 0.020096,
    "Acc": 0.014496,
    "Cnt": 0.013675,
    "Bal": 0.012043,
    "Dri": 0.010739,
    "Vis": 0.009392,
    "Cmp": 0.009161,
}

# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------

def _calc_weighted_score(row: pd.Series, weights: dict[str, float]):
    """
    Compute weighted sum of attributes for one row based
    on provided weights. Attributes not present are treated as 0.
    """
    total = 0.0
    for attr, weight in weights.items():
        if attr == "Pos_x":
            value = row.get("Pos_x", row.get("Pos", 0))
        else:
            value = row.get(attr, 0)
        value = pd.to_numeric(value, errors="coerce")
        if pd.isna(value):
            value = 0
        total += float(value) * weight
    return total


def _calc_ideal_deficit_score(row: pd.Series, ideals: dict[str, float]) -> float:
    """
    Score outfield players by raw points away from the ideal attribute floors.

    If any attribute is below its threshold, return the negative total deficit.
    If all thresholds are met, return the total surplus above the thresholds.
    """
    if not ideals:
        return 0.0

    total_deficit = 0.0
    total_surplus = 0.0
    for attr, ideal in ideals.items():
        value = pd.to_numeric(row.get(attr, 0), errors="coerce")
        if pd.isna(value):
            value = 0
        ideal = float(ideal)
        if ideal <= 0:
            continue
        delta = float(value) - ideal
        if delta < 0:
            total_deficit += abs(delta)
        else:
            total_surplus += delta

    if total_deficit > 0:
        return -total_deficit
    return total_surplus


def _max_weighted_score(weights: dict[str, float]) -> float:
    return sum(abs(weight) * ATTRIBUTE_MAX for weight in weights.values())


def _player_can_play_pos(row: pd.Series, pos: str) -> bool:
    """
    Determines if a player is capable of playing a position
    based on the Positions list in the dataframe.
    Positions should be a Python list stored in 'Positions'.
    """
    return pos in row.get("Positions", [])


# ------------------------------------------------------------------
# Position mapping groups
# ------------------------------------------------------------------

# Direct mapping from app positions to FM-Arena coefficient sets.
POSITION_WEIGHTS = {
    "GK": GK_WEIGHTS,
    "DL": DLR_WEIGHTS,
    "DR": DLR_WEIGHTS,
    "DC": DC_WEIGHTS,
    "DML": WBLR_WEIGHTS,
    "DMR": WBLR_WEIGHTS,
    "DMC": DMC_WEIGHTS,
    "ML": MLR_WEIGHTS,
    "MR": MLR_WEIGHTS,
    "MC": MC_WEIGHTS,
    "AML": AMLR_WEIGHTS,
    "AMR": AMLR_WEIGHTS,
    "AMC": AMC_WEIGHTS,
    "ST": STC_WEIGHTS,
}

# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

def add_position_ratings(df: pd.DataFrame) -> pd.DataFrame:
    """
    Adds a weighted rating for every known position.
    If a player cannot play that position, rating is blank.
    """

    for pos, weights in POSITION_WEIGHTS.items():

        # Build column name
        colname = f"{pos}_rating"
        if pos == "GK":
            max_score = _max_weighted_score(weights)
            df[colname] = df.apply(
                lambda r: (_calc_weighted_score(r, weights) / max_score) * 100
                if _player_can_play_pos(r, pos) else np.nan,
                axis=1
            )
        else:
            df[colname] = df.apply(
                lambda r: _calc_ideal_deficit_score(r, OUTFIELD_IDEAL_ATTRIBUTES)
                if _player_can_play_pos(r, pos) else np.nan,
                axis=1
            )

    return df
