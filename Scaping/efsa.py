"""
EFSA Scraper — simplifié (sans API Deposits)
=============================================
L'API EFSA Deposits n'est pas encore disponible (annoncée 2026).
Ce scraper couvre les 2 sources réellement accessibles :

  1. OpenFoodTox (Zenodo XLSX)  — données toxicologiques structurées
     substances, avis EFSA, valeurs de référence (ADI/TDI/NOAEL), génotoxicité
     Record Zenodo : https://zenodo.org/records/8120114

  2. Zenodo Records API         — publications de la communauté EFSA Knowledge Junction
     rapports, datasets, posters, avis scientifiques

Aucune clé API requise.

Usage :
  pip install requests pandas openpyxl

  python efsa_scraper_simple.py --ingredient "titanium dioxide"
  python efsa_scraper_simple.py --ingredient "caffeine" --cas "58-08-2"
  python efsa_scraper_simple.py --from-list substances.json --output results.json
"""

import re
import sys
import json
import time
import argparse
import logging
from pathlib import Path

import requests

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("[WARN] pandas manquant — pip install pandas openpyxl")

# ──────────────────────────────────────────────────────────────
# Logging
# ──────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────

ZENODO_API       = "https://zenodo.org/api/records"
ZENODO_COMMUNITY = "efsa-kj"
ZENODO_RECORD_ID = "8120114"   # record OpenFoodTox sur Zenodo

# Fichiers OpenFoodTox dans ce record (noms stables)
OPENFOODTOX_FILES = {
    "substances": "OpenFoodToxTX22809_2023.xlsx",
    "outputs":    "EFSAOutputs_KJ_2023.xlsx",
    "refvalues":  "ReferenceValues_KJ_2023.xlsx",
    "genotox":    "Genotoxicity_KJ_2023.xlsx",
}

CACHE_DIR = Path(".efsa_cache")
DELAY     = 0.8   # secondes entre requêtes

# ──────────────────────────────────────────────────────────────
# HTTP helper
# ──────────────────────────────────────────────────────────────

def http_get(url: str, params: dict = None, headers: dict = None) -> requests.Response | None:
    """GET avec gestion d'erreurs et retry sur 429."""
    time.sleep(DELAY)
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
            if r.status_code == 429:
                wait = 15 * (attempt + 1)
                log.warning(f"  Rate limit (429) — attente {wait}s...")
                time.sleep(wait)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.HTTPError as e:
            code = e.response.status_code if e.response else "?"
            log.error(f"  HTTP {code} : {url}")
            return None
        except requests.exceptions.ConnectionError:
            log.error(f"  Connexion impossible (tentative {attempt+1}/3) : {url}")
            time.sleep(5)
        except Exception as e:
            log.error(f"  Erreur réseau : {e}")
            return None
    return None


def clean(text) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", str(text)).strip()


# ──────────────────────────────────────────────────────────────
# SOURCE 1 : OpenFoodTox (Zenodo XLSX)
# ──────────────────────────────────────────────────────────────
#
# OpenFoodTox est la base toxicologique structurée de l'EFSA.
# Elle contient pour chaque substance évaluée :
#   - identifiants (CAS, EC, synonymes)
#   - liste des avis EFSA publiés (outputs)
#   - valeurs de référence : ADI, TDI, NOAEL, ARfD...
#   - données de génotoxicité
#
# Les fichiers sont des XLSX multi-feuilles hébergés sur Zenodo.
# On télécharge une fois et on met en cache local.

# Signatures de colonnes pour détecter la bonne feuille dans chaque XLSX
_SHEET_SIGNATURES = {
    "substances": ["cas", "name", "substance", "ecnumber", "synonym"],
    "outputs":    ["substance", "output", "panel", "published", "legal"],
    "refvalues":  ["substance", "assessment", "year", "reference", "value",
                   "adi", "tdi", "noael"],
    "genotox":    ["substance", "genotox", "endpoint", "result"],
}


