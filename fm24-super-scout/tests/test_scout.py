import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1]))
from scout import add_metrics, growth, load_snapshot
from projections import add_projection_metrics


class ScoutTests(unittest.TestCase):
    def test_club_effect_is_pooled_and_shrunk(self):
        old = pd.DataFrame([{
            "ID": 1, "Club": "Club A", "Date": "2024-01-01", "Age": 20,
            "Current Rating": 50, "Current Ability": 100, "Potential Ability": 180,
        }, {
            "ID": 2, "Club": "Club B", "Date": "2024-01-01", "Age": 20,
            "Current Rating": 50, "Current Ability": 100, "Potential Ability": 180,
        }])
        new = old.copy()
        new["Date"] = "2025-01-01"
        new.loc[new["ID"] == 1, "Current Rating"] = 54
        result = add_projection_metrics(old.iloc[[0]].copy(), [old, new])
        self.assertGreater(result.loc[result.index[0], "Club Development Effect"], 0)

    def test_json_game_date_calculates_age(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            path = Path(folder) / "snapshot.json"
            path.write_text(json.dumps({"Game Date": "2024-04-01", "players": [{
                "UID": 7, "Name": "Player", "DoB": "1994-03-07", "Position": "GK",
                "CA": 130, "PA": 160, "Han": 15, "Ref": 15,
            }]}), encoding="utf-8")
            result = load_snapshot(path)
            self.assertAlmostEqual(result.loc[0, "Age"], 30.0698, places=3)

    def test_role_score_and_position(self):
        frame = pd.DataFrame([{
            "ID": 1, "Name": "Striker", "Position": "ST", "Fin": 16,
            "Cmp": 15, "Acc": 15, "Pac": 15, "Off": 14, "Dri": 13, "Ant": 13,
        }])
        result = add_metrics(frame)
        self.assertEqual(result.loc[0, "Best Position"], "ST")
        self.assertIn("Current Rating", result)
        self.assertEqual(result.loc[0, "Current Rating"], result.loc[0, "Scout Score"])

    def test_json_aliases_and_growth(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            path = Path(folder) / "snapshot.json"
            path.write_text(json.dumps({"players": [{
                "UID": 42, "Name": "Player", "Club Name": "Club", "Position": "MC",
                "CA": 130, "PA": 160, "Pas": 15, "Cmp": 14, "Vis": 14,
            }]}), encoding="utf-8")
            current = load_snapshot(path)
            previous = current.copy()
            previous["Current Ability"] = 120
            result = growth(current, previous)
            self.assertEqual(result.loc[0, "ID"], 42)
            self.assertEqual(result.loc[0, "Club"], "Club")
            self.assertEqual(result.loc[0, "CA Growth"], 10)


if __name__ == "__main__":
    unittest.main()
