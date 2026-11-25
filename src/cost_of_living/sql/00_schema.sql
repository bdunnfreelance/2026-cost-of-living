-- Schemas and persistent tables. Safe to run repeatedly.
-- extract   = raw landing data, no logic
-- transform = cleaned tables and the enriched view
-- present   = what reports and exports read

CREATE SCHEMA IF NOT EXISTS extract;
CREATE SCHEMA IF NOT EXISTS transform;
CREATE SCHEMA IF NOT EXISTS present;

CREATE TABLE IF NOT EXISTS extract.imported_files (
    sha256 VARCHAR PRIMARY KEY,
    source_name VARCHAR NOT NULL,
    imported_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    row_count BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS extract.transactions_raw (
    source_sha256 VARCHAR NOT NULL,
    source_name VARCHAR NOT NULL,
    row_number BIGINT NOT NULL,
    record JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS transform.transactions (
    source_sha256 VARCHAR NOT NULL,
    source_name VARCHAR NOT NULL,
    row_number BIGINT NOT NULL,
    -- Every source row is loaded. Blank or unreadable values are stored as NULL and described
    -- in data_issue (NULL = no problem), which is exported as the Data Status column.
    bank VARCHAR,
    account VARCHAR,
    transaction_date DATE,
    description VARCHAR,
    debit DECIMAL(18, 2),
    credit DECIMAL(18, 2),
    amount DECIMAL(18, 2),
    balance DECIMAL(18, 2),
    category VARCHAR,
    subcategory VARCHAR,
    data_issue VARCHAR,
    PRIMARY KEY (source_sha256, row_number)
);

-- Reference tables. Category names on mappings intentionally aren't foreign keys.
CREATE TABLE IF NOT EXISTS transform.budget_categories (
    payment_category VARCHAR PRIMARY KEY,
    category_group VARCHAR,
    cash_flow VARCHAR,
    comment VARCHAR
);

CREATE TABLE IF NOT EXISTS transform.manual_category_mappings (
    account VARCHAR NOT NULL,
    description VARCHAR NOT NULL,
    payment_category VARCHAR NOT NULL,
    PRIMARY KEY (account, description)
);

-- rule_id is the final priority order: Payee/Payer rules first, then Vendor Type,
-- each in sheet row order. Lower rule_id wins.
CREATE TABLE IF NOT EXISTS transform.mapping_rules (
    rule_id BIGINT PRIMARY KEY,
    rule_priority INTEGER NOT NULL,
    rule_type VARCHAR NOT NULL,
    match_text VARCHAR NOT NULL,
    payment_category VARCHAR NOT NULL,
    comment VARCHAR
);

-- Run log, so the `status` command can tell what has been done and what is out of date.
CREATE TABLE IF NOT EXISTS extract.reference_loads (
    load_id BIGINT PRIMARY KEY,
    loaded_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    workbook_name VARCHAR NOT NULL,
    workbook_mtime DOUBLE NOT NULL,       -- file modified time (epoch seconds) when loaded
    categories BIGINT NOT NULL,
    manual_mappings BIGINT NOT NULL,
    rules BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS extract.export_log (
    export_id BIGINT PRIMARY KEY,
    exported_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    parquet_name VARCHAR NOT NULL,
    transaction_rows BIGINT NOT NULL,
    imported_file_count BIGINT NOT NULL,  -- bank files imported at export time
    reference_load_id BIGINT              -- reference load used (NULL if none recorded)
);
