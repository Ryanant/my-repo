# scripts/isochrone.py
import requests

def get_isochrone(lat, lon, minutes, api_key):
    """
    Fetch a driving isochrone polygon from OpenRouteService for the given location and time.
    """
    url = "https://api.openrouteservice.org/v2/isochrones/driving-car"
    headers = {"Authorization": api_key, "Content-Type": "application/json"}
    body = {
        "locations": [[lon, lat]],
        "range": [minutes * 60]  # convert minutes to seconds
    }

    response = requests.post(url, headers=headers, json=body)
    response.raise_for_status()
    data = response.json()
    return data["features"][0]["geometry"]
