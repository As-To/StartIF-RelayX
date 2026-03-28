"""
Scraper ECHA avec Selenium - Simule un vrai navigateur
Plus difficile à bloquer que requests simple

Installation requise:
pip install selenium webdriver-manager
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import re
import os
from typing import Dict, Optional, List
import pandas as pd

# Import optionnel de webdriver-manager
try:
    from webdriver_manager.chrome import ChromeDriverManager
    HAS_WEBDRIVER_MANAGER = True
except ImportError:
    HAS_WEBDRIVER_MANAGER = False
    print("⚠️  webdriver-manager non installé. Installation recommandée : pip install webdriver-manager")


class ECHAScraperSelenium:
    """
    Scraper ECHA utilisant Selenium pour simuler un navigateur réel.
    Beaucoup plus difficile à bloquer qu'un simple script requests.
    """
    
    def __init__(self, headless: bool = True):
        """
        Args:
            headless: Si True, le navigateur est invisible. Si False, vous voyez le navigateur.
        """
        self.headless = headless
        self.driver = None
        
    def _init_driver(self):
        """Initialise le navigateur Chrome avec plusieurs méthodes de fallback."""
        if self.driver is not None:
            return
        
        print("🌐 Démarrage du navigateur Chrome...")
        
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument("--headless")
        
        # Options pour éviter la détection
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        
        # Méthode 1 : webdriver-manager (RECOMMANDÉ)
        if HAS_WEBDRIVER_MANAGER:
            try:
                print("   Méthode 1 : webdriver-manager (automatique)...")
                service = Service(ChromeDriverManager().install())
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                # Masquer que c'est un webdriver
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                print("✅ Navigateur démarré avec webdriver-manager")
                return
            except Exception as e:
                print(f"   ⚠️  webdriver-manager a échoué : {e}")
        
        # Méthode 2 : chromedriver.exe dans le dossier du projet
        try:
            print("   Méthode 2 : Recherche de chromedriver.exe dans le projet...")
            project_driver = os.path.join(os.path.dirname(__file__), '..', 'chromedriver.exe')
            if os.path.exists(project_driver):
                service = Service(executable_path=project_driver)
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                print(f"✅ Navigateur démarré avec {project_driver}")
                return
        except Exception as e:
            print(f"   ⚠️  chromedriver.exe local introuvable")
        
        # Méthode 3 : chromedriver dans le PATH système
        try:
            print("   Méthode 3 : Utilisation du PATH système...")
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            print("✅ Navigateur démarré avec chromedriver du PATH")
            return
        except Exception as e:
            print(f"   ❌ chromedriver introuvable dans le PATH")
        
        # Méthode 4 : Chemins Windows communs
        common_paths = [
            r"C:\ChromeDriver\chromedriver.exe",
            r"C:\Program Files\ChromeDriver\chromedriver.exe",
            os.path.expanduser(r"~\chromedriver.exe")
        ]
        
        for path in common_paths:
            if os.path.exists(path):
                try:
                    print(f"   Méthode 4 : Tentative avec {path}...")
                    service = Service(executable_path=path)
                    self.driver = webdriver.Chrome(service=service, options=chrome_options)
                    self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                    print(f"✅ Navigateur démarré avec {path}")
                    return
                except Exception as e:
                    continue
        
        # Échec total
        print("\n" + "="*70)
        print("❌ IMPOSSIBLE DE DÉMARRER CHROME")
        print("="*70)
        print("\nSolutions :")
        print("\n1️⃣  MÉTHODE RECOMMANDÉE (la plus simple) :")
        print("   pip install webdriver-manager")
        print("\n2️⃣  INSTALLER CHROMEDRIVER MANUELLEMENT :")
        print("   - Téléchargez : https://googlechromelabs.github.io/chrome-for-testing/")
        print("   - Placez chromedriver.exe dans le dossier du projet")
        print("   - Ou suivez : docs/INSTALL_CHROMEDRIVER.md")
        print("\n3️⃣  SCRIPT AUTOMATIQUE :")
        print("   PowerShell en admin : .\\install_chromedriver.ps1")
        print("="*70 + "\n")
        
        raise Exception("ChromeDriver non trouvé. Consultez les solutions ci-dessus.")
    
    def close(self):
        """Ferme le navigateur."""
        if self.driver:
            self.driver.quit()
            self.driver = None
            print("🔒 Navigateur fermé")
    
    def search_substance(self, query: str, debug: bool = False) -> List[Dict]:
        """
        Recherche une substance sur ECHA avec Selenium.
        
        Args:
            query: Nom de la substance à chercher
            debug: Si True, affiche des infos détaillées et sauvegarde des captures
        """
        self._init_driver()
        
        print(f"🔍 Recherche de '{query}' sur ECHA...")
        
        try:
            # Aller sur la page de recherche ECHA
            url = f"https://echa.europa.eu/fr/search-for-chemicals?q={query}"
            
            if debug:
                print(f"📍 URL visitée : {url}")
            
            self.driver.get(url)
            
            if debug:
                print(f"📍 URL actuelle : {self.driver.current_url}")
            
            # Attendre que la page charge
            print("⏳ Attente du chargement de la page (5s)...")
            time.sleep(5)
            
            # DEBUG: Sauvegarder screenshot et HTML
            if debug:
                try:
                    screenshot_path = f"debug_screenshot_{query.replace(' ', '_')}.png"
                    self.driver.save_screenshot(screenshot_path)
                    print(f"📸 Capture d'écran sauvegardée : {screenshot_path}")
                    
                    html_path = f"debug_html_{query.replace(' ', '_')}.html"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(self.driver.page_source)
                    print(f"💾 HTML sauvegardé : {html_path}")
                except Exception as e:
                    print(f"⚠️  Impossible de sauvegarder debug: {e}")
            
            # Vérifier le titre de la page
            page_title = self.driver.title
            if debug:
                print(f"📄 Titre de la page : {page_title}")
            
            # Vérifier si on a une erreur 403
            page_source = self.driver.page_source
            if "403" in page_source or "Forbidden" in page_source:
                print("❌ Erreur 403 - ECHA bloque l'accès")
                return []
            
            if "Access Denied" in page_source or "Cloudflare" in page_source:
                print("❌ Page bloquée par Cloudflare ou WAF")
                return []
            
            # Chercher les résultats
            results = []
            
            # Attendre les résultats
            try:
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
                
                if debug:
                    print("🔍 Recherche de liens vers les substances...")
                
                # Chercher les liens vers les substances
                links = self.driver.find_elements(By.XPATH, "//a[contains(@href, '/substance-information/')]")
                
                if debug:
                    print(f"🔗 {len(links)} lien(s) trouvé(s) contenant '/substance-information/'")
                
                # Alternative : chercher tous les liens et afficher ce qu'on trouve
                if len(links) == 0 and debug:
                    all_links = self.driver.find_elements(By.TAG_NAME, "a")
                    print(f"📊 Total de liens sur la page : {len(all_links)}")
                    print("📋 Exemples de liens trouvés :")
                    for i, link in enumerate(all_links[:10]):
                        try:
                            href = link.get_attribute('href')
                            text = link.text.strip()[:50]
                            if href:
                                print(f"   {i+1}. {text} -> {href[:80]}")
                        except:
                            pass
                
                for link in links[:10]:
                    try:
                        href = link.get_attribute('href')
                        text = link.text.strip()
                        
                        if href and text:
                            results.append({
                                'name': text,
                                'url': href
                            })
                            if debug:
                                print(f"   ✅ Trouvé : {text}")
                    except:
                        continue
                
                if results:
                    print(f"✅ {len(results)} résultat(s) trouvé(s)")
                else:
                    print("⚠️  Aucun résultat trouvé")
                    if not debug:
                        print("💡 Relancez avec mode debug pour plus d'infos : scraper.search_substance('formaldehyde', debug=True)")
                
                return results
                
            except Exception as e:
                print(f"⚠️  Délai dépassé ou structure de page différente: {e}")
                return []
            
        except Exception as e:
            print(f"❌ Erreur: {e}")
            import traceback
            if debug:
                traceback.print_exc()
            return []
    
    def scrape_substance_page(self, url: str) -> Dict:
        """
        Scrape une page de substance ECHA.
        """
        self._init_driver()
        
        print(f"📄 Scraping de la page : {url}")
        
        info = {
            'url': url,
            'name': '',
            'cas': '',
            'ec': '',
            'molecular_formula': '',
            'classification': [],
            'uses': [],
            'tonnage': '',
            'raw_text': ''
        }
        
        try:
            self.driver.get(url)
            time.sleep(3)
            
            # Récupérer le texte de la page
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            info['raw_text'] = page_text
            
            # Extraire les informations
            
            # Nom
            try:
                title = self.driver.find_element(By.TAG_NAME, "h1")
                info['name'] = title.text.strip()
            except:
                pass
            
            # CAS
            cas_match = re.search(r'\b\d{2,7}-\d{2}-\d\b', page_text)
            if cas_match:
                info['cas'] = cas_match.group()
            
            # EC
            ec_match = re.search(r'\b\d{3}-\d{3}-\d\b', page_text)
            if ec_match:
                info['ec'] = ec_match.group()
            
            # Formule moléculaire
            formula_match = re.search(r'[A-Z][a-z]?\d*(?:[A-Z][a-z]?\d*)*', page_text)
            if formula_match:
                potential_formula = formula_match.group()
                if len(potential_formula) <= 20:  # Éviter les faux positifs
                    info['molecular_formula'] = potential_formula
            
            print(f"✅ Informations extraites pour : {info['name']}")
            return info
            
        except Exception as e:
            print(f"❌ Erreur: {e}")
            return info
    
    def get_substance_info(self, query: str, debug: bool = False) -> Optional[Dict]:
        """
        Recherche et récupère les informations complètes d'une substance.
        
        Args:
            query: Nom de la substance
            debug: Active le mode debug avec captures et logs détaillés
        """
        results = self.search_substance(query, debug=debug)
        
        if not results:
            return None
        
        first_result = results[0]
        print(f"\n📋 Substance sélectionnée : {first_result['name']}")
        
        info = self.scrape_substance_page(first_result['url'])
        return info
    
    def scrape_multiple_substances(self, queries: List[str], output_csv: str = "echa_selenium_scraped.csv") -> pd.DataFrame:
        """
        Scrape plusieurs substances.
        """
        print(f"🔄 Scraping de {len(queries)} substance(s)...")
        
        all_substances = []
        
        for i, query in enumerate(queries, 1):
            print(f"\n[{i}/{len(queries)}] Traitement de : {query}")
            
            info = self.get_substance_info(query)
            
            if info and info['name']:
                all_substances.append({
                    'Name': info['name'],
                    'CAS': info['cas'],
                    'EC': info['ec'],
                    'Molecular formula': info['molecular_formula'],
                    'URL': info['url']
                })
            
            # Pause entre requêtes
            if i < len(queries):
                time.sleep(5)
        
        df = pd.DataFrame(all_substances)
        
        if not df.empty:
            df.to_csv(output_csv, index=False, encoding='utf-8')
            print(f"\n✅ {len(df)} substance(s) sauvegardée(s) dans : {output_csv}")
        
        return df


if __name__ == "__main__":
    print("=" * 70)
    print("SCRAPER ECHA AVEC SELENIUM")
    print("=" * 70)
    print()
    
    scraper = ECHAScraperSelenium(headless=True)
    
    try:
        # Test
        query = "formaldehyde"
        print(f"Test avec : {query}\n")
        
        # Mode DEBUG activé pour voir ce qui se passe
        info = scraper.get_substance_info(query, debug=True)
        
        if info and info['name']:
            print("\n✅ Succès !")
            print(f"Nom : {info['name']}")
            print(f"CAS : {info['cas']}")
            print(f"EC : {info['ec']}")
        else:
            print("\n❌ Échec")
    
    finally:
        scraper.close()
