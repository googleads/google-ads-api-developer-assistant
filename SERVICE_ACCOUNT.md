# Google Ads API Service Account Setup Guide

This guide provides step-by-step instructions for setting up a service account for use with the Google Ads API and this Assistant. Service accounts are ideal for server-to-server applications that do not require human interaction.

---

## Prerequisites

1.  A Google Ads Manager Account (MCC) (required to obtain a developer token).
2.  A Google Cloud Project with the Google Ads API enabled.

---

## Step 1: Create a Service Account in Google Cloud

1.  Open the [Google Cloud Console Credentials page](https://console.cloud.google.com/apis/credentials).
2.  Click **Create Credentials** > **Service account**.
3.  Enter a name and ID (e.g., `google-ads-api-service-account`).
4.  Click **Create and Continue**.
5.  (Optional) Grant any needed project roles. For Google Ads API alone, you generally don't need project-level roles unless you're using other Cloud services.
6.  Click **Done**.

---

## Step 2: Download the JSON Key

1.  In the Service accounts list, click on the email address of the account you just created.
2.  Go to the **Keys** tab.
3.  Click **Add Key** > **Create new key**.
4.  Select **JSON** as the key type and click **Create**.
5.  **Save the downloaded JSON file securely.** This file contains your private credentials. For this Assistant, you should place it in a secure location (e.g., `~/.google-ads-keys/service-account-key.json`).

---

## Step 3: Grant Access in the Google Ads UI

Unlike the OAuth2 flow where you grant access via a consent screen, you must manually add the service account as a user to your Google Ads account.

1.  Sign in to your [Google Ads account](https://ads.google.com/).
2.  Go to **Admin** > **Access and security**.
3.  Click the blue **+** button.
4.  Enter the **Service account email** (e.g., `google-ads-api-service-account@your-project-id.iam.gserviceaccount.com`).
5.  Select an access level (typically **Admin** or **Standard** for API use).
6.  Click **Send invitation**.
7.  Since service accounts cannot "accept" email invitations, the access is typically granted immediately or can be managed directly in the UI.

---

## Step 4: Configure the Extension

Update your primary configuration file in your home directory (e.g., `~/google-ads.yaml`).

### Python (`~/google-ads.yaml`)

```yaml
developer_token: YOUR_DEVELOPER_TOKEN
json_key_file_path: /path/to/your/service-account-key.json
impersonated_email: user@example.com  # Only required if using domain-wide delegation
# login_customer_id: YOUR_MANAGER_CID # Optional
```

### PHP (`~/google_ads_php.ini`)

```ini
[GOOGLE_ADS]
developer_token = "YOUR_DEVELOPER_TOKEN"
json_key_file_path = "/path/to/your/service-account-key.json"
impersonated_email = "user@example.com" ; Optional
```

### Ruby (`~/google_ads_config.rb`)

```ruby
GoogleAds::Config.new do |c|
  c.developer_token = 'YOUR_DEVELOPER_TOKEN'
  c.json_key_file_path = '/path/to/your/service-account-key.json'
  c.impersonated_email = 'user@example.com' # Optional
end
```

### Java (`~/ads.properties`)

```properties
api.googleads.developerToken=YOUR_DEVELOPER_TOKEN
api.googleads.oAuth2Mode=SERVICE_ACCOUNT
api.googleads.oAuth2SecretsJsonPath=/path/to/your/service-account-key.json
api.googleads.oAuth2PrnEmail=user@example.com # Optional
```

---

## Benefits of Service Accounts

- **No Human Interaction**: Perfect for automated scripts and cron jobs.
- **Persistence**: Credentials don't expire like refresh tokens can (unless the key is revoked).
- **Security**: Access can be scoped specifically to the service account.

> [!IMPORTANT]
> Keep your JSON key file secure. Anyone with this file can access your Google Ads account with the permissions granted to the service account.
