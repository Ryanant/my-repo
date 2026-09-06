import sys
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.cleaning import clean_base_columns
from data.loader import load_player_history


ATTRIBUTES = ["Pac", "Acc"]
MIN_YEARS_BETWEEN_SNAPSHOTS = 30 / 365.25


def _build_snapshot_changes(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = df.sort_values(["UID", "Date"])

    rows = []
    for uid, group in df.groupby("UID", sort=False):
        group = group.sort_values("Date")
        previous = group.shift(1)

        years_elapsed = (group["Date"] - previous["Date"]).dt.days / 365.25
        valid_gap = years_elapsed >= MIN_YEARS_BETWEEN_SNAPSHOTS

        for attr in ATTRIBUTES:
            delta = group[attr] - previous[attr]
            annualized_delta = delta / years_elapsed

            change_rows = pd.DataFrame(
                {
                    "UID": uid,
                    "Name": group["Name"],
                    "attribute": attr,
                    "from_date": previous["Date"],
                    "to_date": group["Date"],
                    "from_age": previous["Age"],
                    "to_age": group["Age"],
                    "from_age_year": previous["Age"].astype("float").apply(
                        lambda x: int(x) if pd.notna(x) else pd.NA
                    ),
                    "years_elapsed": years_elapsed,
                    "from_value": previous[attr],
                    "to_value": group[attr],
                    "delta": delta,
                    "annualized_delta": annualized_delta,
                }
            )
            rows.append(change_rows[valid_gap])

    if not rows:
        return pd.DataFrame()

    changes = pd.concat(rows, ignore_index=True)
    return changes.dropna(
        subset=["from_date", "to_date", "from_age", "to_age", "annualized_delta"]
    )


def _print_summary(changes: pd.DataFrame) -> None:
    if changes.empty:
        print("No valid player-to-player snapshot changes found.")
        return

    overall = (
        changes.groupby("attribute")["annualized_delta"]
        .agg(snapshots="count", avg_increase_per_year="mean", median_increase_per_year="median")
        .round(3)
        .reset_index()
    )

    by_age = (
        changes.groupby(["from_age_year", "attribute"])["annualized_delta"]
        .agg(snapshots="count", avg_increase_per_year="mean", median_increase_per_year="median")
        .round(3)
        .reset_index()
        .sort_values(["from_age_year", "attribute"])
    )

    paired = (
        changes.pivot_table(
            index=["UID", "Name", "from_date", "to_date", "from_age_year"],
            columns="attribute",
            values="annualized_delta",
            aggfunc="first",
        )
        .reset_index()
    )
    paired["pace_acc_avg"] = paired[["Pac", "Acc"]].mean(axis=1)

    combined_by_age = (
        paired.groupby("from_age_year")["pace_acc_avg"]
        .agg(snapshots="count", avg_pace_acc_increase_per_year="mean", median_pace_acc_increase_per_year="median")
        .round(3)
        .reset_index()
        .sort_values("from_age_year")
    )

    print("\nOverall annualized attribute growth")
    print(overall.to_string(index=False))

    print("\nAnnualized growth by starting age")
    print(by_age.to_string(index=False))

    print("\nCombined Pace + Acceleration average by starting age")
    print(combined_by_age.to_string(index=False))


def main() -> None:
    df = load_player_history()
    df = clean_base_columns(df)

    missing = [attr for attr in ATTRIBUTES if attr not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")

    changes = _build_snapshot_changes(df)
    _print_summary(changes)


if __name__ == "__main__":
    main()
