from __future__ import annotations

import json
import re
from pathlib import Path
import pandas as pd

from config import EXPORT_HISTORY_FILE, SNAPSHOT_DIR, SHORTLIST_FILE
from attribute_growth import PREDICTED_ATTRIBUTES, add_attribute_predictions
from projections import add_projection_metrics
from ratings import add_prediction_metrics, add_ratings

_LATEST_CACHE_KEY = None
_LATEST_CACHE = None
_HISTORY_CACHE_KEY = None
_HISTORY_CACHE = None
_EXPORT_CACHE_KEY = None
_EXPORT_CACHE = None
_SNAPSHOT_CACHE: dict[tuple[str, int, int], pd.DataFrame] = {}

SCHEDULED_MONTHS = {1, 4, 7, 10}

ATTRIBUTE_ALIASES = {
    "corners": "Cor", "crossing": "Cro", "dribbling": "Dri", "finishing": "Fin", "first_touch": "Fir", "free_kick_taking": "Fre", "heading": "Hea", "long_shots": "Lon", "long_throws": "L Th", "marking": "Mar",
    "penalty_taking": "Pen",
    "passing": "Pas", "tackling": "Tck", "technique": "Tec", "vision": "Vis",
    "aggression": "Agg", "anticipation": "Ant", "bravery": "Bra", "decisions": "Dec", "determination": "Det", "flair": "Fla", "leadership": "Ldr", "off_the_ball": "OtB", "positioning": "Pos", "teamwork": "Tea", "work_rate": "Wor", "composure": "Cmp", "concentration": "Cnt",
    "acceleration": "Acc", "strength": "Str", "stamina": "Sta", "pace": "Pac", "agility": "Agi", "balance": "Bal", "jumping_reach": "Jum", "natural_fitness": "Nat",
    "handling": "Han", "aerial_reach": "Aer", "command_of_area": "Cmd", "communication": "Com", "kicking": "Kic", "one_on_ones": "1v1", "reflexes": "Ref", "throwing": "Thr", "eccentricity": "Ecc", "rushing_out": "TRO", "punching": "Pun",
}


def _positions(value) -> list[str]:
    if isinstance(value, list):
        return [str(x).upper() for x in value]
    text = str(value or "").upper().replace("WB", "D").replace("DM", "DM")
    found = re.findall(r"(?:GK|D[LMR]?|DM[CR]?|M[CLMR]?|AM[CLR]?|ST)", text)
    return list(dict.fromkeys(found))


def _read_file(path: Path) -> pd.DataFrame:
    if path.suffix.lower() in {".html", ".htm"}:
        tables = pd.read_html(path)
        return max(tables, key=len)
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            game_date = payload.get("Game Date") or payload.get("game_date")
            payload = payload.get("players", payload.get("data", payload))
        else:
            game_date = None
        frame = pd.DataFrame(payload)
        if game_date and "Date" not in frame:
            frame["Date"] = game_date
        return frame
    return pd.read_csv(path)


