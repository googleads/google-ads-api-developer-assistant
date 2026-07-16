---
name: assistant-tutorial
description: An interactive tutorial on how to use the Google Ads API Developer Assistant.
---

# Google Ads API Developer Assistant Tutorial (Interactive Guide)

> [!NOTE]
> * If you want a real-world analogy and conceptual explanation for any Google Ads API concept, use the `/explain <concept>` command.
> * If you want to walk through a process or workflow step-by-step, use the `/step-by-step <process>` command.

## Critical Directive for the Agent
When a user invokes `/assistant-tutorial` or requests this tutorial:
1. **NO MD SYNOPSIS FILES:** You MUST NOT write any markdown files or artifacts summarizing the tutorial.
2. **ALWAYS INTERACTIVE:** You MUST run this tutorial as an interactive, conversational experience.
3. **TOPIC SELECTION:** Start by asking the user which specific topic they want to learn about first using the `ask_question` tool.
4. **PROGRESSIVE DISCLOSURE:** Present information in small, manageable pieces. Ask checking questions or prompt the user to proceed before moving on to the next step.
5. **EXPLAIN ANSWER OPTION:** Whenever you pose an interactive check question or quiz to the user, you MUST include a choice/option that allows them to ask the Assistant to answer and explain the answer (e.g., "Have the Assistant reveal and explain the answer"). If selected, you MUST reveal the correct answer and explain the underlying reasoning in chat.


---

## Tutorial Content Reference

Use the reference material below to guide the interactive session based on the user's choices.

### Topic 1: Core Principles & Constraints
- **The "NO MUTATE" Read-Only Policy:** Explain that the Assistant cannot execute mutate operations (such as create, update, or delete) directly. Instead, it provides the code for the mutate in the `saved/code/` directory, which the user can run themselves or incorporate into their codebase.
- **API Versioning:** All code and GAQL queries target the confirmed version in `config/api_version.txt` (currently `v24`).
- **Interactive Check:** Ask the user if they want to see an example workflow diagram or move to campaign creation.

### Topic 2: Campaign Creation (Code Generation Workflow)
- Explain the generation & execution workflow.
- Show the standard template structure for `create_campaign.py`.
- **NO MUTATE Execution Warning:** Remind the user that the Assistant is designed for read-only operations and cannot execute this campaign creation mutate code directly. The user must run the generated script themselves outside of the Assistant.
- **Interactive Check:** Ask the user if they'd like to draft a sample campaign script or if they understand the workflow.

### Topic 3: Shared Sets (Exclusion Lists)
- Explain `SharedSet` (reusable keyword/placement exclusion folders), `SharedCriterion` (items), and `CampaignSharedSet` (connector).
- Describe the relationships and benefits.
- **Interactive Check:** Ask the user a multiple-choice question about the difference between `SharedSet` and `CampaignSharedSet`.

### Topic 4: Code Quality & Standards
- Detail the automated linting (`ruff`), type annotations, and error handling (`GoogleAdsException` wrapper) that the assistant enforces.
- **Interactive Check:** Ask the user if they want to review a Python exception handling template.

### Topic 5: Finding Disapproved Ads (Cross-Account Audit)
- Phase 1: Determine Parent Manager Account (MCC) using `customer_manager_link`.
- Phase 2: Retrieve child accounts recursively using `get_cids_under_mcc` script.
- Phase 3: Query disapproved ads via `ad_group_ad` resource.
- **Interactive Check:** Ask the user if they'd like to run a query to check their current manager links or find disapproved ads in a specific customer ID.

