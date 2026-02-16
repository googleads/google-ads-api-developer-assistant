# Google Ads API Conversion Troubleshooting 

This document provides a technical reference for troubleshooting conversion-related issues in the Google Ads API, based on the official documentation.

---

### 1. Core Concepts
*   **API Response != Attribution**: A successful API import response (no errors) means the data was received, but it does **not** guarantee the conversion will be attributed to an ad. 
*   **Offline Diagnostics**: Always prioritize offline diagnostics for import health. The Google Ads UI is not organized by import date, which can make it difficult to diagnose recent issues.

### 2. Common Error Codes

#### 2.1. Enhanced Conversions for Leads
*   `NO_CONVERSION_ACTION_FOUND`: The conversion action is disabled or inaccessible.
    *   **Disabled**: The action's status is set to REMOVED or HIDDEN. This usually happens if someone "deleted" the action in the Google Ads UI, making it inactive for new uploads.
    *   **Inaccessible**: The API cannot "see" the action from the specific customer_id you are using. This occurs if you have a typo in the ID, or if the action belongs to a different account (like a Manager/MCC account) and hasn't been shared with the client account performing the upload.

*   `INVALID_CONVERSION_ACTION_TYPE`: Must use `UPLOAD_CLICKS` for enhanced conversions for leads.
    *   **Context**: This error happens when you try to upload Enhanced Conversions for Leads to a conversion action that was created as a standard "Webpage" conversion (the kind that uses a tag on your site) instead of an "Import" conversion.
    *   **Fix Step 1 (Create Correct Action Type)**: You cannot "convert" an existing Webpage action into an Upload action. You must:
        *   Go to the Google Ads UI.
        *   Create a New Conversion Action.
        *   Select Import as the source.
        *   Select Manual import using API or uploads and specifically choose Track conversions from clicks.
        *   This ensures the type is set to `UPLOAD_CLICKS`.
    *   **Fix Step 2 (Update API Code)**: Once the new action is created, grab its ID and update your script:
        *   Ensure you are using the `UploadClickConversions` method.
        *   Ensure the `conversion_action` resource name in your code points to the new ID.
        *   Verify that you are including the required user identifiers (like hashed email or phone number) in the `UserIdentifier` field of the request.
    *   **Summary**: The API is telling you, "You're trying to upload lead data to a 'Tag' action, but I only accept that data for an 'Import' action."

*   `CUSTOMER_NOT_ENABLED_ENHANCED_CONVERSIONS_FOR_LEADS`: The setting is disabled in the account. To address this error, you must enable the setting in the Google Ads UI and accept the required terms. This cannot be done entirely via the API because it requires a manual legal agreement.
    *   **Step 1: Accept Customer Data Terms (Manual)**
        1. Log in to your Google Ads account.
        2. Click the Goals icon.
        3. Click the Conversions dropdown and select Settings.
        4. Expand the Customer data terms section.
        5. Read and Accept the terms if you haven't already. This is the most common reason for this error.
    *   **Step 2: Enable the Setting in the UI**
        1. While still in Goals > Conversions > Settings, look for the Enhanced conversions for leads section.
        2. Check the box to Turn on enhanced conversions for leads.
        3. Choose your method (usually "Google Ads API" or "Global site tag").
        4. Click Save.
    *   **Step 3: Verify via API (Autonomous Action by Gemini)**
        *   If you want to check if the setting is correctly enabled using code, Gemini can execute this query against the `customer` resource for you:
            ```sql
            SELECT
              customer.offline_conversion_tracking_info.enable_enhanced_conversions_for_leads,
              customer.offline_conversion_tracking_info.accepted_customer_data_terms
            FROM customer
            ```
    *   **Note**: After enabling the setting, it can sometimes take a few minutes for the API to recognize the change. If you still see the error immediately after saving, wait about 15–30 minutes and try your upload again.

