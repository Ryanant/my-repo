import sys
import numpy as np
import pandas as pd
from pathlib import Path

# Add project root to path for absolute imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import NATURAL_POSITION_ORDER


def build_viz_df(df: pd.DataFrame, positions):
    df['Positions_filter'] = df['Positions'].apply(lambda x: ', '.join(x) + ', All')
    df['Positions'] = df['Positions'].apply(lambda x: ', '.join(x))

    rating_cols = [f'{p}_rating' for p in positions if f'{p}_rating' in df.columns]
    rating_growth_cols = [f'{p}_rating_growth' for p in positions if f'{p}_rating_growth' in df.columns]
    rating_growth_12m_cols = [f'{p}_rating_growth_12m' for p in positions if f'{p}_rating_growth_12m' in df.columns]
    rating_proj_cols = [f'{p}_proj_peak' for p in positions if f'{p}_proj_peak' in df.columns]
    rating_proj_age_cols = [f'{p}_proj_peak_age' for p in positions if f'{p}_proj_peak_age' in df.columns]
    rating_proj_low_cols = [f'{p}_proj_low' for p in positions if f'{p}_proj_low' in df.columns]
    rating_proj_high_cols = [f'{p}_proj_high' for p in positions if f'{p}_proj_high' in df.columns]
    rating_proj_source_cols = [f'{p}_proj_source' for p in positions if f'{p}_proj_source' in df.columns]
    rating_proj_points_cols = [f'{p}_proj_points' for p in positions if f'{p}_proj_points' in df.columns]

    base_cols = [
        'UID','Name','Age_int','age_tag','is_u18','is_u21','is_over_18','is_over_21',
        'Positions','Nat','Positions_filter','PA','CA_est','PA_norm'
    ]
    base_cols = [c for c in base_cols if c in df.columns]

    viz_df = df[base_cols +
            rating_cols +
            rating_growth_cols +
            rating_growth_12m_cols +
            rating_proj_cols +
            rating_proj_age_cols +
            rating_proj_low_cols +
            rating_proj_high_cols +
            rating_proj_source_cols +
            rating_proj_points_cols +
            positions +   # keep for toggle logic
            ['is_latest_export','Date']].round(2)


    viz_df = viz_df[viz_df['is_latest_export']]

    display_cols = rating_cols
    if display_cols:
        viz_df['Max_Rating'] = viz_df[display_cols].max(axis=1)
    else:
        viz_df['Max_Rating'] = 0

    return viz_df, display_cols
