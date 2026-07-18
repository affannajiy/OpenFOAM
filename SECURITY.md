# Security Policy

## Supported Versions

Only the latest released installer (`OpenFOAM_UI_Setup_<version>.exe`) is supported with fixes.

## Reporting a Vulnerability

Please **do not open a public issue** for security problems. Instead email **affannajiy@gmail.com** with:

- What you found and where (file / feature / installer step)
- Steps to reproduce
- Impact as you understand it

You should get a reply within a week. Please give reasonable time for a fix before disclosing publicly.

## Scope Notes

- The launcher can run **elevated commands** (`wsl --install`, WSL updates) — always via a visible Windows UAC prompt, never silently.
- The setup step installs packages **only via `apt`** from official Ubuntu/OpenFOAM repositories; no pip, no scripts fetched from third-party hosts.
- The app itself runs unbundled Python inside your WSL distro; it does not open network ports and only touches your case folders, `%TEMP%` logs/sentinels, and `~/.openfoam_ui_recents.json`.
