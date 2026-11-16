# Feuille de route – alignée sur la grille d'évaluation (100 points)

Chaque étape ci-dessous coche un ou plusieurs critères de la grille. On avance **une étape à la fois**, on la teste, on commit, puis on passe à la suivante.

## Semaine 1 – L1 : cadrage + squelette qui tourne (Fiche 1 : 5 pts)

| Étape | Contenu | Critères visés |
|---|---|---|
| 1.1 | Fiche de cadrage rédigée → **validée par l'enseignant** | A1, R1 |
| 1.2 | Dépôt GitHub créé, les 2 membres invités, branche `main` protégée (PR obligatoire) | D4 |
| 1.3 | Structure du projet Python (`src/`, `tests/`, `pyproject.toml`, dépendances figées) | D1, D2 |
| 1.4 | `docker-compose.yml` : Postgres + pg_stat_statements + HypoPG, Ollama, API, UI | D2 |
| 1.5 | Base de démo (tables `customers`, `orders`, `products`…, ~1 M lignes) + script qui génère du trafic lent | A3 |
| 1.6 | F1 : endpoint `/slow-queries` + page UI qui affiche le top | A2 |
| 1.7 | CI GitHub Actions (lint + tests) au vert dès le début | D1, D2 |
| 1.8 | Fiche de suivi n°1 remplie (honnête, contributions par membre) | F1, F2, F3 |
| ✅ | **Démo 3 min** : `docker compose up` → top des requêtes lentes affiché | |

## Semaine 2 – L2 : MVP mesuré (Fiche 2 : 10 pts)

| Étape | Contenu | Critères visés |
|---|---|---|
| 2.1 | F2 : analyseur EXPLAIN par règles + tests unitaires | A2, D1 |
| 2.2 | F6 : garde-fous (filtre SQL, rôle lecture seule) + journal d'audit + 15 cas d'attaque | A4 |
| 2.3 | F3/F4 : agent LLM (Ollama) – explication + proposition | A3 |
| 2.4 | F5 : validateur HypoPG (gain avant/après) | A3, A4 |
| 2.5 | F7 : UI complète avec Approuver / Rejeter | A2, A4 |
| 2.6 | Jeu de test : 30 requêtes annotées + script `evaluate.py` → tableau C1–C6 | A3, R3 |
| 2.7 | Scénarios dégradés gérés (Ollama coupé, SQL invalide, base coupée) | A2 |
| 2.8 | Fiche de suivi n°2 avec **les premiers chiffres** | F1–F3 |
| ✅ | **Preuve** : 3 cas tirés au hasard du jeu de test passent en direct | |

## Semaine 3 – L3 : version déployée, évaluée, soutenue (85 pts)

| Étape | Contenu | Critères visés |
|---|---|---|
| 3.1 | Améliorer les résultats (prompts, règles) → nouveaux chiffres, **progression L2 → L3** | A3, R3 |
| 3.2 | Couverture de tests mesurée (`pytest-cov`), typage (`mypy`) | D1 |
| 3.3 | Test « machine vierge » : `git clone` + `docker compose up` sur un autre PC | D2 |
| 3.4 | README complet + schéma d'architecture + section Limites | D3 |
| 3.5 | Compte rendu (6 pages max) : problème, choix vs alternative, résultats chiffrés, limites priorisées | R1–R5 |
| 3.6 | Diapositives + répétition chronométrée (12 min démo + 8 min questions) | S1–S5 |
| 3.7 | Extension bonus E1 (langage naturel → SQL) **si le MVP est complet** | Bonus |
| 3.8 | Fiche de suivi n°3 | F1–F3 |
| ⚠️ | **Tout dans le dépôt 48 h avant la soutenance** | |

## Règles à respecter tout au long du projet

- **Commits réguliers de chacun, sur sa partie** (pas de gros commit à la fin) → D4, coefficient individuel.
- **Chaque PR est relue par l'autre membre** avant fusion → D4.
- **Fiche de suivi remplie chaque semaine**, écarts et blocages signalés honnêtement → F2.
- **Démo en direct sur l'application conteneurisée** (une démo enregistrée plafonne S2 à Passable).
- En soutenance, **chaque membre répond seul à au moins une question** → S4 (individuel).
