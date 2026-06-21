# OpenFDA Drug Safety ETL Pipeline

ETL pipeline that pulls adverse drug event reports from the FDA's OpenFDA API, cleans the data, loads it into AWS S3, and makes it queryable with AWS Athena. Deployed as a Lambda function that runs automatically once a day via EventBridge.

## What it does

OpenFDA publishes 20M+ real-world reports of drug side effects submitted by patients, doctors, and manufacturers. This pipeline pulls that data, flattens the messy nested JSON into clean tabular records, and stores it so it can be queried with plain SQL.

```
OpenFDA API → Python/Pandas (clean + flatten) → S3 → Athena (SQL queries)

Lambda + EventBridge run the extract/load steps daily, automatically.
```

## Architecture

| Stage | Tool | Purpose |
|---|---|---|
| Extract | `requests`, OpenFDA API | Pull adverse event reports as JSON |
| Transform | Python, Pandas | Flatten nested fields, decode coded values, clean types |
| Load | `boto3`, AWS S3 | Store cleaned data as CSV |
| Query | AWS Athena | Run SQL directly against S3 data |
| Automate | AWS Lambda | Run extract/transform/load without a server |
| Schedule | AWS EventBridge | Trigger the Lambda function every 24 hours |

## Data

Each raw record from the API is deeply nested — a single report has nested `patient`, `reaction[]`, and `drug[]` objects. The transform step flattens this into:

| Field | Description |
|---|---|
| `safetyreportid` | Unique report ID |
| `receivedate` | Date FDA received the report |
| `serious` | Whether the event was classified as medically serious |
| `seriousnessdeath` | Whether the event resulted in death |
| `country` | Reporting country |
| `patient_age` | Patient age at onset |
| `patient_sex` | Decoded to Male / Female / Unknown |
| `reactions` | Reported adverse reactions |
| `drugs` | Drugs involved in the report |
| `drug_indications` | Why the drug was prescribed |

## Example query

```sql
SELECT 
    drugs,
    COUNT(*) AS total_reports,
    SUM(CASE WHEN seriousnessdeath = 'Yes' THEN 1 ELSE 0 END) AS death_count
FROM adverse_events
GROUP BY drugs
ORDER BY total_reports DESC
LIMIT 10;
```

Returns the most frequently reported drugs and how many of those reports involved a death.

## Issues I ran into

- **Athena was splitting columns on every comma, even inside quotes.** Some drug fields have multiple drugs separated by commas (e.g. `"DOXYCYCLINE, TRAMADOL"`). The default CSV table definition ignored the quotes and broke the column structure. Fixed by switching to `OpenCSVSerde` in the table definition.
- **Empty age values crashed the query.** Missing `patient_age` values caused a `NumberFormatException` when Athena tried to cast them to `DOUBLE`. Fixed by adding `'use.null.for.invalid.data'='true'` to the table properties.
- **Lambda timed out on the default 3-second limit.** Cold-starting the pandas layer plus the API call plus the S3 upload took longer than that. Bumped the timeout to 30 seconds.
- **Lambda's execution role had no S3 permissions by default.** Had to attach `AmazonS3FullAccess` to the function's IAM role before it could write to the bucket.
- **Pandas + numpy pushed the deployment ZIP close to Lambda's size limit.** Removed them from the package and used AWS's pre-built `AWSSDKPandas` Lambda layer instead.

## Files

- `lambda_function.py` — the production script, contains the `lambda_handler` entry point AWS Lambda runs on each scheduled trigger
- `openfda_etl_pipeline.ipynb` — the notebook where I built and tested the extract/transform logic before deploying it

## Stack

Python, Pandas, AWS S3, AWS Lambda, AWS Athena, AWS EventBridge, AWS IAM, REST APIs

## Possible next steps

- Partition S3 data by date for faster Athena queries at scale
- Add a `processed/` layer with pre-aggregated tables
- CloudWatch alarms for pipeline failures
