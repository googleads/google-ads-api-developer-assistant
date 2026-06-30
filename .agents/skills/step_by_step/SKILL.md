---
name: step-by-step
description: Breaks down complex tasks into a structured, numbered list of actionable steps with a verification phase.
---

# Step-by-Step Process

Use this skill to explain how to perform a task, configure a setting, or execute a workflow. This ensures the user receives clear, logical, and actionable guidance.

## Protocol

When asked to provide a step-by-step guide, you MUST structure your response following these rules:

1.  **Logical Ordering:** Chronologically order the steps. Group them under headers (e.g., `## Phase 1: Setup`) if the process is complex.
2.  **Actionable Language:** Start each numbered step with an imperative verb (e.g., *Create*, *Configure*, *Run*, *Verify*).
3.  **Numbered List:** Use strict numbered list formatting (`1.`, `2.`, `3.`).
4.  **Verification Step [MANDATORY]:** You MUST include a final step or section explicitly titled **"Verification"** explaining how the user can verify that the task was completed successfully.

---

## Example Explanation

**Task:** How to retrieve campaign details using GAQL.

1.  **Initialize Client:** Load the `GoogleAdsClient` using your configuration file.
2.  **Construct Query:** Write a GAQL query to select the desired campaign fields.
    ```sql
    SELECT campaign.id, campaign.name, campaign.status FROM campaign LIMIT 10
    ```
3.  **Execute Search:** Call the `GoogleAdsService.search` method, passing your customer ID and the query.
4.  **Iterate Results:** Loop through the returned row set and print the campaign details.
5.  **Verification:** Verify the output by checking that the printed campaign IDs match the expected campaigns in your Google Ads UI.
