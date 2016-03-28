import libvirt
import libvirt_qemu
import time
from bson import ObjectId
import logging
import datetime
import os
import ConfigParser
import sys
from pymongo import MongoClient
import pymongo
import copy
import alarm

cf = ConfigParser.ConfigParser()
cf.read('/etc/instance_monitor.conf')
interval = int(cf.get('mongo', 'interval'))
mongo_ip = cf.get('mongo', 'ip')
mongo_port = int(cf.get('mongo', 'port'))
expire = int(cf.get('mongo', 'expire'))


def run():
    logging.basicConfig(format='%(asctime)s.%(msecs)03d %(process)d %(levelname)s [-] %(message)s',
                        datefmt='%a, %d %b %Y %H:%M:%S',
                        filename='/var/log/ga_to_mongo.log',
                        filemode='w')
    client = MongoClient(mongo_ip, mongo_port)
    db = client.jk
    conn = libvirt.open(None)
    current_collection = db['current']
    total_collection = db['total']

    while True:
        ids = conn.listDomainsID()
        if ids is None or len(ids) == 0:
            logging.error('Failed to get running domains')
        for id in ids:
            dom = conn.lookupByID(id)
            uuid = dom.UUIDString()
            try:
                result = libvirt_qemu.qemuAgentCommand(dom, '{"execute":"guest-get-total-info"}', 1, 0)
                result = eval(result)['return']
                result['time'] = datetime.datetime.now()
            except Exception, e:
                if e[0] == 'Guest agent is not responding: QEMU guest agent is not available due to an error':
                    os.system('systemctl restart libvirtd')
                    conn = libvirt.open(None)
            else:
                if result != {}:
                    global collection
                    try:
                        # add_data
                        current_total = current_collection.find_one({'_id':uuid})
                        try:
                            if current_total is None:
                                current_total = result
                                total = {'processstat': [], 'login': [], 'netstat': [{'receive': {'bytes': 0, 'frame': 0, 'drop': 0, 'packets': 0, 'fifo': 0, 'multicast': 0, 'compressed': 0, 'errs': 0}, 'transmit': {'bytes': 0, 'drop': 0, 'packets': 0, 'fifo': 0, 'carrier': 0, 'colls': 0, 'compressed': 0, 'errs': 0}, 'devname': 'eth0'}, {'receive': {'bytes': 0, 'frame': 0, 'drop': 0, 'packets': 0, 'fifo': 0, 'multicast': 0, 'compressed': 0, 'errs': 0}, 'transmit': {'bytes': 0, 'drop': 0, 'packets': 0, 'fifo': 0, 'carrier': 0, 'colls': 0, 'compressed': 0, 'errs': 0}, 'devname': 'lo'}], 'diskstat': [{'statistics': {'kb_read': 0, 'speed_kb_read': 0, 'tps': 0, 'speed_kb_write': 0, 'kb_write': 0}, 'devname': 'vda'}], 'memstat': {'total': 0, 'used': 0}}
                            else:
                                total = total_collection.find_one({'_id':uuid})
                                if result['netstat'][0]['receive']['bytes'] >= current_total['netstat'][0]['receive']['bytes']:
                                    current_total = result
                                else:
                                    total, current_total = add_data(total, current_total)
                                    current_total = result
                                result, current_total = add_data(total, current_total)
                        except KeyError, e:
                            logging.error(e)
                            continue

                        # send result to mongodb
                        collection = db[uuid]
                        collection.create_index('time', expireAfterSeconds=expire)
                        get_speed(result)
                        collection.insert_one(result)

                        # alarm
                        try:
                            alarm.match_alarm(uuid, result)
                        except Exception, e:
                            logging.error(e)

                        # send add_data to mongodb
                        total.update({'_id': uuid})
                        current_total.update({'_id': uuid})
                        r1 = total_collection.update({'_id': uuid}, total)
                        r2 = current_collection.update({'_id': uuid}, current_total)
                        if r1['updatedExisting'] is False:
                            total_collection.insert_one(total)
                        if r2['updatedExisting'] is False:
                            current_collection.insert_one(current_total)

                    except pymongo.errors.AutoReconnect, e:
                        logging.error('Failed to connect mongodb %s' % e)
                        continue

                    except pymongo.errors.OperationFailure, e:
                        logging.error('Failed to connect mongodb' % e)
                        continue

        time.sleep(interval)


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


