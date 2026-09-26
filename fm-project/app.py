import sys
from pathlib import Path

# Add project root to path for absolute imports
PROJECT_ROOT = Path(__file__).resolve().parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import dash
import pandas as pd
import numpy as np
import plotly.express as px

from dash import dcc, html, dash_table, no_update
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output, State


# ============================================================
# DATA PIPELINE IMPORTS
# ============================================================

from data.loader import load_player_history
from data.cleaning import (
    clean_base_columns,
    add_season_age,
    add_age_group_tags,
)
from features.positions import expand_positions
from features.ratings import (
    OUTFIELD_IDEAL_ATTRIBUTES,
    GK_WEIGHTS,
    add_position_ratings,
)
from features.growth import add_growth_metrics
from features.projections import add_projection_metrics
from features.fm24_evaluator import (
    add_fm24_evaluation,
    get_evaluation_summary,
    get_position_filter_evaluations,
)
from viz.dataframe import build_viz_df
from config import NATURAL_POSITION_ORDER


# ============================================================
# LOAD + PREPARE DATA ONCE
# ============================================================

df = load_player_history()

df = clean_base_columns(df)
df = add_season_age(df)
df = add_age_group_tags(df)

df, all_positions = expand_positions(df)

# Position ratings
df = add_position_ratings(df)

# Growth metrics
df = add_growth_metrics(df)

# Projection metrics
df = add_projection_metrics(df, all_positions)

# FM24 evaluation metrics
df = add_fm24_evaluation(df)

# Visualization dataframe
viz_df, rating_columns_display = build_viz_df(
    df,
    all_positions,
)

# Keep complete historical dataframe
history_df = df.copy()


# ============================================================
# BASIC HELPERS
# ============================================================

def _normalize_uid(uid):
    """
    Normalize player UID to a consistent string representation.
    """
    if uid is None:
        return None

    if pd.isna(uid):
        return None

    if isinstance(uid, str):
        uid = uid.strip()
        return uid or None

    return str(uid)


def _safe_numeric(value):
    """
    Safely convert a value to numeric.
    """
    return pd.to_numeric(value, errors="coerce")


# ============================================================
# FM24 EVALUATION
# ============================================================

def _build_fm24_evaluation_records():
    """
    Build records for FM24 evaluation table.
    """
    eval_summary = get_evaluation_summary(df)
    return eval_summary.to_dict("records")


fm24_eval_columns = [
    {"name": "Name", "id": "Name"},
    {"name": "Age", "id": "Age"},
    {"name": "Positions", "id": "Positions"},
    {"name": "Best Position", "id": "Best_Position"},
    {"name": "Position Group", "id": "Position_Group"},
    {"name": "Score", "id": "Score"},
    {"name": "Ceiling", "id": "Ceiling"},
    {"name": "Category", "id": "Category"},
    {"name": "Tags", "id": "Tags"},
    {"name": "Strengths", "id": "Strengths"},
    {"name": "Weaknesses", "id": "Weaknesses"},
]


CATEGORY_OPTIONS = [
    {"label": "All Categories", "value": "all"},
    {"label": "First Team Ready", "value": "First Team Ready"},
    {"label": "Develop", "value": "Develop"},
    {"label": "Bin", "value": "Bin"},
]


# ============================================================
# LATEST EXTRACT TABLE
# ============================================================

table_key_fields = [
    "Name",
    "Age_int",
    "age_tag",
    "Nat",
    "Positions",
]

ordered_positions = [
    p
    for p in NATURAL_POSITION_ORDER
    if f"{p}_rating" in viz_df.columns
]

for pos in ordered_positions:
    col = f"{pos}_rating"

    if col in viz_df.columns:
        table_key_fields.append(col)


table_key_fields = [
    c
    for c in dict.fromkeys(table_key_fields)
    if c in viz_df.columns
]


table_df = viz_df.copy()

if "Max_Rating" in table_df.columns:
    table_df = table_df.sort_values(
        "Max_Rating",
        ascending=False,
    )


def _format_table_col(col: str) -> str:
    if col == "Name":
        return "Name"

    if col == "Age_int":
        return "Age"

    if col == "age_tag":
        return "Age Tag"

    if col == "Nat":
        return "Nationality"

    if col == "Positions":
        return "Positions"

    if col.endswith("_rating"):
        pos = col.replace("_rating", "")
        return f"{pos} rating"

    return col


