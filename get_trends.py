import urllib.request
import xml.etree.ElementTree as ET
import json

def fetch_google_trends():
    # RSS Google Trends France (Trends quotidiennes + Temps réel)
    urls = [
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=FR",
        "https://trends.google.com/trends/hottrends/visualize/internal/data" # Fallback/complément si besoin
    ]
    
    trends = []
    seen_terms = set()
    
    req = urllib.request.Request(
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=FR",
        headers={'User-Agent': 'Mozilla/5.0'}
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            # Récupération de tous les éléments <item>
            items = root.findall('.//item')
            score = 100
            
            for item in items:
                title = item.find('title')
                if title is not None and title.text:
                    term = title.text.strip().lower()
                    if term not in seen_terms:
                        seen_terms.add(term)
                        trends.append({
                            "term": term,
                            "score": max(score, 10),
                            "source": "Google Trends"
                        })
                        score -= 4  # Décrémente le score de 100 à ~20
                        
    except Exception as e:
        print(f"Erreur lors du scraping Google Trends: {e}")

    # Si Google n'a fourni que 10 tendances, on complète jusqu'à 20 avec des termes OSINT / Sud de secours
    fallback_terms = [
        "agriculture", "manifestation", "sûreté publique", "écologie", 
        "délinquance", "immigration", "réseaux sociaux", "transports", 
        "sécurité routière", "énergie", "climat", "santé", 
        "sécheresse", "inondations", "cyberattaque", "radar"
    ]
    
    score = 40
    for term in fallback_terms:
        if len(trends) >= 20:
            break
        if term.lower() not in seen_terms:
            trends.append({
                "term": term,
                "score": score,
                "source": "OSINT Fallback"
            })
            score = max(score - 2, 5)

    # Sauvegarde dans trending.json (exactement 20 éléments)
    with open('trending.json', 'w', encoding='utf-8') as f:
        json.dump(trends[:20], f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    fetch_google_trends()
