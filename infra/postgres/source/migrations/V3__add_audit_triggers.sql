-- Keeps updated_at current on every UPDATE, so changed rows are easy to find.

CREATE FUNCTION erp.set_updated_at() RETURNS trigger
    LANGUAGE plpgsql AS
$$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DO $$
DECLARE
    table_name text;
BEGIN
    FOR table_name IN
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'erp' AND c.relkind = 'r'
    LOOP
        EXECUTE format(
            'CREATE TRIGGER set_updated_at BEFORE UPDATE ON erp.%I '
            'FOR EACH ROW EXECUTE FUNCTION erp.set_updated_at()',
            table_name
        );
    END LOOP;
END;
$$;