table_columns = [
    {
        "name": _format_table_col(c),
        "id": c,
    }
    for c in table_key_fields
]


def _build_latest_extract_records():
    return table_df[
        table_key_fields
    ].to_dict("records")


# ============================================================
# FORMATION / SQUAD BUILDER DEFINITIONS
# ============================================================

FORMATIONS = {
    "433": [
        "GK",
        "DL",
        "DC",
        "DC",
        "DR",
        "MC",
        "MC",
        "MC",
        "AML",
        "ST",
        "AMR",
    ],
    "433dm": [
        "GK",
        "DL",
        "DC",
        "DC",
        "DR",
        "DMC",
        "DMC",
        "DMC",
        "AML",
        "ST",
        "AMR",
    ],
    "4231": [
        "GK",
        "DL",
        "DC",
        "DC",
        "DR",
        "DMC",
        "DMC",
        "AML",
        "AMC",
        "AMR",
        "ST",
    ],
    "352": [
        "GK",
        "DC",
        "DC",
        "DC",
        "DML",
        "DMR",
        "MC",
        "MC",
        "AMC",
        "ST",
        "ST",
    ],
}


TEAM_OPTIONS = [
    {"label": "First Team", "value": "first"},
    {"label": "U21s", "value": "u21"},
    {"label": "U18s", "value": "u18"},
]


def _formation_slots(
    formation: str,
) -> list[tuple[str, str]]:
    """
    Turn a formation into unique slot IDs.

    Example:
        MC, MC, MC
    becomes:
        MC_1, MC_2, MC_3
    """

    counts = {}
    slots = []

    for pos in FORMATIONS[formation]:
        counts[pos] = counts.get(pos, 0) + 1

        slot_key = f"{pos}_{counts[pos]}"

        slots.append(
            (
                slot_key,
                pos,
            )
        )

    return slots


def _filter_team_df(team: str) -> pd.DataFrame:
    """
    Filter visualization dataframe by squad.
    """

    if team == "u21":
        return viz_df[
            viz_df["is_u21"]
            & ~viz_df["is_u18"]
        ]

    if team == "u18":
        return viz_df[
            viz_df["is_u18"]
        ]

    return viz_df


def _team_selection_score(
    source_df: pd.DataFrame,
    position: str,
    team: str,
) -> pd.Series:

    rating_col = f"{position}_rating"

    if team in {"u21", "u18"}:

        proj_col = f"{position}_proj_peak"

        if proj_col in source_df.columns:
            return source_df[
                proj_col
            ].fillna(
                source_df[rating_col]
            )

    return source_df[rating_col]


def _selection_store_key(
    team: str,
    formation: str,
) -> str:
    return f"{team}::{formation}"


def _build_default_team(
    formation: str,
    team: str,
) -> dict:

    used = set()

    selections = {}

    team_df = _filter_team_df(team)

    for slot_key, pos in _formation_slots(formation):

        rating_col = f"{pos}_rating"

        if rating_col not in team_df.columns:
            continue

        pos_df = team_df[
            pd.to_numeric(
                team_df[rating_col],
                errors="coerce",
            ).notna()
        ].copy()

        if pos_df.empty:
            selections[slot_key] = {
                "pos": pos,
                "starter": None,
                "backup": None,
            }
            continue

        pos_df["_score"] = _team_selection_score(
            pos_df,
            pos,
            team,
        )

        pos_df["_uid_str"] = (
            pos_df["UID"]
            .astype(str)
        )

        pos_df = pos_df[
            ~pos_df["_uid_str"].isin(used)
        ]

        if pos_df.empty:
            selections[slot_key] = {
                "pos": pos,
                "starter": None,
                "backup": None,
            }
            continue

        best = pos_df.sort_values(
            "_score",
            ascending=False,
        ).iloc[0]

        best_uid = _normalize_uid(
            best["UID"]
        )

        selections[slot_key] = {
            "pos": pos,
            "starter": best_uid,
            "backup": None,
        }

        if best_uid is not None:
            used.add(best_uid)

    return selections


def _get_team_selections(
    team_selections: dict | None,
    formation: str,
    team: str,
) -> dict:

    team_selections = team_selections or {}

    key = _selection_store_key(
        team,
        formation,
    )

    selections = team_selections.get(key)

    if selections:
        return selections

    return _build_default_team(
        formation,
        team,
    )


