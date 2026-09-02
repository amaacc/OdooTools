import os
import time
import duckdb
import pandas as pd

def export_duckdb_to_excel():
    db_path = r"c:\OdooDB\odoo_products.duckdb"
    export_dir = r"c:\OdooDB\exports"
    excel_path = os.path.join(export_dir, "odoo_products_latest.xlsx")
    csv_path = os.path.join(export_dir, "odoo_products_latest.csv")
    
    os.makedirs(export_dir, exist_ok=True)
    
    print(f"Connecting to DuckDB database: {db_path}...")
    con = duckdb.connect(db_path)
    
    t0 = time.time()
    print("Reading products table from DuckDB...")
    df = con.execute("SELECT * FROM products ORDER BY id DESC").df()
    print(f"Loaded {len(df)} rows into memory in {round(time.time() - t0, 2)} seconds.")
    
    # Exporting CSV first (lightning fast for large datasets)
    t1 = time.time()
    print(f"Exporting to CSV: {csv_path}...")
    df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"CSV export completed in {round(time.time() - t1, 2)} seconds.")
    
    # Exporting Excel .xlsx
    t2 = time.time()
    print(f"Exporting to Excel: {excel_path}...")
    df.to_excel(excel_path, index=False, engine='openpyxl')
    print(f"Excel export completed in {round(time.time() - t2, 2)} seconds.")
    
    con.close()
    
    print("\n==================================================")
    print("           EXCEL EXPORT SUCCESSFUL!               ")
    print("==================================================")
    print(f"Excel File: {excel_path}")
    print(f"CSV File  : {csv_path}")
    print(f"Total Rows: {len(df)}")
    print("==================================================")

if __name__ == "__main__":
    export_duckdb_to_excel()
