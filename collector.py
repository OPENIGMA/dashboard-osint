import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import re
import os
import time
from email.utils import parsedate_to_datetime

# ============================================================
# 1. Chargement et NETTOYAGE de la base locale des communes
# ============================================================
CITIES_DB = {}
if os.path.exists('communes.json'):
    try:
        with open('communes.json', 'r', encoding='utf-8') as f:
            raw_db = json.load(f)
        for key, value in raw_db.items():
            clean_key = key.strip().lower()
            clean_value = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in value.items()}
            CITIES_DB[clean_key] = clean_value
        print(f"✅ Base locale chargée et nettoyée : {len(CITIES_DB)} communes.")
    except Exception as e:
        print(f"❌ Erreur communes.json : {e}")

# ============================================================
# 2. Chargement et NETTOYAGE des données existantes
# ============================================================
existing_events = []
if os.path.exists('data_feed.json'):
    try:
        with open('data_feed.json', 'r', encoding='utf-8') as f:
            raw_events = json.load(f)
        for evt in raw_events:
            clean_evt = {}
            for k, v in evt.items():
                ck = k.strip()
                if isinstance(v, str):
                    clean_evt[ck] = v.strip()
                elif isinstance(v, dict):
                    clean_evt[ck] = {dk.strip(): (dv.strip() if isinstance(dv, str) else dv) for dk, dv in v.items()}
                else:
                    clean_evt[ck] = v
            existing_events.append(clean_evt)
        print(f"✅ {len(existing_events)} événements existants chargés.")
    except Exception as e:
        print(f"⚠️ Erreur data_feed.json : {e}")

# ============================================================
# 3. Filtrage : conservation des événements de moins de 30 jours
# ============================================================
now = datetime.now(timezone.utc)
cutoff_30d = now - timedelta(days=30)
valid_events = []
seen_urls = set()
seen_titles = set()
max_id = 0

for evt in existing_events:
    try:
        evt_id = str(evt.get("id", ""))
        if evt_id.startswith("evt-"):
            try:
                num = int(evt_id.split("-")[1])
                if num > max_id: max_id = num
            except (ValueError, IndexError): pass

        ts = str(evt.get("timestamp", ""))
        if ts.endswith("Z"): ts = ts[:-1] + "+00:00"
        evt_time = datetime.fromisoformat(ts)
        if evt_time >= cutoff_30d:
            valid_events.append(evt)
            seen_urls.add(str(evt.get("url", "")))
            seen_titles.add(str(evt.get("title", "")))
    except Exception:
        continue

print(f" {len(valid_events)} événements conservés (< 30 jours). ID max : {max_id}")

# ============================================================
# 4. Configuration des Flux RSS LOCAUX DIRECTS (ORANGE)
# ============================================================
LOCAL_RSS_FEEDS = [
    {"name": "La Dépêche du Midi", "url": "https://www.ladepeche.fr/rss.xml"},
    {"name": "Midi Libre", "url": "https://www.midilibre.fr/rss.xml"},
    {"name": "France 3 Occitanie", "url": "https://france3-regions.francetvinfo.fr/occitanie/rss"},
    {"name": "L'Indépendant", "url": "https://www.lindependant.fr/rss.xml"},
    {"name": "La Provence", "url": "https://www.laprovence.com/rss.xml"},
    {"name": "Nice-Matin", "url": "https://www.nicematin.com/rss.xml"},
    {"name": "France 3 PACA", "url": "https://france3-regions.francetvinfo.fr/provence-alpes-cote-d-azur/rss"},
    {"name": "France 3 Corse", "url": "https://france3-regions.francetvinfo.fr/corse/rss"}
]

# ============================================================
# 5. Configuration Réseaux Sociaux (ROUGE) - Google Dorks + RSS
# ============================================================
SOCIAL_MEDIA_QUERIES = [
    # X/Twitter via Nitter (instance publique)
    {"platform": "X/Twitter", "query": "site:nitter.net (Occitanie OR PACA OR Marseille OR Toulouse) (manifestation OR blocage OR incident)", "source_type": "Reseaux Sociaux"},
    # Mastodon instances publiques
    {"platform": "Mastodon", "query": "site:mastodon.social OR site:mastodon.fr (Occitanie OR PACA)", "source_type": "Reseaux Sociaux"},
    # Telegram public channels via Google
    {"platform": "Telegram", "query": "site:t.me (Occitanie OR Marseille OR Toulouse) (alerte OR incident)", "source_type": "Reseaux Sociaux"},
    # Facebook public posts
    {"platform": "Facebook", "query": "site:facebook.com (Occitanie OR PACA) (manifestation OR blocage)", "source_type": "Reseaux Sociaux"}
]

