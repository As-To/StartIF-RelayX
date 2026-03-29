"""
Point d'entree pour lancer une prediction reglementaire.
Usage : python run_prediction.py "Titanium Dioxide"
        python run_prediction.py  (mode interactif)
"""
import sys

# Forcer UTF-8 sur la sortie standard (nécessaire sur Windows)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent import run_agent


def main():
    if len(sys.argv) > 1:
        ingredient = " ".join(sys.argv[1:])
        print(f"=== Analyse de risque reglementaire : {ingredient} ===\n")
        result = run_agent(
            f"Analyse le risque reglementaire pour l'ingredient : {ingredient}"
        )
        print("\n" + "=" * 60)
        print("RESULTAT FINAL")
        print("=" * 60)
        print(result)
    else:
        print("\n" + "=" * 60)
        print("  Agent de prediction reglementaire - Start-IF (POC)")
        print("  Tape 'quit' pour quitter")
        print("=" * 60 + "\n")

        while True:
            ingredient = input("Ingredient a analyser : ").strip()
            if ingredient.lower() in ("quit", "exit", "q"):
                print("Au revoir.")
                break
            if not ingredient:
                continue

            print(f"\n[Analyse en cours...]\n")
            result = run_agent(
                f"Analyse le risque reglementaire pour l'ingredient : {ingredient}"
            )
            print("\n" + "=" * 60)
            print("RESULTAT")
            print("=" * 60)
            print(result)
            print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
