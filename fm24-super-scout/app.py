from pathlib import Path
from functools import lru_cache
from io import StringIO
import pandas as pd
import dash
from dash import Dash, dcc, html, dash_table, Input, Output, State

from config import POSITION_ORDER, SNAPSHOT_DIR
from scout import load_latest, load_history, load_snapshot, growth, save_shortlist
from attribute_growth import PREDICTED_ATTRIBUTES


@lru_cache(maxsize=2)
def _dataframe_from_json(raw: str) -> pd.DataFrame:
    return pd.read_json(StringIO(raw), orient="records")

FORMATION_POSITIONS = {
    "4-4-2": ["GK", "DL", "DC", "DC", "DR", "ML", "MC", "MC", "MR", "ST", "ST"],
    "4-3-3": ["GK", "DL", "DC", "DC", "DR", "DM", "MC", "MC", "AML", "ST", "AMR"],
    "4-2-3-1": ["GK", "DL", "DC", "DC", "DR", "DM", "DM", "AML", "AMC", "AMR", "ST"],
    "3-4-3": ["GK", "DC", "DC", "DC", "ML", "MC", "MC", "MR", "AML", "ST", "AMR"],
    "5-3-2": ["GK", "WBL", "DC", "DC", "DC", "WBR", "MC", "MC", "MC", "ST", "ST"],
    "3-2-2-3": ["GK", "DC", "DR", "DL", "DM", "DM", "AMR", "AML", "ST", "ST", "ST"],
}

FORMATION_LABELS = {
    "3-2-2-3": ["GK", "CB", "RB", "LB", "DM", "DM", "RW", "LW", "ST", "ST", "ST"],
}

DISPLAY_NAMES = {
    "CA Increase": "CA Change",
    "Rating Increase": "Rating Change",
    "Potential Rating": "Projected Rating",
    "Potential Gap": "Projected Growth",
    "Club Development Effect": "Club Effect / Year",
}

DEVELOPMENT_METRICS = [
    {"label": "Current Ability", "value": "Current Ability"},
    {"label": "Current Rating", "value": "Current Rating"},
    {"label": "Potential Ability", "value": "Potential Ability"},
    {"label": "Projected Rating", "value": "Potential Rating"},
    {"label": "Value", "value": "Value"},
] + [{"label": f"{attribute.replace('_', ' ').title()} · 1-year forecast", "value": f"{attribute}_1y_pred"} for attribute in PREDICTED_ATTRIBUTES]


def _best_xi(raw, club, formation):
    df = _dataframe_from_json(raw) if raw else pd.DataFrame()
    if df.empty or not club or formation not in FORMATION_POSITIONS:
        return []
    df = df[df["Club"].astype(str) == club].copy()
    if df.empty:
        return []
    slots = FORMATION_POSITIONS[formation]
    selected = []
    used = set()
    for slot in slots:
        candidates = df[(~df.index.isin(used)) & df["Positions"].map(lambda values: slot in (values if isinstance(values, list) else str(values).split(", ")))].copy()
        if candidates.empty:
            selected.append({"Position": FORMATION_LABELS.get(formation, slots)[len(selected)], "Player": "No suitable player", "Rating": "—", "CA": "—", "PA": "—"})
            continue
        score_col = f"{slot}_rating"
        if score_col in candidates:
            candidates["_rating"] = pd.to_numeric(candidates[score_col], errors="coerce").fillna(candidates["Current Rating"])
        else:
            candidates["_rating"] = pd.to_numeric(candidates["Current Rating"], errors="coerce").fillna(0)
        pick = candidates.sort_values(["_rating", "Current Ability"], ascending=False).iloc[0]
        used.add(pick.name)
        selected.append({"Position": FORMATION_LABELS.get(formation, slots)[len(selected)], "Player": pick.get("Name", "Unknown"), "Rating": round(float(pick["_rating"]), 1), "CA": int(pick["Current Ability"]) if pd.notna(pick.get("Current Ability")) else "—", "PA": int(pick["Potential Ability"]) if pd.notna(pick.get("Potential Ability")) else "—"})
    return selected

