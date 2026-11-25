-- Reference data of the simulated ERP: geography, sales organization, customers, catalog.
-- Identifiers are bigint identities; every table keeps created_at and updated_at, and
-- updated_at is maintained by the erp.set_updated_at() trigger (V3).

CREATE TABLE erp.regions (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        text NOT NULL UNIQUE,
    name        text NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE erp.cities (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    region_id   bigint NOT NULL REFERENCES erp.regions (id),
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    UNIQUE (region_id, name)
);

CREATE TABLE erp.warehouses (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code        text NOT NULL UNIQUE,
    name        text NOT NULL,
    city_id     bigint NOT NULL REFERENCES erp.cities (id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE erp.sales_reps (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code          text NOT NULL UNIQUE,
    full_name     text NOT NULL,
    warehouse_id  bigint NOT NULL REFERENCES erp.warehouses (id),
    hired_on      date NOT NULL,
    left_on       date,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (left_on IS NULL OR left_on >= hired_on)
);

CREATE TABLE erp.customers (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code          text NOT NULL UNIQUE,
    name          text NOT NULL,
    channel       text NOT NULL
        CHECK (channel IN ('TRADITIONAL', 'MODERN_TRADE', 'HORECA', 'ECOMMERCE')),
    city_id       bigint NOT NULL REFERENCES erp.cities (id),
    sales_rep_id  bigint REFERENCES erp.sales_reps (id),
    warehouse_id  bigint NOT NULL REFERENCES erp.warehouses (id),
    opened_on     date NOT NULL,
    closed_on     date,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (closed_on IS NULL OR closed_on >= opened_on)
);

CREATE TABLE erp.brands (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE erp.categories (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        text NOT NULL UNIQUE,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE erp.products (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku          text NOT NULL UNIQUE,
    name         text NOT NULL,
    brand_id     bigint NOT NULL REFERENCES erp.brands (id),
    category_id  bigint NOT NULL REFERENCES erp.categories (id),
    pack_size    text NOT NULL,
    list_price   numeric(12, 2) NOT NULL CHECK (list_price >= 0),
    is_active    boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- Price history: the price in effect on a date is the latest row with effective_from <= date.
CREATE TABLE erp.price_changes (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id      bigint NOT NULL REFERENCES erp.products (id),
    effective_from  date NOT NULL,
    list_price      numeric(12, 2) NOT NULL CHECK (list_price >= 0),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (product_id, effective_from)
);

-- A promotion applies to one product, optionally restricted to one channel.
CREATE TABLE erp.promotions (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id    bigint NOT NULL REFERENCES erp.products (id),
    channel       text
        CHECK (channel IN ('TRADITIONAL', 'MODERN_TRADE', 'HORECA', 'ECOMMERCE')),
    starts_on     date NOT NULL,
    ends_on       date NOT NULL,
    discount_pct  numeric(5, 2) NOT NULL CHECK (discount_pct > 0 AND discount_pct <= 100),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    CHECK (ends_on >= starts_on)
);

CREATE INDEX ON erp.cities (region_id);
CREATE INDEX ON erp.warehouses (city_id);
CREATE INDEX ON erp.sales_reps (warehouse_id);
CREATE INDEX ON erp.customers (city_id);
CREATE INDEX ON erp.customers (sales_rep_id);
CREATE INDEX ON erp.customers (warehouse_id);
CREATE INDEX ON erp.products (brand_id);
CREATE INDEX ON erp.products (category_id);
CREATE INDEX ON erp.price_changes (product_id, effective_from);
CREATE INDEX ON erp.promotions (product_id);
CREATE INDEX ON erp.promotions (starts_on, ends_on);
