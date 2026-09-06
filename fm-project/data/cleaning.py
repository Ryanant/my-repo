import pandas as pd
import numpy as np


def clean_base_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and standardise base columns coming from FM exports.
    """
    # Dates
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['DoB'] = pd.to_datetime(df['DoB'], errors='coerce')

    # Numeric attributes (coerce safely)
    numeric_cols = [
        'Pac','Acc','Jum','Str','Sta','Agi','Bal',
        'Ant','Cnt','Pos','Dec','Vis','Cmp',
        'Pas','Lon','Tec','Dri','Cro','Fin',
        'Fir','Hea','Mar','Tck','Agg','Bra',
        'Wor','Det','Ref','Aer','Han','Thr',
        'Tea','Nat','Com','One','Kic'
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    return df


def add_season_age(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate integer age at export date.
    """

    df['Age_int'] = (
        (df['Date'] - df['DoB']).dt.days // 365
    ).astype('Int64')

    return df


def add_age_group_tags(
    df: pd.DataFrame,
    u18_cutoff: pd.Timestamp | None = None,
    u21_cutoff: pd.Timestamp | None = None
) -> pd.DataFrame:
    """
    Add age-group tags based on season-relative cutoff dates.

    Seasons run July-July. The cutoff dates move forward by one year
    after July 1st:
    - U21 cutoff: 1 January of season end year minus 21 years
    - U18 cutoff: 1 September of season end year minus 18 years

    For example, during the 2040/41 season the cutoffs are:
    - U21: 1 January 2020
    - U18: 1 September 2023
    """
    df = df.copy()

    dob = df["DoB"]
    export_date = pd.to_datetime(df["Date"], errors="coerce")
    after_july_1 = (export_date.dt.month > 7) | (
        (export_date.dt.month == 7) & (export_date.dt.day > 1)
    )
    season_end_year = export_date.dt.year.where(~after_july_1, export_date.dt.year + 1)

    u21_cutoffs = pd.to_datetime(
        {
            "year": season_end_year - 21,
            "month": 1,
            "day": 1,
        },
        errors="coerce",
    )
    u18_cutoffs = pd.to_datetime(
        {
            "year": season_end_year - 18,
            "month": 9,
            "day": 1,
        },
        errors="coerce",
    )

    df["u18_cutoff"] = u18_cutoffs
    df["u21_cutoff"] = u21_cutoffs

    df["is_over_18"] = dob < u18_cutoffs
    df["is_over_21"] = dob < u21_cutoffs
    df["is_u18"] = ~df["is_over_18"]
    df["is_u21"] = ~df["is_over_21"]

    df["age_tag"] = np.select(
        [df["is_u18"], df["is_u21"], df["is_over_21"]],
        ["U18", "U21", "Senior"],
        default="Unknown"
    )

    return df
