# Conversions Troubleshooting Report Template

Use this template to generate the report. Replace all `{placeholders}`
with actual findings. Remove sections that are not applicable.

---

#  Conversions Troubleshooting: {Customer ID}

**Report Date**: {YYYY-MM-DD}
**Time Period Covered**: from {YYYY-MM_DD} to {YYYY-MM-DD}

## 1. Summary
A 2-3 sentence summary of the findings. State the purpose of the report.

### [Introductory Conversion Analysis]
- **Customer ID**: Customer ID
- **Upload Health**: Description of conversion upload health {EXCELLENT|GOOD|FAIR|POOR}
- **Percentage Failing**: Percent of conversion uploads failing and the primary reason

### [Primary Errors & Critical Issues]
- **Errors**: List specific error and their percentages. If percentage in 0, do not list. Do not preface with 'Client Alert'

### [General Health & Technical Findings]
- DO NOT print (Total Success: [succcess}/[fail]) for current day in header for each section. Example: Client Status: EXCELLENT (Total Success: 7757/7757)
- **GOOGLE_ADS_API**: status whith number and percentage of total successful upload s
- **GOOGLE_ADS_WEB_CLIENT**: {status EXCELLENT|GOOD|FAIR|POOR} {successful uploads}/[total successful uploads} {percentage of successful uploads}
- **ADS_DATA_CONNECTOR:** {status EXCELLENT|GOOD|FAIR|POOR} {successful uploads}/[total successful uploads} {percentage of successful uploads}
- **BUlKSHEET ACTIONS:** {status EXCELLENT|GOOD|FAIR|POOR} {successful uploads}/[total successful uploads} {percentage of successful uploads}

### [Actionable Recommendations]
- **Actionable Recommendations:** List of actions that can be taken by the user to correct the current state.

## 2. Consolidation Mandate

All findings—including terminal summaries, structured analysis, verbatim screen output, and complete query data—MUST be consolidated into the single self-contained output report file generated in `saved/data/`. This file MUST start with the exact header `Created by the Google Ads API Developer Assistant` and MUST be the sole artifact submitted to the user for support. Placeholders or external references are strictly prohibited.