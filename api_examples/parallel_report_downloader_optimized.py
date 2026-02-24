# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Downloads multiple reports in parallel using structured logging."""

import argparse
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def fetch_report_threaded(
    client: GoogleAdsClient, customer_id: str, query: str, report_name: str
) -> Tuple[str, Optional[List[Any]], Optional[GoogleAdsException]]:
    """Fetches a single report with centralized exception handling."""
    ga_service = client.get_service("GoogleAdsService")
    logger.info("[%s] Fetching for customer %s...", report_name, customer_id)
    rows = []
    exception = None
    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        for batch in stream:
            for row in batch.results:
                rows.append(row)
        logger.info("[%s] Completed. Found %d rows.", report_name, len(rows))
    except GoogleAdsException as ex:
        logger.error("[%s] Request ID %s failed: %s", report_name, ex.request_id, ex.error.code().name)
        exception = ex
    return report_name, rows, exception


def _get_date_range_strings() -> Tuple[str, str]:
    """Helper for testing compatibility."""
    end = datetime.now()
    start = end - timedelta(days=30)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def main(customer_ids: List[str], login_id: Optional[str], workers: int = 5) -> None:
    """Main execution loop for parallel report retrieval."""
    client = GoogleAdsClient.load_from_storage(version="v23")
    if login_id:
        client.login_customer_id = login_id

    start, end = _get_date_range_strings()

    report_defs = [
        {
            "name": "Campaign_Performance",
            "query": f"SELECT campaign.id, metrics.clicks FROM campaign WHERE segments.date BETWEEN '{start}' AND '{end}' LIMIT 5"
        }
    ]

    results: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_name = {
            executor.submit(fetch_report_threaded, client, cid, rd["query"], f"{rd['name']}_{cid}"): f"{rd['name']}_{cid}"
            for cid in customer_ids for rd in report_defs
        }

        for future in as_completed(future_to_name):
            name = future_to_name[future]
            _, rows, ex = future.result()
            results[name] = {"rows": rows, "exception": ex}

    for name, data in results.items():
        if data["exception"]:
            logger.warning("Report %s failed.", name)
        else:
            logger.info("Report %s: %d rows retrieved.", name, len(data["rows"]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parallel report downloader.")
    parser.add_argument("-c", "--customer_ids", nargs="+", required=True)
    parser.add_argument("-l", "--login_id")
    parser.add_argument("-w", "--workers", type=int, default=5)
    args = parser.parse_args()
    main(args.customer_ids, args.login_id, args.workers)
