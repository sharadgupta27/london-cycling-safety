# credentials/

Place your GCP service-account JSON key here:

```
credentials/service_account.json
```

**All `*.json` files in this directory are gitignored — they will never be committed.**

## Required IAM roles for the service account

| Role | Purpose |
|---|---|
| `BigQuery Data Editor` | Create/write tables in the raw and dbt datasets |
| `BigQuery Job User` | Run query jobs |

## How to create a service account key

```bash
# Create the service account
gcloud iam service-accounts create london-cycling-sa \
  --display-name "London Cycling Safety Pipeline"

# Grant required roles
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:london-cycling-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:london-cycling-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Download the key
gcloud iam service-accounts keys create credentials/service_account.json \
  --iam-account=london-cycling-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

## .env settings

```dotenv
GOOGLE_APPLICATION_CREDENTIALS=/credentials/service_account.json
GCP_PROJECT_ID=your-gcp-project-id
GCP_BQ_DATASET=dbt_london_cycling
GCP_BQ_LOCATION=EU
```

The `GOOGLE_APPLICATION_CREDENTIALS` path uses the **in-container path**
(`/credentials/` is mounted from `credentials/` via `docker-compose.local.yml`).
