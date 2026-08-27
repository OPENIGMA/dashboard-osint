import json
import urllib.request
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
        # Nettoyage agressif des espaces dans les clés et valeurs
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

print(f"📊 {len(valid_events)} événements conservés (< 30 jours). ID max : {max_id}")

# ============================================================
# 4. Configuration des Flux RSS LOCAUX DIRECTS (Occitanie, PACA, Corse)
# ============================================================
LOCAL_RSS_FEEDS = [
    # Occitanie
    {"name": "La Dépêche du Midi", "url": "https://www.ladepeche.fr/rss.xml"},
    {"name": "Midi Libre", "url": "https://www.midilibre.fr/rss.xml"},
    {"name": "France 3 Occitanie", "url": "https://france3-regions.francetvinfo.fr/occitanie/rss"},
    {"name": "L'Indépendant", "url": "https://www.lindependant.fr/rss.xml"},
    # PACA
    {"name": "La Provence", "url": "https://www.laprovence.com/rss.xml"},
    {"name": "Nice-Matin", "url": "https://www.nicematin.com/rss.xml"},
    {"name": "France 3 PACA", "url": "https://france3-regions.francetvinfo.fr/provence-alpes-cote-d-azur/rss"},
    # Corse
    {"name": "France 3 Corse", "url": "https://france3-regions.francetvinfo.fr/corse/rss"}
]

# Mots-clés pour associer un article local à l'une de tes 36 thématiques
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
# 5. Collecte DIRECTE depuis la Presse Locale (Occitanie, PACA, Corse)
# ============================================================
new_articles_count = 0
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

print("📡 Début de l'aspiration des flux RSS LOCAUX...")
for feed in LOCAL_RSS_FEEDS:
    feed_name = feed["name"]
    rss_url = feed["url"]
    try:
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')
            
            for item in items[:25]: # 25 derniers articles par média
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
                    continue # On ignore ce qui ne correspond à aucune de nos 36 thématiques

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
                    "source_type": "Presse Locale Directe", # <-- DÉCLENCHE LA COULEUR ORANGE
                    "theme": theme,
                    "location": location
                })
                new_articles_count += 1
        time.sleep(2) # Délai de courtoisie
    except Exception as e:
        print(f"   ⚠️ Erreur sur {feed_name}: {e}")

print(f"✅ {new_articles_count} articles locaux ajoutés.")

# ============================================================
# 6. Collecte complémentaire via Google News (pour élargir)
# ============================================================
GN_QUERIES = [
    {"theme": "Agriculture", "query": "agriculture OR FNSEA OR EGalim OR PAC"},
    {"theme": "Criminalité organisée", "query": "narcotrafic OR grand banditisme OR point deal"},
    {"theme": "Projet aménagement contesté (PAC)", "query": "ZAD OR bassine OR A69 OR contestation"},
    {"theme": "Manifestation", "query": "manifestation OR cortège OR CRS OR mobilisation"},
    {"theme": "Blocage grève", "query": "grève OR blocage OR syndicat OR piquet"}
]

print("🔍 Début des requêtes Google News complémentaires...")
for item_target in GN_QUERIES:
    theme = item_target["theme"]
    query = item_target["query"]
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fr&gl=FR&ceid=FR:fr"

    try:
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')
            
            for item in items[:10]:
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
                
                seen_urls.add(link)
                seen_titles.add(title)
                location = detect_location(title)
                source_elem = item.find('source')
                raw_source = source_elem.text.strip() if source_elem is not None and source_elem.text else "Presse"
                
                max_id += 1
                valid_events.append({
                    "id": f"evt-{max_id}",
                    "timestamp": pub_iso,
                    "title": title,
                    "summary": f"Article via Google News.",
                    "url": link,
                    "source_name": raw_source,
                    "source_type": "Google News", # <-- RESTE EN BLEU PAR DÉFAUT
                    "theme": theme,
                    "location": location
                })
                new_articles_count += 1
        time.sleep(3)
    except Exception as e:
        print(f"   ⚠️ Erreur Google News [{theme}]: {e}")

# ============================================================
# 7. Tri et sauvegarde finale
# ============================================================
valid_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(valid_events, f, ensure_ascii=False, indent=2)

print(f"🎉 SUCCÈS TOTAL : {len(valid_events)} alertes en base (+{new_articles_count} nouveaux).")
