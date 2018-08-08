import os
import re
import time
import json
import pickle
import shutil

import yaml
import botocore
import boto3
import pytest
import moto
from moto import mock_organizations, mock_sts

from organizer import utils, orgs, crawlers

ORG_ACCESS_ROLE='myrole'
MASTER_ACCOUNT_ID='123456789012'

SIMPLE_ORG_SPEC="""
root:
  - name: root
    accounts:
    - account01
    - account02
    - account03
    child_ou:
      - name: ou01
        child_ou:
          - name: ou01-sub0
      - name: ou02
        child_ou:
          - name: ou02-sub0
      - name: ou03
        child_ou:
          - name: ou03-sub0
"""

COMPLEX_ORG_SPEC="""
root:
  - name: root
    accounts:
    - account01
    - account02
    - account03
    child_ou:
      - name: ou01
        accounts:
        - account04
        - account05
        child_ou:
          - name: ou01-1
            accounts:
            - account08
          - name: ou01-2
            accounts:
            - account09
            - account10
      - name: ou02
        accounts:
        - account06
        - account07
        child_ou:
          - name: ou02-1
            accounts:
            - account11
          - name: ou02-2
            accounts:
            - account12
            - account13
"""

def mock_org_from_spec(client, root_id, parent_id, spec):
    for ou in spec:
        if ou['name'] == 'root':
            ou_id = root_id
        else:
            ou_id = client.create_organizational_unit(
                ParentId=parent_id, 
                Name=ou['name'],
            )['OrganizationalUnit']['Id']
        if 'accounts' in ou:
            for name in ou['accounts']:
                account_id = client.create_account(
                    AccountName=name,
                    Email=name + '@example.com',
                )['CreateAccountStatus']['AccountId']
                client.move_account(
                    AccountId=account_id,
                    SourceParentId=root_id,
                    DestinationParentId=ou_id,
                )
        if 'child_ou' in ou:
            mock_org_from_spec(client, root_id, ou_id, ou['child_ou'])


def build_mock_org(spec):
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org._get_org_client()
    client.create_organization(FeatureSet='ALL')
    org_id = client.describe_organization()['Organization']['Id']
    root_id = client.list_roots()['Roots'][0]['Id']
    mock_org_from_spec(client, root_id, root_id, yaml.load(spec)['root'])
    return (org_id, root_id)

def clean_up():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    if os.path.isdir(org.cache_dir):
        shutil.rmtree(org.cache_dir)

@mock_organizations
def test_org():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    assert isinstance(org, orgs.Org)
    assert org.master_account_id == MASTER_ACCOUNT_ID
    assert org.access_role == ORG_ACCESS_ROLE


@mock_sts
@mock_organizations
def test__get_org_client():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org._get_org_client()
    assert str(type(client)).find('botocore.client.Organizations') > 0

@mock_sts
@mock_organizations
def test_load_client():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org._load_client()
    assert str(type(org.client)).find('botocore.client.Organizations') > 0

@mock_sts
@mock_organizations
def test_load_org():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org._get_org_client()
    client.create_organization(FeatureSet='ALL')
    org._load_client()
    org._load_org()
    assert org.id is not None
    assert org.root_id is not None

@mock_sts
@mock_organizations
def test_org_objects():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org._get_org_client()
    client.create_organization(FeatureSet='ALL')
    org._load_client()
    org._load_org()

    org_object = orgs.OrgObject(org, name='generic')
    assert isinstance(org_object, orgs.OrgObject)
    assert org_object.organization_id == org.id
    assert org_object.master_account_id == org.master_account_id
    assert org_object.name == 'generic'

    account = orgs.OrgAccount(
        org,
        name='account01',
        id='112233445566',
        parent_id=org.root_id,
        email='account01@example.org',
    )
    assert isinstance(account, orgs.OrgAccount)
    assert account.organization_id == org.id
    assert account.master_account_id == org.master_account_id
    assert account.name == 'account01'
    assert account.id == '112233445566'
    assert account.parent_id == org.root_id
    assert account.email == 'account01@example.org'

    ou = orgs.OrganizationalUnit(
        org,
        name='production',
        id='o-jfk0',
        parent_id=org.root_id,
    )
    assert isinstance(ou, orgs.OrganizationalUnit)
    assert ou.organization_id == org.id
    assert ou.master_account_id == org.master_account_id
    assert ou.name == 'production'
    assert ou.id == 'o-jfk0'
    assert ou.parent_id == org.root_id


@mock_sts
@mock_organizations
def test_load_accounts():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org_id, root_id = build_mock_org(SIMPLE_ORG_SPEC)
    org._load_client()
    org._load_org()
    org._load_accounts()
    assert len(org.accounts) == 3
    assert isinstance(org.accounts[0], orgs.OrgAccount)
    assert org.accounts[0].parent_id == org.root_id

 
