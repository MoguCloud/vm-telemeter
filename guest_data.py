import pymongo
from pymongo import MongoClient
import datetime
from bson.son import SON


client = MongoClient(ip, port)
db = client.jk


def get_mem(uuid, count):
    result_dict = {'time': [], 'data': []}
    collection = db[uuid]
    mem = collection.find({}, {'time': 1, 'memstat.used': 1}).sort('_id', pymongo.DESCENDING).limit(count)
    for i in mem:
        result_dict['data'].append(i['memstat']['used'])
        result_dict['time'].append(datetime.datetime.strftime(i['time'], '%Y-%m-%d %H:%M'))
    mem_total = collection.find_one()['memstat']['total']
    result_dict.update({'total': mem_total})
    return result_dict


def get_cpu(uuid, count):
    result_dict = {'time': [], 'data': []}
    collection = db[uuid]
    cpu = collection.find({}, {'time': 1, 'cpuusage.usage': 1}).sort('_id', pymongo.DESCENDING).limit(count)
    for i in cpu:
        result_dict['data'].append(i['cpuusage']['usage'][0])
        result_dict['time'].append(datetime.datetime.strftime(i['time'], '%Y-%m-%d %H:%M'))
    return result_dict


def get_process(uuid, count):
    result_dict = {'time': [], 'data': []}
    collection = db[uuid]
    process = collection.find({}, {'time': 1, 'processinfo.count': 1}).sort('_id', pymongo.DESCENDING).limit(count)
    for i in process:
        result_dict['data'].append(i['processinfo']['count'])
        result_dict['time'].append(datetime.datetime.strftime(i['time'], '%Y-%m-%d %H:%M'))
    return result_dict


def get_receive_netspeed(uuid, count):
    return get_netspeed(uuid, count, 'receive')


def get_transmit_netspeed(uuid, count):
    return get_netspeed(uuid, count, 'transmit')


def get_netspeed(uuid, count, switch):
    mapping = {'transmit': '$netspeed.transmit_byte_speed', 'receive': '$netspeed.receive_byte_speed'}
    switch = mapping[switch]
    collection = db[uuid]
    result_dict = {'time': [], 'data': []}
    unwind = {'$unwind': '$netspeed'}
    match = {'$match': { 'netspeed.devname': 'eth0' }}
    group = {'$group': {'_id': '$_id', 'buffer': {'$push': switch}, 'time': {'$first': '$time'}}}
    sort = {'$sort': SON([('_id', -1)])}
    reverse = {'$sort': SON([('_id', 1)])}
    limit = {'$limit': count}
    netspeed = collection.aggregate([sort, limit, unwind, match, group, reverse])
    for i in netspeed:
        result_dict['data'].append(i['buffer'][0])
        result_dict['time'].append(datetime.datetime.strftime(i['time'], '%Y-%m-%d %H:%M'))
    return result_dict


def get_read_disk(uuid, count):
    return get_disk(uuid, count, 'read')


def get_write_disk(uuid, count):
    return get_disk(uuid, count, 'write')


def get_disk(uuid, count, switch):
    mapping = {'read': '$diskstat.statistics.speed_kb_read', 'write': '$diskstat.statistics.speed_kb_write'}
    switch = mapping[switch]
    collection = db[uuid]
    result_dict = {'data': {}, 'dev_list': []}
    unwind = {'$unwind': '$diskstat'}
    match = {'$match': { 'diskstat.devname': {'$regex': 'vd|disk'}}}
    group = {'$group': {'_id': '$_id', 'dev': {'$push': '$diskstat.devname'}, 'speed': {'$push': switch}, 'time': {'$push': '$time'}}}
    sort = {'$sort': SON([('_id', -1)])}
    reverse = {'$sort': SON([('_id', 1)])}
    limit = {'$limit': count}
    diskspeed = collection.aggregate([sort, limit, unwind, match, group, sort, reverse])
    for i in diskspeed:
        for z in zip(i['speed'], i['dev'], i['time']):
            speed, devname, time = z
            if not result_dict['data'].has_key(devname):
                result_dict['dev_list'].append(devname)
                result_dict['data'][devname] = {'data': [], 'time': []}
            result_dict['data'][devname]['data'].append(speed)
            result_dict['data'][devname]['time'].append(datetime.datetime.strftime(time, '%Y-%m-%d %H:%M'))
    return result_dict


entry = dict(mem=get_mem, cpu=get_cpu, disk_read=get_read_disk, disk_write=get_write_disk,
             net_receive=get_receive_netspeed, net_transmit=get_transmit_netspeed, process=get_process)


def get_data(option, uuid, count):
    try:
        result = entry[option](uuid, count)
    except Exception:
        result = {}
    return result

