import os
import random

import configobj

from publicfunc import PublicFunc

func = PublicFunc()


def get_ini_setting_info():

    path_file = r'A_test_station_setting.ini'

    config_dict = configobj.ConfigObj(path_file, encoding='UTF-8')

    ip_setting_dict = config_dict['ip_info']

    sourse_ip = ip_setting_dict['sourse_ip']
    dest_ip = ip_setting_dict['dest_ip']

    station_setting_dict = config_dict['station_setting']

    path = station_setting_dict['path']
    station = station_setting_dict['station']

    setting_info = {
        'sourse_ip': sourse_ip,
        'dest_ip': dest_ip,
        'path':    path,
        'station': station,
    }

    return setting_info


def analog_values(device_data, data_type=1):

    if data_type == 1:
        num = device_data
    else:
        num = len(device_data)

    values_hex = ''
    for i in range(num):

        index_hex = func.int_to_hex(i, 4)
        index_hex = func.str_reverse(index_hex)

        float_data = random.uniform(0,100)
        float_data = round(float_data,2)
        hex_data  = func.float_to_hex(float_data)
        hex_data = func.str_reverse(hex_data)

        info = ''
        if data_type == 2:
            device_info = device_data[i]
            info = f'#{device_info} - 值:{float_data}#'

        else:
            print(f'第{i+1}个值: {float_data}')

        values_hex += f'{index_hex} {hex_data} [64 25 A0 5D R] {info}\n        '


    return values_hex


def make_analog_code(device_type, device_data):
    '''
    网达 模拟量文件
    device_data: int时直接表示长度 list时表示详细设备
    '''

    is_data_int = isinstance(device_data, int)
    if is_data_int:
        device_num_len = device_data
        data_type = 1
    else:
        device_num_len = len(device_data)
        data_type = 2

    analog_type_hex = f'{device_type}'

    device_len_hex = func.int_to_hex(device_num_len, 4)
    device_len_reverse = func.str_reverse(device_len_hex)

    device_code = analog_values(device_data, data_type)

    send_data = f'''
        EF EF EF EF #帧头#
        10 #初版为0x10,后面做修正分别为0x20...依次递增#
        8F #数据帧标志8fH, 心跳帧标志0FH#
        [E3 93 CC 64 R]#时间戳#
        (13 00 00 00 R) #数据长度#
        <
        4A 4B 31 #目的电报码#
        4C 48 5A #源电报码#
        4C 48 5A #自然站电报码#
                
        10 #数据类型码 模拟量数据类型：0x10#
        01 #数据子类型码 0x01#

        {analog_type_hex} #模拟量类型#
        01 00 #采集频率#
        {device_len_reverse} #模拟量个数 {device_num_len}个 #
        {device_code}
    
        >
        3E 0A #CRC16校验#
        FE FE FE FE #帧尾部#
    '''

    print(send_data)
    send_data = func.deal_data(send_data)
    print(send_data)


    return send_data


def get_mms_alarm_type_dict():

    alarm_type_dict = {
        '03': '道岔挤岔',
        '07': '外电网双路断电报警',
        '08': '外电网三相错序',
        '09': '外电网输入电源瞬间断电',
        '12': '计算机联锁系统报警',
        '13': '电气特性超限',
        '29': '道岔无表示',
        'C0': '电气特性断电',
        'C7': '转辙机动作功率（电流）异常',
        'DE': '外电网输入单路断相/断电',
        'E1': '道岔直流表示电压低于16V报警',
        'E3': '道岔动作电流/功率曲线超限报警',
        '0A': '灯丝报警器报警',
        '0B': '熔丝断丝',
        'E2': '慧景视频缺口报警',
        '14': '监测与其它系统(采集机)通讯中断',
        '16':'道岔运用次数',
        '64':'智能分析故障诊断',
        '62':'智能分析预警',
        '25': '安全监督报警',

    }

    return alarm_type_dict