# ============================================================
# DASHBOARD CALCULATIONS
# ============================================================

def _latest_with_best_values() -> pd.DataFrame:

    out = viz_df.copy()

    rating_cols = [
        f"{p}_rating"
        for p in NATURAL_POSITION_ORDER
        if f"{p}_rating" in out.columns
    ]

    potential_cols = [
        f"{p}_proj_peak"
        for p in NATURAL_POSITION_ORDER
        if f"{p}_proj_peak" in out.columns
    ]

    if rating_cols:

        ratings = out[
            rating_cols
        ].apply(
            pd.to_numeric,
            errors="coerce",
        )

        has_rating = ratings.notna().any(axis=1)

        out["Best_Position"] = "N/A"
        out["Best_Rating"] = np.nan

        out.loc[
            has_rating,
            "Best_Position",
        ] = (
            ratings.loc[has_rating]
            .idxmax(axis=1)
            .str.replace(
                "_rating",
                "",
                regex=False,
            )
        )

        out.loc[
            has_rating,
            "Best_Rating",
        ] = ratings.loc[
            has_rating
        ].max(axis=1)

    else:

        out["Best_Position"] = "N/A"
        out["Best_Rating"] = 0

    if potential_cols:

        out["Best_Potential"] = (
            out[potential_cols]
            .apply(
                pd.to_numeric,
                errors="coerce",
            )
            .max(axis=1)
        )

    else:
        out["Best_Potential"] = out[
            "Best_Rating"
        ]

    out["Potential_Gap"] = (
        out["Best_Potential"]
        - out["Best_Rating"]
    ).round(2)

    return out.round(2)


dashboard_df = _latest_with_best_values()


# ============================================================
# GLOBAL FILTER OPTIONS
# ============================================================

SQUAD_FILTER_OPTIONS = [
    {"label": "All", "value": "all"},
    {"label": "U21", "value": "u21"},
    {"label": "U18", "value": "u18"},
]


POSITION_OPTIONS = [
    {"label": "All", "value": "all"},
] + [
    {
        "label": p,
        "value": p,
    }
    for p in NATURAL_POSITION_ORDER
    if f"{p}_rating" in history_df.columns
]


# Build player options from latest export where possible.
# This gives the global selector the actual current squad.
if "is_latest_export" in history_df.columns:

    latest_player_source = history_df[
        history_df["is_latest_export"]
    ].copy()

else:

    latest_date = history_df["Date"].max()

    latest_player_source = history_df[
        history_df["Date"] == latest_date
    ].copy()


PLAYER_OPTIONS_DF = (
    latest_player_source[
        ["UID", "Name"]
    ]
    .dropna(subset=["UID", "Name"])
    .drop_duplicates("UID")
    .sort_values("Name")
)


PLAYER_OPTIONS = [
    {
        "label": str(row["Name"]),
        "value": str(row["UID"]),
    }
    for _, row in PLAYER_OPTIONS_DF.iterrows()
]


# ============================================================
# GLOBAL FILTER HELPERS
# ============================================================

def _filter_by_players(
    source: pd.DataFrame,
    selected_players: list | None,
) -> pd.DataFrame:

    if not selected_players:
        return source.copy()

    selected = {
        str(uid)
        for uid in selected_players
    }

    return source[
        source["UID"]
        .astype(str)
        .isin(selected)
    ].copy()


def _filter_latest_by_squad(
    latest_df: pd.DataFrame,
    squad: str,
) -> pd.DataFrame:

    if squad == "u18":

        return latest_df[
            latest_df["is_u18"]
        ].copy()

    if squad == "u21":

        return latest_df[
            latest_df["is_u21"]
            & ~latest_df["is_u18"]
        ].copy()

    return latest_df.copy()


def _filter_history_by_squad(
    source: pd.DataFrame,
    squad: str,
) -> pd.DataFrame:

    if squad == "u18":

        return source[
            source["is_u18"]
        ].copy()

    if squad == "u21":

        return source[
            source["is_u21"]
            & ~source["is_u18"]
        ].copy()

    return source.copy()


# ============================================================
# RATING TABLE
# ============================================================

ONE_PAGE_COLUMNS = [
    {"name": "Name", "id": "Name"},
    {"name": "Age", "id": "Age"},
    {"name": "First Rating", "id": "First_Rating"},
    {"name": "Current Rating", "id": "Current_Rating"},
    {"name": "Potential Rating", "id": "Potential_Rating"},
    {
        "name": "Key Stat Growth 12m",
        "id": "Key_Stat_Growth",
    },
]


