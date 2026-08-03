# Deploying the hosted demo

The public demo is the same application as `archcompass web`, served from one container with
three differences: every visitor gets their own workspace behind a session cookie, the
things a stranger must not be able to do are refused, and the model calls are rationed. All
three are switched on by `ARCHCOMPASS_HOSTED=1`, which the hosted entry point requires — it
refuses to start without it rather than defaulting to an unrestricted public server.

## What hosted mode changes

- **A workspace per session.** An opaque token in `archcompass_session` (HttpOnly,
  SameSite=Lax, Secure) names a directory under `ARCHCOMPASS_SESSION_ROOT`. It is the
  container's own filesystem by default, which is ephemeral: an instance scaled to zero
  takes the workspaces with it.
- **Three refusals**, each a 403 explaining what this deployment is: browsing the server's
  folders, indexing anything but a bundled example, and registering a server folder as a
  policy source. Writing policies is unaffected — those live in the session's workspace.
- **A daily budget.** Counted in memory per instance, so a cold start forgets it. The demo
  is protected from one visitor spending the day's free tier, not audited.

`archcompass web` reaches none of this.

## Build and run

```bash
make docker-build   # builds the image and checks the container answers /api/workspace
```

## Deploy to Cloud Run

```bash
gcloud secrets create archcompass-google-api-key --replication-policy=automatic
printf '%s' "$GOOGLE_API_KEY" | gcloud secrets versions add archcompass-google-api-key --data-file=-

gcloud run deploy archcompass \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --set-env-vars ARCHCOMPASS_HOSTED=1,ARCHCOMPASS_PROVIDERS=google \
  --set-secrets GOOGLE_API_KEY=archcompass-google-api-key:latest
```

`--min-instances 0` is the point of the demo's cost profile: nothing runs between visits.
The first request after an idle period pays a cold start, and the sessions from before it
are gone.

## Continuous deployment

`.github/workflows/deploy.yml` redeploys on every push to `main`. GitHub authenticates to
Google by workload identity federation — the repository holds no service-account key, only
the name of a trust that admits this repository's workflows. One-time setup, after
`gcloud auth login`, with `PROJECT` set to the project id and `REPO` to `owner/name`:

```bash
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com \
  iamcredentials.googleapis.com --project "$PROJECT"

# The identity the workflow deploys as.
gcloud iam service-accounts create archcompass-deployer --project "$PROJECT"
SA="archcompass-deployer@$PROJECT.iam.gserviceaccount.com"
for role in run.admin cloudbuild.builds.editor iam.serviceAccountUser \
    storage.admin artifactregistry.writer serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member "serviceAccount:$SA" --role "roles/$role" --condition=None
done

# The trust: only workflows from this repository's main branch may become that identity.
gcloud iam workload-identity-pools create github --location global --project "$PROJECT"
gcloud iam workload-identity-pools providers create-oidc github-actions \
  --location global --workload-identity-pool github --project "$PROJECT" \
  --issuer-uri https://token.actions.githubusercontent.com \
  --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition "assertion.repository == '$REPO'"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT" --format 'value(projectNumber)')"
gcloud iam service-accounts add-iam-policy-binding "$SA" --project "$PROJECT" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"

# The runtime service account reads the key; Cloud Build (run by the deployer) builds.
gcloud secrets add-iam-policy-binding archcompass-google-api-key --project "$PROJECT" \
  --member "serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role roles/secretmanager.secretAccessor

# What the workflow reads, as repository variables.
gh variable set GCP_PROJECT_ID --body "$PROJECT"
gh variable set GCP_REGION --body europe-west1
gh variable set GCP_SERVICE_ACCOUNT --body "$SA"
gh variable set GCP_WORKLOAD_IDENTITY_PROVIDER --body \
  "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github-actions"
```

## Environment

| Variable | Default | What it is |
| --- | --- | --- |
| `ARCHCOMPASS_HOSTED` | — | Required. `1` to serve the hosted demo. |
| `ARCHCOMPASS_PROVIDERS` | every provider this build knows | Comma-separated. `google` alone is what a hosted demo wants: there is no Ollama to reach, and a chooser listing one is a row that can only say "nothing is listening". |
| `GOOGLE_API_KEY` | — | Required when `google` is offered. Startup fails without it, rather than every visitor discovering it one click at a time. |
| `ARCHCOMPASS_SESSION_ROOT` | `/tmp/archcompass-sessions` | Where session workspaces are written. |
| `ARCHCOMPASS_SESSION_CACHE` | `32` | How many session runtimes stay open. Eviction loses no data — the workspace stays on disk and is reopened on the next request. |
| `ARCHCOMPASS_SESSION_DAILY_RUNS` | `25` | Model-spending requests per session per UTC day. |
| `ARCHCOMPASS_GLOBAL_DAILY_RUNS` | `250` | The same, per instance, for everyone. |

The container's `PORT` is honoured, defaulting to 8080, which is what Cloud Run supplies.

## The billing backstop

A GCP budget only ever notifies — nothing Google offers stops spending by itself. The
backstop is therefore a function of last resort: the budget publishes to Pub/Sub topic
`billing-cap`, and `infra/billing-cap` detaches billing from the project when billed
cost reaches the budget's full amount. Cloud Run then stops serving — the demo goes
dark instead of charging anyone. Billing data lags real usage by up to a few hours, so
the cap is approximate to that lag; at one max instance the overshoot is cents.

One-time setup, after the function itself is deployed (deploy command in
`infra/billing-cap/main.py`). Both of these act on billing and need an account holder:

```bash
# The function's service account must be allowed to detach billing.
gcloud projects add-iam-policy-binding arch-compass \
  --member=serviceAccount:99312935671-compute@developer.gserviceaccount.com \
  --role=roles/billing.projectManager --condition=None

# The budget: warn at 50% and 90%, publish every notification to the topic.
gcloud billing budgets create --billing-account=017485-E8D21C-47029F \
  --display-name="arch-compass hard cap" --budget-amount=5EUR \
  --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 \
  --notifications-rule-pubsub-topic=projects/arch-compass/topics/billing-cap
```

Firing is one-way by design: re-attaching billing is a decision made by a person in the
console, never by code. The Artifact Registry repository the deploys build into keeps
its three newest images and deletes the rest after a week, so image storage cannot
creep past the free tier either.
