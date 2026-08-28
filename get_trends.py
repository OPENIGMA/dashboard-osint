import json
import urllib.request
import xml.etree.ElementTree as ET

def fetch_google_trends():
    """Récupère le Top 20 des recherches Google Trends (France) via le flux RSS officiel."""
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
            
            # Extraction des 20 premiers éléments du flux RSS
            items = root.findall('.//item')[:20]
            
            for index, item in enumerate(items):
                title = item.find('title').text
                # Génération d'un score dégressif (100, 95, 90...)
                score = 100 - (index * 4)
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
    
    if not trends_data:
        print("Aucune donnée récupérée.")
        return
        
    # Écriture dans trending.json
    with open('trending.json', 'w', encoding='utf-8') as f:
        json.dump(trends_data, f, ensure_ascii=False, indent=2)
        
    print(f"✅ trending.json mis à jour avec {len(trends_data)} tendances.")

if __name__ == "__main__":
    main()
