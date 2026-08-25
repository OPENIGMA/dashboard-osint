import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import os

# 1. Chargement de la base de données locale des communes
CITIES_DB = {}
if os.path.exists('communes.json'):
    try:
        with open('communes.json', 'r', encoding='utf-8') as f:
            CITIES_DB = json.load(f)
        print(f"Base locale chargée : {len(CITIES_DB)} communes disponibles.")
    except Exception as e:
        print(f"Erreur lecture communes.json : {e}")

SEARCH_QUERIES = [
    {"theme": "Agriculture", "source_type": "Presse", "query": "agriculteurs OR fnsea OR tracteurs Occitanie OR PACA"},
    {"theme": "Blocage occupation", "source_type": "Presse", "query": "blocage autoroute OR barrage routier Toulouse OR Montpellier OR Marseille OR Nîmes OR Béziers OR Avignon OR Gap"},
    {"theme": "Manifestation", "source_type": "Presse", "query": "manifestation cortège Nîmes OR Perpignan OR Toulon OR Nice OR Avignon OR Albi OR Béziers OR Gap OR Digne"},
    {"theme": "Projet Amenagement Conteste", "source_type": "Presse", "query": "A69 OR autoroute OR bassine contestation Occitanie OR PACA"},
    {"theme": "Criminalite organisee", "source_type": "Presse", "query": "narcotrafic OR fusillade OR point de deal Marseille OR Nîmes OR Avignon OR Cavaillon"},
    {"theme": "Agriculture", "source_type": "X (Twitter)", "query": "site:x.com OR site:twitter.com agriculteurs OR tracteurs Occitanie OR PACA"},
    {"theme": "Agriculture", "source_type": "TikTok", "query": "site:tiktok.com agriculteurs OR manifestation Occitanie OR PACA"},
    {"theme": "Agriculture", "source_type": "Facebook", "query": "site:facebook.com/groups OR site:facebook.com agriculteurs en colère Occitanie OR PACA"}
]

def detect_location(text):
    text_lower = text.lower()
    normalized_text = re.sub(r'[-–—]', ' ', text_lower)
    
    sorted_cities = sorted(CITIES_DB.keys(), key=len, reverse=True)
    
    for city_key in sorted_cities:
        if len(city_key) > 3 and (re.search(r'\b' + re.escape(city_key) + r'\b', text_lower) or re.search(r'\b' + re.escape(city_key) + r'\b', normalized_text)):
            info = CITIES_DB[city_key]
            return {
                "region": info["region"].upper(),
                "department": str(info["department"]).zfill(2),
                "city": info["city"],
                "lat": info["lat"],
                "lng": info["lng"]
            }
            
    if "occitanie" in text_lower:
        return {"region": "OCCITANIE", "department": "31", "city": "Toulouse", "lat": 43.6047, "lng": 1.4442}
    return {"region": "PACA", "department": "13", "city": "Marseille", "lat": 43.2965, "lng": 5.3698}

events = []
event_id = 1
seen_titles = set()

for item_target in SEARCH_QUERIES:
    theme = item_target["theme"]
    source_type = item_target["source_type"]
    query = item_target["query"]
    
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fr&gl=FR&ceid=FR:fr"
    
    try:
        req = urllib.request.Request(
            rss_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall('.//item')[:10]:
                title = item.find('title').text if item.find('title') is not None else ''
                link = item.find('link').text if item.find('link') is not None else '#'
                
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                source_elem = item.find('source')
                raw_source = source_elem.text if source_elem is not None else "Web"
                display_source = f"{source_type} ({raw_source})" if source_type != "Presse" else raw_source

                clean_text = re.sub('<[^<]+?>', '', title)
                location = detect_location(clean_text)
                
                events.append({
                    "id": f"evt-{event_id}",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "title": title,
                    "summary": f"Publication issue de {display_source} concernant la thématique {theme}.",
                    "url": link,
                    "source_name": display_source,
                    "theme": theme,
                    "location": location
                })
                event_id += 1
    except Exception as e:
        print(f"Avertissement requête non aboutie ({theme}): {e}")

with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(events, f, ensure_ascii=False, indent=2)

print(f"Exécution terminée : {len(events)} alertes générées.")
