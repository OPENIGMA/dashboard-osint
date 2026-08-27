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
# 1. Chargement et nettoyage de la base locale des communes
# ============================================================
CITIES_DB = {}
if os.path.exists('communes.json'):
    try:
        with open('communes.json', 'r', encoding='utf-8') as f:
            raw_db = json.load(f)
        for key, value in raw_db.items():
            clean_key = key.strip().lower()
            clean_value = {}
            for k, v in value.items():
                ck = k.strip()
                cv = v.strip() if isinstance(v, str) else v
                clean_value[ck] = cv
            CITIES_DB[clean_key] = clean_value
        print(f"✅ Base locale chargée : {len(CITIES_DB)} communes.")
    except Exception as e:
        print(f"❌ Erreur communes.json : {e}")

# ============================================================
# 2. Chargement des données existantes
# ============================================================
existing_events = []
if os.path.exists('data_feed.json'):
    try:
        with open('data_feed.json', 'r', encoding='utf-8') as f:
            existing_events = json.load(f)
        print(f"✅ {len(existing_events)} événements chargés.")
    except Exception as e:
        print(f"⚠️ Erreur data_feed.json : {e}")
        existing_events = []

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
        clean_evt = {}
        for k, v in evt.items():
            ck = k.strip()
            if isinstance(v, str):
                clean_evt[ck] = v.strip()
            elif isinstance(v, dict):
                clean_evt[ck] = {dk.strip(): (dv.strip() if isinstance(dv, str) else dv) for dk, dv in v.items()}
            else:
                clean_evt[ck] = v

        evt_id = str(clean_evt.get("id", ""))
        if evt_id.startswith("evt-"):
            try:
                num = int(evt_id.split("-")[1])
                if num > max_id:
                    max_id = num
            except (ValueError, IndexError):
                pass

        ts = str(clean_evt.get("timestamp", ""))
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        evt_time = datetime.fromisoformat(ts)
        if evt_time >= cutoff_30d:
            valid_events.append(clean_evt)
            seen_urls.add(str(clean_evt.get("url", "")))
            seen_titles.add(str(clean_evt.get("title", "")))
    except Exception:
        continue

print(f"📊 {len(valid_events)} événements conservés (< 30 jours). ID max : {max_id}")

