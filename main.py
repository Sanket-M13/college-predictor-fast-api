import re
import traceback
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from googleapiclient.discovery import build
from bs4 import BeautifulSoup

app = FastAPI()

# API Keys
GOOGLE_API_KEY = "AIzaSyBcVS3wIZlu9Yk7JPiw-M4Qq1CBGKfgft0"
CUSTOM_SEARCH_ENGINE_ID = "c3e72395eaa26458e"

# YouTube API setup
YOUTUBE_API_KEY = GOOGLE_API_KEY
youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

class CollegeQuery(BaseModel):
    college_name: str

def search_google(query, num=1):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": GOOGLE_API_KEY,
        "cx": CUSTOM_SEARCH_ENGINE_ID,
        "q": query,
        "num": num,
    }
    res = requests.get(url, params=params)
    res.raise_for_status()
    return res.json()

def search_youtube_video(query):
    request = youtube.search().list(
        part="snippet",
        q=query,
        type="video",
        maxResults=1,
    )
    response = request.execute()
    if response.get("items"):
        video_id = response["items"][0]["id"]["videoId"]
        return f"https://www.youtube.com/watch?v={video_id}"
    return "Not found"

def fetch_big_description(website_url):
    try:
        print(f"🧾 Fetching long description from {website_url}")
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(website_url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.content, "html.parser")

        # Try meta description
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return meta["content"].strip()

        # Fallback to longest paragraph
        paragraphs = soup.find_all("p")
        long_para = max(paragraphs, key=lambda p: len(p.get_text()), default=None)
        if long_para:
            return long_para.get_text().strip()
    except Exception as e:
        print(f"⚠️ Failed to fetch long description: {e}")
    return None

def sanitize_query(query):
    sanitized = re.sub(r"[^\w\s,]", "", query)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized

def get_location_from_nominatim(query):
    simple_name = sanitize_query(query)
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": simple_name,
        "format": "json",
        "limit": 1,
    }
    headers = {"User-Agent": "CollegeDetailsApp/1.0 (contact@example.com)"}
    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        if data:
            lat, lon = data[0]["lat"], data[0]["lon"]
            return f"https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=18/{lat}/{lon}"
    except Exception as e:
        print(f"❌ Nominatim error: {e}")
    return None

def fallback_google_maps_url(college_name):
    fallback_query = re.sub(r"(Society|Institute|College|Campus|Ltd|Pvt|Unitech|Trust|')", "", college_name, flags=re.I).strip()
    return f"https://www.google.com/maps/search/?api=1&query={requests.utils.quote(fallback_query)}"

@app.post("/college/details")
async def get_college_details(query: CollegeQuery):
    try:
        # Step 1: Google Custom Search
        search_data = search_google(query.college_name, num=1)
        if "items" not in search_data or not search_data["items"]:
            raise HTTPException(status_code=404, detail="College not found")

        top_result = search_data["items"][0]
        college_name = top_result.get("title", "N/A")
        description = top_result.get("snippet", "No description found.")
        website = top_result.get("link", "N/A")

        # Step 2: Enhance description from college website
        long_desc = fetch_big_description(website)
        if long_desc and len(long_desc) > len(description):
            description = long_desc

        # Step 3: Try Google Maps search via Custom Search
        maps_data = search_google(f"{query.college_name} location site:maps.google.com", num=1)
        maps_link = "Not found"
        if "items" in maps_data and maps_data["items"]:
            maps_link = maps_data["items"][0].get("link", "Not found")

        # Step 4: If still not found, try Nominatim
        location_status = "google"
        if maps_link == "Not found":
            maps_link = get_location_from_nominatim(query.college_name)
            location_status = "nominatim" if maps_link else "fallback"

        # Step 5: Final fallback
        if not maps_link:
            maps_link = fallback_google_maps_url(query.college_name)

        # Step 6: YouTube campus tour
        youtube_link = search_youtube_video(f"{query.college_name} campus tour")

        result = {
            "college_name": college_name,
            "description": description,
            "website": website,
            "google_maps_location": maps_link,
            "location_status": location_status,
            "youtube_video": youtube_link,
        }

        print("✅ Final College Details Retrieved:\n", result)
        return result

    except Exception as e:
        print("❌ Exception occurred:")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")
