# Cost of Living Project — Handover

## Goal

Build a simple, local-first family cost-of-living and financial analysis project. Bank transactions are downloaded as CSV files. The user wants to analyse them with pivot-style summaries and charts, and ideally update the data with a desktop shortcut or a simple script.

## Decisions so far

- Prioritise getting a working version quickly on Windows. Linux/Kubuntu portability can be revisited later.
- Recommended stack: Python for CSV import/cleanup, DuckDB for a file-based database, and Power BI Desktop for pivots/charts.
- DuckDB was selected because it stores data in a local database file and runs in-process rather than requiring a continuously running database server.
- Power BI Desktop reports can be kept local. Do not publish them to Power BI Service because publishing uploads report/model data.
- Keep code in Git and back that up to a private cloud repository if desired. Keep financial data out of cloud sync and Git.
- The project and data locations should be distinct. The user initially planned `C:\Dev\2026 CostOfLiving` and `C:\Dev\2026 CostOfLiving\data`; remind them that if `data` is inside the Git project, it must be excluded from Git, and a separate local-only data folder is safer.

## Current environment and progress

- Project folder: `C:\Dev\2026 CostOfLiving`
- VS Code is now opened in a local Windows window, not a WSL remote window.
- VS Code integrated terminal is PowerShell and prompt is `PS C:\Dev\2026 CostOfLiving>`.
- Git is installed: `git version 2.54.0.windows.1`.
- A local Git repository was initialized successfully with `git init`.
- Python is installed: `Python 3.13.5` (`py --version` worked).
- The user has Codex available as a plug-in in VS Code and asked whether it can perform setup steps. Advice was yes: ask it to make one limited change at a time, review commands, and keep bank data out of Git.
- A PowerShell `while ($true) { Clear-Host; Get-Date; ollama ps; Start-Sleep -Seconds 1 }` loop appeared in the terminal. The user was instructed to stop it with Ctrl+C before continuing. It is unrelated to this project setup; confirm the terminal is back at the prompt if necessary.

## Guidance for continuing

The user asked for instructions one step at a time and will say “next step” when ready. Continue in that cadence; do not provide a long batch of setup steps.

Suggested next steps:

1. Confirm the terminal is at the PowerShell prompt and the Ollama loop has stopped.
2. Create a Python virtual environment: `py -m venv .venv`.
3. Add `.venv/`, data, DuckDB database files, and generated report/export files to `.gitignore` before committing anything. Do not put sensitive values or financial records in tracked files.
4. Activate the environment in PowerShell: `\.venv\Scripts\Activate.ps1` (if execution policy blocks this, use a session-scoped workaround or VS Code Python interpreter selection rather than changing machine-wide policy).
5. Create a minimal Python project and install only the needed packages (initially likely `duckdb`; add other packages when the import/report workflow requires them).
6. Create a private GitHub repository and connect it as `origin` only after reviewing `git status` and `.gitignore` to ensure there are no transaction files, database files, or sensitive reports staged.
7. Later, configure Power BI Desktop to read DuckDB through the DuckDB ODBC driver and Power Query ODBC connector. Align 64-bit/32-bit driver and Power BI installations.
8. Build a repeatable CSV import that tracks processed files and handles duplicate/re-downloaded transactions safely. Power BI’s imported model will also need refreshing after the database load.

## Security notes

- Never commit bank CSVs, the `.duckdb` database, Power BI reports containing imported transaction data, or exports containing transaction data.
- A `.gitignore` is a useful guard, not proof that a secret was never committed. Review `git status` and staged diffs before every push.
- Keep sensitive data outside OneDrive/Dropbox/other synced folders if the goal is no cloud copy.
- Do not publish the Power BI report to the Power BI Service. Keep visual assets and any extensions local; network activity can vary by tool and feature, so strict no-egress requirements need firewall/network controls.
- Back up the local database separately to a secure offline location; cloud-backup only the code and non-sensitive documentation.

## Handover note

This file contains project context, not financial data. Continue by helping the user one step at a time from the current setup, and verify each step with them before advancing.
