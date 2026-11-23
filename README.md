# SQL Agent – agent d'optimisation PostgreSQL

Projet n°11 – un agent qui aide les développeurs et les DBA à **repérer, expliquer et corriger les requêtes SQL lentes, sans risquer d'abîmer la base de production**.

> 🚧 En construction – semaine 1 (squelette). Voir [la fiche de cadrage](docs/FICHE_CADRAGE.md) et [la feuille de route](docs/FEUILLE_DE_ROUTE.md).

## Équipe
- Ahmed Sami Maakoul
- Youssef Agoub

## Lancer l'application (Docker, une commande)

Prérequis : Docker Desktop (ou Docker Engine + Compose v2).

**Option A – tout dans Docker** (machine avec ≥ 6 Go de RAM alloués à Docker) :

```bash
docker compose --profile ollama up -d --build
```

**Option B – Ollama déjà installé sur le PC** (recommandé si peu de RAM) :

```bash
copy .env.example .env          # puis décommenter la ligne OLLAMA_URL=http://host.docker.internal:11434
ollama pull qwen2.5-coder:3b
docker compose up -d --build
```

Puis ouvrir :
- Interface : http://localhost:8501
- API (documentation) : http://localhost:8000/docs

Le premier lancement télécharge les images et le modèle (~2 Go) : compter 5 à 15 minutes.

| Service | Rôle | Port PC |
|---|---|---|
| `db` | PostgreSQL 16 + pg_stat_statements + HypoPG (base de démo) | 5433 |
| `api` | L'agent (FastAPI), connecté à la base avec le rôle **lecture seule** `agent_ro` | 8000 |
| `ui` | Interface Streamlit | 8501 |
| `ollama` | LLM local (option A uniquement) | – |

## Limites connues

- **LLM sur processeur** : sans carte graphique, `qwen2.5-coder:3b` répond en ~17 s (modèle chargé) et ~60 s au premier appel (mesuré sur un PC 8 Go de RAM, sans GPU).
- **Ollama dans Docker avec peu de RAM** : sous Windows, Docker Desktop ne reçoit par défaut que la moitié de la RAM. Avec 8 Go au total (3,7 Go pour Docker), le conteneur Ollama n'arrive pas à charger le modèle → utiliser l'option B.

## Lancer en développement (sans Docker)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/Mac : source .venv/bin/activate)
pip install -r requirements-dev.txt
pip install -e .
uvicorn sql_agent.api.main:app --reload
```

Puis ouvrir http://localhost:8000/docs

## Tests et qualité

```bash
pytest          # tests + couverture
ruff check .    # style
mypy src        # typage
```

## Structure

```
src/sql_agent/
├── api/         API FastAPI (point d'entrée)
├── collector/   F1 – requêtes coûteuses (pg_stat_statements)
├── analyzer/    F2 – analyse des plans EXPLAIN
├── llm/         F3/F4 – explication + proposition (Ollama)
├── validator/   F5 – validation des index avec HypoPG
├── guardrails/  F6 – garde-fous + journal d'audit
└── config.py    configuration (variables d'environnement)
tests/           tests unitaires et d'intégration
docs/            fiche de cadrage, feuille de route, fiches de suivi
```
