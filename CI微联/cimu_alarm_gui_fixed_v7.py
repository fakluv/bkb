# -*- coding: utf-8 -*-
import os
import re
import socket
import threading
import time
import traceback
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set

try:
    import pandas as pd
except Exception as exc:
    pd = None
    _PANDAS_IMPORT_ERROR = exc
else:
    _PANDAS_IMPORT_ERROR = None

try:
    import pymysql
except Exception as exc:
    pymysql = None
    _PYMYSQL_IMPORT_ERROR = exc
else:
    _PYMYSQL_IMPORT_ERROR = None


class PublicFunc:
    def deal_data(self, data, fix_hour=0, israndomtime=False, isformat=True,
                  time_type=1, return_data_type=1):
        return_time=[]
        regex=re.compile(r'(#)(.*)(#)')
        data1=regex.sub(r'', data if isinstance(data,str) else data.decode('utf-8'))
        data3=data1.upper().replace('\n','').replace('\t','').replace(' ','')
        while '[' in data3 and ']' in data3:
            si,ei=data3.index('['),data3.index(']')
            old=data3[si+1:ei]
            hour=fix_hour
            if time_type==1:
                if israndomtime:
                    import random; hour=random.randint(0,30*24)
                ori=int(time.time())-hour*3600
            else: ori=time.time()
            st=time.localtime(ori)
            part=self.fix_str(hex(st[1])[2:])+self.fix_str(hex(st[2])[2:])+self.fix_str(hex(st[3])[2:])+self.fix_str(hex(st[4])[2:])+self.fix_str(hex(st[5])[2:])
            rev='R' in old.upper(); th=old.replace('R',''); tl=len(th)
            if tl==8: hx=hex(int(ori))[2:]
            elif tl==12: hx=self.fix_str(hex(st[0]-2000)[2:])+part
            elif tl in (14,18):
                hx=self.fix_str(hex(st[0])[2:],4)+part
                if tl==18: hx+=self.fix_str(hex(int(str(ori-int(ori))[2:5]))[2:],4)
            else: hx=hex(int(ori))[2:]
            if rev: hx=self.str_reverse(hx)
            return_time.append(int(ori)); data3=data3[:si]+hx+data3[ei+1:]
        data4=data3; frame_len=0
        if '{' in data4 and '}' in data4:
            si,ei=data4.index('{'),data4.index('}'); f=data4[si+1:ei].replace('(','').replace(')','').replace('R',''); frame_len=len(f)//2; data4=data4.replace('{','').replace('}','')
        if '<' in data4 and '>' in data4:
            si,ei=data4.index('<'),data4.index('>'); f=data4[si+1:ei].replace('(','').replace(')','').replace('R',''); frame_len=len(f)//2; data4=data4.replace('<','').replace('>','')
        data5=data4.replace('（','(').replace('）',')')
        if '(' in data5 and ')' in data5:
            if frame_len:
                si,ei=data4.index('('),data4.index(')'); partlen=data4[si:ei+1]; n=self.int_to_hex(frame_len,len(partlen)-2); n=self.str_reverse(n) if 'R' in partlen else n; data5=data4[:si]+n+data4[ei+1:]
            else: data5=data4.replace('(','').replace(')','')
        result=self.data_format(data5) if isformat else data5
        return result if return_data_type==1 else (result,return_time[0])

    def data_format(self,data,num=2):
        data=data.replace(' ',''); return ' '.join(data[i:i+num] for i in range(0,len(data),num)).upper()
    def fix_str(self,data,num=2,ishead=True,fix_character='0'):
        data=str(data); return (fix_character*max(0,num-len(data))+data) if ishead else (data+fix_character*max(0,num-len(data)))
    def str_reverse(self,data,num=2):
        data=data.replace(' ',''); return ''.join(data[i:i+num] for i in range(len(data)-num,-1,-num))
    def str_to_bytes(self,str_data): return bytes.fromhex(str_data.upper().replace(' ',''))
    def bin_to_hex(self,data,fix_num=2): return self.fix_str(hex(int('0b'+self.fix_str(data.replace(' ',''),8),2))[2:],fix_num).upper()
    def int_to_hex(self,data,num=2):
        import math
        h=hex(int(data))[2:]; num=max(num,math.ceil(len(h)/2)*2) if len(h)>num else num; return self.fix_str(h,num).upper()

func=PublicFunc()


def split_row(s):
    out=[]
    for x in s.split(' '):
        if not x: continue
        out.extend(x.strip().split('\t'))
    return [x for x in out if x]


