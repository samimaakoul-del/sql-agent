-- Données de démo générées (déterministes grâce à setseed) :
--   100 000 clients, 5 000 produits, 1 000 000 commandes, 2 500 000 lignes de commande.
-- Durée : environ 1 à 3 minutes au premier démarrage.

SELECT setseed(0.42);

INSERT INTO customers (email, full_name, country, created_at)
SELECT 'client' || g || '@example.com',
       'Client ' || g,
       (ARRAY['MA','FR','ES','DE','US','BE','CA','IT'])[1 + floor(random() * 8)::int],
       now() - random() * interval '3 years'
FROM generate_series(1, 100000) AS g;

INSERT INTO products (name, category, price)
SELECT 'Produit ' || g,
       (ARRAY['livres','high-tech','maison','sport','mode','jouets',
              'beauté','jardin','auto','musique','bureau','animaux'])[1 + floor(random() * 12)::int],
       round((5 + random() * 495)::numeric, 2)
FROM generate_series(1, 5000) AS g;

INSERT INTO orders (customer_id, status, created_at, total)
SELECT 1 + floor(random() * 100000)::bigint,
       CASE WHEN r < 0.70 THEN 'delivered'
            WHEN r < 0.85 THEN 'shipped'
            WHEN r < 0.95 THEN 'pending'
            ELSE 'cancelled' END,
       now() - random() * interval '3 years',
       round((10 + random() * 490)::numeric, 2)
FROM (SELECT random() AS r FROM generate_series(1, 1000000)) AS t;

INSERT INTO order_items (order_id, product_id, quantity, unit_price)
SELECT 1 + floor(random() * 1000000)::bigint,
       1 + floor(random() * 5000)::bigint,
       1 + floor(random() * 5)::int,
       round((5 + random() * 495)::numeric, 2)
FROM generate_series(1, 2500000);

-- Clés étrangères ajoutées après le chargement (plus rapide).
-- Rappel : PostgreSQL ne crée PAS d'index automatiquement pour une clé étrangère.
ALTER TABLE orders      ADD FOREIGN KEY (customer_id) REFERENCES customers(id);
ALTER TABLE order_items ADD FOREIGN KEY (order_id)    REFERENCES orders(id);
ALTER TABLE order_items ADD FOREIGN KEY (product_id)  REFERENCES products(id);

-- Statistiques à jour pour que les plans EXPLAIN soient réalistes
ANALYZE;
