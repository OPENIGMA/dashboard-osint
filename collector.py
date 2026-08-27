import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import re
import os
import time
from email.utils import parsedate_to_datetime

# 1. Chargement et nettoyage automatique de la base locale des communes
CITIES_DB = {}
if os.path.exists('communes.json'):
    try:
        with open('communes.json', 'r', encoding='utf-8') as f:
            raw_db = json.load(f)
            # Nettoyage des espaces parasites dans les clés et valeurs
            for key, value in raw_db.items():
                clean_key = key.strip().lower()
                clean_value = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in value.items()}
                CITIES_DB[clean_key] = clean_value
        print(f"✅ Base locale chargée et nettoyée : {len(CITIES_DB)} communes.")
    except Exception as e:
        print(f"❌ Erreur communes.json : {e}")

# 2. Chargement et nettoyage des données existantes
existing_events = []
if os.path.exists('data_feed.json'):
    try:
        with open('data_feed.json', 'r', encoding='utf-8') as f:
            raw_events = json.load(f)
        # Nettoyage des espaces dans les clés des événements existants
        existing_events = []
        for evt in raw_events:
            clean_evt = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in evt.items()}
            if "location" in clean_evt and isinstance(clean_evt["location"], dict):
                clean_evt["location"] = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in clean_evt["location"].items()}
            existing_events.append(clean_evt)
        print(f"✅ {len(existing_events)} événements existants chargés et nettoyés.")
    except Exception as e:
        print(f"⚠️ Erreur lecture data_feed.json : {e}")
        existing_events = []

# 3. Filtrage : On conserve uniquement ce qui a moins de 30 jours
now = datetime.now(timezone.utc)
cutoff_30d = now - timedelta(days=30)
valid_events = []
seen_urls = set()
seen_titles = set()
max_id = 0

for evt in existing_events:
    # Trouver l'ID max pour la génération sécurisée des nouveaux IDs
    evt_id = str(evt.get("id", "")).strip()
    if evt_id.startswith("evt-"):
        try:
            num = int(evt_id.split("-")[1])
            if num > max_id:
                max_id = num
        except (ValueError, IndexError):
            pass
            
    # Filtrer par date et conserver les références uniques
    try:
        ts = str(evt.get("timestamp", "")).strip()
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        evt_time = datetime.fromisoformat(ts)
        if evt_time >= cutoff_30d:
            valid_events.append(evt)
            seen_urls.add(str(evt.get("url", "")).strip())
            seen_titles.add(str(evt.get("title", "")).strip())
    except Exception:
        continue

print(f"📊 {len(valid_events)} événements valides conservés (< 30 jours). ID max actuel : {max_id}")

# 4. Mots-clés avec syntaxe RSS standard élargie (36 thématiques)
SEARCH_QUERIES = [
    {"theme": "Agriculture", "query": "agriculture OR FNSEA OR EGalim OR tracteur OR PAC"},
    {"theme": "Armes", "query": "arme OR fusillade OR trafic d'armes OR confiscation"},
    {"theme": "Chasse", "query": "chasse OR chasseur OR gibier OR ONCFS"},
    {"theme": "Délinquance criminalité", "query": "délinquance OR insécurité OR cambriolage OR agression"},
    {"theme": "Dérives Sectaires", "query": "secte OR dérive sectaire OR emprise mentale"},
    {"theme": "Ecologie", "query": "écologie OR environnement OR climat OR pollution"},
    {"theme": "Education nationale", "query": "école OR collège OR lycée OR professeur OR éducation nationale"},
    {"theme": "Ferroviaire", "query": "SNCF OR train OR gare OR rail OR ferroviaire"},
    {"theme": "Festivité Evènements voie publique", "query": "festival OR fête OR événement OR rassemblement"},
    {"theme": "Criminalité organisée", "query": "narcotrafic OR mafia OR grand banditisme OR cartel"},
    {"theme": "Free Rave Teknival", "query": "teknival OR free party OR rave party OR sound system"},
    {"theme": "Immigration", "query": "immigration OR migrant OR clandestin OR centre de rétention"},
    {"theme": "Nucléaire", "query": "nucléaire OR centrale OR EDF OR ASN"},
    {"theme": "Pêche", "query": "pêche OR pêcheur OR maritime OR marée"},
    {"theme": "Prévention de la délinquance", "query": "prévention OR police municipale OR vidéosurveillance"},
    {"theme": "Santé", "query": "hôpital OR santé OR ARS OR médecin OR épidémie"},
    {"theme": "Séparatisme", "query": "séparatisme OR communautarisme OR repli"},
    {"theme": "Survivalisme", "query": "survivalisme OR survivaliste OR bunker"},
    {"theme": "Transport", "query": "transport OR mobilité OR bus OR autoroute OR aéroport"},
    {"theme": "Visite officielle", "query": "visite officielle OR ministre OR préfet OR inauguration"},
    {"theme": "Radicalisation", "query": "radicalisation OR fiché S OR endoctrinement"},
    {"theme": "Culte", "query": "culte OR religion OR laïcité OR lieu de culte"},
    {"theme": "Prosélytisme", "query": "prosélytisme OR endoctrinement OR conversion"},
    {"theme": "Terrorisme", "query": "terrorisme OR attentat OR antiterroriste OR DGSI"},
    {"theme": "Animaliste", "query": "animaliste OR cause animale OR antispéciste OR L214"},
    {"theme": "Projet aménagement contesté (PAC)", "query": "ZAD OR bassine OR grand projet OR contestation"},
    {"theme": "Ultra gauche", "query": "ultra-gauche OR antifasciste OR black bloc"},
    {"theme": "Ultra droite", "query": "ultra-droite OR identitaire OR extrême droite"},
    {"theme": "JOPH 2030", "query": "JO 2030 OR jeux olympiques OR JO Paris"},
    {"theme": "Elections 2027", "query": "élection 2027 OR présidentielle OR campagne électorale"},
    {"theme": "Apologie", "query": "apologie OR terrorisme OR haine"},
    {"theme": "Blocage grève", "query": "grève OR blocage OR syndicat OR cortège"},
    {"theme": "Cybercriminalité", "query": "cyberattaque OR piratage OR ransomware OR hack"},
    {"theme": "Drones", "query": "drone OR survol OR aéronef"},
    {"theme": "Intrusion", "query": "intrusion OR effraction OR cambriolage"},
    {"theme": "Manifestation", "query": "manifestation OR casseur OR CRS"}
]