TEAM_SPECS = [
    ("Senior", "current", None),
    ("B team", "hybrid", None),
    ("C team", "hybrid", None),
    ("U21", "potential", 21),
    ("U18", "potential", 18),
]


def _number_series(df, column, fallback=0.0):
    if column not in df:
        return pd.Series(fallback, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(fallback)


def _position_values(value):
    if isinstance(value, list):
        return value
    return str(value or "").replace(",", " ").split()


def _position_proficiency(row, slot):
    values = row.get("Position Proficiency", {})
    if isinstance(values, dict):
        value = pd.to_numeric(values.get(slot), errors="coerce")
        return float(value) if pd.notna(value) else 0.0
    return 15.0 if slot in _position_values(row.get("Positions")) else 0.0


def _proficiency_multiplier(value):
    if value >= 20:
        return 1.0
    if value >= 15:
        return 0.95
    if value >= 10:
        return 0.75
    if value >= 5:
        return 0.5
    return 0.0


def _role_scores(candidates, slot):
    current = _number_series(candidates, f"{slot}_rating")
    if f"{slot}_rating" not in candidates:
        current = _number_series(candidates, "Current Rating")
    predicted = _number_series(candidates, f"{slot}_proj_peak")
    if f"{slot}_proj_peak" not in candidates:
        predicted = _number_series(candidates, "Potential Rating")
    return current, predicted


def _choose_candidate(candidates, slot, mode):
    if candidates.empty:
        return None
    current, predicted = _role_scores(candidates, slot)
    candidates = candidates.copy()
    candidates["_current_score"] = current
    candidates["_predicted_score"] = predicted
    candidates["_position_proficiency"] = candidates.apply(
        lambda row: _position_proficiency(row, slot),
        axis=1,
    ).fillna(0)
    candidates["_position_multiplier"] = candidates["_position_proficiency"].map(_proficiency_multiplier)
    candidates["_effective_score"] = candidates["_current_score"] * candidates["_position_multiplier"]
    candidates["_effective_predicted_score"] = candidates["_predicted_score"] * candidates["_position_multiplier"]
    if mode == "current":
        return candidates.sort_values(
            ["_effective_score", "_position_proficiency", "Current Ability"],
            ascending=False,
        ).iloc[0]
    if mode == "potential":
        return candidates.sort_values(
            ["_effective_predicted_score", "_position_proficiency", "Potential Ability"],
            ascending=False,
        ).iloc[0]
    current_pick = candidates.sort_values(
        ["_effective_score", "_position_proficiency", "Current Ability"],
        ascending=False,
    ).iloc[0]
    near_current = candidates[candidates["_effective_score"] >= current_pick["_effective_score"] - 10]
    upgrades = near_current[
        (near_current["_effective_predicted_score"] > current_pick["_effective_score"])
        & (near_current["_effective_predicted_score"] > current_pick["_effective_predicted_score"])
    ]
    if not upgrades.empty:
        return upgrades.sort_values(
            ["_effective_predicted_score", "_position_proficiency", "_effective_score"],
            ascending=False,
        ).iloc[0]
    return current_pick


def _fallback_candidate(candidates, slots):
    if candidates.empty:
        return None
    proficiency = candidates.apply(
        lambda row: max((_position_proficiency(row, slot) for slot in slots), default=0),
        axis=1,
    )
    fallback = candidates[proficiency < 5].copy()
    if fallback.empty:
        return None
    fallback["_fallback_rating"] = _number_series(fallback, "Current Rating")
    fallback["_fallback_potential"] = _number_series(fallback, "Potential Rating")
    return fallback.sort_values(
        ["_fallback_rating", "_fallback_potential", "Current Ability"],
        ascending=False,
    ).iloc[0]


def _build_squads(raw, club, formation):
    df = _dataframe_from_json(raw) if raw else pd.DataFrame()
    if df.empty or not club or formation not in FORMATION_POSITIONS or "Club" not in df:
        return []
    df = df[df["Club"].astype(str) == club].copy()
    if df.empty:
        return []
    slots = FORMATION_POSITIONS[formation]
    labels = FORMATION_LABELS.get(formation, slots)
    used = set()
    rows = []
    assignments = [
        (TEAM_SPECS[0][0], TEAM_SPECS[0][1], TEAM_SPECS[0][2], squad_role)
        for squad_role in ("Starter", "Backup")
    ] + [
        (team, mode, age_limit, squad_role)
        for squad_role in ("Starter", "Backup")
        for team, mode, age_limit in TEAM_SPECS[1:]
    ]
    for team, mode, age_limit, squad_role in assignments:
        for slot_index, slot in enumerate(slots):
            position_label = labels[slot_index]
            candidates = df[~df.index.isin(used)].copy()
            candidates = candidates[
                candidates.apply(lambda row: _position_proficiency(row, slot) >= 5, axis=1)
            ]
            if age_limit is not None and "Age" in candidates:
                candidates = candidates[_number_series(candidates, "Age", 999) <= age_limit]
            pick = _choose_candidate(candidates, slot, mode)
            if pick is None:
                pick = _fallback_candidate(candidates, slots)
            if pick is None:
                rows.append({"Team": team, "Role": squad_role, "Position": position_label, "Player": "No suitable player", "Rating": "—", "Projected": "—", "CA": "—", "PA": "—"})
                continue
            used.add(pick.name)
            rows.append({"Team": team, "Role": squad_role, "Position": position_label, "Player": pick.get("Name", "Unknown"), "Rating": round(float(pick["_current_score"]), 1), "Projected": round(float(pick["_predicted_score"]), 1), "CA": int(pick["Current Ability"]) if pd.notna(pick.get("Current Ability")) else "—", "PA": int(pick["Potential Ability"]) if pd.notna(pick.get("Potential Ability")) else "—"})
    return rows


SNAPSHOT_DIR.mkdir(exist_ok=True)
app = Dash(__name__, title="FM24 Super Scout")
app.index_string = """
<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
@import url('https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700&family=Inter:wght@400;500;600;700&display=swap');
:root{--bg:#0b1117;--panel:#111a23;--line:#26323d;--muted:#8fa0ad;--text:#e9f0f3;--accent:#4dd6a3;}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,Arial,sans-serif}.page{max-width:1500px;margin:0 auto;padding:42px 42px 70px}.header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:32px}.eyebrow,.section-label{color:var(--accent);font-size:11px;font-weight:700;letter-spacing:2px}.header h1{font:700 46px/1 Barlow Condensed,Arial;margin:7px 0;color:#fff}.header p{color:var(--muted);margin:10px 0 0}.header-actions{display:flex;gap:14px;align-items:center}.live-pill{border:1px solid #286d5d;border-radius:20px;color:var(--accent);font-size:11px;font-weight:700;padding:10px 14px;letter-spacing:1px}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:24px}.stat-card,.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px}.stat-card{padding:18px 22px}.stat-value{font:600 25px Barlow Condensed,Arial;color:#fff}.stat-value.green{color:var(--accent)}.stat-label{color:var(--muted);font-size:12px;margin-top:4px}.panel{padding:20px 22px}.panel .section-label{margin-bottom:15px}.filters{display:grid;grid-template-columns:2fr 2fr 1fr 1fr 1fr;gap:10px}.xi-filters{grid-template-columns:2fr 1fr;max-width:800px;margin:20px 0}.muted{color:var(--muted);font-size:13px}.xi-summary{color:var(--accent);font-size:13px;margin:24px 0 12px}.tabs{margin-top:8px}.tabs--light .tab--selected{color:var(--accent)!important}.tab{background:#10171e!important;color:var(--muted)!important;border-color:var(--line)!important;padding:14px 20px!important;font-weight:600}.tab--selected{background:var(--panel)!important;color:var(--accent)!important;border-top:2px solid var(--accent)!important}.input,.dropdown .Select-control{background:#0b1117!important;border:1px solid var(--line)!important;color:var(--text)!important;border-radius:5px!important}.input{height:42px;padding:0 13px;font-size:13px}.input::placeholder{color:#71818d}.Select-value-label,.Select-placeholder{color:var(--muted)!important}.Select-menu-outer{background:#18232d!important;color:var(--text)!important}.toolbar{display:flex;align-items:center;gap:15px;margin:18px 0}.primary,.secondary{border:0;border-radius:5px;padding:11px 16px;font-weight:600;cursor:pointer}.primary{background:var(--accent);color:#07120f}.secondary{background:#202c37;color:var(--text)}.shortlist-status,.status{color:var(--muted);font-size:12px}.status{margin:-18px 0 18px}@media(max-width:800px){.page{padding:25px 15px}.header{display:block}.header-actions{margin-top:20px}.stats,.filters,.xi-filters{grid-template-columns:1fr}.header h1{font-size:38px}}
</style><style>.loading-status{display:flex;align-items:center;gap:12px;color:var(--muted);font-size:12px}.progress-track{height:6px;flex:1;max-width:420px;background:#202c37;border-radius:99px;overflow:hidden}.progress-fill{height:100%;width:35%;background:var(--accent);border-radius:99px;animation:progress-pulse 1.4s ease-in-out infinite}@keyframes progress-pulse{0%{transform:translateX(-120%);width:25%}50%{width:55%}100%{transform:translateX(280%);width:25%}}</style></head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>
"""
search_content = html.Div([
    html.Div([html.Div([html.Div("12,602", id="player-count", className="stat-value"), html.Div("Players loaded", className="stat-label")], className="stat-card"),
              html.Div([html.Div("Live", className="stat-value green"), html.Div("Memory snapshot", className="stat-label")], className="stat-card"),
              html.Div([html.Div("FM24", className="stat-value"), html.Div("Build 24.4.2", className="stat-label")], className="stat-card")], className="stats"),
    html.Div([html.Div("PLAYER SEARCH", className="section-label"),
    html.Div([
        dcc.Input(id="player-query", placeholder="Player name", debounce=True, className="input"),
        dcc.Input(id="club-query", value="Everton", placeholder="Club", debounce=True, className="input"),
        dcc.Dropdown([{"label": p, "value": p} for p in POSITION_ORDER], id="position", placeholder="Any position", clearable=True, className="dropdown"),
        dcc.Input(id="min-ca", type="number", placeholder="Min CA", className="input"),
        dcc.Input(id="min-pa", type="number", placeholder="Min PA", className="input"),
    ], className="filters")], className="panel"),
    html.Div([html.Button("Save visible players", id="shortlist", className="primary"), html.Div(id="shortlist-status", className="shortlist-status")], className="toolbar"),
    dash_table.DataTable(id="players", page_size=25, page_action="custom", page_current=0, page_count=1, sort_action="custom", sort_mode="single", row_selectable="multi", style_table={"overflowX": "auto"}, style_header={"backgroundColor": "#18202a", "color": "#d7e2e8", "fontWeight": "600", "border": "none"}, style_cell={"backgroundColor": "#10171e", "color": "#d7e2e8", "border": "1px solid #26323d", "padding": "12px", "fontFamily": "Inter, Arial", "fontSize": "13px"}, style_data_conditional=[{"if": {"row_index": "odd"}, "backgroundColor": "#141d26"}]),
])

xi_content = html.Div([
    html.Div("BEST XI BUILDER", className="section-label"),
    html.P("Builds Senior, B, C, U21 and U18 squads in that priority order. Each position gets a starter and backup, and a player can only appear once. Senior uses current rating, B/C use the current-versus-projected hybrid, and youth squads use projected rating.", className="muted"),
    html.Div([
        dcc.Dropdown(id="team", value="Everton", placeholder="Select a club", className="dropdown"),
        dcc.Dropdown([{"label": name, "value": name} for name in FORMATION_POSITIONS], value="3-2-2-3", id="formation", clearable=False, className="dropdown"),
    ], className="filters xi-filters"),
    html.Div(id="xi-summary", className="xi-summary"),
    dash_table.DataTable(id="xi-table", columns=[{"name": c, "id": c} for c in ["Team", "Role", "Position", "Player", "Rating", "Projected", "CA", "PA"]], data=[], style_table={"overflowX": "auto"}, style_header={"backgroundColor": "#18202a", "color": "#d7e2e8", "fontWeight": "600", "border": "none"}, style_cell={"backgroundColor": "#10171e", "color": "#d7e2e8", "border": "1px solid #26323d", "padding": "13px", "fontFamily": "Inter, Arial"}, style_data_conditional=[{"if": {"column_id": "Position"}, "color": "#4dd6a3", "fontWeight": "700"}, {"if": {"column_id": "Team"}, "color": "#4dd6a3", "fontWeight": "700"}]),
])

development_content = html.Div([
    html.Div("DEVELOPMENT TRACKER", className="section-label"),
    html.P("Compare quarterly memory snapshots using their real FM game dates.", className="muted"),
    html.Div([
        html.Div([html.Div("PLAYER TREND", className="section-label"), html.P("How this player has changed between dated snapshots.", className="muted")], className="stat-card"),
        html.Div([html.Div("CLUB CONTEXT", className="section-label"), html.P("Whether this club has developed players faster or slower than average.", className="muted")], className="stat-card"),
        html.Div([html.Div("HEADROOM", className="section-label"), html.P("PA − CA is room to improve, not a promise of future ability.", className="muted")], className="stat-card"),
    ], className="stats"),
    html.Div([
        dcc.Dropdown(id="development-player", placeholder="Select an Everton player", className="dropdown"),
        dcc.Dropdown(DEVELOPMENT_METRICS, value="Current Ability", id="development-metric", clearable=False, className="dropdown"),
    ], className="filters xi-filters"),
    html.Div(id="development-summary", className="xi-summary"),
    dcc.Graph(id="development-chart", config={"displayModeBar": False}),
    dash_table.DataTable(id="development-table", columns=[{"name": c, "id": c} for c in ["Date", "Age", "CA", "CA Change", "Rating", "PA", "Value", "Club Effect", "Forecast"]], data=[], style_table={"overflowX": "auto"}, style_header={"backgroundColor": "#18202a", "color": "#d7e2e8", "fontWeight": "600", "border": "none"}, style_cell={"backgroundColor": "#10171e", "color": "#d7e2e8", "border": "1px solid #26323d", "padding": "12px", "fontFamily": "Inter, Arial"}),
])

app.layout = html.Div([
    html.Div([html.Div([html.Div("FM24", className="eyebrow"), html.H1("Super Scout"), html.P("Live player intelligence for Football Manager 2024.")]),
              html.Div([html.Div("READ-ONLY", className="live-pill"), dcc.Upload(id="upload", children=html.Button("Import data", className="secondary"))], className="header-actions")], className="header"),
    html.Div([html.Div("Loading snapshot, calculating ratings and building forecasts…", id="status-text", className="loading-status"), html.Div(className="progress-track", children=html.Div(className="progress-fill"))], id="status", className="status"),
    dcc.Tabs(id="tabs", value="search", className="tabs", children=[dcc.Tab(label="Player Search", value="search", children=search_content), dcc.Tab(label="Best XI Builder", value="xi", children=xi_content), dcc.Tab(label="Development", value="development", children=development_content)]),
    dcc.Store(id="data", data=None),
], className="page")


@app.callback(Output("data", "data"), Input("upload", "contents"), State("upload", "filename"))
def import_file(contents, filename):
    if dash.ctx.triggered_id == "upload" and contents and filename:
        import base64
        target = SNAPSHOT_DIR / Path(filename).name
        target.write_bytes(base64.b64decode(contents.split(",", 1)[1]))
        loaded = load_snapshot(target)
        return loaded.to_json(orient="records", date_format="iso")
    latest = load_latest()
    return latest.to_json(orient="records", date_format="iso")


@app.callback(Output("status-text", "children"), Input("data", "data"))
def update_status(raw):
    if not raw:
        return "Loading snapshot, calculating ratings and building forecasts…"
    return "Ready — latest memory snapshot and forecasts loaded"


@app.callback(Output("players", "data"), Output("players", "columns"), Output("players", "page_count"), Input("data", "data"), Input("player-query", "value"), Input("club-query", "value"), Input("position", "value"), Input("min-ca", "value"), Input("min-pa", "value"), Input("players", "page_current"), Input("players", "page_size"), Input("players", "sort_by"))
def update_table(raw, player_query, club_query, position, min_ca, min_pa, page_current, page_size, sort_by):
    df = _dataframe_from_json(raw).copy() if raw else pd.DataFrame()
    if df.empty:
        return [], [], 0
    if player_query:
        needle = str(player_query).lower()
        df = df[df["Name"].astype(str).str.lower().str.contains(needle)]
    if club_query:
        needle = str(club_query).lower()
        df = df[df["Club"].astype(str).str.lower().str.contains(needle)]
    if position:
        df = df[df["Positions"].map(lambda x: position in (x if isinstance(x, list) else str(x)))]
    if min_ca is not None and "Current Ability" in df:
        df = df[df["Current Ability"] >= min_ca]
    if min_pa is not None and "Potential Ability" in df:
        df = df[df["Potential Ability"] >= min_pa]
    if "Positions" in df:
        df["Positions"] = df["Positions"].map(lambda value: ", ".join(value) if isinstance(value, list) else value)
    if sort_by:
        sort = sort_by[0]
        if sort.get("column_id") in df.columns:
            df = df.sort_values(sort["column_id"], ascending=sort.get("direction") != "desc", na_position="last")
    visible = [c for c in ["ID", "Name", "Club", "Age", "Professionalism", "Positions", "Current Ability", "CA Increase", "Potential Ability", "Best Position", "Current Rating", "Rating Increase", "Potential Rating", "Potential Gap", "Club Development Effect", "Value"] if c in df]
    total = len(df)
    page_size = max(1, int(page_size or 25))
    page_current = max(0, int(page_current or 0))
    page_count = max(1, (total + page_size - 1) // page_size)
    page_current = min(page_current, page_count - 1)
    page = df[visible].iloc[page_current * page_size:(page_current + 1) * page_size]
    return page.to_dict("records"), [{"name": DISPLAY_NAMES.get(c, c), "id": c} for c in visible], page_count


@app.callback(Output("shortlist-status", "children"), Input("shortlist", "n_clicks"), State("players", "data"), prevent_initial_call=True)
def shortlist(_, rows):
    save_shortlist(pd.DataFrame(rows))
    return f"Saved {len(rows)} players to shortlist.csv"


@app.callback(Output("team", "options"), Output("xi-table", "data"), Output("xi-summary", "children"), Input("data", "data"), Input("team", "value"), Input("formation", "value"))
def update_xi(raw, club, formation):
    df = _dataframe_from_json(raw) if raw else pd.DataFrame()
    clubs = sorted(x for x in df.get("Club", pd.Series(dtype=str)).dropna().astype(str).unique() if x not in {"Unknown", "Free Transfer"})
    options = [{"label": x, "value": x} for x in clubs]
    rows = _build_squads(raw, club, formation)
    if not rows:
        return options, [], "Select a club to build the best XI."
    filled = sum(row["Player"] != "No suitable player" for row in rows)
    summary = f"{club} · {formation} · {filled}/{len(rows)} squad positions filled; priority: Senior → B → C → U21 → U18"
    return options, rows, summary
    return options, rows, f"{club} · {formation} · {filled}/11 positions filled"


@app.callback(Output("development-player", "options"), Output("development-player", "value"), Output("development-chart", "figure"), Output("development-table", "data"), Output("development-summary", "children"), Input("data", "data"), Input("development-player", "value"), Input("development-metric", "value"))
def update_development(raw, player_id, metric):
    current = _dataframe_from_json(raw) if raw else pd.DataFrame()
    history = load_history()
    if current.empty:
        return [], None, {"data": [], "layout": {"paper_bgcolor": "#111a23", "plot_bgcolor": "#111a23"}}, [], "No snapshots available."
    players = current[["ID", "Name", "Club"]].drop_duplicates().sort_values(["Club", "Name"])
    everton = players[players["Club"].astype(str).str.casefold() == "everton"]
    players = pd.concat([everton, players[~players.index.isin(everton.index)]])
    options = [{"label": f"{row.Name} · {row.ID}", "value": str(row.ID)} for row in players.itertuples()]
    if player_id is None and options:
        player_id = options[0]["value"]
    points = []
    for path, frame in history:
        match = frame[frame["ID"].astype(str) == str(player_id)]
        if match.empty:
            continue
        row = match.iloc[0]
        snapshot_date = row.get("Date")
        if pd.notna(snapshot_date):
            snapshot_date = pd.Timestamp(snapshot_date).strftime("%Y-%m-%d")
        else:
            snapshot_date = path.stem
        points.append({"Date": snapshot_date, "Age": row.get("Age", None), "CA": row.get("Current Ability", None), "Rating": row.get("Current Rating", None), "PA": row.get("Potential Ability", None), "Value": row.get("Value", None), "Club Effect": row.get("Club Development Effect", None), "Forecast": row.get(metric, None), "Metric": row.get(metric, None)})
    previous_ca = None
    for point in points:
        current_ca = pd.to_numeric(pd.Series([point["CA"]]), errors="coerce").iloc[0]
        point["CA Change"] = None if previous_ca is None or pd.isna(current_ca) else round(float(current_ca - previous_ca), 2)
        if pd.notna(current_ca):
            previous_ca = float(current_ca)
    label = next((x["label"] for x in options if x["value"] == str(player_id)), "Player")
    figure = {"data": [{"x": [p["Date"] for p in points], "y": [p["Metric"] for p in points], "type": "scatter", "mode": "lines+markers", "line": {"color": "#4dd6a3", "width": 3}, "marker": {"size": 8}}], "layout": {"title": f"{label} · {metric}", "paper_bgcolor": "#111a23", "plot_bgcolor": "#111a23", "font": {"color": "#d7e2e8"}, "xaxis": {"gridcolor": "#26323d"}, "yaxis": {"gridcolor": "#26323d"}, "margin": {"l": 50, "r": 20, "t": 50, "b": 100}}}
    latest_match = current[current["ID"].astype(str) == str(player_id)]
    if not latest_match.empty:
        latest_row = latest_match.iloc[0]
        projected = latest_row.get("Potential Rating", None)
        club_effect = pd.to_numeric(pd.Series([latest_row.get("Club Development Effect", 0)]), errors="coerce").iloc[0]
        gap = latest_row.get("Potential Gap", None)
        summary = f"{label} · {len(points)} dated snapshot(s) · projected rating {projected} · projected growth {gap} · club context {club_effect:+.2f}/year"
    else:
        summary = f"{label} · {len(points)} dated snapshot(s)"
    return options, player_id, figure, [{k: p[k] for k in ("Date", "Age", "CA", "CA Change", "Rating", "PA", "Value", "Club Effect", "Forecast")} for p in points], summary


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8765, debug=False)
