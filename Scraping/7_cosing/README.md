# 🧴 CosIng SCCS Scraper

Récupération automatique des **avis SCCS** (Scientific Committee on Consumer Safety) depuis la base de données CosIng de la Commission Européenne.

## 🎯 Objectif

Extraire les **URLs des opinions SCCS** pour vérifier la sécurité et la conformité des ingrédients cosmétiques.

---

## 📚 Qu'est-ce que le SCCS ?

Le **SCCS** est le comité scientifique européen qui évalue la sécurité des ingrédients cosmétiques. Ses opinions sont essentielles pour :
- ✅ Vérifier la sécurité d'un ingrédient
- ✅ Identifier les restrictions d'usage
- ✅ Assurer la conformité réglementaire EU

🔗 **Base CosIng** : https://ec.europa.eu/growth/tools-databases/cosing/

---

## 📊 Données récupérées

| Donnée | Description |
|--------|-------------|
| **INCI_Name** | Nom international officiel |
| **CAS** | Numéro CAS |
| **EC** | Numéro EC européen |
| **Function** | Fonction cosmétique |
| **Restriction** | Restrictions d'usage |
| **SCCS_Opinion** | **🔗 URL vers l'avis SCCS** |
| **Source_URL** | Lien vers la fiche CosIng |

---

## 🚀 Installation

```bash
pip install selenium webdriver-manager pandas beautifulsoup4
```

Le ChromeDriver sera téléchargé automatiquement.

---

## 💻 Utilisation

### ⚡ Méthode 1 : Script rapide (recommandé)

```bash
python quick_sccs.py
```

**Résultats automatiquement sauvegardés dans `sccs_results.csv` ✅**

Récupère automatiquement les informations SCCS de 5 substances de test et crée un fichier CSV avec toutes les données.

**Modifiez le script pour vos propres substances :**

```python
# Dans quick_sccs.py, ligne 16
SUBSTANCES = [
    "retinol",
    "titanium dioxide", 
    "zinc oxide",
    # Ajoutez vos substances ici
]

# Ligne 23 : nom du fichier de sortie
OUTPUT_FILE = "sccs_results.csv"  # Changez si besoin
```

---

### 🔧 Méthode 2 : API Python

```python
from cosing_scraper import CosIngScraper

# Créer le scraper
scraper = CosIngScraper(headless=True)  # Mode invisible

# Rechercher une substance
info = scraper.get_ingredient_info("retinol")

# Récupérer l'URL SCCS
sccs_url = info.get('SCCS_Opinion', '')

if sccs_url and sccs_url.startswith('http'):
    print(f"✅ Avis SCCS: {sccs_url}")
    # URL directe vers le PDF de l'opinion
else:
    print("⚪ Pas d'opinion SCCS")

# Fermer
scraper.close()
```

---

### 📋 Méthode 3 : Batch (plusieurs substances)

```python
from cosing_scraper import CosIngScraper
import pandas as pd

substances = ["retinol", "titanium dioxide", "zinc oxide", "glycerin"]

scraper = CosIngScraper(headless=True)
results = []

for substance in substances:
    info = scraper.get_ingredient_info(substance)
    
    if 'error' not in info:
        results.append({
            'Substance': substance,
            'INCI': info.get('INCI_Name'),
            'CAS': info.get('CAS'),
            'Function': info.get('Function'),
            'SCCS_URL': info.get('SCCS_Opinion'),
            'Has_SCCS': bool(info.get('SCCS_Opinion'))
        })

scraper.close()

# Sauvegarder en CSV
df = pd.DataFrame(results)
df.to_csv('sccs_results.csv', index=False, encoding='utf-8-sig')

print(f"✅ {len(df)} substances traitées")
print(f"🔗 {df['Has_SCCS'].sum()} avec avis SCCS")
```

---

## 📤 Format de sortie CSV

Le fichier `sccs_results.csv` créé automatiquement contient :

| Colonne | Description | Exemple |
|---------|-------------|---------|
| **Substance_Recherchee** | Nom recherché | retinol |
| **INCI_Name** | Nom INCI officiel | RETINOL |
| **CAS** | Numéro CAS | 68-26-8 |
| **Function** | Fonction cosmétique | SKIN CONDITIONING |
| **Restriction** | Restrictions d'usage | (si applicable) |
| **SCCS_Opinion** | URL ou info SCCS | https://ec.europa.eu/.../sccs_o_174.pdf |
| **Has_SCCS_URL** | Booléen (TRUE/FALSE) | TRUE |
| **Source_URL** | Lien CosIng complet | https://ec.europa.eu/cosing/... |
| **Statut** | Statut du traitement | TROUVE / NON_TROUVE / ERREUR |

**Les URLs SCCS sont directement cliquables dans Excel ✅**

### Exemple de fichier généré

| Substance_Recherchee | INCI_Name | CAS | SCCS_Opinion | Has_SCCS_URL |
|---------------------|-----------|-----|--------------|--------------|
| retinol | RETINOL | 68-26-8 | https://ec.europa.eu/.../sccs_o_174.pdf | TRUE |
| glycerin | GLYCERIN | 56-81-5 | | FALSE |
| titanium dioxide | TITANIUM DIOXIDE | 13463-67-7 | https://ec.europa.eu/.../sccs_o_236.pdf | TRUE |

