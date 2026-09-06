"""
FM24 Player Evaluation System
Optimized for FM24's match engine which heavily favors physical attributes.

Classification: "First Team Ready", "Develop", "Bin"
Scores: Position-specific (0-100), Ceiling Score, Development Risk Level
"""

import sys
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

# Add project root to path for absolute imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# =============================================================================
# CONFIGURATION
# =============================================================================

ATTRIBUTE_MAX = 20  # FM attributes are 1-20

# Position-specific attribute weighting (total = 100 for each)
# Based on the user's specification, mapped to individual FM positions
POSITION_WEIGHTS = {
    "GK": {
        "Ref": 25,  # Reflexes
        "One": 20,  # One-on-Ones
        "Han": 15,  # Handling
        "Agi": 15,  # Agility
        "Cnt": 15,  # Concentration
        "Aer": 10,  # Aerial Reach
    },
    "DC": {
        "Pac": 20,  # Pace
        "Acc": 15,  # Acceleration
        "Jum": 20,  # Jumping Reach
        "Str": 15,  # Strength
        "Ant": 15,  # Anticipation
        "Cnt": 15,  # Concentration
    },
    "DL": {
        "Pac": 25,  # Pace
        "Acc": 25,  # Acceleration
        "Sta": 15,  # Stamina
        "Agi": 10,  # Agility
        "Dri": 15,  # Dribbling
        "Wor": 10,  # Work Rate
    },
    "DR": {
        "Pac": 25,  # Pace
        "Acc": 25,  # Acceleration
        "Sta": 15,  # Stamina
        "Agi": 10,  # Agility
        "Dri": 15,  # Dribbling
        "Wor": 10,  # Work Rate
    },
    "DML": {
        "Pac": 25,  # Pace
        "Acc": 25,  # Acceleration
        "Sta": 15,  # Stamina
        "Agi": 10,  # Agility
        "Dri": 15,  # Dribbling
        "Wor": 10,  # Work Rate
    },
    "DMR": {
        "Pac": 25,  # Pace
        "Acc": 25,  # Acceleration
        "Sta": 15,  # Stamina
        "Agi": 10,  # Agility
        "Dri": 15,  # Dribbling
        "Wor": 10,  # Work Rate
    },
    "DMC": {
        "Pac": 15,  # Pace
        "Acc": 15,  # Acceleration
        "Bal": 15,  # Balance
        "Ant": 20,  # Anticipation
        "Cnt": 20,  # Concentration
        "Pas": 15,  # Passing
    },
    "MC": {
        "Pac": 15,  # Pace
        "Acc": 15,  # Acceleration
        "Bal": 15,  # Balance
        "Ant": 20,  # Anticipation
        "Cnt": 20,  # Concentration
        "Pas": 15,  # Passing
    },
    "AMC": {
        "Pac": 15,  # Pace
        "Acc": 15,  # Acceleration
        "Bal": 15,  # Balance
        "Ant": 20,  # Anticipation
        "Cnt": 20,  # Concentration
        "Pas": 15,  # Passing
    },
    "AML": {
        "Pac": 25,  # Pace
        "Acc": 25,  # Acceleration
        "Agi": 15,  # Agility
        "Dri": 20,  # Dribbling
        "Bal": 15,  # Balance
    },
    "AMR": {
        "Pac": 25,  # Pace
        "Acc": 25,  # Acceleration
        "Agi": 15,  # Agility
        "Dri": 20,  # Dribbling
        "Bal": 15,  # Balance
    },
    "ML": {
        "Pac": 25,  # Pace
        "Acc": 25,  # Acceleration
        "Agi": 15,  # Agility
        "Dri": 20,  # Dribbling
        "Bal": 15,  # Balance
    },
    "MR": {
        "Pac": 25,  # Pace
        "Acc": 25,  # Acceleration
        "Agi": 15,  # Agility
        "Dri": 20,  # Dribbling
        "Bal": 15,  # Balance
    },
    "ST": {
        "Pac": 25,  # Pace
        "Acc": 25,  # Acceleration
        "Str": 15,  # Strength
        "Jum": 15,  # Jumping Reach
        "Ant": 10,  # Anticipation
        "Fin": 10,  # Finishing
    },
}

