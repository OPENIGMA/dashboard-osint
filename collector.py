import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
import re

# Mapping des départements par Région
REGION_MAP = {
    "OCC": ["09", "11", "12", "30", "31", "32", "34", "46", "48", "65", "66", "81", "82"],
    "PACA": ["04", "05", "06", "13", "83", "84"],
    "COR": ["2A", "2B", "20"]
}

CITIES_DB = {}

def load_all_communes():
    global CITIES_DB
    all_depts = []
    for depts in REGION_MAP.values():
        all_depts.extend(depts)
    
    print("Chargement dynamique de toutes les communes (Occitanie, PACA, Corse)...")
    for dept in all_depts:
        try:
            # Téléchargement groupé par département
            url = f"https://geo.api.gouv.fr/departements/{dept}/communes?fields=nom,code,codeDepartement,centre"
            req = urllib.request.Request(url, headers={'User-Agent': 'OSINT-Collector/1.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                for city in data:
                    city_name = city['nom']
                    region_code = "OCC"
                    for reg, d_list in REGION_MAP.items():
                        if dept in d_list:
                            region_code = reg
                            break
                    
                    coords = city.get('centre', {}).get('coordinates', [5.0, 43.5])
                    
                    # Stockage du nom exact et version sans accent/tiret
                    clean_key = city_name.lower()
                    CITIES_DB[clean_key] = {
                        "city": city_name,
                        "department": city['codeDepartement'],
                        "region": region_code,
                        "lat": coords[1],
                        "lng": coords[0]
                    }
                    # Alternative sans tirets (ex: murviel les beziers)
                    if '-' in clean_key:
                        alt_key = clean_key.replace('-', ' ')
                        CITIES_DB[alt_key] = CITIES_DB[clean_key]
        except Exception as e:
            print(f"Avertissement chargement dept {dept}: {e}")
            
    print(f"Base chargée avec succès : {len(CITIES_DB)} entrées de communes indexées.")

# Chargement au démarrage
load_all_communes()

# RECHERCHES COMBINÉES : PRESSE & RÉSEAUX SOCIAUX
SEARCH_QUERIES = [
    {"theme": "Agriculture", "source_type": "Presse", "query": "agriculteurs OR fnsea OR tracteurs Occitanie OR PACA"},
    {"theme": "Blocage occupation", "source_type": "Presse", "query": "blocage autoroute OR barrage routier Toulouse OR Montpellier OR Marseille OR Nîmes OR Béziers"},
    {"theme": "Manifestation", "source_type": "Presse", "query": "manifestation cortège Nîmes OR Perpignan OR Toulon OR Nice OR Avignon OR Albi OR Béziers"},
    {"theme": "Projet Amenagement Conteste", "source_type": "Presse", "query": "A69 OR autoroute OR bassine contestation Occitanie OR PACA"},
    {"theme": "Criminalite organisee", "source_type": "Presse", "query": "narcotrafic OR fusillade OR point de deal Marseille OR Nîmes OR Avignon OR Cavaillon"},
    {"theme": "Agriculture", "source_type": "X (Twitter)", "query": "site:x.com OR site:twitter.com agriculteurs OR tracteurs Occitanie OR PACA"},
    {"theme": "Manifestation", "source_type": "X (Twitter)", "query": "site:x.com OR site:twitter.com manifestation OR blocage Toulouse OR Marseille OR Montpellier"},
    {"theme": "Agriculture", "source_type": "TikTok", "query": "site:tiktok.com agriculteurs OR manifestation Occitanie OR PACA"},
    {"theme": "Blocage occupation", "source_type": "TikTok", "query": "site:tiktok.com blocage OR convoi tracteurs Toulouse OR Marseille"},
    {"theme": "Agriculture", "source_type": "Facebook", "query": "site:facebook.com/groups OR site:facebook.com agriculteurs en colère Occitanie OR PACA"},
    {"theme": "Manifestation", "source_type": "Mastodon", "query": "site:mastodon.social OR site:piaille.fr manifestation OR A69 OR blocage"}
]

def detect_location(text):
    text_lower = text.lower()
    # Remplacement des tirets par des espaces pour uniformiser la recherche
    normalized_text = re.sub(r'[-–—]', ' ', text_lower)
    
    # Tri des communes par longueur décroissante pour éviter qu'une petite ville soit capturée dans un mot plus long
    sorted_cities = sorted(CITIES_DB.keys(), key=len, reverse=True)
    
    for city_key in sorted_cities:
        # Recherche uniquement sur les noms de villes de plus de 3 lettres
        if len(city_key) > 3 and (re.search(r'\b' + re.escape(city_key) + r'\b', text_lower) or re.search(r'\b' + re.escape(city_key) + r'\b', normalized_text)):
            info = CITIES_DB[city_key]
            return {
                "region": info["region"],
                "department": info["department"],
                "city": info["city"],
                "lat": info["lat"],
                "lng": info["lng"]
            }
            
    if "occitanie" in text_lower:
        return {"region": "OCC", "department": "31", "city": "Toulouse", "lat": 43.6047, "lng": 1.4442}
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
        req = urllib.request.Request(rss_url, headers={'User-Agent': 'OSINT-Collector/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall('.//item')[:15]:
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
        print(f"Erreur sur la requête {theme} ({source_type}): {e}")

# Sauvegarde
with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(events, f, ensure_ascii=False, indent=2)

print(f"Succès : {len(events)} alertes collectées et géolocalisées.")
