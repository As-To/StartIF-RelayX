"""
Agrégation des résultats de scrapping pour chaque ingrédient SCCS
Usage : python aggregate_scraping.py sccs_file.json
"""
import sys
import json
import os
import pandas as pd
from pathlib import Path


# Recherche le dossier Scraping à la racine du projet (remonte jusqu'à le trouver)
def find_scraping_dir():
    cur = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = cur / 'Scraping'
        if candidate.exists() and candidate.is_dir():
            return candidate
        cur = cur.parent
    raise RuntimeError('Dossier Scraping introuvable')

SCRAPING_DIR = find_scraping_dir()
sys.path.append(str(SCRAPING_DIR / '7_cosing'))
sys.path.append(str(SCRAPING_DIR / '2_api_pubchem'))
sys.path.append(str(SCRAPING_DIR))

from cosing_scraper import CosIngScraper
from pubchem_alternative import PubChemAPI
from pubmed import scrape_ingredient_pubmed

# --- Utilitaires chargement SCCS ---
def load_sccs_ingredients(sccs_path):
    """Charge la liste des ingrédients à partir d'un fichier SCCS (JSON ou CSV)"""
    ext = os.path.splitext(sccs_path)[1].lower()
    if ext == '.json':
        with open(sccs_path, encoding='utf-8') as f:
            data = json.load(f)
        # Essaye de trouver la clé contenant les ingrédients
        if isinstance(data, list):
            return [d.get('Ingredient') or d.get('Substance') or d.get('INCI_Name') for d in data if d.get('Ingredient') or d.get('Substance') or d.get('INCI_Name')]
        elif isinstance(data, dict):
            # Peut-être un format {"annex_II": [...], ...}
            for key in ['annex_II', 'annex_III', 'ingredients']:
                if key in data:
                    return [d.get('Ingredient') or d.get('Substance') or d.get('INCI_Name') for d in data[key] if d.get('Ingredient') or d.get('Substance') or d.get('INCI_Name')]
    elif ext == '.csv':
        df = pd.read_csv(sccs_path)
        for col in ['Ingredient', 'Substance', 'INCI_Name']:
            if col in df.columns:
                return df[col].dropna().unique().tolist()
    raise ValueError('Format SCCS non supporté ou colonne ingrédient introuvable')


