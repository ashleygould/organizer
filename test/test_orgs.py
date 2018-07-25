import re
import botocore
import boto3
import yaml
import moto
from moto import mock_organizations, mock_sts

from organizer import orgs

ORG_ACCESS_ROLE='myrole'
MASTER_ACCOUNT_ID='123456789012'
MOCK_ACCOUNT_NAMES = ['account01', 'account02', 'account03']
MOCK_OU_NAMES = ['ou01', 'ou02', 'ou03']

COMPLEX_ORG_SPEC="""
root:
  - name: root
    accounts:
    - account01
    - account02
    - account03
    ou:
      - name: ou01
        accounts:
        - account04
        - account05
      - name: ou02
        accounts:
        - account06
        - account07
        ou:
          - name: ou01-1
            accounts:
            - account08
          - name: ou01-2
            accounts:
            - account09
            - account10
"""

def mock_org_from_spec(client, spec):
    print(spec)
    print(type(spec))
    for ou in spec:
        if 'ou' in ou:
            mock_org_from_spec(client, ou['ou'])


@mock_sts
@mock_organizations
def test_mock_org():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org.get_org_client()
    mock_org_from_spec(client, yaml.load(COMPLEX_ORG_SPEC)['root'])
    #assert False

    
    

def setup_mock_organization(client):
    client.create_organization(FeatureSet='ALL')
    org_id = client.describe_organization()['Organization']['Id']
    root_id = client.list_roots()['Roots'][0]['Id']
    for name in MOCK_ACCOUNT_NAMES:
        client.create_account(AccountName=name, Email=name + '@example.com')
    for name in MOCK_OU_NAMES:
        ou = client.create_organizational_unit(
                ParentId=root_id, Name=name)['OrganizationalUnit']
        client.create_organizational_unit(ParentId=ou['Id'], Name=ou['Name'] +'-sub0')
    return [org_id, root_id]


@mock_organizations
def test_org():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    assert isinstance(org, orgs.Org)
    assert org.master_account_id == MASTER_ACCOUNT_ID
    assert org.access_role == ORG_ACCESS_ROLE


@mock_sts
@mock_organizations
def test_get_org_client():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org.get_org_client()
    assert str(type(client)).find('botocore.client.Organizations') > 0

@mock_sts
@mock_organizations
def test_load_org():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org.get_org_client()
    client.create_organization(FeatureSet='ALL')
    org.load_org()
    assert org.id is not None
    assert org.root_id is not None
 
@mock_sts
@mock_organizations
def test_org_objects():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org.get_org_client()
    client.create_organization(FeatureSet='ALL')
    org.load_org()
    org_object = orgs.OrgObject(org, 'generic')
    assert isinstance(org_object, orgs.OrgObject)
    assert org_object.organization_id == org.id
    assert org_object.master_account_id == org.master_account_id
    assert org_object.name == 'generic'
    account = orgs.OrgAccount(org, 'account01', '112233445566', org.root_id)
    assert isinstance(account, orgs.OrgAccount)
    assert account.organization_id == org.id
    assert account.master_account_id == org.master_account_id
    assert account.name == 'account01'
    assert account.id == '112233445566'
    assert account.parent_id == org.root_id
    ou = orgs.OrganizationalUnit(org, 'production', 'o-jfk0', org.root_id)
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
    client = org.get_org_client()
    org_id, root_id = setup_mock_organization(client)
    org.load_org()
    org.load_accounts()
    assert len(org.accounts) == 3
    assert isinstance(org.accounts[0], orgs.OrgAccount)
    assert org.accounts[0].parent_id == org.root_id

 
@mock_sts
@mock_organizations
def test_load_org_units():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org.get_org_client()
    org_id, root_id = setup_mock_organization(client)
    org.load_org()
    org.load_org_units()
    assert len(org.org_units) == 6
    for ou in org.org_units:
        assert isinstance(ou, orgs.OrganizationalUnit)

 
@mock_sts
@mock_organizations
def test_load():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org.get_org_client()
    org_id, root_id = setup_mock_organization(client)
    org.load()
    assert org.id == org_id
    assert org.root_id == root_id
    assert len(org.accounts) == 3
    assert len(org.org_units) == 6

 
@mock_sts
@mock_organizations
def test_list_accounts():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org.get_org_client()
    org_id, root_id = setup_mock_organization(client)
    org.load()
    response = org.list_accounts()
    assert isinstance(response, list)
    assert len(response) == 3
    for account in response:
        assert account['Name'] in MOCK_ACCOUNT_NAMES
    for account in response:
        assert re.compile(r'[0-9]{12}').match(account['Id'])
    response = org.list_accounts_by_name()
    assert isinstance(response, list)
    assert len(response) == 3
    assert sorted(response) == MOCK_ACCOUNT_NAMES
    response = org.list_accounts_by_id()
    assert isinstance(response, list)
    assert len(response) == 3
    for account_id in response:
        assert re.compile(r'[0-9]{12}').match(account_id)

 
@mock_sts
@mock_organizations
def test_list_org_units():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org.get_org_client()
    org_id, root_id = setup_mock_organization(client)
    org.load()
    response = org.list_organizational_units()
    assert isinstance(response, list)
    assert len(response) == 6
    for ou in response:
        assert isinstance(ou, dict)
        assert ou['Name'].startswith('ou0')
        assert ou['Id'].startswith('ou-')
    response = org.list_organizational_units_by_name()
    assert isinstance(response, list)
    assert len(response) == 6
    for ou_name in response:
        assert ou_name.startswith('ou0')
    response = org.list_organizational_units_by_id()
    assert isinstance(response, list)
    assert len(response) == 6
    for ou_id in response:
        assert ou_id.startswith('ou-')

 
@mock_sts
@mock_organizations
def test_account_id_by_name():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org.get_org_client()
    org_id, root_id = setup_mock_organization(client)
    org.load()
    account_id = org.get_account_id_by_name('account01')
    accounts_by_boto_client = client.list_accounts()['Accounts']
    assert account_id == next((
        a['Id'] for a in accounts_by_boto_client if a['Name'] == 'account01'
    ), None)

 
@mock_sts
@mock_organizations
def test_account_id_by_name():
    org = orgs.Org(MASTER_ACCOUNT_ID, ORG_ACCESS_ROLE)
    client = org.get_org_client()
    org_id, root_id = setup_mock_organization(client)
    org.load()
    ou_id = org.get_org_unit_id_by_name('ou02')
    ou_by_boto_client = client.list_organizational_units_for_parent(
            ParentId=root_id)['OrganizationalUnits']
    assert ou_id == next((
        ou['Id'] for ou in ou_by_boto_client if ou['Name'] == 'ou02'
    ), None)
