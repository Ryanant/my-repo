"""
main_isochrone_outcodes_from_csv.py
-----------------------------------
Reads UK outcodes from a local CSV (outcode, latitude, longitude),
computes a drive-time isochrone from a postcode using OpenRouteService,
finds which outcodes fall inside that area, and plots the result on a map.
"""

import requests
import pandas as pd
from shapely.geometry import shape, Point
import folium

# -----------------------------
# 1️⃣ Geocode the starting postcode
# -----------------------------
def geocode_postcode(postcode):
    url = f"https://api.postcodes.io/postcodes/{postcode}"
    response = requests.get(url).json()
    if response["status"] == 200:
        result = response["result"]
        return result["latitude"], result["longitude"]
    else:
        raise ValueError(f"Postcode '{postcode}' not found on postcodes.io")

# -----------------------------
# 2️⃣ Fetch isochrone polygon
# -----------------------------
def get_isochrone(lat, lon, minutes, api_key):
    url = "https://api.openrouteservice.org/v2/isochrones/driving-car"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    body = {"locations": [[lon, lat]], "range": [minutes * 60]}  # seconds
    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    data = response.json()
    features = data.get("features", [])
    if not features:
        raise ValueError("No isochrone polygon returned from OpenRouteService.")
    geometry = features[0]["geometry"]
    return shape(geometry), geometry  # Shapely and GeoJSON versions

# -----------------------------
# 3️⃣ Load outcodes from local CSV
# -----------------------------
def load_outcodes(csv_path="uk_outcodes.csv"):
    df = pd.read_csv(csv_path)
    if not {"outcode", "latitude", "longitude"}.issubset(df.columns):
        raise ValueError("CSV must have columns: outcode, latitude, longitude")
    outcodes = df.to_dict("records")
    print(f"✅ Loaded {len(outcodes)} outcodes from {csv_path}")
    return outcodes

# -----------------------------
# 4️⃣ Filter outcodes inside isochrone polygon
# -----------------------------
def filter_outcodes(outcodes, poly):
    inside, outside = [], []
    for o in outcodes:
        try:
            lat, lon = float(o["latitude"]), float(o["longitude"])
            point = Point(lon, lat)
            if poly.contains(point) or poly.intersects(point):
                inside.append(o)
            else:
                outside.append(o)
        except Exception:
            continue
    print(f"🏁 Found {len(inside)} reachable outcodes (out of {len(outcodes)} total).")
    return inside, outside

# -----------------------------
# 5️⃣ Plot everything on a map
# -----------------------------
def plot_map(lat, lon, isochrone_geom, inside, outside):
    m = folium.Map(location=[lat, lon], zoom_start=8, tiles="CartoDB positron")

    # Isochrone polygon
    folium.GeoJson(
        isochrone_geom,
        name="Isochrone",
        style_function=lambda x: {"fillColor": "blue", "color": "blue", "fillOpacity": 0.25}
    ).add_to(m)

    # Reachable outcodes
    for o in inside:
        folium.CircleMarker(
            [o["latitude"], o["longitude"]],
            radius=4,
            color="red",
            fill=True,
            fill_color="red",
            fill_opacity=0.8,
            popup=o["outcode"]
        ).add_to(m)

    # Other outcodes (grey)
    for o in outside:
        folium.CircleMarker(
            [o["latitude"], o["longitude"]],
            radius=2,
            color="gray",
            fill=True,
            fill_color="gray",
            fill_opacity=0.4
        ).add_to(m)

    # Starting postcode marker
    folium.Marker(
        [lat, lon],
        popup="Start",
        icon=folium.Icon(color="green", icon="flag")
    ).add_to(m)

    folium.LayerControl().add_to(m)
    m.save("isochrone_outcodes_map.html")
    print("✅ Map saved as isochrone_outcodes_map.html")

# -----------------------------
# 6️⃣ Main program
# -----------------------------
if __name__ == "__main__":
    ORS_API_KEY = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjY2Yzg5YmU2MDVhOTQwMGZiNmE3MTlkYzZmZWQwNDYzIiwiaCI6Im11cm11cjY0In0="  # replace with your actual key

    start_postcode = input("Enter a UK postcode: ").strip()
    minutes = int(input("Enter drive time in minutes (e.g., 30): "))

    # Geocode
    lat, lon = geocode_postcode(start_postcode)
    print(f"📍 {start_postcode} located at lat={lat}, lon={lon}")

    # Isochrone polygon
    poly, geom = get_isochrone(lat, lon, minutes, ORS_API_KEY)
    print(f"🗺️ Retrieved {minutes}-minute isochrone polygon.")

    # Load outcodes
    all_outcodes = load_outcodes("uk_outcodes.csv")

    # Check which outcodes are inside
    inside, outside = filter_outcodes(all_outcodes, poly)
    reachable = sorted([o["outcode"] for o in inside])
    print(f"\nReachable outcodes from {start_postcode} within {minutes} minutes:")
    print(reachable)

    # Plot map
    plot_map(lat, lon, geom, inside, outside)
