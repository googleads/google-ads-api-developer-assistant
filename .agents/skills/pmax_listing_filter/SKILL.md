---
name: pmax-listing-filter
description: Validates or generates commands to configure Asset Group URL expansion filters (webpage exclusions) for Performance Max campaigns.
---

# PMax Webpage Exclusions Filter

Use this skill to configure webpage listing group filtering (exclusions) for Performance Max campaigns without using Page Feeds. 

**CRITICAL CONSTRAINT (NO MUTATE):** You are strictly prohibited from executing mutations. You MUST NOT run the script with the `--execute` flag. You may only run it in dry-run mode (without `--execute`) to validate the structure. If the user wants to apply the changes, you must provide them with the exact command to run.

## Protocol

1.  **Identify Parameters:** Retrieve the `customer_id`, `asset_group_id`, and `url_exclusion` (the URL path to exclude, e.g., `/blog`) from the context.
2.  **Dry-Run Validation:** Run the script **without** the `--execute` flag in the sequestered virtual environment to verify the configuration is valid:

    ```bash
    ./.venv/bin/python3 .agents/skills/pmax_listing_filter/scripts/create_pmax_webpage_filter.py \
      --customer_id <customer_id> \
      --asset_group_id <asset_group_id> \
      --url_exclusion <url_exclusion_path> \
      --api_version <api_version>
    ```

3.  **Present Execution Command to User:** Once the dry-run succeeds, present the verified command *with* the `--execute` flag to the user in chat, explaining that they must run it themselves to apply the changes.

---

## Examples

### Example 1: Agent Dry-Run Verification (Safe)
*   **Command (Executed by Agent):**
    ```bash
    ./.venv/bin/python3 .agents/skills/pmax_listing_filter/scripts/create_pmax_webpage_filter.py \
      --customer_id 1234567890 \
      --asset_group_id 987654321 \
      --url_exclusion /blog \
      --api_version v17
    ```
*   **Output:**
    ```
    SUCCESS: Subdivision Webpage Listing Filter tree validated/created successfully.
      - Created Listing Filter resource: 'customers/1234567890/assetGroupListingGroupFilters/987654321~-1'
    ```

### Example 2: Instruction for the User (Mutation)
Explain to the user that they can apply the exclusion by running the following command in their terminal:

```bash
./.venv/bin/python3 .agents/skills/pmax_listing_filter/scripts/create_pmax_webpage_filter.py \
  --customer_id 1234567890 \
  --asset_group_id 987654321 \
  --url_exclusion /blog \
  --api_version v17 \
  --execute
```
