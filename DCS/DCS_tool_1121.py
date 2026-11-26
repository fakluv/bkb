import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, Toplevel, BOTH, HORIZONTAL, VERTICAL, LEFT, RIGHT, X, Y, filedialog
import struct
import time
import random
import socket
import queue
import threading
import traceback
import csv
import json
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    import winreg
except ImportError:
    winreg = None

# ---------- openpyxl（读 Excel 必需） ----------
from openpyxl import load_workbook, Workbook

# ---------- xlrd（读取 .xls 旧格式点表，可选） ----------
try:
    import xlrd
    XLRD_OK = True
    XLRD_ERROR = ""
except Exception as _e:
    XLRD_OK = False
    XLRD_ERROR = str(_e)

# ---------- 拓扑图校验依赖（可选导入） ----------
try:
    import requests
    import pymysql
    TOPOLOGY_DEPS_OK = True
    TOPOLOGY_DEPS_ERROR = ""
except Exception as _e:
    TOPOLOGY_DEPS_OK = False
    TOPOLOGY_DEPS_ERROR = str(_e)

try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except Exception:
    pass


# ============================================================
# V1.0 交换机配置文件 Sheet 名称匹配
# ============================================================
CONFIG_SHEET_NAMES = ["NEConfigData", "NE", "设备配置", "交换机列表", "Sheet1"]
MAPPING_SHEET_NAMES = ["Sheet2", "Sheet1", "端口映射", "PortMapping", "映射表"]

# ---------- Disney（C9000-W-000-TCT-160-000011）相关 ----------
DISNEY_SWITCH_SHEET_NAMES = ["NEConfigData", "NE", "设备配置", "交换机列表"]
DISNEY_AP_SHEET_MAIN = ["正线", "Mainline", "MAIN"]
DISNEY_AP_SHEET_TEST = ["试车线", "SHD", "Test"]
DISNEY_WAC_SHEET_MAIN = ["正线", "Mainline", "MAIN"]
DISNEY_WAC_SHEET_TEST = ["试车线", "SHD", "Test"]

# Disney 中设备状态的 2bit 编码
DISNEY_AP_STATUS = {0: 0b00, 1: 0b01, 2: 0b11}      # 正常 / 故障 / 关闭
DISNEY_AP_STATUS_TEXT = {0b00: "正常", 0b01: "故障", 0b11: "关闭", 0b10: "未定义"}
DISNEY_WAC_STATUS = {0: 0b00, 1: 0b01, 2: 0b11}     # 正常 / 故障 / 关闭
DISNEY_SW_STATUS = {0: 0b00, 1: 0b01, 2: 0b10, 3: 0b11}  # 正常/整机故障/高负载/端口异常
DISNEY_SW_STATUS_TEXT = {0: "正常", 1: "整机故障", 2: "高负载", 3: "端口异常"}
DISNEY_PORT_STATUS = {0: 0b00, 1: 0b01, 2: 0b10}    # 正常/故障/超标
DISNEY_PORT_STATUS_TEXT = {0: "正常", 1: "故障", 2: "超标"}

LINE_MAIN = "main"
LINE_TEST = "test"
LINE_NAME = {LINE_MAIN: "正线", LINE_TEST: "试车线"}

SW_STATUS_TEXTS = ["正常", "整机故障", "高负载", "端口异常"]
PORT_STATUS_TEXTS = ["正常", "故障", "超标"]


# ============================================================
# 通用工具函数
# ============================================================
def clean_cell(val):
    if val is None:
        return ""
    if isinstance(val, float):
        if val != val:  # NaN
            return ""
        if val == int(val):
            return str(int(val))
        return str(val)
    s = str(val).strip()
    if s.endswith('.0') and s[:-2].replace("-", "").isdigit():
        s = s[:-2]
    if s.lower() == 'nan':
        return ""
    return s


def parse_port_total(mask: str) -> int:
    if not mask:
        return 0
    if mask.isdigit():
        return int(mask)
    if mask.upper() == "NT":
        return 8
    total = 0
    for part in mask.split(','):
        part = part.strip()
        if part.isdigit():
            total += int(part)
        else:
            for ch in part:
                if ch.upper() == 'N':
                    total += 8
                elif ch.upper() == 'T':
                    total += 2
    return total


def crc32_custom(data: bytes) -> int:
    crc = 0x00000000
    for byte in data:
        crc ^= (byte << 24)
        for _ in range(8):
            if crc & 0x80000000:
                crc = (crc << 1) ^ 0x04C11DB7
            else:
                crc <<= 1
            crc &= 0xFFFFFFFF
    return crc


def clean_val(v):
    """拓扑图校验专用：清洗单元格值"""
    if v is None:
        return ""
    if isinstance(v, float):
        if v != v:
            return ""
        if v == int(v):
            return str(int(v))
        return str(v)
    s = str(v).strip()
    if s.lower() in ("nan", "none", "nat"):
        return ""
    if s.endswith(".0") and s[:-2].replace("-", "").isdigit():
        s = s[:-2]
    return s


def build_api_url(base, station_no):
    base = (base or "").strip()
    if not base:
        return ""
    if base.endswith("stationNo="):
        return f"{base}{station_no}"
    if base.endswith("stationNo"):
        return f"{base}={station_no}"
    if "getDcsSwitchLink" in base:
        sep = "&" if "?" in base else "?"
        return f"{base}{sep}stationNo={station_no}"
    base = base.rstrip("/")
    return f"{base}/bdms/isim-backend/isim/indoorDevice/getDcsSwitchLink?stationNo={station_no}"


