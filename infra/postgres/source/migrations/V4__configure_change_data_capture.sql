-- Change data capture: what Debezium needs to stream the ERP, and nothing more.

-- Full "before" image on UPDATE and DELETE, to analyze status transitions and stock movements.
-- The other tables only need their primary key in the "before" image (the default).
ALTER TABLE erp.orders REPLICA IDENTITY FULL;
ALTER TABLE erp.inventory REPLICA IDENTITY FULL;

-- Explicit table list: a table added later is only captured once it is added here on purpose.
CREATE PUBLICATION sentinel_pub FOR TABLE
    erp.regions, erp.cities, erp.warehouses, erp.sales_reps, erp.customers,
    erp.brands, erp.categories, erp.products, erp.price_changes, erp.promotions,
    erp.orders, erp.order_lines, erp.deliveries, erp.returns, erp.inventory;

-- Debezium connects with this role: it may replicate and read, never write.
CREATE ROLE debezium WITH LOGIN REPLICATION PASSWORD '${debezium_password}';
GRANT CONNECT ON DATABASE atlas TO debezium;
GRANT USAGE ON SCHEMA erp TO debezium;
GRANT SELECT ON ALL TABLES IN SCHEMA erp TO debezium;
