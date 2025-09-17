# coding: utf-8

# -----------------------------
# Imports
import os
import io
import time
import re
from itertools import product
import numpy as np

import pandas as pd
from bs4 import BeautifulSoup as bs

import dash
from dash import dcc, html, dash_table
import dash_bootstrap_components as dbc
from dash.dependencies import Input, Output

# Pandas display options
pd.set_option('display.max_rows', 150)
pd.set_option('display.max_columns', 63)

# -----------------------------
# File paths and folder setup
python_exports = "C:/Users/jackj/Documents/Sports Interactive/Football Manager 2024/Python Exports"
current_save = "Leverkusen"
all_players_file = "all_players_data.csv"

folder_path = os.path.join(python_exports, current_save)
all_players_file_path = os.path.join(folder_path, all_players_file)
all_folder_files = os.listdir(folder_path)

# -----------------------------
# Identify HTML files
all_html_files = [
    f.replace('.html', '') + ' 00:00:01'
    for f in all_folder_files if f.endswith('.html')
]

# -----------------------------
# Load existing exported dates
if not os.path.exists(all_players_file_path):
    exported_dates = pd.DataFrame({'Date': [1, 2]})
else:
    exported_dates = pd.read_csv(all_players_file_path)

exported_dates = exported_dates.Date.unique().tolist()

# -----------------------------
# Process new HTML exports
for file in all_html_files:
    if file not in exported_dates:
        file_name = file.replace(' 00:00:01', '')
        full_path = os.path.join(folder_path, file_name + '.html')

        fm_export = bs(open(full_path, encoding="utf8"), "html.parser").find('table')
        raw_list = pd.read_html(io.StringIO(str(fm_export)))
        raw_table = pd.DataFrame(raw_list[0])

        date = file_name.split('.')[0] + ' 00:00:01'
        raw_table['Date'] = pd.to_datetime(date, format="%Y-%m-%d %H:%M:%S")
        raw_table['DoB'] = pd.to_datetime(raw_table["DoB"].str.split(" ").str[0], format="%d/%m/%Y")
        raw_table['DoB'] += pd.Timedelta(seconds=1)
        raw_table['Age'] = (raw_table['Date'] - raw_table['DoB']).dt.days / 365.25
        raw_table['Acc'] = pd.to_numeric(raw_table['Acc'], errors='coerce')
        raw_table = raw_table.dropna(subset=['Acc'])

        if not os.path.exists(all_players_file_path):
            raw_table.to_csv(all_players_file_path, index=False)
            print(f"Created file: {all_players_file_path}")
        else:
            timestr = time.strftime("%Y%m%d-%H%M%S")
            existing_df = pd.read_csv(all_players_file_path)
            backup_file = os.path.join(folder_path, f'all_players_data_{timestr}.csv')
            existing_df.to_csv(backup_file, index=False)

            combined_df = pd.concat([existing_df, raw_table]).drop_duplicates().reset_index(drop=True)
            combined_df.to_csv(all_players_file_path, index=False)
            print(f"Updated file: {all_players_file_path}")

# -----------------------------
# Load full player dataset
raw_table = pd.read_csv(all_players_file_path)

# -----------------------------
# Position processing functions
def process_segment(segment):
    segment = segment.replace("D/", "Z/").replace("D ", "Z ")
    sides = re.findall(r'\((.*?)\)', segment)[0]
    lines = segment.replace(f"({sides})", "").replace("/", "") \
                   .replace("AM", "A").replace("DM", "O").replace('ST','F') \
                   .replace("WB","O").replace("Z","D").strip()
    return [f"{x}{y}" for x, y in product(lines, sides)]

def combine_segment(segments):
    result = []
    segments = segments.replace('GK','G (C)')
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
    return df

# -----------------------------
# Apply position combinations
df = apply_combinations(raw_table, 'Position')

unique_values = set(item for sublist in df['Positions'] for item in sublist)
for position in unique_values:
    df[position] = df.apply(lambda x: 1 if position in x["Positions"] else 0, axis=1)