def get_excel_data(file_path,sheet_name):
    if pd is None: raise RuntimeError(f'缺少 pandas：{_PANDAS_IMPORT_ERROR}')
    df=pd.read_excel(file_path,sheet_name=sheet_name,header=None)
    alarms=[]; switches=[]; special=[]; maxbit=0; item=0; br=d=f=s=0
    bit_items=[]
    table_names={1:'Xin Hao Table',2:'Qu Duan Table',3:'Dao Cha Table',4:'Bao Jing Table',5:'Gong Neng Deng Table',6:'Biao Shi Deng Table',7:'Jin Lu Table',8:'Te Shu Delay Message'}
    name_index=None
    for idx in df.index.values:
        vals=df.loc[idx]
        row=''.join(f' {v}' for v in vals if 'nan' not in str(v).lower())
        if not row: continue
        parts=split_row(row)
        if not parts or 'sum' in row.lower(): continue
        if '[' in row and ']' in row:
            for k,t in table_names.items():
                if f'[{t}]' in row: item=k; name_index=None
            continue
        try:
            if '#' in row:
                if item==1: br=parts.index('Br')
                if item==3: d=parts.index('D'); f=parts.index('F')
                if item==4: s=parts.index('S')
                name_index=parts.index('NAME') if 'NAME' in parts else None
                continue
            name = ''
            if name_index is not None and name_index < len(parts):
                name = str(parts[name_index]).strip()
            if item==1:
                bit=int(parts[br]); alarms.append(bit); bit_items.append({'table':table_names[item],'bit':bit,'name':name})
            if item==3:
                di,fi=int(parts[d]),int(parts[f]); alarms += [di,fi]; special.append(di)
                bit_items.append({'table':table_names[item],'bit':di,'name':name})
                bit_items.append({'table':table_names[item],'bit':fi,'name':name})
            if item==4:
                bit=int(parts[s]); switches.append(bit); bit_items.append({'table':table_names[item],'bit':bit,'name':name})
            if '#' not in row and item and len(parts)>3:
                mb=int(parts[-3] if item==7 else parts[-2]); maxbit=max(maxbit,mb)
        except (ValueError,IndexError):
            continue
    return {'alarm_bit_indexs':sorted(set(alarms)),'switch_bit_indexs':sorted(set(switches)),'special_bit_index':sorted(set(special)),'max_bit_index':maxbit,'bit_items':bit_items}


def make_info2_code(d,is_alarm,is_switch,selected_alarm=None,selected_switch=None):
    bits=set()
    specials=set(d.get('special_bit_index', []))
    if selected_alarm is not None:
        bits.update(selected_alarm)
        specials=set()
    elif is_alarm:
        bits.update(d.get('alarm_bit_indexs', []))
        specials=set()
    if is_switch:
        bits.update(d.get('switch_bit_indexs', []) if selected_switch is None else selected_switch)
    max_bit=int(d.get('max_bit_index',0))
    raw=''.join('1' if i+1 in bits or i+1 in specials else '0' for i in range(max_bit))
    return ' '.join(func.bin_to_hex(func.fix_str(raw[i:i+8][::-1],8)) for i in range(0,len(raw),8))


def make_code(d,is_alarm,is_switch,selected_alarm=None,selected_switch=None):
    info=make_info2_code(d,is_alarm,is_switch,selected_alarm,selected_switch)
    if is_alarm:
        msg='01'
        info1='''
AA 55
00 00 00 00
00
00 00
00 00 00 00 00 00 00 00 00 00
00 00
00 00
00 00 00 00 00
00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00
'''
    else:
        msg='02'
        info1='''
AA 55
FF FF FF FF
F0
FA FA
F6 F6 F6 F6 F6 F6 F6 F6 F6 F6
55 55
55 55
00 00
00 00 00 00 00
00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00
'''
    code=f'''
AA #帧开始标识#
(01 6B) #帧长度#
{{40 #Message Type#
[5B F0 41 {msg}] #时间戳#
00 19 12 A9 #报文序列号#
00 A9 #联锁设备编号#
#info1信息#{info1}
#info2信息#
{info}
1F BB 5A A7 #CRC校验#}}
55 #帧结束标识#
'''
    return func.deal_data(code)


def make_raw_code(d,is_alarm,is_switch,selected_alarm=None,selected_switch=None):
    info=make_info2_code(d,is_alarm,is_switch,selected_alarm,selected_switch)
    if is_alarm:
        msg='01'
        info1='''AA 55
00 00 00 00
00
00 00
00 00 00 00 00 00 00 00 00 00
00 00
00 00
00 00 00 00 00
00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00'''
    else:
        msg='02'
        info1='''AA 55
FF FF FF FF
F0
FA FA
F6 F6 F6 F6 F6 F6 F6 F6 F6 F6
55 55
55 55
00 00
00 00 00 00 00
00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00'''
    return f'''AA #帧开始标识#
(01 6B) #帧长度#
{{40 #Message Type#
[5B F0 41 {msg}] #时间戳#
00 19 12 A9 #报文序列号#
00 A9 #联锁设备编号#
#info1信息#
{info1}
#info2信息#
{info}
1F BB 5A A7 #CRC校验#}}
55 #帧结束标识#'''

@dataclass
class ConnectionConfig:
    local_ip:str
    station_no:str=''
    station_name:str=''
    master:str=''
    enabled:bool=True
    file_path:str=''
    alarm_bits:Set[int]=field(default_factory=set)
    switch_bits:Set[int]=field(default_factory=set)
    excel_data:Optional[dict]=None
    server:object=None
    client:object=None
    thread:object=None
    sent_count:int=0
    bits_initialized:bool=False

