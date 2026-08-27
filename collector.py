import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
import re
import os
import time
import random
from email.utils import parsedate_to_datetime

# ============================================================
# 1. NETTOYAGE et Chargement de communes.json
# ============================================================
CITIES_DB = {}
if os.path.exists('communes.json'):
    try:
        with open('communes.json', 'r', encoding='utf-8') as f:
            raw_db = json.load(f)
        clean_db = {}
        for key, value in raw_db.items():
            clean_key = key.strip().lower()
            clean_value = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in value.items()}
            clean_db[clean_key] = clean_value
        
        with open('communes.json', 'w', encoding='utf-8') as f:
            json.dump(clean_db, f, ensure_ascii=False, indent=2)
        CITIES_DB = clean_db
        print(f"✅ communes.json nettoyé. {len(CITIES_DB)} communes.")
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
# 3. Filtrage : conservation (< 30 jours) et empreintes
# ============================================================
now = datetime.now(timezone.utc)
cutoff_30d = now - timedelta(days=30)
valid_events = []
seen_urls = set()
seen_titles = set()
seen_normalized_titles = set()
max_id = 0

def normalize_title(title):
    """ Supprime le suffixe du média, la ponctuation et met en minuscules """
    title_clean = title.rsplit(' - ', 1)[0]
    title_clean = re.sub(r'[^\w\s]', '', title_clean.lower())
    return ' '.join(title_clean.split())

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
            if evt.get("url"): seen_urls.add(str(evt["url"]))
            if evt.get("title"): 
                seen_titles.add(str(evt["title"]))
                seen_normalized_titles.add(normalize_title(str(evt["title"])))
    except Exception:
        continue

print(f"📊 {len(valid_events)} événements conservés (< 30 jours). ID max : {max_id}")

# ============================================================
# 4. Mots-clés et fonctions utilitaires
# ============================================================
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
    if not text: 
        return {"region": "INCONNUE", "department": "N/A", "city": "Non localisé", "lat": None, "lng": None}
    
    text_lower = text.lower()
    normalized_text = re.sub(r'[-–—]', ' ', text_lower)
    
    for city_key in sorted(CITIES_DB.keys(), key=len, reverse=True):
        if len(city_key) > 3:
            pattern = r'\b' + re.escape(city_key) + r'\b'
            if re.search(pattern, text_lower) or re.search(pattern, normalized_text):
                info = CITIES_DB[city_key]
                return {
                    "region": str(info.get("region", "INCONNUE")).upper().strip(),
                    "department": str(info.get("department", "N/A")).strip().zfill(2),
                    "city": str(info.get("city", "Non localisé")).strip(),
                    "lat": float(info["lat"]) if info.get("lat") else None,
                    "lng": float(info["lng"]) if info.get("lng") else None
                }
                
    if "occitanie" in text_lower: 
        return {"region": "OCCITANIE", "department": "31", "city": "Toulouse", "lat": 43.6047, "lng": 1.4442}
    if "corse" in text_lower: 
        return {"region": "CORSE", "department": "2A", "city": "Ajaccio", "lat": 41.9272, "lng": 8.7346}
    if "paca" in text_lower: 
        return {"region": "PACA", "department": "13", "city": "Marseille", "lat": 43.2965, "lng": 5.3698}
        
    return {"region": "INCONNUE", "department": "N/A", "city": "Non localisé", "lat": None, "lng": None}

def find_theme(title):
    title_lower = title.lower()
    for theme, keywords in THEME_KEYWORDS.items():
        if any(kw in title_lower for kw in keywords):
            return theme
    return "Non classé"

HEADERS_BROWSER = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}
new_articles_count = 0

# ============================================================
# 5. 🟠 Collecte PRESSE LOCALE (ORANGE)
# ============================================================
LOCAL_RSS_FEEDS = [
    {"name": "La Dépêche du Midi", "url": "https://www.ladepeche.fr/rss.xml"},
    {"name": "Midi Libre", "url": "https://www.midilibre.fr/rss.xml"},
    {"name": "L'Indépendant", "url": "https://www.lindependant.fr/rss.xml"},
    {"name": "La Montagne", "url": "https://www.lamontagne.fr/rss.xml"},
    {"name": "Le Journal Toulousain", "url": "https://www.journaltoulousain.fr/feed/"},
    {"name": "La Gazette du Midi", "url": "https://www.lagazettedumidi.com/feed/"},
    {"name": "La Provence", "url": "https://www.laprovence.com/rss.xml"},
    {"name": "Nice-Matin", "url": "https://www.nicematin.com/rss.xml"},
    {"name": "Var-Matin", "url": "https://www.varmatin.com/rss.xml"},
    {"name": "La Marseillaise", "url": "https://www.lamarseillaise.fr/rss.xml"},
    {"name": "Le Dauphiné Libéré", "url": "https://www.ledauphine.com/rss.xml"},
    {"name": "Corse-Matin", "url": "https://www.corsematin.com/rss.xml"},
    {"name": "France 3 Occitanie", "url": "https://france3-regions.francetvinfo.fr/occitanie/rss"},
    {"name": "France 3 PACA", "url": "https://france3-regions.francetvinfo.fr/provence-alpes-cote-d-azur/rss"},
    {"name": "France 3 Corse", "url": "https://france3-regions.francetvinfo.fr/corse/rss"}
]

