"""
Agent de veille réglementaire — version GRATUITE pour tests
LLM    : Ollama + Mistral (local, 0€)
Search : SearXNG instance publique (gratuit, sans clé API)
PubMed : API officielle gratuite
ECHA   : endpoint public gratuit

Pour passer en production (OpenAI + Tavily), cherche les commentaires
marqués "# PROD:" — ce sont les 2 seules lignes à changer.
"""

import time
import requests
from dotenv import load_dotenv

from langchain_ollama import ChatOllama
# PROD: from langchain_openai import ChatOpenAI

from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import tool

load_dotenv()


# ── LLM local via Ollama ───────────────────────────────────────────────────────
llm = ChatOllama(model="mistral", temperature=0.5)
# PROD: llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# ── Fonction utilitaire : recherche web via SearXNG ───────────────────────────
# SearXNG est un méta-moteur open source. On utilise une instance publique.
# Aucune clé API requise.
SEARX_INSTANCES = [
    "https://searx.be",
    "https://search.mdosch.de",
    "https://searxng.site",
]

def searx_search(query: str, max_results: int = 5) -> str:
    """Recherche sur plusieurs instances SearXNG jusqu'à en trouver une qui répond."""
    headers = {"User-Agent": "RegulatoryAgent/1.0 (research purposes)"}
    for instance in SEARX_INSTANCES:
        try:
            r = requests.get(
                f"{instance}/search",
                params={"q": query, "format": "json", "language": "en"},
                headers=headers,
                timeout=8,
            )
            if r.status_code == 200:
                data = r.json()
                results = data.get("results", [])[:max_results]
                if results:
                    formatted = []
                    for res in results:
                        title = res.get("title", "Sans titre")
                        url = res.get("url", "")
                        content = res.get("content", "")[:200]
                        formatted.append(f"- {title}\n  {url}\n  {content}")
                    return "\n\n".join(formatted)
        except Exception:
            continue  # Essaie l'instance suivante
        time.sleep(1)
    return "Aucun résultat trouvé — toutes les instances SearXNG sont indisponibles."


# ── Outil 1 : Recherche web générale ─────────────────────────────────────────
@tool
def web_search(query: str) -> str:
    """
    Moteur de recherche web. Utilise cet outil pour chercher des informations
    réglementaires, des avis scientifiques, des actualités sur des ingrédients
    cosmétiques ou alimentaires sur internet.
    Entrée : une requête de recherche (en anglais de préférence).
    """
    return searx_search(query)


# ── Outil 2 : Recherche avis SCCS ────────────────────────────────────────────
@tool
def search_sccs_opinions(ingredient: str) -> str:
    """
    Recherche des avis scientifiques du SCCS (Scientific Committee on Consumer Safety)
    sur un ingrédient cosmétique. Les avis SCCS précèdent les restrictions
    européennes de 12 à 36 mois — c'est le signal prédictif le plus fiable.
    Utilise cet outil pour tout ingrédient cosmétique.
    Entrée : nom de l'ingrédient en anglais (ex: "salicylic acid").
    """
    time.sleep(1)
    query = f"SCCS opinion {ingredient} site:health.ec.europa.eu"
    result = searx_search(query, max_results=3)
    # Si SearXNG ne trouve rien sur le site officiel, on élargit
    if "indisponibles" in result or not result.strip():
        query = f"SCCS scientific opinion {ingredient} cosmetics safety"
        result = searx_search(query, max_results=3)
    return result


# ── Outil 3 : PubMed (API officielle gratuite) ────────────────────────────────
@tool
def search_pubmed(query: str) -> str:
    """
    Recherche des articles scientifiques sur PubMed (NIH).
    Utilise cet outil pour trouver des études sur la toxicité, la sécurité,
    ou les effets biologiques d'un ingrédient cosmétique ou alimentaire.
    Entrée : une requête en anglais (ex: "salicylic acid cosmetics safety toxicity").
    Retourne les titres et résumés des 5 articles les plus pertinents.
    """
    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
    try:
        # 1. Récupère les IDs
        r_search = requests.get(
            f"{base}esearch.fcgi",
            params={"db": "pubmed", "term": query, "retmax": 5,
                    "retmode": "json", "sort": "relevance"},
            timeout=10,
        )
        ids = r_search.json().get("esearchresult", {}).get("idlist", [])
        if not ids:
            return f"Aucun article PubMed trouvé pour : {query}"

        # 2. Récupère les abstracts
        r_fetch = requests.get(
            f"{base}efetch.fcgi",
            params={"db": "pubmed", "id": ",".join(ids),
                    "rettype": "abstract", "retmode": "text"},
            timeout=10,
        )
        return r_fetch.text[:2000]
    except Exception as e:
        return f"Erreur PubMed : {e}"


