# Architecture — Start-IF (POC)

Agent de prédiction réglementaire pour ingrédients cosmétiques européens.

---

## Arborescence

```
StartIF-RelayX/
├── start_if_poc/
│   ├── agent/                      # Code de l'agent
│   │   ├── run_prediction.py       # Point d'entrée CLI
│   │   ├── agent.py                # Boucle agent (tool use Anthropic)
│   │   ├── tools.py                # Outils : accès aux données locales
│   │   ├── system_prompt.txt       # Grille d'évaluation réglementaire
│   │   ├── requirements.txt        # Dépendances Python
│   │   ├── .env                    # Clé API et configuration (non versionné)
│   │   └── logs/                   # Fichiers markdown générés par analyse
│   └── Preprocessing/
│       └── data/
│           └── ingredients/        # 41 fichiers JSON, un par ingrédient
├── ARCHITECTURE.md
├── CLAUDE.md
└── README.md
```

---

## Rôle de chaque fichier

### `run_prediction.py` — Point d'entrée

Lance une analyse depuis la ligne de commande ou en mode interactif.

```
python run_prediction.py "benzophenone"          # mode CLI
python run_prediction.py                         # mode interactif
```

**Fonction principale :** `main()` — lit l'ingrédient en argument ou via `input()`,
formate la requête et appelle `run_agent()`.

---

### `agent.py` — Boucle agent

Gère la conversation avec l'API Anthropic (Claude Haiku) en mode tool use.

| Fonction | Rôle |
|----------|------|
| `load_system_prompt()` | Lit `system_prompt.txt` |
| `_ingredient_from_query(query)` | Extrait le nom de l'ingrédient depuis la requête |
| `_write_log(ingredient, log_lines, result)` | Écrit le fichier markdown dans `logs/` |
| `run_agent(query, verbose)` | **Fonction principale** — boucle agent, retourne le texte final |

Variables d'environnement lues : `LLM_API_KEY`, `LLM_MODEL`, `WRITE_LOGS`.

---

### `tools.py` — Accès aux données locales

Lit les fichiers JSON dans `Preprocessing/data/ingredients/`. Aucun appel réseau.

| Fonction | Rôle |
|----------|------|
| `_find_ingredient_file(name)` | Recherche par nom, CAS, INCI ou synonyme PubChem. Priorité : exact > substring > synonymes. Ignore les fichiers illisibles. |
| `search_ingredient(ingredient)` | Retourne toutes les données d'un ingrédient (JSON), PubMed limité aux 5 articles les plus pertinents |
| `list_all_ingredients()` | Liste allégée de tous les ingrédients (nom, CAS, verdict SCCS, annexes EUR-Lex, formule) |

---

### `system_prompt.txt` — Grille d'évaluation

Définit le comportement de l'agent. Contient la méthode de raisonnement en 6 étapes et les règles absolues (ne pas halluciner, citer les sources, répondre en français).

**C'est le principal levier de contrôle du comportement** — modifier ce fichier, pas le code Python.

---

### `Preprocessing/data/ingredients/*.json` — Base de données locale

41 fichiers JSON, un par ingrédient. Structure commune :

```json
{
  "ingredient": "Benzophenone",
  "cas": "...",
  "sccs":    { "dernier_verdict": "...", "avis": [...] },
  "eurlex":  { "in_annex_II": false, "in_annex_III": false },
  "echa":    { "is_svhc": false, "classification_clp": null },
  "pubmed":  { "nb_articles_total": 10, "articles": [...] },
  "pubchem": { "ghs_hazards": null, "synonyms": [...] },
  "cosing":  { "inci_name": "..." }
}
```

Certains champs peuvent être `null` ou absents — les outils gèrent ce cas avec `.get()`.
**Ces fichiers ne doivent jamais être modifiés manuellement.**

---

### `logs/` — Sorties générées

Créé automatiquement si `WRITE_LOGS=true`. Chaque analyse produit un fichier
`{ingredient}_{timestamp}.md` contenant le raisonnement itération par itération
et le résultat final structuré (PROBABILITÉ, HORIZON, NATURE, CONFIANCE, EXPLICATION).

---

## Boucle principale de l'agent

```
run_prediction.py
       │
       ▼
   run_agent(query)          ← agent.py
       │
       ├─ Charge system_prompt.txt
       ├─ Envoie la requête à Claude Haiku (Anthropic API)
       │
       └─ BOUCLE (max 10 itérations) ──────────────────────────────────┐
               │                                                       │
               ├─ Claude répond avec des appels d'outils (tool_use)    │
               │       │                                               │
               │       ├─ search_ingredient(name)  → lit JSON local    │
               │       └─ list_all_ingredients()   → lit tous les JSON │
               │                                                       │
               ├─ Les résultats sont réinjectés dans la conversation   │
               │                                                       │
               └─ Claude répond sans appel d'outil → RÉSULTAT FINAL ───┘
                       │
                       ├─ Affichage console
                       └─ Écriture dans logs/{ingredient}_{timestamp}.md
```

**Résultat attendu :**
```
PROBABILITÉ : 0.0 à 1.0
HORIZON     : fourchette en mois
NATURE      : interdiction / restriction / durcissement / réévaluation
CONFIANCE   : ÉLEVÉE / MOYENNE / FAIBLE
EXPLICATION : 3 à 5 phrases avec sources (SCCS/xxxx/xx, PMIDxxxx, Annexe III entrée x)
```