# Position groups for display purposes
POSITION_GROUPS = {
    "GK": "GK",
    "DC": "CB",
    "DL": "FB/WB",
    "DR": "FB/WB",
    "DML": "FB/WB",
    "DMR": "FB/WB",
    "DMC": "CM",
    "MC": "CM",
    "AMC": "CM",
    "AML": "Winger",
    "AMR": "Winger",
    "ML": "Winger",
    "MR": "Winger",
    "ST": "ST",
}

# Attribute name mappings (FM export names -> our standardized names)
ATTRIBUTE_ALIASES = {
    # Physical
    "Pace": "Pac",
    "Acceleration": "Acc",
    "Agility": "Agi",
    "Balance": "Bal",
    "Stamina": "Sta",
    "Strength": "Str",
    "Jumping Reach": "Jum",
    # Technical
    "Dribbling": "Dri",
    "Passing": "Pas",
    "Finishing": "Fin",
    "Handling": "Han",
    "Reflexes": "Ref",
    "One-on-Ones": "One",
    "Aerial Reach": "Aer",
    # Mental
    "Anticipation": "Ant",
    "Concentration": "Cnt",
    "Work Rate": "Wor",
    "Determination": "Det",
}

# Natural position order (matches other tabs)
NATURAL_POSITION_ORDER = [
    'GK', 'DL', 'DC', 'DR',
    'DML', 'DMC', 'DMR',
    'ML', 'MC', 'MR',
    'AML', 'AMC', 'AMR', 'ST'
]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _get_attribute(row: pd.Series, attr_name: str) -> float:
    """Get attribute value from row, checking both standard and aliased names."""
    # Try direct name first
    val = pd.to_numeric(row.get(attr_name, None), errors="coerce")
    if pd.notna(val):
        return float(val)
    
    # Try aliases
    for full_name, short_name in ATTRIBUTE_ALIASES.items():
        if short_name == attr_name:
            # Try full name
            val = pd.to_numeric(row.get(full_name, None), errors="coerce")
            if pd.notna(val):
                return float(val)
    
    return 0.0


def _normalize_attr(value: float) -> float:
    """Normalize attribute from 0-20 scale to 0-100."""
    return float(np.clip(value / ATTRIBUTE_MAX * 100, 0, 100))


def _get_position_group(position: str) -> str:
    """Get the position group for a specific position."""
    return POSITION_GROUPS.get(position, position)


def _parse_positions(pos_string) -> List[str]:
    """Parse positions from various formats."""
    if isinstance(pos_string, list):
        return pos_string
    if isinstance(pos_string, str):
        return [p.strip() for p in pos_string.split(",") if p.strip()]
    return []


# =============================================================================
# CORE EVALUATION FUNCTIONS
# =============================================================================


def calculate_position_score(row: pd.Series, position: str) -> float:
    """
    Calculate weighted score for a specific position.
    Returns score on 0-100 scale.
    """
    weights = POSITION_WEIGHTS.get(position, {})
    if not weights:
        return 0.0
    
    total_weight = sum(weights.values())
    if total_weight == 0:
        return 0.0
    
    weighted_sum = 0.0
    for attr, weight in weights.items():
        value = _get_attribute(row, attr)
        normalized = _normalize_attr(value)
        weighted_sum += normalized * (weight / total_weight)
    
    return weighted_sum


def calculate_ceiling_score(row: pd.Series) -> float:
    """
    STEP 5: Calculate ceiling score based on physical attributes.
    Ceiling Score = (Pace × 0.35) + (Acceleration × 0.35) + (Agility × 0.15) + (Balance × 0.15)
    Returns score on 0-100 scale.
    """
    pace = _get_attribute(row, "Pac")
    acc = _get_attribute(row, "Acc")
    agi = _get_attribute(row, "Agi")
    bal = _get_attribute(row, "Bal")
    
    # Calculate using 0-20 scale then normalize
    raw_ceiling = (pace * 0.35) + (acc * 0.35) + (agi * 0.15) + (bal * 0.15)
    # Normalize to 0-100 (max possible is 20)
    ceiling_score = (raw_ceiling / ATTRIBUTE_MAX) * 100
    
    return float(np.clip(ceiling_score, 0, 100))


