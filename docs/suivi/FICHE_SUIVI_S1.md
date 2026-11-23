# Fiche de suivi – Semaine 1 (L1 : cadrage + squelette qui tourne)

| | |
|---|---|
| Équipe | Ahmed Sami Maakoul, Youssef Agoub |
| Période | 16/11/2026 → 23/11/2026 |
| Dépôt | https://github.com/samimaakoul-del/sql-agent |

> ⚠️ **À compléter avant de rendre** : les lignes marquées ✏️.

---

## 1. Livrable prévu / livrable obtenu

**Prévu (fiche de cadrage, §6)** : fiche validée ; `docker compose up` lance Postgres (avec données de démo), Ollama, API, UI ; F1 affiche le top des requêtes.

| Élément prévu | État | Preuve |
|---|---|---|
| Fiche de cadrage | ✅ rédigée – ✏️ validée par l'enseignant le __/__ (ou : en attente) | `docs/FICHE_CADRAGE.md` |
| Squelette Python (modules F1–F6, tests, ruff, mypy strict) | ✅ | commit `30e71f5` |
| Stack Docker en une commande (Postgres + pg_stat_statements + HypoPG, API, UI) | ✅ | commits `1ee99de`, `33bbfa1` |
| Ollama dans Docker | ⚠️ partiel – voir écarts | `docker-compose.yml` (profil `ollama`) |
| Base de démo + requêtes lentes | ✅ | commit `e953205` |
| F1 : top des requêtes dans l'interface | ✅ | commit `648a608` |
| Démo de 3 minutes | ✏️ faite en séance le __/__ : oui / non | `docs/DEMO_S1.md` |

**En plus du prévu** : garde-fou « lecture seule » déjà en place et testé (rôle `agent_ro` + lecture seule forcée à la connexion) ; scénario dégradé « base injoignable » géré (erreur 503 avec message clair).

---

## 2. Résultats mesurés (premiers chiffres)

