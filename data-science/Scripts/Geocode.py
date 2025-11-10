# scripts/geocode.py
import requests

def geocode_postcode(postcode):
    """
    Convert a UK postcode to latitude and longitude using postcodes.io.
    """
    url = f"https://api.postcodes.io/postcodes/{postcode}"
    response = requests.get(url).json()
    
    if response["status"] == 200:
        result = response["result"]
        return result["latitude"], result["longitude"]
    else:
        raise ValueError(f"Postcode '{postcode}' not found.")