*   `DUPLICATE_ORDER_ID`: Multiple conversions sent with the same Order ID in the same batch.
    *   **1. The "Quick Fix": De-duplicate your Batch**
        Before you call `UploadClickConversions`, add a step in your code to filter your list. If you have a list of conversions, use a set or a dictionary in Python to ensure you only keep one entry per unique `order_id`.
        ```python
        # Simple Python de-duplication example
        unique_conversions = {}
        for conv in my_conversions:
            unique_conversions[conv.order_id] = conv
        
        # Now only upload the values of the dictionary
        final_batch = list(unique_conversions.values())
        ```
    *   **2. The "Logic Fix": Why are there duplicates?**
        Check your data source (database or CRM) to see why two records have the same ID.
        *   *User Refresh*: Did the user refresh their "Thank You" page? If so, your system might be recording the same sale twice.
        *   *Loop Error*: Check your code for nested loops that might be appending the same conversion to your upload list multiple times.
    *   **3. The "Batching" Rule**
        Google allows you to send up to 2,000 conversions in a single batch. If you have a very large number of conversions, make sure you aren't accidentally including the same records when you move from "Batch 1" to "Batch 2."
    *   **4. Important Distinction**
        *   *Same Batch*: This error only triggers if the duplicates are in the same request.
        *   *Different Batches*: If you send an Order ID now, and then send it again tomorrow in a different request, you might get a different error (`CONVERSION_ALREADY_EXISTS`) or Google might just silently ignore the second one depending on your settings.
    *   **Summary**: Clean your list before you send it! Google expects every `order_id` in a single API request to be unique.

*   `CLICK_NOT_FOUND`: No click matched the provided user identifiers. (Treat as a warning unless frequent).
    *   **Context**: The `CLICK_NOT_FOUND` error means Google couldn't find an ad click that matches the user information (GCLID, Email, or Phone) you provided. If this happens occasionally, it's often just a "ghost" click or an invalid identifier, but if it happens frequently, here is how to fix it:
    *   **1. Respect the "24-Hour Rule"**
        *   Google needs time to process ad clicks before they can be matched to a conversion.
        *   *The Fix*: Wait at least 24 hours after the click happens before you try to upload the conversion. If you try to upload a conversion 5 minutes after the click, Google will often return `CLICK_NOT_FOUND`.
    *   **2. Check Data Normalization (CRITICAL)**
        *   If you are using Enhanced Conversions (email or phone), the data must be perfectly clean before it is hashed.
        *   *The Fix*:
            1. Trim: Remove all leading/trailing spaces.
            2. Lowercase: Convert all characters to lowercase.
            3. Hash: Use SHA-256 hashing.
            * Example: `User@Example.com` must become `user@example.com` before it is hashed.
    *   **3. Verify GCLID Ownership (Autonomous Action by Gemini)**
        *   The GCLID you are uploading must belong to the exact account you are sending the data to.
        *   *The Fix*: Gemini can automatically query the `click_view` resource to verify if the GCLID is valid for your `customer_id`:
            ```sql
            SELECT click_view.gclid
            FROM click_view
            WHERE click_view.gclid = 'YOUR_GCLID_HERE'
            ```
            If this query returns no results, that GCLID doesn't exist in your account.
    *   **4. Lookback Window**
        *   The click might be too old.
        *   *The Fix*: Check the `click_through_lookback_window_days` for the conversion action. If the click happened 31 days ago but your window is 30 days, Google will treat it as if the click was never found.
    *   **5. Proper Identifier Usage**
        *   *The Fix*: Do not mix identifiers. If you have a GCLID, use it. If you are using Enhanced Conversions, provide the `UserIdentifier`. Do not try to "invent" IDs or send dummy data, as this will trigger the error.
    *   **Summary**: If this is happening to 100% of your uploads, it is almost certainly a hashing/normalization issue or you are uploading too quickly after the click. If it's only happening to 1-2%, it is usually normal behavior (e.g., bot clicks or invalid IDs) and can be ignored.