def _key_stat_columns(position: str) -> list[str]:

    if position == "GK":

        return [
            attr
            for attr in GK_WEIGHTS
            if attr != "TRO"
        ]

    return list(
        OUTFIELD_IDEAL_ATTRIBUTES.keys()
    )


def _key_stat_growth_for_uid(
    uid,
    position: str,
    growth_period: str = "12m",
) -> int | None:

    player_history = (
        history_df[
            history_df["UID"] == uid
        ]
        .sort_values("Date")
    )

    if len(player_history) < 2:
        return None

    latest_row = player_history.iloc[-1]

    if growth_period == "all_time":
        previous_row = player_history.iloc[0]
    else:
        previous_row = player_history.iloc[-2]

    attrs = [
        attr
        for attr in _key_stat_columns(position)
        if attr in player_history.columns
    ]

    if not attrs:
        return None

    latest_values = pd.to_numeric(
        latest_row[attrs],
        errors="coerce",
    )

    previous_values = pd.to_numeric(
        previous_row[attrs],
        errors="coerce",
    )

    latest_sum = (
        latest_values
        .fillna(0)
        .sum()
    )

    previous_sum = (
        previous_values
        .fillna(0)
        .sum()
    )

    return int(
        round(
            float(latest_sum)
            - float(previous_sum)
        )
    )


def _build_rating_rows(
    squad: str,
    position: str,
    selected_players: list | None = None,
    growth_period: str = "12m",
) -> list[dict]:

    if (
        position != "all"
        and f"{position}_rating"
        not in history_df.columns
    ):
        return []

    # ---------------------------------------------
    # Latest export only
    # ---------------------------------------------

    latest = history_df[
        history_df["is_latest_export"]
    ].copy()

    # Squad filter
    latest = _filter_latest_by_squad(
        latest,
        squad,
    )

    # Global player filter
    latest = _filter_by_players(
        latest,
        selected_players,
    )

    if latest.empty:
        return []

    # ---------------------------------------------
    # ALL POSITIONS
    # ---------------------------------------------

    if position == "all":

        rating_cols = [
            f"{p}_rating"
            for p in NATURAL_POSITION_ORDER
            if f"{p}_rating" in latest.columns
        ]

        potential_cols = [
            f"{p}_proj_peak"
            for p in NATURAL_POSITION_ORDER
            if f"{p}_proj_peak" in latest.columns
        ]

        if not rating_cols:
            return []

        rating_values = latest[
            rating_cols
        ].apply(
            pd.to_numeric,
            errors="coerce",
        )

        valid_rows = rating_values.notna().any(
            axis=1
        )

        latest = latest[
            valid_rows
        ].copy()

        rating_values = rating_values.loc[
            latest.index
        ]

        latest["Current_Rating"] = (
            rating_values.max(axis=1)
        )

        latest["Best_Position"] = (
            rating_values
            .idxmax(axis=1)
            .str.replace(
                "_rating",
                "",
                regex=False,
            )
        )

        if potential_cols:

            latest["Potential_Rating"] = (
                latest[potential_cols]
                .apply(
                    pd.to_numeric,
                    errors="coerce",
                )
                .max(axis=1)
            )

        else:

            latest["Potential_Rating"] = (
                latest["Current_Rating"]
            )

        # First recorded rating
        history_rating_values = (
            history_df[
                ["UID", "Date"] + rating_cols
            ]
            .copy()
            .sort_values("Date")
        )

        history_rating_values[
            "First_Rating_Row"
        ] = (
            history_rating_values[
                rating_cols
            ]
            .apply(
                pd.to_numeric,
                errors="coerce",
            )
            .max(axis=1)
        )

        first_ratings = (
            history_rating_values[
                history_rating_values[
                    "First_Rating_Row"
                ].notna()
            ]
            .groupby("UID")[
                "First_Rating_Row"
            ]
            .first()
        )

    # ---------------------------------------------
    # SPECIFIC POSITION
    # ---------------------------------------------

    else:

        rating_col = f"{position}_rating"
        potential_col = f"{position}_proj_peak"

        latest = latest[
            pd.to_numeric(
                latest[rating_col],
                errors="coerce",
            ).notna()
        ]

        if latest.empty:
            return []

        latest["Current_Rating"] = (
            pd.to_numeric(
                latest[rating_col],
                errors="coerce",
            )
        )

        if potential_col in latest.columns:

            latest["Potential_Rating"] = (
                pd.to_numeric(
                    latest[potential_col],
                    errors="coerce",
                )
            )

        else:

            latest["Potential_Rating"] = (
                latest["Current_Rating"]
            )

        latest["Best_Position"] = position

        first_ratings = (
            history_df[
                pd.to_numeric(
                    history_df[rating_col],
                    errors="coerce",
                ).notna()
            ]
            .sort_values("Date")
            .groupby("UID")[rating_col]
            .first()
        )

    # ---------------------------------------------
    # Additional fields
    # ---------------------------------------------

    latest["First_Rating"] = (
        latest["UID"].map(first_ratings)
    )

    latest["Key_Stat_Growth"] = latest.apply(
        lambda row: _key_stat_growth_for_uid(
            row["UID"],
            row["Best_Position"],
            growth_period,
        ),
        axis=1,
    )

    if "Age_int" in latest.columns:

        latest["Age"] = latest[
            "Age_int"
        ]

    elif "Age" not in latest.columns:

        latest["Age"] = np.nan

    rows = (
        latest[
            [
                "Name",
                "Age",
                "First_Rating",
                "Current_Rating",
                "Potential_Rating",
                "Key_Stat_Growth",
            ]
        ]
        .round(2)
        .sort_values(
            [
                "Potential_Rating",
                "Current_Rating",
            ],
            ascending=False,
        )
    )

    return rows.to_dict(
        "records"
    )


