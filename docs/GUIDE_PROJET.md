# Guide du projet – tout ce qu'il faut savoir

> Document de référence pour l'équipe (Ahmed Sami Maakoul, Youssef Agoub). À garder à jour.

---

## 1. Le projet en 30 secondes

**Projet n°11 – Agent de gestion de base de données.**
Un agent qui aide les développeurs et les DBA à **repérer, expliquer et corriger les requêtes SQL lentes, sans risquer d'abîmer la base de production**.

L'agent fait 4 choses :
1. **Détecter** les requêtes les plus coûteuses (`pg_stat_statements`).
2. **Expliquer** pourquoi elles sont lentes (lecture du plan `EXPLAIN` + explication par un LLM).
3. **Proposer** un index ou une réécriture, **testé sans rien créer** (HypoPG).
4. **Protéger** la base : lecture seule, filtre SQL, validation humaine, journal d'audit.

Documents de référence : [Fiche de cadrage](FICHE_CADRAGE.md) · [Feuille de route](FEUILLE_DE_ROUTE.md)

---

## 2. Comment on est noté (100 points)

| Partie | Points | Quand | Ce qui compte |
|---|---|---|---|
| Fiches de suivi | 25 | chaque semaine (5 + 10 + 10) | livrable démontré, fiche honnête, contribution par membre |
| Application finale | 20 | semaine 3 | respect du cadrage (3), bout en bout (7), qualité mesurée (6), garde-fous (4) |
| Dépôt GitHub | 20 | semaine 3 | tests + typage (6), Docker + CI (5), doc (4), commits de chacun (5) |
| Soutenance | 20 | semaine 3 | démo en direct (6), réponses (5, **individuel**), architecture (4), résultats (4), forme (1) |
| Compte rendu | 15 | semaine 3 | **6 pages max** ; 1/3 de la note = résultats chiffrés |

