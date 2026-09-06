import pandas as pd

# -----------------------------
# Paths
PYTHON_EXPORTS = "C:/Users/jackj/Documents/Sports Interactive/Football Manager 2024/Python Exports"
CURRENT_SAVE = "Everton"
ALL_PLAYERS_FILE = "all_players_data.csv"

# -----------------------------
# Pandas display options
pd.set_option('display.max_rows', 150)
pd.set_option('display.max_columns', 63)

# -----------------------------
# Natural position order
NATURAL_POSITION_ORDER = [
    'GK','DL','DC','DR',
    'DML','DMC','DMR',
    'ML','MC','MR',
    'AML','AMC','AMR','ST'
]
