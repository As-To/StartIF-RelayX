"""
Scraper pour le site ECHA (European Chemicals Agency)
Récupère les informations des substances depuis les pages web ECHA

⚠️ ATTENTION : ECHA bloque souvent les accès automatisés
Alternative recommandée : Utiliser PubChem API (pubchem_api.py)
"""

import requests
from bs4 import BeautifulSoup
import time
import re
from typing import Dict, Optional, List
import pandas as pd


class ECHAScraper:
    """
    Scraper pour récupérer les informations de substances depuis ECHA.
    """
    
    def __init__(self):
        self.base_url = "https://echa.europa.eu"
        self.search_url = "https://echa.europa.eu/fr/search-for-chemicals"
        
        # Headers pour simuler un navigateur
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        # Session pour maintenir les cookies
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def search_substance(self, query: str) -> List[Dict]:
        """
        Recherche une substance sur ECHA et retourne les résultats.
        
        Args:
            query: Nom de la substance, CAS ou EC
            
        Returns:
            Liste de dictionnaires avec les URLs et noms trouvés
        """
        print(f"🔍 Recherche de '{query}' sur ECHA...")
        
        try:
            # URL de recherche ECHA CHEM
            search_url = f"https://echa.europa.eu/fr/search-for-chemicals?p_p_id=disssubslist_WAR_disssimplesearchportlet&p_p_lifecycle=1&p_p_state=normal&_disssubslist_WAR_disssimplesearchportlet_javax.portlet.action=search&_disssubslist_WAR_disssimplesearchportlet_searchOccured=true&_disssubslist_WAR_disssimplesearchportlet_compSubmit=searchbutton&_disssubslist_WAR_disssimplesearchportlet_ec=&_disssubslist_WAR_disssimplesearchportlet_cas=&_disssubslist_WAR_disssimplesearchportlet_name={query}"
            
            response = self.session.get(search_url, timeout=15)
            
            if response.status_code == 403:
                print("❌ Erreur 403 : ECHA bloque les accès automatisés")
                print("💡 Alternative : Utilisez PubChem API (voir pubchem_api.py)")
                return []
            
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Analyser les résultats de recherche
            results = []
            
            # Rechercher les liens vers les substances
            # ECHA utilise différentes structures, on cherche les patterns communs
            links = soup.find_all('a', href=re.compile(r'/substance-information/-/substanceinfo/'))
            
            for link in links[:10]:  # Limiter à 10 résultats
                href = link.get('href')
                text = link.get_text(strip=True)
                
                if href and text:
                    full_url = href if href.startswith('http') else self.base_url + href
                    results.append({
                        'name': text,
                        'url': full_url
                    })
            
            if results:
                print(f"✅ {len(results)} résultat(s) trouvé(s)")
            else:
                print("⚠️  Aucun résultat trouvé")
                print("   La structure du site ECHA a peut-être changé")
            
            return results
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur de connexion : {e}")
            return []
        except Exception as e:
            print(f"❌ Erreur inattendue : {e}")
            return []
    
    def scrape_substance_page(self, url: str) -> Dict:
        """
        Scrape une page de substance ECHA pour extraire les informations.
        
        Args:
            url: URL de la page de substance
            
        Returns:
            Dictionnaire avec les informations extraites
        """
        print(f"📄 Scraping de la page : {url}")
        
        info = {
            'url': url,
            'name': '',
            'cas': '',
            'ec': '',
            'molecular_formula': '',
            'molecular_weight': '',
            'classification': [],
            'uses': [],
            'tonnage': '',
            'raw_text': ''
        }
        
        try:
            time.sleep(2)  # Pause pour éviter de surcharger le serveur
            
            response = self.session.get(url, timeout=15)
            
            if response.status_code == 403:
                print("❌ Erreur 403 : Accès bloqué par ECHA")
                return info
            
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Sauvegarder le texte brut pour référence
            info['raw_text'] = soup.get_text(separator='\n', strip=True)
            
            # Extraire les informations principales
            
            # 1. Nom de la substance
            title = soup.find('h1')
            if title:
                info['name'] = title.get_text(strip=True)
            
            # 2. Numéro CAS
            cas_pattern = re.compile(r'\b\d{2,7}-\d{2}-\d\b')
            cas_match = cas_pattern.search(info['raw_text'])
            if cas_match:
                info['cas'] = cas_match.group()
            
            # 3. Numéro EC
            ec_pattern = re.compile(r'\b\d{3}-\d{3}-\d\b')
            ec_match = ec_pattern.search(info['raw_text'])
            if ec_match:
                info['ec'] = ec_match.group()
            
            # 4. Formule moléculaire
            formula_section = soup.find(string=re.compile(r'Molecular formula|Formule moléculaire', re.I))
            if formula_section:
                parent = formula_section.find_parent()
                if parent:
                    # Chercher la formule dans les éléments suivants
                    next_elem = parent.find_next()
                    if next_elem:
                        info['molecular_formula'] = next_elem.get_text(strip=True)
            
            # 5. Classification et étiquetage
            classification_keywords = ['Carc.', 'Muta.', 'Repr.', 'Acute Tox.', 'Skin Corr.', 'Eye Dam.']
            for keyword in classification_keywords:
                if keyword in info['raw_text']:
                    # Extraire le contexte autour du mot-clé
                    pattern = re.compile(f'{keyword}[^,\n]*')
                    matches = pattern.findall(info['raw_text'])
                    info['classification'].extend(matches)
            
            # 6. Usages
            uses_section = soup.find(string=re.compile(r'Uses|Usages', re.I))
            if uses_section:
                parent = uses_section.find_parent()
                if parent:
                    uses_list = parent.find_all('li')
                    info['uses'] = [li.get_text(strip=True) for li in uses_list[:5]]
            
            # 7. Tonnage
            tonnage_keywords = ['tonnes', 'tonne', 'T/year', 't/a']
            for keyword in tonnage_keywords:
                pattern = re.compile(rf'[\d,]+-?[\d,]*\s*{keyword}', re.I)
                match = pattern.search(info['raw_text'])
                if match:
                    info['tonnage'] = match.group()
                    break
            
            print(f"✅ Informations extraites pour : {info['name']}")
            return info
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur de connexion : {e}")
            return info
        except Exception as e:
            print(f"❌ Erreur inattendue : {e}")
            return info
    
    def get_substance_info(self, query: str) -> Optional[Dict]:
        """
        Recherche et récupère les informations complètes d'une substance.
        
        Args:
            query: Nom, CAS ou EC de la substance
            
        Returns:
            Dictionnaire avec toutes les informations
        """
        # 1. Rechercher la substance
        results = self.search_substance(query)
        
        if not results:
            print("❌ Aucune substance trouvée")
            return None
        
        # 2. Prendre le premier résultat
        first_result = results[0]
        print(f"\n📋 Substance sélectionnée : {first_result['name']}")
        
        # 3. Scraper la page
        info = self.scrape_substance_page(first_result['url'])
        
        return info
    
    def save_substance_info(self, query: str, output_file: str = None) -> bool:
        """
        Récupère et sauvegarde les informations d'une substance.
        
        Args:
            query: Nom, CAS ou EC
            output_file: Fichier de sortie (optionnel)
            
        Returns:
            True si succès, False sinon
        """
        info = self.get_substance_info(query)
        
        if not info:
            return False
        
        # Créer un nom de fichier si non fourni
        if not output_file:
            safe_name = query.replace(' ', '_').replace('/', '_')
            output_file = f"echa_{safe_name}.txt"
        
        # Formater et sauvegarder
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("INFORMATIONS SUBSTANCE ECHA (Scraping)\n")
            f.write("=" * 70 + "\n\n")
            
            f.write(f"Nom : {info['name']}\n")
            f.write(f"CAS : {info['cas']}\n")
            f.write(f"EC : {info['ec']}\n")
            f.write(f"Formule moléculaire : {info['molecular_formula']}\n")
            f.write(f"Poids moléculaire : {info['molecular_weight']}\n\n")
            
            if info['classification']:
                f.write("Classification :\n")
                for cls in info['classification']:
                    f.write(f"  - {cls}\n")
                f.write("\n")
            
            if info['uses']:
                f.write("Usages :\n")
                for use in info['uses']:
                    f.write(f"  - {use}\n")
                f.write("\n")
            
            if info['tonnage']:
                f.write(f"Tonnage : {info['tonnage']}\n\n")
            
            f.write("URL source : " + info['url'] + "\n")
            f.write("\n" + "=" * 70 + "\n")
        
        print(f"💾 Informations sauvegardées dans : {output_file}")
        return True
    
    def scrape_multiple_substances(self, queries: List[str], output_csv: str = "scraped_substances.csv") -> pd.DataFrame:
        """
        Scrape plusieurs substances et sauvegarde dans un CSV.
        
        Args:
            queries: Liste de noms/CAS/EC
            output_csv: Fichier CSV de sortie
            
        Returns:
            DataFrame avec toutes les substances
        """
        print(f"🔄 Scraping de {len(queries)} substance(s)...")
        print("⏱️  Cela peut prendre du temps (pause entre chaque requête)")
        
        all_substances = []
        
        for i, query in enumerate(queries, 1):
            print(f"\n[{i}/{len(queries)}] Traitement de : {query}")
            
            info = self.get_substance_info(query)
            
            if info:
                all_substances.append({
                    'Name': info['name'],
                    'CAS': info['cas'],
                    'EC': info['ec'],
                    'Molecular formula': info['molecular_formula'],
                    'Classification': '; '.join(info['classification']) if info['classification'] else '',
                    'Uses': '; '.join(info['uses']) if info['uses'] else '',
                    'Tonnage band': info['tonnage'],
                    'URL': info['url']
                })
            else:
                print(f"⚠️  Échec pour : {query}")
            
            # Pause entre les requêtes
            if i < len(queries):
                time.sleep(3)
        
        # Créer le DataFrame
        df = pd.DataFrame(all_substances)
        
        # Sauvegarder
        if not df.empty:
            df.to_csv(output_csv, index=False, encoding='utf-8')
            print(f"\n✅ {len(df)} substance(s) sauvegardée(s) dans : {output_csv}")
        else:
            print("\n❌ Aucune substance n'a pu être scrapée")
        
        return df


