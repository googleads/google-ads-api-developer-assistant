---
description: Explains Google Ads API concepts, fields, or resources using plain language and real-world analogies.
argument-description: <concept> The Google Ads API concept, resource, metric, or segment to explain
---

# Explain Concept (`/explain`)

Provides a 4-part structured explanation of any Google Ads API concept or component.

## Instructions:
1. **Extract Parameters**:
   - Extract the concept name from `$ARGUMENTS` (e.g. `click_view`, `bidding_strategy`, `ad_group_ad`, `change_status`).
   - If not provided, ask the user which Google Ads API concept they would like explained.

2. **Structure the Explanation [MANDATORY 4 SECTIONS]**:
   - **### 1. The Big Picture**: 1-2 sentences summarizing the fundamental problem this concept solves.
   - **### 2. Analogy [MANDATORY]**: A clear, non-technical everyday analogy without jargon.
   - **### 3. Interconnectedness**: How this concept interacts with other Google Ads API resources and services.
   - **### 4. Simple Language**: Summary accessible to non-technical stakeholders while preserving technical correctness.
