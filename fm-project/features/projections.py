import sys
import numpy as np
import pandas as pd
from pathlib import Path

# Add project root to path for absolute imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from features.ratings import (
    OUTFIELD_IDEAL_ATTRIBUTES,
    POSITION_WEIGHTS as RATING_POSITION_WEIGHTS,
    _calc_ideal_deficit_score,
)


AGE_BINS = [0, 20, 24, 28, 35, 60]

# FM forum/tool-tip prior ranges translated to position priors.
POSITION_PEAK_AGE_PRIORS = {
    "GK": 33.0,
    "DC": 30.0,
    "DL": 28.5,
    "DR": 28.5,
    "DML": 28.5,
    "DMR": 28.5,
    "DMC": 29.0,
    "MC": 29.0,
    "ML": 28.0,
    "MR": 28.0,
    "AML": 28.0,
    "AMR": 28.0,
    "AMC": 28.5,
    "ST": 28.5,
}

# Forum-informed personality effect proxy.
PERSONALITY_MULTIPLIER = {
    "Model Citizen": 1.14,
    "Model Professional": 1.12,
    "Professional": 1.09,
    "Perfectionist": 1.08,
    "Resolute": 1.06,
    "Driven": 1.05,
    "Fairly Professional": 1.03,
    "Fairly Determined": 1.02,
    "Balanced": 1.00,
    "Ambitious": 1.04,
    "Fairly Ambitious": 1.01,
    "Light-Hearted": 0.96,
    "Casual": 0.94,
    "Fairly Loyal": 0.99,
    "Temperamental": 0.95,
    "Low Determination": 0.92,
    "Slack": 0.91,
    "Unambitious": 0.90,
    "Fickle": 0.94,
    "Unprofessional": 0.88,
}

# Development nodes discussed in FM24 community tests:
# growth slows around 19 and drops more sharply around 27.
AGE_NODE_MULTIPLIERS = [
    (0.0, 18.99, 1.20),
    (19.0, 22.99, 1.00),
    (23.0, 26.99, 0.72),
    (27.0, 30.99, 0.35),
    (31.0, 60.0, 0.15),
]

# Empirical Bayes shrinkage strength: higher means more cohort pull.
SLOPE_SHRINKAGE_K = 5.0
CA_HIGH_ATTR_THRESHOLD = 16.0
CA_HIGH_ATTR_SURCHARGE = 0.60

CA_POSITION_ALIASES = {
    "WBL": "DML",
    "WBR": "DMR",
    "DM": "DMC",
    "SC": "ST",
}

PACE_ACC_POTENTIAL_BOOST_BY_AGE = {
    15: 7,
    16: 6,
    17: 4,
    18: 3,
    19: 1,
}

OTHER_OUTFIELD_POTENTIAL_BOOST_AGES = {15, 16}

NEGATIVE_PA_MIDPOINT = {
    -10: 190,
    -95: 180,
    -9: 170,
    -85: 160,
    -8: 150,
    -75: 140,
    -7: 130,
    -65: 120,
    -6: 110,
    -55: 100,
    -5: 90,
    -45: 80,
    -4: 70,
    -35: 60,
    -3: 50,
    -25: 40,
    -2: 30,
    -15: 20,
    -1: 15,
}


def _age_bin(age: float) -> str:
    if pd.isna(age):
        return "unknown"
    for i in range(len(AGE_BINS) - 1):
        if AGE_BINS[i] <= age < AGE_BINS[i + 1]:
            return f"{AGE_BINS[i]}-{AGE_BINS[i + 1] - 1}"
    return f"{AGE_BINS[-2]}+"


def _safe_ols_slope(x: np.ndarray, y: np.ndarray) -> float | None:
    if len(x) < 2:
        return None
    try:
        m = np.polyfit(x, y, 1)[0]
        if np.isfinite(m):
            return float(m)
    except Exception:
        return None
    return None


def _robust_player_slope(x: np.ndarray, y: np.ndarray) -> float | None:
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]
    if len(x) < 2:
        return None

    # Fast robustification: winsorize by quantiles then OLS.
    lo = float(np.quantile(y, 0.10))
    hi = float(np.quantile(y, 0.90))
    y_w = np.clip(y, lo, hi)
    return _safe_ols_slope(x, y_w)


