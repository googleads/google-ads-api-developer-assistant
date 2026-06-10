---
name: get-cids-under-mcc
description: Retrieves a list of all child customer account IDs (CIDs) under a given Manager Account (MCC).
---

# Get CIDs Under MCC

 Retrieves all child accounts under a specified Google Ads Manager Account (MCC).

## Usage

1. **Prompt User**: If the MCC account ID was not provided in the initial request, prompt the user to provide their MCC account ID.
2. **Execute Script**: Once the MCC account ID is obtained, run the following command:

```bash
./.venv/bin/python3 .agents/skills/get_cids_under_mcc/scripts/get_cids_under_mcc.py --customer_id <mcc_account_id> --api_version <api_version>
```

### Optional Flags
- `--save_csv`: Saves the results directly to a CSV file in `saved/csv/`.
- `--print_cids`: Prints the detailed table of child customer accounts (Customer ID, Level, Is MCC) to the console.

```bash
./.venv/bin/python3 .agents/skills/get_cids_under_mcc/scripts/get_cids_under_mcc.py --customer_id <mcc_account_id> --api_version <api_version> --save_csv --print_cids
```

### Output Handling
- **Default Output (neither flag)**: Prints a summary count of child accounts (e.g. `Found X child accounts under MCC Y.`).
- **Console Output (with `--print_cids`)**: Displays a formatted table of child accounts.
- **CSV Output (with `--save_csv`)**: Saves the results to `saved/csv/cids_under_mcc_<mcc_account_id>.csv` and prints a success confirmation.
- **Failure (Exit Code 1)**: Review the gRPC error output or invalid customer ID message, correct the input, and retry.
