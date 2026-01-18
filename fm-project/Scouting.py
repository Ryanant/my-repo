import pandas as pd
import numpy as np
import glob
import os
import re
from itertools import product
import unicodedata
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output
import dash_bootstrap_components as dbc

# ------------------------------------------------------
# Load MOST RECENT HTML
# ------------------------------------------------------
folder_path = r"C:/Users/jackj/Documents/Sports Interactive/Football Manager 2024/Python Exports/Scouting/*.html"
html_files = glob.glob(folder_path)

if not html_files:
    raise FileNotFoundError(f"No HTML files found. Checked path:\n{folder_path}")

latest_html = max(html_files, key=os.path.getctime)

with open(latest_html, 'r', encoding='utf-8') as f:
    html_content = f.read()

df = pd.read_html(html_content)[0]
print(f"Loaded: {latest_html}")

# ------------------------------------------------------
# Normalize text for special characters
# ------------------------------------------------------
def normalize_text(s):
    return unicodedata.normalize('NFC', str(s))

df['Name'] = df['Name'].apply(normalize_text)
df['Transfer Value'] = df['Transfer Value'].apply(normalize_text)

# ------------------------------------------------------
# Original coefficients for scoring
# ------------------------------------------------------
position_coeffs = {
    'GK': {'Agi': 0.014640, 'Ref': 0.012837, 'Aer': 0.011812, 'Thr': 0.007465,
           'Com': 0.007436, 'Han': 0.006255, 'Dec': 0.005089, 'TRO': -0.003310},
    'DLR': {'Pac': 0.018991, 'Jum': 0.014582, 'Acc': 0.012670, 'Ant': 0.012269,
            'Cnt': 0.009911, 'Dri': 0.008246, 'Cmp': 0.007720, 'Cro': 0.006812},
    'DC': {'Jum': 0.022608, 'Pac': 0.015882, 'Acc': 0.013536, 'Wor': 0.010819,
           'Ant': 0.010326, 'Pos_x': 0.008864, 'Pas': 0.008826, 'Cnt': 0.008358},
    'DMR': {'Pac': 0.019196, 'Acc': 0.018585, 'Jum': 0.013761, 'Cmp': 0.011762,
             'Vis': 0.010025, 'Cro': 0.009596, 'Wor': 0.008166, 'Det': 0.005121},
    'DML': {'Pac': 0.019196, 'Acc': 0.018585, 'Jum': 0.013761, 'Cmp': 0.011762,
             'Vis': 0.010025, 'Cro': 0.009596, 'Wor': 0.008166, 'Det': 0.005121},
    'DMC': {'Acc': 0.020572, 'Ant': 0.013047, 'Sta': 0.010352, 'Jum': 0.009796,
            'Cmp': 0.009470, 'Pas': 0.009114, 'Lon': 0.007952, 'Dri': 0.007338},
    'AMC': {'Pac': 0.016763, 'Acc': 0.016348, 'Cnt': 0.013697, 'Cmp': 0.012813,
            'Tec': 0.011647, 'Lon': 0.009914, 'Jum': 0.009524, 'Dri': 0.008679},
    'ST': {'Jum': 0.020557, 'Pac': 0.020096, 'Acc': 0.014496, 'Cnt': 0.013675,
           'Bal': 0.012043, 'Dri': 0.010739, 'Vis': 0.009392, 'Cmp': 0.009161}
}

# ------------------------------------------------------
# Score calculator
# ------------------------------------------------------
def calculate_score(row, coeff_dict):
    total = 0
    for attr, weight in coeff_dict.items():
        total += row.get(attr, 0) * weight
    return total

# ------------------------------------------------------
# Calculate raw scores for all 9 positions
# ------------------------------------------------------
for pos_name, coeffs in position_coeffs.items():
    df[f"{pos_name}_score"] = df.apply(lambda r: round(calculate_score(r, coeffs), 2), axis=1)

# ------------------------------------------------------
# Remove bottom 25% for ALL scores unless Club = Portsmouth
# ------------------------------------------------------
score_columns = [f"{p}_score" for p in position_coeffs.keys()]
thresholds = {col: df[col].quantile(0.9) for col in score_columns}

def is_bottom_quartile_row(row):
    return all(row[col] <= thresholds[col] for col in score_columns)

mask_bottom_25 = df.apply(is_bottom_quartile_row, axis=1)
df = df[(~mask_bottom_25) | (df['Club'] == 'Portsmouth')]

# ------------------------------------------------------
# Position parsing
# ------------------------------------------------------
def process_segment(segment):
    segment = segment.replace("D/", "Z/").replace("D ", "Z ")
    sides_match = re.findall(r'\((.*?)\)', segment)
    sides = sides_match[0] if sides_match else 'C'
    lines = segment.replace(f"({sides})", "").replace("/", "") \
                   .replace("AM", "A").replace("DM", "O").replace("ST", "F") \
                   .replace("WB", "O").replace("Z", "D").strip()
    return [f"{x}{y}" for x, y in product(lines, sides)]

