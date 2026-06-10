# Testing `validate_gaql` Skill

This document outlines the automated testing strategy and manual verification workflows for the `validate_gaql` skill.

## 1. Unit Tests

The unit test suite validates the GAQL validation script logic, including:
- Correct validation using the Google Ads API `validate_only` parameter.
- Static rules validation (e.g., blocking forbidden `OR` operators, ensuring referenced `WHERE` fields are `SELECT`ed).
- Proper extraction and display of API error codes and error messages when a dry run fails.

### Running Unit Tests
Execute the test suite within the sequestered virtual environment:
```bash
./.venv/bin/python3 -m unittest discover -s .agents/skills/validate_gaql/tests
```

## 2. Automated Evaluation (`EVAL.txtpb`)

The `EVAL.txtpb` file defines standardized evaluation test cases to evaluate skill invocation. It verifies that when a user requests to validate a GAQL query, the assistant correctly:
1. Invokes the validation script via `run_command` using the sequestered Python virtual environment.
2. Extracts the query string, customer ID, and API version parameters from user context or input.

## 3. Manual Verification

To manually verify the skill within an active session:
1. Input the prompt:
   ```
   Validate the query SELECT campaign.id, campaign.name FROM campaign for customer 1234567890
   ```
2. Verify that the assistant runs the validator script, performs a structural validation check, and reports:
   ```
   SUCCESS: GAQL query is structurally valid.
   ```
