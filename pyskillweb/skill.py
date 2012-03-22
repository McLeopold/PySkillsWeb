#!/usr/bin/env python2
import requests
import json
from argparse import ArgumentParser

api = 'http://localhost:8000'

def print_response(res):
    print(res.status_code)
    print(res.headers['content-type'])
    print
    print(res.text)

def get_contests():
    r = requests.get(api + '/contests/')
    print_response(r)

def get_contest(contest):
    r = requests.get(api + '/contests/' + contest)
    print_response(r)

def post_contest(name):
    payload = {'name': name}
    r = requests.post(api + '/contests/', data=json.dumps(payload))
    print_response(r)

def get_parser():
    parser = ArgumentParser(description='Interface to Skill API')
    parser.add_argument('action', nargs='?', default='get',
                        choices=['get', 'new'])
    parser.add_argument('contest', nargs='?')
    return parser

def action_get(args):
    if args.contest:
        get_contest(args.contest)
    else:
        get_contests()

def action_new(args):
    if args.contest:
        post_contest(args.contest)
    else:
        print('Error: contest name not specified')

if __name__ == '__main__':
    parser = get_parser()
    args = parser.parse_args()
    actions = {'get': action_get,
               'new': action_new }
    actions[args.action](args)
