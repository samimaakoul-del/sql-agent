-- Exécuté une seule fois, à la création de la base.

-- Extensions nécessaires à l'agent
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;  -- F1 : statistiques des requêtes
CREATE EXTENSION IF NOT EXISTS hypopg;              -- F5 : index hypothétiques

-- Garde-fou F6 : l'agent se connecte avec un rôle en LECTURE SEULE.
-- Il peut lire les données et les statistiques, mais ne peut rien modifier.
CREATE ROLE agent_ro LOGIN PASSWORD 'agent_ro';
GRANT pg_read_all_data  TO agent_ro;   -- SELECT sur toutes les tables (pour EXPLAIN)
GRANT pg_read_all_stats TO agent_ro;   -- lecture de pg_stat_statements
ALTER ROLE agent_ro SET default_transaction_read_only = on;
