"""
CosIng Scraper - Récupération de données depuis la base européenne des ingrédients cosmétiques
CosIng Database: https://ec.europa.eu/growth/tools-databases/cosing/

⚠️  CosIng utilise JavaScript - nécessite Selenium
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from bs4 import BeautifulSoup
import pandas as pd
import time
from typing import Dict, Optional, List

class CosIngScraper:
    """Scraper pour la base de données CosIng de la Commission Européenne."""
    
    def __init__(self, headless: bool = True):
        """Initialise le scraper avec Selenium.
        
        Args:
            headless: Si True, Chrome s'exécute en arrière-plan (sans fenêtre)
        """
        self.headless = headless
        
        if not headless:
            print("🔧 Initialisation du navigateur...")
        
        options = webdriver.ChromeOptions()
        if headless:
            options.add_argument('--headless=new')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        options.add_argument('--log-level=3')  # Réduire les logs
        
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        self.wait = WebDriverWait(self.driver, 15)
        
        self.base_url = "https://ec.europa.eu/growth/tools-databases/cosing"
        
        if not headless:
            print("✅ Navigateur prêt!\n")
    def search_ingredient(self, name: str) -> bool:
        """Recherche un ingrédient dans CosIng.
        
        Returns:
            True si trouvé et page de détails chargée, False sinon
        """
        if not self.headless:
            print(f"🔍 Recherche de '{name}'...")
        
        try:
            # Aller sur la page principale
            self.driver.get(self.base_url)
            time.sleep(3)  # Attendre le chargement complet du JS
            
            # Stratégie 1: Trouver n'importe quel champ input de type text
            search_input = None
            
            # Essayer plusieurs méthodes pour trouver le champ
            strategies = [
                # Par attributs
                (By.CSS_SELECTOR, "input[type='text']"),
                (By.CSS_SELECTOR, "input[type='search']"),
                (By.NAME, "search"),
                (By.ID, "search"),
                (By.CSS_SELECTOR, "input.search"),
                (By.CSS_SELECTOR, "input[placeholder*='Search' i]"),
                (By.CSS_SELECTOR, "input[placeholder*='search' i]"),
                # Par XPath plus tolérant
                (By.XPATH, "//input[@type='text']"),
                (By.XPATH, "//input[@type='search']"),
                (By.XPATH, "//input[contains(@class, 'search')]"),
                (By.XPATH, "//input[contains(@placeholder, 'search')]"),
                (By.XPATH, "//input[contains(@placeholder, 'Search')]"),
            ]
            
            for by, selector in strategies:
                try:
                    elements = self.driver.find_elements(by, selector)
                    if elements:
                        # Prendre le premier visible
                        for elem in elements:
                            if elem.is_displayed():
                                search_input = elem
                                break
                    if search_input:
                        break
                except:
                    continue
            
            if not search_input:
                # Alternative: URL directe avec paramètres
                search_url = f"{self.base_url}/index.cfm?fuseaction=search.simple&search={name}"
                self.driver.get(search_url)
                time.sleep(3)
                
                # Chercher directement les résultats
                return self._find_and_click_first_result(name)
            
            # Entrer le nom
            search_input.clear()
            search_input.send_keys(name)
            time.sleep(1)
            
            # Chercher le bouton de recherche
            submit_found = False
            submit_strategies = [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (By.XPATH, "//button[@type='submit']"),
                (By.XPATH, "//input[@type='submit']"),
                (By.XPATH, "//button[contains(text(), 'Search')]"),
                (By.XPATH, "//button[contains(text(), 'search')]"),
                (By.XPATH, "//input[@value='Search']"),
            ]
            
            for by, selector in submit_strategies:
                try:
                    button = self.driver.find_element(by, selector)
                    if button.is_displayed():
                        button.click()
                        submit_found = True
                        break
                except:
                    continue
            
            if not submit_found:
                # Essayer avec Enter
                from selenium.webdriver.common.keys import Keys
                search_input.send_keys(Keys.RETURN)
            
            time.sleep(3)  # Attendre les résultats
            
            # Chercher les résultats
            return self._find_and_click_first_result(name)
            
        except Exception as e:
            if not self.headless:
                print(f"  ❌ Erreur: {e}")
            return False
    
    def _find_and_click_first_result(self, search_term: str) -> bool:
        """Trouve et clique sur le premier résultat de recherche."""
        
        # Stratégies pour trouver les résultats
        result_strategies = [
            # Liens vers détails
            (By.XPATH, "//a[contains(@href, 'details')]"),
            (By.XPATH, "//a[contains(@href, 'Details')]"),
            (By.XPATH, "//a[contains(@href, 'DETAILS')]"),
            # Liens dans tableaux
            (By.CSS_SELECTOR, "table a"),
            (By.XPATH, "//table//a"),
            # Liens dans résultats
            (By.CSS_SELECTOR, ".result a"),
            (By.CSS_SELECTOR, ".results a"),
            (By.XPATH, "//div[contains(@class, 'result')]//a"),
            # N'importe quel lien
            (By.TAG_NAME, "a"),
        ]
        
        for by, selector in result_strategies:
            try:
                links = self.driver.find_elements(by, selector)
                
                # Filtrer les liens pertinents
                for link in links:
                    try:
                        if not link.is_displayed():
                            continue
                        
                        href = link.get_attribute('href')
                        text = link.text.strip()
                        
                        # Ignorer certains liens
                        if not href or any(x in href.lower() for x in ['javascript:', 'mailto:', '#']):
                            continue
                        
                        # Vérifier si c'est un lien vers une fiche de détail
                        if any(x in href.lower() for x in ['details', 'view', 'ingredient']):
                            if text:  # A du texte
                                link.click()
                                time.sleep(2)
                                return True
                    except:
                        continue
            except:
                continue
        
        return False
    
    def extract_detail_table(self) -> Dict:
        """Extrait les données depuis la page de détails."""
        data = {
            'INCI_Name': '',
            'CAS': '',
            'EC': '',
            'EINECS': '',
            'Chemical_Name': '',
            'INN_Name': '',
            'Pharmacopeia_Name': '',
            'Description': '',
            'Function': '',
            'Restriction': '',
            'Status': '',
            'Update_Date': '',
            'SCCS_Opinion': '',  # Scientific Committee on Consumer Safety
            'Source_URL': self.driver.current_url
        }
        
        try:
            # Attendre que la page se charge
            time.sleep(2)
            
            # Prendre le HTML complet
            page_text = self.driver.page_source
            
            # Stratégie 1: Parser avec BeautifulSoup
            soup = BeautifulSoup(page_text, 'html.parser')
            
            # Chercher dans tous les éléments qui ressemblent à des labels
            all_text = soup.get_text()
            
            # Parser ligne par ligne
            lines = all_text.split('\n')
            
            for i, line in enumerate(lines):
                line = line.strip()
                
                if not line or len(line) < 3:
                    continue
                
                # Chercher les patterns "Label: Valeur" ou "Label Valeur"
                if ':' in line:
                    parts = line.split(':', 1)
                elif '\t' in line:
                    parts = line.split('\t', 1)
                else:
                    # Essayer de trouver la valeur sur la ligne suivante
                    if i + 1 < len(lines):
                        parts = [line, lines[i + 1].strip()]
                    else:
                        continue
                
                if len(parts) != 2:
                    continue
                
                label = parts[0].strip().lower()
                value = parts[1].strip()
                
                if not value or len(value) < 2:
                    continue
                
                # Mapper aux champs (plus tolérant)
                if 'inci' in label and 'name' in label and not data['INCI_Name']:
                    data['INCI_Name'] = value
                elif 'cas' in label and ('number' in label or 'no' in label or label == 'cas'):
                    # Nettoyer le CAS
                    cas_clean = value.split()[0] if ' ' in value else value
                    if '-' in cas_clean:
                        data['CAS'] = cas_clean
                elif 'ec' in label and ('number' in label or 'no' in label or label == 'ec'):
                    ec_clean = value.split()[0] if ' ' in value else value
                    if '/' in ec_clean or '-' in ec_clean:
                        data['EC'] = ec_clean
                elif 'einecs' in label:
                    data['EINECS'] = value
                elif any(x in label for x in ['chem', 'iupac', 'chemical']):
                    if not data['Chemical_Name']:
                        data['Chemical_Name'] = value
                elif 'inn' in label:
                    data['INN_Name'] = value
                elif 'pharm' in label:
                    data['Pharmacopeia_Name'] = value
                elif 'description' in label:
                    if not data['Description']:
                        data['Description'] = value
                elif 'function' in label:
                    if not data['Function']:
                        data['Function'] = value
                elif 'restriction' in label:
                    data['Restriction'] = value
                elif 'status' in label:
                    if not data['Status']:
                        data['Status'] = value
                elif 'update' in label or 'date' in label:
                    if not data['Update_Date']:
                        data['Update_Date'] = value
                elif 'sccs' in label or 'opinion' in label:
                    if not data['SCCS_Opinion']:
                        data['SCCS_Opinion'] = value
            
            # Stratégie 2: Chercher dans les tableaux
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['th', 'td'])
                    if len(cells) >= 2:
                        label = cells[0].get_text(strip=True).lower()
                        value = cells[1].get_text(strip=True)
                        
                        if len(value) < 2:
                            continue
                        
                        # Remplir les champs manquants
                        if 'inci' in label and not data['INCI_Name']:
                            data['INCI_Name'] = value
                        elif 'cas' in label and not data['CAS']:
                            if '-' in value.split()[0]:
                                data['CAS'] = value.split()[0]
                        elif 'ec' in label and not data['EC']:
                            if '/' in value or '-' in value:
                                data['EC'] = value.split()[0]
                        elif 'function' in label and not data['Function']:
                            data['Function'] = value
                        elif ('sccs' in label or 'opinion' in label) and not data['SCCS_Opinion']:
                            # Chercher un lien dans la cellule
                            link = cells[1].find('a')
                            if link and link.get('href'):
                                href = link.get('href')
                                # Compléter l'URL si relative
                                if href.startswith('/'):
                                    href = 'https://ec.europa.eu' + href
                                elif not href.startswith('http'):
                                    href = 'https://ec.europa.eu/growth/tools-databases/cosing/' + href
                                data['SCCS_Opinion'] = href
                            else:
                                # Pas de lien, juste le texte (Yes/No)
                                data['SCCS_Opinion'] = value
            
            # Stratégie 3: Chercher dans les définitions (dl/dt/dd)
            dls = soup.find_all('dl')
            for dl in dls:
                dts = dl.find_all('dt')
                dds = dl.find_all('dd')
                
                for dt, dd in zip(dts, dds):
                    label = dt.get_text(strip=True).lower()
                    value = dd.get_text(strip=True)
                    
                    if 'inci' in label and not data['INCI_Name']:
                        data['INCI_Name'] = value
                    elif 'cas' in label and not data['CAS']:
                        data['CAS'] = value
                    elif 'function' in label and not data['Function']:
                        data['Function'] = value
                    elif ('sccs' in label or 'opinion' in label) and not data['SCCS_Opinion']:
                        # Chercher un lien dans dd
                        link = dd.find('a')
                        if link and link.get('href'):
                            href = link.get('href')
                            if href.startswith('/'):
                                href = 'https://ec.europa.eu' + href
                            elif not href.startswith('http'):
                                href = 'https://ec.europa.eu/growth/tools-databases/cosing/' + href
                            data['SCCS_Opinion'] = href
                        else:
                            data['SCCS_Opinion'] = value
            
            # Stratégie 4: Chercher spécifiquement les liens SCCS dans toute la page
            if not data['SCCS_Opinion']:
                # Chercher tous les liens qui mentionnent SCCS
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    href = link.get('href', '')
                    text = link.get_text(strip=True).lower()
                    
                    # Vérifier si c'est un lien SCCS
                    if 'sccs' in href.lower() or 'sccs' in text or 'opinion' in text:
                        if href.startswith('/'):
                            href = 'https://ec.europa.eu' + href
                        elif not href.startswith('http'):
                            href = 'https://ec.europa.eu/growth/tools-databases/cosing/' + href
                        data['SCCS_Opinion'] = href
                        break
            
            # Vérifier qu'on a au moins un identifiant
            if not data['INCI_Name'] and not data['CAS']:
                # Essayer de trouver le titre de la page
                title = soup.find('h1')
                if not title:
                    title = soup.find('h2')
                if title:
                    data['INCI_Name'] = title.get_text(strip=True)
            
            return data
            
        except Exception as e:
            print(f"  ⚠️  Erreur extraction: {e}")
            return data
    
    def get_ingredient_info(self, name: str) -> Dict:
        """Récupère toutes les infos d'un ingrédient."""
        if not self.headless:
            print(f"\nIngrédient: {name}")
        
        # 1. Rechercher et accéder à la page de détails
        found = self.search_ingredient(name)
        
        if not found:
            if not self.headless:
                print(f"  ❌ Non trouvé")
            return {'error': f'Ingrédient "{name}" non trouvé dans CosIng'}
        
        time.sleep(1)
        
        # 2. Extraire les données
        data = self.extract_detail_table()
        
        if not data.get('INCI_Name') and not data.get('CAS'):
            if not self.headless:
                print(f"  ❌ Extraction échouée")
            return {'error': 'Impossible d\'extraire les données'}
        
        if not self.headless:
            print(f"  ✅ {data.get('INCI_Name', name)}")
            print(f"     INCI: {data.get('INCI_Name', 'N/A')}")
            print(f"     CAS: {data.get('CAS', 'N/A')}")
            if data.get('Function'):
                print(f"     Function: {data.get('Function')[:50]}")
            if data.get('SCCS_Opinion'):
                sccs = data.get('SCCS_Opinion')
                if sccs.startswith('http'):
                    print(f"     SCCS Opinion: ✅ Lien trouvé")
                    print(f"     URL: {sccs}")
                else:
                    print(f"     SCCS Opinion: {sccs}")
        
        return data
    
    def close(self):
        """Ferme le navigateur."""
        if self.driver:
            self.driver.quit()
    
    def batch_search(self, names: List[str], output_file: str = "cosing_results.csv", export_format: str = "csv"):
        """Recherche plusieurs ingrédients et exporte en CSV ou JSON."""
        import json
        results = []
        if not self.headless:
            print(f"\nTraitement de {len(names)} ingrédient(s)...")
        for i, name in enumerate(names, 1):
            if not self.headless:
                print(f"\n[{i}/{len(names)}]")
            info = self.get_ingredient_info(name)
            if 'error' not in info:
                results.append(info)
            elif not self.headless:
                print(f"  ❌ {info['error']}")
            if i < len(names):
                time.sleep(2)
        if export_format == "json":
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            if not self.headless:
                print(f"\n✅ {len(results)} résultat(s) sauvegardé(s) dans {output_file} (JSON)")
            return results
        else:
            import pandas as pd
            df = pd.DataFrame(results)
            if not df.empty:
                df.to_csv(output_file, index=False, encoding='utf-8-sig')
                if not self.headless:
                    print(f"\n✅ {len(df)} résultat(s) sauvegardé(s) dans {output_file}")
            elif not self.headless:
                print("\n❌ Aucun résultat trouvé")
            return df


