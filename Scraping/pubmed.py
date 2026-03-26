"""
PubMed Scraper

flux complet:

"salicylic acid"
      ↓
build_query()     → '"salicylic acid"[TIAB] AND (cosmetic[TIAB] OR ...)'
      ↓
esearch (JSON)    → ["38291847", "37845123", "36901234", ...]  (PMIDs)
      ↓
efetch (XML)      → contenu XML des 25 articles
      ↓
parse_xml()       → liste de dicts {title, abstract, doi, mesh, ...}
      ↓
relevance_score() → tri par pertinence sécurité
      ↓
JSON sauvegardé   → pubmed_salicylic_acid.json
"""

import re, sys, json, time, argparse, logging
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

BASE_URL    = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
DELAY_NOKEY = 0.4 # sans clé API, on est limité à 3 requêtes/s → délai de 0.4s entre chaque requête
DELAY_KEY   = 0.12 # avec clé API, on peut faire jusqu'à 10 requêtes/s 
# éviter les erreurs 429 Too Many Requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()

def get(url, params, delay, as_xml=False):
    time.sleep(delay)
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        if as_xml:
            return r.text          # retourne le texte brut XML
        return r.json()
    except Exception as e:
        log.error(f"Erreur {url} : {e}")
        return None

# ──────────────────────────────────────────────────────────────
# Étape 1 : esearch → PMIDs  (JSON, ça marche)
# ──────────────────────────────────────────────────────────────

def build_query(ingredient: str, cas: str | None = None) -> str:
    cosmet = ('(cosmetic[TIAB] OR skincare[TIAB] OR "skin care"[TIAB] OR '
              'dermatol*[TIAB] OR topical[TIAB] OR "personal care"[TIAB] OR '
              'formulation[TIAB] OR ingredient[TIAB])') # [TIAB] = recherche dans Title/Abstract et non dans tout l'article. * = wildcard pour prendre "dermatology", "dermatological", etc.
    base = f'"{ingredient}"[TIAB] AND {cosmet}' # on cherche l'ingrédient dans le titre ou résumé, et on veut que l'article parle de cosmétique (pour éviter les études sur les pesticides, solvants, etc. qui pourraient aussi être toxiques mais ne sont pas utilisés en cosmétique)
    if cas:
        cas_clean = cas.split("/")[0].strip()
        base = f'({base}) OR ("{cas_clean}"[TIAB] AND {cosmet})'
    return base

def search_pmids(query, max_results, api_key, delay) -> list[str]:
    # recuperer les ids des articles pertinents (les PMIDs) via esearch (moteur de recherche de PubMed)
    params = {
        "db": "pubmed", "term": query,
        "retmax": max_results, "retmode": "json",
        "sort": "relevance",
    }
    if api_key:
        params["api_key"] = api_key
    data = get(f"{BASE_URL}/esearch.fcgi", params, delay)
    if not data:
        return []
    pmids = data.get("esearchresult", {}).get("idlist", [])
    total = data.get("esearchresult", {}).get("count", "?")
    log.info(f"     {total} résultats | {len(pmids)} PMIDs récupérés")
    return pmids

# ──────────────────────────────────────────────────────────────
# Étape 2 : efetch → XML → parse
# ──────────────────────────────────────────────────────────────

def fetch_details(pmids, api_key, delay) -> list[dict]:
    # apres recuperation des PMIDs, on utilise efetch pour recuperer les details de chaque article (titre, résumé, auteurs, etc.)
    if not pmids:
        return []
    articles = []
    batch_size = 20 # pour ne pas surcharger l'API

    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i+batch_size]
        params = {
            "db":      "pubmed",
            "id":      ",".join(batch),
            "retmode": "xml",       # XML obligatoire pour efetch. PubMed ne propose pas de JSON
            "rettype": "abstract",
        }
        if api_key:
            params["api_key"] = api_key

        xml_text = get(f"{BASE_URL}/efetch.fcgi", params, delay, as_xml=True)
        if not xml_text:
            continue

        parsed = parse_xml(xml_text)
        articles.extend(parsed)
        log.info(f"     Batch {i//batch_size+1} : {len(parsed)} articles")

    return articles