def download_openfoodtox(file_key: str) -> Path | None:
    """
    Télécharge un XLSX OpenFoodTox depuis Zenodo, avec cache local.
    Si le nom hardcodé échoue, liste les vrais fichiers du record via l'API.
    """
    if not HAS_PANDAS:
        return None

    CACHE_DIR.mkdir(exist_ok=True)
    filename = OPENFOODTOX_FILES.get(file_key)
    if not filename:
        return None

    local = CACHE_DIR / filename
    if local.exists():
        log.info(f"  [cache] {filename}")
        return local

    # Tentative 1 : URL directe
    url = f"https://zenodo.org/records/{ZENODO_RECORD_ID}/files/{filename}?download=1"
    log.info(f"  ⬇️  {filename}...")
    r = http_get(url)

    # Tentative 2 : résolution via l'API Zenodo (si le nom a changé)
    if not r:
        log.info("  Résolution des vrais noms de fichiers via l'API Zenodo...")
        meta = http_get(f"https://zenodo.org/api/records/{ZENODO_RECORD_ID}")
        if meta:
            files = {f["key"]: f["links"]["self"]
                     for f in meta.json().get("files", [])}
            log.info(f"  Fichiers disponibles : {list(files.keys())}")
            # Cherche par mots-clés dans le nom de fichier
            kw_map = {
                "substances": ["substance", "openfoodtox", "tx"],
                "outputs":    ["output"],
                "refvalues":  ["referencevalue", "refvalue"],
                "genotox":    ["genotox"],
            }
            for kw in kw_map.get(file_key, []):
                match = next((fn for fn in files if kw.lower() in fn.lower()), None)
                if match:
                    log.info(f"  Correspondance trouvée : {match}")
                    r = http_get(files[match])
                    if r:
                        local = CACHE_DIR / match
                        break

    if not r:
        log.error(f"  Impossible de télécharger '{file_key}'")
        return None

    local.write_bytes(r.content)
    log.info(f"  ✅ {local.name} ({len(r.content) // 1024} KB)")
    return local


def load_sheet(path: Path, file_key: str) -> "pd.DataFrame | None":
    """
    Ouvre un XLSX et sélectionne automatiquement la bonne feuille
    en comparant ses colonnes aux signatures attendues.
    """
    try:
        xl     = pd.ExcelFile(path, engine="openpyxl")
        sheets = xl.sheet_names
        sigs   = _SHEET_SIGNATURES.get(file_key, [])

        best_sheet, best_score = None, 0
        for sheet in sheets:
            df    = pd.read_excel(xl, sheet_name=sheet, nrows=5, engine="openpyxl")
            cols  = [c.strip().lower() for c in df.columns]
            score = sum(1 for sig in sigs if any(sig in c for c in cols))
            if score > best_score:
                best_score, best_sheet = score, sheet

        # Fallback : feuille avec le plus de lignes
        if best_sheet is None:
            best_sheet = max(sheets,
                             key=lambda s: len(pd.read_excel(xl, sheet_name=s, nrows=9999)))

        df = pd.read_excel(xl, sheet_name=best_sheet, engine="openpyxl")
        df.columns = [c.strip() for c in df.columns]
        log.info(f"  {file_key} [{best_sheet}] : {len(df)} lignes")
        return df

    except Exception as e:
        log.error(f"  Erreur lecture {file_key} : {e}")
        return None