def evaluate_player(row: pd.Series) -> Dict[str, Any]:
    """
    Main evaluation function implementing all steps.
    Evaluates player for their best position and returns results.
    """
    # Parse basic info
    name = row.get("Name", "Unknown")
    age = pd.to_numeric(row.get("Age", row.get("Age_int", None)), errors="coerce")
    if pd.isna(age):
        age = 0
    age = int(age)
    
    positions = _parse_positions(row.get("Positions", row.get("Nat", "")))
    
    # Get physical attributes
    pace = _get_attribute(row, "Pac")
    acc = _get_attribute(row, "Acc")
    agi = _get_attribute(row, "Agi")
    bal = _get_attribute(row, "Bal")
    anticipation = _get_attribute(row, "Ant")
    concentration = _get_attribute(row, "Cnt")
    determination = _get_attribute(row, "Det")
    
    # ========================================================================
    # STEP 5: CEILING SCORE (calculate early for later use)
    # ========================================================================
    ceiling_score = calculate_ceiling_score(row)
    
    # ========================================================================
    # Evaluate for each position the player can play
    # ========================================================================
    position_scores = {}
    position_results = {}
    
    for pos in positions:
        if pos not in POSITION_WEIGHTS:
            continue
        
        # ========================================================================
        # STEP 1: HARD PHYSICAL FLOOR (for outfield players)
        # ========================================================================
        if pos != "GK":
            if pace < 9 or acc < 9:
                position_scores[pos] = -1  # Mark as invalid
                position_results[pos] = {
                    "score": 0,
                    "category": "Bin",
                    "tags": ["Physically Unviable"],
                    "weaknesses": [],
                    "strengths": [],
                }
                if pace < 9:
                    position_results[pos]["weaknesses"].append("Low Pace")
                if acc < 9:
                    position_results[pos]["weaknesses"].append("Low Acceleration")
                continue
        
        # ========================================================================
        # STEP 3: BASE SCORE
        # ========================================================================
        base_score = calculate_position_score(row, pos)
        
        # ========================================================================
        # STEP 2: PHYSICAL RISK BAND
        # ========================================================================
        physical_risk = False
        if pace < 12 or acc < 12:
            base_score -= 10
            physical_risk = True
        
        # ========================================================================
        # STEP 4: ELITE PHYSICAL BOOST
        # ========================================================================
        elite_prospect = False
        if pace >= 15 and acc >= 15:
            if anticipation >= 13 or concentration >= 13:
                base_score += 10
                elite_prospect = True
        
        # Cap score at 100
        base_score = min(base_score, 100)
        
        # ========================================================================
        # STEP 7: DEVELOPMENT HEURISTIC (for young players with low physicals)
        # ========================================================================
        if age <= 17 and (9 <= pace <= 11 or 9 <= acc <= 11):
            if anticipation < 10 and concentration < 10 and determination < 10:
                position_scores[pos] = base_score
                position_results[pos] = {
                    "score": base_score,
                    "category": "Bin",
                    "tags": ["Low Mental Attributes"],
                    "weaknesses": [],
                    "strengths": [],
                }
                continue
        
        # ========================================================================
        # STEP 8: CATEGORY ASSIGNMENT (initial)
        # ========================================================================
        category = "Bin"
        if base_score >= 75:
            category = "First Team Ready"
        elif base_score >= 60:
            category = "Develop"
        
        # ========================================================================
        # AGE-ADJUSTED LOGIC (STEP 6)
        # ========================================================================
        if age <= 17:
            # Cannot be "First Team Ready"
            if category == "First Team Ready":
                category = "Develop"
        elif age >= 21:
            # Cannot be "Develop"
            if category == "Develop":
                category = "First Team Ready" if base_score >= 65 else "Bin"
        
        # ========================================================================
        # STEP 9: OVERRIDE RULES
        # ========================================================================
        # Override UP: Elite physicals guarantee at least "Develop"
        if pace >= 15 and acc >= 15:
            if category == "Bin":
                category = "Develop"
        
        # Override DOWN: Very low physicals always bin
        if pace <= 10 and acc <= 10:
            category = "Bin"
        
        # ========================================================================
        # STEP 10: FINAL ADJUSTMENT USING CEILING
        # ========================================================================
        if ceiling_score >= 80:
            if category == "Bin":
                # Only keep bin if physical floor failed (already handled in Step 1)
                category = "Develop"
        
        if ceiling_score <= 65 and age >= 18:
            if category == "Develop":
                category = "Bin"
        
        # ========================================================================
        # TAGS
        # ========================================================================
        tags = []
        if elite_prospect:
            tags.append("Elite Prospect")
        if physical_risk:
            tags.append("Development Risk")
        if pace + acc >= 30:
            tags.append("Physical Monster")
        if concentration < 10:
            tags.append("High Risk")
        
        # ========================================================================
        # KEY STRENGTHS (top 3 attributes for position)
        # ========================================================================
        weights = POSITION_WEIGHTS.get(pos, {})
        attr_values = {}
        for attr in weights.keys():
            attr_values[attr] = _get_attribute(row, attr)
        
        sorted_attrs = sorted(attr_values.items(), key=lambda x: x[1], reverse=True)
        strengths = [f"{k}: {v}" for k, v in sorted_attrs[:3]]
        
        # ========================================================================
        # WEAKNESS FLAGS
        # ========================================================================
        weaknesses = []
        if pos != "GK":
            if pace < 12:
                weaknesses.append("Low Pace")
            if acc < 12:
                weaknesses.append("Low Acceleration")
            if pace < 9:
                weaknesses.append("Critical Low Pace")
            if acc < 9:
                weaknesses.append("Critical Low Acceleration")
        
        position_scores[pos] = base_score
        position_results[pos] = {
            "score": round(base_score, 2),
            "category": category,
            "tags": tags,
            "weaknesses": weaknesses,
            "strengths": strengths,
        }
    
    # ========================================================================
    # Determine best position and overall result
    # ========================================================================
    if not position_scores:
        # Player has no valid positions
        return {
            "Name": name,
            "Age": age,
            "Positions": ", ".join(positions) if positions else "N/A",
            "Best_Position": "N/A",
            "Position_Group": "Unknown",
            "Score": 0.0,
            "Ceiling_Score": round(ceiling_score, 2),
            "Category": "Bin",
            "Tags": "",
            "Key_Strengths": "",
            "Weakness_Flags": "",
            "All_Positions_Data": {},
        }
    
    # Find best valid position (highest score)
    valid_positions = {pos: score for pos, score in position_scores.items() if score >= 0}
    
    if valid_positions:
        best_pos = max(valid_positions, key=valid_positions.get)
        best_result = position_results[best_pos]
    else:
        # All positions failed physical floor
        best_pos = positions[0] if positions else "N/A"
        best_result = {
            "score": 0,
            "category": "Bin",
            "tags": ["Physically Unviable"],
            "weaknesses": [],
            "strengths": [],
        }
    
    return {
        "Name": name,
        "Age": age,
        "Positions": ", ".join(positions) if positions else "N/A",
        "Best_Position": best_pos,
        "Position_Group": _get_position_group(best_pos),
        "Score": best_result["score"],
        "Ceiling_Score": round(ceiling_score, 2),
        "Category": best_result["category"],
        "Tags": ", ".join(best_result["tags"]) if best_result["tags"] else "",
        "Key_Strengths": ", ".join(best_result["strengths"]) if best_result["strengths"] else "",
        "Weakness_Flags": ", ".join(best_result["weaknesses"]) if best_result["weaknesses"] else "",
        "All_Positions_Data": {pos: position_results[pos] for pos in position_results},
    }