def main():
    if len(sys.argv) < 2:
        print('Usage: python aggregate_scraping.py sccs_file.json')
        sys.exit(1)
    sccs_path = sys.argv[1]
    ingredients = load_sccs_ingredients(sccs_path)
    print(f"{len(ingredients)} ingrédients à traiter")
    print(ingredients)  # <-- Ajoute cette ligne pour debug

    # Instanciation des scrapers
    cosing = CosIngScraper(headless=True)
    pubchem = PubChemAPI()


    cosing_results = {}
    pubchem_results = {}
    pubmed_results = {}
    # Ajoute d'autres sources ici si besoin


    # Pour chaque ingrédient, on va aussi essayer de récupérer le CAS/EC si dispo
    # On recharge le fichier SCCS pour avoir les infos complètes (pas juste la liste)
    ext = os.path.splitext(sccs_path)[1].lower()
    if ext == '.json':
        with open(sccs_path, encoding='utf-8') as f:
            sccs_data = json.load(f)
        if isinstance(sccs_data, dict):
            # Cherche la première clé qui contient une liste d'objets
            for key in ['annex_II', 'annex_III', 'ingredients']:
                if key in sccs_data:
                    sccs_data = sccs_data[key]
                    break
        # sinon c'est déjà une liste
    elif ext == '.csv':
        sccs_data = pd.read_csv(sccs_path).to_dict(orient='records')
    else:
        raise ValueError('Format SCCS non supporté')

    # Créons un mapping ingrédient -> infos SCCS (pour retrouver le CAS/EC)
    ingr_info_map = {}
    for entry in sccs_data:
        key = entry.get('Ingredient') or entry.get('Substance') or entry.get('INCI_Name')
        if key:
            ingr_info_map[key] = entry


    for i, ingr in enumerate(ingredients, 1):
        print(f"[{i}/{len(ingredients)}] {ingr}")
        entry = ingr_info_map.get(ingr, {})
        cas_ec = entry.get('CAS_EC') or entry.get('CAS') or entry.get('EC')
        cas = None
        ec = None
        if cas_ec:
            import re
            # Recherche tous les CAS (xxx-xx-x) et EC (xxx-xxx-x) dans la chaîne
            cas_matches = re.findall(r'\b\d{2,7}-\d{2}-\d\b', str(cas_ec))
            ec_matches = re.findall(r'\b\d{3}-\d{3}-\d\b', str(cas_ec))
            if cas_matches:
                cas = cas_matches[0]
            if ec_matches:
                ec = ec_matches[0]
        # CosIng : on privilégie la recherche par CAS exact si dispo
        try:
            if cas:
                info_cosing = cosing.get_ingredient_info(cas, cas=cas, ec=ec)
            elif ec:
                info_cosing = cosing.get_ingredient_info(ec, cas=cas, ec=ec)
            else:
                info_cosing = cosing.get_ingredient_info(ingr, cas=cas, ec=ec)
        except Exception as e:
            info_cosing = {'error': str(e)}
        # On ne garde le résultat que si le CAS ou EC correspond exactement à la requête SCCS (on ignore le nom)
        match = False
        cosing_name_used = info_cosing.get('cosing_search_value') if isinstance(info_cosing, dict) else None
        cosing_search_type = info_cosing.get('cosing_search_type') if isinstance(info_cosing, dict) else None
        cosing_name_similarity = info_cosing.get('cosing_name_similarity') if isinstance(info_cosing, dict) else None
        if cas and isinstance(info_cosing, dict):
            if info_cosing.get('CAS') and cas.replace(' ', '') == info_cosing.get('CAS').replace(' ', ''):
                match = True
        if not match and ec and isinstance(info_cosing, dict):
            if info_cosing.get('EC') and ec.replace(' ', '') == info_cosing.get('EC').replace(' ', ''):
                match = True
        # Ajoute les valeurs recherchées dans le résultat CosIng
        recherche_info = {
            'ingredient_query': ingr,
            'cas_query': cas,
            'ec_query': ec,
            'cosing_name_used': cosing_name_used,
            'cosing_search_type': cosing_search_type,
            'cosing_name_similarity': cosing_name_similarity
        }
        if match:
            # Ajoute les infos de recherche dans le résultat trouvé
            cosing_results[ingr] = {**info_cosing, **recherche_info, 'cosing_raw_result': info_cosing}
        elif cosing_search_type == 'fuzzy_name' and cosing_name_used:
            # Si on a trouvé un nom ressemblant, on l'indique dans le résultat
            cosing_results[ingr] = {**info_cosing, **recherche_info, 'warning': f'Ingrédient trouvé par similarité de nom (nom CosIng: {cosing_name_used})', 'cosing_raw_result': info_cosing}
        else:
            cosing_results[ingr] = {**recherche_info, 'error': f'Ingrédient "{ingr}" non trouvé dans CosIng (CAS/EC/nom)', 'cosing_raw_result': info_cosing}

        # PubChem : tente par CAS, puis nom
        info_pubchem = None
        if cas:
            try:
                info_pubchem = pubchem.get_full_info(cas, include_extra=False)
            except Exception as e:
                info_pubchem = None
        if not info_pubchem or (isinstance(info_pubchem, dict) and info_pubchem.get('error')):
            try:
                info_pubchem = pubchem.get_full_info(ingr, include_extra=False)
            except Exception as e:
                info_pubchem = {'error': str(e)}
        pubchem_results[ingr] = info_pubchem

        # PubMed (pas d'API directe par CAS, mais on peut passer le CAS en 2e paramètre)
        try:
            articles = scrape_ingredient_pubmed(ingr, cas, max_results=10)
        except Exception as e:
            articles = [{'error': str(e)}]
        pubmed_results[ingr] = articles


        # --- EURLEX ANNEX II/III LOOKUP ---
        # Load eurlex_32009R1223.json
        eurlex_path = SCRAPING_DIR / 'eurlex_32009R1223.json'
        with open(eurlex_path, encoding='utf-8') as f:
            eurlex_data = json.load(f)
        annex_ii = eurlex_data.get('annex_II', [])
        annex_iii = eurlex_data.get('annex_III', [])

        def match_eurlex(entry, cas, ec, name):
            # Accepts multiple CAS/EC separated by / or [ ]
            def split_ids(val):
                if not val:
                    return []
                return [v.strip().replace('[1]','').replace('[2]','') for v in str(val).replace(';', '/').split('/') if v.strip()]
            cas_list = split_ids(entry.get('cas', ''))
            ec_list = split_ids(entry.get('ec', ''))
            # Try CAS/EC match
            if cas and any(cas.replace(' ','') == c.replace(' ','') for c in cas_list):
                return True
            if ec and any(ec.replace(' ','') == e.replace(' ','') for e in ec_list):
                return True
            # Try name match (case-insensitive, ignore accents)
            import unicodedata
            def norm(s):
                return ''.join(c for c in unicodedata.normalize('NFD', str(s or '').lower()) if unicodedata.category(c) != 'Mn')
            if name and norm(name) == norm(entry.get('substance')):
                return True
            # Try INCI name for annex III
            if name and 'inci_name' in entry and norm(name) == norm(entry.get('inci_name')):
                return True
            return False

        eurlex_results = {}
        for ingr in ingredients:
            entry = ingr_info_map.get(ingr, {})
            cas_ec = entry.get('CAS_EC') or entry.get('CAS') or entry.get('EC')
            cas = None
            ec = None
            if cas_ec:
                import re
                cas_matches = re.findall(r'\b\d{2,7}-\d{2}-\d\b', str(cas_ec))
                ec_matches = re.findall(r'\b\d{3}-\d{3}-\d\b', str(cas_ec))
                if cas_matches:
                    cas = cas_matches[0]
                if ec_matches:
                    ec = ec_matches[0]
            # Search in annex II
            found_ii = [a for a in annex_ii if match_eurlex(a, cas, ec, ingr)]
            # Search in annex III
            found_iii = [a for a in annex_iii if match_eurlex(a, cas, ec, ingr)]
            result = {}
            if found_ii:
                result['annex_II'] = found_ii
            if found_iii:
                result['annex_III'] = found_iii
            if not found_ii and not found_iii:
                result['annex_status'] = 'not_listed'
            eurlex_results[ingr] = result



    # Dossier du script (où seront enregistrés les résultats)
    script_dir = Path(__file__).parent.resolve()

    # Sauvegarde par source
    with open(script_dir / 'cosing_results.json', 'w', encoding='utf-8') as f:
        json.dump(cosing_results, f, ensure_ascii=False, indent=2)
    with open(script_dir / 'pubchem_results.json', 'w', encoding='utf-8') as f:
        json.dump(pubchem_results, f, ensure_ascii=False, indent=2)
    with open(script_dir / 'pubmed_results.json', 'w', encoding='utf-8') as f:
        json.dump(pubmed_results, f, ensure_ascii=False, indent=2)

    # Sauvegarde globale (agrégée)

    results = {
        'cosing': cosing_results,
        'pubchem': pubchem_results,
        'pubmed': pubmed_results,
        'eurlex': eurlex_results,
    }
    out_path = script_dir / f"aggregate_{Path(sccs_path).stem}.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"✅ Résultats sauvegardés dans {out_path}")
    print(f"✅ cosing_results.json, pubchem_results.json, pubmed_results.json créés dans {script_dir}")

    cosing.close()

if __name__ == '__main__':
    main()