def _age_node_multiplier(age: float) -> float:
    if pd.isna(age):
        return 1.0
    for start, end, mult in AGE_NODE_MULTIPLIERS:
        if start <= age <= end:
            return mult
    return 1.0


def _personality_multiplier(value: str | None) -> float:
    if not value:
        return 1.0
    mult = PERSONALITY_MULTIPLIER.get(str(value).strip(), 1.0)
    return float(np.clip(mult, 0.85, 1.15))


def _integrated_growth(
    current_age: float,
    peak_age: float,
    slope_per_year: float,
    max_step: float = 0.5,
) -> float:
    if pd.isna(current_age) or pd.isna(peak_age):
        return 0.0
    years_to_peak = max(0.0, float(peak_age) - float(current_age))
    if years_to_peak <= 0:
        return 0.0

    growth = 0.0
    n_steps = int(np.ceil(years_to_peak / max_step))
    for step in range(n_steps):
        a0 = float(current_age) + (step * max_step)
        a1 = min(float(current_age) + ((step + 1) * max_step), float(peak_age))
        dt = max(0.0, a1 - a0)
        if dt <= 0:
            continue
        local_age = 0.5 * (a0 + a1)
        growth += slope_per_year * _age_node_multiplier(local_age) * dt
    return growth


def _position_competency_factor(row: pd.Series, pos: str) -> float:
    # FM-Arena community adjustment approximation:
    # rating * (1 - (20 - role_score)/46)
    role_score = row.get(pos, np.nan)
    role_score = pd.to_numeric(role_score, errors="coerce")
    if pd.isna(role_score):
        return 1.0
    # In this dataset these columns are often 0/1 flags, not 1-20 role scores.
    # Ignore adjustment in that case to avoid suppressing projections.
    if float(role_score) in {0.0, 1.0}:
        return 1.0
    role_score = float(np.clip(role_score, 1.0, 20.0))
    return float(max(0.0, 1.0 - ((20.0 - role_score) / 46.0)))


def _residual_sigma(x: np.ndarray, y: np.ndarray, slope: float | None) -> float:
    if slope is None or len(x) < 3:
        return 0.0
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    intercept = float(np.median(y - (slope * x)))
    residuals = y - (intercept + (slope * x))
    mad = np.median(np.abs(residuals - np.median(residuals)))
    sigma = 1.4826 * mad
    if not np.isfinite(sigma):
        return 0.0
    return float(max(0.0, sigma))


def _normalized_pa(value) -> float | None:
    pa = pd.to_numeric(value, errors="coerce")
    if pd.isna(pa):
        return None
    pa_i = int(round(float(pa)))
    if pa_i > 0:
        return float(np.clip(pa_i, 1, 200))
    return float(NEGATIVE_PA_MIDPOINT.get(pa_i)) if pa_i in NEGATIVE_PA_MIDPOINT else None


def _extract_playable_positions(latest_row: pd.Series) -> list[str]:
    positions_raw = latest_row.get("Positions", [])
    if isinstance(positions_raw, str):
        positions_raw = [p.strip() for p in positions_raw.split(",") if p.strip()]
    if not isinstance(positions_raw, list):
        positions_raw = []

    out = []
    for pos in positions_raw:
        mapped = CA_POSITION_ALIASES.get(pos, pos)
        if mapped in RATING_POSITION_WEIGHTS:
            out.append(mapped)
    if out:
        return sorted(set(out))

    # Fallback: infer from populated position ratings if positions list is unavailable.
    inferred = []
    for pos in RATING_POSITION_WEIGHTS:
        val = pd.to_numeric(latest_row.get(f"{pos}_rating"), errors="coerce")
        if pd.notna(val):
            inferred.append(pos)
    return sorted(set(inferred))


def _rca_weight_profile(latest_row: pd.Series) -> dict[str, float]:
    playable_positions = _extract_playable_positions(latest_row)
    if not playable_positions:
        playable_positions = ["MC"]

    # Approximation used by CAE/FMScout notes for multiposition players:
    # per attribute, use the highest positional weight among natural positions.
    profile: dict[str, float] = {}
    for pos in playable_positions:
        for attr, weight in RATING_POSITION_WEIGHTS.get(pos, {}).items():
            current = profile.get(attr, 0.0)
            if weight > current:
                profile[attr] = float(weight)
    return profile


