import requests
import pandas as pd
import boto3
from datetime import datetime

def extract_record(report):
    """Extract relevant fields from a single adverse event report"""
    patient = report.get('patient', {})
    primary_source = report.get('primarysource', {})
    
    reactions = patient.get('reaction', [])
    reaction_list = ', '.join([r.get('reactionmeddrapt', '') for r in reactions])
    
    drugs = patient.get('drug', [])
    drug_list = ', '.join([d.get('medicinalproduct', '') for d in drugs])
    drug_indications = ', '.join([d.get('drugindication', '') for d in drugs])
    
    return {
        'safetyreportid': report.get('safetyreportid'),
        'receivedate': report.get('receivedate'),
        'serious': report.get('serious'),
        'seriousnessdeath': report.get('seriousnessdeath', '0'),
        'country': primary_source.get('reportercountry'),
        'patient_age': patient.get('patientonsetage'),
        'patient_sex': patient.get('patientsex'),
        'reactions': reaction_list,
        'drugs': drug_list,
        'drug_indications': drug_indications
    }

def transform_df(df):
    df['receivedate'] = pd.to_datetime(df['receivedate'], format='%Y%m%d', errors='coerce')
    
    sex_map = {'1': 'Male', '2': 'Female'}
    df['patient_sex'] = df['patient_sex'].map(sex_map).fillna('Unknown')
    
    df['serious'] = df['serious'].map({'1': 'Yes', '0': 'No'}).fillna('Unknown')
    df['seriousnessdeath'] = df['seriousnessdeath'].map({'1': 'Yes', '0': 'No'}).fillna('No')
    
    df['drug_indications'] = df['drug_indications'].str.strip(', ').str.strip()
    df['patient_age'] = pd.to_numeric(df['patient_age'], errors='coerce')
    
    return df

def lambda_handler(event, context):
    """
    Entry point for AWS Lambda.
    Extracts OpenFDA data, transforms it, and loads it to S3.
    """
    bucket_name = 'aditi-openfda-etl-pipeline'
    base_url = "https://api.fda.gov/drug/event.json"
    
    params = {"limit": 100, "skip": 0}
    response = requests.get(base_url, params=params)
    
    if response.status_code != 200:
        return {
            'statusCode': response.status_code,
            'body': f'Error fetching data from OpenFDA: {response.status_code}'
        }
    
    results = response.json()['results']
    extracted_records = [extract_record(report) for report in results]
    
    df = pd.DataFrame(extracted_records)
    df_clean = transform_df(df)
    
    today = datetime.now().strftime('%Y-%m-%d')
    filename = f'/tmp/openfda_{today}.csv'
    s3_key = f'raw/openfda_{today}.csv'
    
    df_clean.to_csv(filename, index=False)
    
    s3 = boto3.client('s3')
    s3.upload_file(filename, bucket_name, s3_key)
    
    return {
        'statusCode': 200,
        'body': f'Successfully loaded {len(df_clean)} records to {s3_key}'
    }