---

## ⚙️ Modes d'exécution

### Mode Silencieux (production)

```python
scraper = CosIngScraper(headless=True)  # Invisible, pas de messages
```

### Mode Verbose (debug)

```python
scraper = CosIngScraper(headless=False)  # Navigateur visible + messages détaillés
```

Affiche :
```
Ingrédient: retinol
🔍 Recherche de 'retinol'...
  ✅ RETINOL
     INCI: RETINOL
     CAS: 68-26-8
     Function: SKIN CONDITIONING
     SCCS Opinion: ✅ Lien trouvé
     URL: https://ec.europa.eu/health/ph_risk/committees/04_sccs/docs/sccs_o_174.pdf
```

---

## 🧪 Substances avec opinions SCCS fréquentes

Parfait pour tester :

**Ingrédients actifs**
- `retinol` (Vitamine A)
- `retinoic acid`
- `hydroquinone`

**Filtres UV**
- `titanium dioxide`
- `zinc oxide`
- `benzophenone`

**Conservateurs**
- `parabens`
- `methylisothiazolinone`
- `formaldehyde`

---

## ⚡ Performance

- **1 substance** : ~5-8 secondes
- **10 substances** : ~1-2 minutes
- **Mode headless** : Invisible, exécution en arrière-plan

---

## 🔗 Ressources officielles

- **CosIng** : https://ec.europa.eu/growth/tools-databases/cosing/
- **Opinions SCCS** : https://health.ec.europa.eu/scientific-committees/scientific-committee-consumer-safety-sccs/sccs-opinions_en
- **Règlement EU** : Règlement (CE) n°1223/2009

---

## 📁 Structure du projet

```
approches/7_cosing/
├── cosing_scraper.py    # Scraper principal
├── quick_sccs.py        # Script de démo rapide
├── README.md            # Cette documentation
├── STOCKAGE.md          # Guide du fichier CSV de sortie
└── sccs_results.csv     # Résultats (créé automatiquement)
```

**📖 Voir [STOCKAGE.md](STOCKAGE.md) pour tout savoir sur le fichier de sortie CSV**

---

## ✅ Cas d'usage typique

```python
from cosing_scraper import CosIngScraper

# Liste d'ingrédients à vérifier
ingredients = [
    "retinol",
    "glycerin",
    "titanium dioxide",
    "tocopherol"
]

scraper = CosIngScraper(headless=True)

print("Vérification SCCS des ingrédients...\n")

for ing in ingredients:
    info = scraper.get_ingredient_info(ing)
    
    if 'error' in info:
        print(f"❌ {ing}: non trouvé")
        continue
    
    sccs = info.get('SCCS_Opinion', '')
    
    if sccs and sccs.startswith('http'):
        print(f"✅ {ing:20s} → SCCS: {sccs}")
    elif sccs:
        print(f"⚠️  {ing:20s} → SCCS existe (sans URL)")
    else:
        print(f"⚪ {ing:20s} → Pas d'opinion SCCS")

scraper.close()
```

---

## 💡 Interprétation des résultats

| Résultat | Signification |
|----------|---------------|
| **URL SCCS trouvée** | ✅ Opinion disponible → Cliquez pour lire (PDF) |
| **"Yes" sans URL** | ⚠️ Opinion existe → Consultez CosIng manuellement |
| **Vide** | ⚪ Pas d'évaluation spécifique (souvent = sûr) |
| **Restriction présente** | ⚠️ Vérifiez les conditions d'usage |

---

## ❓ Questions fréquentes

**Q: Toutes les substances ont-elles un avis SCCS ?**  
R: Non, seules celles évaluées spécifiquement. L'absence d'avis ne signifie pas danger.

**Q: Les URLs SCCS mènent où ?**  
R: Vers des PDFs d'opinions scientifiques complètes (souvent en anglais).

**Q: Comment accélérer le scraping ?**  
R: Réduisez les `time.sleep()` dans le code, mais attention au rate limiting.

**Q: Le scraper fonctionne sans navigateur visible ?**  
R: Oui, utilisez `headless=True` (mode par défaut).

---

## 🚀 Démarrage rapide

```bash
# 1. Installer les dépendances
pip install selenium webdriver-manager pandas beautifulsoup4

# 2. Tester avec le script fourni
cd approches/7_cosing
python quick_sccs.py

# 3. Résultats automatiquement sauvegardés dans :
#    → sccs_results.csv

# 4. Ouvrir le fichier CSV
start sccs_results.csv
# OU double-cliquez sur le fichier
```

**📊 Le fichier `sccs_results.csv` contient :**
- ✅ Tous les noms INCI, CAS, fonctions
- ✅ Les URLs SCCS (cliquables dans Excel)
- ✅ Les restrictions d'usage
- ✅ Les liens CosIng complets

**📖 Voir [STOCKAGE.md](STOCKAGE.md) pour plus de détails sur le fichier de sortie**

---

**Scraper créé pour le projet StartIF - INSA 4A**  
📅 Mars 2026