# ============================================================
# ACTUAL YEAR-ON-YEAR KEY STAT GROWTH
# ============================================================

AGE_GROWTH_BASE_COLUMNS = [
    {
        "name": "Name",
        "id": "Name",
    },
    {
        "name": "Age",
        "id": "Age",
    },
    {
        "name": "Date",
        "id": "Date",
    },
]


def _build_age_key_stat_growth_rows(
    squad: str,
    position: str,
    selected_players: list | None = None,
    growth_period: str = "12m",
) -> tuple[list[dict], list[dict]]:
    """
    Build ACTUAL attribute changes between consecutive
    recorded FM exports.

    IMPORTANT:

    This does NOT calculate averages.

    This does NOT group changes by age.

    This does NOT require exports to be exactly 12 months apart.

    For every player:

        Export 1 -> Export 2
        Export 2 -> Export 3
        Export 3 -> Export 4

    Each row represents the actual change between those
    two consecutive exports.

    Example:

        Pace:
            14 -> 15 = +1
            15 -> 15 = 0
            15 -> 17 = +2

    FM attributes are integers, so the resulting changes
    are explicitly converted to integers.
    """

    # ---------------------------------------------------------
    # Which attributes should be displayed?
    # ---------------------------------------------------------

    attrs = [
        attr
        for attr in _key_stat_columns(position)
        if attr in history_df.columns
    ]

    columns = [
        {
            "name": "Name",
            "id": "Name",
        },
        {
            "name": "Age",
            "id": "Age",
        },
        {
            "name": "Date",
            "id": "Date",
        },
    ] + [
        {
            "name": attr,
            "id": attr,
        }
        for attr in attrs
    ]

    if not attrs:
        return [], columns

    # ---------------------------------------------------------
    # Start with entire history
    # ---------------------------------------------------------

    source = history_df.copy()

    # ---------------------------------------------------------
    # Squad filter
    # ---------------------------------------------------------

    source = _filter_history_by_squad(
        source,
        squad,
    )

    if source.empty:
        return [], columns

    # ---------------------------------------------------------
    # Global player filter
    # ---------------------------------------------------------

    source = _filter_by_players(
        source,
        selected_players,
    )

    if source.empty:
        return [], columns

    # ---------------------------------------------------------
    # Position filter
    # ---------------------------------------------------------

    if position != "all":

        rating_col = f"{position}_rating"

        if rating_col not in source.columns:
            return [], columns

        source = source[
            pd.to_numeric(
                source[rating_col],
                errors="coerce",
            ).notna()
        ].copy()

    else:

        rating_cols = [
            f"{p}_rating"
            for p in NATURAL_POSITION_ORDER
            if f"{p}_rating" in source.columns
        ]

        if rating_cols:

            rating_values = source[
                rating_cols
            ].apply(
                pd.to_numeric,
                errors="coerce",
            )

            source = source[
                rating_values.notna().any(
                    axis=1
                )
            ].copy()

    if source.empty:
        return [], columns

    # ---------------------------------------------------------
    # Valid dates only
    # ---------------------------------------------------------

    source["Date"] = pd.to_datetime(
        source["Date"],
        errors="coerce",
    )

    source = source[
        source["Date"].notna()
    ].copy()

    if source.empty:
        return [], columns

    growth_cutoff = None
    if growth_period != "all_time":
        growth_cutoff = source["Date"].max() - pd.DateOffset(months=12)

    # ---------------------------------------------------------
    # Sort by player and date
    #
    # THIS IS THE IMPORTANT PART.
    #
    # We are comparing each export to the immediately
    # previous export for that same player.
    # ---------------------------------------------------------

    source = source.sort_values(
        [
            "UID",
            "Date",
        ]
    ).copy()

    rows = []

    # ---------------------------------------------------------
    # Process each player independently
    # ---------------------------------------------------------

    for uid, player_history in source.groupby(
        "UID",
        sort=False,
    ):

        player_history = (
            player_history
            .sort_values("Date")
            .reset_index(drop=True)
        )

        # A player needs at least two exports.
        if len(player_history) < 2:
            continue

        # -----------------------------------------------------
        # Compare every export to the one immediately before it
        # -----------------------------------------------------

        for idx in range(
            1,
            len(player_history),
        ):

            previous = player_history.iloc[
                idx - 1
            ]

            current = player_history.iloc[
                idx
            ]

            if growth_cutoff is not None and current["Date"] < growth_cutoff:
                continue

            current_age = current.get(
                "Age_int",
                current.get("Age"),
            )

            row = {
                "Name": current.get(
                    "Name"
                ),
                "Age": current_age,
                "Date": current.get(
                    "Date"
                ),
            }

            # -------------------------------------------------
            # Calculate every attribute change
            # -------------------------------------------------

            for attr in attrs:

                previous_value = pd.to_numeric(
                    previous.get(attr),
                    errors="coerce",
                )

                current_value = pd.to_numeric(
                    current.get(attr),
                    errors="coerce",
                )

                if (
                    pd.notna(previous_value)
                    and pd.notna(current_value)
                ):

                    change = (
                        float(current_value)
                        - float(previous_value)
                    )

                    # FM attributes are integer values.
                    row[attr] = int(
                        round(change)
                    )

                else:

                    # If either snapshot is missing the
                    # attribute, don't invent a change.
                    row[attr] = 0

            rows.append(row)

    # ---------------------------------------------------------
    # Nothing to show
    # ---------------------------------------------------------

    if not rows:
        return [], columns

    result = pd.DataFrame(rows)

    # ---------------------------------------------------------
    # Newest changes first
    # ---------------------------------------------------------

    result = result.sort_values(
        [
            "Date",
            "Name",
        ],
        ascending=[
            False,
            True,
        ],
    )

    # ---------------------------------------------------------
    # Format dates
    # ---------------------------------------------------------

    result["Date"] = pd.to_datetime(
        result["Date"],
        errors="coerce",
    ).dt.strftime(
        "%d %b %Y"
    )

    # ---------------------------------------------------------
    # Force all attribute changes to integers
    # ---------------------------------------------------------

    for attr in attrs:

        if attr in result.columns:

            result[attr] = (
                pd.to_numeric(
                    result[attr],
                    errors="coerce",
                )
                .fillna(0)
                .astype(int)
            )

    return (
        result.to_dict("records"),
        columns,
    )