def add_fm24_evaluation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add FM24 evaluation columns to dataframe.
    Returns dataframe with added columns for best position evaluation.
    """
    df = df.copy()
    
    # Apply evaluation to each row
    evaluations = df.apply(evaluate_player, axis=1)
    
    # Extract columns
    df["fm24_score"] = evaluations.apply(lambda x: x["Score"])
    df["fm24_ceiling"] = evaluations.apply(lambda x: x["Ceiling_Score"])
    df["fm24_category"] = evaluations.apply(lambda x: x["Category"])
    df["fm24_tags"] = evaluations.apply(lambda x: x["Tags"])
    df["fm24_strengths"] = evaluations.apply(lambda x: x["Key_Strengths"])
    df["fm24_weaknesses"] = evaluations.apply(lambda x: x["Weakness_Flags"])
    df["fm24_best_position"] = evaluations.apply(lambda x: x["Best_Position"])
    df["fm24_position_group"] = evaluations.apply(lambda x: x["Position_Group"])
    
    # Add position-specific score columns
    for pos in NATURAL_POSITION_ORDER:
        col_name = f"fm24_{pos}_score"
        df[col_name] = evaluations.apply(lambda x, p=pos: x["All_Positions_Data"].get(p, {}).get("score", None))
    
    # Add position-specific category columns
    for pos in NATURAL_POSITION_ORDER:
        col_name = f"fm24_{pos}_category"
        df[col_name] = evaluations.apply(lambda x, p=pos: x["All_Positions_Data"].get(p, {}).get("category", None))
    
    return df


def get_evaluation_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Get a summary of FM24 evaluations for the latest extract.
    Returns a clean dataframe with evaluation results.
    """
    # Filter to latest export only
    if "is_latest_export" in df.columns:
        latest_df = df[df["is_latest_export"]].copy()
    else:
        latest_df = df.sort_values("Date").groupby("UID").tail(1).copy()
    
    # Select relevant columns
    summary_cols = [
        "Name", "Age", "Positions",
        "fm24_best_position", "fm24_position_group",
        "fm24_score", "fm24_ceiling", "fm24_category",
        "fm24_tags", "fm24_strengths", "fm24_weaknesses",
    ]
    
    # Ensure all columns exist
    existing_cols = [c for c in summary_cols if c in latest_df.columns]
    summary_df = latest_df[existing_cols].copy()
    
    # Rename for display - ALL columns that need renaming
    summary_df = summary_df.rename(columns={
        "fm24_best_position": "Best_Position",
        "fm24_position_group": "Position_Group",
        "fm24_category": "Category",
    })
    
    # Sort by score descending
    if "fm24_score" in summary_df.columns:
        summary_df = summary_df.sort_values("fm24_score", ascending=False)
    
    return summary_df.reset_index(drop=True)


