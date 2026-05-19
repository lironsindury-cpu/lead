import os, sqlite3, uuid, time, requests
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

GOOGLE_API_KEY = os.environ["GOOGLE_PLACES_API_KEY"]
DB_PATH = "instance/crm.db"

SEARCH_TARGETS = [
    {"query": "מסעדות תל אביב",     "category": "Restaurant"},
    {"query": "מספרות תל אביב",     "category": "Barbershop"},
    {"query": "מכון יופי תל אביב",  "category": "Beauty Salon"},
    {"query": "מוסך תל אביב",       "category": "Garage"},
]

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

def search_places(query):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": GOOGLE_API_KEY, "language": "iw"}
    results, next_page_token = [], None
    while True:
        if next_page_token:
            params["pagetoken"] = next_page_token
            time.sleep(2)
        data = requests.get(url, params=params, timeout=10).json()
        results.extend(data.get("results", []))
        next_page_token = data.get("next_page_token")
        if not next_page_token:
            break
    return results

def get_details(place_id):
    url = "https://maps.googleapis.com/maps/api/place/details/json"
    params = {"place_id": place_id, "fields": "name,formatted_phone_number,website,formatted_address,rating,user_ratings_total", "key": GOOGLE_API_KEY, "language": "iw"}
    return requests.get(url, params=params, timeout=10).json().get("result", {})

inserted = 0
for target in SEARCH_TARGETS:
    print(f"Searching: {target['query']}")
    for place in search_places(target["query"]):
        try:
            d = get_details(place["place_id"])
            phone = d.get("formatted_phone_number")
            if phone and not d.get("website"):
                name = d.get("name", "")
                desc = f"A {target['category']} business named {name} with no active website."
                cur.execute("""INSERT OR IGNORE INTO leads
                    (id, business_name, category, address, rating, review_count, phone, description, status, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,'raw',?,?)""",
                    (str(uuid.uuid4()), name, target["category"],
                     d.get("formatted_address"), d.get("rating"),
                     d.get("user_ratings_total"), phone, desc,
                     datetime.utcnow(), datetime.utcnow()))
                conn.commit()
                inserted += 1
                print(f"Added: {name}")
        except Exception as e:
            print(f"Skipped: {e}")
        time.sleep(0.2)

conn.close()
print(f"Total inserted: {inserted}")