class Worker:
    def __init__(self,cfg,dest_ip,port,stop_event,barrier,packet_factory,interval,log,status):
        self.cfg=cfg; self.dest_ip=dest_ip; self.port=port; self.stop=stop_event; self.barrier=barrier; self.packet_factory=packet_factory; self.interval=interval; self.log=log; self.status=status
    def close(self,s):
        if s:
            try:s.shutdown(socket.SHUT_RDWR)
            except:pass
            try:s.close()
            except:pass
    def run(self):
        server=client=None
        try:
            server=socket.socket(socket.AF_INET,socket.SOCK_STREAM); server.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1); server.settimeout(.5); server.bind((self.cfg.local_ip,self.port)); server.listen(5); self.cfg.server=server; self.status(self.cfg.local_ip,'等待目标连接'); self.log(f'[{self.cfg.local_ip}] TCP 服务端已启动')
            try:self.barrier.wait(timeout=10)
            except:pass
            while not self.stop.is_set():
                try:client,addr=server.accept()
                except socket.timeout:continue
                except OSError:break
                if addr[0]!=self.dest_ip: self.close(client); client=None; continue
                client.settimeout(.5); self.cfg.client=client; self.status(self.cfg.local_ip,f'已连接 {addr[0]}')
                while not self.stop.is_set():
                    try:
                        packet=self.packet_factory(self.cfg); client.sendall(func.str_to_bytes(packet)); self.cfg.sent_count+=1; self.status(self.cfg.local_ip,f'发送中 #{self.cfg.sent_count}')
                    except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError,OSError): break
                    except Exception as exc:
                        if not self.stop.is_set(): self.log(f'[{self.cfg.local_ip}] 发送异常：{exc}')
                        break
                    if self.stop.wait(self.interval):break
                self.close(client); self.cfg.client=None
                if not self.stop.is_set():self.status(self.cfg.local_ip,'客户端断开，继续等待')
        except Exception as exc:
            self.log(f'[{self.cfg.local_ip}] 启动失败：{exc}\n{traceback.format_exc()}'); self.status(self.cfg.local_ip,f'错误：{exc}')
        finally:
            self.close(client); self.close(server); self.cfg.client=None; self.cfg.server=None; self.status(self.cfg.local_ip,'已停止')

