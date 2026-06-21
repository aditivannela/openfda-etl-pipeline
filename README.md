# OpenFDA Drug Safety ETL Pipeline

An end-to-end ETL pipeline that extracts adverse drug event data from the FDA's public OpenFDA API, transforms it into a clean structured format, loads it into AWS S3, and makes it queryable with AWS Athena. The pipeline is deployed as an AWS Lambda function and runs automatically once a day via EventBridge.

## Overview

The OpenFDA Adverse Events API contains 20M+ real-world reports of drug side effects, submitted to the FDA by patients, doctors, and manufacturers. This project builds a pipeline that pulls that data, cleans it, and stores it in a queryable data lake — the same general pattern used in production data engineering for healthcare, pharma, and regulatory analytics.

**Pipeline flow:**

```
OpenFDA REST API
      │  (extract)
      ▼
  Python / Pandas
      │  (transform: flatten nested JSON, clean types, decode codes)
      ▼
   AWS S3 (raw/)
      │
      ▼
  AWS Athena (SQL queries directly on S3 data)

Automation: AWS Lambda + EventBridge (runs daily, no manual trigger needed)
```

## Architecture

| Stage | Tool | Purpose |
|---|---|---|
| Extract | `requests`, OpenFDA REST API | Pull adverse event reports in JSON |
| Transform | Python, Pandas | Flatten nested fields, decode coded values, clean types |
| Load | `boto3`, AWS S3 | Store cleaned data as CSV in a data lake |
| Query | AWS Athena | Run SQL directly against S3 data, no database needed |
| Automate | AWS Lambda | Run the extract/transform/load logic serverlessly |
| Schedule | AWS EventBridge | Trigger the Lambda function once every 24 hours |

## What the data looks like

Each raw API record is deeply nested JSON. For example, a single report contains nested `patient`, `reaction[]`, and `drug[]` objects. The transform step flattens this into a clean tabular structure:

| Field | Description |
|---|---|
| `safetyreportid` | Unique report ID |
| `receivedate` | Date FDA received the report (parsed to `YYYY-MM-DD`) |
| `serious` | Whether the event was classified as medically serious |
| `seriousnessdeath` | Whether the event resulted in death |
| `country` | Reporting country |
| `patient_age` | Patient age at onset |
| `patient_sex` | Decoded to `Male` / `Female` / `Unknown` |
| `reactions` | Comma-separated list of reported adverse reactions |
| `drugs` | Comma-separated list of implicated drugs |
| `drug_indications` | Why the drug was prescribed |

## Example Athena query

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

This returns the most frequently reported drugs in the dataset alongside how many of those reports involved a death — the kind of question this pipeline is built to answer at scale.

## Notable challenges solved

- **Quoted commas breaking CSV parsing in Athena.** Some fields (e.g. multiple drugs per report) contain commas inside quoted strings. Athena's default CSV reader split on every comma regardless of quoting, corrupting the table. Fixed by switching the Athena table definition to `OpenCSVSerde`, which correctly respects quoted fields.
- **Invalid/missing numeric values crashing queries.** Empty `patient_age` values (common in real-world reporting data) caused `NumberFormatException` errors when Athena tried to cast them to `DOUBLE`. Fixed by adding `'use.null.for.invalid.data'='true'` to the table properties, so missing values are treated as `NULL` instead of failing the query.
- **Lambda timeout on cold start.** The default 3-second Lambda timeout was too short to cold-start the pandas layer, call the API, and write to S3. Increased to 30 seconds.
- **IAM permissions.** The Lambda execution role had no S3 write access by default. Resolved by attaching `AmazonS3FullAccess` to the function's role.
- **Package size limits.** Bundling `pandas` and `numpy` directly into the Lambda deployment package pushed it close to AWS's 50MB upload limit. Resolved by removing them from the deployment ZIP and attaching AWS's pre-built `AWSSDKPandas` Lambda layer instead — the standard approach for using large libraries in Lambda.

## Repository contents

- `lambda_function.py` — production script containing the `lambda_handler` entry point AWS Lambda invokes on each scheduled run
- `openfda_etl_pipeline.ipynb` — exploratory notebook showing the step-by-step build process: API exploration, data cleaning logic, and local testing before deployment

## Tech stack

Python · Pandas · AWS S3 · AWS Lambda · AWS Athena · AWS EventBridge · AWS IAM · REST APIs

## Future improvements

- Partition S3 data by date for more efficient Athena queries at larger scale
- Add a `processed/` layer with pre-aggregated tables for common queries
- Add CloudWatch alarms for pipeline failure notifications
