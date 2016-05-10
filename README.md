# instance_monitor.py
每隔指定时间```interval```调用libvirt获取guest-agent数据，进行网络速度、磁盘速度计算存入MongoDB，调用报警规则对本次数据进行处理。

### run()
程序主体。
- 调用libvirt获取所有正在运行的虚拟机的监控数据
- 对磁盘、网络数据总量进行处理
- 对磁盘、网络速度进行计算
- 将处理完的监控数据存入MongoDB
- 进行报警处理
- 磁盘、网络数据总量中间变量```total_collection、current_collection```存入MongoDB


### daemonize()
使instance_monitor.py成为守护进程。

### get_speed()
将总量除以间隔时间计算磁盘速度和网络速度。

### add_data()
磁盘读写总量和网络流量总量在虚机重启后会清零，在虚机重启后加上重启前的数据保证总量不会因为重启被重置。


# alarm.py
从MongoDB获取报警规则对监控数据进行处理。


### get_alarm()
从MongoDB获取报警规则。

### match_alarm()
获取和instance_uuid匹配的报警规则。

### cut_result()
去除网络速度、磁盘速度中无用的项，只保留vdx、eth0的数据。

### match_rule()
对监控数据进行报警处理。

### post()
如果触发报警，post事件到API。


# instance_rule.py
每隔指定时间，从API获取报警规则，存入MongoDB来减轻API压力。

# guest_data.py
监控数据接口。返回count个监控数据给API。

# guest_data_time.py
监控数据接口。返回最近几小时/天的监控数据给API。

# guest_data_latest.py
监控数据接口。返回最新一条监控数据给API。

# instance_monitor.conf 
配置文件
- ```ip```: MongoDB IP
- ```port```: MongoDB port
- ```interval```: 采集监控数据间隔时间
- ```expire```: MongoDB存放数据有效期
- ```rule_url```: API地址
- ```post_url```: API地址
- ```store_interva```l: 存放报警规则的间隔时间