# ============================================================================
# UTILISATION
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("SCRAPER COSING - BASE EUROPÉENNE DES INGRÉDIENTS COSMÉTIQUES")
    print("=" * 70)
    print("\nSource: https://ec.europa.eu/growth/tools-databases/cosing/")
    print("Utilise Selenium - le navigateur va s'ouvrir\n")
    
    scraper = None
    
    try:
        scraper = CosIngScraper(headless=False)  # headless=False pour voir le navigateur
        
        # Exemple 1 : Un ingrédient
        print("\n" + "=" * 70)
        print("EXEMPLE 1 : Recherche simple")
        print("=" * 70)
        
        test_name = input("\nNom de l'ingrédient [défaut: tocopherol] : ").strip() or "tocopherol"
        info = scraper.get_ingredient_info(test_name)
        
        if 'error' not in info:
            print("\nRÉSULTATS:\n")
            for key, value in info.items():
                if value and key != 'Source_URL':
                    print(f"  {key}: {value}")
            print(f"\n  URL: {info.get('Source_URL')}")
        else:
            print(f"\n{info['error']}")
        
        # Exemple 2 : Plusieurs ingrédients
        print("\n" + "=" * 70)
        print("EXEMPLE 2 : Recherche multiple")
        print("=" * 70)
        ingredients = ["tocopherol", "retinol", "niacinamide","triclocarban", "genistein"]
        choice = input(f"\nRechercher {len(ingredients)} ingrédients ? (o/n) : ")
        if choice.lower() == 'o':
            export_format = input("Format d'export (csv/json) [défaut: csv] : ").strip().lower() or "csv"
            output_file = input(f"Nom du fichier de sortie [défaut: cosing_results.{export_format}] : ").strip() or f"cosing_results.{export_format}"
            results = scraper.batch_search(ingredients, output_file=output_file, export_format=export_format)
            if export_format == "csv" and hasattr(results, 'empty') and not results.empty:
                print("\nAperçu des résultats:")
                cols = ['INCI_Name', 'CAS', 'EC', 'Function']
                available = [c for c in cols if c in results.columns]
                if available:
                    print(results[available].to_string(index=False))
    
    except KeyboardInterrupt:
        print("\n\nInterruption utilisateur")
    except Exception as e:
        print(f"\nErreur: {e}")
    finally:
        if scraper:
            scraper.close()
        
        print("\n" + "=" * 70)
        print("Terminé")
        print("=" * 70)
