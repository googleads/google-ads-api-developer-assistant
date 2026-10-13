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
3. **TOPIC SELECTION:** Start by asking the user which specific topic they want to learn about first using an interactive question or message.
4. **PROGRESSIVE DISCLOSURE:** Present information in small, manageable pieces. Ask checking questions or prompt the user to proceed before moving on to the next step.
5. **EXPLAIN ANSWER OPTION:** Whenever you pose an interactive check question or quiz to the user, include a choice/option that allows them to ask the Assistant to answer and explain the answer.

---

## Tutorial Content Reference

### Topic 1: Core Principles & Constraints
- **4-Step HITL Mutation Guard (`execute_mutates`):** By default, live mutations are disabled (`execute_mutates = false` in `config/assistant_config`), and generated code is saved in `saved/code/`. When enabled (`execute_mutates = true`), every write operation must pass the mandatory 4-Step Human-in-the-Loop (HITL) Verification & Consequence Disclosure Protocol (GAQL before-state lookup, `validate_only=True` dry-run receipt in `saved/data/last_dry_run.json`, explicit consequence disclosure, and `PreToolUse` hook-gated execution logged to `saved/logs/mutation_audit.jsonl`).
- **API Versioning:** All code and GAQL queries target the confirmed version in `config/assistant_config`.

### Topic 2: Campaign Creation (Code Generation & HITL Mutation Workflow)
- Explain the generation & 4-Step HITL verification workflow.
- Show standard template structures supporting `--dry-run` (`validate_only=True`) and `--execute`.
- **HITL Safety & Consequence Disclosure:** Remind the user that live mutations require `execute_mutates = true` in `config/assistant_config`, a verified `validate_only=True` dry-run receipt, and explicit user confirmation of financial and serving consequences.

### Topic 3: Shared Sets (Exclusion Lists)
- Explain `SharedSet` (reusable keyword/placement exclusion folders), `SharedCriterion` (items), and `CampaignSharedSet` (connector).
- Describe relationships and benefits.

### Topic 4: Code Quality & Standards
- Detail automated linting (`ruff`), type annotations, and error handling (`GoogleAdsException` wrapper) that the assistant enforces.

### Topic 5: Finding Disapproved Ads (Cross-Account Audit)
- Phase 1: Determine Parent Manager Account (MCC) using `customer_manager_link`.
- Phase 2: Retrieve child accounts recursively using `get_cids_under_mcc` script.
- Phase 3: Query disapproved ads via `ad_group_ad` resource.

### Topic 6: Creating an AI Max for Search Campaign
- **What is AI Max?** Refers to "AI Max for Search campaigns", NOT "Performance Max" campaigns.
- **Enabling AI Max:** Set `ai_max_setting.enable_ai_max = True` on the `Campaign` resource.
- **Campaign Configuration:** `advertising_channel_type = SEARCH`, budget, bidding strategy like Maximize Conversions.
- **Ad Creation:** RSA in `AdGroupAd` using `ResponsiveSearchAdInfo`.

### Topic 7: Creating a Demand Gen Campaign
- **What is Demand Gen?** Drives action across YouTube, Discover, and Gmail using image and video assets.
- **Campaign Configuration:** `advertising_channel_type = DEMAND_GEN`.
- **Ad Group Settings:** `demand_gen_ad_group_settings.channel_controls.selected_channels`.

### Topic 8: Writing Prompts to Produce Reports
- **Prompting Best Practices:** Define main resource, specify metrics, request date/device segments.
- **GAQL Validation Protocol:** Programmatic 4-step sequence (Schema Discovery, Compatibility Check, Static Analysis, Runtime Dry Run).

### Topic 9: Troubleshooting Conversion Problems
- **Diagnostic Protocol:** Run `troubleshoot_conversions.py` for conversion upload issues.
- **Pre-Upload Validation:** Run `validate_conversion_upload.py` to validate CSV formatting and logical time checks before uploading.

### Topic 10: Obtaining Descriptions of API Concepts and Objects
- **Conceptual Explanations:** Use `/explain` or ask for high-level summaries structured with Big Picture, Analogy, Interconnectedness, and Simple Language.
- **Structural Inspection:** Use `inspect_object.py` to view raw field definitions, types, and Enum values.

### Topic 11: Creating a Listing Filter for a Performance Max (PMax) Campaign
- **Webpage Listing Filter:** Configure webpage exclusion listing trees (`vertical = WEBPAGE`) using `create_pmax_webpage_filter.py`.
