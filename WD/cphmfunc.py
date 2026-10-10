# coding:utf8
import multiprocessing
import os
import sys
import time

import psutil

from publicfunc import PublicFunc


class CphmFunc(PublicFunc):

    def get_switch_base_data(self):
        frame_type_value = {
            'C5': '配置',
            'CA': '升级帧',
            '0F': '心跳帧',
            '3F': '数据帧',
            '5F': '应答帧',
            'FF': '无效',
            'CB': '升级数据包回应'
        }

        code_type_value = {

            '0F': '心跳帧',

            '50': '模块发送模拟量曲线数据',
            '51': '模块发送开关量数据',
            '52': '模块发送继电器状态数据',
            '53': '模块发送表示电压数据',
            '54': '模块发送电参数数据',
            '57': '模块发送模拟量曲线分包数据',
            '25': '模块发送重启指令',

            '61': '上位机采集开关量数据',
            '62': '上位机采集继电器状态数据',
            '63': '上位机采集表示电压数据',
            '64': '上位机采集电参数数据',
            '65': '交控道岔采集表示电流曲线(交流：x1，直流：表示电流)',

            'A7': '温度数据读取命令',
            'A8': '位移数据读取命令',
            'A9': '温度数据主动上送命令',
            'AA': '位移数据主动上送命令',
        }

        curve_type_value = {
            '00': '无效',
            '01': 'A相电流曲线，精度0.01A',
            '02': 'B相电流曲线，精度0.01A',
            '03': 'C相电流曲线，精度0.01A',
            '04': '功率曲线，精度0.1W',
            '05': 'AB相电压曲线，精度0.01V',
            '06': 'BC相电压曲线，精度0.01V',
            '07': 'AC相电压曲线，精度0.01V',
            '08': '阻力曲线，精度0.01kN',
            '09': '晃动量曲线，精度0.01mm',
            '0A': '垂直方向加速度曲线(振动)，精度0.01G',
            '0B': '钢轨方向加速度曲线(振动)，精度0.01G',
            '0C': '密贴方向加速度曲线(振动)，精度0.01G',
            '0D': '表示电流: 交控道岔采集x1曲线',
            '0E': '继电器1DQJ励磁电流: 交控道岔采集1dqj曲线',
            '13': 'KZKF电流: 交控道岔采集24v曲线',
            '14': '继电器DBQ励磁电流: 交控道岔采集dbq曲线',
            '15': 'DB电压曲线，精度0.1W',
            '16': 'FB电压曲线，精度0.1W',
            '17': 'A相有功功率曲线，精度0.1W',
            '18': 'B相有功功率曲线，精度0.1W',
            '19': 'C相有功功率曲线，精度0.1W',
            '20': '表示电流曲线: 交控直流道岔采集表示电流曲线',
            '21': 'KZKF电流: 交控直流道岔采集KZKF曲线',
            '22': '继电器1DQJ励磁电流: 交控直流道岔采集1DQJ曲线',
            '23': '转换电流: 交控直流道岔采集转换电流曲线',
            '24': '交控直流道岔采集转换电流二曲线（六线制）',
            '25': '交控定位操作继电器数据',

            '123': '三相电流'
        }

        direction_value = {
            '00': '定到反',
            '01': '反到定',
            '02': '定到定',
            '03': '反到反',
            '04': '定位到故障位',
            '05': '反位到故障位',
            '06': '故障到定位',
            '07': '故障到反位',
            '08': '故障到故障位',
            'FF': '无效'
        }

        device_type = {
            '01': 'SJ',
            '02': 'DCJ',
            '03': 'FCJ',
            '04': '1DQJ',
            '05': '1DQJF',
            '06': '2DQJ',
            '07': 'TJ ',
            '08': 'DBQ',
            '09': 'BHJ',
            '0A': 'DBJ',
            '0B': 'FBJ',
            '0C': 'BB ',
            '0D': 'YCJ',
        }

        basic_data = dict()
        basic_data['frame_type_value'] = frame_type_value
        basic_data['code_type_value'] = code_type_value
        basic_data['curve_type_value'] = curve_type_value
        basic_data['direction_value'] = direction_value
        basic_data['device_type'] = device_type

        return basic_data

    def get_axle_base_data(self):

        kad_code_type = {
            '0F': '心跳帧',

            'A0': '多状态量',
            '57': '曲线数据',

            '01': '轨道电压',
            '02': '轨道相位角',
            '03': '工频干扰电压',
            '04': '轨道电流',
            '05': '工频干扰电流',
            '06': '480轨道交流电压 ',
            '07': '480、驼峰轨道电路直流电压 ',
            '08': '480轨道交流电流 ',
            '09': '480、驼峰轨道电路直流电流 ',
            '10': '电码化电压',
            '11': '电码化电流',
            '12': '电码化载频频率',
            '13': '电码化低频频率',
            '21': '定位表示交流电压',
            '22': '定位表示直流电压',
            '23': '反位表示交流电压',
            '24': '反位表示直流电压',
            '25': '道岔表示交流电流',
            '26': '道岔表示直流电流',
            '30': '信号机电压',
            '31': '信号机电流',
            '40': '防灾异物电压',
            '41': '防灾异物电流',
            '42': '半自动闭塞电压',
            '43': '半自动闭塞电流',
            '44': '站场间联系电路电压',
            '45': '站场间联系电路电流',
            '46': '自闭方向电路电压',
            '47': '自闭方向电路电流',
            '48': 'GJZ220/GJF220电压 ',
            '49': 'GJZ220/GJF220电流 ',
            '4A': '灯丝报警电压',
            '4B': '灯丝报警电流',
            '4C': '缺口报警电压',
            '4D': '缺口报警电流',
            '4E': '电话联系直流电压',
            '4F': '电话联系交流电压',
            '50': '电话联系直流电流',
            '51': '电话联系交流电流',
            '52': '雷击电流',
            '60': '屏蔽门GMJ电压 ',
            '61': '屏蔽门KMJ电压 ',
            '62': '屏蔽门PDKJ电压',
            '63': '屏蔽门PDQCJ电压 ',
            '64': '屏蔽门关门后端电压',
            '65': '屏蔽门开门后端电压',
            '66': '锁紧电压采集',
            '67': '切除电压采集',
            '6A': '计轴磁头电压',
            '6B': '计轴机柜工作电压',
            '6D': '定位表示12线交流电压',
            '6E': '定位表示12线直流电压',
            '6F': '反位表示13线交流电压',
            '70': '反位表示13线直流电压',
        }

        kad_curve_index = {
            0: '总功率曲线',
            1: 'A相电流曲线',
            2: 'B相电流曲线',
            3: 'C相电流曲线',
            4: 'AB相电压曲线',
            5: 'AC相电压曲线',
            6: '道岔电流曲线',
            7: '表9　实时AB、AC动作电压及功率曲线',
            8: 'E机电流曲线',
            9: 'J机电流曲线',
            10: '道岔电流曲线',
            11: '高压不对称曲线',
            12: '磁头电压曲线',
        }

        basic_data = {}
        basic_data['kad_code_type'] = kad_code_type
        basic_data['kad_curve_index'] = kad_curve_index

        return basic_data

    def get_signal_base_data(self):
        frame_type_value = {
            'C5': '配置',
            'CA': '升级帧',
            '0F': '心跳帧',
            '3F': '数据帧',
            '5F': '应答帧',
            'FF': '无效',
            'CB': '升级数据包回应'
        }

        code_type_value = {

            '0F': '心跳帧',
            'FF': '心跳帧',

            '51': '模块发送开关量数据',
            '53': '模块发送表示电压数据',
            '54': '外电网电压电流数据包',
            '55': '外电网断电数据包',
            '56': '外电网瞬间断电曲线数据包',
            '57': '站台门电压数据包',
            '25': '模块发送重启指令',

            '61': '上位机采集开关量数据',
            '63': '上位机采集表示电压数据',
        }

        basic_data = dict()
        basic_data['frame_type_value'] = frame_type_value
        basic_data['code_type_value'] = code_type_value


        return basic_data


    def get_module_device_id(self, server_ip, data_type=1):
        sql = "SELECT * FROM dic_msgindex_zzjno_mapping"
        sql_data = self.get_mysql_data(server_ip, sql, database='press_sms_cphm_test', port=3306, isall=all)

        module_device_id = {}  # {模块编号:[转辙机编号1、编号2...]}
        module_device_id_list = []  # [[模块编号,转辙机编号]...]
        for data in sql_data:
            msg_index = data[1].split('_')
            module_id = int(msg_index[0])
            device_id = int(msg_index[1])

            if module_id not in module_device_id.keys():
                module_device_id[module_id] = []
            module_device_id[module_id].append(device_id)

            module_device_id_list.append([module_id, device_id])

        if data_type == 1:
            print(module_device_id)
            return module_device_id
        else:
            print(module_device_id_list)
            return module_device_id_list

    def get_connect_ip_module(self, server_ip, database, port):

        ip_module = {}
        get_ip_module_sql = 'SELECT ip, module_id FROM dic_client_address'
        sql_data = self.get_mysql_data(server_ip, get_ip_module_sql, database=database, port=port, isall=all)

        for data in sql_data:
            ip, module_ip = data
            module_ip_hex = self.int_to_hex(module_ip, 4)

            ip_module[ip] = module_ip_hex

        return ip_module

    def get_line_label(self, server_ip, database, port):

        get_ip_module_sql = "SELECT param_value FROM dic_cphm_system_config WHERE param_name='line_label'"
        sql_data = self.get_mysql_data(server_ip, get_ip_module_sql, database=database, port=port, isall=False)

        line_label = sql_data[0].lower()

        print('当前读取配置的线路为: ', line_label)

        return line_label

    def get_ini_ip_module(self, line_label):
        # setting_data = self.get_ini('./setting.ini', 'sql_setting', value_type=1)
        # server_ip = setting_data['server_ip']
        # database = setting_data['database']
        # port = int(setting_data['port'])
        # ip_module = get_connect_ip_module(server_ip=server_ip, database=database, port=port)

        # setting_data = self.get_ini('./setting.ini', 'use_database', value_type=1)
        # server_ip = setting_data['server_ip']
        # database = setting_data['database']
        # port = int(setting_data['port'])
        # line_label = get_line_label(server_ip, database, port)

        line_sql_setting = '{}_sql_setting'.format(line_label)
        ip_module = self.get_ini('./setting.ini', line_sql_setting, value_type=1)

        if not len(ip_module):
            print('线路 {} IP和模块的对应关系为空,请检查配置文件(./setting.ini)是否存在数据:{}'.format(line_label, line_sql_setting))
            sys.exit(0)

        for key, value in ip_module.items():
            value_int = int(value)
            value_hex = self.int_to_hex(value_int, 4)
            ip_module[key] = value_hex

        print('{} IP和模块的对应关系为:\n{}'.format(line_label, ip_module))

        return ip_module

    def get_txt_code(self, dir_path, file_name, module_no='', hex_stamp='', zzj_id='', hz='', is_time=False, return_type=1):
        """
        读取道岔模拟量分包报文
        :param dir_path:
        :param file_name:
        :param module_no:
        :param hex_stamp:
        :param zzj_id:
        :return:
        """

        time_change = {}  # 时间戳映射关系 {旧时间戳: 新时间戳}
        interim_value = [0]  # 过渡数值，新时间戳为 当前时间-1000+过渡值，过渡值+2
        now_stamp_int = int(self.get_nowtime(isstamp=True))
        hex_stamp = hex_stamp.replace(' ', '')

        code_datas = self.get_text_data(dir_path, file_name, return_type=1)
        if not len(code_datas):
            print('请检查，没有找到对应的文件数据：{}/{}'.format(dir_path, file_name))
            sys.exit(0)

        # {模块编号:{曲线类型:[data1,data2...]}} 如：{'0001':{'57':{'60AB7197':[data1,data2..]...}, '61':[], '62':[]}}
        module_all_data = {}
        text_all_data = []
        for code_data in code_datas:
            curve_type = code_data[34:36]
            code_time = self.get_switch_code_time(code_data)

            module_datas = []
            if module_no:
                for no in module_no:
                    module_no_hex = self.int_to_hex(no, 4).replace(' ', '')
                    code_data = code_data[0:28] + module_no_hex + code_data[32:]
                    module_datas.append(code_data)
            else:
                module_datas.append(code_data)

            for data in module_datas:
                module_no_hex = code_data[28:32]

                # print('module_no_hex', module_no_hex)
                # if module_no_hex.upper() =='001B':
                #     print('23243535')

                if module_no_hex not in module_all_data.keys():
                    module_all_data[module_no_hex] = {}

                module_data = module_all_data[module_no_hex]
                if curve_type not in module_data.keys():
                    if curve_type in '57':
                        module_data[curve_type] = {}
                    else:
                        module_data[curve_type] = []

                analog_data = module_data[curve_type]
                if curve_type in '57' and code_time not in analog_data.keys():
                    analog_data[code_time] = []

                if is_time:
                    if hex_stamp:
                        change_stamp_hex = hex_stamp
                    else:
                        if code_time not in time_change:
                            change_time_int = now_stamp_int + interim_value[0]
                            change_time_hex = self.int_to_hex(change_time_int)
                            time_change[code_time] = change_time_hex
                            interim_value[0] = interim_value[0] + 1
                        change_stamp_hex = time_change[code_time]
                    data = self.modify_switch_code_time(data, change_stamp_hex)

                if hz:
                    data = data[0:56] + hz + data[60:]

                if zzj_id:
                    for id in zzj_id:
                        id_hex = self.int_to_hex(id, 4)
                        data = data[0:62] + id_hex + data[66:]
                        text_all_data.append(data)

                        if curve_type in ('57'):
                            analog_data[code_time].append(data)
                        else:
                            module_data[curve_type].append(data)
                else:
                    text_all_data.append(data)

                    if curve_type in ('57'):
                        analog_data[code_time].append(data)
                    else:
                        module_data[curve_type].append(data)

        if return_type == 1:
            return text_all_data
        else:
            return module_all_data

    def write_log_txt(self, ori_dir_path, data_type, total_data, file_name=None):

        # data_type: 1:全部数据 2：文件数据 3：ip曲线数据 4：曲线数据 5：开关量数据 6：表示电压数据 7：表示电流数据 10:道岔转动前后的数据
        file_type_name = {
            1: 'total_data_all.txt',
            2: 'total_data_file_{}.txt',
            3: 'total_data_analog_{}.txt',
            4: 'total_data_analog.txt',
            5: 'total_data_switch.txt',
            6: 'total_data_voltage.txt',
            7: 'total_data_current.txt',
            8: 'total_data_electricity.txt',
            9: 'total_data_analog_and_switch.txt',
            10: 'total_data_all_move.txt',
        }
        file_name = file_name if file_name else file_type_name[data_type]

        if data_type in (2, 3):

            for key, value_data in total_data.items():
                dir_file_name = '{}\\{}'.format(ori_dir_path, file_name.format(key))
                print('文件数据正在写入文件...:', dir_file_name)
                with open(dir_file_name, 'w') as f:
                    for data in value_data:
                        data = self.data_format(data)
                        f.write(data + '\n')
                    print('写入完成: {}'.format(file_name.format(key)))
        else:

            dir_file_name = '{}\\{}'.format(ori_dir_path, file_name)
            print('文件数据正在写入文件...:', dir_file_name)
            with open(dir_file_name, 'w') as f:
                for data in total_data:
                    data = self.data_format(data)
                    f.write(data + '\n')
                print('写入完成: {}'.format(file_name))

    def get_log_data(self, ori_dir_path, ori_file_name, is_modify_module=False, line_label=False):

        total_data_ip = {}  # ip全部数据{ip:[]}
        total_data_file = {}  # log全部数据{file:[]}
        total_data_all = []  # 全部数据
        total_data_analog = []  # 模拟量数据
        total_data_switch = []  # 开关量数据
        total_data_voltage = []  # 表示电压数据
        total_data_current = []  # 表示电流数据
        total_data_electricity = []  # 电参数数据
        total_data_analog_and_switch = []  # 模拟量和开关量数据

        # is_write_ip = True
        # is_write_file = True
        is_write_all = True
        # is_write_analog = True
        # is_write_switch = True
        # is_write_voltage = True
        # is_write_current = True
        # is_write_electricity = True
        # is_write_analog_switch = True

        is_write_ip = False
        is_write_file = False
        # is_write_all = False
        is_write_analog = False
        is_write_switch = False
        is_write_voltage = False
        is_write_current = False
        is_write_electricity = False
        is_write_analog_switch = False

        print(r'开始处理目录下原始Log文件: {}\{}'.format(ori_dir_path, ori_file_name))

        if is_modify_module:
            ip_module = self.get_ini_ip_module(line_label)
        else:
            ip_module = {}

        deal_files = []  # 目标文件名称
        dir_files = os.listdir(ori_dir_path)
        for file in dir_files:
            if ori_file_name in file and '.zip' not in file and '.rar' not in file:
                deal_files.append(file)

        if not len(deal_files):
            print(r'找不到文件名包含 {} 的文件'.format(ori_file_name))
            sys.exit(0)

        deal_files.sort()
        for file in deal_files:
            print(r'正在读取的文件：{}\{}'.format(ori_dir_path, file))
            file_name = file.split('.')[0]
            file_path = ori_dir_path + '\\' + file
            file_data = open(file_path, 'r', encoding='utf-8')
            # file_data = open(file_path, 'r', encoding='gbk')
            # file_data = open(file_path, 'r', encoding='gb18030')

            if file_name not in total_data_file:
                total_data_file[file_name] = []

            start_sign = {}  # {module_zzj:[]}
            for data in file_data:
                data = data.replace(' ', '')
                is_ip = False
                ip = ''
                if '报文' in data:
                    is_ip = True
                    if '接收到ip' in data:
                        ip_start_index = data.index('接收到ip')
                        ip_end_index = data.index('端口')
                        ip = data[ip_start_index + 6:ip_end_index]
                    else:
                        ip_start_index = data.index('ip：')
                        ip_end_index = data.index('的报文')
                        ip = data[ip_start_index + 3:ip_end_index]

                    coed_start_index = data.index('文')
                    code_data = data[coed_start_index + 1:]
                else:
                    code_data = data

                module_index = code_data[20:24]
                code_type = code_data[32:34]
                message_type = code_data[34:36]
                code_time = code_data[48:56]
                zzj_index = code_data[64:66]
                pack_sign = code_data[74:76]

                # 获取3F、5F类型的模拟量曲线数据报文
                # target_curve_type = ['01', '02', '03', '0E', '13', '14', '21', '22', '23', '24']
                if code_type not in ('3F', '5F'):
                    continue

                if is_modify_module and is_ip:
                    if ip not in ip_module.keys():
                        print('请检查IP模块映射关系,IP模块映射关系中不存在当前IP:{}\n{}'.format(ip, ip_module))
                        sys.exit(0)
                    module_no_hex = ip_module[ip]
                    code_data = code_data[0:28] + module_no_hex + code_data[32:]

                # 获取曲线数据
                if message_type in ('50', '57'):
                    # 过滤不是曲线标识不是55开始的数据
                    key = '{}_{}'.format(module_index, zzj_index)
                    if key not in start_sign.keys():
                        start_sign[key] = []

                    move_time = start_sign[key]
                    if pack_sign == '55':
                        move_time.append(code_time)
                    else:
                        if code_time not in move_time:
                            continue

                    # file_ip = '{}_{}'.format(file_name, ip)
                    if is_ip:
                        file_ip = '{}'.format(ip)
                        if file_ip not in total_data_ip:
                            total_data_ip[file_ip] = []

                        total_data_ip[file_ip].append(code_data)
                    total_data_analog.append(code_data)

                    total_data_analog_and_switch.append(code_data)

                # 获取开关量数据
                if message_type in ('51', '61'):
                    total_data_switch.append(code_data)
                    total_data_analog_and_switch.append(code_data)

                # 获取表示电压数据
                if message_type in ('53', '63'):
                    total_data_voltage.append(code_data)

                # 获取表示电流数据
                if message_type in '65':
                    total_data_current.append(code_data)

                # 获取电参数数据
                if message_type in '64':
                    total_data_electricity.append(code_data)

                total_data_file[file_name].append(code_data)
                total_data_all.append(code_data)

            print('{} 读取完成'.format(file))

        if is_modify_module and not len(total_data_ip):
            print('源log文件为空 或 文件中IP找不到对应的模块映射，请检查！')
            sys.exit(0)

        start_time = time.time()

        print('Log日志读取完毕，开始写入文件...')
        threads = []

        if is_write_all:
            t = multiprocessing.Process(target=self.write_log_txt, args=(ori_dir_path, 1, total_data_all))
            threads.append(t)

        if is_write_file and len(deal_files) != 1:
            t = multiprocessing.Process(target=self.write_log_txt, args=(ori_dir_path, 2, total_data_file))
            threads.append(t)

        if is_write_ip:
            t = multiprocessing.Process(target=self.write_log_txt, args=(ori_dir_path, 3, total_data_ip))
            threads.append(t)

        if is_write_analog:
            t = multiprocessing.Process(target=self.write_log_txt, args=(ori_dir_path, 4, total_data_analog))
            threads.append(t)

        if is_write_switch:
            t = multiprocessing.Process(target=self.write_log_txt, args=(ori_dir_path, 5, total_data_switch))
            threads.append(t)

        if is_write_voltage:
            t = multiprocessing.Process(target=self.write_log_txt, args=(ori_dir_path, 6, total_data_voltage))
            threads.append(t)

        if is_write_current:
            t = multiprocessing.Process(target=self.write_log_txt, args=(ori_dir_path, 7, total_data_current))
            threads.append(t)

        if is_write_electricity:
            t = multiprocessing.Process(target=self.write_log_txt, args=(ori_dir_path, 8, total_data_electricity))
            threads.append(t)

        if is_write_analog_switch:
            t = multiprocessing.Process(target=self.write_log_txt, args=(ori_dir_path, 9, total_data_analog_and_switch))
            threads.append(t)

        for t in threads:
            t.daemon = True
            t.start()

        for t in threads:
            t.join()

        print('所有文件写入完成,存放目录:', ori_dir_path)

        end_time = time.time()
        print('写入文件耗时: {} 秒({:.2f} 分)'.format(int(end_time - start_time), int(end_time - start_time) / 60))

    def get_log_data2(self, ori_dir_path, ori_file_name, is_modify_module=False, line_label=False):

        total_data_ip = {}  # ip全部数据{ip:[]}
        total_data_file = {}  # log全部数据{file:[]}
        total_data_all = []  # 全部数据
        total_data_analog = []  # 模拟量数据
        total_data_switch = []  # 开关量数据
        total_data_voltage = []  # 表示电压数据
        total_data_current = []  # 表示电流数据
        total_data_electricity = []  # 电参数数据
        total_data_analog_and_switch = []  # 模拟量和开关量数据

        # is_write_ip = True
        # is_write_file = True
        is_write_all = True
        # is_write_analog = True
        # is_write_switch = True
        # is_write_voltage = True
        # is_write_current = True
        # is_write_electricity = True
        # is_write_analog_switch = True

        is_write_ip = False
        is_write_file = False
        # is_write_all = False
        is_write_analog = False
        is_write_switch = False
        is_write_voltage = False
        is_write_current = False
        is_write_electricity = False
        is_write_analog_switch = False

        start_time = time.time()
        print(r'开始处理目录下原始Log文件: {}\{}'.format(ori_dir_path, ori_file_name))

        if is_modify_module:
            ip_module = self.get_ini_ip_module(line_label)
        else:
            ip_module = {}

        deal_files = []  # 目标文件名称
        dir_files = os.listdir(ori_dir_path)
        for file in dir_files:
            if ori_file_name in file:
                deal_files.append(file)

        if not len(deal_files):
            print(r'找不到文件名包含 {} 的文件'.format(ori_file_name))
            sys.exit(0)

        deal_files.sort()

        dir_file_name = '{}\\{}'.format(ori_dir_path, 'total_data_all.txt')
        with open(dir_file_name, 'r', encoding='utf-8') as f:
            for file in deal_files:
                print(r'正在读取的文件：{}\{}'.format(ori_dir_path, file))
                file_name = file.split('.')[0]
                file_path = ori_dir_path + '\\' + file
                file_data = open(file_path, 'r', encoding='utf-8')
                # file_data = open(file_path, 'r', encoding='gbk')

                if file_name not in total_data_file:
                    total_data_file[file_name] = []

                start_sign = {}  # {module_zzj:[]}
                for data in file_data:
                    data = data.replace(' ', '')
                    is_ip = False
                    ip = ''
                    if '报文' in data:
                        is_ip = True
                        if '接收到ip' in data:
                            ip_start_index = data.index('接收到ip')
                            ip_end_index = data.index('端口')
                            ip = data[ip_start_index + 6:ip_end_index]
                        else:
                            ip_start_index = data.index('ip：')
                            ip_end_index = data.index('的报文')
                            ip = data[ip_start_index + 3:ip_end_index]

                        coed_start_index = data.index('文')
                        code_data = data[coed_start_index + 1:]
                    else:
                        code_data = data

                    module_index = code_data[20:24]
                    code_type = code_data[32:34]
                    message_type = code_data[34:36]
                    code_time = code_data[48:56]
                    zzj_index = code_data[64:66]
                    pack_sign = code_data[74:76]

                    # 获取3F、5F类型的模拟量曲线数据报文
                    # target_curve_type = ['01', '02', '03', '0E', '13', '14', '21', '22', '23', '24']
                    if code_type not in ('3F', '5F'):
                        continue

                    if is_modify_module and is_ip:
                        if ip not in ip_module.keys():
                            print('请检查IP模块映射关系,IP模块映射关系中不存在当前IP:{}\n{}'.format(ip, ip_module))
                            sys.exit(0)
                        module_no_hex = ip_module[ip]
                        code_data = code_data[0:28] + module_no_hex + code_data[32:]

                    # 获取曲线数据
                    if message_type in ('50', '57'):
                        # 过滤不是曲线标识不是55开始的数据
                        key = '{}_{}'.format(module_index, zzj_index)
                        if key not in start_sign.keys():
                            start_sign[key] = []

                        move_time = start_sign[key]
                        if pack_sign == '55':
                            move_time.append(code_time)
                        else:
                            if code_time not in move_time:
                                continue

                        # file_ip = '{}_{}'.format(file_name, ip)
                        if is_ip:
                            file_ip = '{}'.format(ip)
                            if file_ip not in total_data_ip:
                                total_data_ip[file_ip] = []

                            total_data_ip[file_ip].append(code_data)
                        total_data_analog.append(code_data)

                        total_data_analog_and_switch.append(code_data)

                    # 获取开关量数据
                    if message_type in ('51', '61'):
                        total_data_switch.append(code_data)
                        total_data_analog_and_switch.append(code_data)

                    # 获取表示电压数据
                    if message_type in ('53', '63'):
                        total_data_voltage.append(code_data)

                    # 获取表示电流数据
                    if message_type in '65':
                        total_data_current.append(code_data)

                    # 获取电参数数据
                    if message_type in '64':
                        total_data_electricity.append(code_data)

                    total_data_file[file_name].append(code_data)
                    total_data_all.append(code_data)

                    f.write(str(code_data))

                print('{} 读取完成'.format(file))

        if is_modify_module and not len(total_data_ip):
            print('源log文件为空 或 文件中IP找不到对应的模块映射，请检查！')
            sys.exit(0)

        end_time = time.time()
        print('写入文件耗时: {} 秒({:.2f} 分)'.format(int(end_time - start_time), int(end_time - start_time) / 60))

    def get_mac_address(self):

        mac_address = []

        addrs = psutil.net_if_addrs()
        for net_name, net_detail in addrs.items():

            if '以太网' in net_name:
                for item in net_detail:
                    address = item[1]
                    if '-' in address:
                        str_address = address.replace('-', ':')
                        mac_address.append(str_address)

        if not len(mac_address):
            print('mac地址获取失败，请检查！')
            sys.exit(0)

        print('本机MAC地址为:', mac_address[0])
        return mac_address[0]

    def get_switch_code_time(self, code_data):
        code_data = code_data.replace(' ', '').replace('\n', '')
        message_type = code_data[34:36]
        send_code_time = code_data[36:44]

        # 模拟量、表示电流
        if message_type in ('50', '57', '65'):
            code_time = code_data[48:56]

        # 开关量
        elif message_type in ('51', '61'):
            code_time = code_data[74:82]

        # 继电器状态
        elif message_type in ('52', '62'):
            code_time = code_data[84:92]

        # 表示电压
        elif message_type in ('53', '63'):
            code_time = code_data[86:94]

        # 电参数 64
        else:
            code_time = code_data[36:44]

        if code_time == '00000000':
            code_time = send_code_time

        return code_time

    def modify_switch_code_time(self, code_data, change_stamp_hex):

        code_data = code_data.replace(' ', '').replace('\n', '')
        message_type = code_data[34:36]

        # 模拟量、表示电流
        if message_type in ('50', '57', '65'):
            code_data = code_data[0:36] + change_stamp_hex + code_data[44:]
            code_data = code_data[0:48] + change_stamp_hex + code_data[56:]

        # 开关量
        elif message_type in ('51', '61'):
            code_time = self.get_switch_code_time(code_data)
            code_data = code_data.replace(code_time, change_stamp_hex)

        # 继电器状态
        elif message_type in ('52', '62'):
            code_time = self.get_switch_code_time(code_data)
            code_data = code_data.replace(code_time, change_stamp_hex)

        # 表示电压
        elif message_type in ('53', '63'):
            code_data = code_data[0:36] + change_stamp_hex + code_data[44:]
            code_data = code_data[0:86] + change_stamp_hex + code_data[94:]

        # 电参数 64
        else:
            code_data = code_data[0:36] + change_stamp_hex + code_data[44:]

        return code_data


if __name__ == '__main__':
    # get_basic_data()

    func = CphmFunc()
    func.get_module_device_id('192.168.1.228')
    dir_path = './报文制造/text'
    file_name = 'test_file.txt'
    # get_txt_code(dir_path, file_name, module_no_hex='0001', hex_stamp='5F 19 39 Cc', device_id=[1], return_type='')
    # get_txt_code(dir_path, file_name, module_no=[1], hex_stamp='5F 19 39 Cc', zzj_id=[3, 2])

    # get_connect_ip_module(server_ip='192.168.1.235', database='sms_connect_cd1', port=3316)

    # get_line_label(server_ip='192.168.1.228', database='test1_sms_cphm', port=3306)

    code_data = '''
71 6B 6E 65 74 00 00 00 55 00 00 01 FF FF 00 01 5F 64 60 A2 93 01 8A B4 00 01 00 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 13 88 13 88 13 88 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 5A 00 00 00 00 00 00 37 FD 42 9F FA FB FC FD
    '''
    # get_code_time(code_data.replace(' ','').replace('\n',''))
