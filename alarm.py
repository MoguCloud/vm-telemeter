import libvirt
import libvirt_qemu
import requests
import json

url = 'http://172.18.16.30/api/instance-rule/'
rule = dict(cpu_load_high=None, cpu_load_low=None, cpu_usage_high=None, cpu_usage_low=None, disk_read_speed_high=None,
            disk_read_speed_low=None, net_read_speed_high=None, net_read_speed_low=None, net_write_speed_high=None,
            net_write_speed_low=None, process_numb_high=None, process_numb_low=None, disk_write_speed_high=None,
            disk_write_speed_low=None, memory_idle_high=None, memory_idle_low=None)
rule_low = dict(cpu_load_low=None, cpu_usage_low="result['cpuusage']['usage'][0]",
                disk_read_speed_low="result['diskstat'][j]['statistics']['speed_kb_read']",
                net_read_speed_low="result['netstat'][0]['receive_byte_speed']",
                net_write_speed_low="result['netstat'][0]['transmit_byte_speed']",
                process_numb_low="result['processinfo']['count']",
                disk_write_speed_low="result['diskstat'][i]['statistics']['speed_kb_write']",
                memory_idle_low="result['memstat']['total'] - result['memstat']['used']")
rule_high = dict(cpu_load_high=None, cpu_usage_high="result['cpuusage']['usage'][0]",
                 disk_read_speed_high="result['diskstat'][i]['statistics']['speed_kb_read']",
                 net_read_speed_high="result['netstat'][0]['receive_byte_speed']",
                 net_write_speed_high="result['netstat'][0]['transmit_byte_speed']",
                 process_numb_high="result['processinfo']['count']",
                 disk_write_speed_high="result['diskstat'][i]['statistics']['speed_kb_write']",
                 memory_idle_high="result['memstat']['total'] - result['memstat']['used']")
useless = ['contacts', 'notice_flag', 'mesage_flag', 'instance_name', 'instance_uuid', 'resource_uri', 'id']
# result = {'memstat': {'total': 129, 'used': 100}, 'netspeed': [{'transmit_byte_speed': 0, 'devname': 'docker0', 'receive_byte_speed': 12345},{'transmit_byte_speed': 0, 'devname': 'eth0', 'receive_byte_speed': 123}, {'transmit_byte_speed': 0, 'devname': 'lo', 'receive_byte_speed': 0}], 'netstat': [{'receive': {'multicast': 0, 'compressed': 0, 'errs': 0, 'packets': 11243982, 'frame': 0, 'drop': 0, 'bytes': 1252149291, 'fifo': 0}, 'transmit': {'carrier': 0, 'colls': 0, 'compressed': 0, 'errs': 0, 'packets': 357962, 'drop': 0, 'bytes': 89794629, 'fifo': 0}, 'devname': 'eth0'}, {'receive': {'multicast': 0, 'compressed': 0, 'errs': 0, 'packets': 0, 'frame': 0, 'drop': 0, 'bytes': 0, 'fifo': 0}, 'transmit': {'carrier': 0, 'colls': 0, 'compressed': 0, 'errs': 0, 'packets': 0, 'drop': 0, 'bytes': 0, 'fifo': 0}, 'devname': 'lo'}], 'diskstat': [{'devname': 'vda', 'statistics': {'kb_read': 188991, 'kb_write': 33683285, 'tps': 0.59, 'speed_kb_write': 1.0674157303370786, 'speed_kb_read': 290.0}}, {'devname': 'vdb', 'statistics': {'kb_read': 188991, 'kb_write': 33683285, 'tps': 0.59, 'speed_kb_write': 1.0674157303370786, 'speed_kb_read': 24999.0}}, {'devname': 'dm-0', 'statistics': {'kb_read': 964, 'kb_write': 0, 'tps': 0, 'speed_kb_write': 0.0, 'speed_kb_read': 0.0}}, {'devname': 'dm-1', 'statistics': {'kb_read': 159067, 'kb_write': 33681225, 'tps': 0.61, 'speed_kb_write': 1.0674157303370786, 'speed_kb_read': 0.0}}, {'devname': 'dm-2', 'statistics': {'kb_read': 640, 'kb_write': 0, 'tps': 0, 'speed_kb_write': 0.0, 'speed_kb_read': 0.0}}], 'host': {'instance_name': u'weichengxi-host1', 'hypervisor_hostname': u'cu01cp043'}, 'login': [], 'processinfo': {'count': 392, 'pro_stat': []}, 'cpuusage': {'count': 1, 'usage': [90, 0]}}


def get_alarm():
    headers = {'content-type': 'application/json'}
    re = requests.get(url, headers=headers)
    alarms = json.loads(re.content)['objects']
    alarm_uuids = [alarm['instance_uuid'] for alarm in alarms]
    return alarms, alarm_uuids


def match_alarm(instance_uuid, result):
    alarms, alarm_uuids = get_alarm()
    if instance_uuid in alarm_uuids:
        for alarm in alarms:
            if alarm['instance_uuid'] == instance_uuid:
                # remove unnecessary field
                for bar in useless:
                    del alarm[bar]
                for bar in rule.keys():
                    if alarm[bar] is None:
                        del alarm[bar]
                print 'alarm: %r\n' % alarm
                # match rule
                cut_result(result)
                match_rule(alarm, result)
                break
    else:
        pass


def match_rule(alarm, result):
    high_rule = dict((k, rule_high[k]) for k in alarm.keys() if 'high' in k and rule_high[k] is not None)
    low_rule = dict((k, rule_low[k]) for k in alarm.keys() if 'low' in k and rule_low[k] is not None)

    # high
    for r in high_rule:
        try:
            if eval(high_rule[r]) > alarm[r]:
                print '%s alarm!' % r
        except KeyError:
            pass
        except NameError:
            for i, _ in enumerate(result['diskstat']):
                if eval(high_rule[r]) > alarm[r]:
                    print '%s %s alarm!' % (result['diskstat'][i]['devname'], r)

    # low
    for r in low_rule:
        try:
            if eval(low_rule[r]) < alarm[r]:
                print '%s alarm!' % r
        except KeyError:
            pass
        except NameError:
            for j, _ in enumerate(result['diskstat']):
                if eval(low_rule[r]) < alarm[r]:
                    print '%s %s alarm!' % (result['diskstat'][j]['devname'], r)


def cut_result(result):
    try:
        result['diskstat'] = filter(lambda diskstat: 'vd' in diskstat['devname'], result['diskstat'])
        result['netspeed'] = filter(lambda netspeed: 'eth0' in netspeed['devname'], result['netspeed'])
    except KeyError:
        pass


conn = libvirt.open(None)
ids = conn.listDomainsID()
for id in ids:
    dom = conn.lookupByID(id)
    instance_uuid = dom.UUIDString()
    result = libvirt_qemu.qemuAgentCommand(dom, '{"execute":"guest-get-total-info"}', 1, 0)
    result = eval(result)['return']
    match_alarm(instance_uuid, result)