print("🟠 Début de la presse locale (ORANGE)...")
for feed in LOCAL_RSS_FEEDS:
    feed_name = feed["name"]
    try:
        req = urllib.request.Request(feed["url"], headers=HEADERS_BROWSER)
        with urllib.request.urlopen(req, timeout=10) as response:
            root = ET.fromstring(response.read())
            items = root.findall('.//item')
            for item in items[:20]:
                title = item.find('title').text.strip() if item.find('title') is not None and item.find('title').text else ''
                link = item.find('link').text.strip() if item.find('link') is not None and item.find('link').text else '#'
                
                clean_t = normalize_title(title)
                if not title or link in seen_urls or title in seen_titles or clean_t in seen_normalized_titles:
                    continue
                    
                theme = find_theme(title)
                if theme == "Non classé": continue

                pub_date_raw = item.find('pubDate').text.strip() if item.find('pubDate') is not None and item.find('pubDate').text else ''
                pub_iso = datetime.now(timezone.utc).isoformat()
                if pub_date_raw:
                    try: pub_iso = parsedate_to_datetime(pub_date_raw).isoformat()
                    except Exception: pass

                seen_urls.add(link)
                seen_titles.add(title)
                seen_normalized_titles.add(clean_t)
                max_id += 1
                
                valid_events.append({
                    "id": f"evt-{max_id}", "timestamp": pub_iso, "title": title,
                    "summary": f"Article direct de {feed_name}.", "url": link,
                    "source_name": feed_name, "source_type": "Presse Locale Directe", "source_category": "orange",
                    "theme": theme, "location": detect_location(title)
                })
                new_articles_count += 1
        time.sleep(1)
    except Exception as e:
        print(f"   ⚠️ Erreur sur {feed_name}: {e}")

# ============================================================
# 6bis. 🔴 Collecte X (TWITTER) et FACEBOOK via GOOGLE DORKS (ROUGE)
# ============================================================

# 1. Extraction automatique de TOUS les mots-clés de TOUTES tes thématiques
all_theme_keywords = set()
for theme, keywords in THEME_KEYWORDS.items():
    for kw in keywords:
        all_theme_keywords.add(kw)

# Création de la chaîne de recherche combinant tous tes mots-clés
theme_query_string = " OR ".join([f'"{kw}"' if " " in kw else kw for kw in all_theme_keywords])

# Dorks ciblant tes 36 thématiques sur les zones Sud (Occitanie, PACA, Corse)
DORK_FEEDS = [
    {
        "platform": "X (Twitter)",
        "query": f"site:x.com ({theme_query_string}) (Occitanie OR PACA OR Corse OR Toulouse OR Marseille OR Nice OR Montpellier OR Nîmes OR Toulon OR Ajaccio)"
    },
    {
        "platform": "Facebook",
        "query": f"site:facebook.com ({theme_query_string}) (Occitanie OR PACA OR Corse OR Toulouse OR Marseille OR Nice OR Montpellier OR Nîmes OR Toulon OR Ajaccio)"
    }
]

