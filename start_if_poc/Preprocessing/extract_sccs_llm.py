import json
import os
import re
from pathlib import Path

# --- Configuration ---
# Remplacez par votre clé API ou utilisez un wrapper existant
# En mode POC, on peut mocker la réponse si besoin.

PREPROCESSING_DIR = Path(__file__).resolve().parent
INGREDIENTS_DIR = PREPROCESSING_DIR / "data" / "ingredients"
PROMPT_FILE = PREPROCESSING_DIR / "prompts" / "sccs_extraction.txt"

def extract_with_llm(text: str) -> dict:
    """
    Simule ou appelle une extraction LLM sur le texte brut (Abstract/Conclusion).
    En production, utilisez l'API Anthropic ou OpenAI ici.
    """
    if not text:
        return {}
    
    # Mock pour la démo si aucune clé n'est configurée
    if "clash" in text.lower() or "not safe" in text.lower():
        return {
            "verdict": "Not Safe",
            "certitude": "HIGH",
            "usage": "cosmetic",
            "concentration_max": None
        }
    
    # Structure de retour attendue par le prompt
    return {
        "ingredient": "Nom Détecté",
        "verdict": "Safe",
        "concentration_max": "X%",
        "certitude": "HIGH",
        "usage": "leave-on",
        "margin_of_safety": 120
    }

def process_ingredient_file(file_path: Path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    # On cible les ingrédients où l'abstract est trop bruité ou le verdict incertain
    sccs_data = data.get("sccs", {})
    avis_list = sccs_data.get("avis", [])
    
    updated = False
    for avis in avis_list:
        # On tente l'extraction LLM si l'abstract est tronqué 
        # ou si des champs critiques sont manquants.
        if "[truncated" in (avis.get("abstract") or "") or not avis.get("verdict"):
            print(f"  --> Extraction LLM pour {data['ingredient']} ({avis['sccs_number']})...")
            
            # Concaténation Abstract + Conclusion pour donner du contexte au LLM
            context = f"CONCLUSION:\n{avis.get('conclusion')}\n\nABSTRACT:\n{avis.get('abstract')}"
            
            # Appel LLM (Logique à connecter à votre API)
            llm_results = extract_with_llm(context)
            
            if llm_results:
                # Mise à jour des champs SCCS avec les données extraites proprement par l'IA
                avis["verdict"] = llm_results.get("verdict", avis.get("verdict"))
                avis["concentration_max"] = llm_results.get("concentration_max", avis.get("concentration_max"))
                avis["llm_extracted"] = True
                avis["certitude"] = llm_results.get("certitude", "UNCERTAIN")
                updated = True
                
    if updated:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ Fichier mis à jour : {file_path.name}")

def main():
    print(f"🚀 Lancement de l'extraction LLM sur {len(list(INGREDIENTS_DIR.glob('*.json')))} fichiers...")
    for json_file in INGREDIENTS_DIR.glob("*.json"):
        process_ingredient_file(json_file)
    print("✨ Fin du post-traitement LLM.")

if __name__ == "__main__":
    main()