def _estimate_current_ca(latest_row: pd.Series, positions) -> float | None:
    ca_direct = pd.to_numeric(latest_row.get("CA"), errors="coerce")
    if pd.notna(ca_direct):
        return float(np.clip(ca_direct, 1, 200))

    weight_profile = _rca_weight_profile(latest_row)
    if not weight_profile:
        return None

    total_weight = float(sum(weight_profile.values()))
    if total_weight <= 0:
        return None

    weighted_attr_sum = 0.0
    high_attr_surcharge = 0.0
    for attr, weight in weight_profile.items():
        val = pd.to_numeric(latest_row.get(attr), errors="coerce")
        if pd.isna(val):
            continue
        v = float(np.clip(val, 1.0, 20.0))
        weighted_attr_sum += v * weight
        if v > CA_HIGH_ATTR_THRESHOLD:
            high_attr_surcharge += ((v - CA_HIGH_ATTR_THRESHOLD) ** 2) * (weight / total_weight)

    avg_attr = weighted_attr_sum / total_weight
    # FM Scout CA guide approximation: CA ~= 20*x - 120 (x = weighted average attribute).
    ca_linear = (20.0 * avg_attr) - 120.0
    ca_est = ca_linear + (CA_HIGH_ATTR_SURCHARGE * high_attr_surcharge)
    return float(np.clip(ca_est, 1, 200))


def _boosted_outfield_row_for_potential(row: pd.Series) -> pd.Series:
    boosted = row.copy()
    age = pd.to_numeric(row.get("Age", row.get("Age_int")), errors="coerce")
    if pd.isna(age):
        return boosted

    age_year = int(age)
    pace_acc_boost = PACE_ACC_POTENTIAL_BOOST_BY_AGE.get(age_year, 0)
    for attr in ["Pac", "Acc"]:
        boosted[attr] = pd.to_numeric(boosted.get(attr, 0), errors="coerce")
        if pd.isna(boosted[attr]):
            boosted[attr] = 0
        boosted[attr] = boosted[attr] + pace_acc_boost

    if age_year in OTHER_OUTFIELD_POTENTIAL_BOOST_AGES:
        for attr in OUTFIELD_IDEAL_ATTRIBUTES:
            if attr in {"Pac", "Acc"}:
                continue
            boosted[attr] = pd.to_numeric(boosted.get(attr, 0), errors="coerce")
            if pd.isna(boosted[attr]):
                boosted[attr] = 0
            boosted[attr] = boosted[attr] + 1

    return boosted


