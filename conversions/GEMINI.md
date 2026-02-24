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
4.  **Referenced Action Rule**: If `segments.conversion_action` is in `WHERE`, it MUST be in `SELECT`.
5.  **Logical Time Verification**: Before upload, AI MUST verify:
    *   `conversion_date_time` > `click_time`.
    *   Click is within Lookback Window.

### 4. Troubleshooting Workflow [MANDATORY]

1.  **STEP 1: Diagnostic Summaries**: Execute queries against `offline_conversion_upload_client_summary` and `offline_conversion_upload_conversion_action_summary`.
    *   **[PITFALL] Attribute Name**: Use `successful_count` and `failed_count`. DO NOT use `success_count`.
2.  **STEP 2: Exception Inspection**: Catch `GoogleAdsException` and iterate over `ex.failure.errors`.
3.  **STEP 3: Identity & Consent**: Verify GCLID ownership and `consent` settings.

### 5. Structured Diagnostic Reporting [MANDATORY]

The AI MUST format final reports as follows:
1.  **Introductory Analysis**: State the Customer ID and the primary issue identified.
2.  **Numbered Technical Findings**: Detailed analysis of specific factors (e.g., Status, Metrics).
3.  **Specific Observations**: Bulleted data points (success rates, specific errors).
4.  **Actionable Recommendations**: Clear next steps for the user.
5.  **Empty Section Handling**: If summaries are empty, AI MUST append "Reason: No standard offline imports detected in last 90 days" inside the report.

---

### 6. References
- **Official Docs**: `https://developers.google.com/google-ads/api/docs/conversions/`
- **GAQL Structure**: `https://developers.google.com/google-ads/api/docs/query/`
