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


cf = ConfigParser.ConfigParser()
cf.read('/etc/ga_to_mongo.conf')
interval = int(cf.get('mongo', 'interval'))
mongo_ip = cf.get('mongo', 'ip')
mongo_port = cf.get('mongo', 'port')


def run():
    logging.basicConfig(format='%(asctime)s.%(msecs)03d %(process)d %(levelname)s [-] %(message)s',
                        datefmt='%a, %d %b %Y %H:%M:%S',
                        filename='/var/log/ga_to_mongo.log',
                        filemode='w')
    client = MongoClient(mongo_ip, mongo_port)
    db = client.jk
    conn = libvirt.open(None)
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
                        collection = db[uuid]
                        get_speed(result)
                        collection.insert_one(result)
                    except pymongo.errors.AutoReconnect:
                        logging.error('Failed to connect mongodb')
                        continue
        time.sleep(20)


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


def main():
    daemonize(pidfile='/var/run/ga_to_mongo.pid', stderr='/var/log/ga_to_mongo.log')
    run()



if __name__ == '__main__':
    main()
