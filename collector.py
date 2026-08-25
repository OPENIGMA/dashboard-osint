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

# 1. Chargement dynamique de toutes les communes des départements du Sud via l'API Gouv
CITIES_DB = {}

def load_all_communes():
    global CITIES_DB
    all_depts = []
    for depts in REGION_MAP.values():
        all_depts.extend(depts)
    
    print("Chargement du référentiel complet des communes (Occitanie, PACA, Corse)...")
    for dept in all_depts:
        try:
            url = f"https://geo.api.gouv.fr/departements/{dept}/communes?fields=nom,code,codeDepartement,centre"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                for city in data:
                    city_name = city['nom']
                    # Trouver la région
                    region_code = "OCC"
                    for reg, d_list in REGION_MAP.items():
                        if dept in d_list:
                            region_code = reg
                            break
                    
                    coords = city.get('centre', {}).get('coordinates', [5.0, 43.5])
                    CITIES_DB[city_name.lower()] = {
                        "city": city_name,
                        "department": city['codeDepartement'],
                        "region": region_code,
                        "lat": coords[1],
                        "lng": coords[0]
                    }
        except Exception as e:
            print(f"Erreur chargement dept {dept}: {e}")
            
    print(f"Référentiel prêt : {len(CITIES_DB)} communes indexées.")

load_all_communes()

# RECHERCHES CIBLÉES EN ZONE SUD
SEARCH_QUERIES = [
    {"theme": "Agriculture", "query": "agriculteurs OR fnsea OR tracteurs OR FNSEA Occitanie OR PACA"},
    {"theme": "Drones", "query": "survol drone OR uav interdit Marseille OR Toulouse OR Nice OR Toulon"},
    {"theme": "Blocage occupation", "query": "blocage autoroute OR barrage routier Toulouse OR Montpellier OR Marseille OR Nîmes"},
    {"theme": "Manifestation", "query": "manifestation cortège Nîmes OR Perpignan OR Toulon OR Nice OR Avignon OR Albi"},
    {"theme": "Cybercriminalité", "query": "cyberattaque OR piratage hôpital OR mairie Occitanie OR PACA"},
    {"theme": "Projet Amenagement Conteste", "query": "A69 OR autoroute OR bassine contestation Occitanie OR PACA"},
    {"theme": "Criminalite organisee", "query": "narcotrafic OR fusillade OR point de deal Marseille OR Nîmes OR Avignon OR Cavaillon"}
]

def detect_location(text):
    text_lower = text.lower()
    
    # Recherche du nom de commune dans le texte (tri par longueur décroissante pour éviter les faux positifs)
    sorted_cities = sorted(CITIES_DB.keys(), key=len, reverse=True)
    
    for city_key in sorted_cities:
        # Recherche du mot exact (évite de confondre 'Albi' dans 'Albigeois' si non souhaité, ou courtes chaînes)
        if len(city_key) > 3 and re.search(r'\b' + re.escape(city_key) + r'\b', text_lower):
            info = CITIES_DB[city_key]
            return {
                "region": info["region"],
                "department": info["department"],
                "city": info["city"],
                "lat": info["lat"],
                "lng": info["lng"]
            }
            
    # Position par défaut si aucune commune précise n'est détectée
    if "occitanie" in text_lower:
        return {"region": "OCC", "department": "31", "city": "Toulouse", "lat": 43.6047, "lng": 1.4442}
    return {"region": "PACA", "department": "13", "city": "Marseille", "lat": 43.2965, "lng": 5.3698}

events = []
event_id = 1
seen_titles = set()

for item_target in SEARCH_QUERIES:
    theme = item_target["theme"]
    query = item_target["query"]
    
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fr&gl=FR&ceid=FR:fr"
    
    try:
        req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall('.//item')[:20]:
                title = item.find('title').text if item.find('title') is not None else ''
                link = item.find('link').text if item.find('link') is not None else '#'
                pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ''
                
                if title in seen_titles:
                    continue
                seen_titles.add(title)

                source_elem = item.find('source')
                source_name = source_elem.text if source_elem is not None else "Presse"
                
                clean_text = re.sub('<[^<]+?>', '', title)
                location = detect_location(clean_text)
                
                events.append({
                    "id": f"evt-{event_id}",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "title": title,
                    "summary": f"Article de presse ({source_name}) relatif à la thématique {theme}.",
                    "url": link,
                    "source_name": source_name,
                    "theme": theme,
                    "location": location
                })
                event_id += 1
    except Exception as e:
        print(f"Erreur sur la requête {theme}: {e}")

# Sauvegarde des données collectées
with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(events, f, ensure_ascii=False, indent=2)

print(f"Succès : {len(events)} alertes géolocalisées et enregistrées.")
