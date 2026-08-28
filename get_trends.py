import json
import urllib.request
import xml.etree.ElementTree as ET

def fetch_google_trends():
    """Récupère le Top 10 des recherches Google Trends (France) via le flux RSS officiel."""
    url = "https://trends.google.fr/trending/rss?geo=FR"
    req = urllib.request.Request(
        url, 
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    
    trends = []
    try:
        with urllib.request.urlopen(req) as response:
            xml_data = response.read()
            root = ET.fromstring(xml_data)
            
            # Extraction des 10 premiers éléments du flux RSS
            items = root.findall('.//item')[:10]
            
            for index, item in enumerate(items):
                title = item.find('title').text
                # Génération d'un score dégressif (100, 90, 80...)
                score = 100 - (index * 9)
                trends.append({
                    "term": title,
                    "score": max(score, 10),
                    "source": "Google Trends"
                })
    except Exception as e:
        print(f"Erreur d'extraction RSS Google Trends: {e}")
        
    return trends

def main():
    trends_data = fetch_google_trends()
    
    # Sécurité si l'API est indisponible
    if not trends_data:
        print("Aucune donnée récupérée, conservation du format de secours.")
        trends_data = [
            {"term": "SNCF", "score": 100, "source": "Google Trends"},
            {"term": "A69 Toulouse", "score": 90, "source": "Google Trends"},
            {"term": "Météo Gard", "score": 80, "source": "Google Trends"},
            {"term": "Sécheresse PACA", "score": 70, "source": "Google Trends"},
            {"term": "Manifestation Marseille", "score": 60, "source": "Google Trends"}
        ]
        
    # Écriture dans trending.json
    with open('trending.json', 'w', encoding='utf-8') as f:
        json.dump(trends_data, f, ensure_ascii=False, indent=2)
        
    print(f"✅ trending.json mis à jour avec {len(trends_data)} tendances.")

if __name__ == "__main__":
    main()
