---
name: get-cids-under-mcc
description: Retrieves a list of all child customer account IDs (CIDs) under a given Manager Account (MCC).
---

# Get CIDs Under MCC

Use this skill to retrieve the hierarchy of child accounts under a Google Ads Manager Account (MCC). This is useful when you need to perform operations across multiple client accounts or understand the account structure.

## Protocol

1. **Identify MCC ID:** Search the session context or user prompt for the Manager Account ID (MCC). If not explicitly provided, ask the user to provide the MCC ID before proceeding.

2. **Execute Retrieval:** Run the retrieval script in the python environment:

    * **To get a summary count only:**
        ```bash
        python3 skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py --customer_id <mcc_id> --api_version <api_version>
        ```

    * **To print the detailed list to console:**
        ```bash
        python3 skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py --customer_id <mcc_id> --api_version <api_version> --print_cids
        ```

    * **To save the list to a CSV file (saved in `saved/csv/`):**
        ```bash
        python3 skills/get-cids-under-mcc/scripts/get_cids_under_mcc.py --customer_id <mcc_id> --api_version <api_version> --save_csv
        ```

3. **Output Processing:**
    * If `--print_cids` was used, parse the console output to get the CIDs, their depth level, and whether they are sub-managers.
    * If `--save_csv` was used, verify the file was created.
