# scripts/main.py
from Geocode import geocode_postcode
from Isochrone import get_isochrone
from Postcode_Filter import get_nearby_postcodes, filter_postcodes_in_isochrone

def reachable_outcodes(start_postcode, api_key, minutes=30):
    """
    Get all reachable postcode outcodes within `minutes` driving from `start_postcode`.
    """
    lat, lon = geocode_postcode(start_postcode)
    isochrone = get_isochrone(lat, lon, minutes, api_key)
    postcodes = get_nearby_postcodes(lat, lon)
    outcodes = filter_postcodes_in_isochrone(postcodes, isochrone)
    return outcodes

if __name__ == "__main__":
    api_key = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjY2Yzg5YmU2MDVhOTQwMGZiNmE3MTlkYzZmZWQwNDYzIiwiaCI6Im11cm11cjY0In0="  # replace with your key
    start_postcode = input("Enter a UK postcode: ").strip()
    minutes = int(input("Enter drive time in minutes (e.g., 30): "))

    try:
        outcodes = reachable_outcodes(start_postcode, api_key, minutes)
        print(f"Reachable outcodes from {start_postcode} within {minutes} minutes:")
        print(outcodes)
    except Exception as e:
        print("Error:", e)
