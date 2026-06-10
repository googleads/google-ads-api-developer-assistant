# Google Ads API Developer Assistant

**TL;DR:** This assistant lets you interact with the Google Ads API using natural language. Ask questions, generate GAQL and code in several languages, and execute API calls directly in your terminal.

## Overview

The Google Ads API Developer Assistant streamlines workflows for developers working with the Google Ads API. Use natural language prompts to:

*   Get answers to Google Ads API questions.
*   Construct Google Ads Query Language (GAQL) queries.
*   Generate executable code in several languages using our client libraries for context.
*   Retrieve and display data from the API.

This assistant is powered by the **antigravity** agent framework (v3.0.0) and leverages `AGENTS.md` files and custom **Skills** to deliver persistent context, robust safety constraints, and automated execution pipelines.

## Agentic Design & Approach

The Assistant uses a structured hierarchy of instruction files and specialized domain tools to ensure safe, precise, and highly competent interactions with the Google Ads API.

### 1. Unified Context via `AGENTS.md`
The master configuration file [AGENTS.md](AGENTS.md) acts as the system contract for the assistant. It sets zero-tolerance policies (such as a read-only constraint on mutating API calls) and defines execution pipelines:
*   **Version Cache Protocol**: Auto-loads API versions from `config/api_version.txt`.
*   **Code Generation Pipeline**: Passes all generated Python code through strict `ruff` linting before saving or displaying it.
*   **Programmatic GAQL Validation**: Evaluates queries against field metadata and compatibility boundaries.

### 2. Domain-Specific "Skills"
Rather than relying on generic AI completions, the assistant is empowered with specialized, test-backed tool directories called **Skills** under `.agents/skills/`. Each skill defines:
*   `SKILL.md`: Human-in-the-loop and model instructions.
*   `scripts/`: Python modules that interface directly with the Google Ads API Client Libraries (e.g., validating queries, navigating account trees, filtering Performance Max URL expansions).
*   `tests/`: Unit test suites validating skill operations.

Key active skills include:
*   **`validate_gaql`**: Dry-runs queries via the API `validate_only` parameter.
*   **`inspect_object`**: Inspects API resources, nested messages, or enum definitions on the fly.
*   **`get_cids_under_mcc`**: Maps client hierarchies under manager accounts.
*   **`troubleshoot_conversions`**: Investigates upload summaries and pre-validates files.
*   **`pmax_listing_filter`**: Standardizes listing group webpage exclusion tree modifications.
*   **`explain`** & **`step_by_step`**: Enforces structured explanation layouts.

## Key Features

*   **Natural Language Q&A:** Ask about Google Ads API concepts, fields, and usage in plain English.
    *   *"What are the available campaign types?"*
    *   *"Tell me about reporting for Performance Max campaigns."*
    *   *"How do I filter by date in GAQL?"*

*   **Natural Language to GAQL & Client Library Code:** Convert requests into executable code using the Google Ads Client Libraries.
    *   Code is saved to `saved/code/`.
    *   *"Show me campaigns with the most conversions last 30 days."*
    *   *"Get all ad groups for customer '123-456-7890'."*
    *   *"Find disapproved ads across all campaigns."*

*   **Direct API Execution:** Run the generated Python code directly and view results, often formatted as tables. Execution takes place within a managed virtual environment that has the Google Ads API Client Libraries installed.

*   **CSV Export:** Save tabular API results to a CSV file in the `saved/csv/` directory.
    *   *"Save results to a csv file"*

*   **Conversion Troubleshooting & Diagnostics:** Generate structured diagnostic reports to debug offline conversion issues.
    *   Reports are saved to `saved/data/`.
    *   *"Troubleshoot my conversions for customer '123-456-7890'."*
    
*   **Validate Complex GAQL Queries:** Validate complex GAQL queries to ensure they are valid and will return the expected results. The Assistant enforces strict validation rules, such as prohibiting the use of the `OR` operator in GAQL queries and the `FROM` clause in metadata queries.
    *   *"validate:"*
        ```sql
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          campaign.advertising_channel_type,
          ad_group.id,
          ad_group.name,
          ad_group.status,
          ad_group_ad.ad.id,
          ad_group_ad.status,
          ad_group_ad.ad.type,
          ad_group_ad.policy_summary.policy_topic_entries,
          metrics.clicks,
          metrics.impressions,
          metrics.cost_micros,
          metrics.conversions,
          segments.date
        FROM ad_group_ad
        WHERE campaign.status = 'ENABLED'
          AND ad_group.status = 'ENABLED'
          AND ad_group_ad.status = 'ENABLED'
          AND segments.date DURING LAST_30_DAYS
          AND metrics.impressions > 100
        ORDER BY metrics.clicks DESC
        LIMIT 500
        ```

## Supported Languages

*   Python
*   PHP
*   Ruby
*   Java
*   C# (.NET)

Code generated by Python, PHP, and Ruby can be executed directly. Code generated by Java and C# must be compiled and executed separately. This is because of security policies. For C# code generation, use 'in dotnet' to set the context.

By default, Python is used for code generation.  As of v2.3.0 you can provide context from your project files using the `context_dir` flag: `./update.sh --context_dir /path/to/your/codebase`. This allows Gemini to include your application logic in its reasoning when creating responses.  This feature enables the Assistant to produce saved code examples in your chosen language, providing support even when an official client library is unavailable.
   * Before requesting code output, tell the Assistant: `write saved code examples in <language of your application>`

## Prerequisites

1.  Familiarity with Google Ads API concepts and authentication.
2.  A Google Ads API developer token.
3.  A configured credentials file in your home directory if using Python (`google-ads.yaml`), PHP (`google_ads_php.ini`), or Ruby (`google_ads_config.rb`).
4.  Antigravity environment configured.
5.  A local clone of each client library for the languages you want to use. `install.sh` (Linux/macOS) or `install.ps1` (Windows) can set this up for you.
6.  Python >= 3.10 installed and available on your system PATH. This is required for executing the default generated Python code directly.