# ============================================================================
# UTILISATION
# ============================================================================

if __name__ == "__main__":
    
    print("=" * 70)
    print("SCRAPER ECHA - European Chemicals Agency")
    print("=" * 70)
    print()
    print("⚠️  AVERTISSEMENT :")
    print("ECHA peut bloquer les accès automatisés (erreur 403)")
    print("Alternative : Utilisez PubChem API (pubchem_api.py)")
    print("=" * 70)
    print()
    
    # Créer le scraper
    scraper = ECHAScraper()
    
    # Test avec une substance
    query = "formaldehyde"
    
    print(f"Test de scraping pour : {query}\n")
    
    # Récupérer les informations
    info = scraper.get_substance_info(query)
    
    if info:
        print("\n📊 Informations récupérées :")
        print(f"Nom : {info['name']}")
        print(f"CAS : {info['cas']}")
        print(f"EC : {info['ec']}")
        print(f"Formule : {info['molecular_formula']}")
        
        # Sauvegarder
        scraper.save_substance_info(query)
    else:
        print("\n❌ Échec du scraping")
        print("\n💡 Solutions alternatives :")
        print("1. Utiliser PubChem API : python -c \"from pubchem_api import PubChemClient; c = PubChemClient(); c.get_substance_full_info('formaldehyde')\"")
        print("2. Télécharger les datasets officiels ECHA (voir SOLUTION_FINALE_ECHA.md)")
        print("3. Utiliser le fichier substances_echa.csv fourni")