# ── Outil 4 : Vérification ECHA SVHC ─────────────────────────────────────────
@tool
def check_echa_svhc(substance_name: str) -> str:
    """
    Vérifie si une substance figure sur la liste SVHC de l'ECHA
    (Substances of Very High Concern — substances extrêmement préoccupantes).
    Présence sur cette liste = signal fort de restriction imminente dans 2 à 5 ans.
    Utilise cet outil pour tout ingrédient chimique ou cosmétique.
    Entrée : nom de la substance en anglais (ex: "salicylic acid").
    """
    try:
        r = requests.get(
            "https://echa.europa.eu/api/search/substance",
            params={"query": substance_name, "language": "en"},
            headers={"User-Agent": "RegulatoryAgent/1.0"},
            timeout=10,
        )
        if r.status_code == 200 and r.json():
            results = []
            for item in r.json()[:3]:
                name = item.get("substanceName", "?")
                cas = item.get("casNumber", "?")
                svhc = item.get("svhc", False)
                results.append(
                    f"- {name} (CAS: {cas}) | SVHC: {'OUI ⚠️' if svhc else 'Non'}"
                )
            return "\n".join(results)
        return (
            f"Aucun résultat ECHA pour '{substance_name}'.\n"
            f"Vérification manuelle : https://echa.europa.eu/fr/candidate-list-table"
        )
    except Exception as e:
        return f"Erreur ECHA : {e}"


# ── Liste des outils ───────────────────────────────────────────────────────────
tools = [web_search]


# ── Prompt ReAct ──────────────────────────────────────────────────────────────
REACT_PROMPT = PromptTemplate.from_template(
    """Tu es un expert en veille réglementaire pour l'industrie cosmétique.

Outils disponibles :
{tools}

RÈGLES ABSOLUES :
- Le champ Action doit contenir UNIQUEMENT le nom de l'outil, sans backticks, sans guillemets, sans espace.
- Exemples valides :   Action: web_search
- Exemples INVALIDES : Action: `web_search`  /  Action: "web_search"
- Action Input ne doit PAS contenir de backticks.
- Les seuls noms d'outils valides sont : {tool_names}

Format OBLIGATOIRE :

Question: la question posée
Thought: ce que je dois faire
Action: web_search
Action Input: salicylic acid ECHA SVHC
Observation: résultat reçu
Thought: ce que je dois faire ensuite
Action: search_pubmed
Action Input: salicylic acid safety cosmetics
Observation: résultat reçu
Thought: j'ai assez d'informations
Final Answer: réponse complète en français avec statut, risques, score Faible/Modéré/Élevé, sources.

Begin!

Question: {input}
Thought:{agent_scratchpad}"""
)

# ── Assemblage ────────────────────────────────────────────────────────────────
agent = create_react_agent(llm, tools, REACT_PROMPT)
agent_executor = AgentExecutor(
    agent=agent,
    tools=tools,
    verbose=True,
    max_iterations=6,
    handle_parsing_errors=True,
)


# ── Interface ligne de commande ────────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("  Agent de veille réglementaire — version gratuite")
    print("  LLM : Ollama/Mistral (local) | Search : SearXNG")
    print("  Tape 'quit' pour quitter")
    print("=" * 60 + "\n")

    while True:
        question = input("Votre question : ").strip()
        if question.lower() in ("quit", "exit", "q"):
            print("Au revoir.")
            break
        if not question:
            continue

        print("\n[L'agent réfléchit — 30 à 60s avec un LLM local...]\n")
        try:
            result = agent_executor.invoke({"input": question})
            print("\n" + "─" * 60)
            print("RÉPONSE :")
            print("─" * 60)
            print(result["output"])
            print("─" * 60 + "\n")
        except Exception as e:
            print(f"\nErreur : {e}")
            print("Conseil : reformule la question plus simplement.\n")


if __name__ == "__main__":
    main()