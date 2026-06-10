# Testing `step_by_step` Skill

This document outlines the evaluation and verification workflows for the `step_by_step` skill.

## 1. Automated Evaluation (`EVAL.txtpb`)

The `EVAL.txtpb` file defines a standardized verification case to evaluate model compliance with the step-by-step instructions. It asserts that when a user asks to explain a process step-by-step, the model:
1. Formats its response as a clear, numbered list (`1.`, `2.`, `3.`).
2. Includes a final **`Verify`** (or Verification) step to explain how the user can verify that the process was completed successfully.

## 2. Manual Verification

To manually verify that the `step_by_step` skill functions correctly:
1. Prompt the assistant with:
   ```
   Explain step by step how to create a search campaign in Google Ads API
   ```
2. Verify that the explanation:
   - Is formatted strictly as a numbered list.
   - Presents actionable steps in a logical, chronological order.
   - Ends with a clear verification step explaining how to check if the campaign was created successfully (e.g., using search queries or the UI).