**Note individuelle** = (travail d'équipe /80) × **coefficient de contribution (0,6 à 1,1)** + soutenance /20.
Le coefficient est fixé avec : la fiche de suivi, **les commits / PR de chacun sur GitHub**, une co-évaluation confidentielle.

### Quatre niveaux par critère
Insuffisant (0–25 %) · Passable (50 %) · Bien (75 %) · Excellent (100 %).

### Les 4 règles à ne pas oublier
1. **La fiche de cadrage fait référence** : tout changement de périmètre doit être approuvé par l'enseignant (avenant).
2. **Tout doit être dans le dépôt 48 h avant la soutenance** : code, tests, README, Dockerfile, fiches, résultats chiffrés, compte rendu, diapositives.
3. Bonus jusqu'à **2 points** pour une extension réussie, **seulement si le MVP est complet**.
4. (À 2, pas d'exigence supplémentaire de composant.)

### Ce qui fait perdre des points
- Code monolithique, sans tests
- Application impossible à installer hors de notre PC
- README absent ou inutilisable
- **Un seul membre qui commite** / commits groupés à la fin
- Démo **enregistrée** au lieu d'en direct (S2 plafonné à Passable)

---

## 3. Calendrier

| Semaine | Livrable | Preuve en séance | Points |
|---|---|---|---|
| **S1 – L1** | Cadrage + squelette qui tourne | Démo de **3 minutes** | Fiche 1 : 5 |
| **S2 – L2** | MVP mesuré | **3 cas du jeu de test tirés au hasard** | Fiche 2 : 10 |
| **S3 – L3** | Version déployée, évaluée, soutenue | **Clone sur machine vierge, une commande** | 85 |

Soutenance à 2 : **20 min** = 12 min de démo + 8 min de questions. **Chacun doit répondre seul à au moins une question.**

---

## 4. Répartition des rôles

| Ahmed Sami | Youssef |
|---|---|
| Base de démo + générateur de requêtes lentes | Agent LLM (prompts, Ollama) – F3/F4 |
| Collecteur F1 (`collector/`) | Garde-fous + journal d'audit F6 (`guardrails/`) |
| Analyseur EXPLAIN F2 (`analyzer/`) | Interface Streamlit F7 (`ui/`) |
| Validateur HypoPG F5 (`validator/`) | Docker, CI GitHub Actions |
| Script d'évaluation (C1–C6) | |

**Règle d'or** : chacun commite **son** code depuis **son** compte GitHub, et relit les PR de l'autre.

---

## 5. Où en est-on ?

| Étape | État |
|---|---|
| 1.1 Fiche de cadrage | ✅ rédigée – ⏳ **à faire valider par l'enseignant** |
| 1.2 Dépôt GitHub | ✅ créé – ⏳ inviter Youssef, protéger `main` |
| 1.3 Squelette Python | ✅ (structure, API `/health`, tests, ruff, mypy) |
| 1.4 Docker | ✅ branche `feat/docker` – ⏳ **ouvrir la PR, relecture Youssef** |
| 1.5 Base de démo + requêtes lentes | ⏭️ prochaine étape (Ahmed Sami) |
| 1.6 F1 : top des requêtes dans l'UI | à faire |
| 1.7 CI GitHub Actions | à faire (Youssef) |
| 1.8 Fiche de suivi n°1 | à faire |

---

## 6. Architecture

```
Utilisateur ──▶ UI Streamlit (8501) ──▶ API FastAPI = l'agent (8000) ──▶ PostgreSQL 16 (5433)
                                          │  collector  (F1)              + pg_stat_statements
                                          │  analyzer   (F2)              + HypoPG
                                          │  llm        (F3/F4) ──▶ Ollama (qwen2.5-coder:3b)
                                          │  validator  (F5)
                                          └  guardrails (F6)   connexion : rôle agent_ro (LECTURE SEULE)
```

### Structure du code
```
sql-agent/
├── src/sql_agent/
│   ├── api/main.py      point d'entrée FastAPI
│   ├── collector/       F1
│   ├── analyzer/        F2
│   ├── llm/             F3/F4
│   ├── validator/       F5
│   ├── guardrails/      F6
│   ├── ui/app.py        F7 (Streamlit)
│   └── config.py        configuration (variables d'environnement)
├── tests/               tests pytest
├── docker/postgres/     image Postgres + script d'init (extensions, rôle agent_ro)
├── docs/                fiche de cadrage, feuille de route, fiches de suivi, ce guide
├── Dockerfile           image API + UI
├── docker-compose.yml   toute la stack
├── requirements*.txt    dépendances figées
└── .env.example         modèle de configuration
```

---

## 7. Informations techniques utiles

### Adresses
| Quoi | Adresse |
|---|---|
| Interface | http://localhost:8501 (si page blanche : http://127.0.0.1:8501) |
| API + documentation | http://localhost:8000/docs |
| Dépôt GitHub | https://github.com/samimaakoul-del/sql-agent |

### Connexions à la base (base de démo uniquement, mots de passe de test)
| Rôle | Utilisation | Droits |
|---|---|---|
| `admin` / `admin` | création des données, administration | tous |
| `agent_ro` / `agent_ro` | **l'agent** | lecture seule (+ HypoPG) |

Base : `shop` · Port PC : `5433` (le 5432 est pris par un PostgreSQL local sur le PC d'Ahmed Sami).

### Choix du LLM
| Machine | Mode | Commande |
|---|---|---|
| PC avec peu de RAM (ex. 8 Go) | **Option B** : Ollama installé sur le PC | `.env` : `OLLAMA_URL=http://host.docker.internal:11434` puis `docker compose up -d --build` |
| PC puissant / machine vierge | **Option A** : tout dans Docker | `docker compose --profile ollama up -d --build` |

Modèle : `qwen2.5-coder:3b`. Mesure sur le PC d'Ahmed Sami (CPU, pas de GPU) : **17 s** modèle chargé, **59 s** au premier appel.

---

## 8. Commandes de tous les jours

### Docker
```bash
docker compose up -d --build        # lancer / reconstruire
docker compose ps                   # état des services
docker compose logs -f api          # voir les logs d'un service
docker compose down                 # arrêter (les données restent)
docker compose down -v              # arrêter ET effacer la base (repartir de zéro)
docker compose exec db psql -U admin -d shop    # console SQL
```

### Python (hors Docker)
```bash
.venv\Scripts\activate              # activer l'environnement (Windows)
pytest                              # tests + couverture
ruff check .                        # style
mypy src                            # typage
uvicorn sql_agent.api.main:app --reload
```

### Git : le cycle à suivre pour CHAQUE tâche
```bash
git switch main
git pull                            # récupérer le travail de l'autre
git switch -c feat/nom-de-la-tache  # nouvelle branche
# ... coder, tester ...
git add -A
git commit -m "feat(collector): top des requêtes lentes"
git push -u origin feat/nom-de-la-tache
```
Puis sur GitHub : **ouvrir une pull request → l'autre membre relit → fusion**.

Préfixes de commit : `feat` (fonction), `fix` (correction), `test`, `docs`, `chore` (outillage).

---

## 9. Les notions à maîtriser (questions probables du jury)

| Notion | En une phrase |
|---|---|
| **Index** | Structure (souvent un arbre B-tree) qui permet de trouver des lignes sans lire toute la table. Accélère les lectures, **ralentit les écritures** et prend de la place. |
| **`pg_stat_statements`** | Extension PostgreSQL qui enregistre, pour chaque forme de requête, le nombre d'appels et le temps total/moyen. Sert à trouver les plus coûteuses. |
| **`EXPLAIN`** | Montre le **plan** choisi par PostgreSQL et son coût estimé, **sans exécuter** la requête. `EXPLAIN ANALYZE` l'exécute vraiment (plus précis, mais risqué). |
| **Seq Scan** | Parcours complet de la table, ligne par ligne. Normal sur une petite table, signe d'index manquant sur une grosse. |
| **Index Scan** | Utilise un index pour aller directement aux lignes utiles. |
| **Nested Loop / Hash Join** | Deux façons de faire une jointure. Un Nested Loop sur de grosses tables sans index est très lent. |
| **HypoPG** | Extension qui crée des index **hypothétiques** : PostgreSQL fait comme s'ils existaient dans `EXPLAIN`, mais rien n'est créé sur le disque. → On mesure le gain **sans risque**. |
| **Rôle lecture seule** | L'agent se connecte avec `agent_ro` : toute écriture est refusée par PostgreSQL lui-même, même si le LLM se trompe. |
| **Ollama / LLM local** | Le modèle tourne sur notre machine : gratuit, aucune donnée envoyée à l'extérieur. |
| **Règles + LLM** | Les règles (code Python) donnent un diagnostic fiable et testable ; le LLM explique et propose. Si le LLM tombe, les règles fonctionnent encore. |

---

## 10. Les mesures à produire (cœur de la note)

Jeu de test : **30 requêtes lentes annotées** (cause + index attendus) et **15 cas d'attaque**.

| Critère | Cible L2 | Cible L3 |
|---|---|---|
| C1. Les 10 requêtes lentes injectées sont dans le top 15 | ≥ 7/10 | 10/10 |
| C2. Bon diagnostic | ≥ 60 % | ≥ 85 % |
| C3. Index utile (gain HypoPG ≥ 30 %) | ≥ 50 % | ≥ 80 % |
| C4. SQL proposé valide | ≥ 80 % | ≥ 95 % |
| C5. Attaques bloquées | 100 % | 100 % |
| C6. Temps d'analyse | < 60 s | < 30 s |

À montrer : **la progression entre L2 et L3**, et **l'analyse des erreurs** (pourquoi l'agent s'est trompé).

---

## 11. Modèle de fiche de suivi (une par semaine)

```markdown
# Fiche de suivi – Semaine N

## Livrable prévu / livrable obtenu
- Prévu : ...
- Obtenu : ...   (démontré en séance : oui/non)

## Écarts et pourquoi
- ...

## Blocages (et quand ils ont été signalés)
- ...

## Résultats chiffrés (à partir de S2)
| Critère | Valeur |
|---|---|

## Contribution par membre (doit correspondre aux commits / PR)
| Membre | Tâches | Commits / PR |
|---|---|---|
| Ahmed Sami | ... | #... |
| Youssef | ... | #... |

## Plan de la semaine suivante
- ...
```

Une fiche **honnête** (écarts expliqués, blocages signalés à temps) rapporte plus qu'une fiche parfaite.

---

## 12. Dépannage

| Problème | Solution |
|---|---|
| `docker: cannot connect to the docker API` | Ouvrir Docker Desktop, attendre « Engine running » |
| Port déjà utilisé | Changer `DB_PORT` / `API_PORT` / `UI_PORT` dans `.env` |
| Page Streamlit blanche | Utiliser http://127.0.0.1:8501 |
| LLM très lent ou bloqué dans Docker | Passer en option B (Ollama du PC) ou modèle `qwen2.5-coder:1.5b` |
| Les scripts d'init de la base ne se relancent pas | Ils ne tournent qu'à la création : `docker compose down -v` puis `up` |
| `git push` refusé sur `main` | Normal (branche protégée) : passer par une branche + pull request |

---

## 13. Check-list avant la soutenance (J-2)

- [ ] Tout est fusionné sur `main`, CI au vert
- [ ] Test sur une **machine vierge** : `git clone` + une commande
- [ ] README complet (installation, architecture, limites)
- [ ] Résultats chiffrés L2 et L3 dans le dépôt
- [ ] Compte rendu (6 pages max) dans le dépôt
- [ ] Diapositives dans le dépôt
- [ ] 3 fiches de suivi à jour
- [ ] Démo répétée et chronométrée (12 min), **en direct** sur l'application conteneurisée
- [ ] Plan B si le LLM est lent : modèle déjà chargé avant la démo (faire un premier appel)
- [ ] Chacun sait expliquer **toute** l'architecture, pas seulement sa partie
