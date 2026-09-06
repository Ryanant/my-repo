import os
import sys
import io
import time
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup as bs

# Add project root to path for absolute imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import PYTHON_EXPORTS, CURRENT_SAVE, ALL_PLAYERS_FILE


def load_player_history() -> pd.DataFrame:
    folder_path = os.path.join(PYTHON_EXPORTS, CURRENT_SAVE)
    all_players_file_path = os.path.join(folder_path, ALL_PLAYERS_FILE)

    all_folder_files = os.listdir(folder_path)

    html_exports = [
        f.replace('.html', '') + ' 00:00:01'
        for f in all_folder_files if f.endswith('.html')
    ]

    if not os.path.exists(all_players_file_path):
        exported_dates = []
    else:
        exported_dates = pd.read_csv(all_players_file_path)['Date'].unique().tolist()

    for file in html_exports:
        if file in exported_dates:
            continue

        file_name = file.replace(' 00:00:01', '')
        full_path = os.path.join(folder_path, file_name + '.html')

        soup = bs(open(full_path, encoding="utf8"), "html.parser").find('table')
        raw_df = pd.read_html(io.StringIO(str(soup)))[0]
        raw_df = raw_df.dropna(subset=['UID'])

        date = file_name.split('.')[0] + ' 00:00:01'
        raw_df['Date'] = pd.to_datetime(date)
        raw_df['DoB'] = pd.to_datetime(raw_df['DoB'].str.split().str[0], format="%d/%m/%Y")
        raw_df['DoB'] += pd.Timedelta(seconds=1)
        raw_df['Age'] = (raw_df['Date'] - raw_df['DoB']).dt.days / 365.25
        raw_df['Acc'] = pd.to_numeric(raw_df['Acc'], errors='coerce')

        if not os.path.exists(all_players_file_path):
            raw_df.to_csv(all_players_file_path, index=False)
        else:
            backup = os.path.join(
                folder_path,
                f"all_players_data_{time.strftime('%Y%m%d-%H%M%S')}.csv"
            )
            pd.read_csv(all_players_file_path).to_csv(backup, index=False)

            combined = pd.concat([
                pd.read_csv(all_players_file_path),
                raw_df
            ]).drop_duplicates()

            combined.to_csv(all_players_file_path, index=False)

    df = pd.read_csv(all_players_file_path)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    df['DoB'] = pd.to_datetime(df['DoB'], errors='coerce')

    return df
