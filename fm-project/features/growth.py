import pandas as pd


def add_growth_metrics(df: pd.DataFrame):
    # -----------------------------
    # Position rating growth (career + last 12 months)
    rating_cols = [c for c in df.columns if c.endswith('_rating')]

    if rating_cols:
        df_sorted = df.sort_values('Date')

        first = (
            df_sorted
              .groupby('UID')
              .first()
              .reset_index()[['UID'] + rating_cols]
              .rename(columns={c: f"{c}_first" for c in rating_cols})
        )

        df = df.merge(first, on='UID', how='left')

        for col in rating_cols:
            df[f"{col}_growth"] = (df[col] - df[f"{col}_first"]).round(2)

        # -----------------------------
        # 12-month growth vs closest snapshot to 12 months ago
        def _baseline_row(group: pd.DataFrame) -> pd.Series:
            latest_date = group['Date'].max()
            if pd.isna(latest_date):
                return pd.Series({'UID': group['UID'].iloc[0], **{c: pd.NA for c in rating_cols}})

            target = latest_date - pd.DateOffset(months=12)
            recent_window = group[(group['Date'] >= target) & (group['Date'] < latest_date)]
            if not recent_window.empty:
                row = recent_window.sort_values('Date').iloc[0]
            else:
                earlier = group[group['Date'] < latest_date]
                if earlier.empty:
                    row = group.sort_values('Date').iloc[0]
                else:
                    row = earlier.sort_values('Date').iloc[-1]

            data = {'UID': row['UID']}
            for c in rating_cols:
                data[c] = row[c]
            return pd.Series(data)

        baseline_rows = []
        for _, group in df_sorted.groupby('UID', sort=False):
            baseline_rows.append(_baseline_row(group))

        base_12m = (
            pd.DataFrame(baseline_rows)
              .rename(columns={c: f"{c}_12m_base" for c in rating_cols})
        )

        df = df.merge(base_12m, on='UID', how='left')

        for col in rating_cols:
            df[f"{col}_growth_12m"] = (df[col] - df[f"{col}_12m_base"]).round(2)

    # -----------------------------
    # Latest export flag
    df['is_latest_export'] = df['Date'] == df['Date'].max()

    return df