def _calculate_age(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate a fractional current age from the snapshot's game date."""
    if "Age" in df and df["Age"].notna().any():
        return df
    if "Date" not in df or "DoB" not in df:
        return df
    game_dates = pd.to_datetime(df["Date"], errors="coerce")
    birth_dates = pd.to_datetime(df["DoB"], errors="coerce")
    valid = game_dates.notna() & birth_dates.notna()
    if not valid.any():
        return df
    out = df.copy()
    out["Age"] = ((game_dates - birth_dates).dt.days / 365.25).where(valid).round(4)
    return out


def _snapshot_date(df: pd.DataFrame):
    if "Date" not in df:
        return None
    dates = pd.to_datetime(df["Date"], errors="coerce").dropna()
    return dates.min() if not dates.empty else None


def _memory_archives() -> list[Path]:
    return sorted(
        (path for path in SNAPSHOT_DIR.glob("fm24-memory-*.json") if path.is_file()),
        key=lambda path: path.stat().st_mtime_ns,
    )


def _memory_current() -> Path:
    return SNAPSHOT_DIR / "fm24-memory.json"


def _raw_snapshot_date(path: Path):
    """Read only the date metadata without running the expensive enrichers."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            value = payload.get("Game Date") or payload.get("game_date")
            if value:
                return pd.to_datetime(value, errors="coerce")
            payload = payload.get("players", payload.get("data", []))
        if isinstance(payload, list) and payload:
            value = payload[0].get("Date") if isinstance(payload[0], dict) else None
            return pd.to_datetime(value, errors="coerce")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass
    return pd.NaT


def _export_history() -> pd.DataFrame:
    global _EXPORT_CACHE_KEY, _EXPORT_CACHE
    if not EXPORT_HISTORY_FILE.exists():
        return pd.DataFrame()
    signature = (str(EXPORT_HISTORY_FILE), EXPORT_HISTORY_FILE.stat().st_mtime_ns, EXPORT_HISTORY_FILE.stat().st_size)
    if signature == _EXPORT_CACHE_KEY and _EXPORT_CACHE is not None:
        return _EXPORT_CACHE.copy()
    frame = pd.read_csv(EXPORT_HISTORY_FILE)
    if "UID" in frame and "ID" not in frame:
        frame.rename(columns={"UID": "ID"}, inplace=True)
    if "Date" in frame:
        frame["Date"] = pd.to_datetime(frame["Date"], errors="coerce")
    _EXPORT_CACHE_KEY, _EXPORT_CACHE = signature, frame
    return frame.copy()


def _enrich_current_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Fill memory-only gaps from the user's existing FM export history."""
    export = _export_history()
    if export.empty or "ID" not in df or "ID" not in export:
        return df
    out = df.copy()
    lookup = export.drop_duplicates("ID", keep="last").set_index("ID")
    ids = out["ID"]
    for column in ("Age", "DoB", "Personality"):
        if column not in lookup:
            continue
        values = ids.map(lookup[column])
        if column not in out:
            out[column] = values
        else:
            out[column] = out[column].where(out[column].notna(), values)
    return out


def load_snapshot(source: str | Path) -> pd.DataFrame:
    path = Path(source)
    stat = path.stat()
    cache_key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _SNAPSHOT_CACHE.get(cache_key)
    if cached is not None:
        return cached.copy()
    df = _read_file(path).copy()
    aliases = {"CA": "Current Ability", "PA": "Potential Ability", "UID": "ID", "Club Name": "Club", "Prof": "Professionalism"}
    attribute_aliases = {value: key for key, value in ATTRIBUTE_ALIASES.items()}
    aliases.update({key: value for key, value in attribute_aliases.items() if key in df.columns and value not in df.columns})
    df.rename(columns={k: v for k, v in aliases.items() if k in df.columns}, inplace=True)
    for col in ("Name", "Club", "Position"):
        if col not in df:
            df[col] = ""
    df["Positions"] = df["Positions"].map(_positions) if "Positions" in df else df["Position"].map(_positions)
    for col in ("Age", "Current Ability", "Potential Ability", "Value"):
        if col in df:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(r"[^0-9.-]", "", regex=True), errors="coerce")
    if "Date" in df:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = _enrich_current_fields(df)
    df = _calculate_age(df)
    enriched = add_metrics(df)
    _SNAPSHOT_CACHE[cache_key] = enriched
    if len(_SNAPSHOT_CACHE) > 8:
        del _SNAPSHOT_CACHE[next(iter(_SNAPSHOT_CACHE))]
    return enriched.copy()


