# Google Ads API Conversion Troubleshooting 

This document provides a technical reference for troubleshooting conversion-related issues in the Google Ads API, based on the official documentation.

---

### 1. Core Concepts
*   **API Response != Attribution**: A successful API import response (no errors) means the data was received, but it does **not** guarantee the conversion will be attributed to an ad. 
*   **Offline Diagnostics**: Always prioritize offline diagnostics for import health. The Google Ads UI is not organized by import date, which can make it difficult to diagnose recent issues.

### 2. Common Error Codes

#### 2.1. Enhanced Conversions for Leads
*   `NO_CONVERSION_ACTION_FOUND`: The conversion action is disabled or inaccessible.
*   `INVALID_CONVERSION_ACTION_TYPE`: Must use `UPLOAD_CLICKS` for enhanced conversions for leads.
*   `CUSTOMER_NOT_ENABLED_ENHANCED_CONVERSIONS_FOR_LEADS`: The setting is disabled in the account.
*   `DUPLICATE_ORDER_ID`: Multiple conversions sent with the same Order ID in the same batch.
*   `CLICK_NOT_FOUND`: No click matched the provided user identifiers. (Treat as a warning unless frequent).

#### 2.2. Enhanced Conversions for Web
*   `CONVERSION_NOT_FOUND`: Could not find a conversion matching the supplied action and ID/Order ID pair.
*   `CUSTOMER_NOT_ACCEPTED_CUSTOMER_DATA_TERMS`: Customer data terms must be accepted in the UI.
*   `CONVERSION_ALREADY_ENHANCED`: An adjustment for this Order ID and action has already been processed.
*   `CONVERSION_ACTION_NOT_ELIGIBLE_FOR_ENHANCEMENT`: This action type cannot be enhanced.

#### 2.3. General Issues
*   `TOO_RECENT_CONVERSION_ACTION`: Wait at least 6 hours after creating a new conversion action before uploading conversions to it.
*   `EXPIRED_EVENT`: The click occurred before the conversion action's `click_through_lookback_window_days`.
*   `CONVERSION_PRECEDES_EVENT`: The conversion timestamp is before the click timestamp.
*   `DUPLICATE_CLICK_CONVERSION_IN_REQUEST`: The same conversion is repeated in a single batch.

### 3. Verification Checklist

1.  **GCLID Ownership**: Query the `click_view` resource to verify if a GCLID belongs to the specific customer account.
2.  **Customer Terms**: Check `customer.offline_conversion_tracking_info.accepted_customer_data_terms` via the `customer` resource.
3.  **Data Normalization**: Ensure email addresses, phone numbers, and names are correctly normalized (trimmed, lowercased) and hashed (SHA-256) before sending.
4.  **Consent**: Verify that `ClickConversion.consent` is properly set in the upload if required by regional policies.

### 4. Troubleshooting Workflow

1.  **Check API Error Details**: Inspect the `GoogleAdsException` for specific `ErrorCode` and `message`.
2.  **Verify Timestamps**: Ensure `conversion_date_time` is in `yyyy-mm-dd hh:mm:ss+|-hh:mm` format and falls within the lookback window.
3.  **Validate Identifiers**: For `CLICK_NOT_FOUND`, ensure you are not mixing `gclid` with `gbraid` or `wbraid` inappropriately. Use only one per conversion.
4.  **Wait for Processing**: Conversions can take up to 3 hours to appear in reporting after a successful upload.
5.  **Check Conversion Settings**: Ensure the conversion action's `status` is `ENABLED` and it is configured for the correct `type`.

#### 4.1. General Troubleshooting
- **Conversions:**
    - Use `offline_conversion_upload_conversion_action_summary` and `offline_conversion_upload_client_summary` for recent conversion import issues.
    - Refer to official documentation for discrepancies and troubleshooting.