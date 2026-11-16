# Fiche de cadrage – Agent d'optimisation de base de données (Projet n°11)

> **Statut : brouillon v0.1** – à faire valider par l'enseignant. Une fois validée, cette fiche **fait référence** pour toute l'évaluation (A1). Tout changement de périmètre = avenant daté en bas de page, approuvé par l'enseignant.

| | |
|---|---|
| Équipe | 2 étudiants : AHMED SAMI MAAKOUL, YOUSSEF AGOUB |
| Durée | 3 semaines (L1 → L2 → L3) |
| Dépôt | `sql-agent` (GitHub, à créer) |

---

## 1. Problématique

**Comment un agent intelligent peut-il aider les développeurs et les DBA à repérer, expliquer et corriger les requêtes SQL lentes, sans risquer d'abîmer la base de production ?**

- **Acteurs** : développeurs back-end et DBA.
- **Problème concret** : requêtes lentes difficiles à trouver, plans `EXPLAIN` difficiles à lire.
- **Tension** : performance (ajouter des index, réécrire) **contre** risque (casser la prod, ralentir les écritures) ; automatisation **contre** contrôle humain.

### Sous-questions (= plan du compte rendu)
1. **Détecter** : comment repérer automatiquement les requêtes les plus coûteuses (statistiques `pg_stat_statements`) ?
2. **Expliquer** : comment interpréter un plan `EXPLAIN` pour trouver la cause (index manquant, jointure inefficace, parcours complet de table) ?
3. **Proposer** : comment proposer un index ou une réécriture vraiment utile, sans ralentir les écritures ?
4. **Protéger** : quels garde-fous pour que l'agent ne modifie jamais le schéma sans validation humaine ?

---

## 2. Périmètre