# -----------------------------
# Coefficient-based rating system
position_coeffs = {
    'GK': {
        'Agi': 0.014640, 'Ref': 0.012837, 'Aer': 0.011812, 'Thr': 0.007465,
        'Com': 0.007436, 'Han': 0.006255, 'Dec': 0.005089, 'TRO': -0.003310
    },
    'DLR': {
        'Pac': 0.018991, 'Jum': 0.014582, 'Acc': 0.012670, 'Ant': 0.012269,
        'Cnt': 0.009911, 'Dri': 0.008246, 'Cmp': 0.007720, 'Cro': 0.006812
    },
    'DC': {
        'Jum': 0.022608, 'Pac': 0.015882, 'Acc': 0.013536, 'Wor': 0.010819,
        'Ant': 0.010326, 'Pos_x': 0.008864, 'Pas': 0.008826, 'Cnt': 0.008358
    },
    'WBLR': {
        'Pac': 0.019196, 'Acc': 0.018585, 'Jum': 0.013761, 'Cmp': 0.011762,
        'Vis': 0.010025, 'Cro': 0.009596, 'Wor': 0.008166, 'Det': 0.005121
    },
    'DMC': {
        'Acc': 0.020572, 'Ant': 0.013047, 'Sta': 0.010352, 'Jum': 0.009796,
        'Cmp': 0.009470, 'Pas': 0.009114, 'Lon': 0.007952, 'Dri': 0.007338
    },
    'MLR': {
        'Pac': 0.020497, 'Dri': 0.014018, 'Acc': 0.012883, 'Cmp': 0.012072,
        'Vis': 0.011542, 'Jum': 0.011150, 'Cro': 0.010598, 'Sta': 0.009658
    },
    'MC': {
        'Ant': 0.014011, 'Acc': 0.012595, 'Cmp': 0.012589, 'Pac': 0.012156,
        'Cro': 0.010100, 'Dri': 0.008134, 'Jum': 0.007918, 'Str': 0.006528
    },
    'AMLR': {
        'Pac': 0.023458, 'Acc': 0.019640, 'Ant': 0.015160, 'Cro': 0.014857,
        'Dri': 0.013533, 'Jum': 0.013029, 'Tec': 0.012662, 'Cmp': 0.012295
    },
    'AMC': {
        'Pac': 0.016763, 'Acc': 0.016348, 'Cnt': 0.013697, 'Cmp': 0.012813,
        'Tec': 0.011647, 'Lon': 0.009914, 'Jum': 0.009524, 'Dri': 0.008679
    },
    'ST': {
        'Jum': 0.020557, 'Pac': 0.020096, 'Acc': 0.014496, 'Cnt': 0.013675,
        'Bal': 0.012043, 'Dri': 0.010739, 'Vis': 0.009392, 'Cmp': 0.009161
    }
}

def calculate_position_score(row, coeffs):
    score = 0
    for attr, weight in coeffs.items():
        if attr == 'Acc Agi':
            score += np.sqrt(row['Acc'] * row['Agi']) * weight
        elif attr == 'Jum^':
            score += (row['Jum'] ** 2) * weight
        else:
            score += row.get(attr, 0) * weight
    return score

df['is_latest_export'] = df['Date'] == df['Date'].max()

all_unique_positions = set([pos for sublist in df['Positions'] for pos in sublist])

# Compute raw ratings for all positions
def get_key_for_pos(pos):
    if pos in ['ML','MR']:
        return 'MLR'
    elif pos in ['DL','DR']:
        return 'DLR'
    elif pos in ['DML','DMR']:
        return 'WBLR'
    elif pos in ['AML','AMR']:
        return 'AMLR'
    elif pos in position_coeffs:
        return pos
    return None

for pos in all_unique_positions:
    key = get_key_for_pos(pos)
    if key:
        df[f'{pos}_rating'] = df.apply(lambda x: calculate_position_score(x, position_coeffs[key]), axis=1)
    else:
        df[f'{pos}_rating'] = 0

# -----------------------------
# Relative percentages
max_values_by_pos = {}
for pos in all_unique_positions:
    pos_col = f'{pos}_rating'
    eligible_players = df[df[pos] == 1]
    if not eligible_players.empty:
        max_values_by_pos[pos_col] = eligible_players[pos_col].max()
    else:
        max_values_by_pos[pos_col] = np.nan

for pos in all_unique_positions:
    pos_col = f'{pos}_rating'
    max_val = max_values_by_pos[pos_col]
    if pd.notna(max_val) and max_val > 0:
        df[f'{pos}_%'] = (df[pos_col] / max_val * 100).round(2)
    else:
        df[f'{pos}_%'] = 0

percentage_columns = [f'{pos}_%' for pos in all_unique_positions]

# -----------------------------
df['Positions_filter'] = df['Positions'].apply(lambda x: ', '.join(x) + ', All')
df['Positions'] = df['Positions'].apply(lambda x: ', '.join(x))

viz_df = df[['Name','Club','Age','Positions','Nat','Transfer Value','Positions_filter'] +
            percentage_columns +
            list(all_unique_positions) +   # keep for toggle logic
            ['is_latest_export']].round(2)

viz_df = viz_df[viz_df['is_latest_export']==True]
viz_df['Age_int'] = viz_df['Age'].apply(np.floor).astype(int)

# -----------------------------
# Natural column order for % ratings
natural_order = ['GK','DL','DC','DR','DML','DMC','DMR','ML','MC','MR','AML','AMC','AMR','ST']
rating_columns_ordered = [f'{pos}_%' for pos in natural_order if f'{pos}_%' in viz_df.columns]

# -----------------------------
# Dash App
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