def get_speed(result):
    try:
        last_data = collection.find().sort('_id', -1).next()
    except StopIteration:
        for i in range(len(result['diskstat'])):
            result['diskstat'][i]['statistics']['speed_kb_write'] = 0
            result['diskstat'][i]['statistics']['speed_kb_read'] = 0
        result['netspeed'] = []
        for i in range(len(result['netstat'])):
            netspeed = {'devname': result['netstat'][i]['devname'], 'transmit_byte_speed': 0, 'receive_byte_speed': 0}
            result['netspeed'].append(netspeed)
    else:
        data_interval = (datetime.datetime.now() - last_data['time']).seconds
        try:
            for i in range(len(result['diskstat'])):
                for j in range(len(last_data['diskstat'])):
                    if result['diskstat'][i]['devname'] == last_data['diskstat'][j]['devname']:
                        result['diskstat'][i]['statistics']['speed_kb_write'] = (result['diskstat'][i]['statistics']['kb_write'] - last_data['diskstat'][j]['statistics']['kb_write']) / data_interval
                        result['diskstat'][i]['statistics']['speed_kb_read'] = (result['diskstat'][i]['statistics']['kb_read'] - last_data['diskstat'][j]['statistics']['kb_read']) / data_interval
                        if result['diskstat'][i]['statistics']['speed_kb_write'] < 0:
                            result['diskstat'][i]['statistics']['speed_kb_write'] = 0
                        if result['diskstat'][i]['statistics']['speed_kb_read'] < 0:
                            result['diskstat'][i]['statistics']['speed_kb_read'] = 0
        except Exception:
            for i in range(len(result['diskstat'])):
                result['diskstat'][i]['statistics']['speed_kb_write'] = 0
                result['diskstat'][i]['statistics']['speed_kb_read'] = 0

        result['netspeed'] = []
        try:
            for i in range(len(result['netstat'])):
                for j in range(len(last_data['netstat'])):
                    netspeed = {}
                    if result['netstat'][i]['devname'] == last_data['netstat'][j]['devname']:
                        netspeed['devname'] = result['netstat'][i]['devname']
                        netspeed['transmit_byte_speed'] = (result['netstat'][i]['transmit']['bytes'] - last_data['netstat'][i]['transmit']['bytes']) / data_interval
                        netspeed['receive_byte_speed'] = (result['netstat'][i]['receive']['bytes'] - last_data['netstat'][i]['receive']['bytes']) / data_interval
                        if netspeed['transmit_byte_speed'] < 0:
                            netspeed['transmit_byte_speed'] = 0
                        if netspeed['receive_byte_speed'] < 0:
                            netspeed['receive_byte_speed'] = 0
                        result['netspeed'].append(netspeed)
        except Exception:
            for i in range(len(result['netstat'])):
                netspeed['devname'] = result['netstat'][i]['devname']
                netspeed['transmit_byte_speed'] = 0
                netspeed['receive_byte_speed'] = 0
                result['netspeed'].append(netspeed)


def add_data(previous, current):
    current_tmp = copy.deepcopy(current)
    previous_diskstat = previous['diskstat']
    current_diskstat = current['diskstat']
    previous_netstat = previous['netstat']
    current_netstat = current['netstat']
    for pre in previous_diskstat:
        for cur in current_diskstat:
            if pre['devname'] == cur['devname']:
                cur['statistics']['kb_read'] += pre['statistics']['kb_read']
                cur['statistics']['kb_write'] += pre['statistics']['kb_write']

    for pre in previous_netstat:
        for cur in current_netstat:
            if pre['devname'] == cur['devname']:
                for keys in cur['receive']:
                    cur['receive'][keys] += pre['receive'][keys]
                for keys in cur['transmit']:
                    cur['transmit'][keys] += pre['transmit'][keys]
    return current, current_tmp


def start():
    daemonize(pidfile='/var/run/instance_monitor.pid', stderr='/var/log/instance_monitor.log')
    run()


if __name__ == '__main__':
    start()
