import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import re
import os
import time
from email.utils import parsedate_to_datetime

# 1. Chargement de la base locale des communes
CITIES_DB = {}
if os.path.exists('communes.json'):
    try:
        with open('communes.json', 'r', encoding='utf-8') as f:
            CITIES_DB = json.load(f)
        print(f"✅ Base locale chargée : {len(CITIES_DB)} communes.")
    except Exception as e:
        print(f"❌ Erreur communes.json : {e}")

# 2. Chargement des données existantes
existing_events = []
if os.path.exists('data_feed.json'):
    try:
        with open('data_feed.json', 'r', encoding='utf-8') as f:
            existing_events = json.load(f)
        print(f"✅ {len(existing_events)} événements chargés depuis data_feed.json.")
    except Exception as e:
        print(f"⚠️ Erreur lecture data_feed.json : {e}")
        existing_events = []

# 3. Filtrage et conservation des IDs stables
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

# 4. Mots-clés avec syntaxe RSS standard
SEARCH_QUERIES = [
    {"theme": "Agriculture", "query": "agriculture Occitanie PACA"},
    {"theme": "Blocage occupation", "query": "blocage Toulouse Marseille Nîmes Avignon"},
    {"theme": "Manifestation", "query": "manifestation Nîmes Perpignan Toulon Nice Avignon"},
    {"theme": "Projet Amenagement Conteste", "query": "A69 autoroute bassine Occitanie PACA"},
    {"theme": "Criminalite organisee", "query": "narcotrafic fusillade Marseille Nîmes Avignon"}
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
                    "region": info["region"].upper().strip(),
                    "department": str(info["department"]).strip().zfill(2),
                    "city": info["city"].strip(),
                    "lat": float(info["lat"]),
                    "lng": float(info["lng"])
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
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'
    }
    
    try:
        print(f"🔍 Recherche : [{theme}] -> {query}")
        req = urllib.request.Request(rss_url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=15) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')
            print(f"   ✅ {len(items)} article(s) trouvé(s) dans le flux RSS.")
            
            for item in items[:15]:
                title_elem = item.find('title')
                title = title_elem.text if title_elem is not None else ''
                
                link_elem = item.find('link')
                link = link_elem.text if link_elem is not None else '#'
                
                pub_date_elem = item.find('pubDate')
                pub_date_raw = pub_date_elem.text if pub_date_elem is not None else ''
                
                pub_iso = datetime.now(timezone.utc).isoformat()
                if pub_date_raw:
                    try:
                        parsed_dt = parsedate_to_datetime(pub_date_raw)
                        pub_iso = parsed_dt.isoformat()
                    except Exception:
                        pass
                        
                clean_title = str(title).strip()
                clean_url = str(link).strip()
                
                # Vérification stricte des doublons par URL et par titre
                if not clean_title or clean_url in seen_urls or clean_title in seen_titles:
                    continue
                    
                seen_urls.add(clean_url)
                seen_titles.add(clean_title)
                
                source_elem = item.find('source')
                raw_source = source_elem.text if source_elem is not None else "Presse Locale"
                
                location = detect_location(clean_title)
                
                # Incrémentation stable de l'ID (garantit aucun chevauchement)
                max_id += 1
                
                valid_events.append({
                    "id": f"evt-{max_id}",
                    "timestamp": pub_iso,
                    "title": clean_title,
                    "summary": f"Article presse ({raw_source}) relatif à la thématique {theme}.",
                    "url": clean_url,
                    "source_name": str(raw_source).strip(),
                    "theme": theme,
                    "location": location
                })
                new_articles_count += 1
                
        time.sleep(3) # Délai pour éviter le blocage par Google
        
    except urllib.error.HTTPError as e:
        print(f"   ❌ Erreur HTTP {e.code} pour [{theme}]: {e.reason}")
    except Exception as e:
        print(f"   ❌ Erreur générale sur [{theme}]: {e}")

# 5. Trier tous les événements par date la plus récente
valid_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

# 6. Sauvegarde propre dans data_feed.json (élimine les espaces parasites dans les clés)
with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(valid_events, f, ensure_ascii=False, indent=2)

print(f"🎉 Succès : {len(valid_events)} alertes totales enregistrées (+{new_articles_count} nouveaux articles).")
