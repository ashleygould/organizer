#!/usr/bin/env python

"""
Usage:
    display_account_aliases.py ROLE

Arguments:
    ROLE        The AWS role name to assume when running organizer
"""

import boto3
from docopt import docopt

from organizer import crawlers, orgs, utils


def get_account_aliases(region, account):
    client = boto3.client('iam', region_name=region, **account.credentials)
    response = client.list_account_aliases()
    return dict(AccountAliases=response['AccountAliases'])


def main():
    args = docopt(__doc__)
    master_account_id = utils.get_master_account_id(args['ROLE'])
    org = orgs.Org(master_account_id, args['ROLE'])
    org.load()
    crawler = crawlers.Crawler(org)
    crawler.load_account_credentials()
    crawler.execute(get_account_aliases)
    print(utils.yamlfmt(crawler.get_payload_response_by_name('get_account_aliases').dump))


if __name__ == "__main__":
    main()