| Mesure | Résultat |
|---|---|
| Lancement de la stack | 1 commande (`docker compose up -d --build`) |
| Chargement de la base de démo (3,6 M lignes) | 37 s |
| Requêtes lentes du catalogue (temps moyen) | 8 à 105 ms |
| Requêtes rapides du catalogue (temps moyen) | 0,01 à 0,3 ms |
| **C1 – les 10 requêtes lentes dans le top 15** | **10/10** (rangs 1 à 10) – cible L3 déjà atteinte |
| Écriture par l'agent (`CREATE TABLE`, `DROP TABLE`) | refusée par PostgreSQL ✅ |
| Index hypothétique HypoPG avec le rôle lecture seule | autorisé ✅ |
| LLM `qwen2.5-coder:3b` sur CPU (Ollama du PC) | 17 s modèle chargé, 59 s au premier appel |
| Tests | 16/16 (dont 4 d'intégration sur la vraie base) |
| Couverture de code | 86 % |

---

## 3. Écarts et pourquoi

1. **Ollama ne fonctionne pas dans Docker sur le PC d'Ahmed Sami.**
   - Constat : le conteneur Ollama n'arrive pas à charger le modèle, même le plus petit (1,5b) ; il reste bloqué en « loading model ».
   - Cause : PC à 7,7 Go de RAM sans GPU ; Docker Desktop n'en reçoit que 3,7 Go.
   - Solution adoptée : deux modes, chacun en une commande. **Option A** (tout dans Docker, `--profile ollama`) pour une machine plus puissante ; **option B** (Ollama installé sur le PC, joint par `host.docker.internal`). Documenté dans le README (section Limites).
   - Conséquence : le modèle par défaut passe de `qwen2.5-coder:7b` à `qwen2.5-coder:3b` (parade prévue dans la fiche, §8). ✏️ Si l'enseignant le demande, à déclarer en avenant.

2. **`pg_stat_statements` remplace les constantes par `$1`, `$2`…**
   - Conséquence pour la semaine 2 : on ne peut pas lancer `EXPLAIN` directement sur ces requêtes. Solution prévue : `EXPLAIN (GENERIC_PLAN)` (PostgreSQL 16).

3. **Classement par temps total ou par temps moyen.**
   - Les requêtes lentes n°9 et n°10 (≈ 40 ms au total) sont juste devant une requête rapide très fréquente (35 ms au total). Avec plus de trafic rapide, elles pourraient passer derrière. → L'interface propose les deux classements ; limite à analyser dans le compte rendu.

4. **Les pull requests ne sont pas encore fusionnées.**
   - Le travail est sur 3 branches empilées (`feat/docker` → `feat/demo-db` → `feat/collector`). La PR #1 est ouverte et attend la relecture de Youssef. `main` ne contient pour l'instant que le squelette.

5. **La CI GitHub Actions (étape 1.7) n'est pas faite.** Reportée en début de semaine 2 (Youssef).

---

## 4. Blocages

| Blocage | Signalé le | Résolu ? |
|---|---|---|
| Ollama dans Docker bloqué (RAM insuffisante) | 16/11 | ✅ oui, contourné (option B) le 16/11 |
| Docker Desktop ne démarre pas tout seul après redémarrage du PC | 23/11 | ✅ oui (lancement manuel, noté dans le guide) |
| ✏️ Relecture des PR en attente | __/__ | ✏️ |

---

## 5. Contribution par membre

> Doit correspondre à l'historique GitHub (commits et pull requests).

| Membre | Tâches réalisées | Commits / PR |
|---|---|---|
| **Ahmed Sami Maakoul** | Fiche de cadrage, feuille de route, squelette, stack Docker, base de démo et catalogue de requêtes, collecteur F1 + route API, guide du projet, script de démo | 7 commits (`30e71f5` → `648a608`), auteur de la PR #1 |
| **Youssef Agoub** | ✏️ (ex. : relecture de la fiche de cadrage, relecture de la PR #1, test de la stack sur son PC…) | ✏️ 0 commit à ce jour |

**Écart de contribution assumé** : cette semaine, l'essentiel du code a été écrit par Ahmed Sami, y compris des parties prévues pour Youssef (Docker, interface minimale) pour pouvoir présenter une démo complète. **Rééquilibrage prévu en semaine 2** : Youssef prend en charge la CI, l'agent LLM (F3/F4), les garde-fous (F6) et l'interface (F7), depuis son propre compte GitHub.

✏️ Outils : un assistant IA (Claude) a été utilisé pour aider à écrire le code et la documentation ; tout a été relu, testé et exécuté par l'équipe. *(Phrase à garder ou adapter selon les règles du cours : les commits portent la mention « Co-Authored-By: Claude ».)*

---

## 6. Plan de la semaine 2 (L2 : MVP mesuré)

| Tâche | Responsable |
|---|---|
| Relire et fusionner les 3 PR de la semaine 1 | Youssef relit, Ahmed Sami fusionne |
| CI GitHub Actions (lint, mypy, tests) au vert | Youssef |
| F2 : analyseur EXPLAIN par règles (`EXPLAIN (GENERIC_PLAN)`) | Ahmed Sami |
| F6 : filtre SQL + journal d'audit + 15 cas d'attaque | Youssef |
| F3/F4 : agent LLM (réponse JSON stricte : explication + index) | Youssef |
| F5 : validateur HypoPG (gain avant/après) | Ahmed Sami |
| F7 : page détail + boutons Approuver / Rejeter | Youssef |
| Jeu de test étendu à 30 requêtes + script d'évaluation C1–C6 | Ahmed Sami |

**Objectif mesurable fin de semaine 2** : cibles L2 de la fiche (C2 ≥ 60 %, C3 ≥ 50 %, C4 ≥ 80 %, C5 = 100 %, C6 < 60 s) et 3 cas tirés au hasard qui passent en direct.
