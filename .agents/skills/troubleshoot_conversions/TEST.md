# Testing `troubleshoot_conversions` Skill

This document outlines the automated testing strategy and manual verification workflows for the `troubleshoot_conversions` skill.

## 1. Unit Tests

The unit test suite validates the core diagnostic logic, including:
- Customer tracking settings inspection (verifying accepted customer data terms).
- Client summary stream processing and daily upload total calculations (`successful + failed + pending`).
- Conversion action summary stream processing and alert unpacking (inspecting the `alert.error` oneof structure).
- Consolidated report file generation adhering to the mandatory 4-part numbered structure.

### Running Unit Tests
Execute the test suite within the sequestered virtual environment:
```bash
./.venv/bin/python3 -m unittest discover -s .agents/skills/troubleshoot_conversions/tests
```

## 2. Automated Evaluation (`EVAL.txtpb`)

The `EVAL.txtpb` file defines standardized evaluation test cases for the skill compatible with evalin. It verifies that when a user requests conversion troubleshooting, the assistant correctly:
1. Invokes the diagnostic script via `run_command`.
2. Formats its response using the required headers (`Introductory Analysis`, `Primary Errors`, `General Health`, `Actionable Recommendations`).

## 3. Manual Verification

To manually verify the skill within an active session:
1. Start the assistant terminal in the project root.
2. Input the prompt: `Troubleshoot my conversions for customer 1234567890`
3. Verify that the assistant executes the script, displays high-level summaries on screen, and writes the consolidated report to `saved/data/conversion_troubleshooting_report_<epoch>.txt`.
