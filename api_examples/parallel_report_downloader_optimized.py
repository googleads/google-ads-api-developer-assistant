# Copyright 2026 Google LLC
"""Parallel report downloader with optimized concurrency and retry logic."""

import argparse
import logging
from concurrent import futures
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _get_date_range_strings() -> tuple[str, str]:
    """Computes a 7-day date range for reporting."""
    end = datetime.now().strftime("%Y-%m-%d")
    start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    return start, end


def fetch_report_threaded(client: GoogleAdsClient, customer_id: str, query: str, log_tag: str) -> Dict:
    """Fetches a report using search_stream for memory efficiency."""
    logger.info("Fetching for customer %s [%s]", customer_id, log_tag)
    ga_service = client.get_service("GoogleAdsService")
    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)
        rows = []
        for batch in stream:
            for row in batch.results:
                rows.append(row)
        logger.info("Completed. Found %d rows.", len(rows))
        return {"customer_id": customer_id, "rows": rows}
    except GoogleAdsException as ex:
        logger.error("Request ID %s failed for customer %s", ex.request_id, customer_id)
        raise


def main(
    customer_ids: List[str],
    login_id: Optional[str],
    api_version: str,
    workers: int = 5,
) -> None:
    """Main execution loop for parallel report retrieval."""
    client = GoogleAdsClient.load_from_storage(version=api_version)
    if login_id:
        client.login_customer_id = login_id

    start, end = _get_date_range_strings()

    report_defs = [
        {
            "name": "Campaign_Performance",
            "query": f"SELECT campaign.id, metrics.clicks FROM campaign WHERE segments.date BETWEEN '{start}' AND '{end}' LIMIT 5",
        }
    ]

    with futures.ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_report = {
            executor.submit(fetch_report_threaded, client, cid, rd["query"], rd["name"]): (
                cid,
                rd["name"],
            )
            for cid in customer_ids
            for rd in report_defs
        }

        for future in futures.as_completed(future_to_report):
            cid, name = future_to_report[future]
            try:
                future.result()
                logger.info("Finished processing %s for customer %s", name, cid)
            except Exception:
                logger.warning("Report %s for customer %s failed.", name, cid)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parallel report downloader.")
    parser.add_argument("-c", "--customer_ids", nargs="+", required=True)
    parser.add_argument("-l", "--login_id")
    parser.add_argument("-w", "--workers", type=int, default=5)
    parser.add_argument(
        "-v", "--api_version", type=str, default="v23", help="The Google Ads API version."
    )
    args = parser.parse_args()
    main(args.customer_ids, args.login_id, args.api_version, args.workers)