def search_openfoodtox(ingredient: str, cas: str | None = None) -> list[dict]:
    """
    Cherche une substance dans OpenFoodTox et retourne :
    - ses identifiants (CAS, EC)
    - les avis EFSA associés (outputs)
    - les valeurs de référence (ADI, TDI, NOAEL)
    - les données de génotoxicité
    """
    if not HAS_PANDAS:
        return []

    ing_lower = ingredient.lower()
    cas_clean = cas.split("/")[0].strip() if cas else None

    # Chargement des 4 fichiers
    dfs = {}
    for key in ["substances", "outputs", "refvalues", "genotox"]:
        path = download_openfoodtox(key)
        if path:
            df = load_sheet(path, key)
            if df is not None:
                dfs[key] = df

    if "substances" not in dfs:
        log.warning("  OpenFoodTox : fichier 'substances' non disponible")
        return []

    sub_df = dfs["substances"]

    # Détection flexible des colonnes de nom, CAS et ID
    name_cols = [c for c in sub_df.columns
                 if any(k in c.lower() for k in ["name", "substance", "param_name", "synonym"])]
    cas_cols  = [c for c in sub_df.columns
                 if any(k in c.lower() for k in ["cas", "casnumber", "cas_number"])]
    id_cols   = [c for c in sub_df.columns
                 if any(k in c.lower() for k in ["param_id", "sub_id", "substanceid", "substance_id"])]

    # Recherche par nom et/ou CAS
    matched = set()
    for col in name_cols:
        mask = sub_df[col].astype(str).str.lower().str.contains(re.escape(ing_lower), na=False)
        matched.update(sub_df[mask].index.tolist())
    if cas_clean:
        for col in cas_cols:
            mask = sub_df[col].astype(str).str.contains(re.escape(cas_clean), na=False)
            matched.update(sub_df[mask].index.tolist())

    log.info(f"  OpenFoodTox : {len(matched)} substance(s) trouvée(s)")
    results = []

    for idx in matched:
        row = sub_df.iloc[idx]

        name  = next((clean(row.get(c)) for c in name_cols
                      if row.get(c) and str(row.get(c)).strip() not in ("nan", "")), "")
        cas_v = next((clean(row.get(c)) for c in cas_cols
                      if row.get(c) and str(row.get(c)).strip() not in ("nan", "")), "")
        sub_id = (next((row.get(c) for c in id_cols if pd.notna(row.get(c))), None)
                  if id_cols else name)

        def join(df_key: str) -> list[dict]:
            """Jointure sur sub_id ou nom de substance."""
            if df_key not in dfs:
                return []
            df = dfs[df_key]
            join_cols = [c for c in df.columns
                         if any(k in c.lower() for k in
                                ["param_id", "substanceid", "substance_id", "substance", "name"])]
            for col in join_cols:
                rows = df[df[col].astype(str).str.lower() == str(sub_id).lower()]
                if len(rows) > 0:
                    return [{k: clean(v) for k, v in r.items()
                             if v and str(v).strip() not in ("nan", "")}
                            for _, r in rows.iterrows()]
            return []

        results.append({
            "source":     "OpenFoodTox",
            "ingredient": name,
            "cas":        cas_v,
            "sub_id":     str(sub_id) if sub_id else "",
            "outputs":    join("outputs"),
            "ref_values": join("refvalues"),
            "genotox":    join("genotox"),   # ← ajout vs v3 (le fichier était ignoré)
        })

    return results


# ──────────────────────────────────────────────────────────────
# SOURCE 2 : Zenodo Records API (communauté EFSA Knowledge Junction)
# ──────────────────────────────────────────────────────────────
#
# Zenodo héberge les publications de la communauté EFSA-KJ :
# rapports techniques, datasets, présentations, avis scientifiques.
# Accessible sans clé, paginé, trié par pertinence ou date.

def search_zenodo(ingredient: str, cas: str | None = None,
                  max_results: int = 25) -> list[dict]:
    """
    Recherche paginée dans la communauté EFSA sur Zenodo.
    Fallback vers une recherche globale si la communauté ne retourne rien.
    """
    q = f'"{ingredient}"'
    if cas:
        q = f'{q} OR "{cas.split("/")[0].strip()}"'

    params = {
        "q":           q,
        "communities": ZENODO_COMMUNITY,
        "size":        min(max_results, 100),
        "sort":        "bestmatch",
        "status":      "published",
    }

    r = http_get(ZENODO_API, params=params)

    # Fallback : sans filtre communauté
    if not r:
        log.info("  Fallback : recherche Zenodo sans filtre communauté")
        params.pop("communities")
        params["q"] = f'{q} AND (efsa OR "food safety")'
        r = http_get(ZENODO_API, params=params)

    if not r:
        return []

    try:
        data    = r.json()
        hits    = data.get("hits", {}).get("hits", data.get("items", []))
        total   = data.get("hits", {}).get("total", len(hits))
        log.info(f"  Zenodo : {total} résultat(s)")

        results = [_parse_zenodo(h, ingredient) for h in hits]
        results = [r for r in results if r]
        results.sort(key=lambda x: -x.get("relevance", 0))
        return results[:max_results]

    except Exception as e:
        log.error(f"  Erreur parsing Zenodo : {e}")
        return []


