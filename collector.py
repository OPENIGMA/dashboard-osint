import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import re

# Chargement du dictionnaire géographique
try:
    with open('taxonomy.json', 'r', encoding='utf-8') as f:
        taxonomy = json.load(f)
except Exception as e:
    taxonomy = {"geography": {"regions": []}}

# Coordonnées des principales villes pour la cartographie
CITY_COORDS = {
    # Occitanie
    "Toulouse": [43.6047, 1.4442], "Montpellier": [43.6108, 3.8767], "Nîmes": [43.8367, 4.3601],
    "Perpignan": [42.6986, 2.8956], "Béziers": [43.3442, 3.2158], "Carcassonne": [43.2130, 2.3537],
    "Narbonne": [43.1843, 3.0040], "Albi": [43.9289, 2.1464], "Tarbes": [43.2333, 0.0833],
    "Rodez": [44.3516, 2.5758], "Montauban": [44.0175, 1.3547], "Auch": [43.6465, 0.5856],
    "Cahors": [44.4479, 1.4419], "Foix": [42.9639, 1.6053], "Mende": [44.5180, 3.5000],
    
    # PACA
    "Marseille": [43.2965, 5.3698], "Nice": [43.7102, 7.2620], "Toulon": [43.1242, 5.9280],
    "Aix-en-Provence": [43.5297, 5.4474], "Avignon": [43.9493, 4.8055], "Cannes": [43.5528, 7.0174],
    "Antibes": [43.5804, 7.1251], "Arles": [43.6767, 4.6278], "Fréjus": [43.4331, 6.7370],
    "Gap": [44.5594, 6.0798], "Digne-les-Bains": [44.0922, 6.2361], "Orange": [44.1381, 4.8078],
    
    # Corse
    "Ajaccio": [41.9272, 8.7346], "Bastia": [42.7028, 9.4500], "Porto-Vecchio": [41.5912, 9.2799],
    "Corte": [42.3060, 9.1500], "Calvi": [42.5686, 8.7574]
}

# 1. LISTE ÉTENDUE DES FLUX RSS (Presse locale, Institutionnels, Réseaux)
RSS_FEEDS = [
    # --- PRESSE REGIONALE : OCCITANIE ---
    {"name": "La Dépêche", "url": "https://www.ladepeche.fr/rss.xml", "region": "OCC"},
    {"name": "Midi Libre", "url": "https://www.midilibre.fr/rss.xml", "region": "OCC"},
    {"name": "L'Indépendant", "url": "https://www.lindependant.fr/rss.xml", "region": "OCC"},
    {"name": "France 3 Occitanie", "url": "https://france3-regions.francetvinfo.fr/occitanie/rss", "region": "OCC"},

    # --- PRESSE REGIONALE : PACA ---
    {"name": "La Provence", "url": "https://www.laprovence.com/rss/une.xml", "region": "PACA"},
    {"name": "Var-Matin", "url": "https://www.varmatin.com/rss", "region": "PACA"},
    {"name": "Nice-Matin", "url": "https://www.nicematin.com/rss", "region": "PACA"},
    {"name": "France 3 PACA", "url": "https://france3-regions.francetvinfo.fr/provence-alpes-cote-d-azur/rss", "region": "PACA"},

    # --- PRESSE REGIONALE : CORSE ---
    {"name": "Corse-Matin", "url": "https://www.corsematin.com/rss", "region": "COR"},
    {"name": "France 3 ViaStella", "url": "https://france3-regions.francetvinfo.fr/corse/rss", "region": "COR"},

    # --- INSTITUTIONNELS & SÉCURITÉ ---
    {"name": "Ministère Intérieur", "url": "https://www.interieur.gouv.fr/rss/actu.xml", "region": "NATIONAL"},
    {"name": "Gendarmerie Nationale", "url": "https://www.gendarmerie.interieur.gouv.fr/rss.xml", "region": "NATIONAL"},

    # --- FLUX RESEAUX SOCIAUX & VEILLE ---
    {"name": "France Info Titres", "url": "https://www.francetvinfo.fr/titres.rss", "region": "NATIONAL"}
]