## Setup

1.  **Install Antigravity CLI:** Download and install `antigravity-cli` from [https://antigravity.google/](https://antigravity.google/).

2.  **Clone the Assistant:** `git clone https://github.com/googleads/google-ads-api-developer-assistant`. This becomes your project directory.

3.  **Run install script**
    *   **Linux/macOS:**
        *   Ensure that [jq](https://github.com/jqlang/jq?tab=readme-ov-file#installation) is installed.
        *   Run `./install.sh`.
            *   By default (no arguments), this installs the **Python** client library to the `client_libs/` directory within this project.
            *   To install additional languages, use flags: `./install.sh --php --ruby --dotnet`.
            *   Execute `./install.sh --help` for more details.
    *   **Windows:**
        *   Open PowerShell and run `.\install.ps1`.
            *   By default, this installs the **Python** client library to the `client_libs\` directory within this project.
            *   To install additional languages, use parameters: `.\install.ps1 -Php -Ruby -Dotnet`.
4.  **Configure Credentials:** Make sure your API credentials configuration files are in your `$HOME` directory. Each language has its own configuration file naming convention and structure. 
5.  **Optional: Default Customer ID:** To set a default customer ID, create a file named `customer_id.txt` in the `google-ads-api-developer-assistant` directory with the content `customer_id:YOUR_CUSTOMER_ID` (e.g., `customer_id: 1234567890`). You can then use prompts like *"Get my campaigns"* and the Assistant will use the CID for the request.
6.  **Google Ads API Version Validation:** On your first run in a session, the assistant will automatically identify the latest stable Google Ads API version and ask you to confirm it. Once confirmed, this version is cached in [api_version.txt](file:///usr/local/google/home/rwh/google-ads-api-developer-assistant/config/api_version.txt) and used for all subsequent prompts. If you need to force a version change or refresh the cache, simply delete or edit the `config/api_version.txt` file.

### Adding Custom Codebases for Context

To provide the assistant with additional context (such as your own codebase or custom client library paths), use the `update.sh` (Linux/macOS) or `update.ps1` (Windows) script with the context path argument.

*   **Linux/macOS:**
    ```bash
    ./update.sh --context_path /path/to/your/custom/codebase
    ```
*   **Windows:**
    ```powershell
    .\update.ps1 -ContextPath C:\path\to\your\custom\codebase
    ```

This registers the specified directory under the global project configuration in `~/.gemini/config/projects/` to ensure it is loaded as context on each invocation of the assistant.

    **By default, Python is used for code generation.  As of v2.3.0 you can provide context from your project files using the `context_dir` flag: `./update.sh --context_dir /path/to/your/codebase`. This allows Gemini to include your application logic in its reasoning when creating responses.  This feature enables the Assistant to produce saved code examples in your chosen language, providing support even when an official client library is unavailable.
   * Before requesting code output, tell the Assistant: `write saved code examples in <language of your choice>`
## Usage

1.  **Start Antigravity Session:**
    ```bash
    cd /path/to/google-ads-api-developer-assistant
    ```
    Ask questions, generate code, and validate queries within your Antigravity terminal session.

2.  **Ask a question:**
    > "What are the resource names for my enabled campaigns sorted by campaign id"

3.  **Generate Code:**
    > "Get me the top 5 campaigns by cost last month for customer 1234567890"

4.  **Execute and Save:**
    > "Run the code"
    > ... (code displayed as the result of a previous request) ...
    > "Save the results to csv"


## Directory Structure

*   `google-ads-api-developer-assistant/`: Root directory.
*   `.agents/`: Contains hooks, skills, and configuration files for the agent.
*   `api_examples/`: Contains example API request/response files.
*   `saved/code/`: Stores Python code generated by the assistant.
*   `saved/csv/`: Stores CSV files exported from API results.
*   `saved/data/`: Stores diagnostic and troubleshooting reports.
*   `customer_id.txt`: (Optional) Stores the default customer ID.

## Mutate Operations

The Assistant is designed to generate code for mutate operations (e.g., creating campaigns, adding users) but will **not** execute them. This execution policy ensures you have full control over any changes to your Google Ads account. You must review the generated code for accuracy and execute it manually outside of the Assistant.

## Known Quirks

*   The underlying model may have been trained on an older API version. It may occasionally generate code with deprecated fields. Execution errors often provide feedback that allows the assistant to self-correct on the next attempt, using the context from the client libraries. To avoid these errors, we always search for the latest version of the API when initializing the session and ask you to verify the version.



## Maintenance

We will periodically release updates to the client libraries.
To ensure you are using the latest versions, run `update.sh` (Linux/macOS) or `update.ps1` (Windows) when a new version of the API is published or a new version of a client library is released.

Starting with release 2.3.0, you can use the `--context_path` argument (Linux/macOS) or `-ContextPath` parameter (Windows) with the update scripts to add additional directories to your context (e.g., your own codebase).

## Uninstallation

If you wish to remove the assistant and the project directory, you can use the uninstallation scripts:

*   **Linux/macOS:**
    ```bash
    ./uninstall.sh
    ```
*   **Windows:**
    ```powershell
    .\uninstall.ps1
    ```

> [!CAUTION]
> These scripts will prompt for confirmation before deleting the entire project directory.

## Contributing

Please see `CONTRIBUTING.md` for guidelines on reporting bugs, suggesting features, and submitting pull requests.

## Support

Use the GitHub Issues tab for bug reports, feature requests, and support questions.

## License

Apache License 2.0. See the `LICENSE` file.
