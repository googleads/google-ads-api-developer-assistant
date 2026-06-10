# Testing `explain` Skill

This document outlines the evaluation and verification workflows for the `explain` explanation skill.

## 1. Automated Evaluation (`EVAL.txtpb`)

The `EVAL.txtpb` file defines a standardized verification case to evaluate model compliance with the structured explanation layout instructions. It asserts that when a user asks to explain a concept, the model strictly structures its output into four sections:
1. **The Big Picture**: A concise 1-2 sentence summary of the fundamental problem the concept solves for the Google Ads ecosystem.
2. **Analogy**: A real-world metaphor that explains how the concept functions.
3. **Interconnectedness**: How the resource/concept interacts with other core elements of the Google Ads API.
4. **Simple Language**: An accessible but technically accurate breakdown.

## 2. Manual Verification

To manually verify that the `explain` skill functions correctly:
1. Prompt the assistant with:
   ```
   Explain the concept of click_view and how it is used in Google Ads API
   ```
2. Verify that the explanation:
   - Is direct, zero-filler, and avoids generic introductions.
   - Adheres to the 4 required structured section headings.
   - Uses an easy-to-understand real-world analogy rather than dry code syntax.
