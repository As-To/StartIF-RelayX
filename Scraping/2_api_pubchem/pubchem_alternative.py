"""
Alternative PubChem - API qui fonctionne vraiment pour récupérer des données
PubChem est plus accessible qu'ECHA pour l'automatisation
"""

import requests
import time
import pandas as pd
from typing import Dict, Optional

class PubChemAPI:
    """Client simple pour l'API PubChem."""
    
    def __init__(self):
        self.base_url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
        self.view_url = "https://pubchem.ncbi.nlm.nih.gov/rest/pug_view"
    
    def get_cid_by_name(self, name: str) -> Optional[int]:
        """Récupère le CID PubChem par nom."""
        url = f"{self.base_url}/compound/name/{name}/cids/JSON"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data['IdentifierList']['CID'][0]
        except Exception as e:
            print(f"❌ Erreur recherche: {e}")
            return None
    
    def get_properties(self, cid: int) -> Dict:
        """Récupère les propriétés d'un composé."""
        properties = [
            'MolecularFormula',
            'MolecularWeight',
            'IUPACName',
            'CanonicalSMILES',
            'Title',
            'InChI',
            'InChIKey',
            'XLogP',
            'ExactMass',
            'MonoisotopicMass',
            'TPSA',
            'Complexity',
            'Charge',
            'HBondDonorCount',
            'HBondAcceptorCount',
            'RotatableBondCount',
            'HeavyAtomCount',
            'IsotopeAtomCount',
            'AtomStereoCount',
            'BondStereoCount',
            'CovalentUnitCount',
            'Volume3D',
            'XStericQuadrupole3D',
            'YStericQuadrupole3D',
            'ZStericQuadrupole3D',
            'FeatureCount3D',
            'FeatureAcceptorCount3D',
            'FeatureDonorCount3D',
            'FeatureAnionCount3D',
            'FeatureCationCount3D',
            'FeatureRingCount3D',
            'FeatureHydrophobeCount3D',
            'ConformerModelRMSD3D',
            'EffectiveRotorCount3D',
            'ConformerCount3D'
        ]
        
        url = f"{self.base_url}/compound/cid/{cid}/property/{','.join(properties)}/JSON"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data['PropertyTable']['Properties'][0]
        except Exception as e:
            print(f"❌ Erreur propriétés: {e}")
            return {}
    
    def get_synonyms(self, cid: int) -> list:
        """Récupère les synonymes (dont le CAS)."""
        url = f"{self.base_url}/compound/cid/{cid}/synonyms/JSON"
        
        try:
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            return data['InformationList']['Information'][0].get('Synonym', [])[:20]
        except Exception as e:
            print(f"❌ Erreur synonymes: {e}")
            return []
    
    def find_cas(self, synonyms: list) -> Optional[str]:
        """Extrait le numéro CAS de la liste de synonymes."""
        import re
        cas_pattern = r'^\d{2,7}-\d{2}-\d$'
        
        for synonym in synonyms:
            if re.match(cas_pattern, str(synonym)):
                return synonym
        return None
    
    def get_ghs_classification(self, cid: int) -> Dict:
        """Récupère la classification GHS (dangers, pictogrammes)."""
        url = f"{self.view_url}/data/compound/{cid}/JSON"
        
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            ghs_data = {
                'hazard_statements': [],
                'precautionary_statements': [],
                'signal_word': '',
                'pictograms': [],
                'hazard_classes': []
            }
            
            # Parcourir toutes les sections
            if 'Record' in data and 'Section' in data['Record']:
                self._extract_ghs_recursive(data['Record']['Section'], ghs_data)
            
            return ghs_data
        except Exception as e:
            print(f"⚠️  Erreur GHS: {e}")
            return {}
    
    def _extract_ghs_recursive(self, sections: list, ghs_data: dict):
        """Parcours récursif pour extraire les données GHS."""
        for section in sections:
            heading = section.get('TOCHeading', '')
            
            # Chercher dans les informations de cette section
            if 'Information' in section:
                for info in section['Information']:
                    name = info.get('Name', '')
                    value = info.get('StringValue', info.get('Value', {}).get('StringWithMarkup', [{}])[0].get('String', ''))
                    
                    if 'GHS Hazard' in name or 'Hazard Statement' in name:
                        if value and value not in ghs_data['hazard_statements']:
                            ghs_data['hazard_statements'].append(value)
                    elif 'Precautionary' in name:
                        if value and value not in ghs_data['precautionary_statements']:
                            ghs_data['precautionary_statements'].append(value)
                    elif 'Signal' in name and not ghs_data['signal_word']:
                        ghs_data['signal_word'] = value
                    elif 'Pictogram' in name:
                        if value and value not in ghs_data['pictograms']:
                            ghs_data['pictograms'].append(value)
                    elif 'Hazard Class' in name:
                        if value and value not in ghs_data['hazard_classes']:
                            ghs_data['hazard_classes'].append(value)
            
            # Chercher dans les sous-sections
            if 'Section' in section:
                self._extract_ghs_recursive(section['Section'], ghs_data)
    
    def get_use_and_manufacturing(self, cid: int) -> Dict:
        """Récupère les informations d'usage et de fabrication."""
        url = f"{self.view_url}/data/compound/{cid}/JSON"
        
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            use_data = {
                'uses': [],
                'methods_of_manufacturing': []
            }
            
            if 'Record' in data and 'Section' in data['Record']:
                self._extract_use_recursive(data['Record']['Section'], use_data)
            
            return use_data
        except Exception as e:
            print(f"⚠️  Erreur usage: {e}")
            return {}
    
    def _extract_use_recursive(self, sections: list, use_data: dict):
        """Parcours récursif pour extraire usage et fabrication."""
        for section in sections:
            heading = section.get('TOCHeading', '')
            
            if 'Information' in section:
                for info in section['Information']:
                    name = info.get('Name', '')
                    
                    # Plusieurs formats possibles pour la valeur
                    value = info.get('StringValue', '')
                    if not value and 'Value' in info:
                        if 'StringWithMarkup' in info['Value']:
                            markup_list = info['Value']['StringWithMarkup']
                            if markup_list:
                                value = markup_list[0].get('String', '')
                    
                    # Chercher les usages
                    if any(keyword in heading.lower() or keyword in name.lower() 
                           for keyword in ['use', 'application', 'purpose']):
                        if value and len(value) > 10 and value not in use_data['uses']:
                            use_data['uses'].append(value)
                    
                    # Chercher les méthodes de fabrication
                    if any(keyword in heading.lower() or keyword in name.lower() 
                           for keyword in ['manufact', 'production', 'synthesis', 'preparation']):
                        if value and len(value) > 10 and value not in use_data['methods_of_manufacturing']:
                            use_data['methods_of_manufacturing'].append(value)
            
            if 'Section' in section:
                self._extract_use_recursive(section['Section'], use_data)
    
    def get_safety_and_hazards(self, cid: int) -> Dict:
        """Récupère les informations de sécurité et dangers."""
        url = f"{self.view_url}/data/compound/{cid}/JSON"
        
        try:
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            safety_data = {
                'exposure_routes': [],
                'symptoms': [],
                'first_aid': [],
                'fire_hazard': '',
                'stability': ''
            }
            
            if 'Record' in data and 'Section' in data['Record']:
                self._extract_safety_recursive(data['Record']['Section'], safety_data)
            
            return safety_data
        except Exception as e:
            print(f"⚠️  Erreur sécurité: {e}")
            return {}
    
    def _extract_safety_recursive(self, sections: list, safety_data: dict):
        """Parcours récursif pour extraire sécurité."""
        for section in sections:
            heading = section.get('TOCHeading', '').lower()
            
            if 'Information' in section:
                for info in section['Information']:
                    name = info.get('Name', '').lower()
                    
                    # Plusieurs formats possibles
                    value = info.get('StringValue', '')
                    if not value and 'Value' in info:
                        if 'StringWithMarkup' in info['Value']:
                            markup_list = info['Value']['StringWithMarkup']
                            if markup_list:
                                value = markup_list[0].get('String', '')
                    
                    # Routes d'exposition
                    if any(kw in heading or kw in name for kw in ['exposure', 'route', 'inhalation', 'ingestion', 'skin']):
                        if value and len(value) > 10 and value not in safety_data['exposure_routes']:
                            safety_data['exposure_routes'].append(value)
                    
                    # Symptômes
                    if any(kw in heading or kw in name for kw in ['symptom', 'effect', 'toxicity']):
                        if value and len(value) > 10 and value not in safety_data['symptoms']:
                            safety_data['symptoms'].append(value)
                    
                    # Premiers secours
                    if any(kw in heading or kw in name for kw in ['first aid', 'emergency', 'treatment']):
                        if value and len(value) > 10 and value not in safety_data['first_aid']:
                            safety_data['first_aid'].append(value)
                    
                    # Incendie
                    if any(kw in heading or kw in name for kw in ['fire', 'flammab', 'combusti']):
                        if value and len(value) > 10 and not safety_data['fire_hazard']:
                            safety_data['fire_hazard'] = value
                    
                    # Stabilité
                    if any(kw in heading or kw in name for kw in ['stability', 'reactivity', 'incompatib']):
                        if value and len(value) > 10 and not safety_data['stability']:
                            safety_data['stability'] = value
            
            if 'Section' in section:
                self._extract_safety_recursive(section['Section'], safety_data)
    
    def get_full_info(self, name: str, include_extra: bool = True) -> Dict:
        """Récupère toutes les infos d'une substance.
        
        Args:
            name: Nom de la substance
            include_extra: Si True, récupère aussi GHS, usage, sécurité (plus lent)
        """
        print(f"\n🔍 Recherche de '{name}' sur PubChem...")
        
        # 1. Trouver le CID
        cid = self.get_cid_by_name(name)
        if not cid:
            return {'error': 'Substance introuvable'}
        
        print(f"✅ CID trouvé: {cid}")
        time.sleep(0.3)  # Respecter l'API
        
        # 2. Propriétés chimiques
        props = self.get_properties(cid)
        time.sleep(0.3)
        
        # 3. Synonymes (pour CAS et EC)
        synonyms = self.get_synonyms(cid)
        cas = self.find_cas(synonyms)
        ec = self.find_ec(synonyms)
        
        # Résultat de base
        result = {
            'Name': props.get('Title', name),
            'CID': cid,
            'CAS': cas or '',
            'EC': ec or '',
            'Molecular formula': props.get('MolecularFormula', ''),
            'Molecular weight': props.get('MolecularWeight', ''),
            'IUPAC name': props.get('IUPACName', ''),
            'InChI': props.get('InChI', ''),
            'InChIKey': props.get('InChIKey', ''),
            'SMILES': props.get('CanonicalSMILES', ''),
            'XLogP': props.get('XLogP', ''),
            'TPSA': props.get('TPSA', ''),
            'Complexity': props.get('Complexity', ''),
            'H-Bond Donors': props.get('HBondDonorCount', ''),
            'H-Bond Acceptors': props.get('HBondAcceptorCount', ''),
            'Rotatable Bonds': props.get('RotatableBondCount', ''),
            'Heavy Atoms': props.get('HeavyAtomCount', ''),
            'Synonyms': synonyms[:10]  # 10 premiers
        }
        
        # 4. Informations additionnelles (optionnel)
        if include_extra:
            print("  📋 Récupération GHS classification...")
            ghs = self.get_ghs_classification(cid)
            time.sleep(0.5)
            
            print("  📋 Récupération usage/fabrication...")
            usage = self.get_use_and_manufacturing(cid)
            time.sleep(0.5)
            
            print("  📋 Récupération infos sécurité...")
            safety = self.get_safety_and_hazards(cid)
            
            # Ajout au résultat
            result.update({
                'GHS_Hazards': ' | '.join(ghs.get('hazard_statements', [])[:5]),  # Max 5
                'GHS_Precautions': ' | '.join(ghs.get('precautionary_statements', [])[:5]),
                'Signal_Word': ghs.get('signal_word', ''),
                'Pictograms': ' | '.join(ghs.get('pictograms', [])),
                'Hazard_Classes': ' | '.join(ghs.get('hazard_classes', [])),
                'Uses': ' | '.join(usage.get('uses', [])[:3]),  # Max 3
                'Manufacturing': ' | '.join(usage.get('methods_of_manufacturing', [])[:2]),
                'Exposure_Routes': ' | '.join(safety.get('exposure_routes', [])[:3]),
                'Symptoms': ' | '.join(safety.get('symptoms', [])[:3]),
                'First_Aid': ' | '.join(safety.get('first_aid', [])[:2]),
                'Fire_Hazard': safety.get('fire_hazard', ''),
                'Stability': safety.get('stability', '')
            })
        
        print(f"✅ Données récupérées pour {result['Name']}")
        return result
    
    def find_ec(self, synonyms: list) -> Optional[str]:
        """Extrait le numéro EC de la liste de synonymes."""
        import re
        ec_pattern = r'^\d{3}-\d{3}-\d$'
        
        for synonym in synonyms:
            if re.match(ec_pattern, str(synonym)):
                return synonym
        return None
    
    def batch_search(self, names: list, output_csv: str = "pubchem_results.csv", include_extra: bool = True) -> pd.DataFrame:
        """Recherche plusieurs substances.
        
        Args:
            names: Liste de noms de substances
            output_csv: Fichier de sortie CSV
            include_extra: Si True, récupère aussi GHS, usage, sécurité (plus lent)
        """
        results = []
        
        print(f"\n🚀 Recherche de {len(names)} substance(s)")
        print(f"{'📋 Mode complet (avec GHS/Usage/Sécurité)' if include_extra else '⚡ Mode rapide (propriétés de base)'}\n")
        
        for i, name in enumerate(names, 1):
            print(f"\n[{i}/{len(names)}] {name}")
            info = self.get_full_info(name, include_extra=include_extra)
            
            if 'error' not in info:
                results.append(info)
            else:
                print(f"❌ Échec pour '{name}'")
            
            # Pause entre requêtes
            if i < len(names):
                wait_time = 2 if include_extra else 1
                time.sleep(wait_time)
        
        df = pd.DataFrame(results)
        
        if not df.empty:
            df.to_csv(output_csv, index=False, encoding='utf-8-sig')
            print(f"\n✅ {len(df)} substance(s) sauvegardée(s) dans {output_csv}")
            print(f"📊 Colonnes disponibles: {len(df.columns)}")
        
        return df


