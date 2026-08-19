---
description: Breaks down complex Google Ads API tasks into sequential, structured steps.
argument-description: <task_description> The Google Ads API task or workflow to break down
---

# Step-by-Step Workflow (`/step-by-step`)

Deconstructs complex Google Ads API development processes into sequential phases with prerequisites, GAQL queries, and code templates.

## Instructions:
1. **Extract Parameters**:
   - Extract the task or workflow description from `$ARGUMENTS`.
   - If not provided, prompt the user for the process they want to break down.

2. **Format Response**:
   - **Phase Breakdown**: Split the workflow into logical phases (Discovery, Preparation, Execution, Verification).
   - **Prerequisites**: Note required permissions, credentials, and target API version.
   - **GAQL & Code**: Provide validated GAQL queries and Python code snippets for each phase.
   - **Read-Only / Mutate Safety**: Note any mutate operations requiring manual review and execution.
