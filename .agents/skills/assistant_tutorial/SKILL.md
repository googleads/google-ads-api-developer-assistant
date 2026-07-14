---
name: assistant-tutorial
description: A tutorial on how to use the Google Ads API Developer Assistant, covering campaign creation, documentation exploration (e.g., Shared Sets), code generation, and finding disapproved ads under an MCC.
---

# Google Ads API Developer Assistant Tutorial

Welcome to the Google Ads API Developer Assistant. This tutorial explains the core capabilities, constraints, and workflows of the Assistant, guiding you through common tasks such as campaign creation, exploring complex resources like Shared Sets, generating high-quality Python code, and running cross-account reports (like finding disapproved ads under an MCC).

---

## 1. Core Principles & Constraints

### 1.1. The "NO MUTATE" Read-Only Policy
*   **The Constraint:** The Assistant is strictly prohibited from executing `mutate`, `create`, `update`, or `delete` calls directly on your Google Ads accounts.
*   **How to Operate:** To create or modify resources, ask the Assistant to **generate the complete code** for you. The Assistant will write the script, lint it, type-annotate it, and save it to the [saved/code/](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/saved/code/) directory. You can then run the script manually from your terminal.

### 1.2. API Versioning
*   **Version Cache:** The Assistant reads the active API version from [config/api_version.txt](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/config/api_version.txt).
*   **Consistency:** All generated code and GAQL queries automatically target this version (e.g., `v24`) to prevent version mismatch errors.

---

## 2. How to Create a Campaign (Code Generation Workflow)

Because of the `NO MUTATE` constraint, you cannot ask the Assistant to "create a campaign right now." Instead, request: *"Generate a script to create a Search campaign with a budget."*

### The Generation and Execution Workflow
1.  **Request:** You prompt the Assistant for a campaign creation script.
2.  **Linting & Verification:** The Assistant writes the code to a temporary location, runs the `ruff` linter to clean it up, and saves the final script in the [saved/code/](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/saved/code/) directory (e.g., `saved/code/create_campaign.py`).
3.  **Run Command:** You execute the script using the sequestered virtual environment:
    ```bash
    GOOGLE_ADS_CONFIGURATION_FILE_PATH=config/google-ads.yaml ./.venv/bin/python3 saved/code/create_campaign.py
    ```

### Example Generated Script Structure
Every generated script wraps the logic cleanly, handles `GoogleAdsException` to suppress noisy stack traces, and utilizes type annotations:

```python
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def create_campaign(client: GoogleAdsClient, customer_id: str, campaign_name: str) -> str:
    """Creates a campaign budget and a campaign using the Google Ads API."""
    # Obtain necessary services
    campaign_budget_service = client.get_service("CampaignBudgetService")
    campaign_service = client.get_service("CampaignService")

    # 1. Create a Budget
    budget_operation = client.get_type("CampaignBudgetOperation")
    budget = budget_operation.create
    budget.name = f"Budget for {campaign_name}"
    budget.amount_micros = 50000000  # $50.00
    budget.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD

    try:
        budget_response = campaign_budget_service.mutate_campaign_budgets(
            customer_id=customer_id, operations=[budget_operation]
        )
        budget_resource_name = budget_response.results[0].resource_name
        print(f"Created budget: {budget_resource_name}")
    except GoogleAdsException as ex:
        print_api_errors(ex)
        sys.exit(1)

    # 2. Create the Campaign
    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.create
    campaign.name = campaign_name
    campaign.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
    campaign.status = client.enums.CampaignStatusEnum.PAUSED
    campaign.manual_cpc = client.get_type("ManualCpc")
    campaign.campaign_budget = budget_resource_name

    try:
        campaign_response = campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_operation]
        )
        campaign_resource_name = campaign_response.results[0].resource_name
        print(f"Created campaign: {campaign_resource_name}")
        return campaign_resource_name
    except GoogleAdsException as ex:
        print_api_errors(ex)
        sys.exit(1)

def print_api_errors(ex: GoogleAdsException) -> None:
    """Helper to format and print Google Ads API errors cleanly."""
    for error in ex.failure.errors:
        print(f"Error [{error.error_code}]: {error.message}")

if __name__ == "__main__":
    # Initialize client using configuration file
    googleads_client = GoogleAdsClient.load_from_storage()
    # Replace with target customer ID
    TARGET_CUSTOMER_ID = "INSERT_CUSTOMER_ID_HERE"
    create_campaign(googleads_client, TARGET_CUSTOMER_ID, "Sample Search Campaign")
```

---

## 3. How to Resolve Complex Documentation Issues (e.g., Shared Sets)

When dealing with complex concepts like **Shared Sets** (used for negative keyword lists, placement exclusion lists, etc.), the Assistant utilizes tools to explore resources programmatically rather than relying on high-level documentation summaries.

### 3.1. Explaining Concepts
You can ask the Assistant to break down concepts or use the `/explain` command:
*   *Prompt:* `/explain What is a SharedSet and how does it relate to CampaignSharedSet?`
*   *Analogy:* Think of a `SharedSet` as a reusable folder of negative keywords. Instead of adding negative keywords to every campaign individually, you attach the folder (`SharedSet`) to multiple campaigns using a connector resource (`CampaignSharedSet`).