def xml_text(el) -> str:
    """Extrait tout le texte d'un élément XML (y compris sous-éléments)."""
    if el is None:
        return ""
    return clean("".join(el.itertext()))


def parse_xml(xml_text_raw: str) -> list[dict]:
    articles = []
    try:
        root = ET.fromstring(xml_text_raw)
    except ET.ParseError as e:
        log.error(f"XML parse error : {e}")
        return []

    for art in root.findall(".//PubmedArticle"):
        try:
            medline = art.find("MedlineCitation")
            article = medline.find("Article")

            # ── PMID ──────────────────────────────────────────
            pmid = xml_text(medline.find("PMID"))

            # ── DOI ───────────────────────────────────────────
            doi = ""
            for id_el in art.findall(".//ArticleId"):
                if id_el.get("IdType") == "doi":
                    doi = id_el.text or ""

            # ── Titre ─────────────────────────────────────────
            title = xml_text(article.find("ArticleTitle"))

            # ── Abstract ──────────────────────────────────────
            abstract_parts = []
            for ab in article.findall(".//AbstractText"):
                label = ab.get("Label", "")
                text  = xml_text(ab)
                abstract_parts.append(f"{label}: {text}" if label else text)
            abstract = clean(" ".join(abstract_parts))

            # ── Auteurs ───────────────────────────────────────
            authors = []
            for auth in article.findall(".//Author")[:5]:
                last = xml_text(auth.find("LastName"))
                init = xml_text(auth.find("Initials"))
                if last:
                    authors.append(f"{last} {init}".strip())

            # ── Journal ───────────────────────────────────────
            journal = xml_text(article.find(".//Journal/Title"))
            if not journal:
                journal = xml_text(article.find(".//Journal/ISOAbbreviation"))

            # ── Date ──────────────────────────────────────────
            pub = article.find(".//Journal/JournalIssue/PubDate")
            year  = xml_text(pub.find("Year"))  if pub is not None else ""
            month = xml_text(pub.find("Month")) if pub is not None else ""
            date  = f"{year}-{month}" if month else year

            # ── MeSH ──────────────────────────────────────────
            mesh = [xml_text(m.find("DescriptorName"))
                    for m in medline.findall(".//MeshHeading")
                    if m.find("DescriptorName") is not None]

            # ── Keywords ──────────────────────────────────────
            keywords = [xml_text(k)
                        for k in medline.findall(".//Keyword")
                        if xml_text(k)]

            articles.append({
                "pmid":     pmid,
                "doi":      doi,
                "title":    title,
                "abstract": abstract,
                "authors":  authors,
                "journal":  journal,
                "date":     date,
                "mesh":     mesh[:10],
                "keywords": keywords[:10],
                "url":      f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            })

        except Exception as e:
            log.warning(f"Erreur parsing article : {e}")
            continue

    return articles

# ──────────────────────────────────────────────────────────────
# Score de pertinence
# ──────────────────────────────────────────────────────────────

SAFETY_KW = re.compile(
    r"\b(safe|unsafe|toxic|irritat|allergi|sensitiz|concern|risk|adverse|"
    r"carcinogen|genotox|mutagenic|endocrine|disrupt|restrict|ban|"
    r"concentration|dose|threshold|NOAEL|LOAEL|MoS|margin.of.safety|"
    r"SCCS|CIR|FDA|ECHA|regulation|cosmetic|dermatol|topical|"
    r"in.vitro|in.vivo|clinical.trial|patch.test)\b",
    re.IGNORECASE
)