THEME_KEYWORDS = {
    "Agriculture": ["agriculture", "agriculteur", "FNSEA", "EGalim", "PAC", "tracteur", "récolte", "élevage", "viticulture", "chambre agriculture"],
    "Armes": ["arme", "fusil", "pistolet", "kalachnikov", "trafic arme", "confiscation", "arsenal"],
    "Chasse": ["chasse", "chasseur", "gibier", "ONCFS", "cynégétique", "battue", "braconnage"],
    "Délinquance criminalité": ["délinquance", "insécurité", "cambriolage", "agression", "vol", "braquage", "vandalisme", "rixe"],
    "Dérives Sectaires": ["secte", "dérive sectaire", "emprise mentale", "gourou", "MIVILUDES"],
    "Ecologie": ["écologie", "environnement", "climat", "pollution", "biodiversité", "sécheresse", "incendie", "canicule"],
    "Education nationale": ["école", "collège", "lycée", "professeur", "éducation nationale", "enseignant", "harcèlement", "DASEN"],
    "Ferroviaire": ["SNCF", "train", "gare", "rail", "ferroviaire", "TGV", "TER", "grève SNCF"],
    "Festivité Evènements voie publique": ["festival", "fête", "événement", "rassemblement", "concert", "carnaval", "féria", "feu artifice"],
    "Criminalité organisée": ["narcotrafic", "mafia", "grand banditisme", "cartel", "point deal", "trafiquant", "DZ mafia", "fusillade", "caïd"],
    "Free Rave Teknival": ["teknival", "free party", "rave party", "sound system", "fête sauvage"],
    "Immigration": ["immigration", "migrant", "clandestin", "centre rétention", "OQTF", "sans-papiers", "CRA"],
    "Nucléaire": ["nucléaire", "centrale nucléaire", "EDF", "ASN", "réacteur", "uranium", "Tricastin", "Marcoule"],
    "Pêche": ["pêche", "pêcheur", "maritime", "marée", "chalutier", "prud'homie", "conchyliculture"],
    "Prévention de la délinquance": ["prévention", "police municipale", "vidéosurveillance", "médiation", "tranquillité publique", "CLSPD"],
    "Santé": ["hôpital", "santé", "ARS", "médecin", "épidémie", "urgence", "SAMU", "plan blanc", "désert médical"],
    "Séparatisme": ["séparatisme", "communautarisme", "repli", "islam radical", "contrat républicain"],
    "Survivalisme": ["survivalisme", "survivaliste", "bunker", "effondrement", "autonomie alimentaire", "prepper"],
    "Transport": ["transport", "mobilité", "bus", "autoroute", "aéroport", "bouchon", "péage", "Vinci"],
    "Visite officielle": ["visite officielle", "ministre", "préfet", "inauguration", "chef État", "président", "Darmanin", "Macron"],
    "Radicalisation": ["radicalisation", "fiché S", "endoctrinement", "salafisme", "djihadisme", "signalement"],
    "Culte": ["culte", "religion", "laïcité", "lieu de culte", "mosquée", "église", "imam", "prêtre"],
    "Prosélytisme": ["prosélytisme", "endoctrinement", "conversion", "propagande", "tabligh"],
    "Terrorisme": ["terrorisme", "attentat", "antiterroriste", "DGSI", "menace terroriste", "Vigipirate"],
    "Animaliste": ["animaliste", "cause animale", "antispéciste", "L214", "corrida", "abattoir", "végan"],
    "Projet aménagement contesté (PAC)": ["ZAD", "bassine", "grand projet", "contestation", "A69", "Toulouse Castres", "bétonisation", "Sivens"],
    "Ultra gauche": ["ultra-gauche", "antifasciste", "black bloc", "anarchiste", "autonomes", "NPA"],
    "Ultra droite": ["ultra-droite", "identitaire", "extrême droite", "nationaliste", "suprémaciste", "RN", "Rassemblement national"],
    "JOPH 2030": ["JO 2030", "jeux olympiques", "JO Paris", "olympique", "paralympique", "JO Nice", "JO Marseille"],
    "Elections 2027": ["élection 2027", "présidentielle", "campagne électorale", "candidat", "scrutin", "meeting"],
    "Apologie": ["apologie", "apologie terrorisme", "incitation haine", "provocation", "négationnisme"],
    "Blocage grève": ["grève", "blocage", "syndicat", "piquet", "CGT", "mouvement social", "escargot", "FO", "Sud"],
    "Cybercriminalité": ["cyberattaque", "piratage", "ransomware", "hack", "fuite données", "phishing", "ANSSI"],
    "Drones": ["drone", "survol", "aéronef", "télépilote", "zone interdite", "anti-drone"],
    "Intrusion": ["intrusion", "effraction", "cambriolage", "violation domicile", "squat", "occupation illicite"],
    "Manifestation": ["manifestation", "cortège", "défilé", "rassemblement", "mobilisation", "CRS", "lacrymogène", "gilet jaune"]
}

