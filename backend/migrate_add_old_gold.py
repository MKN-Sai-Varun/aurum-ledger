#!/usr/bin/env python3
"""Migration script to add old_gold_purchases table to existing database.

This script is safe to run multiple times - it checks if the table exists first.
"""
import sys
from sqlalchemy import text

from app.db import engine


def table_exists(engine, table_name: str) -> bool:
    """Check if a table exists in the database."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
            ),
            {"table_name": table_name},
        )
        return result.fetchone() is not None


def create_old_gold_table(engine):
    """Create the old_gold_purchases table and related objects."""
    
    # Check if table already exists
    if table_exists(engine, "old_gold_purchases"):
        print("✓ Table 'old_gold_purchases' already exists. No migration needed.")
        return
    
    print("Creating 'old_gold_purchases' table...")
    
    with engine.begin() as conn:
        # Create the table
        conn.execute(text("""
            CREATE TABLE old_gold_purchases (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                og_no VARCHAR(20) NOT NULL UNIQUE,
                entry_date DATE NOT NULL,
                bill_no VARCHAR(50) NOT NULL,
                customer_name VARCHAR(100) NOT NULL,
                gross_mg INTEGER NOT NULL,
                deduction_mg INTEGER NOT NULL,
                purity_hundredths INTEGER NOT NULL,
                fine_mg INTEGER NOT NULL,
                rate_paise INTEGER NOT NULL,
                value_paise INTEGER NOT NULL,
                payment_mode VARCHAR(20) NOT NULL,
                pan VARCHAR(20),
                note VARCHAR(500),
                created_by INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(created_by) REFERENCES users (id),
                CHECK (payment_mode IN ('CASH', 'ONLINE', 'CHEQUE')),
                CHECK (gross_mg > 0),
                CHECK (deduction_mg >= 0),
                CHECK (purity_hundredths BETWEEN 0 AND 10000),
                CHECK (fine_mg >= 0),
                CHECK (rate_paise > 0),
                CHECK (value_paise >= 0)
            )
        """))
        
        # Create index
        conn.execute(text("""
            CREATE INDEX ix_old_gold_purchases_entry_date 
            ON old_gold_purchases (entry_date)
        """))
        
        # Create trigger to prevent updates
        conn.execute(text("""
            CREATE TRIGGER tr_old_gold_purchases_no_update
            BEFORE UPDATE ON old_gold_purchases
            BEGIN
                SELECT RAISE(ABORT, 'old_gold_purchases is append-only');
            END
        """))
        
        # Create trigger to prevent deletes
        conn.execute(text("""
            CREATE TRIGGER tr_old_gold_purchases_no_delete
            BEFORE DELETE ON old_gold_purchases
            BEGIN
                SELECT RAISE(ABORT, 'old_gold_purchases is append-only');
            END
        """))
    
    print("✓ Successfully created 'old_gold_purchases' table")
    print("✓ Created index on entry_date")
    print("✓ Created triggers to enforce append-only constraint")


if __name__ == "__main__":
    try:
        print("Starting migration...")
        print(f"Database: {engine.url}")
        create_old_gold_table(engine)
        print("\n✓ Migration completed successfully!")
    except Exception as e:
        print(f"\n✗ Migration failed: {e}", file=sys.stderr)
        sys.exit(1)