print("🔴 Début de la collecte X & Facebook via Google Dorks (ROUGE) sur TOUTES les thématiques...")
for dork in DORK_FEEDS:
    platform = dork["platform"]
    encoded_query = urllib.parse.quote(dork["query"])
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fr&gl=FR&ceid=FR:fr"
    
    try:
        req = urllib.request.Request(rss_url, headers=HEADERS_BROWSER)
        with urllib.request.urlopen(req, timeout=10) as response:
            root = ET.fromstring(response.read())
            items = root.findall('.//item')
            
            for item in items[:20]:
                raw_title = item.find('title').text.strip() if item.find('title') is not None and item.find('title').text else ''
                if not raw_title: continue
                
                # Nettoyage du titre
                title = raw_title.rsplit(' - ', 1)[0].strip()
                link = item.find('link').text.strip() if item.find('link') is not None and item.find('link').text else '#'
                
                clean_t = normalize_title(title)
                if link in seen_urls or title in seen_titles or clean_t in seen_normalized_titles:
                    continue
                    
                theme = find_theme(title)
                # Si le titre contient au moins une ville du Sud mais pas de mot-clé d'une thématique spécifique
                if theme == "Non classé": 
                    theme = "Reseaux Sociaux"

                seen_urls.add(link)
                seen_titles.add(title)
                seen_normalized_titles.add(clean_t)

                pub_date_raw = item.find('pubDate').text.strip() if item.find('pubDate') is not None and item.find('pubDate').text else ''
                pub_iso = datetime.now(timezone.utc).isoformat()
                if pub_date_raw:
                    try: pub_iso = parsedate_to_datetime(pub_date_raw).isoformat()
                    except Exception: pass
                
                max_id += 1
                valid_events.append({
                    "id": f"evt-{max_id}", 
                    "timestamp": pub_iso, 
                    "title": f"[{platform}] {title}", 
                    "summary": f"Publication {platform} détectée par Dork OSINT.", 
                    "url": link,
                    "source_name": platform, 
                    "source_type": "Reseaux Sociaux", 
                    "source_category": "red",  # Force la couleur ROUGE
                    "theme": theme, 
                    "location": detect_location(title)
                })
                new_articles_count += 1
                
        time.sleep(random.uniform(3.0, 5.0))
    except Exception as e:
        print(f"   ⚠️ Erreur Dork [{platform}]: {e}")

# ============================================================
# 7. 🔵 Collecte GOOGLE NEWS (BLEU) - Requêtes combinées
# ============================================================
GN_QUERIES_GROUPED = [
    {"category": "Ordre Public", "query": "manifestation OR grève OR blocage OR ZAD OR narcotrafic OR fusillade"},
    {"category": "Idéologies", "query": "radicalisation OR séparatisme OR dérive sectaire OR terrorisme OR ultra-gauche OR ultra-droite"},
    {"category": "Secteurs Stratégiques", "query": "agriculture OR FNSEA OR nucléaire OR SNCF OR ferroviaire OR transport"},
    {"category": "Institutions", "query": "visite officielle OR JO 2030 OR élection 2027 OR éducation nationale"},
    {"category": "Risques", "query": "cyberattaque OR ransomware OR drone survol OR intrusion"}
]

print("🔵 Début des requêtes Google News optimisées (BLEU)...")
for item_target in GN_QUERIES_GROUPED:
    encoded_query = urllib.parse.quote(item_target["query"])
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fr&gl=FR&ceid=FR:fr"
    
    try:
        req = urllib.request.Request(rss_url, headers=HEADERS_BROWSER)
        with urllib.request.urlopen(req, timeout=10) as response:
            root = ET.fromstring(response.read())
            items = root.findall('.//item')
            
            for item in items[:15]:
                raw_title = item.find('title').text.strip() if item.find('title') is not None and item.find('title').text else ''
                if not raw_title: continue
                
                title = raw_title.rsplit(' - ', 1)[0].strip() # Nettoyage suffixe média
                link = item.find('link').text.strip() if item.find('link') is not None and item.find('link').text else '#'
                
                clean_t = normalize_title(title)
                if link in seen_urls or title in seen_titles or clean_t in seen_normalized_titles:
                    continue
                    
                theme = find_theme(title)
                if theme == "Non classé": continue

                pub_date_raw = item.find('pubDate').text.strip() if item.find('pubDate') is not None and item.find('pubDate').text else ''
                pub_iso = datetime.now(timezone.utc).isoformat()
                if pub_date_raw:
                    try: pub_iso = parsedate_to_datetime(pub_date_raw).isoformat()
                    except Exception: pass

                seen_urls.add(link)
                seen_titles.add(title)
                seen_normalized_titles.add(clean_t)
                
                source_elem = item.find('source')
                raw_source = source_elem.text.strip() if source_elem is not None and source_elem.text else "Google News"
                
                max_id += 1
                valid_events.append({
                    "id": f"evt-{max_id}", 
                    "timestamp": pub_iso, 
                    "title": title,
                    "summary": f"Article via Google News ({raw_source}).", 
                    "url": link,
                    "source_name": raw_source, 
                    "source_type": "Google News", 
                    "source_category": "blue",
                    "theme": theme, 
                    "location": detect_location(title)
                })
                new_articles_count += 1
                
        time.sleep(random.uniform(2.5, 4.0))
    except Exception as e:
        print(f"   ⚠️ Erreur Google News [{item_target['category']}]: {e}")

# ============================================================
# 8. Tri et Sauvegarde
# ============================================================
valid_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(valid_events, f, ensure_ascii=False, indent=2)

print(f"🎉 SUCCÈS : {len(valid_events)} alertes sauvegardées (+{new_articles_count} nouveaux).")