# ============================================================
# APP
# ============================================================

app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP
    ],
    suppress_callback_exceptions=True,
)


# ============================================================
# STYLES
# ============================================================

TABLE_STYLE = {
    "overflowX": "auto",
    "border": "1px solid #d9e2ec",
    "borderRadius": "6px",
}

CELL_STYLE = {
    "fontSize": "0.86rem",
    "padding": "0.42rem",
    "whiteSpace": "normal",
    "height": "auto",
    "fontFamily": (
        "Inter, Segoe UI, Arial, sans-serif"
    ),
}

HEADER_STYLE = {
    "fontWeight": "700",
    "backgroundColor": "#f3f6f9",
    "borderBottom": "1px solid #c8d3df",
}


def _section(
    title: str,
    children,
    class_name: str = "section",
):

    section_children = [
        html.Div(
            title,
            className="section-title",
        )
    ]

    if isinstance(children, list):

        section_children.extend(
            children
        )

    else:

        section_children.append(
            children
        )

    return html.Section(
        section_children,
        className=class_name,
    )


# ============================================================
# DASHBOARD SUMMARY
# ============================================================

latest_export_date = (
    dashboard_df["Date"].max()
    if "Date" in dashboard_df.columns
    else pd.NaT
)

avg_rating = (
    dashboard_df["Best_Rating"].mean()
    if "Best_Rating" in dashboard_df.columns
    else 0
)

