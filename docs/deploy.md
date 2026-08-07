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
| `ARCHCOMPASS_SESSION_DAILY_RUNS` | `10` | Model-spending requests per session per UTC day. |
| `ARCHCOMPASS_GLOBAL_DAILY_RUNS` | `50` | The same, per instance, for everyone. Sized against the free tier: 180,000 vCPU-seconds a month is 6,000 a day, and a review holds its stream open for roughly two minutes. |
| `ARCHCOMPASS_SOURCE_HOSTS` | — | Comma-separated hosts a visitor may name a repository on, e.g. `github.com`. Empty means the demo reviews only its bundled examples, which is what it does without this set. Values must be hosts the build knows an archive address for: `github.com`, `gitlab.com`, `codeberg.org`. |
| `ARCHCOMPASS_MAX_SOURCE_MB` | `64` | How large one fetched repository may be. Counted as it arrives and again over what its archive says it unpacks to. |
| `ARCHCOMPASS_MAX_TOTAL_SOURCE_MB` | `250` | How much every visitor's fetched code may occupy at once. Least-recently-used trees are deleted to stay under it. Raise with the container's memory, not on its own. |
| `ARCHCOMPASS_SOURCE_TIMEOUT` | `120` | Seconds a fetch may take. |
| `ARCHCOMPASS_SESSION_DAILY_FETCHES` | `5` | Repositories fetched per session per UTC day. |
| `ARCHCOMPASS_GLOBAL_DAILY_FETCHES` | `100` | The same, per instance, for everyone. |
| `ARCHCOMPASS_MAX_FILE_KB` | `2048` | Files larger than this are left out of the analysis. |
| `ARCHCOMPASS_MAX_FILES` | `1200` | How many files one repository contributes to an atlas. |
| `ARCHCOMPASS_MAX_PYTHON_MB` | `12` | How much Python one repository may bring. Refused before a file is read, rather than trimmed. |
| `ARCHCOMPASS_MAX_NODES` | `8000` | How many modules, classes and functions one repository may produce. Checked while parsing. Memory costs about 40 KB a node, and repository density varies fourfold, so this is the cap that measures what is actually spent. |

### Reviewing a repository a visitor names

Off unless `ARCHCOMPASS_SOURCE_HOSTS` is set. With it set, the demo fetches a **source
tarball over HTTPS** from those hosts and never runs `git`. That is the point of it rather
than an implementation detail: an extracted archive cannot carry hooks, submodules,
`.gitattributes` filters, credential helpers, an `ssh://` or `file://` transport, or a
redirect to somewhere the server was not asked to go.

The address is matched whole against a fixed pattern before any request is made — exact
host, two path segments, nothing else — and because the host is compared literally and never
resolved, there is no name to rebind between the check and the connection. Redirects are
refused rather than followed. Extraction uses `tarfile`'s `data` filter, which refuses
absolute paths, `..`, symlinks, hard links and device nodes.

Fetched repositories are parsed, never executed: nothing installs their dependencies, reads
their tool configuration, or imports them. `.env` files are excluded from the atlas on the
demo, so a repository's secrets are not excerpted to the model provider.

#### What it costs in memory

Analysis, not fetching, is the expensive thing. Peak memory runs at roughly **48 MB per
**atlas node** — about 27 KB of it — rather than per megabyte of source, and how many nodes
a megabyte carries varies fourfold between repositories. So `ARCHCOMPASS_MAX_NODES` is the
limit that protects the container and `ARCHCOMPASS_MAX_PYTHON_MB` is a cheap gate applied
before a file is read. At the 8,000-node cap an analysis costs roughly 210 MB, and the
hosted app analyses **one repository at a time** so two cannot overlap.

Measured, after the work in ADR 0015: `psf/black` (2,235 nodes) peaks at 245 MB, down from
360; `sqlalchemy` (38,720 nodes) at 1,112 MB, down from 1,615 — well past the node cap and
refused. `django` is refused too.


A container's `/tmp` is `tmpfs`, so a fetched repository is spending the same allowance the
server runs in — the application is around 200 MB with an analysis in flight, against
`--memory 1Gi`. Exhausting it kills the process rather than the fetch, and takes every
session on the instance with it, so the size limits are memory limits and are enforced in
three places:

- `ARCHCOMPASS_MAX_SOURCE_MB` bounds one repository, while it downloads and again while it
  unpacks.
- A visitor holds **one** repository at a time; fetching another replaces it. The atlas of
  the previous one is already stored, so what is dropped is a copy of code.
- `ARCHCOMPASS_MAX_TOTAL_SOURCE_MB` bounds every visitor's code together, deleting
  least-recently-used trees before each fetch. Someone who left a tab open may find their
  repository gone and have to paste the address again — which costs seconds, where running
  out of memory costs everyone their session.

Nothing is written to a bucket or a persistent volume. Every workspace is gone when the
instance recycles.

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