def get_position_filter_evaluations(df: pd.DataFrame, position: str) -> pd.DataFrame:
    """
    Get evaluations filtered to players who can play a specific position.
    Shows the score/category for that specific position, not just best position.
    """
    # Filter to latest export only
    if "is_latest_export" in df.columns:
        latest_df = df[df["is_latest_export"]].copy()
    else:
        latest_df = df.sort_values("Date").groupby("UID").tail(1).copy()
    
    score_col = f"fm24_{position}_score"
    cat_col = f"fm24_{position}_category"
    
    # Check if columns exist
    if score_col not in latest_df.columns or cat_col not in latest_df.columns:
        return pd.DataFrame()
    
    # Filter to players who have a valid score for this position (not None and >= 0)
    pos_df = latest_df[latest_df[score_col].notna() & (latest_df[score_col] >= 0)].copy()
    
    if pos_df.empty:
        return pd.DataFrame()
    
    # Sort by position-specific score descending
    pos_df = pos_df.sort_values(score_col, ascending=False)
    
    # Build result with position-specific data
    result = pd.DataFrame({
        "Name": pos_df["Name"],
        "Age": pos_df["Age"],
        "Positions": pos_df["Positions"],
        "Best_Position": pos_df["fm24_best_position"],
        "Position_Group": pos_df["fm24_position_group"],
        "Score": pos_df[score_col].round(2),
        "Ceiling": pos_df["fm24_ceiling"].round(2),
        "Category": pos_df[cat_col],
        "Tags": pos_df["fm24_tags"],
        "Strengths": pos_df["fm24_strengths"],
        "Weaknesses": pos_df["fm24_weaknesses"],
    })
    
    return result.reset_index(drop=True)


