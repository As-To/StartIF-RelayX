# Synthèse des Statistiques SCCS — Projet RelayX

**Date de génération :** 16 mars 2026
**Périmètre :** Avis SCCS (Scientific Committee on Consumer Safety) — Opinions finales, avis scientifiques et addendums
**Période couverte :** Juillet 2016 – Février 2026

---

## 1. Statistiques Générales SCCS

Le dataset couvre **97 avis SCCS** portant sur **75 ingrédients/produits distincts**, répartis sur une période de près de 10 ans (29 juillet 2016 au 2 février 2026).

### Répartition des Verdicts

| Verdict | Nombre | Pourcentage |
|---------|--------|-------------|
| Safe | 32 | 33,0% |
| Restriction Recommandée | 27 | 27,8% |
| Données Insuffisantes | 20 | 20,6% |
| Not Safe | 18 | 18,6% |

**Observation clé :** Près de **46,4%** des avis conduisent à un signal négatif (Not Safe + Restriction Recommandée), ce qui constitue un indicateur fort pour le modèle de prédiction RelayX. L'avis "Données Insuffisantes" (20,6%) représente également un signal faible potentiel, car il peut évoluer vers un avis négatif lors de soumissions ultérieures.

### Répartition par Catégorie d'Ingrédient

| Catégorie | Nombre d'avis |
|-----------|---------------|
| Other (divers) | 24 |
| Hair Dye | 19 |
| Nanomaterial | 14 |
| Preservative | 14 |
| UV Filter | 13 |
| Fragrance | 11 |
| Colorant | 2 |

### Répartition par Type de Rapport

| Type | Nombre |
|------|--------|
| Final Opinion | 77 |
| Scientific Advice | 14 |
| Scientific Opinion | 2 |
| Autres (Addendum, Revision, Preliminary) | 4 |

---

## 2. Top 5 et Top 10 des Produits à Risque

Critère : ingrédients ayant reçu un avis négatif ("Not Safe" ou "Restriction Recommandée").

### Top 5

| Rang | Ingrédient | Nombre d'avis négatifs |
|------|-----------|----------------------|
| 1 | Methyl salicylate | 3 |
| 2 | Titanium Dioxide (TiO2) | 3 |
| 3 | Aluminium (composés) | 3 |
| 4 | Acetylated Vetiver Oil (AVO) | 2 |
| 5 | Butylparaben | 2 |

### Top 6–10

| Rang | Ingrédient | Nombre d'avis négatifs |
|------|-----------|----------------------|
| 6 | Vitamin A (Retinol) | 2 |
| 7 | Homosalate | 2 |
| 8 | Silver (micron-sized) | 1 |
| 9 | Citral | 1 |
| 10 | Benzyl salicylate | 1 |

**Autres ingrédients "Not Safe" notables :** Benzophenone-1 (BP-1), Benzophenone-2 (BP-2), Benzophenone-3 (BP-3), 4-Methylbenzylidene Camphor (4-MBC, banni), Butylphenyl methylpropional (Lilial, banni), PHMB, Zinc Pyrithione, Triclocarban/Triclosan, HEMA, Prostaglandins, Bisphenol A.

---

## 3. Top 5 et Top 10 des Produits les Plus Évalués

Critère : fréquence totale des avis SCCS (toutes conclusions confondues).

### Top 5

| Rang | Ingrédient | Nombre total d'avis |
|------|-----------|-------------------|
| 1 | Titanium Dioxide (TiO2) | 5 |
| 2 | Methyl salicylate | 3 |
| 3 | Hydroxyapatite (nano) | 3 |
| 4 | Salicylic Acid | 3 |
| 5 | Aluminium (composés) | 3 |

### Top 6–10

| Rang | Ingrédient | Nombre total d'avis |
|------|-----------|-------------------|
| 6 | Silver | 2 |
| 7 | Acetylated Vetiver Oil | 2 |
| 8 | Hexyl Salicylate | 2 |
| 9 | Basic Blue 99 | 2 |
| 10 | Hydroxypropyl p-phenylenediamine | 2 |

---

## 4. Tendances Temporelles

### Nombre d'avis SCCS par année

| Année | Avis Total | Avis Négatifs |
|-------|-----------|---------------|
| 2016 | 6 | 1 |
| 2017 | 5 | 1 |
| 2018 | 7 | 2 |
| 2019 | 9 | 3 |
| 2020 | 6 | 4 |
| 2021 | 15 | 6 |
| 2022 | 6 | 6 |
| 2023 | 13 | 4 |
| 2024 | 13 | 8 |
| 2025 | 13 | 8 |
| 2026 | 4 (partiel) | 2 |

**Tendance observée :** Le volume d'avis a significativement augmenté depuis 2021 (pic de 15 avis). La proportion d'avis négatifs est en forte hausse, passant de ~17% (2016-2018) à ~62% (2024-2025), reflétant un durcissement réglementaire notable, en particulier sur les perturbateurs endocriniens et les UV filters.

---

## 5. Durée Signal → Réglementation (Données partielles)

Cas documentés de transition avis SCCS → action réglementaire EU :

| Ingrédient | Avis SCCS (négatif) | Réglementation EU | Délai |
|-----------|---------------------|-------------------|-------|
| 4-MBC | Avril 2022 (Not Safe) | EU 2024/996 (ban) | ~24 mois |
| Lilial (p-BMHCA) | Mai 2019 (Not Safe) | Banni mars 2022 | ~34 mois |
| Benzophenone-3 | Mars 2021 (Not Safe at 6%) | EU 2022/1176 (restriction) | ~16 mois |
| Octocrylene | Mars 2021 (Restriction) | EU 2022/1176 (restriction) | ~16 mois |
| Nano ingredients (multiple) | 2018-2021 | EU 2024/858 (Omnibus NANO) | ~36-72 mois |

**Statistiques préliminaires :** Durée médiane estimée signal→réglementation : **24 mois** (min: 16, max: 72, moyenne: ~32 mois).

> *Note : Ces chiffres seront affinés après intégration complète des données Eur-Lex par les membres de l'équipe.*

---

## 6. Taux de Suivi (Données partielles)

Sur les 18 avis "Not Safe" identifiés, au moins **5 ont déjà conduit à une action réglementaire concrète** (interdiction ou restriction dans les Annexes du Règlement (CE) 1223/2009), soit un taux de suivi préliminaire d'environ **28%**.

Ce taux est probablement sous-estimé car certaines actions réglementaires sont en cours de finalisation (Omnibus VIII sur Hexyl Salicylate, Silver, OPP/OPP salt) et d'autres données Eur-Lex n'ont pas encore été intégrées.

> *Note : Le taux de suivi complet sera calculé après intégration des données Eur-Lex et du mapping avis→réglementation.*

---

## Méthodologie et Limites

**Sources :** Site officiel de la Commission Européenne (DG SANTE), PDFs des avis SCCS, sources réglementaires secondaires (CIRS Group, Critical Catalyst, CosLaw.eu, REACH24H).

**Limites :**
- Certains verdicts ont été catégorisés à partir de résumés et non des PDFs complets. Une vérification systématique PDF par PDF est recommandée.
- Les avis antérieurs à 2016 (période SCCS 2013-2016) ne sont pas inclus dans cette première itération.
- Les concentrations maximales recommandées sont parfois complexes (multiples conditions, types de produits) et ont été simplifiées dans le dataset.
- Les statistiques de durée signal→réglementation et taux de suivi sont partielles et seront complétées après intégration des données Eur-Lex.
