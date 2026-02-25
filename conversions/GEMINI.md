# Google Ads API Conversion Troubleshooting 

## Metadata
- **Version:** 2.0
- **Target API:** Google Ads API (v23)
- **Role:** Technical Reference for AI Assistant
- **Optimized for:** Machine Comprehension

---

### 1. Core Directives [MANDATORY]
*   **API Response != Attribution**: A successful API import response (no errors) means the data was received, but it does **not** guarantee the conversion will be attributed to an ad. 
*   **Offline Diagnostics Priority**: Always prioritize offline diagnostics for import health. The Google Ads UI is not organized by import date, which can make it difficult to diagnose recent issues.
*   **Mandatory Diagnostic Workflow**: For ALL conversion-related troubleshooting, the AI MUST execute the workflow defined in Section 4.

### 2. Common Error Codes & Resolution Strategies

#### 2.1. Enhanced Conversions for Leads
*   `NO_CONVERSION_ACTION_FOUND`: The conversion action is disabled or inaccessible.
    *   **Root Cause (Disabled)**: Status is REMOVED or HIDDEN.
    *   **Root Cause (Inaccessible)**: Typo in `customer_id` or action belongs to a different account (e.g., MCC) and isn't shared.
*   `INVALID_CONVERSION_ACTION_TYPE`: Must use `UPLOAD_CLICKS`.
    *   **Pitfall**: Happens when uploading to a "Tag" action. MUST create an "Import" action via UI.
*   `CUSTOMER_NOT_ENABLED_ENHANCED_CONVERSIONS_FOR_LEADS`: Setting disabled in UI.
    *   **Mandatory Verification**: Query `customer` resource for `enhanced_conversions_for_leads_enabled` and `accepted_customer_data_terms`.
*   `DUPLICATE_ORDER_ID`: Multiple conversions with same Order ID in one batch.
    *   **Resolution**: De-duplicate the batch in code before calling `UploadClickConversions`.
*   `CLICK_NOT_FOUND`: No click matched user identifiers.
    *   **Critical Verification**: Wait 24 hours (Processing Time). Check hashing/normalization (Trim, Lowercase, SHA-256). Verify GCLID ownership via `click_view`.

#### 2.2. Enhanced Conversions for Web
*   `CONVERSION_NOT_FOUND`: Missing original conversion for enhancement.
    *   **Critical Verification**: Wait 24 hours. Ensure `order_id` matches exactly (case-sensitive).
*   `CUSTOMER_NOT_ACCEPTED_CUSTOMER_DATA_TERMS`: Terms must be accepted in UI.
*   `CONVERSION_ALREADY_ENHANCED`: Conversion already has user data.
    *   **Pitfall**: Only one enhancement allowed per conversion.
*   `CONVERSION_ACTION_NOT_ELIGIBLE_FOR_ENHANCEMENT`: Action type must be `WEBPAGE`.

#### 2.3. General Logic Errors
*   `TOO_RECENT_CONVERSION_ACTION`: Wait 6-24 hours after action creation.
*   `EXPIRED_EVENT`: Click is outside the `click_through_lookback_window_days`.
*   `CONVERSION_PRECEDES_EVENT`: [CRITICAL] Conversion timestamp is before click timestamp.
*   `DUPLICATE_CLICK_CONVERSION_IN_REQUEST`: Same (GCLID, Action) pair repeated in batch.

### 3. Rigorous GAQL Validation for Conversions [CRITICAL]

1.  **NO 'OR' OPERATOR**: GAQL does NOT support `OR` in `WHERE`. Use `IN` or separate queries.
2.  **Conversion Metric Incompatibility**: `metrics.conversions` is INCOMPATIBLE with `FROM conversion_action`.
    *   **Mandatory Fix**: Use `FROM customer`, `campaign`, or `ad_group` and `SELECT segments.conversion_action`.
3.  **Metadata Query Syntax**: `GoogleAdsFieldService` queries MUST NOT include a `FROM` clause.
    *   **Correct**: `SELECT name, selectable WHERE name = 'campaign.id'`
    *   **[PITFALL] Service Selection**: NEVER use `GoogleAdsService` to query `google_ads_field`. You MUST use `GoogleAdsFieldService.search_google_ads_fields`.
    *   **[PITFALL] Field Prefixes**: Metadata fields MUST NOT be prefixed with the resource name (e.g., use `name`, NOT `google_ads_field.name`).
    *   **[PITFALL] Field Names**: Use `data_type`. DO NOT use `type` in `GoogleAdsFieldService` queries; it will result in an `UNRECOGNIZED_FIELD` error.
4.  **Referenced Action Rule**: If `segments.conversion_action` is in `WHERE`, it MUST be in `SELECT`. Failure to do so results in `EXPECTED_REFERENCED_FIELD_IN_SELECT_CLAUSE`.
5.  **No Metrics for Managers**: Metrics (e.g., `metrics.conversions`) CANNOT be requested for a manager account (MCC). You MUST identify and query each client account separately. Failure results in `REQUESTED_METRICS_FOR_MANAGER`.
6.  **Logical Time Verification**: Before upload, AI MUST verify:
    *   `conversion_date_time` > `click_time`.
    *   Click is within Lookback Window.

### 4. Troubleshooting Workflow [MANDATORY]