avg_potential = (
    dashboard_df["Best_Potential"].mean()
    if "Best_Potential" in dashboard_df.columns
    else 0
)

u18_count = (
    int(
        dashboard_df["is_u18"].sum()
    )
    if "is_u18" in dashboard_df.columns
    else 0
)

u21_count = (
    int(
        dashboard_df["is_u21"].sum()
    )
    if "is_u21" in dashboard_df.columns
    else 0
)


# ============================================================
# LAYOUT
# ============================================================

default_position = (
    POSITION_OPTIONS[0]["value"]
    if POSITION_OPTIONS
    else "all"
)


app.layout = dbc.Container(
    fluid=True,
    className="dashboard-shell simple-dashboard",
    children=[

        # ----------------------------------------------------
        # Header
        # ----------------------------------------------------

        html.Header(
            [
                html.Div(
                    [
                        html.Div(
                            "FM24 SQUAD MODEL",
                            className="app-kicker",
                        ),
                        html.H1(
                            "Player Ratings",
                            className="app-title",
                        ),
                    ],
                    className="app-heading",
                ),

                html.Div(
                    [
                        html.Div(
                            "LATEST EXPORT",
                            className="header-label",
                        ),

                        html.Div(
                            (
                                latest_export_date.strftime(
                                    "%d %b %Y"
                                )
                                if pd.notna(
                                    latest_export_date
                                )
                                else "Unknown"
                            ),
                            className="header-value",
                        ),
                    ],
                    className="header-meta",
                ),
            ],
            className="app-header",
        ),

        # ----------------------------------------------------
        # GLOBAL FILTER BAR
        # ----------------------------------------------------

        html.Div(
            [

                # PLAYER FILTER
                html.Div(
                    [
                        html.Label(
                            "Players",
                            className="control-label",
                        ),

                        dcc.Dropdown(
                            id="player_filter",
                            options=PLAYER_OPTIONS,
                            value=[],
                            multi=True,
                            clearable=True,
                            placeholder="All players",
                        ),
                    ],
                    className="control-block",
                ),

                # SQUAD FILTER
                html.Div(
                    [
                        html.Label(
                            "Squad",
                            className="control-label",
                        ),

                        dcc.Dropdown(
                            id="squad_filter",
                            options=SQUAD_FILTER_OPTIONS,
                            value="all",
                            clearable=False,
                        ),
                    ],
                    className="control-block",
                ),

                # POSITION FILTER
                html.Div(
                    [
                        html.Label(
                            "Position",
                            className="control-label",
                        ),

                        dcc.Dropdown(
                            id="position_filter",
                            options=POSITION_OPTIONS,
                            value=default_position,
                            clearable=False,
                        ),
                    ],
                    className="control-block",
                ),

            ],
            className="toolbar",
        ),

        # ----------------------------------------------------
        # TABS
        # ----------------------------------------------------

        dbc.Tabs(
            className="main-tabs",
            children=[

                # ============================================
                # RATINGS TAB
                # ============================================

                dbc.Tab(
                    label="Ratings",
                    tab_id="ratings",
                    children=[

                        _section(
                            "Ratings",

                            [
                                dcc.RadioItems(
                                    id="ratings_growth_period",
                                    options=[
                                        {
                                            "label": "Last 12 months",
                                            "value": "12m",
                                        },
                                        {
                                            "label": "All time",
                                            "value": "all_time",
                                        },
                                    ],
                                    value="12m",
                                    inline=True,
                                    className="radio-row compact-toolbar",
                                ),
                                dash_table.DataTable(
                                    id="ratings_table",

                                    columns=ONE_PAGE_COLUMNS,

                                    data=(
                                        _build_rating_rows(
                                            "all",
                                            default_position,
                                            [],
                                        )
                                        if default_position
                                        else []
                                    ),

                                    page_size=30,

                                    sort_action="native",

                                    style_table={
                                        **TABLE_STYLE,
                                        "minWidth": "100%",
                                    },

                                    style_cell={
                                        **CELL_STYLE,
                                        "minWidth": "140px",
                                        "width": "140px",
                                    },

                                    style_header=HEADER_STYLE,
                                ),
                            ],
                        ),
                    ],
                ),

                # ============================================
                # KEY STAT GROWTH TAB
                # ============================================

                dbc.Tab(
                    label="Key Stat Growth",
                    tab_id="key-stat-growth",
                    children=[

                        _section(
                            "Actual Year-on-Year Key Stat Growth",

                            [
                                dcc.RadioItems(
                                    id="key_stats_growth_period",
                                    options=[
                                        {
                                            "label": "Last 12 months",
                                            "value": "12m",
                                        },
                                        {
                                            "label": "All time",
                                            "value": "all_time",
                                        },
                                    ],
                                    value="12m",
                                    inline=True,
                                    className="radio-row compact-toolbar",
                                ),
                                dash_table.DataTable(
                                    id="age_key_stat_growth_table",

                                    columns=AGE_GROWTH_BASE_COLUMNS,

                                    data=[],

                                    page_size=30,

                                    sort_action="native",

                                    style_table={
                                        **TABLE_STYLE,
                                        "minWidth": "100%",
                                    },

                                    style_cell={
                                        **CELL_STYLE,
                                        "minWidth": "90px",
                                        "width": "90px",
                                    },

                                    style_header=HEADER_STYLE,

                                    # Positive / negative changes
                                    # are visually obvious.
                                    style_data_conditional=[
                                        {
                                            "if": {
                                                "filter_query": (
                                                    "{Pac} > 0"
                                                ),
                                                "column_id": "Pac",
                                            },
                                            "color": "#198754",
                                        },
                                    ],
                                ),
                            ],
                        ),

                        html.Div(
                            (
                                "Each row represents an actual "
                                "change between two consecutive "
                                "recorded FM exports. Positive "
                                "values = attribute increased, "
                                "negative values = attribute "
                                "decreased, 0 = no change."
                            ),
                            className="text-muted mt-3",
                        ),
                    ],
                ),
            ],
        ),
    ],
)