def _parse_zenodo(record: dict, ingredient: str) -> dict | None:
    """Normalise un record Zenodo brut en dict exploitable."""
    try:
        meta     = record.get("metadata", record)
        title    = clean(meta.get("title", ""))
        abstract = clean(meta.get("description", ""))
        date     = clean(meta.get("publication_date", meta.get("created", "")))[:10]
        doi      = clean(record.get("doi", meta.get("doi", "")))
        rec_id   = str(record.get("id", ""))
        rec_type = clean(meta.get("resource_type", {}).get("title", "")) \
                   if isinstance(meta.get("resource_type"), dict) else ""
        keywords = meta.get("keywords", [])
        authors  = [clean(c.get("name", "")) for c in meta.get("creators", [])[:5]
                    if c.get("name")]
        files    = [{"name": f.get("key", ""), "size_kb": round(f.get("size", 0) / 1024, 1)}
                    for f in record.get("files", [])[:5]]

        if not title:
            return None

        url = (doi if doi.startswith("http")
               else f"https://doi.org/{doi}" if doi
               else f"https://zenodo.org/records/{rec_id}")

        return {
            "source":     "Zenodo",
            "record_id":  rec_id,
            "ingredient": ingredient,
            "title":      title,
            "abstract":   abstract[:600],
            "date":       date,
            "type":       rec_type,
            "doi":        doi,
            "url":        url,
            "keywords":   keywords[:10],
            "authors":    authors,
            "files":      files,
            "conclusion": _classify(title, abstract),
            "relevance":  _relevance(title, abstract),
        }
    except Exception as e:
        log.warning(f"  Parse Zenodo : {e}")
        return None


# ──────────────────────────────────────────────────────────────
# Analyse sémantique légère
# ──────────────────────────────────────────────────────────────

_SAFE = re.compile(
    r"\b(safe|no concern|acceptable|no risk|tolerable|no adverse|GRAS|"
    r"acceptable daily intake|ADI established|not genotoxic|no safety concern)\b",
    re.IGNORECASE,
)
_RISK = re.compile(
    r"\b(unsafe|concern|risk|genotoxic|carcinogen|harmful|hazard|restricted|"
    r"banned|not acceptable|adverse effect|endocrine disrupt|safety concern|not safe)\b",
    re.IGNORECASE,
)
_UNCERTAIN = re.compile(
    r"\b(insufficient data|uncertain|further studies|data gap|no conclusion|"
    r"inconclusive|limited data|more data needed)\b",
    re.IGNORECASE,
)
_RELEVANCE = re.compile(
    r"\b(safety|assessment|opinion|risk|evaluation|conclusion|cosmetic|food|feed|"
    r"additive|contaminant|pesticide|acceptable|tolerable|concern|hazard|exposure|"
    r"genotox|EFSA|scientific|toxicology|NOAEL|ADI|TDI|ban|restriction|regulatory)\b",
    re.IGNORECASE,
)


def _classify(title: str, abstract: str) -> str:
    text = f"{title} {abstract}"
    if _RISK.search(text):      return "concern / risk identified"
    if _SAFE.search(text):      return "safe / no concern"
    if _UNCERTAIN.search(text): return "inconclusive / data gaps"
    return "unknown"


def _relevance(title: str, abstract: str) -> int:
    return len(_RELEVANCE.findall(f"{title} {abstract}"))


# ──────────────────────────────────────────────────────────────
# Pipeline principal
# ──────────────────────────────────────────────────────────────

def scrape(ingredient: str, cas: str | None = None,
           max_results: int = 25) -> dict:

    log.info(f"\n{'='*60}")
    log.info(f"  EFSA — '{ingredient}'" + (f" (CAS: {cas})" if cas else ""))
    log.info(f"{'='*60}")

    log.info("\n[1/2] OpenFoodTox (Zenodo XLSX)...")
    oft = search_openfoodtox(ingredient, cas) if HAS_PANDAS else []

    log.info("\n[2/2] Zenodo Records (communauté EFSA-KJ)...")
    zenodo = search_zenodo(ingredient, cas, max_results)

    return {
        "ingredient":  ingredient,
        "cas":         cas or "",
        "openfoodtox": oft,
        "zenodo":      zenodo,
        "summary":     _summary(ingredient, cas, oft, zenodo),
    }


def _summary(ingredient: str, cas: str | None,
             oft: list, zenodo: list) -> dict:
    conclusions = [r["conclusion"] for r in zenodo if r.get("conclusion") != "unknown"]
    dates       = sorted([r["date"] for r in zenodo if r.get("date")], reverse=True)
    types       = list({r["type"] for r in zenodo if r.get("type")})
    ref_values  = [rv for s in oft for rv in s.get("ref_values", [])[:3]]
    genotox     = [g  for s in oft for g  in s.get("genotox",    [])[:3]]

    priority = ["concern / risk identified", "safe / no concern", "inconclusive / data gaps"]
    dominant = next((c for c in priority if c in conclusions), "unknown")

    return {
        "ingredient":        ingredient,
        "cas":               cas or "",
        "dominant_conclusion": dominant,
        "latest_date":       dates[0] if dates else "",
        "document_types":    types,
        "nb_zenodo":         len(zenodo),
        "nb_oft_substances": len(oft),
        "ref_values":        ref_values[:5],
        "genotox_data":      genotox[:3],   # ← nouveau champ utile
    }


