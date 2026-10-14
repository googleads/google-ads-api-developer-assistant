---
description: Starts an interactive, conversational tutorial on using the Google Ads API Developer Assistant.
argument-description: [topic_number] Optional topic number (1-16) to jump to
---

# Assistant Tutorial (`/assistant-tutorial`)

Launches an interactive, conversational guide explaining the principles, workflows, and tools of the Google Ads API Developer Assistant.

## Instructions:
1. **Interactive Delivery Mandate**:
   - Do NOT write a markdown summary file or artifact.
   - Run the tutorial interactively and conversationally.
   - Present information in small, progressive steps.

2. **Topic Outline**:
   1. Core Principles, Configuration (`config/assistant_config`) & Credential Isolation (`config_init.py`)
   2. Campaign Creation & Cryptographic 4-Step HITL Mutation Workflow (`/execute-mutation`)
   3. Shared Sets (Exclusion Lists)
   4. Code Quality & Standards (Ruff, typing, error handling)
   5. Finding Disapproved Ads (Cross-Account Audit & `/get-cids`)
   6. Creating an AI Max for Search Campaign
   7. Creating a Demand Gen Campaign
   8. Writing Prompts to Produce Reports & GAQL Validation Caching (`/validate-gaql`)
   9. Troubleshooting Conversion Problems & GCLID Sampling (`/troubleshoot-conversions`)
   10. Obtaining Descriptions of API Concepts, Protobuf Inspection & Version Parity (`/explain` & `/inspect-object`)
   11. Creating Listing Filters for Performance Max (`/pmax-filter`)
   12. Synchronizing Client Libraries & Assistant Releases (`/sync-client-libs`)
   13. Extension & Dynamic 5-Tier API Version Resolution (`/ext-version`)
   14. Step-by-Step Workflow Breakdown (`/step-by-step`)
   15. Lifecycle Hooks & Deterministic Guardrails (`hooks.json` & `config_init.py`)
   16. Agent-to-Agent (A2A) Sidecar Service & Cross-Workspace Execution

3. **Check Questions & Explanations**:
   - After explaining a topic, prompt the user to continue or quiz their understanding.
   - Always allow the user to request an explanation if needed.