# ============================================================================
# UTILISATION
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("RÉCUPÉRATION DE DONNÉES PUBCHEM - VERSION COMPLÈTE")
    print("=" * 70)
    print()
    print("💡 PubChem fonctionne vraiment (pas de blocage)")
    print("📊 Récupère maintenant: propriétés, GHS, usages, sécurité, etc.")
    print()
    
    api = PubChemAPI()
    
    # Menu de choix
    print("\n" + "=" * 70)
    print("CHOISISSEZ LE TYPE DE RECHERCHE")
    print("=" * 70)
    print("1. Mode RAPIDE (propriétés chimiques de base - ~2s/substance)")
    print("2. Mode COMPLET (+ GHS + usages + sécurité - ~5s/substance)")
    print()
    
    mode = input("Votre choix (1 ou 2) [défaut: 2] : ").strip() or "2"
    include_extra = (mode == "2")
    
    # Exemple 1 : Une substance
    print("\n" + "=" * 70)
    print("EXEMPLE 1 : Recherche simple")
    print("=" * 70)
    
    test_substance = input("\nNom de la substance [défaut: caffeine] : ").strip() or "caffeine"
    info = api.get_full_info(test_substance, include_extra=include_extra)
    
    if 'error' not in info:
        print("\n📊 Résultats :")
        print(f"\n🔬 IDENTIFIANTS:")
        print(f"  Name: {info.get('Name')}")
        print(f"  CID: {info.get('CID')}")
        print(f"  CAS: {info.get('CAS')}")
        print(f"  EC: {info.get('EC', 'Non trouvé')}")
        
        print(f"\n⚗️  PROPRIÉTÉS CHIMIQUES:")
        print(f"  Formule: {info.get('Molecular formula')}")
        print(f"  Poids moléculaire: {info.get('Molecular weight')}")
        print(f"  IUPAC: {info.get('IUPAC name', '')[:80]}...")
        
        print(f"\n📐 DESCRIPTEURS:")
        print(f"  XLogP: {info.get('XLogP')}")
        print(f"  TPSA: {info.get('TPSA')}")
        print(f"  Complexity: {info.get('Complexity')}")
        print(f"  H-Bond Donors: {info.get('H-Bond Donors')}")
        print(f"  H-Bond Acceptors: {info.get('H-Bond Acceptors')}")
        
        if include_extra:
            print(f"\n⚠️  CLASSIFICATION GHS:")
            print(f"  Signal Word: {info.get('Signal_Word', 'Non disponible')}")
            print(f"  Pictogrammes: {info.get('Pictograms', 'Non disponible')}")
            hazards = info.get('GHS_Hazards', '')
            if hazards:
                print(f"  Dangers: {hazards[:150]}...")
            else:
                print(f"  Dangers: Non disponible")
            
            print(f"\n🏭 USAGE & FABRICATION:")
            uses = info.get('Uses', '')
            if uses:
                print(f"  Usages: {uses[:150]}...")
            else:
                print(f"  Usages: Non disponible")
            
            manuf = info.get('Manufacturing', '')
            if manuf:
                print(f"  Fabrication: {manuf[:100]}...")
            
            print(f"\n🚨 SÉCURITÉ:")
            exposure = info.get('Exposure_Routes', '')
            if exposure:
                print(f"  Routes d'exposition: {exposure[:100]}...")
            
            first_aid = info.get('First_Aid', '')
            if first_aid:
                print(f"  Premiers secours: {first_aid[:100]}...")
    
    # Exemple 2 : Plusieurs substances
    print("\n" + "=" * 70)
    print("EXEMPLE 2 : Recherche multiple")
    print("=" * 70)
    
    substances = ["aspirin", "ibuprofen", "paracetamol"]
    
    choice = input(f"\nRechercher {len(substances)} substances ? (o/n) : ")
    
    if choice.lower() == 'o':
        df = api.batch_search(substances, include_extra=include_extra)
        
        if not df.empty:
            print("\n📊 Aperçu des résultats :")
            cols_to_show = ['Name', 'CAS', 'EC', 'Molecular formula', 'Molecular weight']
            available_cols = [c for c in cols_to_show if c in df.columns]
            print(df[available_cols].to_string(index=False))
            
            if include_extra and 'GHS_Hazards' in df.columns:
                print(f"\n⚠️  Aperçu GHS (première substance):")
                print(f"  {df.iloc[0]['GHS_Hazards'][:100]}...")
    
    print("\n" + "=" * 70)
    print("✅ Terminé")
    print("=" * 70)