#### 2.2. Enhanced Conversions for Web
*   `CONVERSION_NOT_FOUND`: Could not find a conversion matching the supplied action and ID/Order ID pair.
    *   **Context**: The `CONVERSION_NOT_FOUND` error occurs when you try to adjust a conversion that Google has no record of. Think of it like trying to "Edit" a document that was never saved. To fix this, check these four areas:
    *   **1. Timing: The "Processing Gap"**
        *   Google needs time to "finalize" a conversion before you can enhance or adjust it.
        *   *The Fix*: Wait at least 24 hours after the original conversion was uploaded (or tracked via the tag) before sending an adjustment or enhancement. If you send them too close together, the adjustment will arrive before the original conversion is "found."
    *   **2. Matching Identifiers (Order ID vs. GCLID)**
        *   You are likely using the wrong "Key" to find the conversion.
        *   *The Fix*: Ensure your `order_id` (also called Transaction ID) and the `conversion_action` ID match exactly what was sent in the original upload.
        *   *Example*: If the original was sent with `order_id`: "SALE123", you cannot adjust it using `order_id`: "sale123" (it is case-sensitive).
    *   **3. Account Ownership**
        *   The adjustment must be sent to the same account that received the original conversion.
        *   *The Fix*: If your original conversion was tracked in Account A, but you are sending the adjustment to Account B (even if they are in the same MCC), Google won't find it.
    *   **4. Conversion Action Consistency**
        *   The adjustment must point to the exact same conversion action.
        *   *The Fix*: If you tracked a sale under the action "Website Purchase," you cannot send an enhancement to "Lead Form Submit" and expect it to find the original sale.
    *   **Summary Checklist**:
        1. Did I wait 24 hours?
        2. Is the `order_id` exactly the same (case-sensitive)?
        3. Am I using the correct `conversion_action` ID?
        4. Am I in the correct Google Ads account?

*   `CUSTOMER_NOT_ACCEPTED_CUSTOMER_DATA_TERMS`: Customer data terms must be accepted in the UI. 
    *   **Context**: To address this error, you must accept the required terms in the Google Ads UI. This cannot be done entirely via the API because it requires a manual legal agreement.
    *   **Why this happens**: This error triggers when you try to use Enhanced Conversions (sending hashed emails or phone numbers). Because you are sending "First-Party Data," Google requires you to legally agree to their data privacy and security policies before they will process the information.
    *   **Step 1: The Fix (Manual Action)**:
        1. Log in to your Google Ads account.
        2. Click the Goals icon (trophy icon) in the left-hand navigation menu.
        3. Navigate to Conversions > Settings.
        4. Find and expand the section labeled Customer data terms.
        5. Click the Review and Accept button.
            * Note: You must have "Admin" or "Standard" access level to see and accept these terms.
        6. Click Save at the bottom of the page.
    *   **Step 2: How to verify it's fixed (Autonomous Action by Gemini)**:
        *   You can run a quick check via the API to confirm the terms are now "Accepted":
            ```sql
            SELECT
              customer.offline_conversion_tracking_info.accepted_customer_data_terms
            FROM customer
            ```

*   `CONVERSION_ALREADY_ENHANCED`: An adjustment for this Order ID and action has already been processed.
    *   **Context**: Google allows you to enhance a conversion (adding email, phone, or address) only once. If you try to update a record that has already been successfully enhanced, you will receive this error.
    *   **1. Check for Duplicate Submissions (The "Only One" Rule)**
        *   *The Fix*: Check your system to see if you are accidentally sending the same enhancement twice. This often happens if your CRM "updates" a record and your script thinks that means it needs to send the data to Google again.
    *   **2. Implement Status Tracking**
        *   Your internal database needs to know which conversions have already been successfully enhanced.
        *   *The Fix*: In your database, add a column named `google_ads_enhanced_at`. Once you get a SUCCESS response from the API, update this column. Before sending new data, filter your query to: `WHERE google_ads_enhanced_at IS NULL`.
    *   **3. Handle "Partial Success" Gracefully**
        *   If you send a batch of 10 enhancements and 5 of them were already enhanced, the API might return this error for those specific 5 while processing the others.
        *   *The Fix*: Inspect the `GoogleAdsException` to see exactly which indices failed. You can safely ignore the `CONVERSION_ALREADY_ENHANCED` errors—it just means the data is already there!
    *   **4. Wait for the Next Sale for New Information**
        *   If you have new information for a customer who already bought something once, you cannot "add" that info to their old sale if it was already enhanced.
        *   *The Fix*: Wait until that customer makes a new purchase with a new Order ID. You can then enhance that new transaction with the updated information.
    *   **Summary**: This error is usually a sign that your automation is too aggressive. It's trying to update records that Google already has all the information for. Simply filtering your data to only send "First-Time Enhancements" will solve the problem.


