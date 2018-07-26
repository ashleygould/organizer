import sys
import boto3
from botocore.exceptions import ClientError


def assume_role_in_account(account_id, role_name):
    role_arn = 'arn:aws:iam::{}:role/{}'.format(account_id, role_name)
    role_session_name = account_id + '-' + role_name.split('/')[-1]
    sts_client = boto3.client('sts')
    try:
        credentials = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=role_session_name
        )['Credentials']
    except ClientError as e:
        if e.response['Error']['Code'] == 'AccessDenied':
            errmsg = 'cannot assume role {} in account {}: AccessDenied'.format(
                role_name, account_id
            )
            sys.exit(errmsg)
    return dict(
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken'],
    )


def get_master_account_id(role_name=None):
    # ISSUE: What exception gets thrown when my account is not part of an org?
    #        Need to fix moto mock_organizations describe_organization endpoint
    sts_client = boto3.client('sts')
    account_id = sts_client.get_caller_identity()['Account']
    credentials = assume_role_in_account(account_id, role_name)
    client = boto3.client('organizations', **credentials)
    try:
        return client.describe_organization()['Organization']['MasterAccountId']
    except Exception as e:
        print('An error occurred while running describe_organization')
        print(e)
        return ''

    