### Topic 6: Creating an AI Max for Search Campaign
- **What is AI Max?** In the Google Ads API, "AI Max" refers to "AI Max for Search campaigns", NOT "Performance Max" campaigns.
- **Enabling AI Max:** Set `ai_max_setting.enable_ai_max = True` on the `Campaign` resource (see [create_ai_max_campaign.py](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/saved/code/create_ai_max_campaign.py#L323)).
- **Campaign Configuration:**
  - `advertising_channel_type` must be set to `SEARCH`.
  - Use a budget and a bidding strategy like Maximize Conversions (`maximize_conversions`).
- **Asset Generation:** Use `AssetGenerationService` (`generate_text` and `generate_images`) to dynamically generate text and image assets from a final URL and business description prompt.
- **RSA Configuration:** Create an Ad Group, then add a Responsive Search Ad (`ResponsiveSearchAdInfo`) inside an `AdGroupAd` using the generated text assets.
- **NO MUTATE Execution Warning:** The Assistant cannot execute the script to create the AI Max Campaign. The user must run the generated Python script themselves in their terminal outside of the Assistant.
- **Interactive Check:** Ask the user if they want to review a sample Python configuration for enabling AI Max on a Search campaign.

### Topic 7: Creating a Demand Gen Campaign
- **What is Demand Gen?** Campaigns that drive action across YouTube, Discover, and Gmail using image and video assets.
- **Campaign Configuration:**
  - `advertising_channel_type` must be set to `DEMAND_GEN` (see [add_demand_gen_campaign.py](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/client_libs/google-ads-python/examples/advanced_operations/add_demand_gen_campaign.py#L197)).
  - Bidding strategy: typically Target CPA (`bidding_strategy_type = TARGET_CPA` with `target_cpa.target_cpa_micros`), Maximize Conversions, or Maximize Click value.
- **Ad Group Settings:** Configure `demand_gen_ad_group_settings.channel_controls.selected_channels` to specify active channels (e.g., `youtube_shorts = True`, `gmail = False`).
- **Ad Creation:** Create an `AdGroupAd` with `ad.demand_gen_video_responsive_ad` containing logo images, videos, business name, headlines, long headlines, and descriptions (see [add_demand_gen_campaign.py](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/client_libs/google-ads-python/examples/advanced_operations/add_demand_gen_campaign.py#L318-L349)).
- **NO MUTATE Execution Warning:** The Assistant cannot execute the script to create the Demand Gen Campaign. The user must run the generated script themselves outside of the Assistant.
- **Interactive Check:** Ask the user which `advertising_channel_type` value is used to define a Demand Gen campaign.

### Topic 8: Writing Prompts to Produce Reports
- **Prompting Best Practices:**
  - Define the main resource (e.g., `campaign`, `ad_group`, `ad_group_ad`, `click_view`).
  - Specify required metrics (e.g., `metrics.impressions`, `metrics.clicks`, `metrics.conversions`).
  - Request specific segments (e.g., `segments.date`, `segments.device`).
- **GAQL Validation Protocol:** The Assistant programmatically validates queries via a 4-step protocol before execution:
  1. *Schema Discovery:* Query `GoogleAdsFieldService` (Note: No `FROM` clause in metadata queries, and use bare field names like `name` instead of `google_ads_field.name`).
  2. *Compatibility Check:* Verify selectable compatibility using `selectable_with`.
  3. *Static Analysis:* Ensure all `WHERE` fields are in `SELECT` (except core date segments), avoid forbidden operators like `OR` (use `IN` instead), and do not use SQL aggregation functions.
  4. *Runtime Dry Run:* Run the validation script [validate_gaql.py](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/.agents/skills/validate_gaql/scripts/validate_gaql.py).
- **Interactive Check:** Ask the user a question about how to filter a field using multiple values without using the `OR` operator in GAQL.

### Topic 9: Troubleshooting Conversion Problems
- **Diagnostic Protocol:** If offline conversion uploads fail, retrieve the Customer ID and execute the troubleshooting diagnostic tool:
  ```bash
  ./.venv/bin/python3 .agents/skills/troubleshoot_conversions/scripts/troubleshoot_conversions.py --customer_id <customer_id> --api_version <api_version>
  ```
  This creates a consolidated report file starting with `Created by the Google Ads API Developer Assistant` under `saved/data/conversion_troubleshooting_report_<epoch>.txt` (see [troubleshoot_conversions.py](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/.agents/skills/troubleshoot_conversions/scripts/troubleshoot_conversions.py)).
- **Pre-Upload Validation:** Before uploading new conversions, validate the CSV format and rules (e.g., checking that `conversion_time` is after `click_time`) using the validation tool [validate_conversion_upload.py](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/.agents/skills/troubleshoot_conversions/scripts/validate_conversion_upload.py):
  ```bash
  ./.venv/bin/python3 .agents/skills/troubleshoot_conversions/scripts/validate_conversion_upload.py --csv_path <path_to_csv> --api_version <api_version>
  ```
- **NO MUTATE Execution Warning:** If you decide to proceed with uploading conversions based on verified CSV diagnostics, please note that the Assistant cannot execute upload mutation code directly. The user must run the conversion upload scripts themselves outside of the Assistant.
- **Interactive Check:** Ask the user which script they should run to generate a troubleshooting report for conversion upload errors.

### Topic 10: Obtaining Descriptions of API Concepts and Objects
- **Conceptual Explanations:** For high-level explanations, use `/explain` or ask the assistant to explain a concept. The assistant uses the [explain SKILL.md](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/.agents/skills/explain/SKILL.md) to generate a structured description:
  1. *The Big Picture:* A high-level 1-2 sentence problem definition.
  2. *Analogy:* A non-technical real-world analogy.
  3. *Interconnectedness:* How it links to other API resources.
  4. *Simple Language:* A non-technical user-friendly summary.
- **Structural/Schema Inspection:** For looking up physical fields, types, and Enum values, use the schema inspect utility [inspect_object.py](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/.agents/skills/inspect_object/scripts/inspect_object.py):
  ```bash
  ./.venv/bin/python3 .agents/skills/inspect_object/scripts/inspect_object.py --object_name <ObjectName> --api_version <api_version>
  ```
  See details in [inspect_object/SKILL.md](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/.agents/skills/inspect_object/SKILL.md).
- **Interactive Check:** Ask the user how they would inspect the structural field definitions of the `AdGroup` resource.

### Topic 11: Creating a Listing Filter for a Performance Max (PMax) Campaign
- **Concept Verification:**
  > [!WARNING]
  > Use `/explain listing filter` for a high-level conceptual explanation of what a listing filter is before configuring it.

- **What is a Listing Filter?**
  In Performance Max (PMax) campaigns, an `AssetGroupListingGroupFilter` specifies which subsets of items (from a Merchant Center product feed) or webpages (when dynamic URL expansion is enabled) are targeted or excluded by a specific Asset Group. For webpage targeting, it acts as a filter tree regulating landing page traffic.

- **Why Create a Webpage Listing Filter?**
  1. **Exclude Non-Commercial Traffic:** Prevent PMax from sending paid traffic to non-converting pages (e.g., `/blog`, `/privacy-policy`, `/terms-of-service`).
  2. **Structure Landing Page Target Routing:** Route search traffic to specific landing pages by setting up inclusions or exclusions on asset groups (e.g., ensuring a "Running Shoes" asset group only targets shoe-related URLs).

- **Core Programmatic Parts & Their Roles:**
  * **`listing_source`:** Dictates what inventory is filtered. Set to `ListingGroupFilterListingSourceEnum.WEBPAGE` for webpage-based filtering (exclusion lists).
  * **`type_`:** Defines the node type in the filter tree structure:
    * `SUBDIVISION`: A parent node (branch) used to split the tree structure. It does not target or exclude traffic directly.
    * `UNIT_INCLUDED` or `UNIT_EXCLUDED`: Leaf nodes (end-nodes) that explicitly target or exclude traffic matching the criteria.
  * **`parent_listing_group_filter`:** Links child nodes to their parent `SUBDIVISION` node, building the tree hierarchy.
  * **`case_value.webpage.conditions`:** Defines the rule matching criteria (using `ListingGroupFilterDimension.WebpageCondition`). Commonly uses the `url_contains` attribute to match specific URL substrings (e.g., `/blog`).

- **Dry-Run Validation:**
  Before executing write commands, the Assistant validates the filter tree in dry-run mode (without writing to the account) by running [create_pmax_webpage_filter.py](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/.agents/skills/pmax_listing_filter/scripts/create_pmax_webpage_filter.py) without the `--execute` flag:
  ```bash
  ./.venv/bin/python3 .agents/skills/pmax_listing_filter/scripts/create_pmax_webpage_filter.py \
    --customer_id <customer_id> \
    --asset_group_id <asset_group_id> \
    --url_exclusion <url_exclusion_path> \
    --api_version <api_version>
  ```

- **Applying the Listing Filter (Mutation):**
  After the structure has been validated, you can execute the command with the `--execute` flag in your terminal to apply the mutation (see [pmax_listing_filter/SKILL.md](file:///home/rwh_google_com/sandbox/google-ads-api-developer-assistant/.agents/skills/pmax_listing_filter/SKILL.md)):
  ```bash
  ./.venv/bin/python3 .agents/skills/pmax_listing_filter/scripts/create_pmax_webpage_filter.py \
    --customer_id <customer_id> \
    --asset_group_id <asset_group_id> \
    --url_exclusion <url_exclusion_path> \
    --api_version <api_version> \
    --execute
  ```
  **NO MUTATE Execution Warning:** The Assistant cannot execute this mutation command directly. The user must copy and run it themselves in their own terminal outside of the Assistant.

- **Interactive Check:** Ask the user what the difference is between a `SUBDIVISION` filter type and a `UNIT_INCLUDED` filter type when building listing filter trees.