*   `CONVERSION_ACTION_NOT_ELIGIBLE_FOR_ENHANCEMENT`: This action type cannot be enhanced.
    *   **Context**: This error means you are trying to use Enhanced Conversions (uploading hashed user data like emails) on a conversion action that doesn't support it. Only certain types of actions allow for this kind of "data boost."
    *   **1. Check the "Source" of the Action**
        *   You can only use Enhanced Conversions on actions where Google can actually "see" the customer on your website.
        *   *The Fix*: Ensure the conversion action was created as a Website conversion.
            *   Eligible: WEBPAGE (tracked via the Google Tag).
            *   Not Eligible: IMPORT (standard offline conversions using GCLID only), PHONE_CALL, or STORE_VISIT.
    *   **2. Verify the "Enhanced Conversions" Toggle in the UI**
        *   Even if it's a Website action, you must explicitly "opt-in" for each specific action.
        *   *The Fix*:
            1. Go to the Google Ads UI > Goals > Conversions.
            2. Click on the specific Conversion Action name.
            3. Expand the Enhanced conversions section.
            4. Check the box to Turn on enhanced conversions.
            5. Select your method (API) and Save.
    *   **3. API Query Check (Autonomous Action by Gemini)**
        *   You can check which of your actions are actually eligible using the API. Look for the type and status:
            ```sql
            SELECT
              conversion_action.name,
              conversion_action.type,
              conversion_action.status
            FROM conversion_action
            WHERE conversion_action.type != 'WEBPAGE'
            ```
        *   If you are trying to enhance any of the results from this query, they will fail with this error.
    *   **4. The "Import" Confusion**
        *   If you are doing Offline Conversions (uploading sales from your CRM), you don't "Enhance" them. You just "Upload" them.
        *   *The Fix*: If you are using `UploadClickConversions`, just send the data. You only use the Enhancement or Adjustment methods if you are trying to add data to a conversion that was originally tracked by a website tag.
    *   **Summary**: To fix this, make sure you are only "enhancing" Webpage-based conversion actions and that you have turned on the toggle in the settings for that specific action.


#### 2.3. General Issues
*   `TOO_RECENT_CONVERSION_ACTION`: Wait at least 6 hours after creating a new conversion action before uploading conversions to it.
    *   **Context**: The `TOO_RECENT_CONVERSION_ACTION` error is a simple matter of timing. When you create a new conversion action in Google Ads, the system needs time to propagate that new ID across all its servers.
    *   **The Fix**: Wait 6 to 24 hours. There is no way to bypass this with code or API settings. Google’s infrastructure requires a few hours to "wake up" and recognize that the new conversion action is ready to accept data.
    *   **Best Practices**:
        1. **Plan Ahead**: If you are launching a new campaign on Monday, create the conversion action on Friday or Saturday.
        2. **Test Later**: Don't try to run a "Test Upload" 5 minutes after clicking "Save" in the UI.
        3. **Error Handling**: If your script gets this error, you can build a simple "Retry" logic:
            ```python
            if "TOO_RECENT_CONVERSION_ACTION" in error_message:
                print("Conversion action is too new. Sleeping for 6 hours...")
                # Add logic to move this record to a queue for later
            ```
    *   **Summary**: If you see this error, don't panic and don't change your code. Your code is likely correct; you just need to give the Google Ads system a few more hours to "settle in."

