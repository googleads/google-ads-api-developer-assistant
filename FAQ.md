# FAQ

## How do I configure my Google Ads API credentials?
The Assistant looks for configuration files in your home directory (`$HOME`). 
- **Python**: `google-ads.yaml`
- **PHP**: `google_ads_php.ini`
- **Ruby**: `google_ads_config.rb`
Refer to the official Google Ads API documentation for the specific structure of each file.

## How do I set a default customer ID?
Create a file named `customer_id.txt` in the project root directory with the format:
`customer_id: 1234567890`

## Which languages are supported for code execution?
Python, PHP, and Ruby can be executed directly within the Assistant using the "Run the code" prompt. Java and C# (.NET) code can be generated but must be compiled and executed externally.

## How do I create a report for conversion upload issues that I can share with Google Support?
After you have completed the interactive troubleshooting, you can use the `/conversions_support_data` command to generate a structured diagnostic report. The report will be saved in the `saved/data/` directory.

## Can I mutate data (create/update/delete) using the Assistant?
The Assistant is designed for read-only operations and generating code. While it can generate code for mutate operations, it will not execute them directly for safety reasons. You should review and execute mutate code manually.