def relevance_score(a: dict) -> int:
    # Tous les articles trouvés ne parlent pas forcément de sécurité. Le score compte le nombre de mots-clés de sécurité présents dans le titre et l'abstract.
    return len(SAFETY_KW.findall(f"{a['title']} {a['abstract']}"))

# ──────────────────────────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────────────────────────

def scrape_ingredient_pubmed(ingredient, cas=None, max_results=25, api_key=None):
    delay = DELAY_KEY if api_key else DELAY_NOKEY
    query = build_query(ingredient, cas)
    log.info(f"  🔬 PubMed — '{ingredient}'")
    log.info(f"     Requête : {query[:120]}…")

    pmids    = search_pmids(query, max_results, api_key, delay)
    articles = fetch_details(pmids, api_key, delay)

    for a in articles:
        a["ingredient_query"] = ingredient
        a["relevance_score"]  = relevance_score(a)

    articles.sort(key=lambda x: -x["relevance_score"])
    return articles


def enrich_sccs_file(sccs_path, max_results, api_key, output_path):
    with open(sccs_path, encoding="utf-8") as f:
        sccs_data = json.load(f)
    log.info(f"📂 {len(sccs_data)} entrées SCCS")

    for i, entry in enumerate(sccs_data, 1):
        ingredient = entry.get("Ingredient")
        cas        = entry.get("CAS_EC")
        if not ingredient:
            entry["pubmed"] = []
            continue
        log.info(f"  [{i}/{len(sccs_data)}] {ingredient}")
        articles       = scrape_ingredient_pubmed(ingredient, cas, max_results, api_key)
        entry["pubmed"] = articles
        log.info(f"     → {len(articles)} articles")
        if i % 3 == 0:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(sccs_data, f, ensure_ascii=False, indent=2)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(sccs_data, f, ensure_ascii=False, indent=2)
    log.info(f"✅ Enrichissement terminé → {output_path}")

# ──────────────────────────────────────────────────────────────
# Affichage
# ──────────────────────────────────────────────────────────────

def print_summary(articles, ingredient):
    print(f"\n{'='*65}")
    print(f"  PubMed — '{ingredient}' — {len(articles)} articles")
    print(f"{'='*65}")
    journals = {}
    for a in articles:
        journals[a["journal"]] = journals.get(a["journal"], 0) + 1
    print("  Top journaux :")
    for j, c in sorted(journals.items(), key=lambda x: -x[1])[:5]:
        print(f"    {c}x  {j}")
    print("\n  Top 5 articles :")
    for i, a in enumerate(articles[:5], 1):
        print(f"\n  [{i}] {a['title'][:72]}")
        print(f"       {a['journal']} | {a['date']} | score={a['relevance_score']}")
        print(f"       {a['url']}")
        if a["abstract"]:
            print(f"       {a['abstract'][:200]}…")
        if a["mesh"]:
            print(f"       MeSH : {', '.join(a['mesh'][:4])}")

# ──────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ingredient",    default=None)
    parser.add_argument("--cas",           default=None)
    parser.add_argument("--max-results",   type=int, default=25)
    parser.add_argument("--api-key",       default=None)
    parser.add_argument("--output",        default=None)
    parser.add_argument("--from-sccs",     default=None)
    parser.add_argument("--enrich-output", default="sccs_enriched.json")
    args = parser.parse_args()

    if args.from_sccs:
        enrich_sccs_file(Path(args.from_sccs), args.max_results,
                         args.api_key, Path(args.enrich_output))
        return

    if not args.ingredient:
        parser.print_help(); sys.exit(1)

    articles = scrape_ingredient_pubmed(
        args.ingredient, args.cas, args.max_results, args.api_key
    )
    print_summary(articles, args.ingredient)

    out = args.output or f"pubmed_{re.sub(r'[^a-z0-9]','_',args.ingredient.lower())}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    log.info(f"\n💾 {out} ({len(articles)} articles)")

if __name__ == "__main__":
    main()