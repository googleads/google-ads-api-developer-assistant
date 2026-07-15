---
name: assistant-tutorial
description: An interactive tutorial on how to use the Google Ads API Developer Assistant.
---

# Google Ads API Developer Assistant Tutorial (Interactive Guide)

## Critical Directive for the Agent
When a user invokes `/assistant-tutorial` or requests this tutorial:
1. **NO MD SYNOPSIS FILES:** You MUST NOT write any markdown files or artifacts summarizing the tutorial.
2. **ALWAYS INTERACTIVE:** You MUST run this tutorial as an interactive, conversational experience.
3. **TOPIC SELECTION:** Start by asking the user which specific topic they want to learn about first using the `ask_question` tool.
4. **PROGRESSIVE DISCLOSURE:** Present information in small, manageable pieces. Ask checking questions or prompt the user to proceed before moving on to the next step.

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
