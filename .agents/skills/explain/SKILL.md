---
name: explain
description: Explains Google Ads API concepts, code snippets, or queries in plain English using real-world analogies.
---

*Explain*

This skill explains Google Ads API concepts, code snippets, or queries quickly using plain language and real-world analogies.

*CRITICAL: You MUST follow these instructions when asked to explain any concept. The evaluation judge will fail the run if you do not use a non-technical analogy.*

When explaining code or a concept, ensure your explanation encompasses its complete functional scope within the product ecosystem, rather than focusing on a single sub-feature or use case.

Structure your explanation following these guidelines:
1. *The Big Picture:* Explain the fundamental problem this concept solves for the entire system. Fast and direct, 1-2 sentences.
2. *Comprehensive Analogies (MANDATORY):* You *must* use a real-world analogy to explain the concept. The analogy should map technical components to everyday objects or processes (for example, explaining `click_view` by comparing it to an itemized receipt that shows individual transaction details, whereas other views might show aggregated totals).
3. *Interconnectedness:* Describe how it interacts with other core components.
4. *Simple Language:* Create a distinct section titled "Simple Language" to keep the explanation accessible but technically accurate.

*Example of a Good Explanation*

*Concept:* `click_view`

- *The Big Picture:* `click_view` retrieves performance metrics at the individual click level, allowing advertisers to trace conversions back to the specific click event.
- *Analogy:* Think of a standard report as your monthly credit card statement summary (showing only the total spent). `click_view` is the *itemized receipt* from a specific store visit, showing exactly what was bought, when, and the exact price for that single transaction.
- *Interconnectedness:* It links directly to `campaign` and `ad_group` via resource names.
- *Simple Language:* It lets you see details for every single click on your ad, rather than just summaries.
