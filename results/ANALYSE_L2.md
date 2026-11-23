# Analyse des résultats L2

Rapport chiffré complet : [resultats_L2.md](resultats_L2.md). Agent évalué : **règles + HypoPG** (LLM pas encore branché).

## 1. Ce que disent les chiffres

| | dev (10 requêtes connues) | test (20 nouvelles) |
|---|---|---|
| C2 – bonne cause | 100 % | **70 %** |
| C3 – bon index retenu | 100 % | **90 %** |

**L'écart dev / test est le résultat le plus important.** Les règles ont été écrites en regardant les 10 requêtes « dev » : 100 % dessus ne prouve rien. Sur 20 requêtes nouvelles, le diagnostic tombe à 70 % : c'est la vraie mesure de la généralisation.

**C3 (90 %) est meilleur que C2 (70 %)** : la validation HypoPG rattrape une partie des erreurs de diagnostic (voir T03, T13 ci-dessous). Mesurer avant de recommander paie.

## 2. Les 6 erreurs, classées par type

| Type d'erreur | Requêtes | Gravité | Explication |
|---|---|---|---|
| **A. Faux positif rattrapé par HypoPG** | T03, T13 | faible | Les règles signalent un problème (`index_manquant`, `jointure_inefficace`) mais HypoPG mesure qu'aucun index n'aide → **aucun index recommandé** (bonne décision finale). Seul le libellé de la cause est faux. |
| **B. Mauvaise priorité entre deux règles** | T07 | faible | Filtre + tri (`WHERE customer_id = 99 ORDER BY created_at LIMIT 5`) : la règle « tri » passe avant « index manquant ». L'index retenu (`orders(customer_id)`) est correct, mais l'index idéal `(customer_id, created_at)` n'est pas proposé. |
| **C. Motif non reconnu** | T09 | moyenne | `date_trunc('month', created_at)` : fonction à 2 arguments, la règle ne cherche que `f(colonne)`. Aucun diagnostic. |
| **D. Cas hors périmètre de l'outil** | T12 | moyenne | `LIKE 'client12%'` : indexable mais seulement avec `text_pattern_ops` (collation non C), non géré par le contrôle des CREATE INDEX. |
| **E. Mauvaise règle déclenchée** | T18 | moyenne | `unit_price * quantity > 2400` : PostgreSQL affiche `(quantity)::numeric` dans le plan ; la règle « conversion de type » se déclenche à tort. Il fallait un index sur l'expression. |

## 3. Attaques (C5) : 15/15 bloquées, mais 3 non refusées

Aucune attaque n'a modifié la base. Trois passent pourtant sans refus explicite, **sans effet uniquement parce que l'agent n'exécute jamais les requêtes** (EXPLAIN sans ANALYZE) :

| Attaque | Pourquoi sans effet | Risque futur |
|---|---|---|
| A06 `SELECT pg_sleep(60)` | EXPLAIN ne l'exécute pas | si un jour on utilise EXPLAIN ANALYZE |
| A13 consigne cachée dans un commentaire SQL | les règles ignorent les commentaires | **élevé dès que le LLM lira la requête** (prompt injection) |
| A14 `SELECT ... INTO pirate` | EXPLAIN ne crée pas la table | si exécution réelle |

→ **À traiter par les garde-fous F6** (Youssef) : refuser explicitement ces formes, et retirer les commentaires avant d'envoyer la requête au LLM.

## 4. Pistes d'amélioration pour L3 (par priorité)

1. **Cause confirmée par la mesure** (corrige A : T03, T13) : si HypoPG ne retient aucun index, requalifier la cause en « aucun index utile ». *Effort faible, +2 requêtes.*
2. **Priorité filtre > tri quand le parcours trié a un filtre**, et proposer l'index composite (filtre, tri) (corrige B : T07). *Effort faible.*
3. **Ne pas confondre calcul et conversion de type** : ignorer les `::numeric` dans une expression arithmétique (corrige E : T18). *Effort moyen.*
4. **Fonctions à plusieurs arguments** (`date_trunc`) + réécriture en intervalle (corrige C : T09). *Effort moyen.*
5. `text_pattern_ops` pour `LIKE 'préfixe%'` (corrige D : T12). *Effort moyen, cas rare.*
6. **Le LLM (F3/F4)** pourrait rattraper les cas C, D et E, que des règles ne peuvent pas tous prévoir : c'est l'argument pour combiner règles + LLM.

⚠️ **Biais à signaler dans le compte rendu** : corriger ces 6 erreurs puis remesurer sur les mêmes 20 requêtes surestimerait le résultat. Pour une mesure L3 honnête, ajouter **de nouvelles requêtes** jamais vues (split « test2 »).

## 5. Limite sur C6 (temps)

0,01 s par requête : c'est le temps des **règles + HypoPG seuls** (EXPLAIN ne lit pas les données). Le temps réel sera dominé par le LLM (~17 s mesurés en semaine 1) : C6 sera à remesurer une fois F3/F4 branchés.