# 2. DICTIONNAIRE DE 36 THÉMATIQUES (CHAMP LEXICAL COMPLET)
KEYWORD_MAP = {
    # Ordre Public & Mouvements Sociaux
    "Evenement voie publique": ["voie publique", "rassemblement", "attroupement", "cortège", "défilé", "espace public"],
    "Manifestation": ["manifestation", "manifestants", "cortège", "mouvement social", "slogan", "pancartes"],
    "Greve": ["grève", "préavis de grève", "débrayage", "grévistes", "mouvement social", "interpro"],
    "Blocage occupation": ["blocage", "barrage", "axe bloqué", "occupé", "opération escargot", "rond-point bloqué"],
    "Projet Amenagement Conteste": ["zad", "zadiste", "projet contesté", "autoroute a69", "bassine", "mégabassine", "lutte territoriale"],
    "Installation illicite": ["installation illicite", "gens du voyage", "campement illégal", "terrain occupé", "caravanes"],
    "Squat": ["squat", "squatteurs", "occupation illégale", "expulsion", "logement squatté"],
    "Free Rave Teknival": ["teknival", "free party", "rave party", "sound system", "raveur", "teuf illégale"],

    # Sécurité & Criminalité
    "Delinquance criminalite": ["délinquance", "vol", "cambriolage", "agression", "faits divers", "refus d'obtempérer", "recel", "homicide"],
    "Criminalite organisee": ["criminalité organisée", "narcotrafic", "trafic de drogue", "règlement de comptes", "point de deal", "mafia", "stupéfiants", "go-fast"],
    "Armes": ["arme à feu", "kalachnikov", "saisie d'armes", "munitions", "coup de feu", "fusillade", "armement", "couteau"],
    "Cybercriminalité": ["cyberattaque", "ransomware", "hacker", "piratage", "vol de données", "phishing", "ransomware", "ddos", "malware"],
    "Drones": ["drone", "drones", "uav", "survol interdit", "aéronef téléguidé", "détection drone", "captation aérienne", "dji"],

    # Idéologies & Radicalités
    "Radicalisation": ["radicalisation", "fiché s", "radicalisé", "islamisme", "embrigadement"],
    "Separatisme": ["séparatisme", "communautarisme", "repli communautaire", "atteinte à la laïcité"],
    "Derives sectaires": ["secte", "dérive sectaire", "miviludes", "emprise mentale", "gourou"],
    "Proselytisme": ["prosélytisme", "prédication", "tractage religieux", "activisme religieux"],
    "Apologie": ["apologie", "apologie du terrorisme", "incitation à la haine", "propos haineux", "provocation"],
    "Terrorisme": ["terrorisme", "terroriste", "attentat", "projet d'attentat", "pnat", "dgsi"],
    "Ultra-droite": ["ultra-droite", "ultradroite", "extrême droite", "identitaire", "neo-nazi", "gropuscule identitaire"],
    "Ultra-gauche": ["ultra-gauche", "ultragauche", "antifa", "antifasciste", "black bloc", "mouvance anarchiste"],
    "Animaliste": ["animaliste", "l214", "intrusion abattoir", "antispéciste", "libération animale"],
    "Ecologie": ["écologie radicale", "les soulevements de la terre", "extinction rebellion", "activiste climat", "action coup de poing"],
    "Survivalisme": ["survivaliste", "survivalisme", "stage de survie", "bunker", "stockage d'armes"],

    # Institutions, Événements & Politique
    "Visite Officielle": ["visite officielle", "déplacement ministériel", "visite présidentielle", "venue du ministre", "visite d'état"],
    "Elections 2027": ["élections 2027", "présidentielle 2027", "candidat 2027", "campagne électorale"],
    "JOPH 2030": ["joph 2030", "jeux olympiques d'hiver", "jo 2030", "alpes 2030", "jo d'hiver"],
    "Enseignement Education nationale": ["éducation nationale", "rectorat", "lycée", "collège", "professeur", "blocus lycée"],
    "Sante": ["urgence hôpital", "ars", "épidémie", "soignants", "chum", "chu", "crise sanitaire"],
    "Culte": ["édifice religieux", "église", "mosquée", "synagogue", "lieu de culte", "pèlerinage"],

    # Secteurs Stratégiques, Économie & Environnement
    "Agriculture": ["agriculteurs", "fnsea", "coordination rurale", "tracteurs", "crise agricole", "agricole", "élevage"],
    "Chasse": ["chasseurs", "chasse", "fédération de chasse", "accident de chasse", "battue"],
    "Transports": ["sncf", "ter", "tramway", "bus", "perturbation trafic", "circulation interrompue"],
    "Ferroviaire": ["train", "ferroviaire", "voie ferrée", "gare", "caténaire", "déraillement"],
    "Nucleaire": ["centrale nucléaire", "edf", "réacteur", "asn", "golfetch", "tricastin", "marcoule"]
}

def detect_theme(text):
    text_lower = text.lower()
    for theme, keywords in KEYWORD_MAP.items():
        if any(kw in text_lower for kw in keywords):
            return theme
    return "Evenement voie publique"

def detect_location(text, feed_region):
    text_lower = text.lower()
    
    # Recherche spécifique de communes dans les régions Sud
    if "geography" in taxonomy:
        for region in taxonomy["geography"]["regions"]:
            for dept in region["departments"]:
                for city in dept.get("cities", []):
                    if city.lower() in text_lower:
                        coords = CITY_COORDS.get(city, [43.5, 5.0])
                        return {
                            "region": region["code"],
                            "department": dept["code"],
                            "city": city,
                            "lat": coords[0],
                            "lng": coords[1]
                        }

    # Géolocalisation par défaut basée sur la région du flux RSS
    default_locations = {
        "OCC": {"region": "OCC", "department": "31", "city": "Toulouse", "lat": 43.6047, "lng": 1.4442},
        "PACA": {"region": "PACA", "department": "13", "city": "Marseille", "lat": 43.2965, "lng": 5.3698},
        "COR": {"region": "COR", "department": "2A", "city": "Ajaccio", "lat": 41.9272, "lng": 8.7346}
    }
    
    return default_locations.get(feed_region, {"region": "PACA", "department": "13", "city": "Marseille", "lat": 43.2965, "lng": 5.3698})

events = []
event_id = 1

for feed in RSS_FEEDS:
    try:
        req = urllib.request.Request(feed["url"], headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            for item in root.findall('.//item')[:20]:
                title = item.find('title').text if item.find('title') is not None else ''
                desc = item.find('description').text if item.find('description') is not None else ''
                link = item.find('link').text if item.find('link') is not None else '#'
                
                full_text = f"{title} {desc}"
                clean_text = re.sub('<[^<]+?>', '', full_text)
                
                theme = detect_theme(clean_text)
                location = detect_location(clean_text, feed.get("region", "NATIONAL"))
                
                events.append({
                    "id": f"evt-{event_id}",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "title": title,
                    "summary": clean_text[:200] + "...",
                    "url": link,
                    "source_name": feed["name"],
                    "theme": theme,
                    "location": location
                })
                event_id += 1
    except Exception as e:
        print(f"Erreur d'extraction sur {feed['name']}: {e}")

with open('data_feed.json', 'w', encoding='utf-8') as f:
    json.dump(events, f, ensure_ascii=False, indent=2)

print(f"Collecte réussie : {len(events)} alertes générées.")
