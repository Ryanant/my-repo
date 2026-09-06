import re
from itertools import product
import pandas as pd


def _process_segment(segment: str):
    segment = segment.replace("D/", "Z/").replace("D ", "Z ")
    sides = re.findall(r'\((.*?)\)', segment)[0]
    lines = (
        segment.replace(f"({sides})", "")
        .replace("/", "")
        .replace("AM", "A")
        .replace("DM", "O")
        .replace("ST", "F")
        .replace("WB", "O")
        .replace("Z", "D")
        .strip()
    )
    return [f"{x}{y}" for x, y in product(lines, sides)]


def _combine_segment(segments: str):
    segments = segments.replace('GK', 'G (C)')
    segments = re.sub(r'\bDM\b(,?)', r'DM (C)\1', segments)

    result = []
    for segment in segments.split(','):
        result.extend(_process_segment(segment.strip()))
    return result


def _replace_values(lst):
    mapping = {
        'O': 'DM', 'GC': 'GK', 'FC': 'ST', 'A': 'AM',
        'DMR': 'WBR', 'DML': 'WBL', 'DMC': 'DM'
    }
    pattern = re.compile('|'.join(mapping.keys()))
    return [pattern.sub(lambda m: mapping[m.group(0)], item) for item in lst]


def expand_positions(df: pd.DataFrame, column: str = "Position"):
    df["Positions"] = (
        df[column]
        .apply(_combine_segment)
        .apply(_replace_values)
    )

    unique_positions = sorted(
        {p for sub in df['Positions'] for p in sub}
    )

    for pos in unique_positions:
        df[pos] = df['Positions'].apply(lambda x: int(pos in x))

    return df, unique_positions