def detect_location(text):
    if not text: return {"region": "OCCITANIE", "department": "31", "city": "Toulouse", "lat": 43.6047, "lng": 1.4442}
    text_lower = text.lower()
    normalized_text = re.sub(r'[-–—]', ' ', text_lower)
    for city_key in sorted(CITIES_DB.keys(), key=len, reverse=True):
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
    if "occitanie" in text_lower: return {"region": "OCCITANIE", "department": "31", "city": "Toulouse", "lat": 43.6047, "lng": 1.4442}
    if "corse" in text_lower: return {"region": "CORSE", "department": "2A", "city": "Ajaccio", "lat": 41.9272, "lng": 8.7346}
    return {"region": "PACA", "department": "13", "city": "Marseille", "lat": 43.2965, "lng": 5.3698}

def find_theme(title):
    title_lower = title.lower()
    for theme, keywords in THEME_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return theme
    return "Non classé"

# ============================================================
# 6. Collecte DIRECTE depuis la Presse Locale (ORANGE)
# ============================================================
new_articles_count = 0
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

print("📡 Début de l'aspiration des flux RSS LOCAUX (ORANGE)...")
for feed in LOCAL_RSS_FEEDS:
    feed_name = feed["name"]
    rss_url = feed["url"]
    try:
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')
            
            for item in items[:25]:
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
                    except Exception: pass

                if not title or link in seen_urls or title in seen_titles:
                    continue
                
                theme = find_theme(title)
                if theme == "Non classé":
                    continue

                seen_urls.add(link)
                seen_titles.add(title)
                location = detect_location(title)
                max_id += 1
                
                valid_events.append({
                    "id": f"evt-{max_id}",
                    "timestamp": pub_iso,
                    "title": title,
                    "summary": f"Article direct de {feed_name}.",
                    "url": link,
                    "source_name": feed_name,
                    "source_type": "Presse Locale Directe",
                    "source_category": "orange",
                    "theme": theme,
                    "location": location
                })
                new_articles_count += 1
        time.sleep(1)
    except Exception as e:
        print(f"   ⚠️ Erreur sur {feed_name}: {e}")

print(f"✅ {new_articles_count} articles locaux (ORANGE) ajoutés.")

# ============================================================
# 7. Collecte Réseaux Sociaux via Google Dorks (ROUGE)
# ============================================================
print("🔴 Début de la collecte Réseaux Sociaux (ROUGE) via Google Dorks...")
for social_query in SOCIAL_MEDIA_QUERIES:
    platform = social_query["platform"]
    query = social_query["query"]
    source_type = social_query["source_type"]
    
    encoded_query = urllib.parse.quote(query)
    search_url = f"https://www.google.com/search?q={encoded_query}&hl=fr"
    
    try:
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            html_content = response.read().decode('utf-8')
            
            # Extraction basique des titres et liens (à améliorer avec BeautifulSoup si besoin)
            import re
            titles = re.findall(r'<h3[^>]*>([^<]+)</h3>', html_content)[:10]
            
            for title in titles:
                clean_title = re.sub(r'<[^>]+>', '', title).strip()
                if not clean_title or clean_title in seen_titles:
                    continue
                
                seen_titles.add(clean_title)
                location = detect_location(clean_title)
                theme = find_theme(clean_title)
                max_id += 1
                
                valid_events.append({
                    "id": f"evt-{max_id}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "title": clean_title,
                    "summary": f"Post trouvé via Google Dork sur {platform}.",
                    "url": search_url,
                    "source_name": platform,
                    "source_type": source_type,
                    "source_category": "red",
                    "theme": theme if theme != "Non classé" else "Reseaux Sociaux",
                    "location": location
                })
                new_articles_count += 1
                
        time.sleep(2)
    except Exception as e:
        print(f"   ⚠️ Erreur sur {platform}: {e}")

print(f"✅ {new_articles_count} posts réseaux sociaux (ROUGE) ajoutés.")

# ============================================================
# 8. Tri et sauvegarde finale
# ============================================================
valid_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(valid_events, f, ensure_ascii=False, indent=2)

print(f"🎉 SUCCÈS TOTAL : {len(valid_events)} alertes en base (+{new_articles_count} nouveaux).")
