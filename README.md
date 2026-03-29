# StartIF-RelayX
Projet académique mené avec la startup RelayX visant à développer un modèle d’IA capable d’anticiper l’obsolescence réglementaire d’ingrédients cosmétiques.

###  Configurer l'environnement
Configurez le fichier .env, conformément au fichier .env.example : clé API Anthropic et nom du modèle souhaité.

### Installer les dépendances nécessaires
```bash
pip install -r requirements.txt
```

### Lancer une analyse

Lance une analyse depuis la ligne de commande ou en mode interactif.

```bash
python run_prediction.py "benzophenone"  # mode CLI
python run_prediction.py                 # mode interactif
```