# ──────────────────────────────────────────────────────────────
# Affichage console
# ──────────────────────────────────────────────────────────────

def print_result(result: dict):
    s   = result["summary"]
    sep = "=" * 65
    print(f"\n{sep}")
    print(f"  EFSA — '{result['ingredient']}'")
    print(f"{sep}")
    print(f"  CAS                    : {s['cas'] or 'N/A'}")
    print(f"  Conclusion dominante   : {s['dominant_conclusion']}")
    print(f"  Date la + récente      : {s['latest_date'] or 'N/D'}")
    print(f"  Documents Zenodo       : {s['nb_zenodo']}")
    print(f"  Substances OpenFoodTox : {s['nb_oft_substances']}")

    if s["ref_values"]:
        print(f"\n  Valeurs de référence (ADI/TDI/NOAEL) :")
        for rv in s["ref_values"][:3]:
            print(f"    {rv}")

    if s["genotox_data"]:
        print(f"\n  Données de génotoxicité :")
        for g in s["genotox_data"]:
            print(f"    {g}")

    if result["zenodo"]:
        print(f"\n  Top 3 Zenodo (par pertinence) :")
        for i, r in enumerate(result["zenodo"][:3], 1):
            print(f"\n  [{i}] {r['title'][:70]}")
            print(f"       Type       : {r['type'] or 'N/D'}")
            print(f"       Date       : {r['date'] or 'N/D'}")
            print(f"       Conclusion : {r['conclusion']}")
            print(f"       URL        : {r['url']}")
            if r.get("abstract"):
                print(f"       Résumé     : {r['abstract'][:160]}…")


# ──────────────────────────────────────────────────────────────
# Mode batch
# ──────────────────────────────────────────────────────────────

def process_list(input_path: Path, output_path: Path, max_results: int):
    """
    Traite une liste de substances depuis un fichier JSON.
    Format attendu : [{"ingredient": "...", "cas": "..."}, ...]
    Sauvegarde intermédiaire toutes les 5 substances.
    """
    with open(input_path, encoding="utf-8") as f:
        items = json.load(f)
    log.info(f"📂 {len(items)} substance(s) à traiter")

    results = []
    for i, item in enumerate(items, 1):
        ingredient = item.get("ingredient", item.get("Ingredient", item.get("name", "")))
        cas        = item.get("cas", item.get("CAS_EC", None))
        if not ingredient:
            continue
        log.info(f"\n[{i}/{len(items)}] {ingredient}")
        results.append(scrape(ingredient, cas, max_results))

        if i % 5 == 0:
            _save(results, output_path)
            log.info(f"  💾 Sauvegarde intermédiaire ({i}/{len(items)})")

    _save(results, output_path)
    log.info(f"\n✅ Terminé → {output_path}")


def _save(data, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="EFSA Scraper (OpenFoodTox + Zenodo) — sans API Deposits",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Exemples :
  python efsa_scraper_simple.py --ingredient "titanium dioxide"
  python efsa_scraper_simple.py --ingredient "aspartame" --cas "22839-47-0" --max 50
  python efsa_scraper_simple.py --from-list substances.json --output results.json
        """,
    )
    parser.add_argument("--ingredient", default=None,
                        help="Substance à rechercher")
    parser.add_argument("--cas",        default=None,
                        help="Numéro CAS optionnel (ex: '13463-67-7')")
    parser.add_argument("--max",        type=int, default=25,
                        help="Nombre max de résultats Zenodo (défaut: 25)")
    parser.add_argument("--from-list",  default=None,
                        help="Fichier JSON de substances à traiter en batch")
    parser.add_argument("--output",     default=None,
                        help="Fichier JSON de sortie")
    args = parser.parse_args()

    if args.from_list:
        out = Path(args.output or "efsa_results.json")
        process_list(Path(args.from_list), out, args.max)
        return

    if not args.ingredient:
        parser.print_help()
        sys.exit(1)

    result = scrape(args.ingredient, args.cas, args.max)
    print_result(result)

    out = args.output or f"efsa_{re.sub(r'[^a-z0-9]', '_', args.ingredient.lower())}.json"
    _save(result, Path(out))
    log.info(f"\n💾 → {out}")


if __name__ == "__main__":
    main()