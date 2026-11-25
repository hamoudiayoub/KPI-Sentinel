-- Gives explicit names to the table-level CHECK constraints, which PostgreSQL had named
-- <table>_check, <table>_check1… Explicit names make violations readable in error messages
-- and in data quality reports.

ALTER TABLE erp.sales_reps RENAME CONSTRAINT sales_reps_check TO sales_reps_left_after_hired_check;
ALTER TABLE erp.customers RENAME CONSTRAINT customers_check TO customers_closed_after_opened_check;
ALTER TABLE erp.promotions RENAME CONSTRAINT promotions_check TO promotions_ends_after_starts_check;
ALTER TABLE erp.orders RENAME CONSTRAINT orders_check TO orders_cancelled_has_timestamp_check;
ALTER TABLE erp.orders RENAME CONSTRAINT orders_check1 TO orders_delivered_has_timestamp_check;
ALTER TABLE erp.order_lines RENAME CONSTRAINT order_lines_check TO order_lines_gross_equals_quantity_times_price_check;
ALTER TABLE erp.order_lines RENAME CONSTRAINT order_lines_check1 TO order_lines_discount_within_gross_check;
ALTER TABLE erp.deliveries RENAME CONSTRAINT deliveries_check TO deliveries_delivered_has_timestamp_check;