*   `EXPIRED_EVENT`: The click occurred before the conversion action's `click_through_lookback_window_days`.
    *   **Context**: To fix the `EXPIRED_EVENT` error, you need to align your upload data with the "Lookback Window" set for your conversion action. This error means the ad click happened so long ago that Google has already "closed the book" on it.
    *   **1. Increase the Lookback Window (The Easiest Fix)**
        *   If you are regularly uploading conversions that happen 45 days after the click, but your window is set to 30 days, they will all fail.
        *   *The Action*: Go to the Google Ads UI > Goals > Conversions. Click the action and edit the Click-through conversion window.
        *   *Maximum*: You can set this up to 90 days. If your window is already at 90 days and you're still getting this error, it means your sales cycle is too long for Google Ads to track.
    *   **2. Filter your Data Source (The Technical Fix)**
        *   Your script should automatically skip records that are too old to be accepted. This saves you from getting "failed" alerts and keeps your reports clean.
        *   *The Action*: In your SQL query or Python script, calculate the "age" of the click and only include it if it's within the window.
            ```python
            from datetime import datetime, timedelta

            # If your window is 90 days
            lookback_limit = datetime.now() - timedelta(days=90)

            # Only process if click_date is newer than the limit
            if click_date > lookback_limit:
                upload_conversion(click_id)
            else:
                print(f"Skipping {click_id}: Click is too old.")
            ```
    *   **3. Check for Timezone Discrepancies**
        *   Sometimes a click might be right on the edge of the window.
        *   *The Action*: Ensure you are using the correct timezone offset in your upload. If you send the time without an offset (e.g., -05:00), Google might assume it's UTC, which could push a "Day 90" click into "Day 91."
    *   **4. Verify the "Creation" of the GCLID**
        *   Sometimes the GCLID itself is just old data from your CRM that got "stuck."
        *   *The Action*: Check your CRM to see if you are accidentally re-processing old leads from months ago.
    *   **Summary**:
        *   *Quick Fix*: Set the window to 90 days in the UI.
        *   *Long-term Fix*: Update your code to skip clicks that are older than your lookback window.

*   `CONVERSION_PRECEDES_EVENT`: The conversion timestamp is before the click timestamp.
    *   **Context**: The `CONVERSION_PRECEDES_EVENT` error is a logical impossibility. Google is saying: "You're telling me this person bought the item at 1:00 PM, but they didn't even click the ad until 1:30 PM." Here is how to fix this data integrity issue:
    *   **1. Audit your Timestamp Logic (The "Why")**
        *   This almost always comes down to how you are pulling dates from your database.
        *   *The Problem*: You might be comparing the Lead Creation Date (Conversion) with the Click Date, but your Lead Creation Date is being recorded in a different timezone than the Click Date.
        *   *The Fix*: Ensure all timestamps are converted to the same timezone (preferably UTC) before you compare them in your script.
    *   **2. Check for System Clock Desync**
        *   If your web server (which records the click) and your CRM server (which records the sale) have clocks that are even 5 minutes apart, you can trigger this error for fast conversions.
        *   *The Fix*: Use a standard time synchronization service (like NTP) for all your servers.
    *   **3. Implement a "Safety Guard" in Code**
        *   Add a simple check to your script to ensure the conversion happened after the click. If it didn't, don't even try to upload it.
            ```python
            # Simple Python check
            if conversion_time <= click_time:
                print(f"ERROR: Conversion ({conversion_time}) happened before click ({click_time}). Skipping.")
                # You might want to log this to investigate why the data is corrupt
                continue
            ```
    *   **4. Human Error in Manual Uploads**
        *   If you are manually entering dates into a CSV or spreadsheet:
        *   *The Fix*: Double-check for typos (e.g., entering 10:00 instead of 22:00 for a late-night conversion).
    *   **Summary**: To fix this, you must ensure your conversion date is always later than your click date. Usually, this means fixing a timezone mismatch or a clock synchronization issue between your website and your CRM.