### 3.2. Understanding and Using Shared Sets
A `SharedSet` represents a shared negative list (e.g., negative keywords or placement exclusions) that can be reused across multiple campaigns.

#### How to Use It:
1. **Create the Shared Set**: Create a `SharedSet` resource with a descriptive name and a specific type (e.g., `NEGATIVE_KEYWORDS`).
2. **Add Criteria**: Add shared criteria (like `SharedCriterion` for individual negative keywords) to your `SharedSet`.
3. **Link to Campaigns**: Create a `CampaignSharedSet` resource linking the campaign's resource name to the `SharedSet`'s resource name.
4. **Benefit**: Any criteria added or removed from the `SharedSet` are automatically applied to all linked campaigns.
---

## 4. How to Generate Clean Code

The Assistant adheres to a strict protocol to ensure code reliability:
1.  **Linter Validation:** Every script is written to a temporary file, run through `ruff check --fix` to enforce Python styling standards, and only moved to [saved/code/](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/saved/code/) once it passes.
2.  **Type Annotations:** All generated functions and parameters are fully type-annotated.
3.  **Error Isolation:** Stack traces are caught and formatted cleanly using `GoogleAdsException`.
4.  **No Environmental Guessing:** Client initialization always uses `GoogleAdsClient.load_from_storage()` pointing to [config/google-ads.yaml](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/config/google-ads.yaml).

---

## 5. How to Find Disapproved Ads Under an MCC (Cross-Account Reporting)

Finding all disapproved ads under a Manager Account (MCC) is a common cross-account auditing task. The Assistant breaks this down into three distinct phases.

### Phase 1: Determine Manager Account (MCC)
If the current customer ID is a client account (not a manager), first query its active parent manager account (MCC) using the `customer_manager_link` resource:
```sql
SELECT customer_manager_link.manager_customer, customer_manager_link.status
FROM customer_manager_link
WHERE customer_manager_link.status = 'ACTIVE'
```
Extract the MCC ID from the retrieved `manager_customer` resource name.

### Phase 2: Retrieve Client Accounts
Next, query the MCC hierarchy using the `get-cids-under-mcc` skill on the MCC ID to find all child customer account IDs (CIDs):
```bash
./.venv/bin/python3 .agents/skills/get_cids_under_mcc/scripts/get_cids_under_mcc.py --customer_id <mcc_id> --api_version v24 --print_cids
```

### Phase 2: Query Disapproved Ads per Customer Account
For each child account, a GAQL query is run against the `ad_group_ad` resource.

#### Validated GAQL Query
```sql
SELECT
  ad_group_ad.ad.id,
  ad_group_ad.ad.name,
  ad_group_ad.policy_summary.approval_status,
  ad_group_ad.policy_summary.policy_topic_entries
FROM ad_group_ad
WHERE ad_group_ad.policy_summary.approval_status = 'DISAPPROVED'
```

> [!IMPORTANT]
> **GAQL Rule Verification:**
> 1.  `WHERE` fields (`approval_status`) are present in the `SELECT` clause.
> 2.  No forbidden `OR` operator is used.
> 3.  The parent repeated field `policy_topic_entries` is selected instead of its sub-fields (complying with repeated field selection constraints).

### Multi-Account Python Script Example
Below is a clean script that combines the MCC lookup and the `ad_group_ad` query:

```python
import sys
from typing import List
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

def get_disapproved_ads(client: GoogleAdsClient, customer_ids: List[str]) -> None:
    """Queries disapproved ads across multiple customer accounts."""
    googleads_service = client.get_service("GoogleAdsService")
    
    query = """
        SELECT
          ad_group_ad.ad.id,
          ad_group_ad.ad.name,
          ad_group_ad.policy_summary.approval_status,
          ad_group_ad.policy_summary.policy_topic_entries
        FROM ad_group_ad
        WHERE ad_group_ad.policy_summary.approval_status = 'DISAPPROVED'
    """

    for cid in customer_ids:
        print(f"\nScanning customer ID: {cid}...")
        try:
            stream = googleads_service.search_stream(customer_id=cid, query=query)
            found_any = False
            for batch in stream:
                for row in batch.results:
                    found_any = True
                    ad_id = row.ad_group_ad.ad.id
                    ad_name = row.ad_group_ad.ad.name or "Unnamed Ad"
                    status = row.ad_group_ad.policy_summary.approval_status.name
                    print(f"  - [Disapproved Ad] ID: {ad_id} | Name: {ad_name} | Status: {status}")
                    
                    # Inspect individual policy issues
                    for entry in row.ad_group_ad.policy_summary.policy_topic_entries:
                        print(f"    * Policy Topic: {entry.topic} | Type: {entry.type_}")
            if not found_any:
                print("  No disapproved ads found.")
        except GoogleAdsException as ex:
            print(f"  Failed to query account {cid}:")
            for error in ex.failure.errors:
                print(f"    Error: {error.message}")

if __name__ == "__main__":
    googleads_client = GoogleAdsClient.load_from_storage()
    # List of CIDs obtained from the get-cids-under-mcc script
    CIDS_TO_SCAN = ["1111111111", "2222222222"]
    get_disapproved_ads(googleads_client, CIDS_TO_SCAN)
```
