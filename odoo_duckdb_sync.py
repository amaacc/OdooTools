import os
import sys
import json
import time
import xmlrpc.client
from datetime import datetime
import duckdb

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "odoo_sync_config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def parse_many2one(val):
    if isinstance(val, (list, tuple)) and len(val) >= 2:
        return val[0], str(val[1])
    elif isinstance(val, (list, tuple)) and len(val) == 1:
        return val[0], ""
    elif isinstance(val, int):
        return val, ""
    return None, ""

def init_duckdb(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = duckdb.connect(db_path)
    
    con.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY,
            product_tmpl_id INTEGER,
            default_code VARCHAR,
            barcode VARCHAR,
            name VARCHAR,
            product_name_arabic VARCHAR,
            display_name VARCHAR,
            active BOOLEAN,
            detailed_type VARCHAR,
            categ_id INTEGER,
            category_name VARCHAR,
            list_price DOUBLE,
            standard_price DOUBLE,
            qty_available DOUBLE,
            virtual_available DOUBLE,
            free_qty DOUBLE,
            incoming_qty DOUBLE,
            outgoing_qty DOUBLE,
            uom_id INTEGER,
            uom_name VARCHAR,
            sfda_number VARCHAR,
            branch_id INTEGER,
            x_studio_concatenated_tags VARCHAR,
            create_date VARCHAR,
            write_date VARCHAR,
            last_sync_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    con.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            sync_id INTEGER PRIMARY KEY,
            sync_type VARCHAR,
            start_time TIMESTAMP,
            end_time TIMESTAMP,
            duration_seconds DOUBLE,
            records_processed INTEGER,
            records_updated INTEGER,
            status VARCHAR,
            error_message VARCHAR
        );
    """)

    con.execute("""
        CREATE SEQUENCE IF NOT EXISTS sync_log_seq START 1;
    """)

    return con

def get_last_write_date(con):
    try:
        res = con.execute("SELECT MAX(write_date) FROM products").fetchone()
        if res and res[0]:
            return res[0]
    except Exception as e:
        print(f"Notice: Could not fetch last write_date: {e}")
    return None

def upsert_records(con, records):
    if not records:
        return 0

    rows = []
    for r in records:
        cat_id, cat_name = parse_many2one(r.get('categ_id'))
        uom_id, uom_name = parse_many2one(r.get('uom_id'))
        tmpl_id, _ = parse_many2one(r.get('product_tmpl_id'))
        branch_id, _ = parse_many2one(r.get('branch_id'))

        rows.append((
            r.get('id'),
            tmpl_id,
            r.get('default_code') or '',
            r.get('barcode') or '',
            r.get('name') or '',
            r.get('product_name_arabic') or '',
            r.get('display_name') or '',
            bool(r.get('active')),
            r.get('detailed_type') or r.get('type') or '',
            cat_id,
            cat_name,
            float(r.get('list_price') or 0.0),
            float(r.get('standard_price') or 0.0),
            float(r.get('qty_available') or 0.0),
            float(r.get('virtual_available') or 0.0),
            float(r.get('free_qty') or 0.0),
            float(r.get('incoming_qty') or 0.0),
            float(r.get('outgoing_qty') or 0.0),
            uom_id,
            uom_name,
            r.get('sfda_number') or '',
            branch_id,
            str(r.get('x_studio_concatenated_tags') or ''),
            str(r.get('create_date') or ''),
            str(r.get('write_date') or '')
        ))

    upsert_sql = """
        INSERT INTO products (
            id, product_tmpl_id, default_code, barcode, name, product_name_arabic,
            display_name, active, detailed_type, categ_id, category_name, list_price,
            standard_price, qty_available, virtual_available, free_qty, incoming_qty,
            outgoing_qty, uom_id, uom_name, sfda_number, branch_id, x_studio_concatenated_tags,
            create_date, write_date, last_sync_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, now())
        ON CONFLICT(id) DO UPDATE SET
            product_tmpl_id = EXCLUDED.product_tmpl_id,
            default_code = EXCLUDED.default_code,
            barcode = EXCLUDED.barcode,
            name = EXCLUDED.name,
            product_name_arabic = EXCLUDED.product_name_arabic,
            display_name = EXCLUDED.display_name,
            active = EXCLUDED.active,
            detailed_type = EXCLUDED.detailed_type,
            categ_id = EXCLUDED.categ_id,
            category_name = EXCLUDED.category_name,
            list_price = EXCLUDED.list_price,
            standard_price = EXCLUDED.standard_price,
            qty_available = EXCLUDED.qty_available,
            virtual_available = EXCLUDED.virtual_available,
            free_qty = EXCLUDED.free_qty,
            incoming_qty = EXCLUDED.incoming_qty,
            outgoing_qty = EXCLUDED.outgoing_qty,
            uom_id = EXCLUDED.uom_id,
            uom_name = EXCLUDED.uom_name,
            sfda_number = EXCLUDED.sfda_number,
            branch_id = EXCLUDED.branch_id,
            x_studio_concatenated_tags = EXCLUDED.x_studio_concatenated_tags,
            create_date = EXCLUDED.create_date,
            write_date = EXCLUDED.write_date,
            last_sync_date = now();
    """

    con.executemany(upsert_sql, rows)
    return len(rows)

def run_sync():
    config = load_config()
    
    url = os.environ.get("ODOO_URL") or config.get("odoo_url")
    db = os.environ.get("ODOO_DB") or config.get("odoo_db")
    username = os.environ.get("ODOO_EMAIL") or config.get("odoo_email")
    password = os.environ.get("ODOO_PASSWORD") or config.get("default_password")
    db_path = config.get("duckdb_path", "c:\\OdooDB\\odoo_products.duckdb")
    batch_size = config.get("batch_size", 2000)
    fields_to_sync = config.get("fields_to_sync", [])

    if not url or not db or not username or not password:
        print("ERROR: Odoo credentials missing. Set ODOO_URL, ODOO_DB, ODOO_EMAIL, ODOO_PASSWORD environment variables or config file.")
        sys.exit(1)

    print("==================================================")
    print("      Odoo 17 Enterprise -> DuckDB Sync Tool      ")
    print("==================================================")
    print(f"Odoo URL: {url}")
    print(f"Odoo DB : {db}")
    print(f"User    : {username}")
    print(f"DuckDB  : {db_path}")

    start_time = datetime.now()
    t0 = time.time()
    con = init_duckdb(db_path)

    last_write = get_last_write_date(con)
    if last_write:
        sync_type = "Incremental"
        domain = [['write_date', '>', last_write], ['active', 'in', [True, False]]]
        print(f"\nMode: INCREMENTAL (Syncing products modified after {last_write})")
    else:
        sync_type = "Full"
        domain = [['active', 'in', [True, False]]]
        print("\nMode: FULL SYNC (Initial load of all products)")

    try:
        common = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/common')
        uid = common.authenticate(db, username, password, {})
        if not uid:
            raise ValueError("Authentication to Odoo failed! Check username/password.")

        models = xmlrpc.client.ServerProxy(f'{url}/xmlrpc/2/object')
        
        print("Searching matching product IDs in Odoo...")
        product_ids = models.execute_kw(db, uid, password, 'product.product', 'search', [domain])
        total_found = len(product_ids)
        print(f"Found {total_found} products to sync.")

        total_upserted = 0
        if total_found > 0:
            for i in range(0, total_found, batch_size):
                chunk_ids = product_ids[i:i + batch_size]
                chunk_num = (i // batch_size) + 1
                total_chunks = (total_found + batch_size - 1) // batch_size
                print(f"Fetching batch {chunk_num}/{total_chunks} ({len(chunk_ids)} records)...")
                
                records = models.execute_kw(
                    db, uid, password, 'product.product', 'read',
                    [chunk_ids],
                    {'fields': fields_to_sync}
                )
                
                count = upsert_records(con, records)
                total_upserted += count
                print(f"Batch {chunk_num} saved to DuckDB. Total synced so far: {total_upserted}/{total_found}")

        t1 = time.time()
        duration = round(t1 - t0, 2)
        end_time = datetime.now()

        # Record log
        log_sql = """
            INSERT INTO sync_log (
                sync_id, sync_type, start_time, end_time, duration_seconds,
                records_processed, records_updated, status, error_message
            ) VALUES (
                nextval('sync_log_seq'), ?, ?, ?, ?, ?, ?, 'SUCCESS', ''
            )
        """
        con.execute(log_sql, (sync_type, start_time, end_time, duration, total_found, total_upserted))

        total_in_db = con.execute("SELECT COUNT(*) FROM products").fetchone()[0]

        # Automatic Export to Excel and CSV
        export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
        os.makedirs(export_dir, exist_ok=True)
        excel_path = os.path.join(export_dir, "odoo_products_latest.xlsx")
        csv_path = os.path.join(export_dir, "odoo_products_latest.csv")

        print("Exporting latest data to CSV & Excel...")
        try:
            con.execute(f"COPY products TO '{csv_path.replace('\\', '/')}' (HEADER, DELIMITER ',');")
            print(f"CSV Export saved: {csv_path}")
            
            # Export to Excel using pandas
            df_export = con.execute("SELECT * FROM products ORDER BY id DESC").df()
            df_export.to_excel(excel_path, index=False, engine='openpyxl')
            print(f"Excel Export saved: {excel_path}")
        except Exception as export_err:
            print(f"Warning: Export failed: {export_err}")

        print("\n==================================================")
        print("             SYNC COMPLETED SUCCESSFULLY          ")
        print("==================================================")
        print(f"Sync Type        : {sync_type}")
        print(f"Synced Records   : {total_upserted}")
        print(f"Total Products DB: {total_in_db}")
        print(f"Duration         : {duration} seconds")
        print("==================================================\n")

    except Exception as e:
        t1 = time.time()
        duration = round(t1 - t0, 2)
        end_time = datetime.now()
        err_msg = str(e)
        print(f"\nERROR DURING SYNC: {err_msg}")

        try:
            log_sql = """
                INSERT INTO sync_log (
                    sync_id, sync_type, start_time, end_time, duration_seconds,
                    records_processed, records_updated, status, error_message
                ) VALUES (
                    nextval('sync_log_seq'), ?, ?, ?, ?, 0, 0, 'FAILED', ?
                )
            """
            con.execute(log_sql, (sync_type, start_time, end_time, duration, err_msg))
        except Exception:
            pass

        con.close()
        sys.exit(1)

    con.close()

if __name__ == "__main__":
    run_sync()