def add_projection_metrics(df: pd.DataFrame, positions) -> pd.DataFrame:
    rating_cols = [f"{p}_rating" for p in positions if f"{p}_rating" in df.columns]
    if not rating_cols:
        return df

    df = df.copy()
    uid_latest = df.sort_values("Date").groupby("UID").tail(1).copy()

    uid_ca_est: dict[str, float] = {}
    uid_pa_norm: dict[str, float] = {}
    for _, row in uid_latest.iterrows():
        uid = row.get("UID")
        uid_ca_est[uid] = _estimate_current_ca(row, positions)
        uid_pa_norm[uid] = _normalized_pa(row.get("PA"))

    df["CA_est"] = df["UID"].map(uid_ca_est)
    df["PA_norm"] = df["UID"].map(uid_pa_norm)

    for pos in positions:
        col = f"{pos}_rating"
        if col not in df.columns:
            continue

        if pos == "GK":
            df[f"{pos}_proj_peak"] = df[col]
        else:
            df[f"{pos}_proj_peak"] = df.apply(
                lambda r: _calc_ideal_deficit_score(
                    _boosted_outfield_row_for_potential(r),
                    OUTFIELD_IDEAL_ATTRIBUTES,
                )
                if pd.notna(pd.to_numeric(r.get(col), errors="coerce"))
                else np.nan,
                axis=1,
            )

        df[f"{pos}_proj_peak_age"] = df["Age"]
        df[f"{pos}_proj_low"] = df[[col, f"{pos}_proj_peak"]].min(axis=1)
        df[f"{pos}_proj_high"] = df[[col, f"{pos}_proj_peak"]].max(axis=1)
        df[f"{pos}_proj_source"] = "age_attribute_boost"
        df[f"{pos}_proj_points"] = df.groupby("UID")["UID"].transform("count")

    return df

    # Estimate peak age per position from historical max ratings and blend with priors.
    peak_age_by_pos: dict[str, float] = {}
    for pos in positions:
        col = f"{pos}_rating"
        if col not in df.columns:
            continue
        peaks = (
            df[df[col] > 0]
              .sort_values(["UID", col])
              .groupby("UID")
              .tail(1)
        )
        ages = peaks["Age"].dropna()
        data_peak = float(ages.median()) if not ages.empty else None
        prior_peak = POSITION_PEAK_AGE_PRIORS.get(pos, 27.0)
        if data_peak is None:
            peak_age_by_pos[pos] = prior_peak
        else:
            # More shrinkage to prior when data is thin.
            n = int(len(ages))
            w = float(n / (n + 100))
            peak_age_by_pos[pos] = float((w * data_peak) + ((1 - w) * prior_peak))

    # Build position/age-bin robust slopes for fallback and shrinkage target.
    slope_lookup: dict[str, dict[str, float]] = {}
    slope_std_lookup: dict[str, dict[str, float]] = {}
    global_slope_lookup: dict[str, float] = {}
    for pos in positions:
        col = f"{pos}_rating"
        if col not in df.columns:
            continue
        slopes: dict[str, list[float]] = {}
        all_slopes: list[float] = []
        for uid, group in df[df[col] > 0].groupby("UID"):
            x = group["Age"].to_numpy()
            y = group[col].to_numpy()
            m = _robust_player_slope(x, y)
            if m is None:
                continue
            age_bin = _age_bin(group["Age"].max())
            slopes.setdefault(age_bin, []).append(m)
            all_slopes.append(m)
        slope_lookup[pos] = {
            k: float(np.median(v)) for k, v in slopes.items() if v
        }
        slope_std_lookup[pos] = {
            k: float(np.std(v)) for k, v in slopes.items() if v
        }
        global_slope_lookup[pos] = float(np.median(all_slopes)) if all_slopes else 0.0

    # Determination influence is a secondary modifier.
    det_available = "Det" in df.columns

    uid_history = {uid: g.sort_values("Date") for uid, g in df.groupby("UID")}

    for pos in positions:
        col = f"{pos}_rating"
        if col not in df.columns:
            continue

        peak_age = peak_age_by_pos.get(pos, 27.0)
        fallback_by_age = slope_lookup.get(pos, {})
        fallback_std_by_age = slope_std_lookup.get(pos, {})
        fallback_global = global_slope_lookup.get(pos, 0.0)

        per_uid_proj: dict[str, float] = {}
        per_uid_peak_age: dict[str, float] = {}
        per_uid_low: dict[str, float] = {}
        per_uid_high: dict[str, float] = {}
        per_uid_source: dict[str, str] = {}
        per_uid_points: dict[str, int] = {}

        # Only process players that have a rating in this position.
        eligible_uids = df.loc[df[col] > 0, "UID"].dropna().unique().tolist()
        for uid in eligible_uids:
            group = uid_history.get(uid)
            if group is None:
                continue
            latest = group.iloc[-1]
            current_age = latest.get("Age", np.nan)
            current_rating = latest.get(col, np.nan)

            if pd.isna(current_rating) or current_rating <= 0:
                per_uid_proj[uid] = np.nan
                per_uid_peak_age[uid] = np.nan
                per_uid_low[uid] = np.nan
                per_uid_high[uid] = np.nan
                per_uid_source[uid] = "no_rating"
                per_uid_points[uid] = int(len(group))
                continue

            g_pos = group[group[col] > 0]
            x = g_pos["Age"].to_numpy()
            y = g_pos[col].to_numpy()
            n_points = int(np.sum(np.isfinite(x) & np.isfinite(y)))

            # 1) robust player trend
            player_slope = _robust_player_slope(x, y)
            source = "player_robust"
            if player_slope is None:
                age_bin = _age_bin(current_age)
                player_slope = fallback_by_age.get(age_bin, fallback_global)
                source = "cohort_robust"

            # 2) empirical Bayes shrinkage to cohort slope
            age_bin = _age_bin(current_age)
            cohort_slope = fallback_by_age.get(age_bin, fallback_global)
            w_player = float(n_points / (n_points + SLOPE_SHRINKAGE_K))
            m = (w_player * float(player_slope)) + ((1.0 - w_player) * float(cohort_slope))
            if source == "player_robust":
                source = "player_robust_shrunk"
            else:
                source = "cohort_robust_shrunk"

            # 3) forum-informed drivers (smaller than trend signal)
            if det_available and pd.notna(latest.get("Det")):
                det = float(latest["Det"])
                m = m * (1.0 + ((det - 10.0) / 60.0))

            m = m * _personality_multiplier(latest.get("Personality"))

            # 4) integrate age curve to peak rather than single multiplier
            growth_to_peak = _integrated_growth(current_age, peak_age, m)
            projected = float(current_rating) + growth_to_peak

            # Apply positional familiarity factor only when a true 1-20 role score exists.
            pos_factor = _position_competency_factor(latest, pos)
            projected *= pos_factor
            current_floor = float(current_rating) * pos_factor

            projected = min(100.0, max(current_floor, projected))

            # 4b) Blend with CA->PA potential and apply PA-informed ceiling when available.
            ca_est = uid_ca_est.get(uid)
            pa_norm = uid_pa_norm.get(uid)
            if ca_est is not None and pa_norm is not None:
                ca_gap = max(0.0, float(pa_norm) - float(ca_est))
                max_gain_from_gap = ca_gap / 2.0
                best_rating = max(1.0, float(uid_max_rating.get(uid, current_rating)))
                pos_alignment = float(np.clip(float(current_rating) / best_rating, 0.35, 1.0))
                pa_ceiling = min(100.0, float(current_rating) + (max_gain_from_gap * pos_alignment))

                # Younger players should realize more of the gap by peak age.
                years_to_peak = max(0.0, float(peak_age) - float(current_age))
                dev_window = float(np.clip(years_to_peak / 8.0, 0.0, 1.0))
                pa_target = float(current_rating) + (max_gain_from_gap * pos_alignment * dev_window)

                # Trust trend more as player history points increase.
                w_hist = float(n_points / (n_points + 4.0))
                projected = (w_hist * projected) + ((1.0 - w_hist) * pa_target)
                projected = min(projected, pa_ceiling, float(pa_norm) / 2.0)
                projected = max(current_floor, projected)
                source = f"{source}_pa_blend"

            # 5) uncertainty from both player residual dispersion and cohort trend volatility.
            years_to_peak = max(0.0, float(peak_age) - float(current_age))
            slope_std = float(fallback_std_by_age.get(age_bin, 0.0))
            resid_sigma = _residual_sigma(x, y, player_slope)
            uncertainty = float(np.sqrt((resid_sigma ** 2) + ((slope_std * years_to_peak) ** 2)))
            band = 1.28 * uncertainty  # ~80% band
            if ca_est is not None and pa_norm is not None:
                gap_factor = float(np.clip(0.70 + ((pa_norm - ca_est) / 120.0), 0.70, 1.30))
                band *= gap_factor
            low = max(current_floor, projected - band)
            high = min(100.0, projected + band)

            per_uid_proj[uid] = projected
            per_uid_peak_age[uid] = peak_age
            per_uid_low[uid] = low
            per_uid_high[uid] = high
            per_uid_source[uid] = source
            per_uid_points[uid] = n_points

        df[f"{pos}_proj_peak"] = df["UID"].map(per_uid_proj)
        df[f"{pos}_proj_peak_age"] = df["UID"].map(per_uid_peak_age)
        df[f"{pos}_proj_low"] = df["UID"].map(per_uid_low)
        df[f"{pos}_proj_high"] = df["UID"].map(per_uid_high)
        df[f"{pos}_proj_source"] = df["UID"].map(per_uid_source)
        df[f"{pos}_proj_points"] = df["UID"].map(per_uid_points)

    return df
