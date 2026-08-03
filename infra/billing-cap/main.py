"""Detach billing from the project when the budget's cap is reached.

The backstop of last resort, not the first line: Cloud Run is capped at one instance and
the app rations model runs, so this exists for the case nobody predicted. A GCP budget
only ever notifies — nothing Google offers stops spending by itself — so this function is
what turns the €5 budget's notification into a stop: billing detaches, Cloud Run loses
its billing account, and the demo goes dark instead of charging anyone.

Deliberately idempotent and quiet. Budget notifications repeat (several per day at every
threshold), so "already detached" is the common case after firing once, and raising there
would only page about a job already done. Re-attaching billing is a human decision made
in the console, never something this code can do.

Deploy (one-time, documented in docs/deploy.md):
  gcloud functions deploy billing-cap --gen2 --runtime=python312 \
    --region=europe-west1 --trigger-topic=billing-cap \
    --entry-point=stop_billing --source=infra/billing-cap --project=arch-compass
"""

from __future__ import annotations

import base64
import json

import functions_framework
from google.cloud import billing_v1

PROJECT = "projects/arch-compass"


@functions_framework.cloud_event
def stop_billing(event) -> None:
    notification = json.loads(base64.b64decode(event.data["message"]["data"]).decode())
    # costAmount is what has actually been billed so far in the period; the budget's own
    # thresholds decide when notifications start arriving. Detach only at or past the
    # full budget, so the 50% warning mail is a warning and nothing more.
    if notification.get("costAmount", 0) < notification.get("budgetAmount", 0):
        return
    client = billing_v1.CloudBillingClient()
    info = client.get_project_billing_info(name=PROJECT)
    if not info.billing_enabled:
        return
    client.update_project_billing_info(
        name=PROJECT,
        project_billing_info=billing_v1.ProjectBillingInfo(billing_account_name=""),
    )