def get_mms_file_data(path, station):

    file_path_dict = {}
    path_dir_list = os.listdir(path)
    true_station = func.get_true_key_name(path_dir_list, station)

    new_path = f'{path}/{true_station}'

    path_file_list = os.listdir(new_path)

    part_file_name_list = [['开关量','switch'], ['模拟量','analog'], ['道岔曲线','switchgap'], ['站码信息','station_info'], ['报警设备','alarm_device'], ['采集设备','collect_device']]

    for file_info, file_name in part_file_name_list:
        true_file_info = func.get_true_key_name(path_file_list, file_info)
        file_path_name = f'{new_path}/{true_file_info}'

        file_path_dict[file_name] = file_path_name


    print('file_path_dict', file_path_dict)

    return file_path_dict


def get_line_value_list(line_data):

    line_data = line_data.replace(' ','').replace('\n','')
    line_data_split = line_data.split('=')
    line_value_str = line_data_split[1]
    line_value_list = line_value_str.split(',')

    return line_value_list


def get_mms_ini_data(path, station):
    file_path_dict = get_mms_file_data(path, station)

    analog_file         = file_path_dict['analog']          # 模拟量文件
    switchgap_curve_file      = file_path_dict['switchgap']       # 道岔曲线文件
    alarm_device_file   = file_path_dict['alarm_device']    # 报警设备编号文件
    collect_device_file = file_path_dict['collect_device']  # 采集设备状态文件


    # 报警设备编号
    alarm_device_list = []
    f_encoded = func.get_file_charset(alarm_device_file)
    file_data = open(alarm_device_file, 'r', encoding=f_encoded)
    for line_data in file_data:

        if '=' not in line_data or '总数' in line_data: continue

        line_value_list = get_line_value_list(line_data)
        index = int(line_value_list[0])
        device_name = line_value_list[1]

        alarm_device_list.append([index, device_name])

    # print('alarm_device_list', alarm_device_list)



    # 模拟量文件
    analog_data_dict = {}
    f_encoded = func.get_file_charset(analog_file)
    file_data = open(analog_file, 'r', encoding=f_encoded)

    is_get_item_name = False
    is_get_data = False
    item_name = ''

    for line_data in file_data:
        line_data = line_data.replace(' ','').replace('\n','')

        if line_data == '': continue
        # print('line_data', line_data)

        if '[子项' in line_data:
            is_get_item_name = True
            if is_get_data: is_get_data = False

        if is_get_item_name and '名称=' in line_data:
            item_name = line_data.split('=')[1]
            is_get_item_name = False

            analog_data_dict[item_name] = []
            # print('item_name', item_name)

        if '序号=' in line_data:
            is_get_data = True
            continue

        if is_get_data:
            line_value_list = get_line_value_list(line_data)
            device_name = line_value_list[0]
            index = int(line_value_list[2])

            # print('index, device_name', index, device_name)

            analog_data_dict[item_name].append([index, device_name])

    # print('analog_data_dict', analog_data_dict)


    # 道岔曲线
    curve_data_dict = {}
    f_encoded = func.get_file_charset(switchgap_curve_file)
    file_data = open(switchgap_curve_file, 'r', encoding=f_encoded)

    is_get_item_name = False
    is_get_data = False
    item_name = ''

    for line_data in file_data:
        line_data = line_data.replace(' ','').replace('\n','')

        if line_data == '': continue
        # print('line_data', line_data)

        if '[子项' in line_data:
            is_get_item_name = True
            if is_get_data: is_get_data = False

        if is_get_item_name and '名称=' in line_data:
            item_name = line_data.split('=')[1]
            is_get_item_name = False

            curve_data_dict[item_name] = []
            # print('item_name', item_name)

        if '序号=' in line_data or '开始AD号=' in line_data:
            is_get_data = True
            continue

        if '=' not in line_data or ';;' in line_data:
            continue

        if is_get_data:
            line_value_list = get_line_value_list(line_data)
            device_name = line_value_list[0]
            index = int(line_value_list[2])

            if 'DUMMY' == device_name:
                continue

            # print('index, device_name', index, device_name)

            curve_data_dict[item_name].append([index, device_name])

    # print('analog_data_dict', analog_data_dict)


    ini_data_dict = {
        'alarm_device_list': alarm_device_list,
        'analog_data_dict': analog_data_dict,
        'curve_data_dict': curve_data_dict,
    }

    return ini_data_dict

if __name__ == '__main__':
    # get_ini_setting_info()

    path = './file/zy'
    station = '福田'
    get_mms_ini_data(path, station)
