import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
import re

# Chargement de la taxonomie
try:
    with open('taxonomy.json', 'r', encoding='utf-8') as f:
        taxonomy = json.load(f)
except Exception:
    taxonomy = {"geography": {"regions": []}}

# Coordonnées des villes principales
CITY_COORDS = {
    "Toulouse": [43.6047, 1.4442], "Montpellier": [43.6108, 3.8767], "Nîmes": [43.8367, 4.3601],
    "Perpignan": [42.6986, 2.8956], "Béziers": [43.3442, 3.2158], "Carcassonne": [43.2130, 2.3537],
    "Narbonne": [43.1843, 3.0040], "Albi": [43.9289, 2.1464], "Tarbes": [43.2333, 0.0833],
    "Rodez": [44.3516, 2.5758], "Montauban": [44.0175, 1.3547], "Auch": [43.6465, 0.5856],
    "Cahors": [44.4479, 1.4419], "Foix": [42.9639, 1.6053], "Mende": [44.5180, 3.5000],
    "Marseille": [43.2965, 5.3698], "Nice": [43.7102, 7.2620], "Toulon": [43.1242, 5.9280],
    "Aix-en-Provence": [43.5297, 5.4474], "Avignon": [43.9493, 4.8055], "Ajaccio": [41.9272, 8.7346], "Bastia": [42.7028, 9.4500]
}

# RECHERCHES CIBLÉES EN ZONE SUD (Exemples de requêtes dynamiques)
SEARCH_QUERIES = [
    {"theme": "Agriculture", "query": "agriculteurs OR fnsea OR tracteurs OR FNSEA Occitanie OR PACA"},
    {"theme": "Drones", "query": "survol drone OR uav interdit Marseille OR Toulouse OR Nice"},
    {"theme": "Blocage occupation", "query": "blocage autoroute OR barrage routier Toulouse OR Montpellier OR Marseille"},
    {"theme": "Manifestation", "query": "manifestation cortège Nîmes OR Perpignan OR Toulon OR Nice"},
    {"theme": "Cybercriminalité", "query": "cyberattaque OR piratage hôpital OR mairie Occitanie OR PACA"},
    {"theme": "Projet Amenagement Conteste", "query": "A69 OR autoroute OR bassine contestation Occitanie"},
    {"theme": "Criminalite organisee", "query": "narcotrafic OR fusillade OR point de deal Marseille OR Nîmes OR Avignon"}
]

def detect_location(text):
    text_lower = text.lower()
    if "geography" in taxonomy:
        for region in taxonomy["geography"]["regions"]:
            for dept in region["departments"]:
                for city in dept.get("cities", []):
                    if city.lower() in text_lower:
                        coords = CITY_COORDS.get(city, [43.5, 5.0])
                        return {
                            "region": region["code"],
                            "department": dept["code"],
                            "city": city,
                            "lat": coords[0],
                            "lng": coords[1]
                        }
    # Défaut Occitanie / PACA
    if "occitanie" in text_lower or "toulouse" in text_lower:
        return {"region": "OCC", "department": "31", "city": "Toulouse", "lat": 43.6047, "lng": 1.4442}
    return {"region": "PACA", "department": "13", "city": "Marseille", "lat": 43.2965, "lng": 5.3698}

events = []
event_id = 1
seen_titles = set()

for item_target in SEARCH_QUERIES:
    theme = item_target["theme"]
    query = item_target["query"]
    
    # Construction du flux RSS dynamique Google News
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fr&gl=FR&ceid=FR:fr"
    
    try:
        req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall('.//item')[:15]:
                title = item.find('title').text if item.find('title') is not None else ''
                link = item.find('link').text if item.find('link') is not None else '#'
                pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
                
                # Éviter les doublons
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                # Extraction de la source
                source_elem = item.find('source')
                source_name = source_elem.text if source_elem is not None else "Presse Locale"
                
                clean_text = re.sub('<[^<]+?>', '', title)
                location = detect_location(clean_text)
                
                events.append({
                    "id": f"evt-{event_id}",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "title": title,
                    "summary": f"Article presse ({source_name}) relatif à la thématique {theme}.",
                    "url": link,
                    "source_name": source_name,
                    "theme": theme,
                    "location": location
                })
                event_id += 1
    except Exception as e:
        print(f"Erreur sur la requête {theme}: {e}")

# Sauvegarde
with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(events, f, ensure_ascii=False, indent=2)

print(f"Succès : {len(events)} alertes extraites du web.")
