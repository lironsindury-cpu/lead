import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

GOOGLE_API_KEY = os.environ["GOOGLE_PLACES_API_KEY"]
CRM_URL        = "http://127.0.0.1:5001"
CRM_API_KEY    = "secret-key"

SEARCH_TARGETS = [
    {"query": "מסעדות תל אביב",     "category": "Restaurant"},
    {"query": "מספרות תל אביב",     "category": "Barbershop"},
    {"query": "מכון יופי תל אביב",  "category": "Beauty Salon"},
    {"query": "מוסך תל אביב",       "category": "Garage"},
]

def search_places(query):
    url    = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": GOOGLE_API_KEY, "language": "iw"}
    results, next_page_token = [], None
    while True:
        if next_page_token:
            params["pagetoken"] = next_page_token
            time.sleep(2)
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        results.extend(data.get("results", []))
        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break
    return results

def get_details(place_id):
    url    = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {
        "place_id": place_id,
        "fields":   "name,formatted_phone_number,website,formatted_address,rating,user_ratings_total",
        "key":      GOOGLE_API_KEY,
        "language": "iw",
    }
    resp = requests.get(url, params=params, timeout=10)
    return resp.json().get("result", {})

def push_leads(leads):
    if not leads:
        return
    resp = requests.post(
        f"{CRM_URL}/api/admin/leads",
        json=leads,
        headers={"X-API-Key": CRM_API_KEY},
        timeout=15,
    )
    data = resp.json()
    print(f"Pushed {data['inserted']} leads")

def run():
    for target in SEARCH_TARGETS:
        print(f"Searching: {target['query']}")
        places = search_places(target["query"])
        print(f"Found {len(places)} places")
        batch = []
        for place in places:
            try:
                details = get_details(place["place_id"])
                phone   = details.get("formatted_phone_number")
                website = details.get("website")
                name    = details.get("name", "")
                category = target["category"]

                if phone and not website:
                    description = f"A {category} business named {name} with no active website."
                    batch.append({
                        "business_name": name,
                        "category":      category,
                        "address":       details.get("formatted_address"),
                        "rating":        details.get("rating"),
                        "review_count":  details.get("user_ratings_total"),
                        "phone":         phone,
                        "description":   description,
                    })
                    print(f"Added: {name} | desc: {description[:50]}")
            except Exception as e:
                print(f"Skipped: {e}")
            time.sleep(0.2)
        print(f"Qualified: {len(batch)}")
        push_leads(batch)

if __name__ == "__main__":
    run()
