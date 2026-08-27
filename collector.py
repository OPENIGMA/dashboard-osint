import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import re
import os
import time
from email.utils import parsedate_to_datetime

# 1. Chargement et nettoyage de la base locale des communes
CITIES_DB = {}
if os.path.exists('communes.json'):
    try:
        with open('communes.json', 'r', encoding='utf-8') as f:
            raw_db = json.load(f)
            # Nettoyage automatique des espaces parasites dans les clés et valeurs
            for key, value in raw_db.items():
                clean_key = key.strip().lower()
                clean_value = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in value.items()}
                CITIES_DB[clean_key] = clean_value
        print(f"✅ Base locale chargée et nettoyée : {len(CITIES_DB)} communes.")
    except Exception as e:
        print(f"❌ Erreur communes.json : {e}")

# 2. Chargement des données existantes
existing_events = []
if os.path.exists('data_feed.json'):
    try:
        with open('data_feed.json', 'r', encoding='utf-8') as f:
            existing_events = json.load(f)
        print(f"✅ {len(existing_events)} événements existants chargés.")
    except Exception as e:
        print(f"⚠️ Erreur data_feed.json : {e}")
        existing_events = []

# 3. Filtrage : On conserve uniquement ce qui a moins de 30 jours
now = datetime.now(timezone.utc)
cutoff_30d = now - timedelta(days=30)
valid_events = []
seen_titles = set()

for evt in existing_events:
    try:
        # Nettoyage des clés et valeurs pour garantir un JSON propre
        clean_evt = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in evt.items()}
        if "location" in clean_evt and isinstance(clean_evt["location"], dict):
            clean_evt["location"] = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in clean_evt["location"].items()}
        
        ts = clean_evt.get("timestamp", "")
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        evt_time = datetime.fromisoformat(ts)
        if evt_time >= cutoff_30d:
            valid_events.append(clean_evt)
            seen_titles.add(clean_evt.get("title", ""))
    except Exception:
        continue

print(f"📊 {len(valid_events)} événements valides conservés (moins de 30 jours).")

# 4. Mots-clés de recherche
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
                    "region": str(info.get("region", "OCCITANIE")).upper().strip(),
                    "department": str(info.get("department", "31")).strip().zfill(2),
                    "city": str(info.get("city", "Toulouse")).strip(),
                    "lat": float(info.get("lat", 43.6047)),
                    "lng": float(info.get("lng", 1.4442))
                }
                
    if "occitanie" in text_lower:
        return {"region": "OCCITANIE", "department": "31", "city": "Toulouse", "lat": 43.6047, "lng": 1.4442}
    return {"region": "PACA", "department": "13", "city": "Marseille", "lat": 43.2965, "lng": 5.3698}

# 5. Récupération des nouveaux articles
event_id = len(valid_events) + 1
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
                        
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)
                
                source_elem = item.find('source')
                raw_source = source_elem.text.strip() if source_elem is not None and source_elem.text else "Presse Locale"
                
                location = detect_location(title)
                
                valid_events.append({
                    "id": f"evt-{event_id}",
                    "timestamp": pub_iso,
                    "title": title,
                    "summary": f"Article presse ({raw_source}) relatif à la thématique {theme}.",
                    "url": link,
                    "source_name": raw_source,
                    "theme": theme,
                    "location": location
                })
                event_id += 1
                new_articles_count += 1
                
        time.sleep(3) # Délai anti-blocage
        
    except Exception as e:
        print(f"   ❌ Erreur sur [{theme}]: {e}")

# 6. Tri et sauvegarde
valid_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(valid_events, f, ensure_ascii=False, indent=2)

print(f"🎉 Succès : {len(valid_events)} alertes totales (+{new_articles_count} nouveaux).")