def add_metrics(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "Positions" not in out and "Position" in out:
        out["Positions"] = out["Position"].map(_positions)
    elif "Positions" in out:
        out["Positions"] = out["Positions"].map(_positions)
    out = add_ratings(out)
    out["Scout Score"] = out["Current Rating"]
    out = add_prediction_metrics(out)
    if "ID" not in out:
        out["ID"] = out["Name"].astype(str)
    return out


def load_latest() -> pd.DataFrame:
    current_path = _memory_current()
    archives = _memory_archives()
    if not current_path.exists() and not archives:
        return pd.DataFrame()
    latest_path = current_path if current_path.exists() else archives[-1]
    latest_date = _raw_snapshot_date(latest_path)
    previous_path = None
    # A memory dump keeps both the authoritative current file and a dated
    # archive. Do not compare those identical files; find the latest archive
    # from a genuinely earlier in-game date instead.
    for candidate in reversed(archives):
        if candidate == latest_path:
            continue
        candidate_date = _raw_snapshot_date(candidate)
        if pd.isna(latest_date):
            previous_path = candidate
            break
        if not pd.isna(candidate_date) and candidate_date.normalize() != latest_date.normalize():
            previous_path = candidate
            break
    paths = [path for path in (latest_path, previous_path) if path is not None]
    signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
    global _LATEST_CACHE_KEY, _LATEST_CACHE
    if signature == _LATEST_CACHE_KEY and _LATEST_CACHE is not None:
        return _LATEST_CACHE.copy()
    latest = load_snapshot(latest_path)
    previous = load_snapshot(previous_path) if previous_path is not None else None
    dated_history = [frame for path, frame in load_history(include_current=False) if path != latest_path]
    projection_history = dated_history or ([previous] if previous is not None else [])
    if EXPORT_HISTORY_FILE.exists():
        projection_history.append(load_snapshot(EXPORT_HISTORY_FILE))
    latest = add_attribute_predictions(latest, dated_history)
    latest = add_projection_metrics(latest, projection_history)
    _LATEST_CACHE_KEY = signature
    _LATEST_CACHE = growth(latest, previous)
    return _LATEST_CACHE.copy()


def load_history(include_current: bool = True) -> list[tuple[Path, pd.DataFrame]]:
    files = _memory_archives()
    export_signature = None
    export = _export_history()
    if EXPORT_HISTORY_FILE.exists():
        export_signature = (str(EXPORT_HISTORY_FILE), EXPORT_HISTORY_FILE.stat().st_mtime_ns, EXPORT_HISTORY_FILE.stat().st_size)
    signature = (include_current, tuple(sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files)), export_signature)
    global _HISTORY_CACHE_KEY, _HISTORY_CACHE
    if signature == _HISTORY_CACHE_KEY and _HISTORY_CACHE is not None:
        return [(path, frame.copy()) for path, frame in _HISTORY_CACHE]
    entries = []
    current_date = _raw_snapshot_date(SNAPSHOT_DIR / "fm24-memory.json") if include_current else pd.NaT
    for path in files:
        # Most archives are interim captures. Read their lightweight date
        # metadata first, and only run the full dataframe enrichment for a
        # scheduled archive that belongs in the development history.
        path_date = _raw_snapshot_date(path)
        if _is_scheduled_snapshot_date(path_date) and (
            pd.isna(current_date) or pd.isna(path_date) or path_date.normalize() != current_date.normalize()
        ):
            entries.append((path, load_snapshot(path)))
    latest_path = SNAPSHOT_DIR / "fm24-memory.json"
    if include_current and latest_path.exists():
        entries.append((latest_path, load_snapshot(latest_path)))
    if not export.empty:
        entries.append((EXPORT_HISTORY_FILE, load_snapshot(EXPORT_HISTORY_FILE)))
    def entry_date(item):
        frame = item[1]
        if "Date" in frame and frame["Date"].notna().any():
            return pd.to_datetime(frame["Date"], errors="coerce").min()
        return pd.Timestamp.fromtimestamp(item[0].stat().st_mtime)
    # A scheduled archive and fm24-memory.json can represent the same game
    # date. Keep the current file as the authoritative copy for that date.
    unique = {}
    undated = []
    for item in entries:
        current_date = entry_date(item)
        if pd.isna(current_date):
            undated.append(item)
        else:
            unique[current_date.normalize()] = item
    _HISTORY_CACHE_KEY = signature
    _HISTORY_CACHE = sorted([*unique.values(), *undated], key=entry_date)
    return [(path, frame.copy()) for path, frame in _HISTORY_CACHE]


def _is_scheduled_snapshot(frame: pd.DataFrame) -> bool:
    if "Date" not in frame or frame["Date"].dropna().empty:
        return False
    date = pd.to_datetime(frame["Date"], errors="coerce").dropna().min()
    return date.day == 1 and date.month in SCHEDULED_MONTHS


def _is_scheduled_snapshot_date(date) -> bool:
    if pd.isna(date):
        return False
    return date.day == 1 and date.month in SCHEDULED_MONTHS


def growth(df: pd.DataFrame, previous: pd.DataFrame | None) -> pd.DataFrame:
    out = df.copy()
    if previous is None or previous.empty or "Current Ability" not in out or "Current Ability" not in previous:
        out["CA Growth"] = 0.0
        out["CA Increase"] = 0.0
        out["Rating Increase"] = 0.0
        return out
    old = previous[["ID", "Current Ability"]].drop_duplicates("ID").set_index("ID")["Current Ability"]
    out["CA Growth"] = (out["Current Ability"] - out["ID"].map(old)).fillna(0).round(2)
    out["CA Increase"] = out["CA Growth"]
    if "Current Rating" in out and "Current Rating" in previous:
        old_rating = previous[["ID", "Current Rating"]].drop_duplicates("ID").set_index("ID")["Current Rating"]
        out["Rating Increase"] = (out["Current Rating"] - out["ID"].map(old_rating)).fillna(0).round(2)
    else:
        out["Rating Increase"] = 0.0
    return out


def save_shortlist(df: pd.DataFrame) -> None:
    df.to_csv(SHORTLIST_FILE, index=False)
