# README: Google Ads API Developer Assistant (Gemini CLI Extension)

**TL;DR:** This extension for the Gemini CLI lets you interact with the Google Ads API using natural language. Ask questions, generate GAQL and Python code, and execute API calls that read directly in your terminal.

## Overview

The Google Ads API Developer Assistant enhances the Gemini CLI to streamline workflows for developers working with the Google Ads API. Use natural language prompts to:

*   Get answers to Google Ads API questions.
*   Construct Google Ads Query Language (GAQL) queries.
*   Generate executable Python code using the `google-ads-python` client library for context.
*   Retrieve and display data from the API.

This extension leverages `gemini-cli`'s ability to use `GEMINI.md` files and the settings in `.gemini/settings.json` to provide persistent context, making interactions more efficient.

## Key Features

*   **Natural Language Q&A:** Ask about Google Ads API concepts, fields, and usage in plain English.
    *   *"What are the available campaign types?"*
    *   *"Tell me about reporting for Performance Max campaigns."*
    *   *"How do I filter by date in GAQL?"*

*   **Natural Language to GAQL & Python Code:** Convert requests into ready-to-run Python code.
    *   Code is saved to `saved_code/`.
    *   *"Show me campaigns with the most conversions last 30 days."*
    *   *"Get all ad groups for customer '123-456-7890'."*
    *   *"Find disapproved ads across all campaigns."*

*   **Direct API Execution:** Run the generated Python code from the CLI and view results, often formatted as tables.

*   **CSV Export:** Save tabular API results to a CSV file in the `saved_csv/` directory.
    *   *"Save results to a csv file"*

## Prerequisites

1.  Familiarity with Google Ads API concepts and authentication.
2.  A Google Ads API developer token.
3.  A configured `google-ads.yaml` credentials file in your home directory (see [google-ads-python docs](https://github.com/googleads/google-ads-python/blob/main/google-ads.yaml)).
4.  Gemini CLI installed (see [Gemini CLI docs](https://github.com/google-gemini/gemini-cli)).
5.  A local clone of the [google-ads-python](https://github.com/googleads/google-ads-python) client library. Clone this in a directory that is NOT under the Google Ads API Developer Assistant project directory.
6.  Python >= 3.10 installed and available on your system PATH.

## Setup Guide

1.  **Install Gemini CLI:** Ensure that [Gemini CLI](https://github.com/google-gemini/gemini-cli) is installed.

2.  **Clone Google Ads Python Library:** Clone the [google-ads-python](https://github.com/googleads/google-ads-python) repository to a local directory (e.g., `$HOME/path/to/google-ads-python`) that is not under the Google Ads API Developer Assistant project directory. This provides context for code generation.

3.  **Configure Credentials:** Make sure your [google-ads.yaml](https://github.com/googleads/google-ads-python/blob/main/google-ads.yaml) file with API credentials is in your `$HOME` directory.

4.  **Clone the Extension:** `git clone https://github.com/googleads/google-ads-api-developer-assistant`. This becomes your project directory. You need to be in this directory when you run gemini-cli.

5.  **Set Context in Gemini:** The `gemini` command must be run from the root of the `google-ads-api-developer-assistant` project directory. Configure the context paths in `.gemini/settings.json`:
    *   Edit `/path/to/your/google-ads-api-developer-assistant/.gemini/settings.json`.
    *   Add the **full absolute paths** to the `context.includeDirectories` array:
        *   Your `google-ads-python` library clone.
        *   The `api_examples` directory within this project.
        *   The `saved_code` directory within this project.

    **Example `.gemini/settings.json`:**
    ```json
    {
      "context": {
        "includeDirectories": [
          "/path/to/your/google-ads-api-developer-assistant/api_examples",
          "/path/to/your/google-ads-api-developer-assistant/saved_code",
          "/path/to/your/google-ads-python"
        ]
      }
    }
    ```
    *Note: Replace the placeholder paths with the actual absolute paths on your system.*

6.  **Optional: Default Customer ID:** To set a default customer ID, create a file named `customer_id.txt` in the `google-ads-api-developer-assistant` directory with the content `customer_id=YOUR_CUSTOMER_ID` (e.g., `customer_id=1234567890`). You can then use prompts like *"Get campaigns for the default customer"*.

## Usage Examples

1.  **Start Gemini CLI:**
    ```bash
    cd /path/to/google-ads-api-developer-assistant
    gemini
    ```

2.  **Ask a question:**
    > "What are the resource names for my enabled campaigns sorted by campaign id"

3.  **Generate Code:**
    > "Get me the top 5 campaigns by cost last month for customer 1234567890"

4.  **Execute and Save:**
    > "Run the code"
    > ... (results displayed) ...
    > "Save the results to csv"

## Directory Structure

*   `google-ads-api-developer-assistant/`: Root directory. **Launch `gemini` from here.**
*   `.gemini/`: Contains `settings.json` for context configuration.
*   `api_examples/`: Contains example API request/response files.
*   `saved_code/`: Stores Python code generated by Gemini.
*   `saved_csv/`: Stores CSV files exported from API results.
*   `customer_id.txt`: (Optional) Stores the default customer ID.

## Known Quirks

*   The underlying model may have been trained on an older API version. It might occasionally generate code with deprecated fields. Execution errors often provide feedback that allows Gemini CLI to self-correct on the next attempt, using the context from the `google-ads-python` client library.

## Contributing

Please see `CONTRIBUTING.md` for guidelines on reporting bugs, suggesting features, and submitting pull requests.

## Support

Use the GitHub Issues tab for bug reports, feature requests, and support questions.

## License

Apache License 2.0. See the `LICENSE` file.
