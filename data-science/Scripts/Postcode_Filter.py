# scripts/postcode_filter.py
import requests
from shapely.geometry import Point, shape

def get_nearby_postcodes(lat, lon, radius=50000):
    """
    Fetch nearby UK postcodes using postcodes.io.
    """
    url = f"https://api.postcodes.io/postcodes?lon={lon}&lat={lat}&radius={radius}&wideSearch=true&limit=100"
    response = requests.get(url).json()
    
    return [
        {
            "postcode": p["postcode"],
            "outcode": p["outcode"],
            "lat": p["latitude"],
            "lon": p["longitude"]
        }
        for p in response.get("result", [])
    ]

def filter_postcodes_in_isochrone(postcodes, isochrone_geometry):
    """
    Filter postcodes that fall inside the given isochrone polygon and return unique outcodes.
    """
    poly = shape(isochrone_geometry)
    inside = []

    for p in postcodes:
        point = Point(p["lon"], p["lat"])
        if poly.contains(point):
            inside.append(p["outcode"])

    return sorted(set(inside))  # unique, sorted outcodes
