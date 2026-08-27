import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import re
import os
from email.utils import parsedate_to_datetime

# 1. Chargement de la base locale des communes
CITIES_DB = {}
if os.path.exists('communes.json'):
    try:
        with open('communes.json', 'r', encoding='utf-8') as f:
            CITIES_DB = json.load(f)
        print(f"Base locale chargée : {len(CITIES_DB)} communes.")
    except Exception as e:
        print(f"Erreur communes.json : {e}")

# Charge les données existantes si le fichier existe déjà
existing_events = []
if os.path.exists('data_feed.json'):
    try:
        with open('data_feed.json', 'r', encoding='utf-8') as f:
            existing_events = json.load(f)
    except Exception:
        existing_events = []

# Filtrage : On supprime d'entrée ce qui a plus de 30 jours
now = datetime.now(timezone.utc)
cutoff_30d = now - timedelta(days=30)

valid_events = []
seen_titles = set()

for evt in existing_events:
    try:
        evt_time = datetime.fromisoformat(evt["timestamp"].replace("Z", "+00:00"))
        if evt_time >= cutoff_30d:
            valid_events.append(evt)
            seen_titles.add(evt["title"])
    except Exception:
        continue

# Mots-clés optimisés avec filtre "when:7d" pour forcer les articles récents
SEARCH_QUERIES = [
    {"theme": "Agriculture", "source_type": "Presse", "query": "(agriculteurs OR fnsea OR tracteurs) (Occitanie OR PACA) when:7d"},
    {"theme": "Blocage occupation", "source_type": "Presse", "query": "(blocage OR barrage) (Toulouse OR Marseille OR Nîmes OR Béziers OR Avignon OR Gap) when:7d"},
    {"theme": "Manifestation", "source_type": "Presse", "query": "manifestation (Nîmes OR Perpignan OR Toulon OR Nice OR Avignon OR Albi OR Béziers) when:7d"},
    {"theme": "Projet Conteste", "source_type": "Presse", "query": "(A69 OR autoroute OR bassine) (Occitanie OR PACA) when:7d"},
    {"theme": "Criminalite", "source_type": "Presse", "query": "(narcotrafic OR fusillade OR \"point de deal\") (Marseille OR Nîmes OR Avignon) when:7d"}
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

event_id = len(valid_events) + 1
new_articles_count = 0

for item_target in SEARCH_QUERIES:
    theme = item_target["theme"]
    source_type = item_target["source_type"]
    query = item_target["query"]
    
    encoded_query = urllib.parse.quote(query)
    # Ajout du paramètre sort par date dans l'URL RSS
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fr&gl=FR&ceid=FR:fr"
    
    try:
        req = urllib.request.Request(
            rss_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            items = root.findall('.//item')
            print(f"[{theme}] {len(items)} articles trouvés dans le flux RSS.")

            for item in items[:10]:
                title = item.find('title').text if item.find('title') is not None else ''
                link = item.find('link').text if item.find('link') is not None else '#'
                pub_date_raw = item.find('pubDate').text if item.find('pubDate') is not None else ''
                
                # Parsing de la date RFC822 de Google (ex: "Wed, 27 Aug 2026 06:30:00 GMT") vers ISO
                pub_iso = datetime.now(timezone.utc).isoformat()
                if pub_date_raw:
                    try:
                        parsed_dt = parsedate_to_datetime(pub_date_raw)
                        pub_iso = parsed_dt.isoformat()
                    except Exception:
                        pass

                if title in seen_titles:
                    continue
                seen_titles.add(title)

                source_elem = item.find('source')
                raw_source = source_elem.text if source_elem is not None else "Web"
                display_source = f"{source_type} ({raw_source})" if source_type != "Presse" else raw_source

                clean_text = re.sub('<[^<]+?>', '', title)
                location = detect_location(clean_text)
                
                valid_events.append({
                    "id": f"evt-{event_id}",
                    "timestamp": pub_iso,  # Utilise la date réelle de publication
                    "pubDate": pub_date_raw,
                    "title": title,
                    "summary": f"Alerte issue de {display_source}.",
                    "url": link,
                    "source_name": display_source,
                    "theme": theme,
                    "location": location
                })
                event_id += 1
                new_articles_count += 1
    except Exception as e:
        print(f"Avertissement ({theme}): {e}")

# Trier tous les événements par date décroissante (les plus récents en premier)
valid_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

# Enregistrement du fichier avec purge automatique appliquée
with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(valid_events, f, ensure_ascii=False, indent=2)

print(f"Terminé : {len(valid_events)} alertes valides dans la base ({new_articles_count} nouveaux articles ajoutés).")
