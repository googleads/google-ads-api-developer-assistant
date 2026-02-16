# Copyright 2025 Google LLC
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

"""This example creates a campaign experiment from a draft campaign.

The draft campaign is created from a base campaign. Both the experiment and
the experiment arms are created in this process.
"""

import argparse
import sys
import uuid

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.api_core import protobuf_helpers


def main(client, customer_id, base_campaign_id):
    """The main method that creates all necessary entities for the example.

    Args:
        client: an initialized GoogleAdsClient instance.
        customer_id: a client customer ID.
        base_campaign_id: the campaign ID to associate with the control arm of
          the experiment.
    """
    experiment = create_experiment_resource(client, customer_id)
    draft_campaign_resource_name = create_experiment_arms(
        client, customer_id, base_campaign_id, experiment
    )

    # This is where you'll define the changes for your second campaign version.
    # For example, you might change bids, ad copy, targeting, etc.
    modify_treatment_campaign(client, customer_id, draft_campaign_resource_name)

    # When you're done setting up the experiment and arms and modifying the
    # draft campaign, this will begin the experiment.
    experiment_service = client.get_service("ExperimentService")
    print(f"Scheduling experiment with resource name {experiment}...")
    experiment_service.schedule_experiment(resource_name=experiment)
    print("Experiment scheduled successfully.")


def create_experiment_resource(client, customer_id):
    """Creates a new experiment resource.

    Args:
        client: an initialized GoogleAdsClient instance.
        customer_id: a client customer ID.

    Returns:
        the resource name for the new experiment.
    """
    experiment_operation = client.get_type("ExperimentOperation")
    experiment = experiment_operation.create

    experiment.name = f"Campaign Version Test Experiment #{uuid.uuid4()}"
    experiment.type_ = client.enums.ExperimentTypeEnum.SEARCH_CUSTOM
    experiment.suffix = "[experiment]"
    experiment.status = client.enums.ExperimentStatusEnum.SETUP

    experiment_service = client.get_service("ExperimentService")
    response = experiment_service.mutate_experiments(
        customer_id=customer_id, operations=[experiment_operation]
    )

    experiment_resource_name = response.results[0].resource_name
    print(f"Created experiment with resource name {experiment_resource_name}")

    return experiment_resource_name


def create_experiment_arms(client, customer_id, base_campaign_id, experiment):
    """Creates a control and treatment experiment arms.

    Args:
        client: an initialized GoogleAdsClient instance.
        customer_id: a client customer ID.
        base_campaign_id: the campaign ID to associate with the control arm of
          the experiment.
        experiment: the resource name for an experiment.

    Returns:
        the resource name for the new treatment experiment arm's in-design campaign.
    """
    operations = []

    campaign_service = client.get_service("CampaignService")

    # The "control" arm references an already-existing campaign.
    operation_1 = client.get_type("ExperimentArmOperation")
    exa_1 = operation_1.create
    exa_1.control = True
    exa_1.campaigns.append(
        campaign_service.campaign_path(customer_id, base_campaign_id)
    )
    exa_1.experiment = experiment
    exa_1.name = "Control Arm (Original Campaign)"
    exa_1.traffic_split = 50  # Example: 50% traffic to control
    operations.append(operation_1)

    # The non-"control" arm, also called a "treatment" arm, will automatically
    # generate a draft campaign that you can modify before starting the
    # experiment.
    operation_2 = client.get_type("ExperimentArmOperation")
    exa_2 = operation_2.create
    exa_2.control = False
    exa_2.experiment = experiment
    exa_2.name = "Treatment Arm (New Version)"
    exa_2.traffic_split = 50  # Example: 50% traffic to treatment
    operations.append(operation_2)

    experiment_arm_service = client.get_service("ExperimentArmService")
    request = client.get_type("MutateExperimentArmsRequest")
    request.customer_id = customer_id
    request.operations = operations
    request.response_content_type = (
        client.enums.ResponseContentTypeEnum.MUTABLE_RESOURCE
    )
    response = experiment_arm_service.mutate_experiment_arms(request=request)

    # Results always return in the order that you specify them in the request.
    # Since we created the treatment arm second, it will be the second result.
    control_arm_result = response.results[0]
    treatment_arm_result = response.results[1]

    print(f"Created control arm with resource name {control_arm_result.resource_name}")
    print(
        f"Created treatment arm with resource name {treatment_arm_result.resource_name}"
    )

    # The in_design_campaigns field contains the resource name of the draft
    # campaign that was created for the treatment arm. This is the campaign
    # you will modify.
    draft_campaign_resource_name = (
        treatment_arm_result.experiment_arm.in_design_campaigns[0]
    )
    print(f"Draft campaign for treatment arm: {draft_campaign_resource_name}")
    return draft_campaign_resource_name


def modify_treatment_campaign(client, customer_id, draft_campaign_resource_name):
    """Modifies the given in-design campaign (the treatment arm).

    Args:
        client: an initialized GoogleAdsClient instance.
        customer_id: a client customer ID.
        draft_campaign_resource_name: the resource name for an in-design campaign.
    """
    campaign_service = client.get_service("CampaignService")
    campaign_operation = client.get_type("CampaignOperation")
    campaign = campaign_operation.update
    campaign.resource_name = draft_campaign_resource_name

    # =========================================================================
    # IMPORTANT: THIS IS WHERE YOU ADD YOUR CHANGES FOR THE SECOND CAMPAIGN VERSION
    # =========================================================================
    # For example, you might change the campaign's name, budget, bidding strategy,
    # add/remove ad groups, keywords, ads, etc.
    #
    # Here's an example of changing the campaign name and budget:
    campaign.name = f"New Version Campaign Name #{uuid.uuid4()}"
    campaign.budget.amount_micros = 20_000_000  # Example: Set budget to 20 USD

    # You MUST specify which fields are being updated by setting the update_mask.
    # The protobuf_helpers.field_mask utility can help with this.
    client.copy_from(
        campaign_operation.update_mask,
        protobuf_helpers.field_mask(None, campaign._pb),
    )

    try:
        campaign_service.mutate_campaigns(
            customer_id=customer_id, operations=[campaign_operation]
        )
        print(
            f"Updated draft campaign {draft_campaign_resource_name} with your changes."
        )
    except GoogleAdsException as ex:
        print(
            f"Failed to modify draft campaign '{draft_campaign_resource_name}' "
            f"with request ID '{ex.request_id}' and status '{ex.error.code().name}'."
        )
        for error in ex.errors:
            print(f"\tError with message '{error.message}'.")
            if error.location:
                for field_path_element in error.location.field_path_elements:
                    print(f"\t\tOn field: {field_path_element.field_name}")
        sys.exit(1)


if __name__ == "__main__":
    # GoogleAdsClient will read the google-ads.yaml configuration file in the
    # home directory if none is specified.
    googleads_client = GoogleAdsClient.load_from_storage(version="v23")

    parser = argparse.ArgumentParser(
        description="Create a campaign experiment based on a campaign draft."
    )
    # The following argument(s) are required to run the example.
    parser.add_argument(
        "-c",
        "--customer_id",
        type=str,
        required=True,
        help="The Google Ads customer ID.",
    )
    parser.add_argument(
        "-i",
        "--base_campaign_id",
        type=str,
        required=True,
        help="The ID of the base campaign to use for the experiment.",
    )
    args = parser.parse_args()

    try:
        main(googleads_client, args.customer_id, args.base_campaign_id)
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