# ============================================================
# 4. Grille OSINT complète : 36 thématiques élargies
# ============================================================
SEARCH_QUERIES = [
    {
        "theme": "Agriculture",
        "query": "agriculture OR agriculteur OR FNSEA OR EGalim OR PAC OR tracteur OR moisson OR récolte OR élevage OR viticulture OR ferme OR agroalimentaire OR JA OR jeunes agriculteurs OR chambre agriculture"
    },
    {
        "theme": "Armes",
        "query": "arme OR fusil OR pistolet OR kalachnikov OR trafic armes OR confiscation OR arsenal OR munitions OR armurerie OR port arme OR arme blanche OR couteau"
    },
    {
        "theme": "Chasse",
        "query": "chasse OR chasseur OR gibier OR ONCFS OR cynégétique OR battue OR sanglier OR cerf OR permis chasse OR fédération chasse OR braconnage"
    },
    {
        "theme": "Délinquance criminalité",
        "query": "délinquance OR insécurité OR cambriolage OR agression OR vol OR braquage OR vandalisme OR rixe OR coups blessures OR délit OR récidive OR flagrant délit"
    },
    {
        "theme": "Dérives Sectaires",
        "query": "secte OR dérive sectaire OR emprise mentale OR gourou OR manipulation mentale OR MIVILUDES OR endoctrinement OR communauté fermée"
    },
    {
        "theme": "Ecologie",
        "query": "écologie OR environnement OR climat OR pollution OR biodiversité OR réchauffement OR carbone OR pesticide OR sécheresse OR inondation OR incendie OR canicule OR qualité air"
    },
    {
        "theme": "Education nationale",
        "query": "école OR collège OR lycée OR professeur OR éducation nationale OR enseignant OR recteur OR académie OR élève OR cantine scolaire OR harcèlement scolaire OR DASEN"
    },
    {
        "theme": "Ferroviaire",
        "query": "SNCF OR train OR gare OR rail OR ferroviaire OR TGV OR TER OR Intercités OR ligne ferroviaire OR retard train OR grève SNCF OR RER"
    },
    {
        "theme": "Festivité Evènements voie publique",
        "query": "festival OR fête OR événement OR rassemblement OR concert OR carnaval OR feria OR fête votive OR spectacle OR feu artifice OR fête foraine"
    },
    {
        "theme": "Criminalité organisée",
        "query": "narcotrafic OR mafia OR grand banditisme OR cartel OR point deal OR trafiquant OR blanchiment OR racket OR réseau criminel OR DZ mafia OR caïd OR guetteur"
    },
    {
        "theme": "Free Rave Teknival",
        "query": "teknival OR free party OR rave party OR sound system OR rave OR fête sauvage OR rassemblement illégal musique OR free OR teknival"
    },
    {
        "theme": "Immigration",
        "query": "immigration OR migrant OR clandestin OR centre rétention OR OQTF OR sans-papiers OR demandeur asile OR réfugié OR passeur OR frontière OR CRA OR HCR"
    },
    {
        "theme": "Nucléaire",
        "query": "nucléaire OR centrale nucléaire OR EDF OR ASN OR réacteur OR uranium OR déchet nucléaire OR irradiation OR Tricastin OR Cadarache OR Marcoule"
    },
    {
        "theme": "Pêche",
        "query": "pêche OR pêcheur OR maritime OR marée OR chalutier OR prud'homie OR quota pêche OR aquaculture OR conchyliculture OR port de pêche"
    },
    {
        "theme": "Prévention de la délinquance",
        "query": "prévention délinquance OR police municipale OR vidéosurveillance OR médiation OR tranquillité publique OR CLSPD OR voisinage OR sécurité publique"
    },
    {
        "theme": "Santé",
        "query": "hôpital OR santé OR ARS OR médecin OR épidémie OR urgence OR SAMU OR clinique OR désert médical OR plan blanc OR pharmacie OR infirmier"
    },
    {
        "theme": "Séparatisme",
        "query": "séparatisme OR communautarisme OR repli communautaire OR loi séparatisme OR contrat républicain OR islamisme OR islam radical"
    },
    {
        "theme": "Survivalisme",
        "query": "survivalisme OR survivaliste OR bunker OR effondrement OR autonomie alimentaire OR prepper OR préparation survie OR collapse"
    },
    {
        "theme": "Transport",
        "query": "transport OR mobilité OR bus OR autoroute OR aéroport OR tramway OR métro OR circulation OR bouchon OR péage OR Vinci autoroutes OR LiO"
    },
    {
        "theme": "Visite officielle",
        "query": "visite officielle OR ministre OR préfet OR inauguration OR déplacement ministériel OR chef État OR président OR sous-préfet OR Darmanin OR Macron"
    },
    {
        "theme": "Radicalisation",
        "query": "radicalisation OR fiché S OR endoctrinement OR radicalisé OR déradicalisation OR salafisme OR djihadisme OR signalement radicalisation"
    },
    {
        "theme": "Culte",
        "query": "culte OR religion OR laïcité OR lieu culte OR mosquée OR église OR synagogue OR temple OR imam OR prêtre OR pasteur OR aumônier"
    },
    {
        "theme": "Prosélytisme",
        "query": "prosélytisme OR endoctrinement OR conversion forcée OR propagande OR embrigadement OR prédication OR tabligh"
    },
    {
        "theme": "Terrorisme",
        "query": "terrorisme OR attentat OR antiterroriste OR DGSI OR menace terroriste OR cellule terroriste OR Etat islamique OR Al-Qaïda OR PNAT OR Vigipirate"
    },
    {
        "theme": "Animaliste",
        "query": "animaliste OR cause animale OR antispéciste OR L214 OR droits animaux OR maltraitance animale OR corrida OR abattoir OR végan OR SPA"
    },
    {
        "theme": "Projet aménagement contesté (PAC)",
        "query": "ZAD OR bassine OR grand projet OR contestation OR A69 OR Toulouse Castres OR autoroute contestée OR aménagement OR bétonisation OR artificialisation OR méga-bassine OR Sivens"
    },
    {
        "theme": "Ultra gauche",
        "query": "ultra-gauche OR antifasciste OR black bloc OR anarchiste OR autonomes OR NPA OR zadiste OR anticapitaliste OR antifascisme"
    },
    {
        "theme": "Ultra droite",
        "query": "ultra-droite OR identitaire OR extrême droite OR nationaliste OR suprémaciste OR néonazi OR skinhead OR RN OR Rassemblement national OR Reconquête"
    },
    {
        "theme": "JOPH 2030",
        "query": "JO 2030 OR jeux olympiques OR JO Paris OR olympique OR paralympique OR JO Nice OR JO Marseille OR JO Alpes OR CIO"
    },
    {
        "theme": "Elections 2027",
        "query": "élection 2027 OR présidentielle OR campagne électorale OR candidat OR scrutin OR législatives OR municipales OR meeting politique OR sondage"
    },
    {
        "theme": "Apologie",
        "query": "apologie OR apologie terrorisme OR incitation haine OR provocation OR glorification OR apologie crime OR négationnisme"
    },
    {
        "theme": "Blocage grève",
        "query": "grève OR blocage OR syndicat OR piquet grève OR CGT OR FO OR Sud OR préavis grève OR mouvement social OR opération escargot"
    },
    {
        "theme": "Cybercriminalité",
        "query": "cyberattaque OR piratage OR ransomware OR hack OR fuite données OR phishing OR malware OR cybersécurité OR virus informatique OR rançon OR ANSSI"
    },
    {
        "theme": "Drones",
        "query": "drone OR survol OR aéronef OR télépilote OR zone interdite OR drone sauvage OR anti-drone OR drone militaire"
    },
    {
        "theme": "Intrusion",
        "query": "intrusion OR effraction OR cambriolage OR violation domicile OR squat OR occupation illicite OR intrusion site sensible"
    },
    {
        "theme": "Manifestation",
        "query": "manifestation OR cortège OR défilé OR rassemblement OR mobilisation OR gilet jaune OR CRS OR forces ordre OR lacrymogène OR nasse"
    }
]

