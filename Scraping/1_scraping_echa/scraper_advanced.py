"""
Scraper ECHA Avancé avec techniques anti-blocage
=================================================

Ce scraper utilise plusieurs techniques pour éviter les blocages :
- Rotation des User-Agents
- Délais aléatoires entre requêtes
- Headers réalistes
- Gestion des cookies
- Retry avec backoff exponentiel
- Option Selenium pour cas difficiles

Utilisation :
    scraper = ECHAScraperAdvanced()
    infos = scraper.get_substance_info("formaldehyde")
"""

import requests
from bs4 import BeautifulSoup
import time
import re
import random
from typing import Dict, Optional, List
import pandas as pd
from urllib.parse import quote


class ECHAScraperAdvanced:
    """
    Scraper ECHA avancé avec techniques anti-blocage.
    """
    
    # Liste de User-Agents pour rotation
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ]
    
    def __init__(self, use_selenium=False):
        """
        Initialise le scraper.
        
        Args:
            use_selenium: Si True, utilise Selenium (plus lent mais contourne mieux les blocages)
        """
        self.base_url = "https://echa.europa.eu"
        self.use_selenium = use_selenium
        self.session = requests.Session()
        self._update_headers()
        
        # Délais entre requêtes (min, max en secondes)
        self.delay_range = (2, 5)
        
        # Pour Selenium
        self.driver = None
        if use_selenium:
            self._init_selenium()
    
    def _update_headers(self):
        """Met à jour les headers avec un User-Agent aléatoire."""
        user_agent = random.choice(self.USER_AGENTS)
        
        self.headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"'
        }
        
        self.session.headers.update(self.headers)
    
    def _init_selenium(self):
        """Initialise Selenium (nécessite: pip install selenium)."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            
            options = Options()
            options.add_argument('--headless')  # Mode invisible
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument(f'user-agent={random.choice(self.USER_AGENTS)}')
            
            # Désactiver la détection de webdriver
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_experimental_option('useAutomationExtension', False)
            options.add_argument('--disable-blink-features=AutomationControlled')
            
            self.driver = webdriver.Chrome(options=options)
            print("✅ Selenium initialisé")
            
        except ImportError:
            print("⚠️  Selenium non installé. Installer avec: pip install selenium")
            print("⚠️  Télécharger ChromeDriver: https://chromedriver.chromium.org/")
            self.use_selenium = False
        except Exception as e:
            print(f"⚠️  Erreur Selenium: {e}")
            self.use_selenium = False
    
    def _wait(self):
        """Attend un délai aléatoire entre min et max."""
        delay = random.uniform(*self.delay_range)
        time.sleep(delay)
    
    def _get_with_retry(self, url: str, max_retries=3) -> Optional[requests.Response]:
        """
        Effectue une requête GET avec retry et backoff exponentiel.
        """
        for attempt in range(max_retries):
            try:
                # Mettre à jour les headers avant chaque requête
                self._update_headers()
                
                response = self.session.get(url, timeout=30)
                
                if response.status_code == 200:
                    return response
                elif response.status_code == 403:
                    print(f"⚠️  Erreur 403 (tentative {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        wait_time = (2 ** attempt) * 3  # Backoff exponentiel
                        print(f"   Attente de {wait_time}s avant retry...")
                        time.sleep(wait_time)
                elif response.status_code == 429:
                    print(f"⚠️  Rate limit (tentative {attempt + 1}/{max_retries})")
                    time.sleep(60)  # Attendre 1 minute
                else:
                    print(f"⚠️  Code HTTP {response.status_code}")
                    
            except requests.exceptions.Timeout:
                print(f"⚠️  Timeout (tentative {attempt + 1}/{max_retries})")
            except Exception as e:
                print(f"⚠️  Erreur: {e}")
            
            if attempt < max_retries - 1:
                self._wait()
        
        return None
    
    def search_substance(self, query: str) -> List[Dict]:
        """
        Recherche une substance sur ECHA.
        
        Args:
            query: Nom, CAS ou EC de la substance
            
        Returns:
            Liste de résultats [{name, cas, ec, url}]
        """
        print(f"\n🔍 Recherche ECHA pour: '{query}'")
        
        if self.use_selenium:
            return self._search_with_selenium(query)
        else:
            return self._search_with_requests(query)
    
    def _search_with_requests(self, query: str) -> List[Dict]:
        """Recherche avec requests (plus rapide)."""
        
        # Encoder la requête pour l'URL
        encoded_query = quote(query)
        
        # URL de recherche ECHA
        search_url = f"https://echa.europa.eu/fr/information-on-chemicals/registered-substances?p_p_id=disssimplesearch_WAR_disssearchportlet&p_p_lifecycle=1&p_p_state=normal&p_p_mode=view&p_p_col_id=column-1&p_p_col_pos=2&p_p_col_count=3&_disssimplesearch_WAR_disssearchportlet_sessionCriteriaId=DISS-true&_disssimplesearch_WAR_disssearchportlet_searchOccured=true&_disssimplesearch_WAR_disssearchportlet_keywords={encoded_query}"
        
        response = self._get_with_retry(search_url)
        
        if not response:
            print("❌ Impossible de contacter ECHA après plusieurs tentatives")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        
        # Chercher les résultats dans la page
        # ECHA utilise des divs avec class "substanceIdentification"
        substance_divs = soup.find_all('div', class_=re.compile(r'substance'))
        
        if not substance_divs:
            # Alternative: chercher tous les liens vers les pages de substances
            links = soup.find_all('a', href=re.compile(r'/substance-information/-/substanceinfo/'))
            
            for link in links[:10]:
                href = link.get('href')
                text = link.get_text(strip=True)
                
                if href and text:
                    full_url = href if href.startswith('http') else self.base_url + href
                    
                    # Extraire CAS et EC si présents dans le texte environnant
                    parent_text = link.parent.get_text() if link.parent else text
                    
                    cas_match = re.search(r'\b(\d{2,7}-\d{2}-\d)\b', parent_text)
                    ec_match = re.search(r'\b(\d{3}-\d{3}-\d)\b', parent_text)
                    
                    results.append({
                        'name': text,
                        'cas': cas_match.group(1) if cas_match else '',
                        'ec': ec_match.group(1) if ec_match else '',
                        'url': full_url
                    })
        
        if results:
            print(f"✅ {len(results)} résultat(s) trouvé(s)")
        else:
            print("⚠️  Aucun résultat - Structure HTML peut avoir changé")
            self._debug_save_html(soup, query)
        
        return results
    
    def _search_with_selenium(self, query: str) -> List[Dict]:
        """Recherche avec Selenium (contourne mieux les blocages)."""
        if not self.driver:
            print("❌ Selenium non disponible")
            return []
        
        try:
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            
            encoded_query = quote(query)
            search_url = f"https://echa.europa.eu/fr/information-on-chemicals/registered-substances?p_p_id=disssimplesearch_WAR_disssearchportlet&_disssimplesearch_WAR_disssearchportlet_keywords={encoded_query}"
            
            self.driver.get(search_url)
            
            # Attendre le chargement
            time.sleep(5)
            
            # Parser le HTML avec BeautifulSoup
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Même logique que _search_with_requests
            results = []
            links = soup.find_all('a', href=re.compile(r'/substance-information/-/substanceinfo/'))
            
            for link in links[:10]:
                href = link.get('href')
                text = link.get_text(strip=True)
                
                if href and text:
                    full_url = href if href.startswith('http') else self.base_url + href
                    parent_text = link.parent.get_text() if link.parent else text
                    
                    cas_match = re.search(r'\b(\d{2,7}-\d{2}-\d)\b', parent_text)
                    ec_match = re.search(r'\b(\d{3}-\d{3}-\d)\b', parent_text)
                    
                    results.append({
                        'name': text,
                        'cas': cas_match.group(1) if cas_match else '',
                        'ec': ec_match.group(1) if ec_match else '',
                        'url': full_url
                    })
            
            print(f"✅ {len(results)} résultat(s) trouvé(s) avec Selenium")
            return results
            
        except Exception as e:
            print(f"❌ Erreur Selenium: {e}")
            return []
    
    def get_substance_info(self, substance_url: str) -> Dict:
        """
        Récupère les informations détaillées d'une substance.
        
        Args:
            substance_url: URL de la page ECHA de la substance
            
        Returns:
            Dictionnaire avec toutes les informations extraites
        """
        print(f"\n📄 Récupération des infos : {substance_url}")
        
        self._wait()  # Délai avant requête
        
        if self.use_selenium:
            return self._scrape_with_selenium(substance_url)
        else:
            return self._scrape_with_requests(substance_url)
    
    def _scrape_with_requests(self, url: str) -> Dict:
        """Scraping avec requests."""
        
        info = {
            'url': url,
            'name': '',
            'cas': '',
            'ec': '',
            'molecular_formula': '',
            'iupac_name': '',
            'classification': [],
            'hazards': [],
            'uses': [],
            'tonnage': ''
        }
        
        response = self._get_with_retry(url)
        
        if not response:
            print("❌ Impossible de récupérer la page")
            return info
        
        soup = BeautifulSoup(response.text, 'html.parser')
        text = soup.get_text()
        
        # 1. Nom
        h1 = soup.find('h1')
        if h1:
            info['name'] = h1.get_text(strip=True)
        
        # 2. CAS
        cas_match = re.search(r'\b(\d{2,7}-\d{2}-\d)\b', text)
        if cas_match:
            info['cas'] = cas_match.group(1)
        
        # 3. EC
        ec_match = re.search(r'\b(\d{3}-\d{3}-\d)\b', text)
        if ec_match:
            info['ec'] = ec_match.group(1)
        
        # 4. Formule moléculaire
        formula_match = re.search(r'(?:Molecular formula|Formule moléculaire)[:\s]*([A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)*)', text, re.I)
        if formula_match:
            info['molecular_formula'] = formula_match.group(1)
        
        # 5. IUPAC
        iupac_match = re.search(r'(?:IUPAC name|Nom IUPAC)[:\s]*([^\n]+)', text, re.I)
        if iupac_match:
            info['iupac_name'] = iupac_match.group(1).strip()
        
        # 6. Classification GHS
        ghs_codes = re.findall(r'\b(H\d{3}[A-Za-z]?)\b', text)
        info['hazards'] = list(set(ghs_codes))  # Dédupliquer
        
        # 7. Tonnage
        tonnage_match = re.search(r'([\d,]+-?[\d,]*\s*(?:tonnes?|T/year|t/a))', text, re.I)
        if tonnage_match:
            info['tonnage'] = tonnage_match.group(1)
        
        print(f"✅ Informations extraites pour '{info['name']}'")
        
        return info
    
    def _scrape_with_selenium(self, url: str) -> Dict:
        """Scraping avec Selenium."""
        if not self.driver:
            return self._scrape_with_requests(url)
        
        try:
            self.driver.get(url)
            time.sleep(5)  # Attendre le chargement complet
            
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            # Utiliser la même logique que _scrape_with_requests
            # mais avec le HTML complet chargé par Selenium
            return self._scrape_with_requests.__wrapped__(self, url)
            
        except Exception as e:
            print(f"❌ Erreur Selenium: {e}")
            return {}
    
    def _debug_save_html(self, soup, query):
        """Sauvegarde le HTML pour déboguer."""
        filename = f"debug_echa_{query.replace(' ', '_')}.html"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(str(soup.prettify()))
        print(f"💾 HTML sauvegardé dans {filename} pour analyse")
    
    def search_and_scrape(self, query: str) -> List[Dict]:
        """
        Recherche et récupère les infos de toutes les substances correspondantes.
        
        Args:
            query: Nom, CAS ou EC
            
        Returns:
            Liste de dictionnaires avec toutes les infos
        """
        # 1. Rechercher
        results = self.search_substance(query)
        
        if not results:
            return []
        
        # 2. Scraper chaque résultat
        detailed_results = []
        
        for i, result in enumerate(results[:3], 1):  # Limiter à 3 pour ne pas surcharger
            print(f"\n--- Résultat {i}/{min(len(results), 3)} ---")
            
            if result.get('url'):
                details = self.get_substance_info(result['url'])
                # Fusionner avec les infos de recherche
                result.update(details)
            
            detailed_results.append(result)
        
        return detailed_results
    
    def get_substance_info_safe(self, query: str) -> Optional[Dict]:
        """
        Méthode sécurisée pour récupérer les infos d'une substance par nom/CAS/EC.
        Alias de search_and_scrape() qui retourne le premier résultat.
        
        Args:
            query: Nom, CAS ou EC de la substance
            
        Returns:
            Dictionnaire avec les infos de la première substance trouvée, ou None
        """
        results = self.search_and_scrape(query)
        
        if results and len(results) > 0:
            return results[0]
        
        return None
    
    def scrape_multiple_substances(self, queries: List[str], output_csv: str = "echa_results.csv") -> pd.DataFrame:
        """
        Scrape plusieurs substances et sauvegarde dans un CSV.
        
        Args:
            queries: Liste de noms/CAS/EC
            output_csv: Fichier CSV de sortie
            
        Returns:
            DataFrame avec tous les résultats
        """
        all_results = []
        
        for i, query in enumerate(queries, 1):
            print(f"\n[{i}/{len(queries)}] Traitement de : {query}")
            results = self.search_and_scrape(query)
            all_results.extend(results)
            
            if i < len(queries):
                self._wait()  # Pause entre substances
        
        df = pd.DataFrame(all_results)
        
        if not df.empty:
            df.to_csv(output_csv, index=False, encoding='utf-8-sig')
            print(f"\n✅ {len(df)} résultat(s) sauvegardé(s) dans {output_csv}")
        else:
            print("\n❌ Aucun résultat trouvé")
        
        return df
    
    def export_to_csv(self, results: List[Dict], filename: str = "echa_results.csv"):
        """Exporte les résultats en CSV."""
        if not results:
            print("❌ Aucun résultat à exporter")
            return
        
        df = pd.DataFrame(results)
        df.to_csv(filename, index=False, encoding='utf-8-sig')
        print(f"✅ Résultats exportés dans {filename}")
    
    def __del__(self):
        """Ferme le driver Selenium."""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass


# ============================================================================
# Fonction utilitaire simple
# ============================================================================

def search_echa(substance_name: str, use_selenium: bool = False) -> List[Dict]:
    """
    Fonction simple pour rechercher sur ECHA.
    
    Args:
        substance_name: Nom de la substance
        use_selenium: Utiliser Selenium (plus lent mais plus fiable)
        
    Returns:
        Liste de résultats
    """
    scraper = ECHAScraperAdvanced(use_selenium=use_selenium)
    return scraper.search_and_scrape(substance_name)


if __name__ == "__main__":
    print("=" * 70)
    print("SCRAPER ECHA AVANCÉ - TEST")
    print("=" * 70)
    
    # Test 1: Recherche simple
    print("\n\n🧪 TEST 1: Recherche avec requests")
    print("-" * 70)
    
    scraper = ECHAScraperAdvanced(use_selenium=False)
    results = scraper.search_and_scrape("formaldehyde")
    
    if results:
        print(f"\n✅ {len(results)} substance(s) trouvée(s)")
        for result in results:
            print(f"\n📌 {result.get('name', 'N/A')}")
            print(f"   CAS: {result.get('cas', 'N/A')}")
            print(f"   EC: {result.get('ec', 'N/A')}")
            print(f"   Formule: {result.get('molecular_formula', 'N/A')}")
            print(f"   Dangers: {', '.join(result.get('hazards', []))}")
        
        # Export CSV
        scraper.export_to_csv(results)
    else:
        print("\n❌ Aucun résultat")
        print("\n💡 Si ECHA bloque toujours :")
        print("   1. Essayez avec Selenium: use_selenium=True")
        print("   2. Utilisez PubChem API (pubchem_api.py)")
        print("   3. Téléchargez le dataset ECHA complet")
    
    print("\n" + "=" * 70)
    print("FIN DU TEST")
    print("=" * 70)