def detect_location(text):
    if not text:
        return {"region": "OCCITANIE", "department": "31", "city": "Toulouse", "lat": 43.6047, "lng": 1.4442}
        
    text_lower = text.lower()
    normalized_text = re.sub(r'[-–—]', ' ', text_lower)
    sorted_cities = sorted(CITIES_DB.keys(), key=len, reverse=True)
    
    for city_key in sorted_cities:
        if len(city_key) > 3:
            pattern = r'\b' + re.escape(city_key) + r'\b'
            if re.search(pattern, text_lower) or re.search(pattern, normalized_text):
                info = CITIES_DB[city_key]
                return {
                    "region": str(info.get("region", "OCCITANIE")).upper().strip(),
                    "department": str(info.get("department", "31")).strip().zfill(2),
                    "city": str(info.get("city", "Toulouse")).strip(),
                    "lat": float(info.get("lat", 43.6047)),
                    "lng": float(info.get("lng", 1.4442))
                }
                
    if "occitanie" in text_lower:
        return {"region": "OCCITANIE", "department": "31", "city": "Toulouse", "lat": 43.6047, "lng": 1.4442}
    return {"region": "PACA", "department": "13", "city": "Marseille", "lat": 43.2965, "lng": 5.3698}

new_articles_count = 0

for item_target in SEARCH_QUERIES:
    theme = item_target["theme"]
    query = item_target["query"]
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fr&gl=FR&ceid=FR:fr"
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    
    try:
        print(f"🔍 Recherche : [{theme}] -> {query}")
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')
            print(f"   ✅ {len(items)} article(s) trouvé(s).")
            
            for item in items[:15]:
                title_elem = item.find('title')
                title = title_elem.text.strip() if title_elem is not None and title_elem.text else ''
                
                link_elem = item.find('link')
                link = link_elem.text.strip() if link_elem is not None and link_elem.text else '#'
                
                pub_date_elem = item.find('pubDate')
                pub_date_raw = pub_date_elem.text.strip() if pub_date_elem is not None and pub_date_elem.text else ''
                
                pub_iso = datetime.now(timezone.utc).isoformat()
                if pub_date_raw:
                    try:
                        parsed_dt = parsedate_to_datetime(pub_date_raw)
                        pub_iso = parsed_dt.isoformat()
                    except Exception:
                        pass
                        
                if not title or link in seen_urls or title in seen_titles:
                    continue
                    
                seen_urls.add(link)
                seen_titles.add(title)
                
                source_elem = item.find('source')
                raw_source = source_elem.text.strip() if source_elem is not None and source_elem.text else "Presse Locale"
                
                location = detect_location(title)
                
                # Incrémentation stable de l'ID (garantit aucun chevauchement)
                max_id += 1
                
                valid_events.append({
                    "id": f"evt-{max_id}",
                    "timestamp": pub_iso,
                    "title": title,
                    "summary": f"Article presse ({raw_source}) relatif à la thématique {theme}.",
                    "url": link,
                    "source_name": raw_source,
                    "theme": theme,
                    "location": location
                })
                new_articles_count += 1
                
        time.sleep(3) # Délai anti-blocage de Google
        
    except Exception as e:
        print(f"   ❌ Erreur sur [{theme}]: {e}")

# 5. Tri et sauvegarde propre (sans espaces parasites)
valid_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(valid_events, f, ensure_ascii=False, indent=2)

print(f"🎉 Succès : {len(valid_events)} alertes totales enregistrées (+{new_articles_count} nouveaux).")