# ============================================================
# 5. Détection de localisation
# ============================================================
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

# ============================================================
# 6. Collecte des nouveaux articles
# ============================================================
new_articles_count = 0
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}

for item_target in SEARCH_QUERIES:
    theme = item_target["theme"]
    query = item_target["query"]
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=fr&gl=FR&ceid=FR:fr"

    try:
        print(f"🔍 [{theme}] -> {query[:50]}...")
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

                clean_title = str(title).strip()
                clean_url = str(link).strip()

                if not clean_title or clean_url in seen_urls or clean_title in seen_titles:
                    continue

                seen_urls.add(clean_url)
                seen_titles.add(clean_title)

                source_elem = item.find('source')
                raw_source = source_elem.text.strip() if source_elem is not None and source_elem.text else "Presse Locale"

                location = detect_location(clean_title)

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

        time.sleep(5)

    except urllib.error.HTTPError as e:
        print(f"   ❌ Erreur HTTP {e.code} pour [{theme}]: {e.reason}")
    except Exception as e:
        print(f"   ❌ Erreur sur [{theme}]: {e}")

# ============================================================
# 7. Tri et sauvegarde
# ============================================================
valid_events.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(valid_events, f, ensure_ascii=False, indent=2)

print(f"🎉 Succès : {len(valid_events)} alertes totales (+{new_articles_count} nouveaux articles).")