*   `DUPLICATE_CLICK_CONVERSION_IN_REQUEST`: The same conversion is repeated in a single batch.
    *   **Context**: The `DUPLICATE_CLICK_CONVERSION_IN_REQUEST` error is very similar to the "Duplicate Order ID" error, but it refers to the Click ID (GCLID) itself. It means you have included the exact same GCLID and Conversion Action combination more than once in the same API request. Here is how to fix it:
    *   **1. De-duplicate your Batch (The Code Fix)**
        *   Before sending your list of conversions to the API, you must ensure that each (GCLID, ConversionAction) pair is unique within that specific batch.
            ```python
            # Use a set to track unique combinations of (GCLID, ActionID)
            unique_batch = []
            seen_combinations = set()

            for conversion in my_list:
                combo = (conversion.gclid, conversion.conversion_action)
                if combo not in seen_combinations:
                    unique_batch.append(conversion)
                    seen_combinations.add(combo)

            # Now send 'unique_batch' to the API
            ```
    *   **2. Identify the "Loop Hole" in your Code**
        *   This error usually happens because of a logic bug in how you are building your upload list:
        *   *Duplicate Database Rows*: Your SQL query might be returning two rows for the same click if it’s joined with multiple products or sessions.
        *   *Nested Loops*: You might be accidentally appending the same conversion object to your list inside a loop.
    *   **3. Difference from DUPLICATE_ORDER_ID**
        *   `DUPLICATE_ORDER_ID`: You sent two different clicks but gave them the same transaction ID.
        *   `DUPLICATE_CLICK_CONVERSION_IN_REQUEST`: You sent the exact same click twice. Even if they have different Order IDs, Google won't allow the same click to convert twice in a single request.
    *   **4. Handling Partial Failures**
        *   If you are using `partial_failure = True` in your API request, the rest of your conversions will still process, but you will see this error for the duplicate entries. You can safely ignore these errors if you know your data source occasionally has duplicates, but it's better to clean the data first to save on API overhead.
    *   **Summary**: To fix this, filter your list of conversions to ensure that no GCLID appears more than once for the same conversion action in a single API call.

### 3. Verification 

1.  **GCLID Ownership**: Query the `click_view` resource to verify if a GCLID belongs to the specific customer account.
2.  **Customer Terms**: Check `customer.offline_conversion_tracking_info.accepted_customer_data_terms` via the `customer` resource.
3.  **Data Normalization**: Ensure email addresses, phone numbers, and names are correctly normalized (trimmed, lowercased) and hashed (SHA-256) before sending.
4.  **Consent**: Verify that `ClickConversion.consent` is properly set in the upload if required by regional policies.
5.  **Logical Time Verification**: Before uploading any conversion, you MUST verify that the `conversion_date_time` is logically valid:
    *   **Normalization**: Ensure both click and conversion timestamps are in the same timezone (preferably UTC) before comparing.
    *   **No Pre-Click Conversions**: The conversion timestamp MUST be strictly after the click timestamp to avoid `CONVERSION_PRECEDES_EVENT`.
    *   **Lookback Window**: The click MUST have occurred within the `click_through_lookback_window_days` defined for the conversion action to avoid `EXPIRED_EVENT`.
6.  **No OR Operator (CRITICAL)**: GAQL does not support the `OR` operator in the `WHERE` clause. You **MUST** perform multiple separate queries or filter results in code to achieve "OR" logic.

### 4. Troubleshooting Workflow

1.  **MANDATORY FIRST STEP: Diagnostic Summaries**: Before investigating specific errors or identifiers, you **MUST** execute queries against `offline_conversion_upload_client_summary` and `offline_conversion_upload_conversion_action_summary`. These resources provide the most accurate view of recent import health and systemic failures.
2.  **Check API Error Details**: Inspect the `GoogleAdsException` for specific `ErrorCode` and `message`.
3.  **Verify Timestamps**: Ensure `conversion_date_time` is in `yyyy-mm-dd hh:mm:ss+|-hh:mm` format and falls within the lookback window.
4.  **Validate Identifiers**: For `CLICK_NOT_FOUND`, ensure you are not mixing `gclid` with `gbraid` or `wbraid` inappropriately. Use only one per conversion.
5.  **Wait for Processing**: Conversions can take up to 3 hours to appear in reporting after a successful upload.
6.  **Check Conversion Settings**: Ensure the conversion action's `status` is `ENABLED` and it is configured for the correct `type`.

#### 4.1. General Troubleshooting
- **Conversions:**
    - Use `offline_conversion_upload_conversion_action_summary` and `offline_conversion_upload_client_summary` for recent conversion import issues.
    - Refer to official documentation for discrepancies and troubleshooting.

### 5. Output and Documentation

#### 5.1. References
- **Conversion Docs:** `https://developers.google.com/google-ads/api/docs/conversions/`