def get_position_specific_evaluations(df: pd.DataFrame, position: str) -> pd.DataFrame:
    """
    Get evaluations for a specific position.
    """
    if "is_latest_export" in df.columns:
        latest_df = df[df["is_latest_export"]].copy()
    else:
        latest_df = df.sort_values("Date").groupby("UID").tail(1).copy()
    
    score_col = f"fm24_{position}_score"
    cat_col = f"fm24_{position}_category"
    
    # Filter to players who can play this position and have a score
    if score_col not in latest_df.columns:
        return pd.DataFrame()
    
    pos_df = latest_df[latest_df[score_col].notna()].copy()
    pos_df = pos_df.sort_values(score_col, ascending=False)
    
    # Select display columns
    display_cols = ["Name", "Age", "Positions", score_col, "fm24_ceiling", cat_col, "fm24_tags"]
    existing_cols = [c for c in display_cols if c in pos_df.columns]
    
    result = pos_df[existing_cols].copy()
    result = result.rename(columns={
        score_col: "Score",
        cat_col: "Category",
        "fm24_ceiling": "Ceiling",
        "fm24_tags": "Tags",
    })
    
    return result.reset_index(drop=True)


def get_players_by_category(df: pd.DataFrame, category: str) -> pd.DataFrame:
    """
    Get players filtered by FM24 category (based on best position).
    """
    if "fm24_category" not in df.columns:
        return pd.DataFrame()
    
    return df[df["fm24_category"] == category].copy()


# =============================================================================
# STANDALONE USAGE
# =============================================================================

if __name__ == "__main__":
    # Test with sample data covering different scenarios
    sample_data = [
        # Elite physical striker - should be First Team Ready
        {
            "Name": "Elite Striker",
            "Age": 22,
            "Positions": ["ST"],
            "Pac": 17, "Acc": 16, "Agi": 15, "Bal": 14,
            "Str": 15, "Jum": 14, "Ant": 14, "Fin": 15,
            "Cnt": 13, "Det": 15,
        },
        # Young winger with high ceiling - should be Develop
        {
            "Name": "Young Winger",
            "Age": 17,
            "Positions": ["AML", "AMR"],
            "Pac": 14, "Acc": 15, "Agi": 16, "Bal": 13,
            "Dri": 14, "Ant": 11, "Cnt": 10, "Det": 12,
        },
        # Slow CB - should be Bin
        {
            "Name": "Slow CB",
            "Age": 24,
            "Positions": ["DC"],
            "Pac": 8, "Acc": 8, "Agi": 9, "Bal": 10,
            "Str": 15, "Jum": 16, "Ant": 14, "Cnt": 13,
        },
        # GK with good reflexes
        {
            "Name": "Top GK",
            "Age": 25,
            "Positions": ["GK"],
            "Ref": 17, "One": 16, "Han": 15, "Agi": 14,
            "Cnt": 15, "Aer": 13, "Pac": 10, "Acc": 9,
        },
        # Physical monster FB
        {
            "Name": "Physical FB",
            "Age": 20,
            "Positions": ["DR", "DML"],
            "Pac": 16, "Acc": 16, "Agi": 13, "Bal": 12,
            "Sta": 15, "Dri": 12, "Wor": 14, "Ant": 12, "Cnt": 11,
        },
        # Low physicals CM - Development Risk
        {
            "Name": "Technical CM",
            "Age": 19,
            "Positions": ["MC"],
            "Pac": 11, "Acc": 11, "Agi": 13, "Bal": 14,
            "Ant": 15, "Cnt": 15, "Pas": 16, "Det": 14,
        },
    ]

    print("=" * 80)
    print("FM24 PLAYER EVALUATION SYSTEM - TEST RESULTS")
    print("=" * 80)

    for player in sample_data:
        result = evaluate_player(pd.Series(player))
        print(f"\nPlayer: {result['Name']} (Age: {result['Age']})")
        print(f"  Positions: {result['Positions']}")
        print(f"  Best Position: {result['Best_Position']} ({result['Position_Group']})")
        print(f"  Score: {result['Score']}")
        print(f"  Ceiling: {result['Ceiling_Score']}")
        print(f"  Category: {result['Category']}")
        print(f"  Tags: {result['Tags'] if result['Tags'] else 'None'}")
        print(f"  Strengths: {result['Key_Strengths'] if result['Key_Strengths'] else 'None'}")
        print(f"  Weaknesses: {result['Weakness_Flags'] if result['Weakness_Flags'] else 'None'}")
        
        # Show all position scores
        if result['All_Positions_Data']:
            print("  Position Breakdown:")
            for pos, data in result['All_Positions_Data'].items():
                print(f"    {pos}: Score={data['score']}, Category={data['category']}")