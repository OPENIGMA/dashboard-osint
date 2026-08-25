import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import re

# Chargement de la taxonomie
with open('taxonomy.json', 'r', encoding='utf-8') as f:
    taxonomy = json.load(f)

# Coordonnées approximatives des villes pour le géocodage automatique
CITY_COORDS = {
    "Toulouse": [43.6047, 1.4442],
    "Montpellier": [43.6108, 3.8767],
    "Nîmes": [43.8367, 4.3601],
    "Perpignan": [42.6986, 2.8956],
    "Marseille": [43.2965, 5.3698],
    "Nice": [43.7102, 7.2620],
    "Toulon": [43.1242, 5.9280],
    "Avignon": [43.9493, 4.8055],
    "Ajaccio": [41.9272, 8.7346],
    "Bastia": [42.7028, 9.4500]
}

# Liste des flux RSS de test (Presse Sud & Nationale)
RSS_FEEDS = [
    {"name": "France Info", "url": "https://www.francetvinfo.fr/titres.rss"},
    {"name": "La Dépêche", "url": "https://www.ladepeche.fr/rss.xml"}
]

# Dictionnaire de correspondance Mots-clés -> Thématique
KEYWORD_MAP = {
    "Blocage occupation": ["blocage", "barrage", "occupé", "manifestants"],
    "Manifestation": ["manifestation", "rassemblement", "cortège", "grève"],
    "Cybercriminalité": ["piratage", "cyberattaque", "ransomware", "hacker"],
    "Séparatisme": ["communautarisme", "séparatisme"],
    "Terrorisme": ["attentat", "terroriste", "déchéance"],
    "Nucléaire": ["centrale", "nucléaire", "edf", "réacteur"],
    "Agriculture": ["agriculteurs", "fnsea", "tracteurs", "récolte"]
}

def detect_theme(text):
    text_lower = text.lower()
    for theme, keywords in KEYWORD_MAP.items():
        if any(kw in text_lower for kw in keywords):
            return theme
    return "Evenement voie publique" # Thème par défaut

def detect_location(text):
    for region in taxonomy["geography"]["regions"]:
        for dept in region["departments"]:
            for city in dept.get("cities", []):
                if city.lower() in text.lower():
                    coords = CITY_COORDS.get(city, [43.5, 5.0])
                    return {
                        "region": region["code"],
                        "department": dept["code"],
                        "city": city,
                        "lat": coords[0],
                        "lng": coords[1]
                    }
    # Localisation Sud par défaut (Zone Sud)
    return {
        "region": "PACA",
        "department": "13",
        "city": "Marseille",
        "lat": 43.2965,
        "lng": 5.3698
    }

events = []
event_id = 1

for feed in RSS_FEEDS:
    try:
        req = urllib.request.Request(feed["url"], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            # Traitement des items RSS
            for item in root.findall('.//item')[:15]: # Limité aux 15 derniers par flux
                title = item.find('title').text if item.find('title') is not None else ''
                desc = item.find('description').text if item.find('description') is not None else ''
                link = item.find('link').text if item.find('link') is not None else '#'
                
                # Nettoyage sommaire du texte
                full_text = f"{title} {desc}"
                clean_text = re.sub('<[^<]+?>', '', full_text)
                
                theme = detect_theme(clean_text)
                location = detect_location(clean_text)
                
                events.append({
                    "id": f"evt-{event_id}",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "title": title,
                    "summary": clean_text[:180] + "...",
                    "url": link,
                    "source_name": feed["name"],
                    "theme": theme,
                    "location": location
                })
                event_id += 1
    except Exception as e:
        print(f"Erreur sur le flux {feed['name']}: {e}")

# Sauvegarde dans data_feed.json
with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(events, f, ensure_ascii=False, indent=2)

print(f"Succès : {len(events)} alertes enregistrées dans data_feed.json")
