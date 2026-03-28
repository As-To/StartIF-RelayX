"""
Script simple : Récupération des URLs SCCS depuis CosIng

Usage : python quick_sccs.py
Résultats sauvegardés dans : sccs_results.csv

Modifiez la liste 'substances' ci-dessous pour vos propres ingrédients.
"""

from cosing_scraper import CosIngScraper
import pandas as pd
import time

# ============================================================================
# CONFIGURATION - MODIFIEZ ICI
# ============================================================================

# Liste des substances à vérifier
SUBSTANCES = [
    # "retinol",
    # "titanium dioxide", 
    # "zinc oxide",
    # "glycerin",
    # "tocopherol", 
    "Basic Brown 16"
]

# Fichier de sortie (JSON par défaut)
OUTPUT_FILE = "cosing_results.json"

# ============================================================================
# SCRIPT - NE PAS MODIFIER
# ============================================================================

if __name__ == "__main__":
    
    print("=" * 80)
    print("RÉCUPÉRATION DES AVIS SCCS DEPUIS COSING")
    print("=" * 80)
    print(f"\n📋 {len(SUBSTANCES)} substance(s) à traiter")
    print(f"💾 Sortie : {OUTPUT_FILE}\n")
    
    # Créer une seule instance du scraper pour toutes les substances
    scraper = CosIngScraper(headless=True)
    results = []
    
    try:
        for i, substance in enumerate(SUBSTANCES, 1):
            print(f"🔍 [{i}/{len(SUBSTANCES)}] {substance:25s} → ", end="", flush=True)
            
            try:
                # Récupérer toutes les infos
                info = scraper.get_ingredient_info(substance)
                
                if 'error' in info:
                    print(f"❌ {info['error']}")
                    results.append({
                        'Substance_Recherchee': substance,
                        'INCI_Name': '',
                        'CAS': '',
                        'Function': '',
                        'Restriction': '',
                        'SCCS_Opinion': '',
                        'Has_SCCS_URL': False,
                        'Source_URL': '',
                        'Statut': 'NON_TROUVE'
                    })
                else:
                    sccs = info.get('SCCS_Opinion', '')
                    has_sccs_url = bool(sccs and sccs.startswith('http'))
                    
                    results.append({
                        'Substance_Recherchee': substance,
                        'INCI_Name': info.get('INCI_Name', ''),
                        'CAS': info.get('CAS', ''),
                        'Function': info.get('Function', ''),
                        'Restriction': info.get('Restriction', ''),
                        'SCCS_Opinion': sccs,
                        'Has_SCCS_URL': has_sccs_url,
                        'Source_URL': info.get('Source_URL', ''),
                        'Statut': 'TROUVE'
                    })
                    
                    if has_sccs_url:
                        print(f"✅ {sccs}")
                    elif sccs:
                        print(f"⚠️  SCCS existe: {sccs}")
                    else:
                        print(f"⚪ Pas d'opinion SCCS")
                
            except Exception as e:
                print(f"❌ Erreur: {str(e)[:50]}")
                results.append({
                    'Substance_Recherchee': substance,
                    'INCI_Name': '',
                    'CAS': '',
                    'Function': '',
                    'Restriction': '',
                    'SCCS_Opinion': '',
                    'Has_SCCS_URL': False,
                    'Source_URL': '',
                    'Statut': f'ERREUR: {str(e)[:100]}'
                })
            
            # Pause entre requêtes (sauf pour la dernière)
            if i < len(SUBSTANCES):
                time.sleep(2)
        
    finally:
        scraper.close()
    
    # Sauvegarder les résultats dans un JSON
    import json
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # Résumé
    print()
    print("=" * 80)
    print("RÉSUMÉ")
    print("=" * 80)
    print(f"✅ Total traité : {len(results)}")
    print(f"🔗 Avec URL SCCS : {sum(1 for r in results if r.get('Has_SCCS_URL'))}")
    print(f"⚪ Sans SCCS : {sum(1 for r in results if not r.get('SCCS_Opinion'))}")
    print(f"💾 Fichier créé : {OUTPUT_FILE}")
    print("=" * 80)
    print()
    print("💡 Ouvrez le fichier JSON avec un éditeur ou Excel pour voir tous les détails")
    print("💡 Les URLs SCCS sont cliquables dans certains outils (ex: Excel, navigateur)")
    print("=" * 80)
