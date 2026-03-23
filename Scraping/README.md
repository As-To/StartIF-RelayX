# 🧪 Collecte de données chimiques et cosmétiques - Guide de test

## 📋 Installation

```bash
pip install -r requirements.txt
```

## 🎯 Approches disponibles

Ce projet contient **7 approches** pour récupérer des données chimiques/cosmétiques depuis différentes sources (ECHA, PubChem, CosIng).

**📄 Voir [ANALYSE_COMPARATIVE.txt](ANALYSE_COMPARATIVE.txt)** pour une analyse complète des avantages/limites de chaque source.

---

## 🚀 Comment tester chaque approche

### Approche 1 : Scraping ECHA (3 variantes)

**Source :** European Chemicals Agency (base réglementaire EU)  
**Localisation :** `approches/1_scraping_echa/`

**⚠️ Attention :** ECHA a une forte protection anti-bot, taux d'échec élevé.

```bash
# Variante basique (simple requests - souvent bloqué)
cd approches/1_scraping_echa
python scraper_basic.py

# Variante avancée (rotation user-agent, retry logic)
python scraper_advanced.py

# Variante Selenium (navigateur réel - meilleur taux de succès)
python scraper_selenium.py
```

**📊 Taux de succès estimés :** Basic ~30% | Advanced ~60% | Selenium ~90%

---

### Approche 2 : API PubChem ⭐ RECOMMANDÉ

**Source :** NIH PubChem (base scientifique mondiale)  
**Localisation :** `approches/2_api_pubchem/`

**✅ Avantages :** Pas de blocage, 100% fiable, 30+ colonnes de données

```bash
cd approches/2_api_pubchem
python test_complet.py
```

**Résultat :** Fichier CSV avec 30 colonnes (CAS, EC, formule, GHS, propriétés moléculaires, etc.)

---

### Approche 3 : Mode hybride

**Source :** PubChem + saisie manuelle  
**Localisation :** `approches/3_mode_hybride/`

```bash
cd approches/3_mode_hybride
python hybrid_collector.py
```

---

### Approche 4 : Automatisation 100%

**Source :** PubChem en mode batch  
**Localisation :** `approches/4_auto_100_pourcent/`

```bash
cd approches/4_auto_100_pourcent
python auto_update.py
```

---

### Approche 5 : Ajout manuel

**Source :** Saisie interactive  
**Localisation :** `approches/5_ajout_manuel/`

```bash
cd approches/5_ajout_manuel
python add_substance.py
```

---

### Approche 6 : Gestionnaire BDD

**Source :** Interface de gestion centralisée  
**Localisation :** `approches/6_gestionnaire_bdd/`

```bash
cd approches/6_gestionnaire_bdd
python update_database.py
```

**Menu interactif :** Ajouter, supprimer, modifier, afficher statistiques

---

### Approche 7 : CosIng (Cosmétiques EU + Avis SCCS) ⭐ UNIQUE

**Source :** Base européenne cosmétiques avec avis scientifiques SCCS  
**Localisation :** `approches/7_cosing/`

**✅ Spécialité :** Extraction des URLs vers avis SCCS (PDF réglementaires)

```bash
cd approches/7_cosing
python quick_sccs.py
```

**Résultat :** Fichier `sccs_results.csv` avec nom INCI, fonction cosmétique, restrictions, URLs vers avis SCCS

**Exemple de substances cosmétiques à tester :**
- retinol
- titanium dioxide
- parabens
- zinc oxide

---

## 📚 Documentation détaillée

Chaque approche contient son propre README avec explications détaillées dans son dossier.

Consultez **[ANALYSE_COMPARATIVE.txt](ANALYSE_COMPARATIVE.txt)** pour comprendre :
- Les avantages et limites de chaque source de données
- Quand utiliser ECHA vs PubChem vs CosIng
- La qualité et fiabilité des données obtenues
- Les recommandations pour chaque cas d'usage

---

## 📊 Recommandations rapides

| Besoin | Approche recommandée |
|--------|---------------------|
| **Démarrage rapide, données générales** | Approche 2 (PubChem API) |
| **Cosmétiques EU, avis SCCS** | Approche 7 (CosIng) |
| **Conformité réglementaire EU** | Approche 1 (ECHA Selenium) |
| **Grandes quantités (100+)** | Approche 2 (PubChem API) |
| **Quelques substances manuelles** | Approche 5 (Ajout manuel) |

---

**Version** : 3.0  
**Date** : Mars 2026  
**Projet** : StartIF INSA
