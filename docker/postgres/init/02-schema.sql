-- Base de démo : une boutique en ligne.
--
-- IMPORTANT : seules les clés primaires sont indexées. Aucun index sur les clés
-- étrangères ni sur les colonnes de recherche (email, status, created_at...).
-- C'est voulu : ce sont les « index manquants » que l'agent doit trouver.

CREATE TABLE customers (
    id          bigserial PRIMARY KEY,
    email       text        NOT NULL,
    full_name   text        NOT NULL,
    country     char(2)     NOT NULL,
    created_at  timestamptz NOT NULL
);

CREATE TABLE products (
    id        bigserial PRIMARY KEY,
    name      text          NOT NULL,
    category  text          NOT NULL,
    price     numeric(10,2) NOT NULL
);

CREATE TABLE orders (
    id           bigserial PRIMARY KEY,
    customer_id  bigint        NOT NULL,
    status       text          NOT NULL,   -- delivered, shipped, pending, cancelled
    created_at   timestamptz   NOT NULL,
    total        numeric(10,2) NOT NULL
);

CREATE TABLE order_items (
    id          bigserial PRIMARY KEY,
    order_id    bigint        NOT NULL,
    product_id  bigint        NOT NULL,
    quantity    int           NOT NULL,
    unit_price  numeric(10,2) NOT NULL
);