def combine_segment(segments):
    result = []
    segments = segments.replace('GK', 'G (C)')
    segments = re.sub(r'\bDM\b(,?)', r'DM (C)\1', segments)
    for segment in segments.split(','):
        result.extend(process_segment(segment.strip()))
    return result

def replace_values(lst):
    mapping = {
        'O': 'DM', 'GC': 'GK', 'FC': 'ST', 'A': 'AM',
        'DMR': 'WBR', 'DML': 'WBL', 'DMC': 'DM'
    }
    return [re.sub('|'.join(mapping.keys()), lambda m: mapping[m.group(0)], item) for item in lst]

def apply_combinations(df, column):
    df["Positions"] = df[column].apply(combine_segment).apply(replace_values)
    unique_values = set(item for sublist in df['Positions'] for item in sublist)
    for position in unique_values:
        df[position] = df.apply(lambda x: 1 if position in x["Positions"] else 0, axis=1)
    return df, unique_values

df, unique_positions = apply_combinations(df, 'Position')

# ------------------------------------------------------
# Override scores: if player cannot play position → 0
# ------------------------------------------------------
for pos in position_coeffs.keys():
    score_col = f"{pos}_score"
    if score_col in df.columns:
        df[score_col] = df.apply(
            lambda x: x[score_col] if x.get(pos, 0) == 1 else 0,
            axis=1
        )

# ------------------------------------------------------
# Display ONLY these 6 positions
# ------------------------------------------------------
display_positions = ["GK", "DC", "DMR", "DML", "DMC", "AMC", "ST"]
display_score_columns = [f"{p}_score" for p in display_positions]

# ------------------------------------------------------
# Prepare Dash table
# ------------------------------------------------------
position_columns = sorted(unique_positions)
columns_to_include = (
    ["Name", "Club", "Transfer Value", "Age", "Position"]
    + display_score_columns
    + position_columns
    + ["Link"]
)

df['Link'] = f"[Open HTML](file:///{latest_html})"

output_df = df[columns_to_include]

# ------------------------------------------------------
# Dash App
# ------------------------------------------------------
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

min_age = int(df['Age'].min())
max_age = int(df['Age'].max())

positions_dropdown = ['All'] + position_columns

app.layout = dbc.Container([

    html.H1("FM Scouting Raw Scores", style={'text-align': 'center', 'margin-bottom': '20px'}),

    dbc.Row([
        dbc.Col([
            html.Label("Age Range"),
            dcc.RangeSlider(
                id='age_slider',
                min=min_age,
                max=max_age,
                value=[min_age, max_age],
                marks={i: str(i) for i in range(min_age, max_age+1)},
                step=1,
                tooltip={"placement": "bottom", "always_visible": False}
            )
        ], width=4),

        dbc.Col([
            html.Label("Position"),
            dcc.Dropdown(
                id='position_dropdown',
                options=[{'label': pos, 'value': pos} for pos in positions_dropdown],
                value='All',
                clearable=False
            )
        ], width=3),

        dbc.Col([
            html.Label("Club Filter"),
            dcc.RadioItems(
                id='portsmouth_filter',
                options=[
                    {'label': 'All Clubs', 'value': 'All'},
                    {'label': 'Portsmouth Only', 'value': 'True'},
                    {'label': 'Exclude Portsmouth', 'value': 'False'}
                ],
                value='All',
                inline=True
            )
        ], width=5)
    ], style={'margin-bottom': '20px'}),

    dash_table.DataTable(
        id='scores_table',
        columns=[
            {"name": col, "id": col, "presentation": "markdown"} if col=="Link"
            else {"name": col, "id": col}
            for col in output_df.columns
        ],
        data=output_df.to_dict('records'),
        page_size=20,
        sort_action="native",
        filter_action="native",
        style_table={'overflowX': 'auto'},
        style_cell={'fontSize': 12, 'padding': '5px'},
    )
], fluid=True)

# ------------------------------------------------------
# Callback
# ------------------------------------------------------
@app.callback(
    Output('scores_table', 'data'),
    Input('age_slider', 'value'),
    Input('position_dropdown', 'value'),
    Input('portsmouth_filter', 'value')
)
def filter_table(age_range, position, portsmouth_filter):

    filtered_df = output_df[
        (output_df['Age'] >= age_range[0]) &
        (output_df['Age'] <= age_range[1])
    ]

    if position != 'All':
        filtered_df = filtered_df[filtered_df[position] == 1]

    if portsmouth_filter == 'True':
        filtered_df = filtered_df[filtered_df['Club'] == 'Portsmouth']
    elif portsmouth_filter == 'False':
        filtered_df = filtered_df[filtered_df['Club'] != 'Portsmouth']

    return filtered_df.to_dict('records')

# ------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
