import anthropic
import json
import os
import re
from datetime import datetime
from dotenv import load_dotenv
from tools import search_ingredient, list_all_ingredients

load_dotenv()

# Cle API depuis variable d'environnement ou en dur pour le POC
API_KEY = os.environ.get("LLM_API_KEY")
MODEL = os.environ.get("LLM_MODEL", "claude-haiku-4-5-20251001")
MAX_ITERATIONS = 10
WRITE_LOGS = os.environ.get("WRITE_LOGS", "true").lower() == "true"

LOGS_DIR = os.path.join(os.path.dirname(__file__), "logs")

client = anthropic.Anthropic(api_key=API_KEY)

TOOLS_SPEC = [
    {
        "name": "search_ingredient",
        "description": (
            "Recherche toutes les informations disponibles sur un ingredient "
            "cosmetique : avis SCCS (verdict, conclusion, abstract), statut "
            "EUR-Lex (Annexe II/III), statut ECHA (SVHC, CLP), articles "
            "PubMed recents, profil chimique PubChem, et donnees CosIng. "
            "Accepte le nom courant, le nom INCI, le numero CAS ou un synonyme."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "ingredient": {
                    "type": "string",
                    "description": "Nom de l'ingredient, nom INCI, ou numero CAS"
                }
            },
            "required": ["ingredient"]
        }
    },
    {
        "name": "list_all_ingredients",
        "description": (
            "Liste tous les ingredients disponibles dans la base avec leur "
            "statut SCCS, EUR-Lex et formule chimique. Utile pour identifier "
            "des ingredients de la meme famille chimique (ex: benzophenones, "
            "parabens) et raisonner par analogie."
        ),
        "input_schema": {
            "type": "object",
            "properties": {}
        }
    }
]

TOOL_FUNCTIONS = {
    "search_ingredient": search_ingredient,
    "list_all_ingredients": list_all_ingredients,
}


def load_system_prompt():
    prompt_path = os.path.join(os.path.dirname(__file__), "system_prompt.txt")
    with open(prompt_path, encoding="utf-8") as f:
        return f.read()


def _ingredient_from_query(query: str) -> str:
    """Extrait le nom de l'ingrédient depuis la requête utilisateur."""
    # La requête est de la forme "... : NOM_INGREDIENT"
    if ":" in query:
        return query.split(":")[-1].strip()
    return query.strip()


def _write_log(ingredient: str, log_lines: list[str], final_result: str):
    """Écrit le raisonnement et le résultat final dans un fichier markdown."""
    os.makedirs(LOGS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r"[^\w\-]", "_", ingredient.lower())[:40]
    filepath = os.path.join(LOGS_DIR, f"{slug}_{timestamp}.md")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(f"# Analyse réglementaire : {ingredient}\n\n")
        f.write(f"**Date** : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  \n")
        f.write(f"**Modèle** : {MODEL}\n\n")
        f.write("---\n\n")
        f.write("## Raisonnement\n\n")
        for line in log_lines:
            f.write(line + "\n")
        '''
        f.write("\n---\n\n")
        f.write("## Résultat final\n\n")
        f.write(final_result + "\n")
        '''

    return filepath


def run_agent(query: str, verbose: bool = True, reference_date: str = None) -> str:
    """
    Lance l'agent de prediction reglementaire sur une requete.
    Retourne le texte final de l'agent.
    """
    today = reference_date or datetime.now().strftime("%Y-%m-%d")
    system = f"DATE_ACTUELLE: {today}\n\n" + load_system_prompt()
    messages = [{"role": "user", "content": query}]
    log_lines = []

    for iteration in range(MAX_ITERATIONS):
        if verbose:
            print(f"\n--- Iteration {iteration + 1} ---")
        log_lines.append(f"### Itération {iteration + 1}\n")

        response = client.messages.create(
            model=MODEL,
            max_tokens=4096,
            system=system,
            tools=TOOLS_SPEC,
            messages=messages
        )

        assistant_content = response.content
        messages.append({"role": "assistant", "content": assistant_content})

        # Extraire les blocs texte et tool_use
        text_blocks = [b.text for b in assistant_content if b.type == "text"]
        tool_uses = [b for b in assistant_content if b.type == "tool_use"]

        # Afficher et logger le raisonnement intermediaire
        for text in text_blocks:
            if text.strip():
                if verbose:
                    print(f"[Raisonnement] {text[:200]}...")
                log_lines.append(f"**Raisonnement :**\n\n{text}\n")

        # Si pas d'appel d'outil, l'agent a termine
        if not tool_uses:
            final_text = "\n".join(text_blocks)
            if WRITE_LOGS:
                ingredient = _ingredient_from_query(query)
                path = _write_log(ingredient, log_lines, final_text)
                if verbose:
                    print(f"\n[Log] Analyse sauvegardée : {path}")
            return final_text

        # Executer chaque outil
        tool_results = []
        for tool_use in tool_uses:
            func = TOOL_FUNCTIONS.get(tool_use.name)

            if verbose:
                print(f"[Outil] {tool_use.name}({json.dumps(tool_use.input)})")
            log_lines.append(f"**Outil appelé :** `{tool_use.name}({json.dumps(tool_use.input, ensure_ascii=False)})`\n")

            if func:
                try:
                    result = func(**tool_use.input)
                except Exception as e:
                    result = json.dumps({"error": f"Erreur execution: {str(e)}"})
            else:
                result = json.dumps({"error": f"Outil inconnu: {tool_use.name}"})

            if verbose:
                result_preview = result[:150] + "..." if len(result) > 150 else result
                print(f"[Resultat] {result_preview}")
            log_lines.append(f"**Résultat (extrait) :** `{result[:300]}{'...' if len(result) > 300 else ''}`\n")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result
            })

        messages.append({"role": "user", "content": tool_results})

    # Si on atteint le max d'iterations
    final_text = "[ERREUR] L'agent a atteint le nombre maximum d'iterations sans conclure."
    if WRITE_LOGS:
        ingredient = _ingredient_from_query(query)
        _write_log(ingredient, log_lines, final_text)
    return final_text