@app.callback(
    Output('my_squad', 'data'),
    Output('my_squad', 'columns'),
    [
        Input('age_range_slider', 'value'),
        Input('position_filter', 'value'),
        Input('club_filter', 'value'),
        Input('name_filter', 'value'),
        Input('show_all_toggle', 'value')
    ]
)
def update_datatable(selected_age_range, selected_positions, club_filter, name_filter, show_all_toggle):
    df_filtering = viz_df.copy()
    df_filtering['Positions_filter'] = df_filtering['Positions_filter'].str.split(', ')

    # Apply position filter
    if 'All' not in selected_positions:
        df_filtering = df_filtering[df_filtering['Positions_filter'].apply(
            lambda x: any(pos in x for pos in selected_positions)
        )]
    df_filtering['Positions_filter'] = df_filtering['Positions_filter'].apply(lambda x: ', '.join(x))

    # Apply age filter
    df_filtering = df_filtering[
        (selected_age_range[0] <= df_filtering['Age_int']) &
        (df_filtering['Age_int'] <= selected_age_range[1])
    ]

    # Apply club filter
    if club_filter:
        df_filtering = df_filtering[df_filtering['Club'].str.contains(club_filter, case=False, na=False)]

    # Apply name filter
    if name_filter:
        df_filtering = df_filtering[df_filtering['Name'].str.contains(name_filter, case=False, na=False)]

    # -----------------------------
    # Toggle handling: show all ratings or only positions player can play
    if not show_all_toggle:
        for pos in all_unique_positions:
            pos_col = f'{pos}_%'
            if pos_col in df_filtering.columns and pos in df_filtering.columns:
                df_filtering.loc[df_filtering[pos] == 0, pos_col] = 0

    # -----------------------------
    # Show only clean columns (hide Positions_filter + binary indicators)
    columns_to_show = ['Name','Club','Age','Positions','Nat','Transfer Value'] + rating_columns_ordered
    columns = [{"name": col, "id": col} for col in columns_to_show]

    return df_filtering[columns_to_show].to_dict('records'), columns

# ----------------------------- DASH APP LAYOUT -----------------------------
app.layout = dbc.Container([
    dbc.Row(html.H1("Squad Dashboard", style={'text-align': 'center', 'margin-bottom': '20px'})),

    # Filters row - evenly spaced
    dbc.Row([
        dbc.Col([
            html.Label("Age Range", style={'font-weight': 'bold'}),
            dcc.RangeSlider(
                min=15, max=40, step=1, value=[15, 40], id='age_range_slider',
                marks={i: str(i) for i in range(15, 41) if i % 5 == 0},
                tooltip={"placement": "bottom", "always_visible": True}
            )
        ], width=3),

        dbc.Col([
            html.Label("Position", style={'font-weight': 'bold'}),
            dcc.Dropdown(
                id="position_filter",
                options=[{'label': pos, 'value': pos} for pos in sorted(all_unique_positions) + ['All']],
                multi=True, value=['All'], placeholder="Select positions"
            )
        ], width=3),

        dbc.Col([
            html.Label("Club", style={'font-weight': 'bold'}),
            dcc.Input(
                id="club_filter", type='text', placeholder='Enter club...', debounce=True, value="",
                style={'width': '100%'}
            )
        ], width=3),

        dbc.Col([
            html.Label("Player Name", style={'font-weight': 'bold'}),
            dcc.Input(
                id="name_filter", type='text', placeholder='Enter player...', debounce=True, value="",
                style={'width': '100%'}
            )
        ], width=3),
    ], className='mb-3'),

    # Toggle row
    dbc.Row([
        dbc.Col(
            dbc.Switch(id="show_all_toggle", label="Show all position ratings", value=False),
            width=3
        ),
    ], className='mb-3'),

   # ... everything above unchanged ...

    # DataTable
    dbc.Row(
        dbc.Col(
            dash_table.DataTable(
                id='my_squad',
                columns=[{"name": i, "id": i} for i in viz_df.columns],
                data=viz_df.to_dict('records'),
                page_size=15,
                filter_action="native",
                sort_action="native",
                sort_mode="multi",
                row_selectable="multi",
                style_table={'overflowX': 'auto'},
                style_cell={'fontSize': 12, 'padding': '5px'},

                # ✅ Conditional formatting
                style_data_conditional=[
                    {
                        'if': {
                            'filter_query': f'{{{col}}} >= 70',
                            'column_id': col
                        },
                        'backgroundColor': '#c6efce',
                        'color': 'black'
                    }
                    for col in rating_columns_ordered
                ] + [
                    {
                        'if': {
                            'filter_query': f'{{{col}}} >= 30 && {{{col}}} < 70',
                            'column_id': col
                        },
                        'backgroundColor': '#ffeb9c',
                        'color': 'black'
                    }
                    for col in rating_columns_ordered
                ] + [
                    {
                        'if': {
                            'filter_query': f'{{{col}}} < 30 && {{{col}}} > 0',
                            'column_id': col
                        },
                        'backgroundColor': '#f2dcdb',
                        'color': 'black'
                    }
                    for col in rating_columns_ordered
                ] + [
                    {
                        'if': {
                            'filter_query': f'{{{col}}} = 0',
                            'column_id': col
                        },
                        'backgroundColor': 'white',
                        'color': 'lightgrey'
                    }
                    for col in rating_columns_ordered
                ]
            )
        ),
    )
], fluid=True)

# -----------------------------
if __name__ == '__main__':
    app.run(debug=True, jupyter_mode="external")
