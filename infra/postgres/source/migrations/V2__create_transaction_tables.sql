-- Transactions of the simulated ERP: orders and their lines, deliveries, returns, stock.
-- Amounts are numeric(12, 2) in MAD; timestamps are timestamptz, stored in UTC.

CREATE TABLE erp.orders (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    customer_id    bigint NOT NULL REFERENCES erp.customers (id),
    sales_rep_id   bigint REFERENCES erp.sales_reps (id),
    warehouse_id   bigint NOT NULL REFERENCES erp.warehouses (id),
    channel        text NOT NULL
        CHECK (channel IN ('TRADITIONAL', 'MODERN_TRADE', 'HORECA', 'ECOMMERCE')),
    status         text NOT NULL DEFAULT 'PLACED'
        CHECK (status IN ('PLACED', 'CONFIRMED', 'SHIPPED', 'DELIVERED', 'CANCELLED')),
    placed_at      timestamptz NOT NULL,
    confirmed_at   timestamptz,
    shipped_at     timestamptz,
    delivered_at   timestamptz,
    cancelled_at   timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    CHECK (status <> 'CANCELLED' OR cancelled_at IS NOT NULL),
    CHECK (status <> 'DELIVERED' OR delivered_at IS NOT NULL)
);

-- gross_amount is stored, not generated: generated columns are not published by default.
CREATE TABLE erp.order_lines (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id         uuid NOT NULL REFERENCES erp.orders (id) ON DELETE CASCADE,
    line_number      integer NOT NULL CHECK (line_number > 0),
    product_id       bigint NOT NULL REFERENCES erp.products (id),
    promotion_id     bigint REFERENCES erp.promotions (id),
    quantity         integer NOT NULL CHECK (quantity > 0),
    unit_price       numeric(12, 2) NOT NULL CHECK (unit_price >= 0),
    gross_amount     numeric(12, 2) NOT NULL CHECK (gross_amount >= 0),
    discount_amount  numeric(12, 2) NOT NULL DEFAULT 0 CHECK (discount_amount >= 0),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    UNIQUE (order_id, line_number),
    CHECK (gross_amount = quantity * unit_price),
    CHECK (discount_amount <= gross_amount)
);

CREATE TABLE erp.deliveries (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id         uuid NOT NULL UNIQUE REFERENCES erp.orders (id) ON DELETE CASCADE,
    warehouse_id     bigint NOT NULL REFERENCES erp.warehouses (id),
    promised_on      date NOT NULL,
    status           text NOT NULL DEFAULT 'SCHEDULED'
        CHECK (status IN ('SCHEDULED', 'IN_TRANSIT', 'DELIVERED', 'FAILED')),
    shipped_at       timestamptz,
    delivered_at     timestamptz,
    delivered_units  integer NOT NULL DEFAULT 0 CHECK (delivered_units >= 0),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    CHECK (status <> 'DELIVERED' OR delivered_at IS NOT NULL)
);

CREATE TABLE erp.returns (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id     uuid NOT NULL REFERENCES erp.orders (id) ON DELETE CASCADE,
    product_id   bigint NOT NULL REFERENCES erp.products (id),
    quantity     integer NOT NULL CHECK (quantity > 0),
    amount       numeric(12, 2) NOT NULL CHECK (amount >= 0),
    reason       text NOT NULL
        CHECK (reason IN ('DAMAGED', 'EXPIRED', 'WRONG_ITEM', 'CUSTOMER_REFUSAL', 'OTHER')),
    returned_at  timestamptz NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now()
);

-- Current stock per warehouse and product; every movement is an UPDATE of the row.
CREATE TABLE erp.inventory (
    warehouse_id      bigint NOT NULL REFERENCES erp.warehouses (id),
    product_id        bigint NOT NULL REFERENCES erp.products (id),
    quantity_on_hand  integer NOT NULL CHECK (quantity_on_hand >= 0),
    reorder_point     integer NOT NULL DEFAULT 0 CHECK (reorder_point >= 0),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (warehouse_id, product_id)
);

CREATE INDEX ON erp.orders (customer_id);
CREATE INDEX ON erp.orders (sales_rep_id);
CREATE INDEX ON erp.orders (warehouse_id);
CREATE INDEX ON erp.orders (placed_at);
CREATE INDEX ON erp.orders (status);
CREATE INDEX ON erp.order_lines (product_id);
CREATE INDEX ON erp.order_lines (promotion_id);
CREATE INDEX ON erp.deliveries (warehouse_id);
CREATE INDEX ON erp.deliveries (promised_on);
CREATE INDEX ON erp.returns (order_id);
CREATE INDEX ON erp.returns (product_id);
CREATE INDEX ON erp.returns (returned_at);
CREATE INDEX ON erp.inventory (product_id);