1.  **STEP 1: Diagnostic Summaries**: Execute queries against `offline_conversion_upload_client_summary` and `offline_conversion_upload_conversion_action_summary`.
    *   **[PITFALL] Attribute Name**: Use `successful_count` and `failed_count`. DO NOT use `success_count`.
    *   **[PITFALL] Summary Object**: `daily_summaries` (OfflineConversionSummary) DOES NOT have a `total_count` field. Use `successful_count + failed_count + pending_count` for a total. `total_event_count` is only available at the top-level resource, not within `daily_summaries`.
    *   **[PITFALL] Alert Object**: `alerts` (OfflineConversionAlert) uses `error` and `error_percentage`. DO NOT use `error_code` or `error_count`.
    *   **[PITFALL] Alerts Field Location**: The `alerts` field is located at the top-level resource (`offline_conversion_upload_client_summary` or `offline_conversion_upload_conversion_action_summary`), NOT within the `daily_summaries` list.
2.  **STEP 2: Exception Inspection**: Catch `GoogleAdsException` and iterate over `ex.failure.errors`.
3.  **STEP 3: Identity & Consent**: Verify GCLID ownership and `consent` settings.

### 5. Structured Diagnostic Reporting [MANDATORY]

The AI MUST format final reports as follows:
1.  **Introductory Analysis**: State the Customer ID and the primary issue identified.
2.  **Numbered Technical Findings**: Detailed analysis of specific factors (e.g., Status, Metrics).
3.  **Specific Observations**: Bulleted data points (success rates, specific errors).
4.  **Actionable Recommendations**: Clear next steps for the user.
5.  **Empty Section Handling**: If summaries are empty, AI MUST append "Reason: No standard offline imports detected in last 90 days" inside the report.
6.  **Full Diagnostic Data Mandate**: The report MUST contain the verbatim output or detailed data from the `offline_conversion_upload_client_summary` and `offline_conversion_upload_conversion_action_summary` queries to ensure transparency and complete diagnostic visibility.
7.  **Structured Analysis Mandate**: The report MUST include a structured section containing "Primary Errors Identified" (with root causes and fixes), "Specific Action Failures", "General Health" assessment, and "Actionable Recommendations" as presented to the user.
8.  **Verbatim Screen Output Mandate**: The report MUST ALWAYS include the verbatim structured analysis and recommendations text presented to the user on the screen (e.g. detailed findings for EXPIRED_EVENT, specific action failures, and timing issues).

**Consolidation Mandate**: All findings, including terminal summaries, the structured analysis, the verbatim screen output, and the **complete verbatim data** from all troubleshooting scripts and queries, MUST be consolidated into a **single, uniquely named text file** in `saved/data/`. 

**Mandatory Naming Rule**:
- For reports generated via the `/conversions_support_package` command, the file MUST be named exactly `conversions_support_package_<epoch>.text`.
- For any other conversion-related reports or files, DO NOT use this specific naming convention.

This file MUST be the sole artifact submitted to the user for support. It must start with the header "Created by the Google Ads API Developer Assistant". Placeholders or references to other files for "details" are strictly prohibited; all data must be contained within this single file.

---

### 6. References
- **Official Docs**: `https://developers.google.com/google-ads/api/docs/conversions/`
- **GAQL Structure**: `https://developers.google.com/google-ads/api/docs/query/`

---

### 7. Python Object Inspection & Error Handling [MANDATORY]

#### 7.1. Proto-plus Message Inspection
*   **No Direct Descriptor Access**: NEVER use `obj.DESCRIPTOR`, `obj.pb`, or `obj.meta` on a message instance or class. These are hidden by the `proto-plus` wrapper.
*   **Correct Inspection**: Use `type(obj).pb(obj)` for instances. For classes, use `Class.meta.pb.DESCRIPTOR` to access the underlying protobuf descriptor.
*   **Linter Compliance**: When using `type(obj).pb(obj)` for inspection, ensure the resulting object is actually used or use a leading underscore (e.g., `_pb_obj`) to avoid "unused variable" linter errors (e.g., Ruff F841).
*   **AttributeError Handling**: If an `AttributeError: Unknown field for <Type>: <field>` occurs, it means the attribute is not defined in the protobuf message. Immediately verify the field name against the official API documentation or use `dir(obj)` to see available attributes.

#### 7.2. Conversion-Specific Object Pitfalls
*   **OfflineConversionAlert**: 
    *   **CRITICAL: Error Field Structure**: The `alert.error` field is NOT a direct enum. it is a `oneof` message (type `OfflineConversionError`) containing fields for different error categories (e.g., `conversion_upload_error`, `conversion_adjustment_upload_error`).
    *   **Mandatory Access Pattern**: To get the error string, you MUST identify which field in the `oneof` is set and then access its `.name`. The `oneof` field name in `OfflineConversionError` is `error_code`.
    *   **Example Code**: 
        ```python
        # Mandatory access pattern for OfflineConversionError oneof
        error_type = type(alert.error).pb(alert.error).WhichOneof("error_code")
        error_val = getattr(alert.error, error_type)
        error_name = error_val.name
        ```
*   **Diagnostic Reports**: When summarizing failed conversions, always include the error name and the `error_percentage` from `OfflineConversionAlert`.
