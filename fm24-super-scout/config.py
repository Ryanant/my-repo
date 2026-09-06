from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
SNAPSHOT_DIR = PROJECT_ROOT / "snapshots"
SHORTLIST_FILE = PROJECT_ROOT / "shortlist.csv"
EXPORT_HISTORY_FILE = Path.home() / "Documents" / "Sports Interactive" / "Football Manager 2024" / "Python Exports" / "Everton" / "all_players_data.csv"

POSITION_ORDER = ["GK", "SW", "DL", "DC", "DR", "DM", "ML", "MC", "MR", "WBL", "WBR", "AML", "AMC", "AMR", "ST"]
ROLE_WEIGHTS = {
    "GK": {"reflexes": 0.25, "handling": 0.20, "one_on_ones": 0.15, "agility": 0.10, "communication": 0.10, "aerial_reach": 0.10, "decisions": 0.10},
    "DC": {"jumping_reach": 0.18, "pace": 0.16, "acceleration": 0.14, "anticipation": 0.14, "positioning": 0.14, "tackling": 0.12, "composure": 0.12},
    "DM": {"positioning": 0.16, "anticipation": 0.16, "passing": 0.16, "composure": 0.14, "stamina": 0.12, "decisions": 0.12, "tackling": 0.14},
    "MC": {"passing": 0.18, "composure": 0.16, "vision": 0.16, "decisions": 0.14, "anticipation": 0.14, "stamina": 0.10, "technique": 0.12},
    "ST": {"finishing": 0.20, "composure": 0.16, "acceleration": 0.15, "pace": 0.14, "positioning": 0.14, "dribbling": 0.11, "anticipation": 0.10},
}
for _wide in ("DL", "DR"):
    ROLE_WEIGHTS[_wide] = {"pace": .18, "acceleration": .16, "tackling": .14, "crossing": .14, "stamina": .12, "positioning": .12, "work_rate": .14}
for _wide in ("AML", "AMR"):
    ROLE_WEIGHTS[_wide] = {"dribbling": .18, "pace": .17, "acceleration": .15, "passing": .14, "crossing": .12, "technique": .13, "vision": .11}
ROLE_WEIGHTS["AMC"] = {"vision": .18, "passing": .16, "technique": .16, "composure": .14, "dribbling": .14, "decisions": .12, "anticipation": .10}