# ============================================================
# Excel 读取辅助（基于 openpyxl，无 pandas 依赖）
# ============================================================
def _get_excel_sheet_names(file_path):
    wb = load_workbook(file_path, read_only=True, data_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def _read_excel_rows(file_path, sheet_name=None):
    """读取 Excel 工作表为二维 list（每行为 list）。sheet_name=None 时读取第一个工作表。"""
    wb = load_workbook(file_path, read_only=True, data_only=True)
    try:
        if sheet_name is None:
            ws = wb[wb.sheetnames[0]]
        else:
            if sheet_name not in wb.sheetnames:
                raise ValueError(f"工作表不存在: {sheet_name}")
            ws = wb[sheet_name]
        rows = []
        for row in ws.iter_rows(values_only=True):
            rows.append(list(row))
        return rows
    finally:
        wb.close()


def _is_xls_file(file_path):
    p = str(file_path).lower()
    return p.endswith(".xls") and not p.endswith(".xlsx")


def get_sheet_names_any(file_path):
    """兼容 .xls（xlrd）与 .xlsx/.xlsm（openpyxl）的工作表名读取。"""
    if _is_xls_file(file_path):
        if not XLRD_OK:
            raise ValueError(f"读取 .xls 文件需要 xlrd 库，请执行 pip install xlrd\n（{XLRD_ERROR}）")
        bk = xlrd.open_workbook(file_path)
        return list(bk.sheet_names())
    return _get_excel_sheet_names(file_path)


def read_rows_any(file_path, sheet_name=None):
    """兼容 .xls（xlrd）与 .xlsx/.xlsm（openpyxl）的整表读取。"""
    if not _is_xls_file(file_path):
        return _read_excel_rows(file_path, sheet_name)

    if not XLRD_OK:
        raise ValueError(f"读取 .xls 文件需要 xlrd 库，请执行 pip install xlrd\n（{XLRD_ERROR}）")
    bk = xlrd.open_workbook(file_path)
    if sheet_name is None:
        sh = bk.sheet_by_index(0)
    else:
        if sheet_name not in bk.sheet_names():
            raise ValueError(f"工作表不存在: {sheet_name}")
        sh = bk.sheet_by_name(sheet_name)
    rows = []
    for r in range(sh.nrows):
        row = []
        for c in range(sh.ncols):
            cell = sh.cell(r, c)
            val = cell.value
            if cell.ctype == xlrd.XL_CELL_EMPTY or cell.ctype == xlrd.XL_CELL_BLANK:
                val = None
            row.append(val)
        rows.append(row)
    return rows


# ============================================================
# 数据加载函数
# ============================================================
def load_switches_from_neconfig_v1(file_path, sheet_name):
    rows = read_rows_any(file_path, sheet_name)
    switches = []
    in_switch = False
    port_nbr_col = None
    for row in rows:
        a = clean_cell(row[0]) if len(row) > 0 else ""
        if a == "[Switch]":
            in_switch = True
            continue
        if not in_switch:
            continue
        if a.startswith("[") and a != "[Switch]":
            break
        if a.upper() == "NO":
            for col_idx, val in enumerate(row):
                if clean_cell(val).upper() == "PORTNBR":
                    port_nbr_col = col_idx
                    break
            break
    if port_nbr_col is None:
        sample_row = None
        for row in rows:
            a = clean_cell(row[0]) if len(row) > 0 else ""
            if a.isdigit() and int(a) >= 1000:
                sample_row = row
                break
        if sample_row is not None:
            if len(sample_row) > 10 and clean_cell(sample_row[10]) not in ["", "0"]:
                port_nbr_col = 10
            else:
                port_nbr_col = 9
        else:
            port_nbr_col = 9

    in_switch = False
    for row in rows:
        a = clean_cell(row[0]) if len(row) > 0 else ""
        b = clean_cell(row[1]) if len(row) > 1 else ""
        if a == "[Switch]":
            in_switch = True
            continue
        if not in_switch:
            continue
        if a.startswith("[") and a != "[Switch]":
            break
        if a == "":
            continue
        if a.isdigit() and ("//" in b or b.startswith("/")):
            continue
        if a.upper() in ["NO", "TYPE"]:
            continue
        if a.isdigit() and int(a) >= 1000:
            try:
                no = int(a)
                port_mask = clean_cell(row[port_nbr_col]) if len(row) > port_nbr_col else ""
                station = clean_cell(row[6]) if len(row) > 6 else ""
                hostname = clean_cell(row[2]) if len(row) > 2 else ""
                switches.append({
                    "no": no, "station": station, "hostname": hostname,
                    "port_mask": port_mask, "total_ports": parse_port_total(port_mask)
                })
            except Exception:
                continue
    return switches


def load_port_mapping_v1(file_path, sheet_name):
    rows = read_rows_any(file_path, sheet_name)
    mapping = {}
    current = None
    for row in rows:
        a = clean_cell(row[0]) if len(row) > 0 else ""
        b = clean_cell(row[1]) if len(row) > 1 else ""
        if a == "" and b == "":
            current = None
            continue
        if a.isdigit() and len(a) >= 4 and ("//" in b or b.startswith("/")):
            current = int(a)
            mapping[current] = {}
            continue
        if current is not None:
            if a.isdigit():
                if b == "" or b.isdigit() or "//" in b or b.startswith("/"):
                    continue
                mapping[current][int(a)] = b
            elif "|" in a:
                parts = a.split('|')
                if len(parts) == 2:
                    p = clean_cell(parts[0])
                    d = clean_cell(parts[1])
                    if p.isdigit():
                        mapping[current][int(p)] = d
    return mapping


def load_switches_from_neconfig_v2(file_path):
    rows = read_rows_any(file_path, "NMSConfig")
    in_section = False
    header_row = None
    for idx, row in enumerate(rows):
        first = clean_cell(row[0]) if len(row) > 0 else ""
        if first == "[SwitchAndPort]":
            in_section = True
            continue
        if not in_section:
            continue
        if first.startswith("[") and first != "[SwitchAndPort]":
            break
        if any("SwitchID" in str(c) for c in row):
            header_row = idx
            break
    if header_row is None:
        raise ValueError("未找到 'SwitchID' 表头，不是有效的 NMSConfig 格式")

    headers = [clean_cell(c) for c in rows[header_row]]
    col_map = {}
    for col_name in ['SwitchID', 'SwitchName', 'Station', 'PortID', 'PortDev']:
        if col_name in headers:
            col_map[col_name] = headers.index(col_name)
        else:
            raise ValueError(f"缺少必需列: {col_name}")

    switches_dict = {}
    for idx in range(header_row + 1, len(rows)):
        row = rows[idx]
        if col_map['SwitchID'] >= len(row):
            break
        sw_val = clean_cell(row[col_map['SwitchID']])
        if sw_val == "":
            break
        try:
            switch_id = int(sw_val)
        except ValueError:
            break
        switch_name = clean_cell(row[col_map['SwitchName']]) if col_map['SwitchName'] < len(row) else ""
        station = clean_cell(row[col_map['Station']]) if col_map['Station'] < len(row) else ""
        port_id_str = clean_cell(row[col_map['PortID']]) if col_map['PortID'] < len(row) else ""
        if port_id_str == "":
            continue
        try:
            port_id = int(port_id_str)
        except ValueError:
            continue
        port_dev = clean_cell(row[col_map['PortDev']]) if col_map['PortDev'] < len(row) else ""
        if switch_id not in switches_dict:
            switches_dict[switch_id] = {
                'no': switch_id, 'hostname': switch_name,
                'station': station, 'ports': []
            }
        switches_dict[switch_id]['ports'].append({'port_id': port_id, 'dev': port_dev})
    switches = list(switches_dict.values())
    switches.sort(key=lambda x: x['no'])
    return switches


# ============================================================
# Disney（C9000 NMS 接口）数据加载
#   交换机：NEConfigData（配置文件，列 STATION / NMSNO / PortNbr）
#       STATION 以 SHD 开头 -> 试车线，其余 -> 正线
#   AP / WAC：AP点表 / WAC点表（工作表“正线”“试车线”）
# ============================================================
def _norm_cell(v):
    return clean_cell(v).replace("\xa0", " ").replace("\u3000", " ").strip()


def detect_line(station):
    """根据车站/集中区判断所属线路。"""
    s = _norm_cell(station).upper()
    if not s:
        return LINE_MAIN
    if s.startswith("SHD") or "试车" in s:
        return LINE_TEST
    return LINE_MAIN


def load_switches_disney(file_path, sheet_name=None):
    """解析 Disney 交换机配置表（NEConfigData）。

    返回 [{'no','hostname','station','nmsno','port_mask','total_ports','line',...}]
    """
    if sheet_name is None:
        names = get_sheet_names_any(file_path)
        for pattern in DISNEY_SWITCH_SHEET_NAMES:
            for s in names:
                if pattern in s:
                    sheet_name = s
                    break
            if sheet_name:
                break
        if sheet_name is None:
            sheet_name = names[0]

    rows = read_rows_any(file_path, sheet_name)

    header_idx = None
    for idx, row in enumerate(rows):
        ups = [_norm_cell(c).upper() for c in row]
        if "NO" in ups and ("HOSTNAME" in ups or "PORTNBR" in ups or "STATION" in ups):
            header_idx = idx
            break
    if header_idx is None:
        raise ValueError("配置文件中未找到 'NO / HOSTNAME' 表头，不是有效的 NEConfigData 格式")

    headers = [_norm_cell(c).upper() for c in rows[header_idx]]

    def col_of(*cands):
        for cand in cands:
            for i, h in enumerate(headers):
                if h == cand:
                    return i
        return None

    c_no = col_of("NO")
    c_host = col_of("HOSTNAME", "NAME")
    c_station = col_of("STATION", "集中区", "车站")
    c_nmsno = col_of("NMSNO", "NMS_NO")
    c_port = None
    for i, h in enumerate(headers):
        if "PORTNBR" in h or "PORTNBR" == h.replace(" ", ""):
            c_port = i
            break
    if c_port is None and c_station is not None and c_station + 2 < len(headers):
        c_port = c_station + 2

    if c_no is None or c_host is None:
        raise ValueError("配置表缺少必需的 NO / HOSTNAME 列")

    switches = []
    for idx in range(header_idx + 1, len(rows)):
        row = rows[idx]
        if c_no >= len(row):
            break
        a = _norm_cell(row[c_no])
        if a == "":
            continue
        if a.startswith("["):
            break
        if not a.isdigit():
            break
        try:
            no = int(a)
        except ValueError:
            break
        hostname = _norm_cell(row[c_host]) if c_host < len(row) else ""
        station = _norm_cell(row[c_station]) if (c_station is not None and c_station < len(row)) else ""
        port_mask = _norm_cell(row[c_port]) if (c_port is not None and c_port < len(row)) else ""
        try:
            nmsno = int(_norm_cell(row[c_nmsno])) if (c_nmsno is not None and c_nmsno < len(row)
                                                       and _norm_cell(row[c_nmsno]).lstrip("-").isdigit()) else 0
        except Exception:
            nmsno = 0
        switches.append({
            "no": no,
            "hostname": hostname,
            "station": station,
            "nmsno": nmsno,
            "port_mask": port_mask,
            "total_ports": parse_port_total(port_mask),
            "line": detect_line(station),
        })
    if not switches:
        raise ValueError("配置表中未解析到任何交换机（请检查 NO / HOSTNAME / PortNbr 列）")
    return switches


def load_point_table(file_path, kind, sheet_name):
    """解析 AP 点表 / WAC 点表的一个工作表。

    kind: "AP" | "WAC"
    返回 [{'no','name','ip','zone','net','km','direction','train','onboard'}]
    """
    rows = read_rows_any(file_path, sheet_name)
    kind = (kind or "AP").upper()
    name_keys = ("AP名称", "无线单元名称", "WAC名称") if kind == "AP" else ("WAC名称",)
    if kind == "AP":
        name_keys = ("AP名称", "无线单元名称", "AP NAME", "NAME")

    items = []
    cols = None
    for row in rows:
        cells = [_norm_cell(c) for c in row]
        if any(c == "序号" for c in cells) or any(c.upper() == "NO" for c in cells):
            mapping = {}
            for i, c in enumerate(cells):
                up = c.upper()
                if c == "序号" or up == "NO":
                    mapping.setdefault("no", i)
                elif any(k.upper() in up for k in name_keys) and "name" not in mapping:
                    mapping["name"] = i
                elif "IP" in up and "ip" not in mapping:
                    mapping["ip"] = i
                elif ("集中区" in c or "STATION" in up) and "zone" not in mapping:
                    mapping["zone"] = i
                elif "网络" in c or "NET" == up and "net" not in mapping:
                    mapping["net"] = i
                elif "公里标" in c and "km" not in mapping:
                    mapping["km"] = i
                elif "方向" in c and "direction" not in mapping:
                    mapping["direction"] = i
                elif "列车" in c and "train" not in mapping:
                    mapping["train"] = i
            cols = mapping if "name" in mapping else None
            continue

        if not cols:
            continue

        def cell(key):
            i = cols.get(key)
            if i is None or i >= len(cells):
                return ""
            return cells[i]

        name = clean_cell(cell("name"))
        if not name:
            continue
        no_s = clean_cell(cell("no"))
        if no_s and not no_s.isdigit():
            continue
        items.append({
            "no": int(no_s) if no_s.isdigit() else len(items) + 1,
            "name": name,
            "ip": clean_cell(cell("ip")),
            "zone": clean_cell(cell("zone")),
            "net": clean_cell(cell("net")),
            "km": clean_cell(cell("km")),
            "direction": clean_cell(cell("direction")),
            "train": clean_cell(cell("train")),
            "onboard": ("车载" in name) or ("_Client" in name) or bool(clean_cell(cell("train"))),
            "sheet": sheet_name,
        })
    return items


def pick_point_sheets(file_path, line, kind="AP"):
    """按线路挑选点表工作表（正线 / 试车线）。"""
    names = get_sheet_names_any(file_path)
    keys = DISNEY_AP_SHEET_MAIN if line == LINE_MAIN else DISNEY_AP_SHEET_TEST
    picked = []
    for s in names:
        for k in keys:
            if k.lower() in s.lower():
                picked.append(s)
                break
    return picked


# ============================================================
# 报文打包函数
# ============================================================
def build_packet_v1(switches, port_mapping, custom_status=None, nms_version=None):
    HEADER = 0xAA
    END = 0x55
    MSG_ID = 0x10
    NMS_INDEX = 0x00
    AP_NUM = 0

    stamp = int(time.time())
    if nms_version is None:
        nms_version = random.randint(0, 0xFFFFFFFF)

    bit_buffer = bytearray()
    cur_byte = 0
    bit_pos = 0
    switch_info = []

    def write_bits(value, bit_len):
        nonlocal cur_byte, bit_pos
        for i in range(bit_len - 1, -1, -1):
            bit = (value >> i) & 0x01
            if bit:
                cur_byte |= (1 << (7 - bit_pos))
            bit_pos += 1
            if bit_pos == 8:
                bit_buffer.append(cur_byte)
                cur_byte = 0
                bit_pos = 0

    def flush_bits():
        nonlocal cur_byte, bit_pos
        if bit_pos > 0:
            bit_buffer.append(cur_byte)
            cur_byte = 0
            bit_pos = 0

    sw_num = len(switches)
    for sw in switches:
        no = sw["no"]
        total_ports = sw["total_ports"]
        sw_status = custom_status[no][0] if (custom_status and no in custom_status) else 0b00
        write_bits(sw_status, 2)

        sw_map = port_mapping.get(no, {})
        port_summary = {"正常": 0, "故障": 0, "超标": 0}
        port_details = []
        for port_no in range(1, total_ports + 1):
            port_status = 0b00
            if custom_status and no in custom_status:
                port_status = custom_status[no][1].get(port_no, port_status)
            write_bits(port_status, 2)
            if port_status == 0b00:
                port_summary["正常"] += 1
            elif port_status == 0b01:
                port_summary["故障"] += 1
            elif port_status == 0b10:
                port_summary["超标"] += 1
            port_details.append({"port_no": port_no, "status": port_status,
                                 "dev": sw_map.get(port_no, "")})

        switch_info.append({
            'no': no, 'hostname': sw["hostname"], 'station': sw.get("station", ""),
            'total_ports': total_ports, 'sw_status': sw_status,
            'port_summary': port_summary, 'ports': port_details
        })

    flush_bits()
    switch_bytes = bytes(bit_buffer)

    data = bytearray()
    data.append(MSG_ID)
    data.extend(struct.pack(">I", stamp))
    data.append(NMS_INDEX)
    data.extend(struct.pack(">I", nms_version))
    data.extend(struct.pack(">H", AP_NUM))
    data.append(sw_num)
    data.extend(switch_bytes)
    data.append(END)

    data_len = len(data) + 4
    packet = bytearray()
    packet.append(HEADER)
    packet.extend(struct.pack(">H", data_len))
    packet.extend(data)
    crc = crc32_custom(bytes(data))
    packet.extend(struct.pack(">I", crc))
    return bytes(packet), switch_info


def build_packet_v2(switches, custom_status=None, nms_version=None):
    HEADER = 0xAA
    END = 0x55
    MSG_ID = 0x10
    NMS_INDEX = 0x01
    AP_NUM = 0

    stamp = int(time.time())
    if nms_version is None:
        nms_version = random.randint(0, 0xFFFFFFFF)

    bit_buffer = bytearray()
    cur_byte = 0
    bit_pos = 0
    switch_info = []

    def write_bits(value, bit_len):
        nonlocal cur_byte, bit_pos
        for i in range(bit_len - 1, -1, -1):
            bit = (value >> i) & 0x01
            if bit:
                cur_byte |= (1 << (7 - bit_pos))
            bit_pos += 1
            if bit_pos == 8:
                bit_buffer.append(cur_byte)
                cur_byte = 0
                bit_pos = 0

    def flush_bits():
        nonlocal cur_byte, bit_pos
        if bit_pos > 0:
            bit_buffer.append(cur_byte)
            cur_byte = 0
            bit_pos = 0

    sw_num = len(switches)
    write_bits(sw_num, 16)

    for sw in switches:
        no = sw["no"]
        port_ids = sorted([p['port_id'] for p in sw['ports']])
        start_bit = len(bit_buffer) * 8 + bit_pos
        write_bits(no, 16)

        sw_status_val = 0
        sw_status_text = 0
        if custom_status and no in custom_status:
            sw_st = custom_status[no][0]
            sw_status_text = sw_st
            if sw_st == 1:
                sw_status_val |= 0x01
            elif sw_st == 2:
                sw_status_val |= 0x02
            elif sw_st == 3:
                sw_status_val |= 0x04
        write_bits(sw_status_val, 8)

        port_status_dict = custom_status.get(no, (0, {}))[1] if (custom_status and no in custom_status) else {}
        port_summary = {"正常": 0, "故障": 0, "超标": 0}
        for pid in port_ids:
            port_stat = port_status_dict.get(pid, 0)
            port_val = 0
            if port_stat == 1:
                port_val |= 0x01
                port_summary["故障"] += 1
            elif port_stat == 2:
                port_val |= 0x02
                port_summary["超标"] += 1
            else:
                port_summary["正常"] += 1
            write_bits(port_val, 4)

        if len(port_ids) % 2 == 1:
            write_bits(0, 4)

        flush_bits()
        end_bit = len(bit_buffer) * 8
        byte_len = (end_bit - start_bit + 7) // 8
        switch_info.append({
            'no': no, 'hostname': sw['hostname'],
            'sw_status': sw_status_text, 'port_summary': port_summary,
            'offset': start_bit // 8, 'length': byte_len
        })

    flush_bits()
    switch_bytes = bytes(bit_buffer)

    msg_body = bytearray()
    msg_body.extend(struct.pack(">I", stamp))
    msg_body.append(MSG_ID)
    msg_body.append(NMS_INDEX)
    msg_body.extend(struct.pack(">I", nms_version))
    msg_body.extend(struct.pack(">H", AP_NUM))
    msg_body.extend(switch_bytes)
    msg_body.append(END)

    msg_id_to_end = msg_body[4:]
    len_value = len(msg_id_to_end) + 4

    packet = bytearray()
    packet.append(HEADER)
    packet.extend(struct.pack(">H", len_value))
    packet.extend(msg_body)
    crc = crc32_custom(bytes(msg_id_to_end))
    packet.extend(struct.pack(">I", crc))
    return bytes(packet), switch_info


def build_packet_v4(switches, custom_status=None, config=None, nms_version=None):
    config = config or {}
    HEADER = 0xAA
    END = 0x55
    MSG_ID = 0x10
    NMS_INDEX = 0x01

    stamp = int(time.time())
    if nms_version is None:
        nms_version = random.randint(0, 0xFFFFFFFF)

    cpu_threshold = max(0, min(100, int(config.get("cpu_threshold", 80))))
    service_port_speed = max(0, min(0xFFFFFFFF, int(config.get("service_port_speed", 50000))))
    non_service_port_speed = max(0, min(0xFFFFFFFF, int(config.get("non_service_port_speed", 5000))))
    bw_min = max(0, min(100, int(config.get("bandwidth_min", 0))))
    bw_max = max(0, min(100, int(config.get("bandwidth_max", 100))))
    if bw_min > bw_max:
        bw_min, bw_max = bw_max, bw_min

    sw_info_list = []
    switch_bytes = bytearray()

    for sw in switches:
        no = int(sw["no"])
        hostname = sw.get("hostname", "")
        station = sw.get("station", "")
        port_list = sorted(sw.get("ports", []), key=lambda p: int(p['port_id']))
        port_ids = [int(p['port_id']) for p in port_list]
        port_dev_map = {int(p['port_id']): p.get('dev', '') for p in port_list}
        port_count = len(port_ids)

        user_sw_status = 0
        user_port_status = {}
        if custom_status and no in custom_status:
            user_sw_status = custom_status[no][0]
            user_port_status = custom_status[no][1]

        cpu_usage = random.randint(0, 100)
        if user_sw_status == 2:
            cpu_usage = random.randint(cpu_threshold, 100)

        port_flux = {}
        port_bandwidth = {}
        port_error = {}
        has_port_error = False
        for pid in port_ids:
            st = user_port_status.get(pid, 0)
            if st == 2:
                flux = random.randint(min(service_port_speed, 0xFFFFFFFF), 0xFFFFFFFF)
                bandwidth = random.randint(max(bw_max // 2, 50), 100)
            else:
                flux = random.randint(0, 0xFFFFFFFF)
                bandwidth = random.randint(bw_min, bw_max)
            port_flux[pid] = flux
            port_bandwidth[pid] = bandwidth
            port_error[pid] = random.randint(0, 0xFFFF)
            if st in (1, 2):
                has_port_error = True

        sw_status_byte = 0
        if user_sw_status == 1:
            sw_status_byte |= 0x01
        if user_sw_status == 2:
            sw_status_byte |= 0x02
        if user_sw_status == 3:
            sw_status_byte |= 0x04

        switch_bytes.extend(struct.pack(">H", no))
        switch_bytes.append(sw_status_byte)
        switch_bytes.append(cpu_usage)

        status_bit_buf = bytearray()
        cur_byte = 0
        bit_pos = 0
        for pid in port_ids:
            st = user_port_status.get(pid, 0)
            port_val = 0
            if st == 1:
                port_val = 0b0001
            elif st == 2:
                port_val = 0b0010
            for i in range(3, -1, -1):
                bit = (port_val >> i) & 0x01
                if bit:
                    cur_byte |= (1 << (7 - bit_pos))
                bit_pos += 1
                if bit_pos == 8:
                    status_bit_buf.append(cur_byte)
                    cur_byte = 0
                    bit_pos = 0
        if bit_pos > 0:
            status_bit_buf.append(cur_byte)
        switch_bytes.extend(status_bit_buf)

        for pid in port_ids:
            switch_bytes.extend(struct.pack(">H", port_flux[pid] & 0xFFFF))
        for pid in port_ids:
            switch_bytes.append(port_bandwidth[pid] & 0xFF)
        for pid in port_ids:
            switch_bytes.extend(struct.pack(">H", port_error[pid] & 0xFFFF))

        ports_info = []
        for pid in port_ids:
            st = user_port_status.get(pid, 0)
            ports_info.append({
                'id': pid, 'status': st,
                'flux': port_flux[pid], 'bandwidth': port_bandwidth[pid],
                'error': port_error[pid], 'dev': port_dev_map.get(pid, '')
            })

        sw_info_list.append({
            'no': no, 'hostname': hostname, 'station': station,
            'sw_status': user_sw_status, 'sw_status_byte': sw_status_byte,
            'cpu_usage': cpu_usage, 'port_count': port_count,
            'port_status_bytes': bytes(status_bit_buf), 'ports': ports_info
        })

    body = bytearray()
    body.extend(struct.pack(">I", stamp))
    body.append(MSG_ID)
    body.append(NMS_INDEX)
    body.extend(struct.pack(">I", nms_version))
    body.append(cpu_threshold)
    body.extend(struct.pack(">I", service_port_speed))
    body.extend(struct.pack(">I", non_service_port_speed))
    body.extend(struct.pack(">H", 0))
    body.extend(struct.pack(">H", len(switches)))
    body.extend(switch_bytes)
    body.append(END)

    lbw = len(body) + 4
    crc = crc32_custom(bytes(body[4:]))

    packet = bytearray()
    packet.append(HEADER)
    packet.extend(struct.pack(">H", lbw))
    packet.extend(body)
    packet.extend(struct.pack(">I", crc))

    meta_info = {
        'cpu_threshold': cpu_threshold,
        'service_port_speed': service_port_speed,
        'non_service_port_speed': non_service_port_speed,
        'bandwidth_min': bw_min, 'bandwidth_max': bw_max
    }
    return bytes(packet), sw_info_list, meta_info


def build_packet_v6(switches, custom_status=None, config=None, nms_version=None):
    config = config or {}
    HEADER = 0xAA
    END = 0x55
    MSG_ID = 0x10
    NMS_INDEX = 0x01

    stamp = int(time.time())
    if nms_version is None:
        nms_version = random.randint(0, 0xFFFFFFFF)

    cpu_threshold = max(0, min(100, int(config.get("cpu_threshold", 80))))
    service_port_speed = int(config.get("service_port_speed", 50000))
    non_service_port_speed = int(config.get("non_service_port_speed", 5000))

    memory_min = max(0, min(100, int(config.get("memory_min", 0))))
    memory_max = max(0, min(100, int(config.get("memory_max", 100))))
    if memory_min > memory_max:
        memory_min, memory_max = memory_max, memory_min

    delay_min = max(0, int(config.get("trans_delay_min", 0)))
    delay_max = max(0, int(config.get("trans_delay_max", 5)))
    if delay_min > delay_max:
        delay_min, delay_max = delay_max, delay_min

    loss_min = max(0, min(100, int(config.get("packet_loss_min", 0))))
    loss_max = max(0, min(100, int(config.get("packet_loss_max", 5))))
    if loss_min > loss_max:
        loss_min, loss_max = loss_max, loss_min

    bit_min = max(0, min(100, int(config.get("bit_error_min", 0))))
    bit_max = max(0, min(100, int(config.get("bit_error_max", 5))))
    if bit_min > bit_max:
        bit_min, bit_max = bit_max, bit_min

    bw_min = max(0, min(100, int(config.get("bandwidth_min", 0))))
    bw_max = max(0, min(100, int(config.get("bandwidth_max", 100))))
    if bw_min > bw_max:
        bw_min, bw_max = bw_max, bw_min

    def get_switch_config(name, no, default=0):
        data = config.get(name, {})
        if not isinstance(data, dict):
            return default
        return data.get(no, data.get(str(no), default))

    def get_port_config(name, no, pid, default=0):
        data = config.get(name, {})
        if not isinstance(data, dict):
            return default
        sw_data = data.get(no, data.get(str(no), {}))
        if not isinstance(sw_data, dict):
            return default
        return sw_data.get(pid, sw_data.get(str(pid), default))

    def get_port_status(no, pid, custom_status):
        if no not in custom_status:
            return 0
        port_dict = custom_status[no][1]
        if not isinstance(port_dict, dict):
            return 0
        return int(port_dict.get(pid, 0))

    body = bytearray()
    body.extend(struct.pack(">I", stamp))
    body.append(MSG_ID)
    body.append(NMS_INDEX)
    body.extend(struct.pack(">I", nms_version))
    body.append(cpu_threshold)
    body.extend(struct.pack(">I", service_port_speed))
    body.extend(struct.pack(">I", non_service_port_speed))
    body.extend(struct.pack(">H", 0))
    body.extend(struct.pack(">H", len(switches)))

    infos = []

    for sw in switches:
        no = int(sw["no"])
        hostname = sw.get("hostname", "")
        station = sw.get("station", "")
        ports = sorted([int(p["port_id"]) for p in sw.get("ports", [])])

        sw_status = int(custom_status.get(no, (0, {}))[0])
        sw_status_byte = {0: 0x00, 1: 0x01, 2: 0x02, 3: 0x04}.get(sw_status, 0x00)
        dual_power = int(get_switch_config("dual_power", no, 0)) & 0xFF
        ring_status = int(get_switch_config("ring_status", no, 0)) & 0xFF
        ring_master = int(get_switch_config("ring_master", no, 1)) & 0xFF

        cpu_usage = random.randint(cpu_threshold, 100) if sw_status == 2 else random.randint(0, 100)
        memory_usage = random.randint(memory_min, memory_max)
        transmission_delay = random.randint(delay_min, delay_max)

        body.extend(struct.pack(">H", no))
        body.append(sw_status_byte)
        body.append(dual_power)
        body.append(cpu_usage)
        body.append(memory_usage)
        body.extend(struct.pack(">H", transmission_delay))
        body.append(ring_status)
        body.append(ring_master)

        break_port_ids = []
        for pid in ports:
            brk = int(get_port_config("break_port", no, pid, 5))
            brk = 6 if brk == 6 else 5
            body.append(brk)
            break_port_ids.append(brk)

        optical_status_list = []
        for pid in ports:
            optical = max(0, min(3, int(get_port_config("optical_status", no, pid, 0))))
            body.append(optical)
            optical_status_list.append(optical)

        port_status_list = []
        status_bit_buf = bytearray()
        status_cur_byte = 0
        status_bit_pos = 0

        def write_status_bits(value, bit_len):
            nonlocal status_cur_byte, status_bit_pos
            for i in range(bit_len - 1, -1, -1):
                bit = (value >> i) & 0x01
                if bit:
                    status_cur_byte |= (1 << (7 - status_bit_pos))
                status_bit_pos += 1
                if status_bit_pos == 8:
                    status_bit_buf.append(status_cur_byte)
                    status_cur_byte = 0
                    status_bit_pos = 0

        for pid in ports:
            status = max(0, min(2, get_port_status(no, pid, custom_status)))
            port_status_list.append(status)
            write_status_bits(status, 4)
        if len(ports) % 2 == 1:
            write_status_bits(0, 4)
        if status_bit_pos > 0:
            status_bit_buf.append(status_cur_byte)
        body.extend(status_bit_buf)

        flux_list = []
        for pid in ports:
            flux = random.randint(0, 65535)
            body.extend(struct.pack(">H", flux))
            flux_list.append(flux)

        bandwidth_list = []
        for pid in ports:
            bw = random.randint(bw_min, bw_max)
            body.append(bw)
            bandwidth_list.append(bw)

        forward_speed_list = []
        for pid in ports:
            fs = random.randint(0, 0xFFFFFFFF)
            body.extend(struct.pack(">I", fs))
            forward_speed_list.append(fs)

        error_list = []
        for pid in ports:
            e = random.randint(0, 65535)
            body.extend(struct.pack(">H", e))
            error_list.append(e)

        packet_loss_list = []
        for pid in ports:
            pl = random.randint(loss_min, loss_max)
            body.append(pl)
            packet_loss_list.append(pl)

        bit_error_list = []
        for pid in ports:
            be = random.randint(bit_min, bit_max)
            body.append(be)
            bit_error_list.append(be)

        port_infos = []
        for i, pid in enumerate(ports):
            port_infos.append({
                "id": pid, "status": port_status_list[i],
                "optical_status": optical_status_list[i], "break_status": break_port_ids[i],
                "flux": flux_list[i], "bandwidth": bandwidth_list[i],
                "forward_speed": forward_speed_list[i], "error": error_list[i],
                "packet_loss": packet_loss_list[i], "bit_error": bit_error_list[i]
            })

        infos.append({
            "no": no, "hostname": hostname, "station": station,
            "sw_status": sw_status, "sw_status_byte": sw_status_byte,
            "dual_power": dual_power, "cpu_usage": cpu_usage,
            "memory_usage": memory_usage, "transmission_delay": transmission_delay,
            "ring_status": ring_status, "ring_master": ring_master,
            "break_port_ids": break_port_ids, "port_status_bytes": bytes(status_bit_buf),
            "ports": port_infos
        })

    body.append(END)
    length = len(body) + 4
    crc = crc32_custom(bytes(body[4:]))

    packet = bytearray()
    packet.append(HEADER)
    packet.extend(struct.pack(">H", length))
    packet.extend(body)
    packet.extend(struct.pack(">I", crc))

    meta = {
        "cpu_threshold": cpu_threshold,
        "service_port_speed": service_port_speed,
        "non_service_port_speed": non_service_port_speed,
        "memory_min": memory_min, "memory_max": memory_max,
        "trans_delay_min": delay_min, "trans_delay_max": delay_max,
        "packet_loss_min": loss_min, "packet_loss_max": loss_max,
        "bit_error_min": bit_min, "bit_error_max": bit_max,
        "bandwidth_min": bw_min, "bandwidth_max": bw_max
    }
    return bytes(packet), infos, meta


# ============================================================
# Disney 报文打包 / 解析（C9000-W-000-TCT-160-000011）
#
# 帧结构（与接口说明书 Table 3 顺序一致，MSG_ID 在 STAMP 之前）：
#   HEADER(8)=0xAA | LEN(16) | MSG_ID(8)=0x10 | STAMP(32) | NMS_INDEX(8)
#   | NMS_VERSION(32) | AP_NUM(16) | AP状态(2bit×n) | AC_NUM(16) | AC状态(2bit×n)
#   | SW_NUM(8) | [SW_STATUS(2) + 端口状态(2bit×n)] × SW_NUM | END(8)=0x55 | CRC32(32)
#   说明：每种设备状态不足整字节时补 0；CRC 计算范围 MSG_ID ~ END；
#        LEN 为从 MSG_ID 起到 CRC 校验结束的字节数（= body长度 + 4）
# ============================================================
class BitWriter:
    def __init__(self):
        self.buf = bytearray()
        self.cur = 0
        self.pos = 0

    def write(self, value, bit_len):
        value = int(value)
        for i in range(bit_len - 1, -1, -1):
            if (value >> i) & 0x01:
                self.cur |= (1 << (7 - self.pos))
            self.pos += 1
            if self.pos == 8:
                self.buf.append(self.cur)
                self.cur = 0
                self.pos = 0

    def pad(self):
        if self.pos:
            self.buf.append(self.cur)
            self.cur = 0
            self.pos = 0

    @property
    def bit_len(self):
        return len(self.buf) * 8 + self.pos

    def bytes(self):
        self.pad()
        return bytes(self.buf)


class BitReader:
    def __init__(self, data, start_bit=0):
        self.data = data
        self.pos = start_bit

    def read(self, bit_len):
        v = 0
        for _ in range(bit_len):
            byte_i = self.pos // 8
            bit_i = 7 - (self.pos % 8)
            bit = (self.data[byte_i] >> bit_i) & 0x01 if byte_i < len(self.data) else 0
            v = (v << 1) | bit
            self.pos += 1
        return v

    def align(self):
        self.pos = (self.pos + 7) // 8 * 8

    @property
    def pad_bits(self):
        return (-self.pos) % 8


def build_packet_disney(switches, port_mapping, aps, wacs, custom_status=None,
                        nms_version=None, nms_index=0x00, pad_blocks=True):
    """生成 Disney 报文。

    switches       : 该线路交换机列表（含 no/hostname/total_ports）
    port_mapping   : {交换机编号: {端口号: 设备名}}
    aps / wacs     : 该线路 AP / WAC 列表（含 status: 0正常 1故障 2关闭）
    custom_status  : {交换机编号: (整机状态0~3, {端口号: 0正常 1故障 2超标})}
    """
    HEADER = 0xAA
    END = 0x55
    MSG_ID = 0x10

    stamp = int(time.time())
    if nms_version is None:
        nms_version = random.randint(0, 0xFFFFFFFF)
    if len(switches) > 0xFF:
        raise ValueError("交换机数量超过 255 台（SW_NUM 仅 8bit）")
    if len(aps) > 0xFFFF or len(wacs) > 0xFFFF:
        raise ValueError("AP / WAC 数量超过 65535")

    body = bytearray()
    body.append(MSG_ID)                     # MSG_ID 在 STAMP 之前（与接口说明书一致）
    body.extend(struct.pack(">I", stamp))
    body.append(int(nms_index) & 0xFF)
    body.extend(struct.pack(">I", nms_version))

    bw = BitWriter()

    # ---------- AP 段 ----------
    ap_infos = []
    bw.write(len(aps), 16)
    for ap in aps:
        st = int(ap.get("status", 0))
        code = DISNEY_AP_STATUS.get(st, 0)
        bw.write(code, 2)
        ap_infos.append({
            "no": ap.get("no"), "name": ap.get("name", ""), "zone": ap.get("zone", ""),
            "net": ap.get("net", ""), "ip": ap.get("ip", ""),
            "status": st, "code": code, "onboard": bool(ap.get("onboard"))
        })
    if pad_blocks:
        bw.pad()

    # ---------- AC(WAC) 段 ----------
    wac_infos = []
    bw.write(len(wacs), 16)
    for wac in wacs:
        st = int(wac.get("status", 0))
        code = DISNEY_WAC_STATUS.get(st, 0)
        bw.write(code, 2)
        wac_infos.append({
            "no": wac.get("no"), "name": wac.get("name", ""), "zone": wac.get("zone", ""),
            "net": wac.get("net", ""), "ip": wac.get("ip", ""),
            "status": st, "code": code
        })
    if pad_blocks:
        bw.pad()

    # ---------- 交换机段 ----------
    bw.write(len(switches), 8)
    sw_infos = []
    for sw in switches:
        no = int(sw["no"])
        total_ports = int(sw.get("total_ports", 0))
        if total_ports <= 0:
            total_ports = len(port_mapping.get(no, {}))

        sw_status = 0
        port_status = {}
        if custom_status and no in custom_status:
            sw_status = int(custom_status[no][0])
            port_status = custom_status[no][1] or {}
        if sw_status not in DISNEY_SW_STATUS:
            sw_status = 0

        bw.write(DISNEY_SW_STATUS[sw_status], 2)

        sw_map = port_mapping.get(no, {})
        ports = []
        summary = {0: 0, 1: 0, 2: 0}
        for port_no in range(1, total_ports + 1):
            pst = int(port_status.get(port_no, 0))
            if pst not in DISNEY_PORT_STATUS:
                pst = 0
            bw.write(DISNEY_PORT_STATUS[pst], 2)
            summary[pst] += 1
            ports.append({"port_no": port_no, "status": pst, "dev": sw_map.get(port_no, "")})

        sw_infos.append({
            "no": no, "hostname": sw.get("hostname", ""), "station": sw.get("station", ""),
            "total_ports": total_ports, "sw_status": sw_status,
            "summary": summary, "ports": ports
        })

    bw.pad()
    bw.write(END, 8)
    body.extend(bw.bytes())

    length = len(body) + 4      # LEN：从 MSG_ID 到 CRC 校验结束
    crc = crc32_custom(bytes(body))   # CRC：MSG_ID ~ END

    packet = bytearray()
    packet.append(HEADER)
    packet.extend(struct.pack(">H", length))
    packet.extend(body)
    packet.extend(struct.pack(">I", crc))

    info = {
        "stamp": stamp, "msg_id": MSG_ID, "nms_index": int(nms_index) & 0xFF,
        "nms_version": nms_version, "ap_num": len(aps), "aps": ap_infos,
        "wac_num": len(wacs), "wacs": wac_infos, "sw_num": len(switches),
        "switches": sw_infos, "len_field": length, "pad_blocks": bool(pad_blocks),
        "body": bytes(body),
    }
    return bytes(packet), info


def parse_packet_disney(packet, port_counts=None, pad_blocks=True):
    """解析 Disney 报文，返回字段字典。

    port_counts: 各交换机端口数（帧内不含端口数，需外部提供才能继续解析交换机段）
    """
    n = len(packet)
    if n < 18:
        raise ValueError("报文长度不足，不是有效的 Disney 帧")
    if packet[0] != 0xAA:
        raise ValueError(f"帧头错误：0x{packet[0]:02X}（应为 0xAA）")

    res = {}
    res["raw"] = bytes(packet)
    res["header"] = packet[0]
    res["len_field"] = int.from_bytes(packet[1:3], "big")
    res["msg_id"] = packet[3]
    res["stamp"] = int.from_bytes(packet[4:8], "big")
    res["nms_index"] = packet[8]
    res["nms_version"] = int.from_bytes(packet[9:13], "big")
    res["len_ok"] = (res["len_field"] == n - 3)

    br = BitReader(packet, 13 * 8)

    res["ap_num"] = br.read(16)
    res["ap_num_offset"] = 13
    ap_bit0 = br.pos
    res["ap_codes"] = [br.read(2) for _ in range(res["ap_num"])]
    res["ap_pad_bits"] = br.pad_bits if pad_blocks else 0
    res["ap_offset"] = ap_bit0 // 8
    res["ap_len"] = (ap_bit0 + res["ap_num"] * 2 + 7) // 8 - res["ap_offset"]
    if pad_blocks:
        br.align()

    res["wac_num_offset"] = br.pos // 8
    res["wac_num"] = br.read(16)
    ac_bit0 = br.pos
    res["wac_codes"] = [br.read(2) for _ in range(res["wac_num"])]
    res["wac_pad_bits"] = br.pad_bits if pad_blocks else 0
    res["wac_offset"] = ac_bit0 // 8
    res["wac_len"] = (ac_bit0 + res["wac_num"] * 2 + 7) // 8 - res["wac_offset"]
    if pad_blocks:
        br.align()

    res["sw_num_offset"] = br.pos // 8
    res["sw_num"] = br.read(8)
    res["sw_offset"] = br.pos // 8

    switches = []
    decoded = 0
    for i in range(res["sw_num"]):
        if port_counts is not None and i < len(port_counts):
            pc = int(port_counts[i] or 0)
            st = br.read(2)
            ports = [br.read(2) for _ in range(pc)]
            switches.append({"index": i + 1, "sw_status": st, "ports": ports})
            decoded += 1
        else:
            break
    res["switches"] = switches
    res["sw_decoded"] = decoded

    br.align()
    res["end_offset"] = br.pos // 8
    res["end"] = br.read(8)
    res["crc_offset"] = br.pos // 8
    res["crc"] = int.from_bytes(packet[-4:], "big")
    res["crc_calc"] = crc32_custom(packet[3:-4])    # MSG_ID(偏移0x03) ~ END
    res["crc_ok"] = (res["crc"] == res["crc_calc"])
    res["end_ok"] = (res["end"] == 0x55)
    return res


# ============================================================
# 主界面
# ============================================================
class NMSApp(tk.Tk):
    LOG_MAX_LINES = 3000
    CONTINUOUS_LOG_EVERY = 10
    REG_PATH = r"Software\NMSApp"
    CONFIG_NAME_MAP = {
        "local_ip": "local_ip",
        "udp_ip": "target_ip",
        "udp_port": "target_port",
        "interval_ms": "interval_ms",
        "data_file": "data_file",
        "mapping_file": "mapping_file",
        "ap_file": "ap_file",
        "wac_file": "wac_file",
        "local_ip_main": "local_ip_main",
        "local_ip_shd": "local_ip_shd"
    }

    def __init__(self):
        super().__init__()
        self.title("DCS协议报文工具 v3.1（新增 Disney 版本）")
        self.geometry("1360x800")
        self.set_window_icon()

        self.data_file = tk.StringVar()
        self.mapping_file = tk.StringVar()
        self.ap_file = tk.StringVar()
        self.wac_file = tk.StringVar()
        self.local_ip = tk.StringVar()
        self.local_ip_main = tk.StringVar()
        self.local_ip_shd = tk.StringVar()
        self.udp_ip = tk.StringVar()
        self.udp_port = tk.StringVar()
        self.interval_ms = tk.StringVar()

        self.version_var = tk.StringVar(value="V1.0")
        self.all_switches = []
        self.port_mapping = {}
        self.selected_indices = set()
        self.switch_status = {}
        self.version = None
        self.tree = None
        self.ap_tree = None
        self.wac_tree = None
        self.ap_list = []
        self.wac_list = []
        self.log_text = None
        self.status_var = tk.StringVar(value="就绪")
        self._loading = False

        # Disney 专用配置
        self.disney_config = {
            "nms_index_main": 0,
            "nms_index_test": 1,
            "pad_blocks": True,
        }
        self.disney_packets = {}
        self._send_sock_main = None
        self._send_sock_shd = None

        self.global_sw_var = tk.IntVar(value=0)
        self.global_port_var = tk.IntVar(value=0)

        self.current_packet = None
        self.continuous_running = False
        self.after_id = None
        self.preview_window = None
        self._topology_window = None

        self._send_sock = None
        self._sent_count = 0
        self._last_status_text = None
        self._log_line_count = 0

        self.v6_config = {
            "cpu_threshold": 80,
            "service_port_speed": 50000,
            "non_service_port_speed": 5000,
            "memory_min": 0, "memory_max": 100,
            "trans_delay_min": 0, "trans_delay_max": 5,
            "packet_loss_min": 0, "packet_loss_max": 5,
            "bit_error_min": 0, "bit_error_max": 5,
            "bandwidth_min": 0, "bandwidth_max": 100,
            "dual_power": {}, "ring_status": {}, "ring_master": {},
            "optical_status": {}, "break_port": {}
        }
        self.load_config()
        self._setup_config_traces()
        self.create_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def set_window_icon(self):
        try:
            base = sys._MEIPASS if hasattr(sys, '_MEIPASS') else os.path.abspath(".")
            p = os.path.join(base, "spider.ico")
            if os.path.exists(p):
                self.iconbitmap(p)
        except Exception as e:
            print(f"设置图标失败：{e}")

    # ---------- 注册表配置 ----------
    def load_config(self):
        defaults = {"local_ip": "", "target_ip": "127.0.0.1", "target_port": "10010",
                    "interval_ms": "1000", "data_file": "", "mapping_file": "",
                    "ap_file": "", "wac_file": "", "local_ip_main": "", "local_ip_shd": ""}
        try:
            cfg = self._read_registry()
        except Exception as e:
            print(f"读取注册表异常: {e}")
            cfg = {}
        for attr_name, reg_key in self.CONFIG_NAME_MAP.items():
            val = cfg.get(reg_key, defaults.get(reg_key, ""))
            setattr(self, attr_name, tk.StringVar(value=str(val)))

    def save_config(self):
        self._write_registry()

    def _setup_config_traces(self):
        for attr_name in self.CONFIG_NAME_MAP.keys():
            var = getattr(self, attr_name, None)
            if var is None:
                continue
            try:
                var.trace_add("write", self._on_config_changed)
            except Exception:
                pass

    def _on_config_changed(self, *args):
        try:
            self._write_registry()
        except Exception:
            pass

    def _read_registry(self):
        result = {}
        if winreg is None:
            return result
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.REG_PATH, 0, winreg.KEY_READ) as key:
                for attr_name, reg_key in self.CONFIG_NAME_MAP.items():
                    try:
                        value, _ = winreg.QueryValueEx(key, reg_key)
                        result[reg_key] = value
                    except FileNotFoundError:
                        pass
        except FileNotFoundError:
            pass
        except Exception as e:
            print(f"读取注册表失败: {e}")
        return result

    def _write_registry(self):
        if winreg is None:
            return
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.REG_PATH) as key:
                for attr_name, reg_key in self.CONFIG_NAME_MAP.items():
                    var = getattr(self, attr_name, None)
                    if var is None:
                        continue
                    try:
                        value = var.get()
                    except Exception:
                        value = ""
                    winreg.SetValueEx(key, reg_key, 0, winreg.REG_SZ, str(value))
        except Exception as e:
            print(f"保存到注册表失败: {e}")

    # ---------- 弹窗居中 ----------
    def _center_window(self, win, width=None, height=None):
        try:
            win.update_idletasks()
            self.update_idletasks()
            main_x = self.winfo_rootx()
            main_y = self.winfo_rooty()
            main_w = self.winfo_width()
            main_h = self.winfo_height()
            if width is None:
                width = win.winfo_reqwidth()
            if height is None:
                height = win.winfo_reqheight()
            x = main_x + max(0, (main_w - width) // 2)
            y = main_y + max(0, (main_h - height) // 2)
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight()
            if x + width > sw:
                x = max(0, sw - width)
            if y + height > sh:
                y = max(0, sh - height)
            if x < 0:
                x = 0
            if y < 0:
                y = 0
            win.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass

    def on_close(self):
        self.save_config()
        self.stop_continuous_send(silent=True)
        if self.preview_window is not None and self.preview_window.winfo_exists():
            self.preview_window.destroy()
        if self._topology_window is not None:
            try:
                if self._topology_window.winfo_exists():
                    self._topology_window.destroy()
            except Exception:
                pass
        self.destroy()

    # ---------- 界面 ----------
    def create_widgets(self):
        main_pane = ttk.Panedwindow(self, orient=HORIZONTAL)
        main_pane.pack(fill=BOTH, expand=True, padx=5, pady=5)

        left_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, weight=3)
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=2)

        # 文件选择
        top_frame = ttk.Frame(left_frame)
        top_frame.pack(pady=5, fill='x', padx=5)
        self.file_frame = ttk.Frame(top_frame)
        self.file_frame.pack(fill='x')

        version_frame = ttk.Frame(top_frame)
        version_frame.pack(fill='x', pady=(4, 0))
        ttk.Label(version_frame, text="版本:").pack(side='left')
        version_combo = ttk.Combobox(version_frame, textvariable=self.version_var,
                                     values=["V1.0", "V3.0", "V4.0", "V6.0", "Disney"],
                                     state="readonly", width=10)
        version_combo.pack(side='left', padx=5)
        version_combo.bind("<<ComboboxSelected>>", self.on_version_changed)
        self._build_file_selectors()

        # 全局状态设置
        global_frame = ttk.LabelFrame(left_frame, text="全局状态设置（选择后实时生效）")
        global_frame.pack(fill='x', padx=5, pady=(5, 2))
        row_sw = ttk.Frame(global_frame)
        row_sw.pack(fill='x', padx=8, pady=3)
        ttk.Label(row_sw, text="整机状态:", width=12, anchor='w').pack(side='left')
        for text, val in [("整机故障", 1), ("高负载", 2), ("端口异常", 3), ("正常", 0)]:
            ttk.Radiobutton(row_sw, text=text, variable=self.global_sw_var,
                            value=val, command=self.apply_global_sw_status).pack(side='left', padx=6)

        row_port = ttk.Frame(global_frame)
        row_port.pack(fill='x', padx=8, pady=3)
        ttk.Label(row_port, text="统一端口状态:", width=12, anchor='w').pack(side='left')
        for text, val in [("故障", 1), ("超标", 2), ("正常", 0)]:
            ttk.Radiobutton(row_port, text=text, variable=self.global_port_var,
                            value=val, command=self.apply_global_port_status).pack(side='left', padx=6)

        # 操作按钮栏
        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(pady=5, fill='x', padx=5)
        ttk.Button(btn_frame, text="全选", command=self.select_all).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="取消全选", command=self.deselect_all).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="V6.0参数设置", command=self.v6_parameter_setting).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="V4.0参数设置", command=self.v4_parameter_setting).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="Disney参数设置", command=self.disney_parameter_setting).pack(side='left', padx=2)
        ttk.Button(btn_frame, text="拓扑图数据校验",
                   command=self.open_topology_check).pack(side='left', padx=8)

        # 设备列表（交换机 / AP / WAC 三个页签）
        self.list_nb = ttk.Notebook(left_frame)
        self.list_nb.pack(fill='both', expand=True, padx=5, pady=5)

        sw_tab = ttk.Frame(self.list_nb)
        self.list_nb.add(sw_tab, text='交换机')

        tree_frame = ttk.Frame(sw_tab)
        tree_frame.pack(fill='both', expand=True)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        columns = ("选择", "编号", "主机名", "车站", "端口数", "整机状态", "端口设置")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings')
        for c, t, w in [("选择","选择",50),("编号","编号",70),("主机名","主机名",150),
                        ("车站","车站",100),("端口数","端口数",70),
                        ("整机状态","整机状态",100),("端口设置","端口设置",80)]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor='center' if c != "主机名" and c != "车站" else 'w')
        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        hsb.grid(row=1, column=0, sticky='ew')

        # ---------- AP 页签 ----------
        ap_tab = ttk.Frame(self.list_nb)
        self.list_nb.add(ap_tab, text='AP列表')
        ap_bar = ttk.Frame(ap_tab)
        ap_bar.pack(fill='x', pady=3, padx=3)
        ttk.Button(ap_bar, text="全部启用", width=8,
                   command=lambda: self.set_all_ap_enabled(True)).pack(side='left', padx=2)
        ttk.Button(ap_bar, text="全部禁用", width=8,
                   command=lambda: self.set_all_ap_enabled(False)).pack(side='left', padx=2)
        ttk.Label(ap_bar, text="批量状态:").pack(side='left', padx=(10, 2))
        for txt, v in [("正常", 0), ("故障", 1), ("关闭", 2)]:
            ttk.Button(ap_bar, text=txt, width=6,
                       command=lambda v=v: self.set_all_ap_status(v)).pack(side='left', padx=2)
        ttk.Label(ap_bar, text="（点击“状态”列循环切换 正常→故障→关闭）",
                  foreground="gray").pack(side='left', padx=8)

        self.ap_tree = self._create_point_tree(ap_tab, "ap")

        # ---------- WAC 页签 ----------
        wac_tab = ttk.Frame(self.list_nb)
        self.list_nb.add(wac_tab, text='WAC列表')
        wac_bar = ttk.Frame(wac_tab)
        wac_bar.pack(fill='x', pady=3, padx=3)
        ttk.Button(wac_bar, text="全部启用", width=8,
                   command=lambda: self.set_all_wac_enabled(True)).pack(side='left', padx=2)
        ttk.Button(wac_bar, text="全部禁用", width=8,
                   command=lambda: self.set_all_wac_enabled(False)).pack(side='left', padx=2)
        ttk.Label(wac_bar, text="批量状态:").pack(side='left', padx=(10, 2))
        for txt, v in [("正常", 0), ("故障", 1), ("关闭", 2)]:
            ttk.Button(wac_bar, text=txt, width=6,
                       command=lambda v=v: self.set_all_wac_status(v)).pack(side='left', padx=2)
        ttk.Label(wac_bar, text="（点击“状态”列循环切换 正常→故障→关闭）",
                  foreground="gray").pack(side='left', padx=8)

        self.wac_tree = self._create_point_tree(wac_tab, "wac")

        status_frame = ttk.Frame(left_frame)
        status_frame.pack(fill='x', padx=5, pady=2)
        ttk.Label(status_frame, textvariable=self.status_var).pack(side='left')

        # 右侧：日志 + UDP 设置
        log_frame = ttk.Frame(right_frame)
        log_frame.pack(fill='both', expand=True, padx=5, pady=5)
        ttk.Label(log_frame, text="运行日志", font=("Arial", 10, "bold")).pack(anchor='w')
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD,
                                                  font=("Consolas", 9), state='disabled')
        self.log_text.pack(fill='both', expand=True)

        udp_frame = ttk.Frame(right_frame)
        udp_frame.pack(fill='x', padx=5, pady=5)

        row1 = ttk.Frame(udp_frame); row1.pack(fill='x', pady=2)
        ttk.Label(row1, text="目标IP:").pack(side='left')
        ttk.Entry(row1, textvariable=self.udp_ip, width=15).pack(side='left', padx=5)
        ttk.Label(row1, text="目标端口:").pack(side='left', padx=(10, 0))
        ttk.Entry(row1, textvariable=self.udp_port, width=8).pack(side='left', padx=5)
        ttk.Label(row1, text="发送间隔(ms):").pack(side='left', padx=(10, 0))
        ttk.Entry(row1, textvariable=self.interval_ms, width=8).pack(side='left', padx=5)

        row1b = ttk.Frame(udp_frame); row1b.pack(fill='x', pady=2)
        ttk.Label(row1b, text="本机IP:").pack(side='left')
        ttk.Entry(row1b, textvariable=self.local_ip, width=15).pack(side='left', padx=5)
        ttk.Label(row1b, text="（V1.0/V3.0/V4.0/V6.0 使用）", foreground="gray").pack(side='left')

        disney_ip_frame = ttk.LabelFrame(udp_frame, text="Disney 发送配置（正线 / 试车线分别绑定本机IP，目标IP与端口共用）")
        disney_ip_frame.pack(fill='x', pady=4)
        row1d = ttk.Frame(disney_ip_frame); row1d.pack(fill='x', pady=3, padx=6)
        ttk.Label(row1d, text="本机IP(正线):").pack(side='left')
        ttk.Entry(row1d, textvariable=self.local_ip_main, width=15).pack(side='left', padx=5)
        ttk.Label(row1d, text="本机IP(试车线):").pack(side='left', padx=(12, 0))
        ttk.Entry(row1d, textvariable=self.local_ip_shd, width=15).pack(side='left', padx=5)

        row2 = ttk.Frame(udp_frame); row2.pack(fill='x', pady=2)
        ttk.Button(row2, text="发送", command=self.send_and_generate).pack(side='left', padx=2)
        ttk.Button(row2, text="复制日志", command=self.copy_log).pack(side='left', padx=2)
        ttk.Button(row2, text="查看报文预览", command=self.show_packet_preview).pack(side='left', padx=2)
        ttk.Button(row2, text="解析报文(粘贴)", command=self.parse_packet_dialog).pack(side='left', padx=2)

        row3 = ttk.Frame(udp_frame); row3.pack(fill='x', pady=2)
        self.btn_start_continuous = ttk.Button(row3, text="开始持续发送", command=self.start_continuous_send)
        self.btn_start_continuous.pack(side='left', padx=2)
        self.btn_stop_continuous = ttk.Button(row3, text="停止发送", command=self.stop_continuous_send, state="disabled")
        self.btn_stop_continuous.pack(side='left', padx=2)
        ttk.Label(row3, text="时间戳实时变化").pack(side='left', padx=8)

    # ---------- AP / WAC 列表 ----------
    def _create_point_tree(self, parent, kind):
        frame = ttk.Frame(parent)
        frame.pack(fill='both', expand=True)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        columns = ("启用", "线路", "序号", "名称", "IP地址", "所属集中区", "网络", "状态")
        tree = ttk.Treeview(frame, columns=columns, show='headings')
        for c, w in [("启用", 50), ("线路", 70), ("序号", 55), ("名称", 170),
                     ("IP地址", 110), ("所属集中区", 80), ("网络", 110), ("状态", 70)]:
            tree.heading(c, text=c)
            tree.column(c, width=w, anchor='center' if c != "名称" and c != "IP地址" and c != "网络" else 'w')
        tree.bind("<ButtonRelease-1>", lambda e, k=kind: self.on_point_tree_click(k, e))
        tree.tag_configure("st1", foreground="#C00000")   # 故障
        tree.tag_configure("st2", foreground="#7F7F7F")   # 关闭

        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.grid(row=0, column=0, sticky='nsew')
        vsb.grid(row=0, column=1, sticky='ns')
        return tree

    def _is_disney(self):
        return (self.version or self.version_var.get()) == "Disney"

    def refresh_point_trees(self):
        for tree, items in ((self.ap_tree, self.ap_list), (self.wac_tree, self.wac_list)):
            if tree is None:
                continue
            for iid in tree.get_children():
                tree.delete(iid)
            for idx, it in enumerate(items):
                st = int(it.get("status", 0))
                tags = [str(idx)] + ([f"st{st}"] if st else [])
                tree.insert("", "end",
                            values=("☑" if it.get("enabled", True) else "☐",
                                    LINE_NAME.get(it.get("line"), ""),
                                    it.get("no", ""),
                                    it.get("name", ""),
                                    it.get("ip", ""),
                                    it.get("zone", ""),
                                    it.get("net", ""),
                                    DISNEY_AP_STATUS_TEXT.get(DISNEY_AP_STATUS.get(st, 0), "")),
                            tags=tuple(tags))

    def on_point_tree_click(self, kind, event):
        tree = self.ap_tree if kind == "ap" else self.wac_tree
        items = self.ap_list if kind == "ap" else self.wac_list
        if tree is None:
            return
        region = tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col_index = int(tree.identify_column(event.x).replace("#", "")) - 1
        item = tree.identify_row(event.y)
        if not item:
            return
        tags = tree.item(item, "tags")
        if not tags:
            return
        idx = int(tags[0])
        if idx >= len(items):
            return
        it = items[idx]
        if col_index == 0:
            it["enabled"] = not it.get("enabled", True)
            tree.set(item, column="启用", value="☑" if it["enabled"] else "☐")
        elif col_index == 7:
            it["status"] = (int(it.get("status", 0)) + 1) % 3
            tree.set(item, column="状态",
                     value=DISNEY_AP_STATUS_TEXT[DISNEY_AP_STATUS[it["status"]]])
            st = it["status"]
            tree.item(item, tags=(str(idx),) + ((f"st{st}",) if st else ()))
        self._set_status(f"{'AP' if kind == 'ap' else 'WAC'} 已启用 "
                         f"{sum(1 for x in items if x.get('enabled', True))} / {len(items)} 个")

    def _set_all_point_enabled(self, items, tree, flag):
        for i, it in enumerate(items):
            it["enabled"] = flag
        if tree is not None:
            for i, item in enumerate(tree.get_children()):
                tree.set(item, column="启用", value="☑" if flag else "☐")

    def _set_all_point_status(self, items, tree, status):
        for it in items:
            it["status"] = status
        if tree is not None:
            for i, item in enumerate(tree.get_children()):
                tree.set(item, column="状态",
                         value=DISNEY_AP_STATUS_TEXT[DISNEY_AP_STATUS[status]])
                tree.item(item, tags=(str(i),) + ((f"st{status}",) if status else ()))

    def set_all_ap_enabled(self, flag):
        self._set_all_point_enabled(self.ap_list, self.ap_tree, flag)
        self._set_status(f"AP 全部{'启用' if flag else '禁用'}")

    def set_all_wac_enabled(self, flag):
        self._set_all_point_enabled(self.wac_list, self.wac_tree, flag)
        self._set_status(f"WAC 全部{'启用' if flag else '禁用'}")

    def set_all_ap_status(self, status):
        self._set_all_point_status(self.ap_list, self.ap_tree, status)
        self._log(f"AP 批量状态设置为: {DISNEY_AP_STATUS_TEXT[DISNEY_AP_STATUS[status]]}")

    def set_all_wac_status(self, status):
        self._set_all_point_status(self.wac_list, self.wac_tree, status)
        self._log(f"WAC 批量状态设置为: {DISNEY_AP_STATUS_TEXT[DISNEY_AP_STATUS[status]]}")

    # ---------- 打开拓扑图数据校验窗口 ----------
    def open_topology_check(self):
        if not TOPOLOGY_DEPS_OK:
            messagebox.showerror(
                "依赖缺失",
                f"拓扑图数据校验需要以下依赖：\n"
                f"  requests、pymysql（openpyxl 已内置）\n\n"
                f"导入错误信息：\n{TOPOLOGY_DEPS_ERROR}\n\n"
                f"请执行：pip install requests pymysql",
                parent=self)
            return

        if self._topology_window is not None:
            try:
                if self._topology_window.winfo_exists():
                    self._topology_window.lift()
                    self._topology_window.focus_force()
                    return
            except Exception:
                pass

        self._topology_window = TopologyCheckWindow(self)

    # ---------- 全局状态 ----------
    def apply_global_sw_status(self):
        sw_status = self.global_sw_var.get()
        text = SW_STATUS_TEXTS[sw_status]
        if not self.all_switches:
            self._log(f"全局整机状态预选: {text}（暂无设备）")
            return
        for sw in self.all_switches:
            no = sw["no"]
            if no in self.switch_status:
                self.switch_status[no] = (sw_status, self.switch_status[no][1])
            else:
                self.switch_status[no] = (sw_status, {})
        children = self.tree.get_children()
        for idx, sw in enumerate(self.all_switches):
            if idx < len(children):
                self.tree.set(children[idx], column="整机状态", value=text)
        self._log(f"全局整机状态已更新为: {text}")

    def apply_global_port_status(self):
        port_status = self.global_port_var.get()
        text = PORT_STATUS_TEXTS[port_status]
        if not self.all_switches:
            self._log(f"全局端口状态预选: {text}（暂无设备）")
            return
        for sw in self.all_switches:
            no = sw["no"]
            if self.version == 'Disney':
                ports = list(range(1, int(sw.get("total_ports", 0)) + 1))
            elif self.version in ('V3.0', 'V4.0', 'V6.0'):
                ports = [p['port_id'] for p in sw['ports']]
            else:
                ports = list(self.port_mapping.get(no, {}).keys())
            if not ports:
                continue
            port_dict = {p: port_status for p in ports}
            if no in self.switch_status:
                self.switch_status[no] = (self.switch_status[no][0], port_dict)
            else:
                self.switch_status[no] = (0, port_dict)
        self._log(f"全局统一端口状态已更新为: {text}")

    # ---------- 文件选择 ----------
    def _build_file_selectors(self):
        for w in self.file_frame.winfo_children():
            w.destroy()
        version = self.version_var.get()

        def add_row(label, var, cmd):
            r = ttk.Frame(self.file_frame); r.pack(fill='x', pady=1)
            ttk.Label(r, text=label, width=10).pack(side='left')
            ttk.Entry(r, textvariable=var, width=42).pack(side='left', padx=5)
            ttk.Button(r, text="浏览...", command=cmd).pack(side='left')

        if version == "Disney":
            add_row("配置文件:", self.data_file, self.select_data_file)
            add_row("映射文件:", self.mapping_file, self.select_mapping_file)
            add_row("AP点表:", self.ap_file, self.select_ap_file)
            add_row("WAC点表:", self.wac_file, self.select_wac_file)
        elif version == "V1.0":
            add_row("配置文件:", self.data_file, self.select_data_file)
            add_row("映射文件:", self.mapping_file, self.select_mapping_file)
        else:
            add_row("数据文件:", self.data_file, self.select_data_file)

    def select_data_file(self):
        version = self.version_var.get()
        if version == "Disney":
            title = "选择交换机配置文件（NEConfigData）"
        elif version == "V1.0":
            title = "选择交换机配置文件（NEConfigData）"
        else:
            title = "选择数据文件（NMSConfig）"
        file = filedialog.askopenfilename(
            title=title,
            filetypes=[("Excel 文件", "*.xlsx *.xlsm *.xls"), ("所有文件", "*.*")])
        if file:
            self.data_file.set(file)
            if version in ("V1.0", "Disney"):
                self._try_load_when_ready()
            else:
                self.load_data()

    def select_mapping_file(self):
        file = filedialog.askopenfilename(
            title="选择端口映射文件",
            filetypes=[("Excel 文件", "*.xlsx *.xlsm *.xls"), ("所有文件", "*.*")])
        if file:
            self.mapping_file.set(file)
            self._try_load_when_ready()

    def select_ap_file(self):
        file = filedialog.askopenfilename(
            title="选择 AP 点表",
            filetypes=[("Excel 文件", "*.xlsx *.xlsm *.xls"), ("所有文件", "*.*")])
        if file:
            self.ap_file.set(file)
            self._try_load_when_ready()

    def select_wac_file(self):
        file = filedialog.askopenfilename(
            title="选择 WAC 点表",
            filetypes=[("Excel 文件", "*.xlsx *.xlsm *.xls"), ("所有文件", "*.*")])
        if file:
            self.wac_file.set(file)
            self._try_load_when_ready()

    def _try_load_when_ready(self):
        v = self.version_var.get()
        if v == "Disney":
            if self.data_file.get() and self.mapping_file.get() and self.ap_file.get() and self.wac_file.get():
                self.load_data()
            else:
                miss = []
                if not self.data_file.get():
                    miss.append("配置文件")
                if not self.mapping_file.get():
                    miss.append("映射文件")
                if not self.ap_file.get():
                    miss.append("AP点表")
                if not self.wac_file.get():
                    miss.append("WAC点表")
                self._set_status("请继续选择：" + "、".join(miss))
        else:
            if self.data_file.get() and self.mapping_file.get():
                self.load_data()
            else:
                self._set_status("请继续选择映射文件" if self.data_file.get() else "请继续选择配置文件")

    def on_version_changed(self, event=None):
        self._build_file_selectors()
        self.all_switches = []
        self.port_mapping = {}
        self.ap_list = []
        self.wac_list = []
        self.selected_indices.clear()
        self.switch_status.clear()
        self.refresh_tree()
        self.refresh_point_trees()
        self.version = None
        self._set_status("已切换版本，请选择文件后加载")

    # ---------- 日志 ----------
    def _log(self, message):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            self.log_text.configure(state='normal')
            self.log_text.insert(tk.END, f"[{ts}] {message}\n")
            self._log_line_count += 1
            if self._log_line_count > self.LOG_MAX_LINES:
                drop = self._log_line_count - self.LOG_MAX_LINES
                self.log_text.delete("1.0", f"{drop + 1}.0")
                self._log_line_count = self.LOG_MAX_LINES
            self.log_text.see(tk.END)
            self.log_text.configure(state='disabled')
        except Exception:
            pass

    def _set_status(self, text):
        if text != self._last_status_text:
            self._last_status_text = text
            self.status_var.set(text)

    # ---------- 网络发送 ----------
    def _create_send_socket(self):
        return self._create_socket_bound(self.local_ip.get().strip())

    def _create_socket_bound(self, local_ip):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if local_ip:
            sock.bind((local_ip, 0))
        return sock

    def _open_disney_sockets(self):
        self._close_disney_sockets()
        ip_main = self.local_ip_main.get().strip()
        ip_shd = self.local_ip_shd.get().strip()
        self._send_sock_main = self._create_socket_bound(ip_main)
        try:
            self._send_sock_shd = self._create_socket_bound(ip_shd)
        except Exception:
            try:
                self._send_sock_main.close()
            except Exception:
                pass
            self._send_sock_main = None
            raise

    def _close_disney_sockets(self):
        for attr in ("_send_sock_main", "_send_sock_shd"):
            s = getattr(self, attr, None)
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
                setattr(self, attr, None)

    def _open_continuous_socket(self):
        self._close_send_socket()
        try:
            self._send_sock = self._create_send_socket()
        except Exception as e:
            self._send_sock = None
            raise e

    def _close_send_socket(self):
        if self._send_sock is not None:
            try:
                self._send_sock.close()
            except Exception:
                pass
            self._send_sock = None

    def _build_packet(self):
        if not self.selected_indices:
            raise ValueError("请至少选择一台交换机")
        if self._is_disney():
            raise ValueError("Disney 版本为双线路报文，请使用“发送 / 预览”，不能单独生成单包")
        selected = [self.all_switches[i] for i in sorted(self.selected_indices)]
        custom = {}
        for sw in selected:
            no = sw["no"]
            custom[no] = self.switch_status.get(no, (0, {}))

        if self.version == 'V6.0':
            packet, _, _ = build_packet_v6(selected, custom, self.v6_config)
        elif self.version == 'V4.0':
            packet, _, _ = build_packet_v4(selected, custom, self.v6_config)
        elif self.version == 'V3.0':
            packet, _ = build_packet_v2(selected, custom)
        else:
            packet, _ = build_packet_v1(selected, self.port_mapping, custom)
        return packet

    # ---------- Disney 双线路组包 ----------
    def _collect_disney_line(self, line):
        sws = [self.all_switches[i] for i in sorted(self.selected_indices)
               if self.all_switches[i].get("line", LINE_MAIN) == line]
        aps = [a for a in self.ap_list if a.get("line", LINE_MAIN) == line and a.get("enabled", True)]
        wacs = [w for w in self.wac_list if w.get("line", LINE_MAIN) == line and w.get("enabled", True)]
        custom = {sw["no"]: self.switch_status.get(sw["no"], (0, {})) for sw in sws}
        return sws, aps, wacs, custom

    def _build_disney_packets(self):
        """生成 {'main': (packet, info, sws), 'test': (...)}"""
        if not self.selected_indices:
            raise ValueError("请至少选择一台交换机（正线 / 试车线）")
        if not self.ap_list and not self.wac_list:
            raise ValueError("AP / WAC 列表为空，请先加载 AP点表 与 WAC点表")

        result = {}
        for line in (LINE_MAIN, LINE_TEST):
            sws, aps, wacs, custom = self._collect_disney_line(line)
            if not sws and not aps and not wacs:
                continue
            if line == LINE_TEST:
                nms_index = int(self.disney_config.get("nms_index_test", 1))
            else:
                nms_index = int(self.disney_config.get("nms_index_main", 0))
            packet, info = build_packet_disney(
                sws, self.port_mapping, aps, wacs, custom,
                nms_index=nms_index,
                pad_blocks=bool(self.disney_config.get("pad_blocks", True)))
            info["line"] = line
            result[line] = (packet, info, sws)
        if not result:
            raise ValueError("没有可发送的数据（请检查交换机选择与 AP/WAC 启用状态）")
        return result

    def _check_disney_targets(self):
        ip_main = self.local_ip_main.get().strip()
        ip_shd = self.local_ip_shd.get().strip()
        if not ip_main or not ip_shd:
            missing = []
            if not ip_main:
                missing.append("正线")
            if not ip_shd:
                missing.append("试车线")
            raise ValueError("Disney 版本必须配置两个本机IP：" + "、".join(missing) + " 的本机IP为空")
        target_ip = self.udp_ip.get().strip()
        if not target_ip:
            raise ValueError("目标 IP 为空")
        try:
            target_port = int(self.udp_port.get().strip())
            if not (0 < target_port < 65536):
                raise ValueError("端口超出范围")
        except ValueError as e:
            raise ValueError(f"无效的端口号: {e}")
        return ip_main, ip_shd, target_ip, target_port

    def _send_disney_once(self):
        """同时发送正线、试车线两包，返回 (ok, 描述文本)"""
        packets = self._build_disney_packets()
        ip_main, ip_shd, target_ip, target_port = self._check_disney_targets()
        ip_map = {LINE_MAIN: ip_main, LINE_TEST: ip_shd}

        msgs = []
        ok_all = True
        for line in (LINE_MAIN, LINE_TEST):
            if line not in packets:
                continue
            packet, info, _ = packets[line]
            local_ip = ip_map[line]
            sock = None
            try:
                sock = self._create_socket_bound(local_ip)
                sock.sendto(packet, (target_ip, target_port))
                msgs.append(f"{LINE_NAME[line]}({local_ip}) {len(packet)}字节 发送成功")
            except Exception as e:
                ok_all = False
                msgs.append(f"{LINE_NAME[line]}({local_ip}) 发送失败: {e}")
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except Exception:
                        pass
        self.disney_packets = packets
        return ok_all, "；".join(msgs)

    def _send_udp(self, packet, sock=None):
        target_ip = self.udp_ip.get().strip()
        if not target_ip:
            return False, "目标 IP 为空"
        try:
            target_port = int(self.udp_port.get().strip())
            if not (0 < target_port < 65536):
                raise ValueError("端口超出范围")
        except ValueError as e:
            return False, f"无效的端口号: {e}"

        own_sock = sock is None
        if own_sock:
            try:
                sock = self._create_send_socket()
            except Exception as e:
                return False, f"创建套接字失败: {e}"
        try:
            sock.sendto(packet, (target_ip, target_port))
            return True, f"已发送 {len(packet)} 字节到 {target_ip}:{target_port}"
        except Exception as e:
            if not own_sock:
                self._close_send_socket()
            return False, str(e)
        finally:
            if own_sock:
                try:
                    sock.close()
                except Exception:
                    pass

    # ---------- 加载数据 ----------
    def find_sheet(self, file_path, name_list):
        try:
            sheets = _get_excel_sheet_names(file_path)
            for pattern in name_list:
                for s in sheets:
                    if pattern in s:
                        return s
            return None
        except Exception:
            return None

    def select_sheet_dialog(self, sheet_list, prompt, default=None):
        win = Toplevel(self)
        win.title("选择工作表")
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text=prompt, wraplength=350).pack(pady=10)
        listbox = tk.Listbox(win, height=10)
        listbox.pack(fill='both', expand=True, padx=10, pady=5)
        for s in sheet_list:
            listbox.insert(tk.END, s)
        if default and default in sheet_list:
            listbox.selection_set(sheet_list.index(default))
        selected = [None]

        def on_ok():
            sel = listbox.curselection()
            if sel:
                selected[0] = listbox.get(sel[0])
                win.destroy()
            else:
                messagebox.showinfo("提示", "请选择一个工作表", parent=win)

        btn_frame = ttk.Frame(win)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="确定", command=on_ok).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side='left', padx=5)
        self._center_window(win, 400, 300)
        self.wait_window(win)
        return selected[0]

    def load_data(self):
        if self._loading:
            return
        self._loading = True
        try:
            version = self.version_var.get()

            if version == "Disney":
                self._load_disney_data()
                return

            if version in ("V3.0", "V4.0", "V6.0"):
                file_path = self.data_file.get().strip()
                if not file_path:
                    self._set_status("请选择数据文件")
                    return
                if not os.path.exists(file_path):
                    messagebox.showerror("错误", "所选文件不存在", parent=self)
                    return
                try:
                    sheets = _get_excel_sheet_names(file_path)
                except Exception as e:
                    messagebox.showerror("错误", f"无法读取文件: {e}", parent=self)
                    return
                if not any('NMSConfig' in s for s in sheets):
                    messagebox.showerror("错误", "所选文件未包含 'NMSConfig' 工作表", parent=self)
                    return

                self.all_switches = load_switches_from_neconfig_v2(file_path)
                self.version = version
                self.port_mapping = {}
                for sw in self.all_switches:
                    self.port_mapping[sw['no']] = {p['port_id']: p['dev'] for p in sw['ports']}
                self.selected_indices.clear()
                self.switch_status.clear()
                self.refresh_tree()
                total = sum(len(sw['ports']) for sw in self.all_switches)
                msg = f"加载成功 ({version}): {len(self.all_switches)} 台交换机, {total} 个配置端口"
                self._set_status(msg)
                self._log(msg)
                self.select_all()
                return

            config_file = self.data_file.get().strip()
            mapping_file = self.mapping_file.get().strip()
            if not config_file:
                self._set_status("请选择配置文件")
                return
            if not mapping_file:
                self._set_status("请选择映射文件")
                return
            if not os.path.exists(config_file):
                messagebox.showerror("错误", "配置文件不存在", parent=self)
                return
            if not os.path.exists(mapping_file):
                messagebox.showerror("错误", "映射文件不存在", parent=self)
                return

            sheet_ne = self.find_sheet(config_file, CONFIG_SHEET_NAMES)
            if sheet_ne is None:
                sheet_ne = self.select_sheet_dialog(_get_excel_sheet_names(config_file),
                                                    "未匹配到交换机配置Sheet，请手动选择")
                if sheet_ne is None:
                    return

            sheet_rel = self.find_sheet(mapping_file, MAPPING_SHEET_NAMES)
            if sheet_rel is None:
                sheet_rel = self.select_sheet_dialog(_get_excel_sheet_names(mapping_file),
                                                     "未匹配到端口映射Sheet，请手动选择")
                if sheet_rel is None:
                    return

            self.all_switches = load_switches_from_neconfig_v1(config_file, sheet_ne)
            self.port_mapping = load_port_mapping_v1(mapping_file, sheet_rel)
            self.version = 'V1.0'
            self.selected_indices.clear()
            self.switch_status.clear()
            self.refresh_tree()
            msg = (f"加载成功 (V1.0): {len(self.all_switches)} 台交换机, "
                   f"{sum(len(v) for v in self.port_mapping.values())} 条端口映射")
            
            self._set_status(msg)
            self._log(msg)
            self.select_all()
        except Exception as e:
            messagebox.showerror("加载失败", str(e), parent=self)
            self._log(f"加载失败: {e}")
        finally:
            self._loading = False

    def _load_disney_data(self):
        cfg_file = self.data_file.get().strip()
        map_file = self.mapping_file.get().strip()
        ap_file = self.ap_file.get().strip()
        wac_file = self.wac_file.get().strip()

        for label, path in (("配置文件", cfg_file), ("映射文件", map_file),
                            ("AP点表", ap_file), ("WAC点表", wac_file)):
            if not path:
                self._set_status(f"请选择{label}")
                return
            if not os.path.exists(path):
                messagebox.showerror("错误", f"{label}不存在：\n{path}", parent=self)
                return

        sheet_ne = self.find_sheet(cfg_file, DISNEY_SWITCH_SHEET_NAMES)
        if sheet_ne is None:
            sheet_ne = self.select_sheet_dialog(get_sheet_names_any(cfg_file),
                                                "未匹配到交换机配置Sheet，请手动选择")
            if sheet_ne is None:
                return

        sheet_rel = self.find_sheet(map_file, MAPPING_SHEET_NAMES)
        if sheet_rel is None:
            sheet_rel = self.select_sheet_dialog(get_sheet_names_any(map_file),
                                                 "未匹配到端口映射Sheet，请手动选择")
            if sheet_rel is None:
                return

        # 交换机 + 端口映射（与 V1.0 相同的数据来源）
        switches = load_switches_disney(cfg_file, sheet_ne)
        port_mapping = load_port_mapping_v1(map_file, sheet_rel)

        # AP / WAC 点表（正线、试车线分别读取）
        ap_list, wac_list = [], []
        warn = []
        for line in (LINE_MAIN, LINE_TEST):
            ap_sheets = pick_point_sheets(ap_file, line, "AP")
            if not ap_sheets:
                warn.append(f"AP点表缺少{LINE_NAME[line]}工作表")
            for sh in ap_sheets:
                for it in load_point_table(ap_file, "AP", sh):
                    it["line"] = line
                    it.setdefault("status", 0)
                    it.setdefault("enabled", True)
                    ap_list.append(it)

            wac_sheets = pick_point_sheets(wac_file, line, "WAC")
            if not wac_sheets:
                warn.append(f"WAC点表缺少{LINE_NAME[line]}工作表")
            for sh in wac_sheets:
                for it in load_point_table(wac_file, "WAC", sh):
                    it["line"] = line
                    it.setdefault("status", 0)
                    it.setdefault("enabled", True)
                    wac_list.append(it)

        if not ap_list:
            raise ValueError("未从 AP点表 解析到任何 AP，请检查表头（序号 / AP名称 / IP地址 / 所属集中区 / 网络）")
        if not wac_list:
            raise ValueError("未从 WAC点表 解析到任何 WAC，请检查表头（序号 / WAC名称 / IP地址 / 所属集中区 / 网络）")

        self.all_switches = switches
        self.port_mapping = port_mapping
        self.ap_list = ap_list
        self.wac_list = wac_list
        self.version = "Disney"
        self.selected_indices.clear()
        self.switch_status.clear()

        # 默认 NMS 编号取配置表中该线路第一台交换机的 NMSNO
        for line, key in ((LINE_MAIN, "nms_index_main"), (LINE_TEST, "nms_index_test")):
            nos = [sw.get("nmsno", 0) for sw in switches if sw.get("line") == line]
            if nos:
                self.disney_config[key] = int(nos[0])

        self.refresh_tree()
        self.refresh_point_trees()

        n_main = sum(1 for s in switches if s["line"] == LINE_MAIN)
        n_test = sum(1 for s in switches if s["line"] == LINE_TEST)
        ap_main = sum(1 for a in ap_list if a["line"] == LINE_MAIN)
        ap_test = sum(1 for a in ap_list if a["line"] == LINE_TEST)
        wac_main = sum(1 for w in wac_list if w["line"] == LINE_MAIN)
        wac_test = sum(1 for w in wac_list if w["line"] == LINE_TEST)

        msg = (f"加载成功 (Disney)：交换机 {len(switches)} 台"
               f"（正线{n_main}/试车线{n_test}），AP {len(ap_list)} 个"
               f"（正线{ap_main}/试车线{ap_test}），WAC {len(wac_list)} 个"
               f"（正线{wac_main}/试车线{wac_test}）")
        self._set_status(msg)
        self._log(msg)
        for w in warn:
            self._log(f"注意: {w}")
        self.select_all()

    def refresh_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, sw in enumerate(self.all_switches):
            sw_status_str = "正常"
            if idx in self.selected_indices and sw["no"] in self.switch_status:
                sw_status_str = SW_STATUS_TEXTS[self.switch_status[sw["no"]][0]]
            if self.version in ('V3.0', 'V4.0', 'V6.0'):
                port_count = len(sw.get('ports', []))
            else:
                port_count = sw.get('total_ports', 0)
            self.tree.insert("", "end",
                             values=("☐", sw["no"], sw["hostname"], sw["station"],
                                     port_count, sw_status_str, "设置端口"),
                             tags=(str(idx),))

    def on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col_index = int(self.tree.identify_column(event.x).replace("#", "")) - 1
        item = self.tree.identify_row(event.y)
        if not item:
            return
        idx = int(self.tree.item(item, "tags")[0])
        sw = self.all_switches[idx]
        no = sw["no"]

        if col_index == 0:
            if idx in self.selected_indices:
                self.selected_indices.remove(idx)
                self.tree.set(item, column="选择", value="☐")
            else:
                self.selected_indices.add(idx)
                self.tree.set(item, column="选择", value="☑")
                if no not in self.switch_status:
                    self.switch_status[no] = (self.global_sw_var.get(), {})
            self._set_status(f"已选择 {len(self.selected_indices)} 台设备")
        elif col_index == 5:
            if idx not in self.selected_indices:
                messagebox.showinfo("提示", "请先选中该设备", parent=self)
                return
            self.open_sw_status_menu(idx)
        elif col_index == 6:
            if idx not in self.selected_indices:
                messagebox.showinfo("提示", "请先选中该设备", parent=self)
                return
            self.open_port_settings(idx)

    def open_sw_status_menu(self, idx):
        sw = self.all_switches[idx]
        no = sw["no"]
        current = self.switch_status.get(no, (0, {}))[0] if no in self.switch_status else 0

        win = Toplevel(self)
        win.title(f"整机状态设置 - {no} {sw['hostname']}")
        win.transient(self)
        win.grab_set()

        var = tk.IntVar(value=current)
        frame = ttk.Frame(win); frame.pack(fill='both', expand=True, padx=15, pady=12)
        ttk.Label(frame, text=f"交换机 {no} ({sw['hostname']})：",
                  font=("Arial", 10, "bold")).pack(anchor='w', pady=(0, 8))
        row = ttk.Frame(frame); row.pack(fill='x')
        for text, val in [("整机故障", 1), ("高负载", 2), ("端口异常", 3), ("正常", 0)]:
            ttk.Radiobutton(row, text=text, variable=var, value=val).pack(side='left', padx=6)

        def save():
            st = var.get()
            if no in self.switch_status:
                self.switch_status[no] = (st, self.switch_status[no][1])
            else:
                self.switch_status[no] = (st, {})
            self.tree.set(self.tree.get_children()[idx], column="整机状态",
                          value=SW_STATUS_TEXTS[st])
            win.destroy()

        btn = ttk.Frame(frame); btn.pack(pady=10)
        ttk.Button(btn, text="确定", command=save).pack(side='left', padx=5)
        ttk.Button(btn, text="取消", command=win.destroy).pack(side='left', padx=5)
        self._center_window(win, 360, 140)

    def open_port_settings(self, idx):
        sw = self.all_switches[idx]
        no = sw["no"]
        if self.version == 'Disney':
            dev_map = self.port_mapping.get(no, {})
            mapped_ports = list(range(1, int(sw.get("total_ports", 0)) + 1))
            port_dev_map = {p: dev_map.get(p, "") for p in mapped_ports}
        elif self.version in ('V3.0', 'V4.0', 'V6.0'):
            mapped_ports = sorted([p['port_id'] for p in sw['ports']])
            port_dev_map = {p['port_id']: p['dev'] for p in sw['ports']}
        else:
            mapped_ports = sorted(self.port_mapping.get(no, {}).keys())
            port_dev_map = self.port_mapping.get(no, {})
        if not mapped_ports:
            messagebox.showinfo("提示", f"交换机 {no} 没有配置端口", parent=self)
            return

        current = self.switch_status.get(no, (0, {}))[1] if no in self.switch_status else {}

        win = Toplevel(self)
        win.title(f"端口状态设置 - {no} {sw['hostname']}")
        win.transient(self)
        win.grab_set()

        top_bar = ttk.Frame(win); top_bar.pack(fill='x', padx=10, pady=6)
        ttk.Label(top_bar, text="点击后立即生效", foreground="gray").pack(side='left')

        outer = ttk.Frame(win); outer.pack(fill='both', expand=True, padx=10, pady=5)
        outer.rowconfigure(0, weight=1); outer.columnconfigure(0, weight=1)
        canvas = tk.Canvas(outer, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky='nsew')
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        sb.grid(row=0, column=1, sticky='ns')
        canvas.configure(yscrollcommand=sb.set)

        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        def set_port_status(port_id, value):
            if no not in self.switch_status:
                self.switch_status[no] = (0, {})
            sw_st, pd_ = self.switch_status[no]
            pd_[port_id] = value
            self.switch_status[no] = (sw_st, pd_)

        for p in mapped_ports:
            row = ttk.Frame(inner); row.pack(fill='x', pady=3, padx=5)
            dev = port_dev_map.get(p, "未知设备")
            ttk.Label(row, text=f"端口 {p}（{dev}）:", width=22, anchor='w').pack(side='left', padx=5)
            var = tk.IntVar(value=current.get(p, 0))
            for text, val in [("故障", 1), ("超标", 2), ("正常", 0)]:
                ttk.Radiobutton(row, text=text, variable=var, value=val,
                                command=lambda pid=p, v=var: set_port_status(pid, v.get())
                                ).pack(side='left', padx=5)

        btn_frame = ttk.Frame(win); btn_frame.pack(pady=8)
        ttk.Button(btn_frame, text="完成",
                   command=lambda: self._close_port_settings(win, no)).pack(side='left', padx=5)
        win.protocol("WM_DELETE_WINDOW", lambda: self._close_port_settings(win, no))
        self._center_window(win, 560, 520)

    def _close_port_settings(self, win, no):
        try:
            win.grab_release()
        except Exception:
            pass
        try:
            win.unbind_all("<MouseWheel>")
        except Exception:
            pass
        try:
            win.destroy()
        except Exception:
            pass
        self._log(f"交换机 {no} 端口状态已保存（实时生效）")

    def select_all(self):
        for idx in range(len(self.all_switches)):
            self.selected_indices.add(idx)
            self.tree.set(self.tree.get_children()[idx], column="选择", value="☑")
            no = self.all_switches[idx]["no"]
            if no not in self.switch_status:
                self.switch_status[no] = (self.global_sw_var.get(), {})
        self._set_status(f"已选择 {len(self.selected_indices)} 台设备")

    def deselect_all(self):
        self.selected_indices.clear()
        for idx in range(len(self.all_switches)):
            self.tree.set(self.tree.get_children()[idx], column="选择", value="☐")
        self._set_status("已取消所有选择")

    # ---------- 参数设置 ----------
    def v6_parameter_setting(self):
        win = Toplevel(self)
        win.title("V6.0参数设置")
        win.transient(self)
        win.grab_set()
        frame = ttk.Frame(win); frame.pack(fill='both', expand=True, padx=15, pady=12)
        fields = [
            ("CPU高负载阈值(%)", "cpu_threshold", 80),
            ("业务端口流量上限(Kbit/s)", "service_port_speed", 50000),
            ("非业务端口流量上限(Kbit/s)", "non_service_port_speed", 5000),
            ("内存使用率最小值(%)", "memory_min", 0),
            ("内存使用率最大值(%)", "memory_max", 100),
            ("传输时延最小值", "trans_delay_min", 0),
            ("传输时延最大值", "trans_delay_max", 5),
            ("丢包率最小值", "packet_loss_min", 0),
            ("丢包率最大值", "packet_loss_max", 5),
            ("误码率最小值", "bit_error_min", 0),
            ("误码率最大值", "bit_error_max", 5),
            ("端口带宽使用率最小值(%)", "bandwidth_min", 0),
            ("端口带宽使用率最大值(%)", "bandwidth_max", 100)
        ]
        vars = {}
        for r, (label, key, default) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=r, column=0, sticky='w', pady=3)
            v = tk.StringVar(value=str(self.v6_config.get(key, default)))
            vars[key] = v
            ttk.Entry(frame, textvariable=v, width=16).grid(row=r, column=1, padx=8, pady=3)

        def save():
            try:
                vals = {k: int(v.get().strip()) for k, v in vars.items()}
                if not 0 <= vals['cpu_threshold'] <= 100:
                    raise ValueError('CPU阈值必须为0~100')
                if not 0 <= vals['memory_min'] <= vals['memory_max'] <= 100:
                    raise ValueError('内存范围无效')
                if not 0 <= vals['bandwidth_min'] <= vals['bandwidth_max'] <= 100:
                    raise ValueError('带宽范围无效')
                for a, b in [('trans_delay_min', 'trans_delay_max'),
                             ('packet_loss_min', 'packet_loss_max'),
                             ('bit_error_min', 'bit_error_max')]:
                    if vals[a] < 0 or vals[a] > vals[b]:
                        raise ValueError(f'{a}、{b}范围无效')
                self.v6_config.update(vals)
                win.destroy()
                self._log('V6.0参数设置已保存')
                messagebox.showinfo('成功', 'V6.0参数设置已保存', parent=self)
            except Exception as e:
                messagebox.showerror('参数错误', str(e), parent=win)

        ttk.Button(frame, text='保存', command=save).grid(row=len(fields), column=0, pady=12)
        ttk.Button(frame, text='取消', command=win.destroy).grid(row=len(fields), column=1, pady=12)
        self._center_window(win, 460, 430)

    def v4_parameter_setting(self):
        win = Toplevel(self)
        win.title("V4.0参数设置")
        win.transient(self)
        win.grab_set()
        frame = ttk.Frame(win); frame.pack(fill='both', expand=True, padx=15, pady=12)
        fields = [
            ("CPU高负载阈值(%)  0~100", "cpu_threshold", 80),
            ("业务端口流量超限值(Kbit/s)  0~4294967295", "service_port_speed", 50000),
            ("非业务端口流量超限值(Kbit/s)  0~4294967295", "non_service_port_speed", 5000),
            ("端口带宽使用率最小值(%)  0~100", "bandwidth_min", 0),
            ("端口带宽使用率最大值(%)  0~100", "bandwidth_max", 100),
        ]
        vars = {}
        for r, (label, key, default) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=r, column=0, sticky='w', pady=4)
            v = tk.StringVar(value=str(self.v6_config.get(key, default)))
            vars[key] = v
            ttk.Entry(frame, textvariable=v, width=20).grid(row=r, column=1, padx=8, pady=4)

        def save():
            try:
                vals = {k: int(v.get().strip()) for k, v in vars.items()}
                if not 0 <= vals['cpu_threshold'] <= 100:
                    raise ValueError('CPU阈值必须为0~100')
                if not 0 <= vals['service_port_speed'] <= 0xFFFFFFFF:
                    raise ValueError('业务端口流量超限值必须为0~4294967295')
                if not 0 <= vals['non_service_port_speed'] <= 0xFFFFFFFF:
                    raise ValueError('非业务端口流量超限值必须为0~4294967295')
                if not 0 <= vals['bandwidth_min'] <= vals['bandwidth_max'] <= 100:
                    raise ValueError('带宽使用率范围无效(0~100且 min<=max)')
                self.v6_config.update(vals)
                win.destroy()
                self._log('V4.0参数设置已保存')
                messagebox.showinfo('成功', 'V4.0参数设置已保存', parent=self)
            except Exception as e:
                messagebox.showerror('参数错误', str(e), parent=win)

        ttk.Button(frame, text='保存', command=save).grid(row=len(fields), column=0, pady=15)
        ttk.Button(frame, text='取消', command=win.destroy).grid(row=len(fields), column=1, pady=15)
        self._center_window(win, 500, 260)

    def disney_parameter_setting(self):
        win = Toplevel(self)
        win.title("Disney 参数设置")
        win.transient(self)
        win.grab_set()
        frame = ttk.Frame(win); frame.pack(fill='both', expand=True, padx=15, pady=12)

        ttk.Label(frame, text="NMS编号（NMS_INDEX）",
                  font=("Arial", 9, "bold")).grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 4))
        ttk.Label(frame, text="正线 NMS_INDEX (0~255):").grid(row=1, column=0, sticky='w', pady=3)
        v_main = tk.StringVar(value=str(self.disney_config.get("nms_index_main", 0)))
        ttk.Entry(frame, textvariable=v_main, width=16).grid(row=1, column=1, padx=8, pady=3)
        ttk.Label(frame, text="试车线 NMS_INDEX (0~255):").grid(row=2, column=0, sticky='w', pady=3)
        v_test = tk.StringVar(value=str(self.disney_config.get("nms_index_test", 1)))
        ttk.Entry(frame, textvariable=v_test, width=16).grid(row=2, column=1, padx=8, pady=3)

        ttk.Label(frame, text="（默认取配置表 NMSNO：正线 0 / 试车线 1）",
                  foreground="gray").grid(row=3, column=0, columnspan=2, sticky='w')

        ttk.Separator(frame, orient=HORIZONTAL).grid(row=4, column=0, columnspan=2, sticky='ew', pady=8)
        pad_var = tk.BooleanVar(value=bool(self.disney_config.get("pad_blocks", True)))
        ttk.Checkbutton(frame, text="AP / AC 状态段不足整字节时补 0（对齐到整字节，协议要求）",
                        variable=pad_var).grid(row=5, column=0, columnspan=2, sticky='w', pady=3)
        ttk.Label(frame, text="如 AP 数量×2bit 不是 8 的整数倍，则在 AP 段末尾补 0；AC 段同理",
                  foreground="gray").grid(row=6, column=0, columnspan=2, sticky='w')

        def save():
            try:
                m = int(v_main.get().strip())
                t = int(v_test.get().strip())
                if not (0 <= m <= 255 and 0 <= t <= 255):
                    raise ValueError("NMS_INDEX 必须在 0~255 之间")
                self.disney_config["nms_index_main"] = m
                self.disney_config["nms_index_test"] = t
                self.disney_config["pad_blocks"] = bool(pad_var.get())
                win.destroy()
                self._log(f"Disney 参数已保存：正线NMS={m}，试车线NMS={t}，补位={self.disney_config['pad_blocks']}")
            except Exception as e:
                messagebox.showerror("参数错误", str(e), parent=win)

        btn = ttk.Frame(frame); btn.grid(row=7, column=0, columnspan=2, pady=12)
        ttk.Button(btn, text="保存", command=save).pack(side='left', padx=6)
        ttk.Button(btn, text="取消", command=win.destroy).pack(side='left', padx=6)
        self._center_window(win, 560, 300)

    # ---------- 显示辅助 ----------
    def _v6_status_text(self, v):
        return {0:"正常",1:"整机故障",2:"高负载",3:"端口异常"}.get(v,"未知")
    def _v6_optical_text(self, v):
        return {0:"正常",1:"发射功率异常",2:"接收功率异常",3:"收发功率均异常"}.get(v,"未知")
    def _v6_break_text(self, v):
        return "断链" if v == 6 else "正常"
    def _v6_power_text(self, v):
        p1, p2 = (v >> 4) & 0x0F, v & 0x0F
        t = lambda x: {0:"正常",1:"故障",2:"未安装"}.get(x,"未知")
        return f"电源1={t(p1)}, 电源2={t(p2)}"
    def _v6_port_status_text(self, v):
        return {0:"正常",1:"故障",2:"超标"}.get(v,"未知")
    def _v6_hex(self, v, l):
        return " ".join(f"{b:02X}" for b in v.to_bytes(l, byteorder="big"))
    def _v6_hex_list(self, vs):
        return " ".join(f"{int(x) & 0xFF:02X}" for x in vs)
    def _v6_hex_list_u16(self, vs):
        out = []
        for v in vs:
            out.append(f"{(int(v) >> 8) & 0xFF:02X}")
            out.append(f"{int(v) & 0xFF:02X}")
        return " ".join(out)
    def _v6_hex_list_u32(self, vs):
        out = []
        for v in vs:
            out.extend([f"{(int(v) >> 24) & 0xFF:02X}", f"{(int(v) >> 16) & 0xFF:02X}",
                        f"{(int(v) >> 8) & 0xFF:02X}", f"{int(v) & 0xFF:02X}"])
        return " ".join(out)
    def _v6_port_summary(self, ports):
        n = f = o = 0
        for p in ports:
            s = p["status"]
            if s == 0: n += 1
            elif s == 1: f += 1
            elif s == 2: o += 1
        return n, f, o
    def _v1_status_text(self, v):
        return {0:"正常",1:"整机故障",2:"高负载",3:"端口异常"}.get(v,"未知")
    def _v1_port_status_text(self, v):
        return {0:"正常",1:"故障",2:"超标"}.get(v,"未知")

    # ---------- 报文预览 ----------
    def show_packet_preview(self):
        if self._is_disney():
            self._show_disney_preview()
            return
        try:
            packet, infos, meta = self._build_packet_detail()
        except Exception as e:
            messagebox.showerror("预览失败", str(e), parent=self)
            return
        if self.preview_window is not None and self.preview_window.winfo_exists():
            self.preview_window.destroy()
        win = Toplevel(self)
        self.preview_window = win
        win.title("报文预览 - " + str(self.version or self.version_var.get()))
        win.transient(self)

        def close_preview():
            self.preview_window = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", close_preview)

        top = ttk.Frame(win); top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text=f"版本：{self.version or self.version_var.get()}    报文长度：{len(packet)} 字节").pack(side="left")
        ttk.Button(top, text="刷新预览", command=lambda: self._refresh_preview(win)).pack(side="right")

        text = scrolledtext.ScrolledText(win, wrap=tk.NONE, font=("Consolas", 10))
        text.pack(fill="both", expand=True, padx=8, pady=8)
        text.insert("end", "#============================================================#\n")
        text.insert("end", "#                    完整十六进制报文                        #\n")
        text.insert("end", "#============================================================#\n")
        text.insert("end", " ".join(f"{b:02X}" for b in packet) + "\n\n")

        if self.version == "V6.0":
            self._preview_v6(text, packet, infos, meta)
        elif self.version == "V4.0":
            self._preview_v4(text, packet, infos, meta)
        elif self.version == "V1.0":
            self._preview_v1(text, packet, infos, meta)
        else:
            text.insert("end", "#【字段说明】#\n")
            text.insert("end", f"#起始标志：AA#\n")
            text.insert("end", f"#帧长度字段：{int.from_bytes(packet[1:3], 'big')}#\n")
            text.insert("end", f"#消息类型：{packet[7]:02X}#\n")
            text.insert("end", f"#版本：{self.version or self.version_var.get()}#\n")

        text.insert("end", "\n")
        text.insert("end", f"{packet[-4:].hex(' ').upper()} #CRC32 CRC校验值#\n")
        text.configure(state="disabled")
        self._center_window(win, 1200, 800)
        win.lift()
        win.focus_force()

    def _preview_v6(self, text, packet, infos, meta):
        text.insert("end", "#============================================================#\n")
        text.insert("end", "#                       公共字段                             #\n")
        text.insert("end", "#============================================================#\n")
        text.insert("end", f"AA #HEADER 起始标志 = 0xAA#\n")
        text.insert("end", f"{packet[1]:02X} {packet[2]:02X} #FRAME_LENGTH 帧长度 = {len(packet) - 3} 字节#\n")
        text.insert("end", f"{packet[3]:02X} {packet[4]:02X} {packet[5]:02X} {packet[6]:02X} "
                           f"#STAMP 时间戳 = {int.from_bytes(packet[3:7], 'big')}#\n")
        text.insert("end", f"{packet[7]:02X} #MESSAGE_TYPE 消息类型 = 0x{packet[7]:02X}#\n")
        text.insert("end", f"{packet[8]:02X} #NMS_NO NMS编号 = {packet[8]}#\n")
        text.insert("end", f"{packet[9]:02X} {packet[10]:02X} {packet[11]:02X} {packet[12]:02X} "
                           f"#NMS_VERSION NMS软件版本 = {int.from_bytes(packet[9:13], 'big')}#\n")
        text.insert("end", f"{meta['cpu_threshold']:02X} #SW_CPU_HIGH_VALUE CPU高负载阈值 = {meta['cpu_threshold']}%#\n")
        text.insert("end", f"{self._v6_hex(meta['service_port_speed'], 4)} #SW_SERVICE_PORT_SPEED = {meta['service_port_speed']} Kbit/s#\n")
        text.insert("end", f"{self._v6_hex(meta['non_service_port_speed'], 4)} #SW_NON_SERVICE_PORT_SPEED = {meta['non_service_port_speed']} Kbit/s#\n")
        text.insert("end", f"00 00 #AP_NUM AP数量 = 0（固定）#\n")
        text.insert("end", f"{len(infos) >> 8:02X} {len(infos) & 0xFF:02X} #SW_NUM 交换机数量 = {len(infos)}#\n\n")

        text.insert("end", "#============================================================#\n")
        text.insert("end", "#                    V6.0交换机及端口数据                    #\n")
        text.insert("end", "#============================================================#\n\n")
        for info in infos:
            no = info["no"]; hostname = info["hostname"]; ports = info["ports"]
            n, f, o = self._v6_port_summary(ports)
            text.insert("end", f"#----- 交换机 {no} {hostname} -----#\n\n")
            text.insert("end", f"{self._v6_hex(no, 2)} #SW_ID 交换机编号 = {no}#\n")
            text.insert("end", f"{info['sw_status_byte']:02X} #SW_STATUS 整机状态 = {self._v6_status_text(info['sw_status'])}#\n")
            text.insert("end", f"{info['dual_power']:02X} #SW_POWER_STATUS 双电源: {self._v6_power_text(info['dual_power'])}#\n")
            text.insert("end", f"{info['cpu_usage']:02X} #SW_CpuUsage CPU利用率 = {info['cpu_usage']}%#\n")
            text.insert("end", f"{info['memory_usage']:02X} #SW_MEMORY 内存利用率 = {info['memory_usage']}%#\n")
            text.insert("end", f"{self._v6_hex(info['transmission_delay'], 2)} #SW_TRANSMISSION_DELAY = {info['transmission_delay']}ms#\n")
            text.insert("end", f"{info['ring_status']:02X} #SW_TR2_STATUS 环网断链状态 = {self._v6_break_text(info['ring_status'])}#\n")
            text.insert("end", f"{info['ring_master']:02X} #SW_TR2_MASTER 环网主节点标识 = {info['ring_master']}#\n")
            text.insert("end", f"{self._v6_hex_list(info['break_port_ids'])} #SW_TR2_BRKPORT_ID 环网断链端口 (5=正常 6=断链)#\n")
            text.insert("end", "# 断链详情: " + ", ".join(f"端口{p['id']}:{self._v6_break_text(p['break_status'])}" for p in ports) + " #\n")
            text.insert("end", f"{self._v6_hex_list([p['optical_status'] for p in ports])} #SW_PORTn_SFP_STATE 光模块状态#\n")
            text.insert("end", "# 光模块详情: " + ", ".join(f"端口{p['id']}:{self._v6_optical_text(p['optical_status'])}" for p in ports) + " #\n")
            text.insert("end", f"{' '.join(f'{b:02X}' for b in info['port_status_bytes'])} #SW_PORTn_STATUS 端口状态#\n")
            text.insert("end", "# 端口状态详情: " + ", ".join(f"端口{p['id']}:{self._v6_port_status_text(p['status'])}" for p in ports) + " #\n")
            text.insert("end", f"{self._v6_hex_list_u16([p['flux'] for p in ports])} #SW_PORTn_FLUX 端口流量#\n")
            text.insert("end", f"{self._v6_hex_list([p['bandwidth'] for p in ports])} #SW_PORTn_BANDWIDTHUTILI 带宽利用率#\n")
            text.insert("end", f"{self._v6_hex_list_u32([p['forward_speed'] for p in ports])} #SW_PORTn_FORWARD_SPEED 转发速率#\n")
            text.insert("end", f"{self._v6_hex_list_u16([p['error'] for p in ports])} #SW_PORTn_ERROR 错误包数#\n")
            text.insert("end", f"{self._v6_hex_list([p['packet_loss'] for p in ports])} #SW_PORTn_PACKET_LOSS 丢包率#\n")
            text.insert("end", f"{self._v6_hex_list([p['bit_error'] for p in ports])} #SW_PORTn_BIT_ERROR 误码率#\n")
            text.insert("end", f"#端口汇总: 正常{n}, 故障{f}, 超标{o}#\n\n")

    def _preview_v4(self, text, packet, infos, meta):
        text.insert("end", "#============================================================#\n")
        text.insert("end", "#                       公共字段                             #\n")
        text.insert("end", "#============================================================#\n")

        if len(packet) < 30:
            text.insert("end", "# 报文长度不足，无法解析\n")
            return

        header = packet[0]
        lbw = int.from_bytes(packet[1:3], 'big')
        stamp = int.from_bytes(packet[3:7], 'big')
        msg_id = packet[7]
        nms_index = packet[8]
        nms_version = int.from_bytes(packet[9:13], 'big')
        cpu_th = packet[13]
        eport_th = int.from_bytes(packet[14:18], 'big')
        gport_th = int.from_bytes(packet[18:22], 'big')
        ap_num = int.from_bytes(packet[22:24], 'big')
        sw_num = int.from_bytes(packet[24:26], 'big')

        nms_idx_text = {0x01: "主NMS", 0x02: "备NMS"}.get(nms_index, "未知")
        stamp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stamp))

        text.insert("end", f"{header:02X} #HEADER 帧开始标识 = 0x{header:02X}#\n")
        text.insert("end", f"{packet[1]:02X} {packet[2]:02X} "
                           f"#LEN 帧长度(从STAMP到CRC校验结束) = {lbw} 字节#\n")
        text.insert("end", f"{packet[3]:02X} {packet[4]:02X} {packet[5]:02X} {packet[6]:02X} "
                           f"#STAMP 时间戳 = {stamp} ({stamp_str})#\n")
        text.insert("end", f"{msg_id:02X} "
                           f"#MSG_ID 消息类型 = 0x{msg_id:02X} (NMS_TO_MSS_ALARM_INFO)#\n")
        text.insert("end", f"{nms_index:02X} "
                           f"#NMS_INDEX NMS编号 = 0x{nms_index:02X} ({nms_idx_text})#\n")
        text.insert("end", f"{packet[9]:02X} {packet[10]:02X} {packet[11]:02X} {packet[12]:02X} "
                           f"#NMS_VERSION NMS软件版本 = 0x{nms_version:08X} ({nms_version})#\n")
        text.insert("end", f"{cpu_th:02X} "
                           f"#SW_CPU_USAGE_HIGH_VALUE CPU高负载阈值 = {cpu_th}%#\n")
        text.insert("end", f"{packet[14]:02X} {packet[15]:02X} {packet[16]:02X} {packet[17]:02X} "
                           f"#SW_EPORT_HIGH_SPEED_VALUE 业务端口流量超限值 = {eport_th} Kbit/s#\n")
        text.insert("end", f"{packet[18]:02X} {packet[19]:02X} {packet[20]:02X} {packet[21]:02X} "
                           f"#SW_GPORT_HIGH_SPEED_VALUE 非业务端口流量超限值 = {gport_th} Kbit/s#\n")
        text.insert("end", f"{packet[22]:02X} {packet[23]:02X} "
                           f"#AP_NUM AP数量 = {ap_num} (固定0)#\n")
        text.insert("end", f"{packet[24]:02X} {packet[25]:02X} "
                           f"#SW_NUM 交换机数量 = {sw_num}#\n\n")

        text.insert("end", "#============================================================#\n")
        text.insert("end", "#                    V4.0交换机及端口数据                    #\n")
        text.insert("end", "#============================================================#\n\n")

        offset = 26

        for sw_info in infos:
            no = sw_info['no']
            hostname = sw_info['hostname']
            station = sw_info['station']
            port_count = sw_info['port_count']
            ports = sw_info['ports']

            text.insert("end", f"#----- 交换机 {no} {hostname} ({station}) 共{port_count}个端口 -----#\n\n")

            if offset + 2 > len(packet):
                text.insert("end", "# 数据不足，解析中断\n")
                break

            sid = int.from_bytes(packet[offset:offset + 2], 'big')
            text.insert("end", f"{packet[offset]:02X} {packet[offset + 1]:02X} "
                               f"#SW_ID 交换机编号 = {sid}#\n")
            offset += 2

            sw_status_byte = packet[offset]
            text.insert("end", f"{sw_status_byte:02X} "
                               f"#SW_STATUS 交换机状态 = 0b{sw_status_byte:08b}#\n")

            port_bit = (sw_status_byte >> 4) & 0x01
            cpu_bit = (sw_status_byte >> 2) & 0x01
            whole_bit = sw_status_byte & 0x01
            text.insert("end", f"# 位解析: 整机状态位(b0)={whole_bit} "
                               f"({'整机故障' if whole_bit else '正常'}), "
                               f"CPU状态位(b2)={cpu_bit} "
                               f"({'CPU高负载' if cpu_bit else '正常'}), "
                               f"端口状态位(b4)={port_bit} "
                               f"({'端口异常' if port_bit else '正常'})#\n")
            offset += 1

            cpu_usage = packet[offset]
            text.insert("end", f"{cpu_usage:02X} "
                               f"#SW_CpuUsage CPU利用率 = {cpu_usage}%#\n")
            offset += 1

            n_status_bytes = (port_count + 1) // 2
            status_bytes = packet[offset:offset + n_status_bytes]
            port_status_hex = " ".join(f"{b:02X}" for b in status_bytes)
            text.insert("end", f"{port_status_hex} "
                               f"#SW_PORTn_STATUS 端口状态 "
                               f"(4bit/端口, 两端口1字节, 奇数端口补4位0)#\n")

            port_status_details = []
            for i in range(port_count):
                byte_idx = i // 2
                if i % 2 == 0:
                    val = (status_bytes[byte_idx] >> 4) & 0x0F
                else:
                    val = status_bytes[byte_idx] & 0x0F
                pid = ports[i]['id'] if i < len(ports) else (i + 1)
                if val == 0b0001:
                    st_text = "故障"
                elif val == 0b0010:
                    st_text = "超标"
                elif val == 0b0000:
                    st_text = "正常"
                else:
                    st_text = f"未知(0b{val:04b})"
                port_status_details.append(f"端口{pid}:{st_text}")
            text.insert("end", "# 端口状态详情: " + ", ".join(port_status_details) + " #\n")
            offset += n_status_bytes

            flux_values = []
            flux_hex_parts = []
            for i in range(port_count):
                if offset + 2 > len(packet):
                    break
                flux = int.from_bytes(packet[offset:offset + 2], 'big')
                pid = ports[i]['id'] if i < len(ports) else (i + 1)
                flux_values.append(f"端口{pid}:{flux}")
                flux_hex_parts.append(f"{packet[offset]:02X} {packet[offset + 1]:02X}")
                offset += 2
            flux_hex = " ".join(flux_hex_parts)
            text.insert("end", f"{flux_hex} "
                               f"#SW_PORTn_FLUX 端口流量 (每端口2字节, 单位Kbit/s)#\n")
            text.insert("end", "# 流量详情: " + ", ".join(flux_values) + " #\n")

            bw_values = []
            bw_hex_parts = []
            for i in range(port_count):
                if offset + 1 > len(packet):
                    break
                bw = packet[offset]
                pid = ports[i]['id'] if i < len(ports) else (i + 1)
                bw_values.append(f"端口{pid}:{bw}%")
                bw_hex_parts.append(f"{bw:02X}")
                offset += 1
            bw_hex = " ".join(bw_hex_parts)
            text.insert("end", f"{bw_hex} "
                               f"#SW_PORTn_BANDWIDTHUTILI 端口带宽使用率 (每端口1字节, 0~100)#\n")
            text.insert("end", "# 带宽使用率详情: " + ", ".join(bw_values) + " #\n")

            err_values = []
            err_hex_parts = []
            for i in range(port_count):
                if offset + 2 > len(packet):
                    break
                err = int.from_bytes(packet[offset:offset + 2], 'big')
                pid = ports[i]['id'] if i < len(ports) else (i + 1)
                err_values.append(f"端口{pid}:{err}")
                err_hex_parts.append(f"{packet[offset]:02X} {packet[offset + 1]:02X}")
                offset += 2
            err_hex = " ".join(err_hex_parts)
            text.insert("end", f"{err_hex} "
                               f"#SW_PORTn_ERROR 端口错误包数 (每端口2字节)#\n")
            text.insert("end", "# 错误包数详情: " + ", ".join(err_values) + " #\n")

            normal = sum(1 for p in ports if p['status'] == 0)
            fault = sum(1 for p in ports if p['status'] == 1)
            over = sum(1 for p in ports if p['status'] == 2)
            text.insert("end", f"#端口汇总: 正常{normal}, 故障/DOWN{fault}, 流量超标{over}#\n\n")

        if offset < len(packet) - 4:
            end_byte = packet[offset]
            text.insert("end", f"{end_byte:02X} "
                               f"#END 帧结束标识 = 0x{end_byte:02X}#\n")
            offset += 1

        text.insert("end", f"# CRC 计算范围: 从 MSG_ID(偏移0x07) 到 END(偏移0x{offset - 1:02X})#\n")

    def _preview_v1(self, text, packet, infos, meta):
        text.insert("end", "#============================================================#\n")
        text.insert("end", "#                   V1.0 帧结构详情                          #\n")
        text.insert("end", "#============================================================#\n\n")
        if len(packet) < 20:
            return
        text.insert("end", f"{packet[0]:02X} #HEADER = 0x{packet[0]:02X}#\n")
        text.insert("end", f"{packet[1]:02X} {packet[2]:02X} #LEN = {int.from_bytes(packet[1:3], 'big')} 字节#\n")
        text.insert("end", f"{packet[3]:02X} #MSG_ID#\n")
        text.insert("end", f"{packet[4]:02X} {packet[5]:02X} {packet[6]:02X} {packet[7]:02X} #STAMP = {int.from_bytes(packet[4:8], 'big')}#\n")
        text.insert("end", f"{packet[8]:02X} #NMS_INDEX#\n")
        text.insert("end", f"{packet[9]:02X} {packet[10]:02X} {packet[11]:02X} {packet[12]:02X} #NMS_VERSION#\n")
        text.insert("end", f"{packet[13]:02X} {packet[14]:02X} #AP_NUM#\n")
        text.insert("end", f"{packet[15]:02X} #SW_NUM#\n\n")
        for info in infos:
            text.insert("end", f"#===== 交换机 {info['no']} {info['hostname']} =====#\n")
            text.insert("end", f"  SW_STATUS = {self._v1_status_text(info['sw_status'])}\n")
            line = "  "
            for i, p in enumerate(info['ports'], 1):
                dev = f"({p['dev']})" if p.get('dev') else ""
                line += f"端口{p['port_no']}:{self._v1_port_status_text(p['status'])}{dev} "
                if i % 4 == 0:
                    text.insert("end", line + "\n")
                    line = "  "
            if line.strip():
                text.insert("end", line + "\n")
            s = info['port_summary']
            text.insert("end", f"  #汇总: 正常={s['正常']}, 故障={s['故障']}, 超标={s['超标']}#\n\n")

    # ---------- Disney 报文预览 / 解析 ----------
    def _show_disney_preview(self):
        try:
            packets = self._build_disney_packets()
            self._check_disney_targets()
        except Exception as e:
            messagebox.showerror("预览失败", str(e), parent=self)
            return

        if self.preview_window is not None and self.preview_window.winfo_exists():
            self.preview_window.destroy()
        win = Toplevel(self)
        self.preview_window = win
        win.title("报文预览 - Disney（正线 + 试车线）")
        win.transient(self)

        def close_preview():
            self.preview_window = None
            win.destroy()
        win.protocol("WM_DELETE_WINDOW", close_preview)

        total = sum(len(p[0]) for p in packets.values())
        top = ttk.Frame(win); top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text=f"版本：Disney    共 {len(packets)} 条报文，合计 {total} 字节").pack(side="left")
        ttk.Button(top, text="刷新预览", command=lambda: self._refresh_preview(win)).pack(side="right")

        text = scrolledtext.ScrolledText(win, wrap=tk.NONE, font=("Consolas", 10))
        text.pack(fill="both", expand=True, padx=8, pady=8)

        for line in (LINE_MAIN, LINE_TEST):
            if line not in packets:
                continue
            packet, info, sws = packets[line]
            port_counts = [int(s.get("total_ports", 0)) for s in sws]
            try:
                res = parse_packet_disney(packet, port_counts, info.get("pad_blocks", True))
            except Exception as e:
                text.insert("end", f"#【{LINE_NAME[line]}】解析失败: {e}\n")
                continue
            self._render_disney_packet(text, line, packet, info, res, sws)

        text.configure(state="disabled")
        self._center_window(win, 1240, 820)
        win.lift()
        win.focus_force()

    def _render_disney_packet(self, text, line, packet, info, res, sws):
        local_ip = (self.local_ip_main.get().strip() if line == LINE_MAIN
                    else self.local_ip_shd.get().strip())
        target = f"{self.udp_ip.get().strip()}:{self.udp_port.get().strip()}"

        text.insert("end", "#" + "=" * 68 + "#\n")
        text.insert("end", f"#  【{LINE_NAME[line]}】 报文  {len(packet)} 字节   "
                           f"本机 {local_ip or '(未配置)'} → {target}\n")
        text.insert("end", "#" + "=" * 68 + "#\n\n")

        text.insert("end", "#---------- 十六进制 ----------#\n")
        for off in range(0, len(packet), 16):
            chunk = packet[off:off + 16]
            text.insert("end", f"{off:04X}  " + " ".join(f"{b:02X}" for b in chunk) + "\n")

        text.insert("end", "\n#---------- 字段解析 ----------#\n")
        text.insert("end", f"{packet[0]:02X}        #HEADER    帧开始标识 = 0x{packet[0]:02X}\n")
        text.insert("end", f"{packet[1]:02X} {packet[2]:02X}     #LEN       帧长度(MSG_ID~CRC结束) = {res['len_field']} 字节"
                           f"  {'✔' if res['len_ok'] else '✘ 与实际不符'}\n")
        stamp_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(res["stamp"]))
        text.insert("end", f"{packet[3]:02X}        #MSG_ID    消息类型 = 0x{res['msg_id']:02X} (NMS_TO_MSS_ALARM_INFO)\n")
        text.insert("end", f"{packet[4]:02X} {packet[5]:02X} {packet[6]:02X} {packet[7]:02X}  "
                           f"#STAMP     时间戳 = {res['stamp']} ({stamp_str})\n")
        text.insert("end", f"{packet[8]:02X}        #NMS_INDEX NMS编号 = {res['nms_index']}\n")
        text.insert("end", f"{packet[9]:02X} {packet[10]:02X} {packet[11]:02X} {packet[12]:02X}  "
                           f"#NMS_VERSION NMS软件版本 = {res['nms_version']} (0x{res['nms_version']:08X})\n\n")

        # ---- AP 段 ----
        ap_bytes = packet[res["ap_offset"]:res["ap_offset"] + res["ap_len"]]
        text.insert("end", f"{packet[13]:02X} {packet[14]:02X}     #AP_NUM    AP数量 = {res['ap_num']}\n")
        text.insert("end", f"{' '.join(f'{b:02X}' for b in ap_bytes)}  "
                           f"#AP_MODULE_STATUS 状态位(2bit/AP, 4个/字节, 高位在前"
                           f"{', 末尾补%d位0' % res['ap_pad_bits'] if res['ap_pad_bits'] else ''})\n")
        cnt = {0b00: 0, 0b01: 0, 0b11: 0, 0b10: 0}
        for i, code in enumerate(res["ap_codes"]):
            cnt[code] = cnt.get(code, 0) + 1
            ap = info["aps"][i] if i < len(info["aps"]) else {}
            tag = "(车载)" if ap.get("onboard") else ""
            text.insert("end", f"     AP{i + 1:<4} {ap.get('name', ''):<16}{tag:<6}"
                               f" 集中区={ap.get('zone', '') or '-':<5} 网络={ap.get('net', '') or '-':<10}"
                               f" 状态={DISNEY_AP_STATUS_TEXT.get(code, '未知')}(0b{code:02b})\n")
        text.insert("end", f"     #AP汇总: 正常{cnt[0b00]} 故障{cnt[0b01]} 关闭{cnt[0b11]}"
                           f"{' 未定义' + str(cnt[0b10]) if cnt[0b10] else ''}\n\n")

        # ---- AC(WAC) 段 ----
        ac_bytes = packet[res["wac_offset"]:res["wac_offset"] + res["wac_len"]]
        text.insert("end", f"{packet[res['wac_num_offset']]:02X} {packet[res['wac_num_offset'] + 1]:02X}     "
                           f"#AC_NUM    WAC数量 = {res['wac_num']}\n")
        text.insert("end", f"{' '.join(f'{b:02X}' for b in ac_bytes)}  "
                           f"#AC_MODULE_STATUS 状态位(2bit/WAC"
                           f"{', 末尾补%d位0' % res['wac_pad_bits'] if res['wac_pad_bits'] else ''})\n")
        ccnt = {0b00: 0, 0b01: 0, 0b11: 0, 0b10: 0}
        for i, code in enumerate(res["wac_codes"]):
            ccnt[code] = ccnt.get(code, 0) + 1
            wac = info["wacs"][i] if i < len(info["wacs"]) else {}
            text.insert("end", f"     WAC{i + 1:<3} {wac.get('name', ''):<12}"
                               f" 集中区={wac.get('zone', '') or '-':<5} 网络={wac.get('net', '') or '-':<10}"
                               f" 状态={DISNEY_AP_STATUS_TEXT.get(code, '未知')}(0b{code:02b})\n")
        text.insert("end", f"     #WAC汇总: 正常{ccnt[0b00]} 故障{ccnt[0b01]} 关闭{ccnt[0b11]}\n\n")

        # ---- 交换机段 ----
        text.insert("end", f"{packet[res['sw_num_offset']]:02X}        #SW_NUM    交换机数量 = {res['sw_num']}\n")
        text.insert("end", "#（本段不含交换机编号，接收端按顺序映射；以下按当前配置顺序还原）\n")
        for i, sw_res in enumerate(res["switches"]):
            sw = sws[i] if i < len(sws) else {}
            st = sw_res["sw_status"]
            ports = sw_res["ports"]
            n = sum(1 for p in ports if p == 0)
            f_ = sum(1 for p in ports if p == 1)
            o = sum(1 for p in ports if p == 2)
            text.insert("end", f"\n  #--- 交换机{sw.get('no', '?')} {sw.get('hostname', '')} "
                               f"({sw.get('station', '')}) 端口{len(ports)}个 ---#\n")
            text.insert("end", f"  SW_STATUS = 0b{st:02b} ({DISNEY_SW_STATUS_TEXT.get(st, '未知')})\n")
            text.insert("end", f"  端口状态 = {' '.join(f'{p:02b}' for p in ports)}\n")
            text.insert("end", f"  #端口汇总: 正常{n} 故障{f_} 超标{o}\n")
        if res["sw_decoded"] < res["sw_num"]:
            text.insert("end", f"\n  #注意：未能解析全部交换机（{res['sw_decoded']}/{res['sw_num']}），"
                               f"帧内不含端口数，需外部配置表配合解析\n")

        text.insert("end", f"\n{packet[res['end_offset']]:02X}        #END       帧结束标识 = 0x{packet[res['end_offset']]:02X}"
                           f"  {'✔' if res['end_ok'] else '✘'}\n")
        crc_hex = " ".join(f"{b:02X}" for b in packet[-4:])
        text.insert("end", f"{crc_hex}  #CRC32     报文CRC = 0x{res['crc']:08X} / 计算值 = 0x{res['crc_calc']:08X}"
                           f"  {'✔ 校验一致' if res['crc_ok'] else '✘ 校验不一致'}\n")
        text.insert("end", f"#CRC 计算范围：偏移 0x03 (MSG_ID) ~ 0x{len(packet) - 5:02X} (END)\n\n")
        text.insert("end", "#" + "=" * 68 + "#\n\n")

    def parse_packet_dialog(self):
        """粘贴十六进制报文进行解析（Disney 帧）。"""
        win = Toplevel(self)
        win.title("解析报文（粘贴十六进制）")
        win.transient(self)
        frame = ttk.Frame(win); frame.pack(fill='both', expand=True, padx=10, pady=8)

        bar = ttk.Frame(frame); bar.pack(fill='x', pady=(0, 6))
        ttk.Label(bar, text="线路:").pack(side='left')
        line_var = tk.StringVar(value=LINE_MAIN)
        ttk.Radiobutton(bar, text="正线", variable=line_var, value=LINE_MAIN).pack(side='left', padx=4)
        ttk.Radiobutton(bar, text="试车线", variable=line_var, value=LINE_TEST).pack(side='left', padx=4)
        ttk.Label(bar, text="（用于按配置表的端口数还原交换机段）",
                  foreground="gray").pack(side='left', padx=8)

        ttk.Label(frame, text="报文十六进制（空格/换行均可）:").pack(anchor='w')
        src = scrolledtext.ScrolledText(frame, height=6, font=("Consolas", 10))
        src.pack(fill='x', pady=4)

        ttk.Label(frame, text="解析结果:").pack(anchor='w')
        out = scrolledtext.ScrolledText(frame, height=22, font=("Consolas", 10), wrap=tk.NONE)
        out.pack(fill='both', expand=True, pady=4)

        def do_parse():
            out.configure(state='normal')
            out.delete("1.0", "end")
            try:
                hexstr = re.sub(r'[^0-9A-Fa-f]', '', src.get("1.0", "end"))
                if not hexstr:
                    raise ValueError("请输入报文十六进制内容")
                if len(hexstr) % 2:
                    raise ValueError("十六进制字符数为奇数，请检查")
                packet = bytes.fromhex(hexstr)
                line = line_var.get()
                sws = [s for s in self.all_switches if s.get("line", LINE_MAIN) == line]
                port_counts = [int(s.get("total_ports", 0)) for s in sws] if sws else None
                res = parse_packet_disney(packet, port_counts,
                                          bool(self.disney_config.get("pad_blocks", True)))
                out.insert("end", f"报文长度: {len(packet)} 字节\n")
                out.insert("end", f"HEADER      = 0x{packet[0]:02X}\n")
                out.insert("end", f"LEN         = {res['len_field']} 字节 {'✔' if res['len_ok'] else '✘'}\n")
                out.insert("end", f"MSG_ID      = 0x{res['msg_id']:02X}\n")
                out.insert("end", f"STAMP       = {res['stamp']} "
                                  f"({time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(res['stamp']))})\n")
                out.insert("end", f"NMS_INDEX   = {res['nms_index']}\n")
                out.insert("end", f"NMS_VERSION = {res['nms_version']} (0x{res['nms_version']:08X})\n")
                out.insert("end", f"AP_NUM      = {res['ap_num']}  (补{res['ap_pad_bits']}位)\n")
                for i, code in enumerate(res["ap_codes"]):
                    out.insert("end", f"    AP{i + 1:<4} 0b{code:02b} {DISNEY_AP_STATUS_TEXT.get(code, '')}\n")
                out.insert("end", f"AC_NUM      = {res['wac_num']}  (补{res['wac_pad_bits']}位)\n")
                for i, code in enumerate(res["wac_codes"]):
                    out.insert("end", f"    WAC{i + 1:<3} 0b{code:02b} {DISNEY_AP_STATUS_TEXT.get(code, '')}\n")
                out.insert("end", f"SW_NUM      = {res['sw_num']}\n")
                for i, sw_res in enumerate(res["switches"]):
                    sw = sws[i] if i < len(sws) else {}
                    st = sw_res["sw_status"]
                    out.insert("end", f"    SW{i + 1:<3} {sw.get('no', ''):<6}{sw.get('hostname', ''):<26}"
                                      f"状态={DISNEY_SW_STATUS_TEXT.get(st, '未知')}  端口数={len(sw_res['ports'])}\n")
                if res["sw_decoded"] < res["sw_num"]:
                    out.insert("end", f"    （仅解析 {res['sw_decoded']} 台：帧内无端口数，"
                                      f"请先加载配置表）\n")
                out.insert("end", f"END         = 0x{res['end']:02X} {'✔' if res['end_ok'] else '✘'}\n")
                out.insert("end", f"CRC32       = 0x{res['crc']:08X} / 计算 0x{res['crc_calc']:08X} "
                                  f"{'✔ 一致' if res['crc_ok'] else '✘ 不一致'}\n")
            except Exception as e:
                out.insert("end", f"解析失败: {e}\n")
            out.configure(state='disabled')

        btn = ttk.Frame(frame); btn.pack(fill='x', pady=4)
        ttk.Button(btn, text="解析", command=do_parse).pack(side='left', padx=4)
        ttk.Button(btn, text="关闭", command=win.destroy).pack(side='left', padx=4)
        self._center_window(win, 900, 700)

    def _build_packet_detail(self):
        if not self.selected_indices:
            raise ValueError("请至少选择一台交换机")
        selected = [self.all_switches[i] for i in sorted(self.selected_indices)]
        custom = {sw['no']: self.switch_status.get(sw['no'], (0, {})) for sw in selected}
        if self.version == 'V6.0':
            return build_packet_v6(selected, custom, self.v6_config)
        if self.version == 'V4.0':
            return build_packet_v4(selected, custom, self.v6_config)
        if self.version == 'V3.0':
            p, i = build_packet_v2(selected, custom)
            return p, i, {}
        p, i = build_packet_v1(selected, self.port_mapping, custom)
        return p, i, {}

    def _refresh_preview(self, win):
        win.destroy()
        self.preview_window = None
        self.show_packet_preview()

    # ---------- 发送 ----------
    def send_and_generate(self):
        if self._is_disney():
            self._send_disney()
            return
        try:
            packet = self._build_packet()
            self.current_packet = packet
            target_ip = self.udp_ip.get().strip()
            target_port = self.udp_port.get().strip()
            hexstr = ' '.join(f'{b:02X}' for b in packet)
            self._log(f"发送报文到 {target_ip}:{target_port}，长度 {len(packet)} 字节\n报文: {hexstr}")
            ok, msg = self._send_udp(packet)
            if ok:
                self._set_status(f"发送成功: {msg}")
                self._log(f"发送成功: {msg}")
            else:
                self._set_status(f"发送失败: {msg}")
                messagebox.showerror("发送失败", msg, parent=self)
        except Exception as e:
            messagebox.showerror("生成失败", str(e), parent=self)
            self._log(f"生成失败: {e}")

    def _send_disney(self):
        try:
            self._check_disney_targets()
            packets = self._build_disney_packets()
            target_ip = self.udp_ip.get().strip()
            target_port = self.udp_port.get().strip()
            for line in (LINE_MAIN, LINE_TEST):
                if line in packets:
                    packet, info, _ = packets[line]
                    self._log(f"[{LINE_NAME[line]}] 生成报文 {len(packet)} 字节（AP {info['ap_num']} 个 / "
                              f"WAC {info['wac_num']} 个 / 交换机 {info['sw_num']} 台），"
                              f"发往 {target_ip}:{target_port}")
            ok, msg = self._send_disney_once()
            self._set_status(("发送成功: " if ok else "部分失败: ") + msg)
            self._log(msg)
            if not ok:
                messagebox.showerror("发送失败", msg, parent=self)
        except Exception as e:
            messagebox.showerror("发送失败", str(e), parent=self)
            self._log(f"Disney 发送失败: {e}")

    def start_continuous_send(self):
        if self.continuous_running:
            return
        if not self.selected_indices:
            messagebox.showinfo("提示", "请至少选择一台交换机", parent=self)
            return
        if not self.udp_ip.get().strip():
            messagebox.showerror("错误", "请输入目标 IP", parent=self)
            return
        try:
            interval = int(self.interval_ms.get().strip())
            if interval < 100:
                messagebox.showerror("错误", "发送间隔不能小于100ms", parent=self)
                return
        except ValueError:
            messagebox.showerror("错误", "发送间隔必须是整数", parent=self)
            return

        if self._is_disney():
            try:
                self._check_disney_targets()
                self._open_disney_sockets()
            except Exception as e:
                messagebox.showerror("错误", f"无法建立发送通道: {e}", parent=self)
                return
        else:
            try:
                self._open_continuous_socket()
            except Exception as e:
                messagebox.showerror("错误", f"创建套接字失败: {e}", parent=self)
                return

        self.continuous_running = True
        self._sent_count = 0
        self.btn_start_continuous.config(state="disabled")
        self.btn_stop_continuous.config(state="normal")
        self._log(f"持续发送已启动，间隔 {interval} ms")
        self.after_id = self.after(1, self.continuous_send)

    def continuous_send(self):
        if not self.continuous_running:
            return
        if self._is_disney():
            self._continuous_send_disney()
            return
        try:
            packet = self._build_packet()
            ok, msg = self._send_udp(packet, self._send_sock)
            self._sent_count += 1
            if ok:
                if self._sent_count <= 3 or self._sent_count % self.CONTINUOUS_LOG_EVERY == 0:
                    self._log(f"[持续] 第 {self._sent_count} 次发送成功")
                self._set_status(f"[持续] 已发送 {self._sent_count} 次")
            else:
                self._log(f"[持续] 第 {self._sent_count} 次失败: {msg}")
        except Exception as e:
            self._log(f"[持续] 生成失败: {e}")
            self.stop_continuous_send()
            return
        if not self.continuous_running:
            return
        try:
            interval = max(100, int(self.interval_ms.get().strip()))
        except ValueError:
            interval = 1000
        self.after_id = self.after(interval, self.continuous_send)

    def _continuous_send_disney(self):
        try:
            packets = self._build_disney_packets()
            target_ip = self.udp_ip.get().strip()
            target_port = int(self.udp_port.get().strip())
            errs = []
            for line, sock in ((LINE_MAIN, self._send_sock_main), (LINE_TEST, self._send_sock_shd)):
                if line not in packets:
                    continue
                if sock is None:
                    errs.append(f"{LINE_NAME[line]} 套接字不可用")
                    continue
                try:
                    sock.sendto(packets[line][0], (target_ip, target_port))
                except Exception as e:
                    errs.append(f"{LINE_NAME[line]}: {e}")
            self._sent_count += 1
            if errs:
                self._log(f"[持续] 第 {self._sent_count} 次失败: {'; '.join(errs)}")
            elif self._sent_count <= 3 or self._sent_count % self.CONTINUOUS_LOG_EVERY == 0:
                self._log(f"[持续] 第 {self._sent_count} 次发送成功（正线+试车线）")
            self._set_status(f"[持续] 已发送 {self._sent_count} 次（正线+试车线）")
        except Exception as e:
            self._log(f"[持续] 生成失败: {e}")
            self.stop_continuous_send()
            return
        if not self.continuous_running:
            return
        try:
            interval = max(100, int(self.interval_ms.get().strip()))
        except ValueError:
            interval = 1000
        self.after_id = self.after(interval, self.continuous_send)

    def stop_continuous_send(self, silent=False):
        was_running = self.continuous_running
        self.continuous_running = False
        if self.after_id is not None:
            try:
                self.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None
        self._close_send_socket()
        self._close_disney_sockets()
        try:
            self.btn_start_continuous.config(state="normal")
            self.btn_stop_continuous.config(state="disabled")
        except Exception:
            pass
        if was_running and not silent:
            self._log(f"持续发送已停止（共发送 {self._sent_count} 次）")

    def copy_log(self):
        content = self.log_text.get("1.0", tk.END).strip()
        if content:
            self.clipboard_clear()
            self.clipboard_append(content)
            self._set_status("日志已复制到剪贴板")
        else:
            messagebox.showinfo("提示", "日志为空", parent=self)


