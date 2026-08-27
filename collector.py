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
# 4. Mots-clés pour le classement thématique
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

headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
new_articles_count = 0

# ============================================================
# 5. 🟠 Collecte PRESSE LOCALE (ORANGE)
# ============================================================
LOCAL_RSS_FEEDS = [
    {"name": "La Dépêche du Midi", "url": "https://www.ladepeche.fr/rss.xml"},
    {"name": "Midi Libre", "url": "https://www.midilibre.fr/rss.xml"},
    {"name": "L'Indépendant", "url": "https://www.lindependant.fr/rss.xml"},
    {"name": "La Montagne", "url": "https://www.lamontagne.fr/rss.xml"},
    {"name": "Midi Olympique", "url": "https://www.midi-olympique.fr/rss"},
    {"name": "Le Journal Toulousain", "url": "https://www.journaltoulousain.fr/feed/"},
    {"name": "La Gazette du Midi", "url": "https://www.lagazettedumidi.com/feed/"},
    {"name": "La Gazette Ariégeoise", "url": "https://www.lagazetteariegeoise.fr/feed/"},
    {"name": "Le Journal de Millau", "url": "https://www.journaldemillau.fr/feed/"},
    {"name": "Lozère Nouvelle", "url": "https://www.lozerenouvelle.fr/rss.xml"},
    {"name": "La Provence", "url": "https://www.laprovence.com/rss.xml"},
    {"name": "Nice-Matin", "url": "https://www.nicematin.com/rss.xml"},
    {"name": "Var-Matin", "url": "https://www.varmatin.com/rss.xml"},
    {"name": "La Marseillaise", "url": "https://www.lamarseillaise.fr/rss.xml"},
    {"name": "Le Dauphiné Libéré", "url": "https://www.ledauphine.com/rss.xml"},
    {"name": "Corse-Matin", "url": "https://www.corsematin.com/rss.xml"},
    {"name": "Corse Net Infos", "url": "https://www.corsenetinfos.corsica/feed/"},
    {"name": "Le Journal de la Corse", "url": "https://www.journaldelacorse.corsica/rss.xml"},
    {"name": "France 3 Occitanie", "url": "https://france3-regions.francetvinfo.fr/occitanie/rss"},
    {"name": "France 3 PACA", "url": "https://france3-regions.francetvinfo.fr/provence-alpes-cote-d-azur/rss"},
    {"name": "France 3 Corse", "url": "https://france3-regions.francetvinfo.fr/corse/rss"}
]