@mock_sts
@mock_organizations
def test_load_org_units():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org_id, root_id = build_mock_org(SIMPLE_ORG_SPEC)
    org._load_client()
    org._load_org()
    org._load_org_units()
    assert len(org.org_units) == 6
    for ou in org.org_units:
        assert isinstance(ou, orgs.OrganizationalUnit)

@mock_sts
@mock_organizations
def test_org_cache():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org_id, root_id = build_mock_org(SIMPLE_ORG_SPEC)
    org._load_client()
    org._load_org()
    org._load_accounts()
    org._load_org_units()

    org._save_cached_org_to_file()
    assert os.path.exists(org.cache_file)

    os.remove(org.cache_file)
    with pytest.raises(RuntimeError) as e:
        loaded_dump = org._get_cached_org_from_file()
    assert str(e.value) == 'Cache file not found'

    org._save_cached_org_to_file()
    timestamp = os.path.getmtime(org.cache_file) - 3600
    os.utime(org.cache_file,(timestamp,timestamp))
    with pytest.raises(RuntimeError) as e:
        loaded_dump = org._get_cached_org_from_file()
    assert str(e.value) == 'Cache file too old'

    org._save_cached_org_to_file()
    org_dump = org.dump()
    loaded_dump = org._get_cached_org_from_file()
    assert loaded_dump == org_dump

    org_from_pickle_file = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org_from_pickle_file._load_org_dump(loaded_dump)
    org.client = None
    assert org.dump() == org_from_pickle_file.dump()

@mock_sts
@mock_organizations
def test_load():
    org_id, root_id = build_mock_org(SIMPLE_ORG_SPEC)
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    clean_up()
    assert not os.path.exists(org.cache_dir)
    assert not os.path.exists(org.cache_file)
    org.load()
    print(org.cache_file)
    assert os.path.exists(org.cache_file)
    assert org.id == org_id
    assert org.root_id == root_id
    assert len(org.accounts) == 3
    assert len(org.org_units) == 6

    org_from_pickle_file = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org_from_pickle_file.load()
    assert org.dump() == org_from_pickle_file.dump()
    clean_up()

 
@mock_sts
@mock_organizations
def test_dump_accounts():
    org_id, root_id = build_mock_org(SIMPLE_ORG_SPEC)
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org.load()

    response = org.dump_accounts()
    assert isinstance(response, list)
    assert len(response) == 3
    mock_account_names = yaml.load(SIMPLE_ORG_SPEC)['root'][0]['accounts']
    for account in response:
        assert account['master_account_id'] == MASTER_ACCOUNT_ID
        assert account['organization_id'] == org_id
        assert account['name'] in mock_account_names
        assert re.compile(r'[0-9]{12}').match(account['id'])
        assert account['parent_id'] == root_id
        assert account['email'] == account['name'] + '@example.com'
        assert len(account['aliases']) == 0
        assert len(account['credentials']) == 0

    response = org.list_accounts_by_name()
    assert isinstance(response, list)
    assert len(response) == 3
    assert sorted(response) == mock_account_names

    response = org.list_accounts_by_id()
    assert isinstance(response, list)
    assert len(response) == 3
    for account_id in response:
        assert re.compile(r'[0-9]{12}').match(account_id)
    clean_up()

 
@mock_sts
@mock_organizations
def test_get_account_id_by_name():
    org_id, root_id = build_mock_org(SIMPLE_ORG_SPEC)
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org.load()
    account_id = org.get_account_id_by_name('account01')
    accounts_by_boto_client = org.client.list_accounts()['Accounts']
    assert account_id == next((
        a['Id'] for a in accounts_by_boto_client if a['Name'] == 'account01'
    ), None)
    clean_up()

 
@mock_sts
@mock_organizations
def test_get_account_name_by_id():
    org_id, root_id = build_mock_org(SIMPLE_ORG_SPEC)
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org.load()
    account_id = org.get_account_id_by_name('account01')
    account_name = org.get_account_name_by_id(account_id)
    accounts_by_boto_client = org.client.list_accounts()['Accounts']
    assert account_name == next((
        a['Name'] for a in accounts_by_boto_client if a['Id'] == account_id
    ), None)
    clean_up()

 
@mock_sts
@mock_organizations
def test_get_account():
    org_id, root_id = build_mock_org(SIMPLE_ORG_SPEC)
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org.load()
    account = org.get_account('account01')
    assert isinstance(account, orgs.OrgAccount)
    assert org.get_account(account) == account
    assert account.name == 'account01'
    assert account.id == org.get_account_id_by_name('account01')
    clean_up()


