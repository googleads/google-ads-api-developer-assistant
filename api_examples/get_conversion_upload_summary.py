import argparse
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException


def main(client: GoogleAdsClient, customer_id: str) -> None:
    ga_service = client.get_service("GoogleAdsService")

    query = """
        SELECT
            offline_conversion_upload_client_summary.alerts,
            offline_conversion_upload_client_summary.client,
            offline_conversion_upload_client_summary.daily_summaries,
            offline_conversion_upload_client_summary.job_summaries,
            offline_conversion_upload_client_summary.last_upload_date_time,
            offline_conversion_upload_client_summary.resource_name,
            offline_conversion_upload_client_summary.status,
            offline_conversion_upload_client_summary.success_rate,
            offline_conversion_upload_client_summary.successful_event_count,
            offline_conversion_upload_client_summary.total_event_count
        FROM
            offline_conversion_upload_client_summary
    """

    try:
        stream = ga_service.search_stream(customer_id=customer_id, query=query)

        print("Offline conversion upload client summary:")
        for batch in stream:
            for row in batch.results:
                summary = row.offline_conversion_upload_client_summary
                print(f"Resource Name: {summary.resource_name}")
                print(f"Status: {summary.status}")
                print(f"Total Event Count: {summary.total_event_count}")
                print(f"Successful Event Count: {summary.successful_event_count}")
                print(f"Success Rate: {summary.success_rate}")
                print(f"Last Upload Time: {summary.last_upload_date_time}")
                print("Alerts:")
                for alert in summary.alerts:
                    print(f"  Error: {alert.error.conversion_upload_error.name}")
                print("Daily Summaries:")
                for daily_summary in summary.daily_summaries:
                    print(f"  Date: {daily_summary.upload_date}")
                    print(f"  Successful Count: {daily_summary.successful_count}")
                    print(f"  Failed Count: {daily_summary.failed_count}")
                print("Job Summaries:")
                for job_summary in summary.job_summaries:
                    print(f"  Job ID: {job_summary.job_id}")
                    print(f"  Successful Count: {job_summary.successful_count}")
                    print(f"  Failed Count: {job_summary.failed_count}")
                    print(f"  Upload Time: {job_summary.upload_date}")

    except GoogleAdsException as ex:
        print(
            f'Request with ID "{ex.request_id}" failed with status '
            f'"{ex.error.code().name}" and includes the following errors:'
        )
        for error in ex.failure.errors:
            print(f'\tError with message "{error.message}".')
            if error.location:
                for field_path_element in error.location.field_path_elements:
                    print(f"\t\tOn field: {field_path_element.field_name}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Get offline conversion upload client summary."
    )
    parser.add_argument(
        "-c",
        "--customer_id",
        type=str,
        required=True,
        help="The Google Ads customer ID.",
    )
    args = parser.parse_args()

    googleads_client = GoogleAdsClient.load_from_storage(version="v22")

    try:
        main(googleads_client, args.customer_id)
    except GoogleAdsException as ex:
        print(
            f'Request with ID "{ex.request_id}" failed with status '
            f'"{ex.error.code().name}" and includes the following errors:'
        )
        for error in ex.failure.errors:
            print(f'\tError with message "{error.message}".')
            if error.location:
                for field_path_element in error.location.field_path_elements:
                    print(f"\t\tOn field: {field_path_element.field_name}")
        sys.exit(1)