### Dans le MVP (obligatoire)
| # | Fonction | Description |
|---|---|---|
| F1 | Détection | Lister le top N des requêtes les plus coûteuses depuis `pg_stat_statements` (temps total, temps moyen, nb d'appels). |
| F2 | Analyse du plan | Lancer `EXPLAIN (FORMAT JSON)` (sans `ANALYZE` par défaut) et détecter par règles : *Seq Scan* sur grande table, jointure *Nested Loop* coûteuse, tri sur disque, filtre non indexé. |
| F3 | Explication | Le LLM (Ollama local) explique la cause en français clair, à partir du plan et des règles détectées. |
| F4 | Proposition | L'agent propose un `CREATE INDEX` et/ou une réécriture de requête. |
| F5 | Validation sans risque | Chaque index proposé est testé comme **index hypothétique (HypoPG)** : on compare le coût estimé avant/après **sans rien créer**. Une proposition n'est gardée que si le gain est ≥ 30 %. |
| F6 | Garde-fous | Connexion en **lecture seule**, filtre SQL (seuls `SELECT` / `EXPLAIN` sont exécutés), toute DDL reste « en attente » jusqu'à **validation humaine**, **journal d'audit** de toutes les actions. |
| F7 | Interface | Interface web : liste des requêtes lentes → détail (plan, explication, proposition, gain estimé) → bouton Approuver / Rejeter. |

### Hors périmètre (explicitement exclu)
- Agir sur une vraie base de production (on travaille sur une base de démo générée).
- Autres SGBD que PostgreSQL.
- Création automatique d'index sans validation.

### Extensions possibles (bonus, seulement si le MVP est complet)
- **E1** : génération de SQL à partir d'une question en langage naturel (avec le schéma en contexte).
- **E2** : estimation du coût d'un index sur les écritures (taille de l'index, nb d'`INSERT`/`UPDATE` sur la table).

---

## 3. Architecture

```
            ┌────────────────────────────── docker compose ──────────────────────────────┐
            │                                                                              │
 Utilisateur│  ┌───────────┐  HTTP   ┌──────────────────────────────┐   SQL lecture seule  │
 (dev / DBA)├─▶│ UI        │ ──────▶ │ API (FastAPI) = l'agent      │ ───────────────────▶ │ ┌──────────────┐
            │  │ Streamlit │ ◀────── │  1. Collecteur (F1)          │                      │ │ PostgreSQL 16│
            │  └───────────┘         │  2. Analyseur EXPLAIN (F2)   │ ◀─────────────────── │ │ + pg_stat_   │
            │                        │  3. Agent LLM (F3, F4)       │                      │ │   statements │
            │                        │  4. Validateur HypoPG (F5)   │                      │ │ + HypoPG     │
            │                        │  5. Garde-fous + audit (F6)  │                      │ │ base de démo │
            │                        └──────────────┬───────────────┘                      │ └──────────────┘
            │                                       │ HTTP                                 │
            │                                ┌──────▼──────┐                               │
            │                                │ Ollama      │  modèle : qwen2.5-coder       │
            │                                └─────────────┘                               │
            └──────────────────────────────────────────────────────────────────────────────┘
```

### Parcours d'une requête (exemple)
1. L'utilisateur ouvre l'UI → l'API lit `pg_stat_statements` et renvoie le top 10.
2. Il clique sur une requête → l'API passe le texte au **garde-fou** (doit être un `SELECT`), puis lance `EXPLAIN (FORMAT JSON)`.
3. L'**analyseur** trouve par exemple : « Seq Scan sur `orders` (2 M lignes), filtre sur `customer_id` ».
4. L'**agent LLM** reçoit plan + diagnostic + schéma de la table → renvoie une explication et `CREATE INDEX ON orders(customer_id)`.
5. Le **validateur** crée l'index *hypothétique* avec HypoPG, relance `EXPLAIN` : coût 45 000 → 12. Gain 99,9 % → proposition gardée.
6. La proposition est enregistrée « en attente » dans le **journal d'audit**. Rien n'est créé tant qu'un humain n'a pas cliqué « Approuver ».

### Choix techniques (à justifier dans le compte rendu, R2)
| Choix | Alternative écartée | Raison |
|---|---|---|
| PostgreSQL + HypoPG | MySQL | HypoPG permet de tester un index **sans le créer** → cœur de la promesse « sans abîmer la prod ». |
| Ollama local (qwen2.5-coder) | API Claude / OpenAI | Gratuit, aucune donnée envoyée à l'extérieur (schéma de la base reste privé), reproductible sans clé. |
| Règles + LLM | LLM seul | Les règles donnent un diagnostic fiable et testable ; le LLM sert à expliquer et proposer. Si le LLM est indisponible, les règles fonctionnent encore. |
| FastAPI + Streamlit | Django / React | Rapide à écrire en Python, API documentée automatiquement, UI simple. |

---

## 4. Critères de réussite mesurés (A3, R3)

Mesurés sur un **jeu de test de 30 requêtes lentes annotées** (cause attendue + index attendu) et **15 cas d'attaque** pour les garde-fous.

| Critère | Mesure | Cible L2 | Cible L3 |
|---|---|---|---|
| C1. Détection | Les 10 requêtes injectées comme lentes apparaissent dans le top 15 | ≥ 7/10 | 10/10 |
| C2. Diagnostic | Cause trouvée = cause annotée | ≥ 60 % | ≥ 85 % |
| C3. Index utile | Index proposé avec gain HypoPG ≥ 30 % | ≥ 50 % | ≥ 80 % |
| C4. SQL valide | Propositions syntaxiquement valides (parsées par PostgreSQL) | ≥ 80 % | ≥ 95 % |
| C5. Garde-fous | Cas d'attaque bloqués (`DROP`, `DELETE`, injection dans un commentaire, etc.) | 100 % | 100 % |
| C6. Temps | Analyse complète d'une requête | < 60 s | < 30 s |

---

## 5. Scénarios

- **Principal** : top requêtes → analyse → explication → index validé par HypoPG → approbation humaine → journalisé.
- **Dégradés** (doivent être gérés, A2) :
  - Ollama indisponible → diagnostic par règles seul + message clair.
  - Requête non-`SELECT` soumise → refusée et journalisée.
  - SQL invalide renvoyé par le LLM → détecté, une nouvelle tentative, puis abandon propre.
  - Base inaccessible → erreur claire, pas de plantage.
  - Aucune requête lente → message « rien à optimiser ».

---

## 6. Planning et livrables

| Semaine | Livrable | Preuve demandée |
|---|---|---|
| **L1** – cadrage + squelette | Fiche validée ; `docker compose up` lance Postgres (avec données de démo), Ollama, API, UI ; F1 affiche le top des requêtes. | Démo de 3 min en séance |
| **L2** – MVP mesuré | F1 → F7 fonctionnels ; jeu de test de 30 requêtes ; premiers chiffres C1–C6. | 3 cas du jeu de test tirés au hasard |
| **L3** – version finale | Cibles L3 visées, tests + CI au vert, README, compte rendu (6 p.), diapositives. **Tout dans le dépôt 48 h avant.** | Clone sur machine vierge, une commande |

## 7. Répartition des rôles

| AHMED SAMI MAAKOUL | YOUSSEF AGOUB |
|---|---|
| Base de démo + générateur de requêtes lentes | Agent LLM (prompts, Ollama) |
| Collecteur (F1) + analyseur EXPLAIN (F2) | Garde-fous + journal d'audit (F6) |
| Validateur HypoPG (F5) | Interface Streamlit (F7) |
| Script d'évaluation (C1–C6) | Docker, CI GitHub Actions |

Chacun écrit les tests de ses modules et relit les pull requests de l'autre.

## 8. Risques

| Risque | Parade |
|---|---|
| Ollama trop lent sur CPU | Modèle plus petit (`qwen2.5-coder:3b`), cache des réponses |
| Le LLM invente des colonnes | Le schéma réel est fourni dans le prompt + vérification avant HypoPG |
| HypoPG non disponible dans l'image Postgres | Image Docker personnalisée (Dockerfile) |

---

## Avenants
*(aucun pour l'instant)*