# ============================================================
# 拓扑图数据校验窗口（Toplevel 版）
# ============================================================
class TopologyCheckWindow(tk.Toplevel):
    """拓扑表 ↔ API 数据比对工具（弹窗版）"""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.root = self  # 兼容原代码 self.root.xxx

        self.title("DCS拓扑表 ↔ API 数据比对工具 v2.1")
        self.transient(parent)
        self.set_window_icon()

        self.base_url_var = tk.StringVar(
            self,
            value="http://192.168.1.237/bdms/isim-backend/isim/indoorDevice/getDcsSwitchLink?stationNo=")
        self.excel_path_var = tk.StringVar(self)
        self.db_host_var = tk.StringVar(self, value="192.168.1.237")
        self.db_port_var = tk.StringVar(self, value="3306")
        self.db_name_var = tk.StringVar(self, value="base")
        self.db_user_var = tk.StringVar(self, value="root")
        self.db_pass_var = tk.StringVar(self, value="mysql")
        self.status_var = tk.StringVar(self, value="就绪")

        self.show_success_var = tk.BooleanVar(self, value=True)
        self.show_fail_var = tk.BooleanVar(self, value=True)
        self.show_mismatch_var = tk.BooleanVar(self, value=True)
        self.show_missing_json_var = tk.BooleanVar(self, value=True)
        self.show_missing_excel_var = tk.BooleanVar(self, value=True)
        self.show_error_var = tk.BooleanVar(self, value=True)
        self.show_duplicate_var = tk.BooleanVar(self, value=True)

        self.stations = []
        self.excel_data = {}
        self.compare_workers = 8
        self._excel_station_index = {}
        self._excel_dups = {}
        self._thread_local = threading.local()

        self.results = []
        self.visible_results = []
        self._running = False
        self._ui_log_queue = queue.Queue(maxsize=20000)

        self._build_ui()
        self._center_on_parent()
        self.root.after(200, self._drain_ui_log)

    def _center_on_parent(self):
        try:
            self.update_idletasks()
            self.parent.update_idletasks()
            px = self.parent.winfo_rootx()
            py = self.parent.winfo_rooty()
            pw = self.parent.winfo_width()
            ph = self.parent.winfo_height()
            w, h = 1560, 980
            x = px + max(0, (pw - w) // 2)
            y = py + max(0, (ph - h) // 2)
            sw = self.parent.winfo_screenwidth()
            sh = self.parent.winfo_screenheight()
            if x + w > sw:
                x = max(0, sw - w)
            if y + h > sh:
                y = max(0, sh - h)
            if x < 0:
                x = 0
            if y < 0:
                y = 0
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            self.geometry("1560x980")

    def set_window_icon(self):
        candidates = []
        if hasattr(sys, "_MEIPASS"):
            candidates.append(os.path.join(sys._MEIPASS, "Cjdowner-Cryptocurrency-Verify.ico"))
        candidates.append(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                       "Cjdowner-Cryptocurrency-Verify.ico"))
        for p in candidates:
            try:
                if os.path.exists(p):
                    self.iconbitmap(p)
                    return
            except Exception:
                pass

    # ---------- 线程安全 UI 调度 ----------
    def _ui(self, fn, *args, **kwargs):
        try:
            self.root.after(0, lambda: fn(*args, **kwargs))
        except Exception:
            pass

    def _set_status(self, text):
        self._ui(self.status_var.set, text)

    def _set_progress(self, value=None, maximum=None):
        def _do():
            try:
                if maximum is not None:
                    self.progress.configure(maximum=maximum)
                if value is not None:
                    self.progress.configure(value=value)
            except Exception:
                pass
        self._ui(_do)

    def _get_session(self):
        s = getattr(self._thread_local, "session", None)
        if s is None:
            s = requests.Session()
            s.verify = False
            s.headers.update({"User-Agent": "TopologyCheck/2.1"})
            self._thread_local.session = s
        return s

    # ---------- UI 构建 ----------
    def _build_ui(self):
        top = ttk.LabelFrame(self, text="配置", padding=10)
        top.pack(fill="x", padx=10, pady=5)
        top.columnconfigure(1, weight=1)
        top.columnconfigure(3, weight=1)

        ttk.Label(top, text="API 基础地址:").grid(row=0, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.base_url_var).grid(row=0, column=1, columnspan=3, sticky="we", padx=5, pady=3)

        ttk.Label(top, text="拓扑表 Excel:").grid(row=1, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.excel_path_var).grid(row=1, column=1, columnspan=2, sticky="we", padx=5, pady=3)
        ttk.Button(top, text="浏览...", command=self._browse_excel).grid(row=1, column=3, sticky="e", padx=5, pady=3)

        ttk.Label(top, text="数据库主机:").grid(row=2, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.db_host_var, width=20).grid(row=2, column=1, sticky="w", padx=5, pady=3)
        ttk.Label(top, text="端口:").grid(row=2, column=2, sticky="e", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.db_port_var, width=10).grid(row=2, column=3, sticky="w", padx=5, pady=3)

        ttk.Label(top, text="数据库名:").grid(row=3, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.db_name_var, width=20).grid(row=3, column=1, sticky="w", padx=5, pady=3)
        ttk.Label(top, text="用户名:").grid(row=3, column=2, sticky="e", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.db_user_var, width=20).grid(row=3, column=3, sticky="w", padx=5, pady=3)

        ttk.Label(top, text="密码:").grid(row=4, column=0, sticky="w", padx=5, pady=3)
        ttk.Entry(top, textvariable=self.db_pass_var, width=20, show="*").grid(row=4, column=1, sticky="w", padx=5, pady=3)

        btn = ttk.Frame(self); btn.pack(fill="x", padx=10, pady=5)
        ttk.Button(btn, text="① 加载站点",   command=self._load_stations_thread).pack(side="left", padx=5)
        ttk.Button(btn, text="② 加载拓扑表", command=self._load_excel_thread).pack(side="left", padx=5)
        ttk.Button(btn, text="③ 开始比对",   command=self._start_compare_thread).pack(side="left", padx=5)
        ttk.Button(btn, text="导出当前显示", command=self._export_results).pack(side="left", padx=5)
        ttk.Button(btn, text="清空日志",     command=self._clear_log).pack(side="left", padx=5)

        filt = ttk.LabelFrame(self, text="显示过滤（影响界面显示与导出）", padding=6)
        filt.pack(fill="x", padx=10, pady=3)
        ttk.Checkbutton(filt, text="显示成功（一致）", variable=self.show_success_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Separator(filt, orient="vertical").pack(side="left", fill="y", padx=5)
        ttk.Checkbutton(filt, text="显示失败", variable=self.show_fail_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Checkbutton(filt, text="└ 值不一致", variable=self.show_mismatch_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Checkbutton(filt, text="└ JSON 缺失", variable=self.show_missing_json_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Checkbutton(filt, text="└ Excel 缺失", variable=self.show_missing_excel_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Checkbutton(filt, text="└ 错误", variable=self.show_error_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Checkbutton(filt, text="└ 端口重复", variable=self.show_duplicate_var,
                        command=self._refresh_view).pack(side="left", padx=8)
        ttk.Button(filt, text="全选",   command=self._select_all_filters).pack(side="right", padx=3)
        ttk.Button(filt, text="仅失败", command=self._only_fail_filters).pack(side="right", padx=3)
        ttk.Button(filt, text="仅成功", command=self._only_success_filters).pack(side="right", padx=3)

        self.progress = ttk.Progressbar(self, mode="determinate")
        self.progress.pack(fill="x", padx=10, pady=(5, 0))
        ttk.Label(self, textvariable=self.status_var).pack(anchor="w", padx=10)

        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=10, pady=5)

        f1 = ttk.Frame(nb); nb.add(f1, text="日志")
        self.log_text = scrolledtext.ScrolledText(f1, wrap="word")
        self.log_text.pack(fill="both", expand=True)

        f2 = ttk.Frame(nb); nb.add(f2, text="站点列表")
        self.station_tree = ttk.Treeview(f2, columns=("no", "name"), show="headings")
        self.station_tree.heading("no", text="站点编号")
        self.station_tree.heading("name", text="站点名称")
        self.station_tree.column("no", width=140)
        self.station_tree.column("name", width=320)
        self.station_tree.pack(fill="both", expand=True)

        f3 = ttk.Frame(nb); nb.add(f3, text="比对结果")
        rcols = ("station", "switch", "port", "type", "excel", "json", "status")
        headers = ["站点", "交换机", "端口", "对比项", "Excel 值", "JSON 值", "结果"]
        widths  = [110, 200, 60, 100, 260, 260, 100]
        self.result_tree = ttk.Treeview(f3, columns=rcols, show="headings")
        for c, h, w in zip(rcols, headers, widths):
            self.result_tree.heading(c, text=h)
            self.result_tree.column(c, width=w, anchor="w")
        vsb = ttk.Scrollbar(f3, orient="vertical", command=self.result_tree.yview)
        self.result_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.result_tree.pack(fill="both", expand=True)

        self.result_tree.tag_configure(ST_SUCCESS,       background="#e6ffe6")
        self.result_tree.tag_configure(ST_MISMATCH,      background="#ffd9d9")
        self.result_tree.tag_configure(ST_MISSING_JSON,  background="#ffe9b3")
        self.result_tree.tag_configure(ST_MISSING_EXCEL, background="#d9e6ff")
        self.result_tree.tag_configure(ST_ERROR,         background="#f0c0f0")
        self.result_tree.tag_configure(ST_DUPLICATE, background="#ff4d4d", foreground="#ffffff")

        self.summary_var = tk.StringVar(self, value="比对结果：尚未执行")
        ttk.Label(self, textvariable=self.summary_var).pack(anchor="w", padx=10, pady=(0, 5))

    # ---------- 过滤 ----------
    def _select_all_filters(self):
        for v in (self.show_success_var, self.show_fail_var, self.show_mismatch_var,
                  self.show_missing_json_var, self.show_missing_excel_var,
                  self.show_error_var, self.show_duplicate_var):
            v.set(True)
        self._refresh_view()

    def _only_fail_filters(self):
        self.show_success_var.set(False)
        for v in (self.show_fail_var, self.show_mismatch_var, self.show_missing_json_var,
                  self.show_missing_excel_var, self.show_error_var,
                  self.show_duplicate_var):
            v.set(True)
        self._refresh_view()

    def _only_success_filters(self):
        self.show_success_var.set(True)
        self.show_fail_var.set(False)
        self._refresh_view()

    def _pass_filter(self, status):
        if status == ST_SUCCESS:
            return self.show_success_var.get()
        if not self.show_fail_var.get():
            return False
        if status == ST_MISMATCH:       return self.show_mismatch_var.get()
        if status == ST_MISSING_JSON:   return self.show_missing_json_var.get()
        if status == ST_MISSING_EXCEL:  return self.show_missing_excel_var.get()
        if status == ST_ERROR:          return self.show_error_var.get()
        if status == ST_DUPLICATE:      return self.show_duplicate_var.get()
        return True

    def _refresh_view(self):
        try:
            for i in self.result_tree.get_children():
                self.result_tree.delete(i)
            self.visible_results = []
            for r in self.results:
                if not self._pass_filter(r.get("status", ST_SUCCESS)):
                    continue
                self.visible_results.append(r)
                tag = r.get("status", ST_SUCCESS)
                self.result_tree.insert("", "end",
                    values=(r["station"], r["switch"], r.get("port", ""),
                            r["type"], r["excel"], r["json"],
                            STATUS_LABEL.get(tag, tag)),
                    tags=(tag,))
            cnt = {ST_SUCCESS: 0, ST_MISMATCH: 0, ST_MISSING_JSON: 0,
                  ST_MISSING_EXCEL: 0, ST_ERROR: 0, ST_DUPLICATE: 0}
            for r in self.results:
                s = r.get("status", ST_SUCCESS)
                cnt[s] = cnt.get(s, 0) + 1
            total = len(self.results)
            fail_total = sum(cnt[s] for s in FAIL_STATUSES)
            self.summary_var.set(
                f"全部 {total} 条  |  一致 {cnt[ST_SUCCESS]}  |  失败 {fail_total}  "
                f"（不一致 {cnt[ST_MISMATCH]}，JSON缺失 {cnt[ST_MISSING_JSON]}，"
                f"Excel缺失 {cnt[ST_MISSING_EXCEL]}，端口重复 {cnt[ST_DUPLICATE]}，"
                f"错误 {cnt[ST_ERROR]}）  "
                f"|  当前显示 {len(self.visible_results)} 条")
        except Exception:
            pass

    # ---------- 日志 ----------
    def _log(self, msg):
        try:
            self._ui_log_queue.put_nowait(msg)
        except Exception:
            pass

    def _drain_ui_log(self):
        batch = []
        try:
            while True:
                try:
                    batch.append(self._ui_log_queue.get_nowait())
                except queue.Empty:
                    break
        except Exception:
            pass
        if batch:
            ts = datetime.now().strftime("%H:%M:%S")
            text = "".join(f"[{ts}] {m}\n" for m in batch)
            try:
                self.log_text.insert("end", text)
                self.log_text.see("end")
            except Exception:
                pass
        try:
            self.root.after(200, self._drain_ui_log)
        except Exception:
            pass

    def _clear_log(self):
        try:
            self.log_text.delete("1.0", "end")
        except Exception:
            pass

    def _browse_excel(self):
        p = filedialog.askopenfilename(title="选择拓扑表 Excel",
                                       filetypes=[("Excel 文件", "*.xlsx")],
                                       parent=self)
        if p:
            self.excel_path_var.set(p)
            self._load_excel_thread()

    # ---------- 站点 ----------
    def _load_stations_thread(self):
        if self._running:
            messagebox.showwarning("提示", "当前有任务正在执行", parent=self)
            return
        threading.Thread(target=self._load_stations, daemon=True).start()

    def _load_stations(self):
        self._running = True
        try:
            self._set_status("正在读取站点...")
            self._log("连接数据库读取 dic_station ...")
            conn = pymysql.connect(
                host=self.db_host_var.get().strip(),
                port=int(self.db_port_var.get().strip() or "3306"),
                user=self.db_user_var.get().strip(),
                password=self.db_pass_var.get().strip(),
                database=self.db_name_var.get().strip(),
                charset="utf8mb4",
                connect_timeout=10)
            try:
                with conn.cursor() as cur:
                    cur.execute("select station_no, station_name from dic_station")
                    rows = cur.fetchall()
            finally:
                conn.close()

            self.stations = [(str(r[0]), str(r[1])) for r in rows]
            self._log(f"共读取到 {len(self.stations)} 个站点")

            def _fill():
                try:
                    for i in self.station_tree.get_children():
                        self.station_tree.delete(i)
                    for no, name in self.stations:
                        self.station_tree.insert("", "end", values=(no, name))
                except Exception:
                    pass
            self._ui(_fill)
            self._set_status(f"站点加载完成：{len(self.stations)} 个")
        except Exception as e:
            self._log(f"读取站点失败：{e}")
            self._ui(messagebox.showerror, "数据库错误", str(e))
        finally:
            self._running = False

    # ---------- 拓扑表 ----------
    def _load_excel_thread(self):
        path = self.excel_path_var.get().strip()
        if not path:
            p = filedialog.askopenfilename(title="选择拓扑表 Excel",
                                           filetypes=[("Excel 文件", "*.xlsx")],
                                           parent=self)
            if not p:
                return
            self.excel_path_var.set(p)
            path = p
        if not os.path.exists(path):
            messagebox.showerror("错误", f"文件不存在：{path}", parent=self)
            return
        threading.Thread(target=self._load_excel, args=(path,), daemon=True).start()

    def _load_excel(self, path):
        self._running = True
        try:
            self._set_status("正在读取拓扑表...")
            self._log(f"读取拓扑表：{path}")
            if not path.lower().endswith(".xlsx"):
                raise ValueError("轻量版仅支持 .xlsx，请将 .xls 另存为 .xlsx 后再加载。")

            wb = load_workbook(path, read_only=True, data_only=True)
            excel_data = {}
            excel_dups = {}
            try:
                for ws in wb.worksheets:
                    sheet_name = ws.title.strip()
                    if sheet_name in ("设备类型状态表", "NMSConfig"):
                        continue
                    ports = {}
                    dups = set()
                    for row in ws.iter_rows(values_only=True):
                        if len(row) < 9:
                            continue
                        sw1 = clean_val(row[0]); ip1 = clean_val(row[1])
                        p1  = clean_val(row[2]); c1  = clean_val(row[3])
                        dev = clean_val(row[4]); c2  = clean_val(row[5])
                        sw2 = clean_val(row[6]); ip2 = clean_val(row[7])
                        p2  = clean_val(row[8])
                        if sw1 == "交换机1":
                            continue
                        if c1 == "1" and sw1 and p1:
                            key = (sw1, p1)
                            if key in ports:
                                dups.add(key)
                            else:
                                ports[key] = {"dev": dev, "ip": ip1}
                        if c2 == "1" and sw2 and p2:
                            key = (sw2, p2)
                            if key in ports:
                                dups.add(key)
                            else:
                                ports[key] = {"dev": dev, "ip": ip2}
                    if ports:
                        excel_data[sheet_name] = ports
                        if dups:
                            excel_dups[sheet_name] = dups
                            self._log(f"  · {sheet_name}：{len(ports)} 个端口，"
                                      f"发现 {len(dups)} 个重复端口")
                        else:
                            self._log(f"  · {sheet_name}：{len(ports)} 个端口")
            finally:
                wb.close()

            self.excel_data = excel_data

            index = {}
            dup_index = {}
            for k, v in excel_data.items():
                k0 = k.strip()
                k_alt = k0.replace("站", "")
                index[k0] = v
                index[k_alt] = v
                d = excel_dups.get(k)
                if d:
                    dup_index[k0] = d
                    dup_index[k_alt] = d
            self._excel_station_index = index
            self._excel_dups = dup_index

            self._log(f"拓扑表加载完成：共 {len(excel_data)} 个站点")
            self._set_status(f"拓扑表加载完成：{len(excel_data)} 个站点")
        except Exception as e:
            self._log(f"读取拓扑表失败：{e}")
            self._ui(messagebox.showerror, "Excel 错误", str(e))
        finally:
            self._running = False

    # ---------- 比对 ----------
    def _start_compare_thread(self):
        if self._running:
            messagebox.showwarning("提示", "当前有任务正在执行", parent=self)
            return
        if not self.stations:
            messagebox.showwarning("提示", "请先加载站点", parent=self)
            return
        if not self.excel_data:
            messagebox.showwarning("提示", "请先加载拓扑表", parent=self)
            return
        if not self.base_url_var.get().strip():
            messagebox.showwarning("提示", "请填写 API 基础地址", parent=self)
            return
        threading.Thread(target=self._compare_all, daemon=True).start()

    def _compare_all(self):
        self._running = True
        self.results = []
        total = len(self.stations)
        self._set_progress(value=0, maximum=total)

        base_url = self.base_url_var.get().strip()

        def _clear_tree():
            try:
                for i in self.result_tree.get_children():
                    self.result_tree.delete(i)
            except Exception:
                pass
        self._ui(_clear_tree)

        try:
            self._log(f"开始比对，共 {total} 个站点；并发数 {self.compare_workers}")
            completed = 0

            def worker(item):
                no, name = item
                try:
                    res, log_msg = self._compare_one_station(no, name, base_url)
                    return no, name, res, log_msg, None
                except Exception as e:
                    return no, name, [{
                        "station": name, "switch": "", "port": "",
                        "type": "异常", "excel": "", "json": str(e),
                        "status": ST_ERROR}], f"[{name}] 比对异常：{e}", e

            workers = min(max(1, self.compare_workers), max(1, total))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="compare") as executor:
                futures = [executor.submit(worker, item) for item in self.stations]
                for future in as_completed(futures):
                    no, name, res, log_msg, exc = future.result()
                    self.results.extend(res)
                    completed += 1
                    if log_msg:
                        self._log(log_msg)
                    if completed == total or completed == 1 or completed % 5 == 0:
                        self._set_progress(value=completed)
                        self._set_status(f"正在比对 [{completed}/{total}]，并发 {workers}")

            self._ui(self._refresh_view)
            self._log(f"比对完成，全部记录 {len(self.results)} 条")
            self._set_status(f"比对完成：{total} 个站点，全部记录 {len(self.results)} 条")
        except Exception as e:
            self._log(f"批量比对异常：{e}")
            self._ui(messagebox.showerror, "比对错误", str(e))
        finally:
            self._running = False

    def _find_excel_station(self, station_name):
        index = self._excel_station_index
        if station_name in index:
            return station_name, index[station_name]
        alt = station_name.replace("站", "")
        if alt in index:
            return alt, index[alt]
        for k, v in self.excel_data.items():
            kk = k.replace("站", "")
            if kk and (kk in alt or alt in kk):
                return k, v
        return None, None

    def _compare_one_station(self, station_no, station_name, base_url):
        results = []
        url = build_api_url(base_url, station_no)

        try:
            session = self._get_session()
            resp = session.get(url, timeout=30)
            resp.encoding = "utf-8"
            data = resp.json()
        except Exception as e:
            results.append({
                "station": station_name, "switch": "", "port": "", "type": "API请求",
                "excel": "", "json": f"请求失败: {e}", "status": ST_ERROR})
            return results, ""

        if data.get("code") != 200:
            results.append({
                "station": station_name, "switch": "", "port": "", "type": "API返回",
                "excel": "", "json": f"code={data.get('code')} msg={data.get('msg')}",
                "status": ST_ERROR})
            return results, ""

        json_ports = {}
        json_dups = set()
        for group in (data.get("data") or []):
            for child in (group.get("child") or []):
                dev_name = child.get("name", "")
                link_to = str(child.get("linkTo", ""))
                if "1" in link_to:
                    sw = clean_val(child.get("switch1Name", ""))
                    p = clean_val(child.get("port1", ""))
                    ip = clean_val(child.get("ip1", ""))
                    if sw and p:
                        key = (sw, p)
                        if key in json_ports:
                            json_dups.add(key)
                        else:
                            json_ports[key] = {"dev": dev_name, "ip": ip}
                if "2" in link_to:
                    sw = clean_val(child.get("switch2Name", ""))
                    p = clean_val(child.get("port2", ""))
                    ip = clean_val(child.get("ip2", ""))
                    if sw and p:
                        key = (sw, p)
                        if key in json_ports:
                            json_dups.add(key)
                        else:
                            json_ports[key] = {"dev": dev_name, "ip": ip}

        matched_name, excel_ports = self._find_excel_station(station_name)
        excel_dups = self._excel_dups.get(matched_name, set()) if matched_name else set()

        if excel_ports is None:
            results.append({
                "station": station_name, "switch": "", "port": "", "type": "站点",
                "excel": "Excel 无此站点", "json": "", "status": ST_MISSING_EXCEL})
            for key in sorted(json_dups, key=lambda x: (x[0], self._port_sort(x[1]))):
                sw, port = key
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "端口重复(JSON)",
                    "excel": "", "json": f"端口 {port} 重复出现",
                    "status": ST_DUPLICATE})
            return results, ""

        all_keys = set(excel_ports.keys()) | set(json_ports.keys())
        diff_count = 0
        ok_count = 0

        for key in sorted(all_keys, key=lambda x: (x[0], self._port_sort(x[1]))):
            sw, port = key
            ep = excel_ports.get(key)
            jp = json_ports.get(key)

            if ep and not jp:
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "端口/设备",
                    "excel": f"{ep['dev']} ({ep['ip']})", "json": "缺失",
                    "status": ST_MISSING_JSON})
                diff_count += 1
                continue

            if jp and not ep:
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "端口/设备",
                    "excel": "缺失", "json": f"{jp['dev']} ({jp['ip']})",
                    "status": ST_MISSING_EXCEL})
                diff_count += 1
                continue

            port_ok = True
            if ep["dev"] != jp["dev"]:
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "设备名", "excel": ep["dev"], "json": jp["dev"],
                    "status": ST_MISMATCH})
                diff_count += 1
                port_ok = False

            e_ip, j_ip = ep["ip"], jp["ip"]
            if (e_ip and j_ip and e_ip != j_ip
                    and e_ip != "0.0.0.0" and j_ip != "0.0.0.0"):
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "IP", "excel": e_ip, "json": j_ip,
                    "status": ST_MISMATCH})
                diff_count += 1
                port_ok = False

            if port_ok:
                results.append({
                    "station": station_name, "switch": sw, "port": port,
                    "type": "端口/设备",
                    "excel": f"{ep['dev']} ({ep['ip']})",
                    "json": f"{jp['dev']} ({jp['ip']})",
                    "status": ST_SUCCESS})
                ok_count += 1

        for key in sorted(excel_dups, key=lambda x: (x[0], self._port_sort(x[1]))):
            sw, port = key
            results.append({
                "station": station_name, "switch": sw, "port": port,
                "type": "端口重复(Excel)",
                "excel": f"端口 {port} 在交换机 {sw} 下重复出现",
                "json": "",
                "status": ST_DUPLICATE})
            diff_count += 1

        for key in sorted(json_dups, key=lambda x: (x[0], self._port_sort(x[1]))):
            sw, port = key
            results.append({
                "station": station_name, "switch": sw, "port": port,
                "type": "端口重复(JSON)",
                "excel": "",
                "json": f"端口 {port} 在交换机 {sw} 下重复出现",
                "status": ST_DUPLICATE})
            diff_count += 1

        return results, f"[{station_name}] 一致 {ok_count} 条，差异 {diff_count} 条"

    @staticmethod
    def _port_sort(p):
        try:
            return (0, int(p))
        except Exception:
            return (1, str(p))

    # ---------- 导出 ----------
    def _export_results(self):
        if not self.visible_results:
            messagebox.showinfo("提示", "当前显示为空，无内容可导出", parent=self)
            return
        p = filedialog.asksaveasfilename(
            title="导出当前显示结果",
            defaultextension=".xlsx",
            filetypes=[("Excel 文件", "*.xlsx"), ("CSV 文件", "*.csv")],
            initialfile=f"拓扑比对结果_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            parent=self)
        if not p:
            return
        try:
            headers = ["站点", "交换机", "端口", "对比项", "Excel 值", "JSON 值", "结果"]
            if p.lower().endswith(".csv"):
                with open(p, "w", newline="", encoding="utf-8-sig") as f:
                    writer = csv.writer(f)
                    writer.writerow(headers)
                    for r in self.visible_results:
                        writer.writerow([
                            r.get("station", ""), r.get("switch", ""), r.get("port", ""),
                            r.get("type", ""), r.get("excel", ""), r.get("json", ""),
                            STATUS_LABEL.get(r.get("status", ""), r.get("status", ""))])
            else:
                wb = Workbook()
                ws = wb.active
                ws.title = "比对结果"
                ws.append(headers)
                for r in self.visible_results:
                    ws.append([
                        r.get("station", ""), r.get("switch", ""), r.get("port", ""),
                        r.get("type", ""), r.get("excel", ""), r.get("json", ""),
                        STATUS_LABEL.get(r.get("status", ""), r.get("status", ""))])
                wb.save(p)
                wb.close()
            self._log(f"结果已导出（{len(self.visible_results)} 条）：{p}")
            messagebox.showinfo("导出成功", f"已导出 {len(self.visible_results)} 条到：\n{p}", parent=self)
        except Exception as e:
            messagebox.showerror("导出失败", str(e), parent=self)


# 状态常量
ST_SUCCESS       = "success"
ST_MISMATCH      = "mismatch"
ST_MISSING_JSON  = "missing_json"
ST_MISSING_EXCEL = "missing_excel"
ST_ERROR         = "error"
ST_DUPLICATE     = "duplicate"

STATUS_LABEL = {
    ST_SUCCESS: "一致",
    ST_MISMATCH: "值不一致",
    ST_MISSING_JSON: "JSON 缺失",
    ST_MISSING_EXCEL: "Excel 缺失",
    ST_ERROR: "错误",
    ST_DUPLICATE: "端口重复",
}
FAIL_STATUSES = {ST_MISMATCH, ST_MISSING_JSON, ST_MISSING_EXCEL, ST_ERROR, ST_DUPLICATE}


# ============================================================
# 入口
# ============================================================
def main():
    import traceback, os, sys, datetime
    import tempfile
    log_path = os.path.join(tempfile.gettempdir(), "启动错误.log")

    def _write_crash(exc_info):
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n{'='*60}\n{datetime.datetime.now()}\n")
                f.write("".join(traceback.format_exception(*exc_info)))
        except Exception:
            pass

    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    try:
        app = NMSApp()
    except Exception:
        _write_crash(sys.exc_info())
        # 尝试弹窗提示
        try:
            import tkinter.messagebox as mb
            mb.showerror("启动失败", f"程序启动失败，详情见：\n{log_path}")
        except Exception:
            pass
        return

    def _tk_exc_hook(exc_type, exc_val, exc_tb):
        try:
            _write_crash((exc_type, exc_val, exc_tb))
            traceback.print_exception(exc_type, exc_val, exc_tb, file=sys.__stderr__)
        except Exception:
            pass
    app.report_callback_exception = _tk_exc_hook

    try:
        app.mainloop()
    except Exception:
        _write_crash(sys.exc_info())


if __name__ == "__main__":
    main()


