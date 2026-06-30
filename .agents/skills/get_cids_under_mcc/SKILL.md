---
name: get-cids-under-mcc
description: Retrieves a list of all child customer account IDs (CIDs) under a given Manager Account (MCC).
---

# Get CIDs Under MCC

Use this skill to retrieve the hierarchy of child accounts under a Google Ads Manager Account (MCC). This is useful when you need to perform operations across multiple client accounts or understand the account structure.

## Protocol

1.  **Identify MCC ID:**
    *   Search the session context or user prompt for the Manager Account ID (MCC).
    *   If not explicitly provided, check if the default ID in `customer_id.txt` is a Manager Account.
    *   If still undetermined, ask the user to provide the MCC ID before proceeding.

2.  **Execute Retrieval:** Run the retrieval script in the sequestered virtual environment. **Always** pass the `--customer_id` and `--api_version` arguments to avoid interactive prompts.

    *   **To get a summary count only:**
        ```bash
        ./.venv/bin/python3 .agents/skills/get_cids_under_mcc/scripts/get_cids_under_mcc.py --customer_id <mcc_id> --api_version <api_version>
        ```

    *   **To print the detailed list to console:**
        ```bash
        ./.venv/bin/python3 .agents/skills/get_cids_under_mcc/scripts/get_cids_under_mcc.py --customer_id <mcc_id> --api_version <api_version> --print_cids
        ```

    *   **To save the list to a CSV file (saved in `saved/csv/`):**
        ```bash
        ./.venv/bin/python3 .agents/skills/get_cids_under_mcc/scripts/get_cids_under_mcc.py --customer_id <mcc_id> --api_version <api_version> --save_csv
        ```

3.  **Output Processing:**
    *   If `--print_cids` was used, parse the console output to get the CIDs, their depth level, and whether they are sub-managers.
    *   If `--save_csv` was used, verify the file was created at `saved/csv/cids_under_mcc_<mcc_id>.csv`.

---

## Examples

### Example 1: Printing CIDs to Console
*   **Command:**
    ```bash
    ./.venv/bin/python3 .agents/skills/get_cids_under_mcc/scripts/get_cids_under_mcc.py --customer_id 1234567890 --api_version v17 --print_cids
    ```
*   **Output:**
    ```
    Child accounts under MCC 1234567890:
    Customer ID     Level   Is MCC  
    --------------------------------
    2345678901      1       No      
    3456789012      1       Yes     
    4567890123      2       No      
    ```

### Example 2: Saving to CSV
*   **Command:**
    ```bash
    ./.venv/bin/python3 .agents/skills/get_cids_under_mcc/scripts/get_cids_under_mcc.py --customer_id 1234567890 --api_version v17 --save_csv
    ```
*   **Output:**
    ```
    SUCCESS: Results saved to /usr/local/google/home/rwh/google-ads-api-developer-assistant/saved/csv/cids_under_mcc_1234567890.csv
    ```
