# -*- coding: utf8 -*-
import requests
import json
from pymongo import MongoClient
import pymongo
import ConfigParser
import time
import datetime
import os
import sys


cf = ConfigParser.ConfigParser()
cf.read('/etc/instance_monitor.conf')
rule_url = cf.get('api', 'rule_url')
store_interval = int(cf.get('api', 'store_interval'))
mongo_ip = cf.get('mongo', 'ip')
mongo_port = int(cf.get('mongo', 'port'))
client = MongoClient(mongo_ip, mongo_port)
db = client.rule


def run():
    while True:
        try:
            headers = {'content-type': 'application/json'}
            re = requests.get(rule_url, headers=headers)
            alarms = json.loads(re.content)['objects']
            now = datetime.datetime.now()
            result = {'alarms': alarms, 'time': now}
            collection = db['rule']
            r = collection.update({}, result)
            if r['updatedExisting'] is False:
                collection.insert_one(result)
        except:
            pass

        time.sleep(store_interval)


def daemonize(pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError, e:
        sys.stderr.write("fork #1 failed: (%d) %s\n" % (e.errorno, e.strerror))
        sys.exit(1)

    os.chdir('/')
    os.umask(0)
    os.setsid()

    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError, e:
        sys.stderr.write("fork #2 failed: (%d) %s\n" % (e.errorno, e.strerror))
        sys.exit(1)

    for f in sys.stdout, sys.stderr:
        f.flush()

    si = file(stdin, 'r')
    so = file(stdout, 'a+')
    se = file(stderr, 'a+', 0)
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())
    pid = str(os.getpid())
    file(pidfile, 'w+').write("%s\n" % pid)


def start():
    daemonize(pidfile='/var/run/instance_rule.pid', stderr='/var/log/instance_rule.log')
    run()


if __name__ == '__main__':
    start()
