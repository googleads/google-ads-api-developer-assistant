---
name: validate-gaql
description: Validates Google Ads Query Language (GAQL) queries via 4-step static analysis and live API dry-runs.
---

# Validate GAQL Skill

Before presenting or running any GAQL query, pass this 4-step sequence:

1. **Schema Discovery:** Verify field existence, selectability, and filterability using `search_google_ads_fields`.
2. **Compatibility Check:** Verify all selected fields are compatible with the primary resource.
3. **Static Analysis:**
   - `WHERE` fields MUST be in `SELECT` (unless date segments).
   - **NO `OR` operator:** Replace `OR` with `IN` or split into multiple queries.
   - **NO `FROM` in Metadata:** Queries to `GoogleAdsFieldService` MUST NOT contain a `FROM` clause.
4. **Runtime Dry Run:** Execute API dry-run search request against target customer ID.