# ============================================================
# CALLBACK: RATINGS TABLE
# ============================================================

@app.callback(
    Output(
        "ratings_table",
        "data",
    ),
    Output(
        "ratings_table",
        "columns",
    ),

    Input(
        "squad_filter",
        "value",
    ),

    Input(
        "position_filter",
        "value",
    ),

    Input(
        "player_filter",
        "value",
    ),
    Input(
        "ratings_growth_period",
        "value",
    ),
)
def update_ratings_table(
    squad,
    position,
    selected_players,
    growth_period,
):
    if not position:
        return [], ONE_PAGE_COLUMNS

    rows = _build_rating_rows(
        squad or "all",
        position,
        selected_players or [],
        growth_period or "12m",
    )
    columns = [
        {
            **column,
            "name": (
                "Key Stat Growth All Time"
                if column["id"] == "Key_Stat_Growth"
                and growth_period == "all_time"
                else column["name"]
            ),
        }
        for column in ONE_PAGE_COLUMNS
    ]
    return rows, columns


# ============================================================
# CALLBACK: ACTUAL KEY STAT GROWTH
# ============================================================

@app.callback(
    Output(
        "age_key_stat_growth_table",
        "data",
    ),

    Output(
        "age_key_stat_growth_table",
        "columns",
    ),

    Input(
        "squad_filter",
        "value",
    ),

    Input(
        "position_filter",
        "value",
    ),

    Input(
        "player_filter",
        "value",
    ),
    Input(
        "key_stats_growth_period",
        "value",
    ),
)
def update_age_key_stat_growth_table(
    squad,
    position,
    selected_players,
    growth_period,
):

    if not position:

        return (
            [],
            AGE_GROWTH_BASE_COLUMNS,
        )

    rows, columns = (
        _build_age_key_stat_growth_rows(
            squad or "all",
            position,
            selected_players or [],
            growth_period or "12m",
        )
    )

    return rows, columns


# ============================================================
# RUN APP
# ============================================================

if __name__ == "__main__":
    app.run(
        debug=True
    )