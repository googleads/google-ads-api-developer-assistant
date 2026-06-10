---
name: pmax-listing-filter
description: Configures Asset Group URL expansion filters (listing group webpage exclusions) for Performance Max campaigns.
---

# PMax webpage exclusions filter

This skill provides verified webpage listing group filtering capability for Performance Max campaigns. It establishes webpage partition trees (subdivision trees) without the need for Page Feeds.

## Usage

Execute the webpage filter script to validate or construct the webpage exclusion tree on an Asset Group:

```bash
./.venv/bin/python3 .agents/skills/pmax_listing_filter/scripts/create_pmax_webpage_filter.py \
  --customer_id <customer_id> \
  --asset_group_id <asset_group_id> \
  --url_exclusion <url_exclusion_path> \
  --api_version <api_version>
```

### Options
* `--execute`: Runs the actual mutation on the API (omitting this performs a standard `validate_only=True` dry-run verification).

### Examples

1. Validate listing filter exclusion structure in dry-run mode:
```bash
./.venv/bin/python3 .agents/skills/pmax_listing_filter/scripts/create_pmax_webpage_filter.py \
  --customer_id 12345678 \
  --asset_group_id 98765 \
  --url_exclusion /blog \
  --api_version v24
```

2. Perform the actual mutation to apply filter exclusion:
```bash
./.venv/bin/python3 .agents/skills/pmax_listing_filter/scripts/create_pmax_webpage_filter.py \
  --customer_id 12345678 \
  --asset_group_id 98765 \
  --url_exclusion /blog \
  --api_version v24 \
  --execute
```
