# Google Ads API Developer Assistant - Conversion Troubleshooting Guide

## Metadata
- **Version:** 3.0.0
- **Role:** Technical Reference for AI Assistant
- **Optimized for:** Machine Comprehension

---

This document provides the targeted diagnostic workflow for troubleshooting offline conversion uploads. 

### 1. Core Directive & Workspace Rules
For all global rules, hard constraints, tech stack guidelines, GAQL validation sequence, Python linting protocols, and workspace isolation compliance, **you MUST strictly adhere to the master [AGENTS.md](../AGENTS.md)** configuration at the repository root.

---

### 2. Conversion Troubleshooting Workflow [MANDATORY]

When troubleshooting offline conversion imports, upload client summaries, or upload action alerts:

1. **Statically Validate Conversion Files**:
   Before any conversion upload is attempted or simulated, programmatically validate formatting, GCLID integrity, and date fields using the `troubleshoot-conversions` validation tool:
   ```bash
   ./.venv/bin/python3 .agents/skills/troubleshoot_conversions/scripts/validate_conversion_upload.py --csv_path <path_to_csv> --api_version <api_version>
   ```

2. **Retrieve Account & Action Diagnostics**:
   Execute the primary diagnostic collector script inside the sequestered virtual environment:
   ```bash
   ./.venv/bin/python3 .agents/skills/troubleshoot_conversions/scripts/troubleshoot_conversions.py --customer_id <customer_id> --api_version <api_version>
   ```

3. **Analyze and Report**:
   * Read the consolidated diagnostic output written to `saved/data/conversion_troubleshooting_report_<epoch>.txt`.
   * Cross-reference results with historical diagnostics to check for persistent trends.
   * Present a concise summary of the findings, highlight critical alert codes (e.g. `EXPIRED_CLICK`, `CLICK_NOT_FOUND`), and propose concrete remediation steps.