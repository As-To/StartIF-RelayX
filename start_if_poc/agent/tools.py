import json
import os
import glob

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "Preprocessing", "data", "ingredients")


def _find_ingredient_file(ingredient: str) -> dict | None:
    """Recherche un ingrédient par nom, CAS, INCI, ou synonyme PubChem.
    Retourne le JSON du meilleur match, ou None si rien trouvé.
    Ignore silencieusement les fichiers JSON illisibles ou malformés.
    """
    query = ingredient.lower().strip()
    candidates = []  # liste de (data, longueur_nom) pour choisir le match le plus spécifique

    for filepath in glob.glob(os.path.join(DATA_DIR, "*.json")):
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue  # fichier illisible ou malformé, on passe

        ingredient_name = data.get("ingredient", "").lower()
        cas = data.get("cas", "") or ""
        inci = data.get("inci_name", "") or data.get("cosing", {}).get("inci_name", "") or ""

        # Priorité 1 : égalité exacte sur le nom, le CAS ou l'INCI
        if query == ingredient_name or query == cas.lower() or query == inci.lower():
            return data

        # Priorité 2 : le nom du fichier (slug)
        filename_slug = os.path.basename(filepath).replace(".json", "").replace("_", " ")
        if query == filename_slug:
            return data

        # Priorité 3 : substring match — on collecte pour choisir le plus spécifique
        if (query in ingredient_name or query in cas.lower() or query in inci.lower()):
            candidates.append((data, len(ingredient_name)))
            continue

        # Priorité 4 : synonymes PubChem
        synonyms = data.get("pubchem", {}).get("synonyms", []) or []
        for syn in synonyms[:20]:
            if isinstance(syn, str) and query in syn.lower():
                candidates.append((data, len(ingredient_name)))
                break

    if candidates:
        # Retourner le match avec le nom le plus court (= le plus spécifique)
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]

    return None


def search_ingredient(ingredient: str) -> str:
    """
    Recherche toutes les informations disponibles sur un ingredient
    cosmetique : SCCS, EUR-Lex, ECHA, PubMed, PubChem, CosIng.
    Accepte le nom courant, le nom INCI, le numero CAS, ou un synonyme.
    """
    data = _find_ingredient_file(ingredient)
    if data is None:
        return json.dumps(
            {"error": f"Ingredient '{ingredient}' non trouve dans la base. "
             "Essayez avec un synonyme, le nom INCI ou le numero CAS."},
            ensure_ascii=False
        )

    # Limiter les articles PubMed aux 5 plus pertinents pour ne pas
    # exploser la fenetre de contexte de Haiku
    pubmed = data.get("pubmed", {}) or {}
    articles = pubmed.get("articles", []) or []
    if len(articles) > 5:
        articles_sorted = sorted(articles, key=lambda a: a.get("relevance_score", 0), reverse=True)
        pubmed["articles"] = articles_sorted[:5]
        pubmed["note"] = f"{len(articles)} articles au total, seuls les 5 plus pertinents sont affiches"

    return json.dumps(data, ensure_ascii=False, indent=2)


def list_all_ingredients() -> str:
    """
    Liste tous les ingredients disponibles dans la base avec leur
    statut SCCS et EUR-Lex. Utile pour identifier des ingredients
    de la meme famille chimique (ex: benzophenones, parabens).
    Ignore silencieusement les fichiers illisibles ou malformés.
    """
    ingredients = []
    for filepath in sorted(glob.glob(os.path.join(DATA_DIR, "*.json"))):
        try:
            with open(filepath, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue  # fichier illisible ou malformé, on passe

        sccs = data.get("sccs", {}) or {}
        eurlex = data.get("eurlex", {}) or {}
        pubchem = data.get("pubchem", {}) or {}
        avis = sccs.get("avis", []) or []

        ingredients.append({
            "ingredient": data.get("ingredient"),
            "cas": data.get("cas"),
            "categorie": avis[0].get("categorie") if avis else None,
            "dernier_verdict_sccs": sccs.get("dernier_verdict"),
            "in_annex_II": eurlex.get("in_annex_II", False),
            "in_annex_III": eurlex.get("in_annex_III", False),
            "molecular_formula": pubchem.get("molecular_formula"),
        })

    return json.dumps(ingredients, ensure_ascii=False, indent=2)
