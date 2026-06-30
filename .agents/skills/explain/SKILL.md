---
name: explain
description: Explains Google Ads API concepts, code snippets, or queries using plain language and analogies.
---

# Explain

Use this skill to explain Google Ads API concepts, code snippets, or queries. This ensures explanations are accessible to both technical and non-technical stakeholders while maintaining technical accuracy.

## Protocol

When asked to explain a concept, you MUST structure your response with the following four sections:

### 1. The Big Picture
Provide a high-level summary of the fundamental problem this concept solves for the entire system. Limit this to 1-2 direct sentences.

### 2. Analogy [MANDATORY]
You MUST use a real-world, non-technical analogy to explain the concept. Map the technical components to everyday objects or processes.
*   *Constraint:* Do not use technical jargon in the analogy itself.

### 3. Interconnectedness
Describe how this concept interacts with other core components of the Google Ads API. Mention specific resources or services it links to.

### 4. Simple Language
Create a distinct section titled "Simple Language" to summarize the concept in a way that is accessible to non-technical users, without losing technical correctness.

---

## Example Explanation

**Concept:** `click_view`

### The Big Picture
`click_view` retrieves performance metrics at the individual click level, allowing advertisers to trace conversions back to the specific click event.

### Analogy
Think of a standard report as your monthly credit card statement summary (which only shows the total spent). `click_view` is the **itemized receipt** from a specific store visit, showing exactly what was bought, when, and the exact price for that single transaction.

### Interconnectedness
It links directly to `campaign` and `ad_group` via their resource names, allowing you to associate individual click data with the hierarchy of your ad account.

### Simple Language
It lets you see details for every single click on your ad, rather than just summaries of clicks over time.
