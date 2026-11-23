# Démo semaine 1 (3 minutes) – « squelette qui tourne »

**Avant la séance** (5 min) : ouvrir Docker Desktop, puis
```bash
docker compose up -d --build
docker compose run --rm workload
```
Ouvrir http://localhost:8501 (ou http://127.0.0.1:8501) et http://localhost:8000/docs.

---

## Déroulé

| Temps | On montre | On dit |
|---|---|---|
| 0:00 – 0:30 | La fiche de cadrage | « Problématique : repérer, expliquer et corriger les requêtes lentes **sans abîmer la prod**. » |
| 0:30 – 1:00 | `docker compose ps` | « Toute l'application se lance en **une commande** : base PostgreSQL avec HypoPG, API, interface. » |
| 1:00 – 1:30 | Terminal : `docker compose run --rm workload` | « Base de démo : **1 million de commandes**. On simule une application avec 10 requêtes lentes connues et 8 rapides. » |
| 1:30 – 2:30 | L'interface (F1) | « L'agent lit `pg_stat_statements` : les **10 requêtes lentes sont aux 10 premières places**. On peut classer par coût total ou par coût moyen. » |
| 2:30 – 3:00 | Terminal : écriture refusée (ci-dessous) | « Garde-fou n°1 : l'agent se connecte en **lecture seule**. Même s'il se trompe, PostgreSQL refuse toute modification. » |

Commande pour le dernier point :
```bash
docker compose exec -e PGPASSWORD=agent_ro db psql -h localhost -U agent_ro -d shop -c "DROP TABLE orders"
```
Résultat attendu : `ERROR: cannot execute DROP TABLE in a read-only transaction`

## Questions possibles
- *Pourquoi les valeurs sont-elles remplacées par `$1` ?* → pg_stat_statements regroupe les requêtes de même forme ; pour l'analyse on utilisera `EXPLAIN (GENERIC_PLAN)` (PostgreSQL 16).
- *Pourquoi un LLM local ?* → gratuit, aucune donnée de la base envoyée à l'extérieur.
- *Et la suite ?* → semaine 2 : analyse des plans EXPLAIN, explication par le LLM, test des index avec HypoPG.