class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title('CIMU 报警/恢复报文发送工具'); self.geometry('1450x860'); self.minsize(1200,700)
        self.rows=[]; self.widgets=[]; self.running=False; self.stop_event=threading.Event(); self.workers=[]
        self.dest=tk.StringVar(value='192.168.1.134')
        self.master_no=tk.StringVar(value='1')
        self.port=tk.StringVar(value='10040')
        self.sheet=tk.StringVar(value='SDI码位')
        self.interval=tk.StringVar(value='1.5')
        self.startip=tk.StringVar(value='192.168.2.131')
        self.count=tk.StringVar(value='8')
        # 数据库连接参数（支持 Linux / Windows 上的 MySQL）
        self.db_host=tk.StringVar(value='192.168.1.134')
        self.db_port=tk.StringVar(value='3306')
        self.db_name=tk.StringVar(value='base')
        self.db_user=tk.StringVar(value='root')
        self.db_pass=tk.StringVar(value='mysql')
        self.send_mode=tk.StringVar(value='alarm')   # 报警/恢复 二选一
        self.switch=tk.BooleanVar(value=True)        # 开关量，独立选项
        self.testmode=tk.StringVar(value='full')
        self.all_enabled=tk.BooleanVar(value=True)
        self.status=tk.StringVar(value='未运行')
        self._ui(); self.protocol('WM_DELETE_WINDOW',self.close_app)

    def _ui(self):
        top=ttk.Frame(self,padding=8); top.pack(fill='x')
        ttk.Label(top,textvariable=self.status).pack(side='right')

        p=ttk.LabelFrame(self,text='参数',padding=8); p.pack(fill='x',padx=8,pady=(0,8))

        # 第 1 行：基础参数
        r0=ttk.Frame(p); r0.grid(row=0,column=0,sticky='w')
        fields=[('目标IP',self.dest,14),('master',self.master_no,12),('目标端口',self.port,8),
                ('Sheet',self.sheet,12),('间隔(s)',self.interval,7),
                ('起始本机IP',self.startip,15),('数量',self.count,6)]
        for i,(label,var,w) in enumerate(fields):
            ttk.Label(r0,text=label).grid(row=0,column=i*2,sticky='w')
            ttk.Entry(r0,textvariable=var,width=w).grid(row=0,column=i*2+1,padx=(4,12))

        # 第 2 行：数据库连接信息（支持 Linux / Windows 上的 MySQL）
        r1=ttk.Frame(p); r1.grid(row=1,column=0,sticky='w',pady=(8,0))
        dbfields=[('数据库IP',self.db_host,15),('端口',self.db_port,7),
                  ('数据库名',self.db_name,12),('账号',self.db_user,10),('密码',self.db_pass,10)]
        for i,(label,var,w) in enumerate(dbfields):
            ttk.Label(r1,text=label).grid(row=0,column=i*2,sticky='w')
            ttk.Entry(r1,textvariable=var,width=w).grid(row=0,column=i*2+1,padx=(4,12))
        ttk.Button(r1,text='获取数据库连接',command=self.load_db_connections).grid(row=0,column=10,padx=(4,0))

        # 第 3 行：发送模式 / 测试模式 / 连接生成
        r2=ttk.Frame(p); r2.grid(row=2,column=0,sticky='w',pady=(8,0))
        ttk.Label(r2,text='发送模式').grid(row=0,column=0,sticky='w')
        self.alarm_rb=ttk.Radiobutton(r2,text='报警',value='alarm',variable=self.send_mode)
        self.alarm_rb.grid(row=0,column=1,sticky='w')
        self.restore_rb=ttk.Radiobutton(r2,text='恢复',value='restore',variable=self.send_mode)
        self.restore_rb.grid(row=0,column=2,sticky='w')
        self.switch_cb=ttk.Checkbutton(r2,text='开关量',variable=self.switch)
        self.switch_cb.grid(row=0,column=3,sticky='w',padx=(12,0))
        ttk.Label(r2,text='测试模式').grid(row=0,column=4,sticky='w',padx=(30,0))
        ttk.Radiobutton(r2,text='全量模式',value='full',variable=self.testmode,command=self.mode_changed).grid(row=0,column=5,sticky='w')
        ttk.Radiobutton(r2,text='抽测模式',value='sample',variable=self.testmode,command=self.mode_changed).grid(row=0,column=6,sticky='w')
        ttk.Button(r2,text='批量生成连接',command=self.generate_rows).grid(row=0,column=7,padx=(30,8))
        ttk.Checkbutton(r2,text='全选连接',variable=self.all_enabled,command=self.toggle_all).grid(row=0,column=8)

        # 工具条：保留发送/停止
        tb=ttk.Frame(self,padding=(8,0,8,8)); tb.pack(fill='x')
        self.startb=ttk.Button(tb,text='发送报文',command=self.start_send); self.startb.pack(side='right',padx=6)
        self.stopb=ttk.Button(tb,text='停止发送',command=self.stop_send,state='disabled'); self.stopb.pack(side='right')

        lf=ttk.LabelFrame(self,text='连接列表',padding=5); lf.pack(fill='both',expand=True,padx=8,pady=(0,8)); self.canvas=tk.Canvas(lf,highlightthickness=0); self.scroll=ttk.Scrollbar(lf,orient='vertical',command=self.canvas.yview); self.container=ttk.Frame(self.canvas); self.container.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all'))); self.canvas.create_window((0,0),window=self.container,anchor='nw'); self.canvas.configure(yscrollcommand=self.scroll.set); self.canvas.pack(side='left',fill='both',expand=True); self.scroll.pack(side='right',fill='y')
        self.widths=[55,55,125,320,220,220,80,310]
        header=ttk.Frame(self.container); header.grid(row=0,column=0,sticky='ew',pady=(0,4)); titles=['启用','序号','本机 IP','文件','数据库站点','状态','已发送','操作']
        for i,(t,w) in enumerate(zip(titles,self.widths)): header.grid_columnconfigure(i,minsize=w,weight=0); ttk.Label(header,text=t,anchor='center').grid(row=0,column=i,sticky='ew')
        self.logtxt=tk.Text(self,height=8,wrap='none'); self.logtxt.pack(fill='x',padx=8,pady=(0,8))

    def db_summary(self,cfg):
        if cfg.station_no:
            return f"{cfg.station_no} {cfg.station_name}"
        return '未获取站点'

    def db_connect(self):
        if pymysql is None:
            raise RuntimeError(f'缺少 pymysql：{_PYMYSQL_IMPORT_ERROR}，请安装 pymysql')
        host = self.db_host.get().strip() or self.dest.get().strip()
        try:
            port = int(self.db_port.get().strip() or '3306')
        except ValueError:
            raise ValueError('数据库端口必须是数字')
        database = self.db_name.get().strip() or 'base'
        user = self.db_user.get().strip() or 'root'
        password = self.db_pass.get()
        # pymysql 连接对 MySQL 服务端所在操作系统透明：
        # 无论是 Linux 上的 MySQL 还是 Windows 上的 MySQL，只要通过 TCP/IP 提供 3306（或自定义端口）服务即可。
        return pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
            charset='utf8mb4',
            connect_timeout=5,
            read_timeout=10,
            write_timeout=10,
            autocommit=True,
        )

    def load_db_connections(self):
        master=self.master_no.get().strip()
        if not master:
            messagebox.showwarning('提示','请先填写 master 过滤值'); return
        try:
            conn=self.db_connect()
            with conn.cursor() as cur:
                cur.execute("SELECT b.STATION_NO,IP,STATION_NAME FROM dic_mss_netaddress_config a RIGHT JOIN dic_station b ON a.STATION_NO=b.STATION_NO WHERE a.SYS_NO=9 AND master=%s", (master,))
                rows=cur.fetchall()
            conn.close()
            found=[]
            seen=set()
            for r in rows:
                ip=str(r[1] or '').strip()
                if not ip or ip in seen:
                    continue
                seen.add(ip)
                found.append((ip, str(r[0] or ''), str(r[2] or '')))

            for ch in list(self.container.winfo_children())[1:]:
                ch.destroy()
            self.rows=[]
            self.widgets=[]
            for ip, station_no, station_name in found:
                cfg=ConnectionConfig(local_ip=ip, station_no=station_no,
                    station_name=station_name, master=master, enabled=True)
                self.add_row(cfg)
            self.update_bit_buttons()
            self.log(f'数据库获取完成：master={master}，创建 {len(found)} 条连接')
        except Exception as e:
            messagebox.showerror('数据库连接失败',str(e)); self.log(f'数据库获取失败：{e}')

    def validate_sql(self, cfg):
        if not cfg.station_no:
            raise ValueError('该连接尚未获取到 station_no，请先点击“获取数据库连接”')
        d = self.ensure_data(cfg)
        names = []
        for item in d.get('bit_items', []):
            if item['bit'] in cfg.alarm_bits and item.get('name'):
                names.append(item['name'])
        names = list(dict.fromkeys(names))
        if not names:
            raise ValueError('请先在抽测模式中勾选报警 bit，且 Excel NAME 列不能为空')

        conn = self.db_connect()
        try:
            placeholders = ','.join(['%s'] * len(names))
            sql = f"""
                select c.STATION_NAME, a.DEVICE_NAME
                from alarm_history a
                left join dic_cad_map_info b on a.DEVICE_NAME = b.name
                inner join dic_station c on b.STATION_NO = c.STATION_NO
                where a.SYS_NO=9
                  and a.DEVICE_NAME in ({placeholders})
                  and a.station_no=%s
                  and a.RECOVER_TIME is null
            """
            with conn.cursor() as cur:
                cur.execute(sql, tuple(names) + (cfg.station_no,))
                rows = cur.fetchall()

            result_map = {}
            for row in rows:
                station_name = str(row[0]) if row[0] is not None else ''
                device_name = str(row[1])
                result_map.setdefault(device_name, set()).add(station_name)

            result_set = set(result_map.keys())
            missing = [n for n in names if n not in result_set]

            missing_map = {}
            if missing:
                mp = ','.join(['%s'] * len(missing))
                sql2 = f"""
                    select a.name, b.STATION_NAME
                    from dic_cad_map_info a
                    left join dic_station b on a.station_no = b.STATION_NO
                    where a.name in ({mp})
                """
                with conn.cursor() as cur:
                    cur.execute(sql2, tuple(missing))
                    for name, station_name in cur.fetchall():
                        name = str(name)
                        station_name = str(station_name) if station_name is not None else ''
                        missing_map.setdefault(name, set()).add(station_name)
        finally:
            conn.close()

        def fmt(name, src_map, not_found_text):
            if name in src_map:
                locs = '、'.join(sorted(s for s in src_map[name] if s)) or '未获取到 STATION_NAME'
            else:
                locs = not_found_text
            return f'{name}（位于：{locs}）'

        matched_lines = [fmt(n, result_map, '未查询到') for n in names if n in result_set]
        missing_lines = [fmt(n, missing_map, '未查询到') for n in missing]

        dlg = tk.Toplevel(self)
        dlg.title(f'{cfg.local_ip} - SQL 校验')
        dlg.geometry('760x520')
        dlg.transient(self)
        dlg.grab_set()
        dlg.update_idletasks()
        self.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f'+{max(0, x)}+{max(0, y)}')

        ttk.Label(
            dlg,
            text=f"站点：{cfg.station_no} {cfg.station_name}\nSQL 查询返回 {len(rows)} 条，勾选报警名称 {len(names)} 个"
        ).pack(anchor='w', padx=12, pady=10)

        t = tk.Text(dlg, wrap='word')
        t.pack(fill='both', expand=True, padx=12, pady=5)
        t.insert(
            'end',
            '勾选的报警名称：\n' + '\n'.join(names) +
            '\n\n数据库匹配结果（报警名称 - STATION_NAME）：\n' +
            ('\n'.join(matched_lines) if matched_lines else '（无数据）') +
            '\n\n缺失报警名称：\n' +
            ('\n'.join(missing_lines) if missing_lines else '无缺失，全部匹配')
        )
        t.configure(state='disabled')
        ttk.Button(dlg, text='关闭', command=dlg.destroy).pack(anchor='e', padx=12, pady=10)

        self.log(f'[{cfg.local_ip}] SQL 校验：勾选 {len(names)}，查询 {len(rows)}，缺失 {len(missing)}')

    def mode_changed(self):
        self.update_bit_buttons()
        self.log(f'测试模式：{"全量模式" if self.testmode.get()=="full" else "抽测模式"}')

    def update_bit_buttons(self):
        sample = self.testmode.get() == 'sample'
        for w in self.widgets:
            w['bit'].configure(state='normal' if sample else 'disabled')
        st = 'disabled' if sample else 'normal'
        for ctrl in (getattr(self, 'alarm_rb', None),
                     getattr(self, 'restore_rb', None),
                     getattr(self, 'switch_cb', None)):
            if ctrl is not None:
                ctrl.configure(state=st)

    def log(self,msg): self.after(0,lambda:self._log(msg))
    def _log(self,msg): self.logtxt.insert('end',f'[{datetime.now():%H:%M:%S}] {msg}\n'); self.logtxt.see('end')
    def status_update(self,ip,msg):
        def f():
            for cfg,w in zip(self.rows,self.widgets):
                if cfg.local_ip==ip: w['status'].configure(text=msg); w['count'].configure(text=str(cfg.sent_count)); break
        self.after(0,f)
    def ip_int(self,ip):
        p=[int(x) for x in ip.strip().split('.')]
        if len(p)!=4 or any(x<0 or x>255 for x in p):raise ValueError('IP 地址非法')
        return (p[0]<<24)|(p[1]<<16)|(p[2]<<8)|p[3]
    def ip_str(self,n):
        if not 0<=n<=0xffffffff:raise ValueError('批量 IP 超出范围')
        return '.'.join(str((n>>s)&255) for s in (24,16,8,0))
    def generate_rows(self):
        if self.running:messagebox.showwarning('提示','发送过程中不能重新生成连接');return
        try:st=self.ip_int(self.startip.get()); num=int(self.count.get()); assert 1<=num<=1000
        except Exception as e:messagebox.showerror('参数错误',str(e));return
        old={r.local_ip:r for r in self.rows}; children=list(self.container.winfo_children());
        for ch in children[1:]:ch.destroy()
        self.rows=[]; self.widgets=[]
        for i in range(num):
            ip=self.ip_str(st+i); o=old.get(ip); cfg=ConnectionConfig(local_ip=ip, station_no=o.station_no if o else '', station_name=o.station_name if o else '', master=o.master if o else '', enabled=o.enabled if o else True, file_path=o.file_path if o else '', alarm_bits=set(o.alarm_bits) if o else set(), switch_bits=set(o.switch_bits) if o else set(), excel_data=o.excel_data if o else None, bits_initialized=o.bits_initialized if o else False); self.add_row(cfg)
        self.update_bit_buttons(); self.log(f'已生成 {num} 条连接')
    def add_row(self,cfg):
        self.rows.append(cfg); idx=len(self.rows); row=ttk.Frame(self.container); row.grid(row=idx,column=0,sticky='ew'); vars={}
        en=tk.BooleanVar(value=cfg.enabled); ttk.Checkbutton(row,variable=en,command=lambda c=cfg,v=en:setattr(c,'enabled',v.get())).grid(row=0,column=0,padx=2); ttk.Label(row,text=str(idx),anchor='center').grid(row=0,column=1,padx=2); ttk.Label(row,text=cfg.local_ip,anchor='center').grid(row=0,column=2,padx=2)
        filevar=tk.StringVar(value=os.path.basename(cfg.file_path) if cfg.file_path else '未选择'); fb=ttk.Frame(row); fb.grid(row=0,column=3,sticky='ew'); ttk.Label(fb,textvariable=filevar,anchor='w').pack(side='left',fill='x',expand=True); ttk.Button(fb,text='选择文件',width=9,command=lambda c=cfg,v=filevar:self.select_file(c,v)).pack(side='right')
        bits=tk.StringVar(value=self.db_summary(cfg)); ttk.Label(row,textvariable=bits,anchor='center').grid(row=0,column=4,sticky='ew'); sl=ttk.Label(row,text='未运行',anchor='w'); sl.grid(row=0,column=5,sticky='ew'); cl=ttk.Label(row,text='0',anchor='center'); cl.grid(row=0,column=6,sticky='ew'); op=ttk.Frame(row); op.grid(row=0,column=7,sticky='w'); bb=ttk.Button(op,text='查看开关量和报警bit位',command=lambda c=cfg,v=bits:self.bits_dialog(c,v)); bb.pack(side='left'); ttk.Button(op,text='预览报文',command=lambda c=cfg:self.preview(c)).pack(side='left',padx=4); ttk.Button(op,text='SQL校验',command=lambda c=cfg:self.validate_sql(c)).pack(side='left',padx=4)
        for col,w in enumerate(self.widths): row.grid_columnconfigure(col,minsize=w,weight=0)
        self.widgets.append({'enabled':en,'file':filevar,'bits':bits,'status':sl,'count':cl,'bit':bb})
    def toggle_all(self):
        v=self.all_enabled.get()
        for c,w in zip(self.rows,self.widgets):c.enabled=v; w['enabled'].set(v)
    def ensure_data(self,cfg):
        if not cfg.file_path:raise ValueError(f'{cfg.local_ip} 未选择 Excel 文件')
        if cfg.excel_data is None:cfg.excel_data=get_excel_data(cfg.file_path,self.sheet.get().strip() or 'SDI码位')
        return cfg.excel_data
    def select_file(self,cfg,var):
        path=filedialog.askopenfilename(filetypes=[('Excel','*.xls *.xlsx *.xlsm'),('All','*.*')]);
        if not path:return
        try:d=get_excel_data(path,self.sheet.get().strip() or 'SDI码位'); cfg.file_path=path; cfg.excel_data=d; cfg.alarm_bits=set(d['alarm_bit_indexs']); cfg.switch_bits=set(d['switch_bit_indexs']); cfg.bits_initialized=False; var.set(os.path.basename(path)); self.refresh_summary(cfg); self.log(f'[{cfg.local_ip}] 文件已选择')
        except Exception as e:messagebox.showerror('读取 Excel 失败',str(e))
    def refresh_summary(self,cfg):
        i=self.rows.index(cfg); self.widgets[i]['bits'].set(self.db_summary(cfg))
    def bits_dialog(self,cfg,label):
        if self.testmode.get()!='sample':messagebox.showinfo('提示','该按钮仅在抽测模式下可用');return
        try:d=self.ensure_data(cfg)
        except Exception as e:messagebox.showerror('提示',str(e));return
        dlg=tk.Toplevel(self); dlg.title(f'{cfg.local_ip} - 查看开关量和报警bit位'); dlg.geometry('1050x760'); dlg.transient(self); dlg.grab_set(); dlg.update_idletasks(); self.update_idletasks(); x=self.winfo_rootx()+(self.winfo_width()-dlg.winfo_width())//2; y=self.winfo_rooty()+(self.winfo_height()-dlg.winfo_height())//2; dlg.geometry(f'+{max(0,x)}+{max(0,y)}'); ttk.Label(dlg,text='抽测模式固定发送恢复报文；以下勾选 bit 会写入 Info2').pack(anchor='w',padx=10,pady=8)
        initial_alarm=set(cfg.alarm_bits) if cfg.bits_initialized else set()
        initial_switch=set(cfg.switch_bits) if cfg.bits_initialized else set()
        av={b:tk.BooleanVar(value=b in initial_alarm) for b in d['alarm_bit_indexs']}; sv={b:tk.BooleanVar(value=b in initial_switch) for b in d['switch_bit_indexs']}
        acts=ttk.Frame(dlg); acts.pack(fill='x',padx=10); ttk.Button(acts,text='报警全选',command=lambda:[v.set(True) for v in av.values()]).pack(side='left');ttk.Button(acts,text='报警全不选',command=lambda:[v.set(False) for v in av.values()]).pack(side='left',padx=4);ttk.Button(acts,text='开关量全选',command=lambda:[v.set(True) for v in sv.values()]).pack(side='left',padx=(15,4));ttk.Button(acts,text='开关量全不选',command=lambda:[v.set(False) for v in sv.values()]).pack(side='left');
        pane=ttk.Panedwindow(dlg,orient='horizontal');pane.pack(fill='both',expand=True,padx=10,pady=10)
        def group(title,vals,mp,kind):
            box=ttk.LabelFrame(pane,text=title,padding=6); cv=tk.Canvas(box,highlightthickness=0); sb=ttk.Scrollbar(box,orient='vertical',command=cv.yview); ct=ttk.Frame(cv);ct.bind('<Configure>',lambda e:cv.configure(scrollregion=cv.bbox('all'))); win=cv.create_window((0,0),window=ct,anchor='nw'); cv.bind('<Configure>',lambda e:cv.itemconfigure(win,width=e.width)); cv.bind('<MouseWheel>',lambda e:cv.yview_scroll(int(-e.delta/120),'units')); ct.bind('<MouseWheel>',lambda e:cv.yview_scroll(int(-e.delta/120),'units')); cv.bind('<Button-4>',lambda e:cv.yview_scroll(-1,'units')); cv.bind('<Button-5>',lambda e:cv.yview_scroll(1,'units')); cv.configure(yscrollcommand=sb.set);cv.pack(side='left',fill='both',expand=True);sb.pack(side='right',fill='y')
            items=[x for x in d.get('bit_items',[]) if x['bit'] in vals and ((kind=='alarm' and x['bit'] in d['alarm_bit_indexs']) or (kind=='switch' and x['bit'] in d['switch_bit_indexs']))]
            grouped={}
            for x in items: grouped.setdefault(x['table'],[]).append(x)
            row=0
            for table, entries in grouped.items():
                ttk.Label(ct,text=table,font=('Microsoft YaHei UI',10,'bold')).grid(row=row,column=0,columnspan=4,sticky='w',pady=(8,3)); row+=1
                for n,x in enumerate(entries):
                    label=f"Bit {x['bit']}：{x['name']}" if x['name'] else f"Bit {x['bit']}"
                    ttk.Checkbutton(ct,text=label,variable=mp[x['bit']]).grid(row=row,column=n%2,sticky='w',padx=10,pady=4)
                    if n%2==1: row+=1
                if len(entries)%2: row+=1
            pane.add(box,weight=1)
        group('报警 bit',list(av),av,'alarm'); group('开关量 bit',list(sv),sv,'switch')
        bot=ttk.Frame(dlg);bot.pack(fill='x',padx=10,pady=8)
        def save():
            cfg.alarm_bits={b for b,v in av.items() if v.get()}
            cfg.switch_bits={b for b,v in sv.items() if v.get()}
            cfg.bits_initialized=True
            label.set(self.db_summary(cfg))
            dlg.destroy()
        ttk.Button(bot,text='取消',command=dlg.destroy).pack(side='right');ttk.Button(bot,text='保存',command=save).pack(side='right',padx=6)

    def packet(self,cfg):
        d=self.ensure_data(cfg)
        if self.testmode.get()=='sample':
            return make_code(
                d,
                False,
                True,
                selected_alarm=set(cfg.alarm_bits),
                selected_switch=set(cfg.switch_bits),
            )
        is_alarm = self.send_mode.get() == 'alarm'
        use_switch = self.switch.get()
        return make_code(d, is_alarm, use_switch, selected_alarm=None, selected_switch=None)

    def preview(self,cfg):
        try:
            d=self.ensure_data(cfg)
            if self.testmode.get()=='sample':
                raw=make_raw_code(d,False,True,set(cfg.alarm_bits),set(cfg.switch_bits))
                send=make_code(d,False,True,set(cfg.alarm_bits),set(cfg.switch_bits))
                title='抽测模式：恢复报文 + 已选择报警/开关量 bit'
            else:
                is_alarm = self.send_mode.get() == 'alarm'
                use_switch = self.switch.get()
                raw=make_raw_code(d,is_alarm,use_switch)
                send=self.packet(cfg)
                title='全量模式：' + ('报警报文' if is_alarm else '恢复报文')
        except Exception as e:
            messagebox.showerror('预览失败',str(e));return

        dlg=tk.Toplevel(self)
        dlg.title(f'{cfg.local_ip} - 预览报文')
        dlg.geometry('1100x760')
        dlg.transient(self); dlg.update_idletasks(); self.update_idletasks(); x=self.winfo_rootx()+(self.winfo_width()-dlg.winfo_width())//2; y=self.winfo_rooty()+(self.winfo_height()-dlg.winfo_height())//2; dlg.geometry(f'+{max(0,x)}+{max(0,y)}')
        ttk.Label(dlg,text=title).pack(anchor='w',padx=10,pady=8)
        ttk.Label(dlg,text='原始报文（保留换行）').pack(anchor='w',padx=10)
        top=tk.Text(dlg,wrap='none',height=24)
        top.pack(fill='both',expand=True,padx=10,pady=(4,8))
        top.insert('1.0',raw)
        top.configure(state='disabled')
        ttk.Label(dlg,text='实际发送 HEX').pack(anchor='w',padx=10)
        bottom=tk.Text(dlg,wrap='word',height=8)
        bottom.pack(fill='both',expand=True,padx=10,pady=(4,10))
        bottom.insert('1.0',send)
        bottom.configure(state='disabled')

    def start_send(self):
        if self.running:return
        try:dest=self.dest.get().strip();self.ip_int(dest);port=int(self.port.get());interval=float(self.interval.get());assert 1<=port<=65535 and interval>0;active=[c for c in self.rows if c.enabled]; assert active
        except Exception as e:messagebox.showerror('参数错误',str(e));return
        try:
            for c in active:
                self.ensure_data(c)
                if self.testmode.get()=='sample' and not c.alarm_bits and not c.switch_bits:raise ValueError(f'{c.local_ip} 抽测模式至少选择一个 bit')
        except Exception as e:messagebox.showerror('启动失败',str(e));return
        self.stop_event.clear();self.running=True;bar=threading.Barrier(len(active));self.workers=[]
        for c in active:
            c.sent_count=0;w=Worker(c,dest,port,self.stop_event,bar,self.packet,interval,self.log,self.status_update);c.thread=threading.Thread(target=w.run,name='CIMU-'+c.local_ip,daemon=True);self.workers.append(w)
        for w in self.workers:w.cfg.thread.start()
        self.startb.configure(state='disabled');self.stopb.configure(state='normal');self.status.set(f'运行中：{len(active)} 条');self.log('所有启用连接并发启动')
    def stop_send(self):
        if not self.running:return
        self.stop_event.set()
        for c in self.rows:
            for s in (c.client,c.server):
                if s:
                    try:s.shutdown(socket.SHUT_RDWR)
                    except:pass
                    try:s.close()
                    except:pass
        threading.Thread(target=self._join_watch,daemon=True).start()
    def _join_watch(self):
        deadline=time.time()+5
        for w in self.workers:
            if w.cfg.thread:w.cfg.thread.join(max(0,deadline-time.time()))
        self.after(0,self._stopped)
    def _stopped(self):self.running=False;self.startb.configure(state='normal');self.stopb.configure(state='disabled');self.status.set('已停止');self.log('所有发送线程已停止')
    def close_app(self):
        if self.running:self.stop_send();time.sleep(.2)
        self.destroy()

if __name__=='__main__':App().mainloop()