@mock_sts
@mock_organizations
def test_dump_org_units():
    org_id, root_id = build_mock_org(SIMPLE_ORG_SPEC)
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org.load()

    response = org.dump_org_units()
    assert isinstance(response, list)
    assert len(response) == 6
    for ou in response:
        assert isinstance(ou, dict)
        assert ou['master_account_id'] == MASTER_ACCOUNT_ID
        assert ou['organization_id'] == org_id
        assert ou['name'].startswith('ou0')
        assert ou['id'].startswith('ou-')
        assert (
            ou['parent_id'] == root_id
            or ou['parent_id'].startswith(root_id.replace('r-', 'ou-'))
        )

    response = org.list_org_units_by_name()
    assert isinstance(response, list)
    assert len(response) == 6
    for ou_name in response:
        assert ou_name.startswith('ou0')

    response = org.list_org_units_by_id()
    assert isinstance(response, list)
    assert len(response) == 6
    for ou_id in response:
        assert ou_id.startswith('ou-')
    clean_up()

 
@mock_sts
@mock_organizations
def test_get_org_unit_id():
    org_id, root_id = build_mock_org(SIMPLE_ORG_SPEC)
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org.load()
    ou = org.org_units[0]
    assert ou.id == org.get_org_unit_id(ou)
    assert ou.id == org.get_org_unit_id(ou.id)
    assert ou.id == org.get_org_unit_id(ou.name)
    clean_up()

 
@mock_sts
@mock_organizations
def test_list_accounts_in_ou():
    org_id, root_id = build_mock_org(COMPLEX_ORG_SPEC)
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org.load()
    org_units = org.dump_org_units()
    #print(org_units)
    org_accounts = org.dump_accounts()
    #print(org_accounts)

    #ou_id = org.get_org_unit_id('ou02')
    #print(root_id)
    response = org.list_accounts_in_ou(root_id)
    #print(response)
    accounts_by_boto_client = org.client.list_accounts_for_parent(
        ParentId=root_id
        #ParentId=ou_id
    )['Accounts']
    #print(accounts_by_boto_client)
    for account in response:
        assert account.id == next((
            a['Id'] for a in accounts_by_boto_client
            if a['Name'] == account.name
        ), None)

    response = org.list_accounts_in_ou_by_name(ou_id)
    assert sorted(response) == sorted([a['Name'] for a in accounts_by_boto_client])

    response = org.list_accounts_in_ou_by_id(ou_id)
    assert sorted(response) == sorted([a['Id'] for a in accounts_by_boto_client])
    clean_up()

 
"""
@mock_sts
@mock_organizations
def test_list_accounts_under_ou():
    org_id, root_id = build_mock_org(COMPLEX_ORG_SPEC)
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org.load()
    ou02_id = org.get_org_unit_id_by_name('ou02')
    ou02_1_id = org.get_org_unit_id_by_name('ou02-1')

    response = org._recurse_org_units_under_ou(root_id)
    assert len(response) == 6
    for ou_id in response:
        assert ou_id.startswith('ou-')

    response = org._recurse_org_units_under_ou(ou02_id)
    assert len(response) == 2

    response = org.list_accounts_under_ou(root_id)
    assert len(response) == 13
    for account in response:
        assert account['Name'].startswith('account')
        assert re.compile(r'[0-9]{12}').match(account['Id'])

    response = org.list_accounts_under_ou(ou02_id)
    assert len(response) == 5

    response = org.list_accounts_under_ou(ou02_1_id)
    assert len(response) == 1

    response = org.list_accounts_under_ou_by_name(root_id)
    assert len(response) == 13
    for account_name in response:
        assert account_name.startswith('account')

    response = org.list_accounts_under_ou_by_id(ou02_id)
    assert len(response) == 5
    for account_id in response:
        assert re.compile(r'[0-9]{12}').match(account_id)
    clean_up()


@mock_sts
@mock_organizations
def test_org_dump():
    org_id, root_id = build_mock_org(COMPLEX_ORG_SPEC)
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    org.load()
    crawler = crawlers.Crawler(org)
    crawler.load_account_credentials()
    dump = org.dump()
    assert isinstance(dump, dict)
    assert dump['id']
    assert dump['id'].startswith('o-')
    assert re.compile(r'[0-9]{12}').match(dump['master_account_id'])
    assert dump['root_id'].startswith('r-')
    for account in dump['accounts']:
        assert re.compile(r'[0-9]{12}').match(account['id'])
        assert account['name'].startswith('account')
        assert account['parent_id'].startswith(('r-', 'ou-'))
    for ou in dump['org_units']:
        assert ou['id'].startswith('ou-')
        assert ou['name'].startswith('ou')
        assert ou['parent_id'].startswith(('r-', 'ou-'))
    json_dump = org.dump_json()
    assert isinstance(json_dump, str)
    assert json.loads(json_dump) == dump
    clean_up()
"""