print("🟠 Début de l'aspiration des flux RSS LOCAUX (ORANGE)...")
for feed in LOCAL_RSS_FEEDS:
    feed_name = feed["name"]
    rss_url = feed["url"]
    try:
        req = urllib.request.Request(rss_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            items = root.findall('.//item')
            for item in items[:20]:
                title = item.find('title').text.strip() if item.find('title') is not None and item.find('title').text else ''
                link = item.find('link').text.strip() if item.find('link') is not None and item.find('link').text else '#'
                pub_date_raw = item.find('pubDate').text.strip() if item.find('pubDate') is not None and item.find('pubDate').text else ''
                pub_iso = datetime.now(timezone.utc).isoformat()
                if pub_date_raw:
                    try: pub_iso = parsedate_to_datetime(pub_date_raw).isoformat()
                    except Exception: pass
                if not title or link in seen_urls or title in seen_titles: continue
                theme = find_theme(title)
                if theme == "Non classé": continue
                seen_urls.add(link)
                seen_titles.add(title)
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
# 6. 🔴 Collecte RÉSEAUX SOCIAUX (ROUGE)
# ============================================================
SOCIAL_RSS_FEEDS = [
    {
        "platform": "Reddit (France)",
        "url": "https://www.reddit.com/r/France/new/.rss",
        "keywords": ["manifestation", "blocage", "incident", "police", "narcotrafic", "A69", "grève", "incendie", "fusillade", "drone", "tracteur", "ZAD"]
    },
    {
        "platform": "Mastodon (Piaille.fr)",
        "url": "https://piaille.fr/public/local.rss",
        "keywords": ["manifestation", "blocage", "incident", "police", "narcotrafic", "A69", "grève", "incendie", "ZAD", "tracteur"]
    }
]

print("🔴 Début de la collecte Réseaux Sociaux (ROUGE)...")
for social_feed in SOCIAL_RSS_FEEDS:
    platform = social_feed["platform"]
    rss_url = social_feed["url"]
    keywords = social_feed["keywords"]
    try:
        req = urllib.request.Request(rss_url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) OSINTBot/1.0'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            # Gestion hybride RSS (<item>) et Atom (<entry>)
            items = root.findall('.//item') or root.findall('.//{http://www.w3.org/2005/Atom}entry')
            
            for item in items[:20]:
                # Extraction du titre
                title_elem = item.find('title') or item.find('{http://www.w3.org/2005/Atom}title')
                title = title_elem.text.strip() if title_elem is not None and title_elem.text else ''
                
                # Extraction du lien
                link = '#'
                link_elem = item.find('link') or item.find('{http://www.w3.org/2005/Atom}link')
                if link_elem is not None:
                    link = link_elem.attrib.get('href', link_elem.text or '#').strip()

                title_lower = title.lower()
                if not any(kw in title_lower for kw in keywords): 
                    continue
                    
                if not title or link in seen_urls or title in seen_titles: 
                    continue
                    
                seen_urls.add(link)
                seen_titles.add(title)
                
                theme = find_theme(title)
                if theme == "Non classé": 
                    theme = "Reseaux Sociaux"
                    
                max_id += 1
                valid_events.append({
                    "id": f"evt-{max_id}", 
                    "timestamp": datetime.now(timezone.utc).isoformat(), 
                    "title": f"[{platform}] {title}", 
                    "summary": f"Post trouvé sur {platform}.", 
                    "url": link,
                    "source_name": platform, 
                    "source_type": "Reseaux Sociaux", 
                    "source_category": "red",
                    "theme": theme, 
                    "location": detect_location(title)
                })
                new_articles_count += 1
        time.sleep(2)
    except Exception as e:
        print(f"   ⚠️ Erreur sur {platform}: {e}")

# ============================================================
# 7. 🔵 Collecte GOOGLE NEWS (BLEU)
# ============================================================
GN_QUERIES = [
    {"theme": "Agriculture", "query": "agriculture OR agriculteur OR FNSEA OR EGalim OR PAC OR tracteur"},
    {"theme": "Armes", "query": "arme OR fusil OR pistolet OR kalachnikov OR trafic arme OR confiscation"},
    {"theme": "Chasse", "query": "chasse OR chasseur OR gibier OR ONCFS OR cynégétique OR battue"},
    {"theme": "Délinquance criminalité", "query": "délinquance OR insécurité OR cambriolage OR agression OR vol OR braquage"},
    {"theme": "Dérives Sectaires", "query": "secte OR dérive sectaire OR emprise mentale OR gourou OR MIVILUDES"},
    {"theme": "Ecologie", "query": "écologie OR environnement OR climat OR pollution OR biodiversité OR sécheresse"},
    {"theme": "Education nationale", "query": "école OR collège OR lycée OR professeur OR éducation nationale OR enseignant"},
    {"theme": "Ferroviaire", "query": "SNCF OR train OR gare OR rail OR ferroviaire OR TGV OR TER"},
    {"theme": "Festivité Evènements voie publique", "query": "festival OR fête OR événement OR rassemblement OR concert OR carnaval"},
    {"theme": "Criminalité organisée", "query": "narcotrafic OR mafia OR grand banditisme OR cartel OR point deal OR fusillade"},
    {"theme": "Free Rave Teknival", "query": "teknival OR free party OR rave party OR sound system OR fête sauvage"},
    {"theme": "Immigration", "query": "immigration OR migrant OR clandestin OR centre rétention OR OQTF OR sans-papiers"},
    {"theme": "Nucléaire", "query": "nucléaire OR centrale nucléaire OR EDF OR ASN OR réacteur OR uranium"},
    {"theme": "Pêche", "query": "pêche OR pêcheur OR maritime OR marée OR chalutier OR prud'homie"},
    {"theme": "Prévention de la délinquance", "query": "prévention OR police municipale OR vidéosurveillance OR médiation"},
    {"theme": "Santé", "query": "hôpital OR santé OR ARS OR médecin OR épidémie OR urgence OR SAMU"},
    {"theme": "Séparatisme", "query": "séparatisme OR communautarisme OR repli OR islam radical"},
    {"theme": "Survivalisme", "query": "survivalisme OR survivaliste OR bunker OR effondrement OR autonomie"},
    {"theme": "Transport", "query": "transport OR mobilité OR bus OR autoroute OR aéroport OR bouchon"},
    {"theme": "Visite officielle", "query": "visite officielle OR ministre OR préfet OR inauguration OR président"},
    {"theme": "Radicalisation", "query": "radicalisation OR fiché S OR endoctrinement OR salafisme OR djihadisme"},
    {"theme": "Culte", "query": "culte OR religion OR laïcité OR lieu de culte OR mosquée OR église"},
    {"theme": "Prosélytisme", "query": "prosélytisme OR endoctrinement OR conversion OR propagande"},
    {"theme": "Terrorisme", "query": "terrorisme OR attentat OR antiterroriste OR DGSI OR menace terroriste"},
    {"theme": "Animaliste", "query": "animaliste OR cause animale OR antispéciste OR L214 OR corrida"},
    {"theme": "Projet aménagement contesté (PAC)", "query": "ZAD OR bassine OR grand projet OR contestation OR A69 OR bétonisation"},
    {"theme": "Ultra gauche", "query": "ultra-gauche OR antifasciste OR black bloc OR anarchiste OR autonomes"},
    {"theme": "Ultra droite", "query": "ultra-droite OR identitaire OR extrême droite OR nationaliste OR suprémaciste"},
    {"theme": "JOPH 2030", "query": "JO 2030 OR jeux olympiques OR JO Paris OR olympique OR paralympique"},
    {"theme": "Elections 2027", "query": "élection 2027 OR présidentielle OR campagne électorale OR candidat"},
    {"theme": "Apologie", "query": "apologie OR apologie terrorisme OR incitation haine OR provocation"},
    {"theme": "Blocage grève", "query": "grève OR blocage OR syndicat OR piquet OR mouvement social"},
    {"theme": "Cybercriminalité", "query": "cyberattaque OR piratage OR ransomware OR hack OR fuite données"},
    {"theme": "Drones", "query": "drone OR survol OR aéronef OR télépilote OR zone interdite"},
    {"theme": "Intrusion", "query": "intrusion OR effraction OR squat OR occupation illicite"},
    {"theme": "Manifestation", "query": "manifestation OR cortège OR défilé OR rassemblement OR CRS"}
]

print("🔵 Début des requêtes Google News complémentaires (BLEU)...")
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
                title = item.find('title').text.strip() if item.find('title') is not None and item.find('title').text else ''
                link = item.find('link').text.strip() if item.find('link') is not None and item.find('link').text else '#'
                pub_date_raw = item.find('pubDate').text.strip() if item.find('pubDate') is not None and item.find('pubDate').text else ''
                pub_iso = datetime.now(timezone.utc).isoformat()
                if pub_date_raw:
                    try: pub_iso = parsedate_to_datetime(pub_date_raw).isoformat()
                    except Exception: pass
                if not title or link in seen_urls or title in seen_titles: continue
                seen_urls.add(link)
                seen_titles.add(title)
                source_elem = item.find('source')
                raw_source = source_elem.text.strip() if source_elem is not None and source_elem.text else "Presse"
                max_id += 1
                valid_events.append({
                    "id": f"evt-{max_id}", "timestamp": pub_iso, "title": title,
                    "summary": f"Article via Google News.", "url": link,
                    "source_name": raw_source, "source_type": "Google News", "source_category": "blue",
                    "theme": theme, "location": detect_location(title)
                })
                new_articles_count += 1
        time.sleep(2)
    except Exception as e:
        print(f"   ⚠️ Erreur Google News [{theme}]: {e}")

# ============================================================
# 8. Tri et sauvegarde finale
# ============================================================
valid_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(valid_events, f, ensure_ascii=False, indent=2)

print(f"🎉 SUCCÈS TOTAL : {len(valid_events)} alertes en base (+{new_articles_count} nouveaux).")
