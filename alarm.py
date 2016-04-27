# -*- coding: utf8 -*-
import libvirt
import libvirt_qemu
import requests
import json
import ConfigParser
import pymongo
from pymongo import MongoClient


cf = ConfigParser.ConfigParser()
cf.read('/etc/instance_monitor.conf')
rule_url = cf.get('api', 'rule_url')
post_url = cf.get('api', 'post_url')
mongo_ip = cf.get('mongo', 'ip')
mongo_port = int(cf.get('mongo', 'port'))


rule = dict(cpu_load_high=None, cpu_load_low=None, cpu_usage_high=None, cpu_usage_low=None, disk_read_speed_high=None,
            disk_read_speed_low=None, net_read_speed_high=None, net_read_speed_low=None, net_write_speed_high=None,
            net_write_speed_low=None, process_numb_high=None, process_numb_low=None, disk_write_speed_high=None,
            disk_write_speed_low=None, memory_idle_high=None, memory_idle_low=None)
rule_low = dict(cpu_load_low=None, cpu_usage_low="result['cpuusage']['usage'][0]",
                disk_read_speed_low="result['diskstat'][j]['statistics']['speed_kb_read']",
                net_read_speed_low="result['netstat'][0]['receive_byte_speed']",
                net_write_speed_low="result['netstat'][0]['transmit_byte_speed']",
                process_numb_low="result['processinfo']['count']",
                disk_write_speed_low="result['diskstat'][j]['statistics']['speed_kb_write']",
                memory_idle_low="result['memstat']['total'] - result['memstat']['used']")
rule_high = dict(cpu_load_high=None, cpu_usage_high="result['cpuusage']['usage'][0]",
                 disk_read_speed_high="result['diskstat'][i]['statistics']['speed_kb_read']",
                 net_read_speed_high="result['netstat'][0]['receive_byte_speed']",
                 net_write_speed_high="result['netstat'][0]['transmit_byte_speed']",
                 process_numb_high="result['processinfo']['count']",
                 disk_write_speed_high="result['diskstat'][i]['statistics']['speed_kb_write']",
                 memory_idle_high="result['memstat']['total'] - result['memstat']['used']")
useless = ['contacts', 'notice_flag', 'mesage_flag', 'instance_name', 'instance_uuid', 'resource_uri', 'id']
event_dict = dict(cpu_load_high='CPU负载:%d 超过报警值:%d\n', cpu_load_low='CPU负载:%d 低于报警值:%d\n',
                  cpu_usage_high='CPU使用率:%d%% 超过报警值:%d%%\n', cpu_usage_low='CPU使用率:%d%% 低于报警值:%d%%\n',
                  disk_read_speed_high='磁盘%s读速度:%.2fKB/s 超过报警值:%dKB/s\n', disk_read_speed_low='磁盘%s读速度:%.2fKB/s 低于报警值:%dKB/s\n',
                  net_read_speed_high='网络上行速度:%.2fB/S 超过报警值:%dB/S\n', net_read_speed_low='网络上行速度:%.2fB/S 低于报警值:%dB/S\n',
                  net_write_speed_high='网络下行速度:%.2fB/S 超过报警值:%dB/S\n', net_write_speed_low='网络下行速度:%.2fB/S 低于报警值:%dB/S\n',
                  process_numb_high='进程数:%d 超过报警值:%d\n', process_numb_low='进程数:%d 低于报警值:%d\n',
                  disk_write_speed_high='磁盘%s写速度:%.2fKB/s 超过报警值:%dKB/s\n', disk_write_speed_low='磁盘%s写速度:%.2fKB/s 低于报警值:%dKB/s\n',
                  memory_idle_high='内存剩余量:%dMB 超过报警值:%dMB\n', memory_idle_low='内存剩余量:%dMB 低于报警值:%dMB\n')
post_data = {"detail": None,"name": None, "rule_id": None}

def get_alarm():
    client = MongoClient(mongo_ip, mongo_port)
    db = client.rule
    collection = db['rule']
    alarms = collection.find_one()['alarms']
    alarm_uuids = [alarm['instance_uuid'] for alarm in alarms]
    return alarms, alarm_uuids


def match_alarm(instance_uuid, result):
    alarms, alarm_uuids = get_alarm()
    if instance_uuid in alarm_uuids:
        for alarm in alarms:
            post_data['name'] = alarm['instance_name']
            post_data['rule_id'] = alarm['id']
            if alarm['instance_uuid'] == instance_uuid:
                # remove unnecessary field
                for bar in useless:
                    del alarm[bar]
                for bar in rule.keys():
                    if alarm[bar] is None:
                        del alarm[bar]
                # match rule
                cut_result(result)
                match_rule(alarm, result)
                break
    else:
        pass


def match_rule(alarm, result):
    event = ''
    high_rule = dict((k, rule_high[k]) for k in alarm.keys() if 'high' in k and rule_high[k] is not None)
    low_rule = dict((k, rule_low[k]) for k in alarm.keys() if 'low' in k and rule_low[k] is not None)

    # high
    for r in high_rule:
        try:
            if eval(high_rule[r]) > alarm[r]:
                # print '%s alarm!' % r
                event += event_dict[r] % (eval(high_rule[r]), alarm[r])
        except KeyError:
            pass
        except Exception:
            for i, _ in enumerate(result['diskstat']):
                if eval(high_rule[r]) > alarm[r]:
                    # print '%s %s alarm!' % (result['diskstat'][i]['devname'], r)
                    event += event_dict[r] % (result['diskstat'][i]['devname'], eval(high_rule[r]), alarm[r])

    # low
    for r in low_rule:
        try:
            if eval(low_rule[r]) < alarm[r]:
                # print '%s alarm!' % r
                event += event_dict[r] % (eval(low_rule[r]), alarm[r])
        except KeyError:
            pass
        except Exception:
            for j, _ in enumerate(result['diskstat']):
                if eval(low_rule[r]) < alarm[r]:
                    # print '%s %s alarm!' % (result['diskstat'][j]['devname'], r)
                    event += event_dict[r] % (result['diskstat'][j]['devname'], eval(low_rule[r]), alarm[r])

    if event is not '':
        post_data['detail'] = event
        post(post_url, post_data)


def post(url, data):
    headers = {'content-type': 'application/json'}
    return requests.post(url, data=json.dumps(data), headers=headers)


def cut_result(result):
    try:
        result['diskstat'] = filter(lambda diskstat: 'vd' or 'disk' in diskstat['devname'], result['diskstat'])
        result['netspeed'] = filter(lambda netspeed: 'eth0' in netspeed['devname'], result['netspeed'])
    except KeyError:
        pass

if __name__ == '__main__':
    conn = libvirt.open(None)
    ids = conn.listDomainsID()
    for id in ids:
        dom = conn.lookupByID(id)
        instance_uuid = dom.UUIDString()
        result = libvirt_qemu.qemuAgentCommand(dom, '{"execute":"guest-get-total-info"}', 1, 0)
        result = eval(result)['return']
        match_alarm(instance_uuid, result)

