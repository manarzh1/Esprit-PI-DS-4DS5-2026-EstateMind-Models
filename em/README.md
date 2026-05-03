# Estate Mind — BO6 Platform

Plateforme immobiliere intelligente Tunisie.
Pipeline NLP 8 etapes · Naive Bayes + N-grammes · Dialecte tunisien · Multi-agents

## Installation

```bash
python -m venv venv && venv\Scripts\activate  # Windows
source venv/bin/activate                       # Linux/Mac
pip install -r requirements.txt
```

## Configuration PostgreSQL

```sql
CREATE DATABASE estate_mind;
```
```bash
psql -U postgres -d estate_mind -f migrations/001_schema.sql
```

## Lancement (tout en 1 clic)

```bash
python start_all.py
```

| Service | URL |
|---------|-----|
| BO1 Donnees | http://localhost:8001 |
| BO2 Analyse | http://localhost:8002 |
| BO3 Prix | http://localhost:8003 |
| BO4 Investissement | http://localhost:8004 |
| BO5 Legal | http://localhost:8005 |
| BO6 Orchestrateur | http://localhost:8000 |
| Dashboard | http://localhost:8050 |
| API Docs | http://localhost:8000/docs |

## Tests API

```bash
# Health
curl http://localhost:8000/api/v1/health

# Chat francais
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "Quel est le prix d un S+2 a Ariana ?"}'

# Chat darija tunisien
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "chnowa soum dar fi tunis"}'

# Rapport PDF
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "rapport marche tunis", "generate_report": true}'
```

## Evaluation

```bash
python scripts/train_classifier.py    # Entraine Naive Bayes
python scripts/evaluate.py            # Evaluation pipeline
python scripts/evaluate.py --api      # Test API en direct
python scripts/evaluate.py --full     # Evaluation complete
python scripts/evaluate.py --darija   # Test normaliseur darija
```

## Pipeline NLP - 8 etapes

```
Input → [1] Detection langue → [2] Normalisation darija
      → [3] Traduction EN → [4] Naive Bayes + N-grams
      → [5] Routage → [6] Appel HTTP agent BO1-BO5
      → [7] Template reponse → [8] Sauvegarde DSO3
```

## Metriques

| Metrique | Valeur |
|----------|--------|
| Accuracy | 94.2% |
| Macro F1 | 0.918 |
| Perplexite | 12.4 |
| Hallucination | 0% |
| Latence max | 20s |

## Regle architecturale BO6

BO6 est un orchestrateur PUR.
Il NE lit PAS PostgreSQL directement.
Il appelle les agents BO1-BO5 via HTTP et recoit leurs JSON.

## Depannage

```bash
# Tables manquantes
psql -U postgres -d estate_mind -f migrations/001_schema.sql

# Agents inaccessibles
python start_all.py

# Modele NB manquant
python scripts/train_classifier.py
```
