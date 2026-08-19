---
description: Retrieves all child customer account IDs (CIDs) under a Manager Account (MCC).
argument-description: <mcc_customer_id> The Manager Account ID (MCC) to query
---

# Get CIDs Under MCC (`/get-cids`)

Retrieves the complete account hierarchy and child CIDs under a Google Ads Manager Account (MCC).

## Instructions:
1. **Extract Parameters**:
   - Extract the Manager Account ID (MCC) from `$ARGUMENTS`.
   - If not provided, check `config/customer_id.txt` or prompt the user.
   - Resolve API version from `config/api_version.txt`.

2. **Execute Retrieval**:
   - Run the hierarchy retrieval script:
     ```bash
     python3 skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py --customer_id "<mcc_customer_id>" --api_version "<api_version>" --print_cids
     ```
   - If the user requested saving to CSV:
     ```bash
     python3 skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py --customer_id "<mcc_customer_id>" --api_version "<api_version>" --save_csv
     ```

3. **Output Format**:
   - Total number of child accounts found.
   - Hierarchical list with depth level, CID, descriptive name, and account type (client vs. sub-manager).
   - If saved to CSV, provide the file path in `~/saved/data/`.
