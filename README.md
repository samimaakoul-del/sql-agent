# SQL Agent – agent d'optimisation PostgreSQL

Projet n°11 – un agent qui aide les développeurs et les DBA à **repérer, expliquer et corriger les requêtes SQL lentes, sans risquer d'abîmer la base de production**.

> 🚧 En construction – semaine 1 (squelette). Voir [la fiche de cadrage](docs/FICHE_CADRAGE.md) et [la feuille de route](docs/FEUILLE_DE_ROUTE.md).

## Équipe
- Ahmed Sami Maakoul
- Youssef Agoub

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
