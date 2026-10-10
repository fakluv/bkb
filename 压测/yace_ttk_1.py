import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
import socket
import threading
import time
import json
import random
import queue
import select
from datetime import datetime
import ipaddress
import binascii
from collections import deque
import os
import sys
import ttkbootstrap as tb

# 缓存文件路径（程序根目录，JSON格式）
CACHE_FILE = os.path.join(os.path.dirname(sys.argv[0]), "network_test_tool_cache.json")
# 内存优化配置
MAX_LOG_QUEUE_SIZE = 2000
MAX_LOG_LINES = 500
BATCH_PROCESS_SIZE = 50
TCP_RECV_BUFFER = 2048
UDP_RECV_BUFFER = 2048


class NetworkConnection:
    """网络连接类，处理单个TCP/UDP连接（支持TCP Server多客户端）"""

    def __init__(self, conn_id, sub_conn_id, config, data_queue):
        self.conn_id = conn_id
        self.sub_conn_id = sub_conn_id
        self.config = config
        self.data_queue = data_queue
        self.running = False
        self.socket = None
        self.thread = None
        self.bytes_sent = 0
        self.bytes_received = 0
        self.packets_sent = 0
        self.packets_received = 0
        self.connection_time = None
        self.client_socket = None  # 保留但不再主要使用（多客户端模式）
        self.clients_holder = []  # 存储所有活跃客户端 socket
        self.last_log_time = 0
        self.log_interval = 0.2

    def get_full_id(self):
        return f"{self.conn_id}.{self.sub_conn_id}" if self.sub_conn_id else str(self.conn_id)

    def get_client_count(self):
        """返回当前连接的客户端数量（仅对TCP Server有效）"""
        return len(self.clients_holder)

    def log(self, message, is_received=False, data=None, raw_data=None, force_log=False):
        current_time = time.time()
        if not force_log and current_time - self.last_log_time < self.log_interval:
            return
        self.last_log_time = current_time
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        display_data = None

        if raw_data is not None:
            try:
                if isinstance(raw_data, (bytes, bytearray)):
                    display_data = raw_data.hex(' ', 1)[:100]
                else:
                    display_data = str(raw_data)[:100]
            except:
                display_data = "数据解析失败"
        elif data is not None:
            display_data = str(data)[:100]

        log_entry = {
            'conn_id': self.conn_id,
            'sub_conn_id': self.sub_conn_id,
            'full_conn_id': self.get_full_id(),
            'timestamp': timestamp,
            'message': message[:50],
            'is_received': is_received,
            'data': display_data,
            'stats': {
                'bytes_sent': self.bytes_sent,
                'bytes_received': self.bytes_received,
                'packets_sent': self.packets_sent,
                'packets_received': self.packets_received
            }
        }

        try:
            self.data_queue.put(log_entry, timeout=0.001)
        except queue.Full:
            try:
                self.data_queue.get_nowait()
                self.data_queue.put(log_entry, timeout=0.001)
            except:
                pass

    def create_socket(self):
        try:
            protocol = self.config.get('protocol', 'TCP Client')
            if protocol == 'TCP Client':
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            elif protocol == 'TCP Server':
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            elif protocol == 'UDP':
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            else:
                raise ValueError(f"不支持的协议: {protocol}")

            if protocol in ['TCP Client', 'TCP Server']:
                self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            src_ip = self.config.get('src_ip', '0.0.0.0')
            src_port = int(self.config.get('src_port', 0))

            if protocol == 'TCP Server':
                if src_port == 0:
                    raise ValueError("TCP Server必须指定源端口")
                self.socket.bind((src_ip, src_port))
                self.log(f"TCP Server已监听 {src_ip}:{src_port}", force_log=True)
            elif src_ip and src_port:
                self.socket.bind((src_ip, src_port))
                self.log(f"已绑定源IP: {src_ip}:{src_port}")
            return True
        except Exception as e:
            self.log(f"创建套接字失败: {str(e)}", force_log=True)
            return False

    def _get_send_data(self):
        data_content = self.config.get('data', '')
        data_type = self.config.get('data_type', 'hex')
        encoding = self.config.get('encoding', 'utf-8')
        if not data_content:
            return b''

        try:
            if data_type == 'hex':
                clean_data = data_content.replace(' ', '').replace('\n', '').replace('\r', '')
                return binascii.unhexlify(clean_data) if clean_data else b''
            else:
                return data_content.encode(encoding)
        except Exception as e:
            self.log(f"数据处理失败: {str(e)}", force_log=True)
            return b''

    def _send_data_to_socket(self, sock):
        try:
            data_bytes = self._get_send_data()
            if not data_bytes:
                return
            sent = sock.send(data_bytes)
            self.bytes_sent += sent
            self.packets_sent += 1
            self.log(f"发送数据 (长度: {sent}字节)", raw_data=data_bytes)
        except BrokenPipeError:
            self.log("客户端已断开", force_log=True)
            sock.close()
            if sock in self.clients_holder:
                self.clients_holder.remove(sock)
        except Exception as e:
            self.log(f"发送失败: {str(e)}", force_log=True)
            sock.close()
            if sock in self.clients_holder:
                self.clients_holder.remove(sock)

    def _run_tcp_server(self):
        """TCP Server 主循环 - 支持多客户端并发"""
        try:
            self.socket.listen(5)  # 最大等待连接数
            self.socket.settimeout(0.5)  # 超时以便检查 running 标志
            self.log("TCP Server 开始监听，支持多客户端并发", force_log=True)

            last_send_time = time.time()
            interval_ms = self.config.get('interval_ms', 1000)
            send_data = self._get_send_data()  # 预取发送数据

            while self.running:
                current_time = time.time()

                # --- 1. 接受新连接（非阻塞超时） ---
                try:
                    client_sock, client_addr = self.socket.accept()
                    client_sock.setblocking(False)
                    client_sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    self.clients_holder.append(client_sock)
                    self.log(f"接受客户端连接: {client_addr}", force_log=True)
                except socket.timeout:
                    pass  # 超时正常，继续循环
                except OSError as e:
                    # 如果套接字已被关闭（如调用了 stop），则退出循环
                    if "closed" in str(e).lower() or "10038" in str(e):
                        self.log("监听套接字已关闭，退出服务", force_log=True)
                        break
                    else:
                        self.log(f"接受连接异常: {str(e)}", force_log=True)
                        # 其他错误，继续尝试
                except Exception as e:
                    self.log(f"接受连接失败: {str(e)}", force_log=True)
                    if not self.running:
                        break

                # --- 2. 发送数据给所有客户端（按间隔） ---
                if send_data and current_time - last_send_time >= interval_ms / 1000.0:
                    # 复制客户端列表，避免在迭代时修改
                    for sock in self.clients_holder[:]:
                        try:
                            sent = sock.send(send_data)
                            self.bytes_sent += sent
                            self.packets_sent += 1
                            self.log(f"发送数据 (长度: {sent}字节) 到 {sock.getpeername()}", raw_data=send_data)
                        except (BrokenPipeError, ConnectionResetError):
                            self.log(f"客户端 {sock.getpeername()} 断开 (发送失败)", force_log=True)
                            sock.close()
                            self.clients_holder.remove(sock)
                        except Exception as e:
                            self.log(f"发送数据到 {sock.getpeername()} 失败: {str(e)}", force_log=True)
                            sock.close()
                            self.clients_holder.remove(sock)
                    last_send_time = current_time

                # --- 3. 接收所有客户端的数据（非阻塞） ---
                if self.clients_holder:
                    try:
                        readable, _, _ = select.select(self.clients_holder, [], [], 0.1)
                        for sock in readable:
                            try:
                                recv_data = sock.recv(TCP_RECV_BUFFER)
                                if recv_data:
                                    self.bytes_received += len(recv_data)
                                    self.packets_received += 1
                                    self.log(f"接收客户端 {sock.getpeername()} 数据 (长度: {len(recv_data)}字节)",
                                             is_received=True, raw_data=recv_data)
                                else:
                                    # 客户端正常关闭连接
                                    self.log(f"客户端 {sock.getpeername()} 断开连接", force_log=True)
                                    sock.close()
                                    self.clients_holder.remove(sock)
                            except (ConnectionResetError, BrokenPipeError):
                                self.log(f"客户端 {sock.getpeername()} 异常断开", force_log=True)
                                sock.close()
                                self.clients_holder.remove(sock)
                            except Exception as e:
                                self.log(f"接收客户端 {sock.getpeername()} 数据失败: {str(e)}", force_log=True)
                                sock.close()
                                self.clients_holder.remove(sock)
                    except Exception as e:
                        self.log(f"select 错误: {str(e)}", force_log=True)
                        # 如果 select 出错，可能套接字已被关闭，尝试清理
                        for sock in self.clients_holder[:]:
                            try:
                                sock.close()
                            except:
                                pass
                        self.clients_holder.clear()
                        if not self.running:
                            break

        except Exception as e:
            self.log(f"TCP Server 运行异常: {str(e)}", force_log=True)
        finally:
            # 清理所有客户端连接
            for sock in self.clients_holder:
                try:
                    sock.close()
                except:
                    pass
            self.clients_holder.clear()
            self.log("TCP Server 已停止", force_log=True)

    def _run_tcp_client(self, dst_ip, dst_port, interval_ms):
        try:
            self.socket.connect((dst_ip, dst_port))
            self.socket.setblocking(0)
            self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.log(f"已连接到 {dst_ip}:{dst_port}")
            last_send_time = time.time()
            data_bytes = self._get_send_data()

            while self.running:
                current_time = time.time()
                if current_time - last_send_time >= interval_ms / 1000 and data_bytes:
                    try:
                        sent = self.socket.send(data_bytes)
                        self.bytes_sent += sent
                        self.packets_sent += 1
                        self.log(f"发送数据 (长度: {sent}字节)", raw_data=data_bytes)
                        last_send_time = current_time
                    except Exception as e:
                        self.log(f"发送失败: {str(e)}", force_log=True)
                        break

                try:
                    readable, _, _ = select.select([self.socket], [], [], 0.1)
                    if readable:
                        recv_data = self.socket.recv(TCP_RECV_BUFFER)
                        if recv_data:
                            self.bytes_received += len(recv_data)
                            self.packets_received += 1
                            self.log(f"接收数据 (长度: {len(recv_data)}字节)",
                                     is_received=True, raw_data=recv_data)
                        else:
                            self.log("TCP连接被远端关闭", force_log=True)
                            break
                except Exception as e:
                    self.log(f"接收失败: {str(e)}", force_log=True)
                    break
        except Exception as e:
            self.log(f"TCP Client连接失败: {str(e)}", force_log=True)
        finally:
            self.socket.close()

    def _run_udp(self, dst_ip, dst_port, interval_ms):
        data_bytes = self._get_send_data()
        last_send_time = time.time()
        while self.running:
            current_time = time.time()
            if current_time - last_send_time >= interval_ms / 1000 and data_bytes:
                try:
                    sent = self.socket.sendto(data_bytes, (dst_ip, dst_port))
                    self.bytes_sent += sent
                    self.packets_sent += 1
                    self.log(f"发送数据 (长度: {sent}字节)", raw_data=data_bytes)
                    last_send_time = current_time
                except Exception as e:
                    self.log(f"发送失败: {str(e)}", force_log=True)
                    break

            try:
                readable, _, _ = select.select([self.socket], [], [], 0.1)
                if readable:
                    recv_data, addr = self.socket.recvfrom(UDP_RECV_BUFFER)
                    self.bytes_received += len(recv_data)
                    self.packets_received += 1
                    self.log(f"从{addr}接收数据 (长度: {len(recv_data)}字节)",
                             is_received=True, raw_data=recv_data)
            except Exception as e:
                self.log(f"接收失败: {str(e)}", force_log=True)
                break

    def start(self):
        if self.running:
            return
        self.running = True
        self.connection_time = datetime.now()
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        self.log("连接已启动")

    def _run_loop(self):
        try:
            if not self.create_socket():
                self.running = False
                return
            protocol = self.config.get('protocol', 'TCP Client')
            interval_ms = self.config.get('interval_ms', 1000)
            if protocol == 'TCP Server':
                self._run_tcp_server()
            else:
                dst_ip = self.config.get('dst_ip', '127.0.0.1')
                dst_port = int(self.config.get('dst_port', 8080))
                if protocol == 'TCP Client':
                    self._run_tcp_client(dst_ip, dst_port, interval_ms)
                elif protocol == 'UDP':
                    self._run_udp(dst_ip, dst_port, interval_ms)
        except Exception as e:
            self.log(f"运行异常: {str(e)}", force_log=True)
        finally:
            self.stop()

    def stop(self):
        if not self.running:
            return
        self.running = False
        # 关闭所有客户端连接
        for sock in self.clients_holder:
            try:
                sock.close()
            except:
                pass
        self.clients_holder.clear()
        # 关闭监听套接字
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.connection_time = None
        self.log("服务已停止", force_log=True)


class MultiConnectionGroup:
    """多连接组，支持序列化和内存优化"""

    def __init__(self, group_id, group_name, base_config, global_config, data_queue):
        self.group_id = group_id
        self.group_name = group_name
        self.base_config = base_config
        self.global_config = global_config
        self.data_queue = data_queue
        self.sub_connections = []
        self.running = False

        self.src_ips = self._parse_list(base_config.get('src_ips', ''))
        self.src_ports = self._parse_list(base_config.get('src_ports', ''))
        self.send_datas = self._parse_hex_datas(base_config.get('send_datas', ''))
        self._validate_and_adjust_lists()

    def _parse_list(self, input_str):
        if not input_str:
            return []
        return [item.strip() for item in input_str.split(';') if item.strip()]

    def _parse_hex_datas(self, input_str):
        if not input_str:
            return []
        data_strings = input_str.split('<br>')
        parsed_datas = []
        for data_str in data_strings:
            if not data_str.strip():
                continue
            hex_chars = [c.upper() for c in data_str if c in '0123456789ABCDEFabcdef']
            hex_str = ''.join(hex_chars)
            if len(hex_str) % 2 != 0:
                hex_str = '0' + hex_str
            parsed_datas.append(hex_str)
        return parsed_datas

    def _validate_and_adjust_lists(self):
        protocol = self.base_config.get('protocol', 'TCP Client')
        if protocol == 'TCP Server':
            if not self.src_ports:
                self.src_ports = ['8080', '8081', '8082']
            if not self.src_ips:
                self.src_ips = ['0.0.0.0'] * len(self.src_ports)
            if len(self.src_ips) < len(self.src_ports):
                last_ip = self.src_ips[-1] if self.src_ips else '0.0.0.0'
                while len(self.src_ips) < len(self.src_ports):
                    self.src_ips.append(last_ip)
        else:
            max_len = max(len(self.src_ips), len(self.src_ports), len(self.send_datas))
            while len(self.src_ips) < max_len:
                if self.src_ips:
                    try:
                        ip_parts = list(map(int, self.src_ips[-1].split('.')))
                        ip_parts[-1] += 1
                        if ip_parts[-1] > 255:
                            ip_parts[-1] = 1
                        new_ip = '.'.join(map(str, ip_parts))
                        self.src_ips.append(new_ip)
                    except:
                        self.src_ips.append(f"192.168.2.{len(self.src_ips) + 1}")
                else:
                    self.src_ips.append(f"192.168.2.{len(self.src_ips) + 1}")
            while len(self.src_ports) < max_len:
                if self.src_ports:
                    try:
                        new_port = int(self.src_ports[-1]) + 1
                        if new_port > 65535:
                            new_port = 10000 + len(self.src_ports)
                        self.src_ports.append(str(new_port))
                    except:
                        self.src_ports.append(str(10000 + len(self.src_ports)))
                else:
                    self.src_ports.append(str(10000 + len(self.src_ports)))
        while len(self.send_datas) < len(self.src_ports):
            self.send_datas.append(self.send_datas[-1] if self.send_datas else "2355" * 10)

    def create_sub_connections(self):
        self.sub_connections.clear()
        protocol = self.base_config.get('protocol', 'TCP Client')
        for idx in range(len(self.src_ports)):
            sub_config = self.global_config.copy()
            sub_config.update({
                'src_ip': self.src_ips[idx],
                'src_port': self.src_ports[idx],
                'data': self.send_datas[idx],
                'protocol': protocol,
                'data_type': self.base_config.get('data_type', self.global_config.get('data_type', 'hex')),
                'encoding': self.base_config.get('encoding', self.global_config.get('encoding', 'utf-8')),
                'interval_ms': self.base_config.get('interval_ms', self.global_config.get('interval_ms', 1000))
            })
            if protocol != 'TCP Server':
                sub_config.update({
                    'dst_ip': self.base_config.get('dst_ip', '127.0.0.1'),
                    'dst_port': self.base_config.get('dst_port', '8080')
                })
            else:
                sub_config['dst_ip'] = ''
                sub_config['dst_port'] = ''
            sub_conn = NetworkConnection(
                conn_id=self.group_id,
                sub_conn_id=idx + 1,
                config=sub_config,
                data_queue=self.data_queue
            )
            sub_conn.log_interval = self.global_config.get('log_interval', 0.2)
            self.sub_connections.append(sub_conn)

    def start(self):
        if self.running:
            return False
        self.create_sub_connections()
        self.running = True
        for sub_conn in self.sub_connections:
            sub_conn.start()
        return True

    def stop(self):
        self.running = False
        for sub_conn in self.sub_connections:
            sub_conn.stop()
        self.sub_connections.clear()

    def is_running(self):
        return any(sub_conn.running for sub_conn in self.sub_connections) if self.sub_connections else False

    def get_stats(self):
        total_stats = {
            'bytes_sent': 0,
            'bytes_received': 0,
            'packets_sent': 0,
            'packets_received': 0,
            'active_sub_conns': 0,
            'total_sub_conns': len(self.sub_connections)
        }
        for sub_conn in self.sub_connections:
            total_stats['bytes_sent'] += sub_conn.bytes_sent
            total_stats['bytes_received'] += sub_conn.bytes_received
            total_stats['packets_sent'] += sub_conn.packets_sent
            total_stats['packets_received'] += sub_conn.packets_received
            if sub_conn.running:
                # 对于 TCP Server，统计实际连接的客户端数；其他协议统计子连接是否运行
                if sub_conn.config.get('protocol') == 'TCP Server':
                    total_stats['active_sub_conns'] += sub_conn.get_client_count()
                else:
                    total_stats['active_sub_conns'] += 1
        return total_stats

    def update_global_config(self, new_global_config):
        self.global_config = new_global_config
        if self.running:
            self.stop()
            self.start()
        for sub_conn in self.sub_connections:
            sub_conn.log_interval = new_global_config.get('log_interval', 0.2)

    def update_group_name(self, new_name):
        self.group_name = new_name


class ConnectionDialog:
    """连接配置对话框"""

    def __init__(self, parent, title, config=None):
        self.parent = parent
        self.config = config
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("500x750")
        self.dialog.transient(parent)
        self.dialog.grab_set()

        ttk.Label(self.dialog, text="协议类型:").pack(anchor=tk.W, padx=20, pady=(20, 5))
        self.protocol_var = tk.StringVar(value="TCP Client")
        self.protocol_combo = ttk.Combobox(self.dialog, textvariable=self.protocol_var,
                                           values=["TCP Client", "TCP Server", "UDP"], state="readonly")
        self.protocol_combo.pack(fill=tk.X, padx=20, pady=5)

        ttk.Label(self.dialog, text="数据类型:").pack(anchor=tk.W, padx=20, pady=5)
        self.data_type_var = tk.StringVar(value="hex")
        self.data_type_combo = ttk.Combobox(self.dialog, textvariable=self.data_type_var,
                                            values=["hex", "text"], state="readonly")
        self.data_type_combo.pack(fill=tk.X, padx=20, pady=5)

        ttk.Label(self.dialog, text="编码格式:").pack(anchor=tk.W, padx=20, pady=5)
        self.encoding_var = tk.StringVar(value="utf-8")
        self.encoding_combo = ttk.Combobox(self.dialog, textvariable=self.encoding_var,
                                           values=["utf-8", "gbk", "gb2312"], state="readonly")
        self.encoding_combo.pack(fill=tk.X, padx=20, pady=5)

        ttk.Label(self.dialog, text="发送间隔(ms):").pack(anchor=tk.W, padx=20, pady=5)
        self.interval_var = tk.StringVar(value="1000")
        self.interval_entry = ttk.Entry(self.dialog, textvariable=self.interval_var)
        self.interval_entry.pack(fill=tk.X, padx=20, pady=5)

        ttk.Label(self.dialog, text="源IP地址 (多个用分号分隔):").pack(anchor=tk.W, padx=20, pady=5)
        self.src_ips_var = tk.StringVar(value="0.0.0.0" if self.config and self.config.get(
            'protocol') == 'TCP Server' else "192.168.2.1;192.168.2.2;192.168.2.3")
        self.src_ips_entry = ttk.Entry(self.dialog, textvariable=self.src_ips_var)
        self.src_ips_entry.pack(fill=tk.X, padx=20, pady=5)

        ttk.Label(self.dialog, text="源端口 (多个用分号分隔):").pack(anchor=tk.W, padx=20, pady=5)
        default_ports = "8080;8081;8082" if self.config and self.config.get(
            'protocol') == 'TCP Server' else "10001;10002;10003"
        self.src_ports_var = tk.StringVar(value=default_ports)
        self.src_ports_entry = ttk.Entry(self.dialog, textvariable=self.src_ports_var)
        self.src_ports_entry.pack(fill=tk.X, padx=20, pady=5)

        self.dst_frame = ttk.Frame(self.dialog)
        self.dst_frame.pack(fill=tk.X, padx=20, pady=5)
        ttk.Label(self.dst_frame, text="目的IP地址:").pack(anchor=tk.W, pady=5)
        self.dst_ip_var = tk.StringVar(value="192.168.1.219")
        self.dst_ip_entry = ttk.Entry(self.dst_frame, textvariable=self.dst_ip_var)
        self.dst_ip_entry.pack(fill=tk.X, pady=5)
        ttk.Label(self.dst_frame, text="目的端口:").pack(anchor=tk.W, pady=5)
        self.dst_port_var = tk.StringVar(value="8080")
        self.dst_port_entry = ttk.Entry(self.dst_frame, textvariable=self.dst_port_var)
        self.dst_port_entry.pack(fill=tk.X, pady=5)

        ttk.Label(self.dialog, text="发送数据 (多个用<br>分隔):").pack(anchor=tk.W, padx=20, pady=5)
        self.data_text = tk.Text(self.dialog, height=8)
        self.data_text.pack(fill=tk.X, padx=20, pady=5)
        default_data = "23 55 23 55 23 55 23 55 23 55<br>24 55 23 55 23 55 23 55 23 55<br>25 55 23 55 23 55 23 55 23 55"
        self.data_text.insert(1.0, default_data)

        self.button_frame = ttk.Frame(self.dialog)
        self.button_frame.pack(fill=tk.X, padx=20, pady=20)
        ttk.Button(self.button_frame, text="确定", command=self._on_ok).grid(row=0, column=0, padx=5)
        ttk.Button(self.button_frame, text="取消", command=self._on_cancel).grid(row=0, column=1, padx=5)
        self.button_frame.grid_columnconfigure(0, weight=1)
        self.button_frame.grid_columnconfigure(1, weight=1)

        self.protocol_var.trace('w', self._on_protocol_change)
        if config:
            self._fill_config_data()
        self._on_protocol_change()

    def _on_protocol_change(self, *args):
        protocol = self.protocol_var.get()
        if protocol == 'TCP Server':
            self.dst_frame.pack_forget()
        else:
            self.dst_frame.pack(fill=tk.X, padx=20, pady=5)

    def _fill_config_data(self):
        self.protocol_var.set(self.config.get('protocol', 'TCP Client'))
        self.data_type_var.set(self.config.get('data_type', 'hex'))
        self.encoding_var.set(self.config.get('encoding', 'utf-8'))
        self.interval_var.set(str(self.config.get('interval_ms', 1000)))
        self.src_ips_var.set(self.config.get('src_ips', ''))
        self.src_ports_var.set(self.config.get('src_ports', ''))
        if self.config.get('protocol') != 'TCP Server':
            self.dst_ip_var.set(self.config.get('dst_ip', '127.0.0.1'))
            self.dst_port_var.set(self.config.get('dst_port', '8080'))
        self.data_text.delete(1.0, tk.END)
        self.data_text.insert(1.0, self.config.get('send_datas', ''))

    def show(self):
        self.parent.wait_window(self.dialog)
        return self.result

    def _on_ok(self):
        try:
            protocol = self.protocol_var.get()
            config = {
                'protocol': protocol,
                'data_type': self.data_type_var.get(),
                'encoding': self.encoding_var.get(),
                'interval_ms': int(self.interval_var.get()),
                'src_ips': self.src_ips_var.get(),
                'src_ports': self.src_ports_var.get(),
                'send_datas': self.data_text.get(1.0, tk.END).strip()
            }
            if config['interval_ms'] < 10:
                raise ValueError("发送间隔不能小于10ms")
            src_ips = [ip.strip() for ip in config['src_ips'].split(';') if ip.strip()]
            src_ports = [port.strip() for port in config['src_ports'].split(';') if port.strip()]
            if not src_ports:
                raise ValueError("源端口不能为空")
            for ip in src_ips:
                if ip and ip != '0.0.0.0':
                    ipaddress.ip_address(ip)
            for port in src_ports:
                port_int = int(port)
                if not (0 <= port_int <= 65535):
                    raise ValueError(f"无效的源端口: {port}")
            if protocol == 'TCP Server':
                if len(src_ports) != len(set(src_ports)):
                    raise ValueError("TCP Server的源端口不能重复")
                config['dst_ip'] = ''
                config['dst_port'] = ''
            else:
                if not self.dst_ip_var.get():
                    raise ValueError("目的IP地址不能为空")
                ipaddress.ip_address(self.dst_ip_var.get())
                if not self.dst_port_var.get():
                    raise ValueError("目的端口不能为空")
                dst_port_int = int(self.dst_port_var.get())
                if not (0 <= dst_port_int <= 65535):
                    raise ValueError("目的端口必须在0-65535之间")
                config['dst_ip'] = self.dst_ip_var.get()
                config['dst_port'] = self.dst_port_var.get()
            self.result = config
            self.dialog.destroy()
        except ValueError as e:
            messagebox.showerror("输入错误", f"配置无效: {str(e)}")
        except Exception as e:
            messagebox.showerror("错误", f"未知错误: {str(e)}")

    def _on_cancel(self):
        self.result = None
        self.dialog.destroy()


class NetworkTestTool:
    """主工具类，支持JSON缓存和内存优化"""

    def __init__(self, root):
        self.root = root
        self.root.title("TCP/UDP网络压测工具（多源IP+TCP Server）")
        self.root.geometry("1400x900")

        self.global_config = {
            'data_type': 'hex',
            'encoding': 'utf-8',
            'data': '',
            'interval_ms': 1000,
            'log_interval': 0.2
        }
        self.connection_groups = {}
        self.group_count = 0
        self.data_queue = queue.Queue(maxsize=MAX_LOG_QUEUE_SIZE)
        self.last_stats_update = 0
        self.stats_update_interval = 1.0
        self.log_update_interval = 0.2
        self.max_log_lines = MAX_LOG_LINES
        self.batch_size = BATCH_PROCESS_SIZE

        # 存储每个组的 ScrolledText 引用，避免通过索引获取
        self.group_send_texts = {}
        self.group_log_texts = {}

        self.setup_ui()
        self.load_cache()
        self.start_queue_processor()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        control_frame = ttk.LabelFrame(main_frame, text="控制面板", padding=10)
        control_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))

        global_frame = ttk.LabelFrame(control_frame, text="全局配置", padding=10)
        global_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(global_frame, text="数据类型:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.data_type_var = tk.StringVar(value=self.global_config['data_type'])
        self.data_type_combo = ttk.Combobox(global_frame, textvariable=self.data_type_var,
                                            values=["hex", "text"], state="readonly")
        self.data_type_combo.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(global_frame, text="编码格式:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.encoding_var = tk.StringVar(value=self.global_config['encoding'])
        self.encoding_combo = ttk.Combobox(global_frame, textvariable=self.encoding_var,
                                           values=["utf-8", "gbk", "gb2312"], state="readonly")
        self.encoding_combo.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(global_frame, text="发送数据:").grid(row=2, column=0, sticky=tk.NW, padx=5, pady=2)
        self.data_text = tk.Text(global_frame, height=5, width=30)
        self.data_text.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        self.data_text.insert(1.0, self.global_config['data'])

        ttk.Label(global_frame, text="发送间隔(ms):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.interval_var = tk.StringVar(value=str(self.global_config['interval_ms']))
        self.interval_entry = ttk.Entry(global_frame, textvariable=self.interval_var, width=10)
        self.interval_entry.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)

        perf_frame = ttk.LabelFrame(control_frame, text="性能设置", padding=10)
        perf_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(perf_frame, text="日志频率限制(秒):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.log_interval_var = tk.StringVar(value=str(self.global_config['log_interval']))
        self.log_interval_entry = ttk.Entry(perf_frame, textvariable=self.log_interval_var, width=10)
        self.log_interval_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Button(perf_frame, text="应用频率设置", command=self.apply_log_interval).grid(row=0, column=2, sticky=tk.W,
                                                                                          padx=5, pady=2)

        btn_frame = ttk.Frame(control_frame)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="添加多源连接组", command=self.add_connection_group).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="批量启动所有组", command=self.start_all_groups).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="批量停止所有组", command=self.stop_all_groups).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="应用全局配置", command=self.apply_global_config).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="清空所有日志", command=self.clear_all_logs).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="重命名连接组", command=self.rename_selected_group).pack(fill=tk.X, pady=2)

        self.conn_list_frame = ttk.LabelFrame(control_frame, text="连接组列表", padding=10)
        self.conn_list_frame.pack(fill=tk.BOTH, expand=True)
        self.conn_listbox = tk.Listbox(self.conn_list_frame, height=15)
        self.conn_listbox.pack(fill=tk.BOTH, expand=True)
        self.conn_listbox.bind('<<ListboxSelect>>', self.on_group_select)

        self.detail_frame = ttk.Frame(main_frame)
        self.detail_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(self.detail_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.overview_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.overview_tab, text="概览")
        self.setup_overview_tab()

        self.status_var = tk.StringVar(value="就绪 - JSON缓存，内存优化")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.update_group_list()

    def setup_overview_tab(self):
        stats_frame = ttk.LabelFrame(self.overview_tab, text="统计信息", padding=10)
        stats_frame.pack(fill=tk.X, padx=5, pady=5)
        self.active_connections_var = tk.StringVar(value="活动连接: 0/0")
        self.total_sent_var = tk.StringVar(value="总发送: 0 字节")
        self.total_received_var = tk.StringVar(value="总接收: 0 字节")
        self.log_queue_var = tk.StringVar(value="日志队列: 0")
        self.active_threads_var = tk.StringVar(value="活动线程: 0")
        ttk.Label(stats_frame, textvariable=self.active_connections_var).pack(anchor=tk.W)
        ttk.Label(stats_frame, textvariable=self.total_sent_var).pack(anchor=tk.W)
        ttk.Label(stats_frame, textvariable=self.total_received_var).pack(anchor=tk.W)
        ttk.Label(stats_frame, textvariable=self.log_queue_var).pack(anchor=tk.W)
        ttk.Label(stats_frame, textvariable=self.active_threads_var).pack(anchor=tk.W)

        log_frame = ttk.LabelFrame(self.overview_tab, text="全局日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.global_log_text = scrolledtext.ScrolledText(log_frame, height=25)
        self.global_log_text.pack(fill=tk.BOTH, expand=True)
        ttk.Button(log_frame, text="清空日志", command=lambda: self.global_log_text.delete(1.0, tk.END)).pack(
            anchor=tk.E)

    def create_group_tab(self, group_id, group_name):
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=group_name)
        group = self.connection_groups[group_id]
        protocol = group.base_config.get('protocol', 'TCP Client')

        config_frame = ttk.LabelFrame(tab, text="连接配置", padding=10)
        config_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(config_frame, text="协议:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Label(config_frame, text=protocol).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Label(config_frame, text="数据类型:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=2)
        ttk.Label(config_frame, text=group.base_config.get('data_type', 'hex')).grid(row=0, column=3, sticky=tk.W,
                                                                                     padx=5, pady=2)

        ttk.Label(config_frame, text="编码格式:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Label(config_frame, text=group.base_config.get('encoding', 'utf-8')).grid(row=1, column=1, sticky=tk.W,
                                                                                      padx=5, pady=2)
        ttk.Label(config_frame, text="发送间隔(ms):").grid(row=1, column=2, sticky=tk.W, padx=5, pady=2)
        ttk.Label(config_frame, text=str(group.base_config.get('interval_ms', 1000))).grid(row=1, column=3, sticky=tk.W,
                                                                                           padx=5, pady=2)

        ttk.Label(config_frame, text="源IP:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Label(config_frame, text="; ".join(group.src_ips)).grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        ttk.Label(config_frame, text="源端口:").grid(row=2, column=2, sticky=tk.W, padx=5, pady=2)
        ttk.Label(config_frame, text="; ".join(group.src_ports)).grid(row=2, column=3, sticky=tk.W, padx=5, pady=2)

        if protocol != 'TCP Server':
            ttk.Label(config_frame, text="目的IP:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
            ttk.Label(config_frame, text=group.base_config.get('dst_ip', '127.0.0.1')).grid(row=3, column=1,
                                                                                            sticky=tk.W, padx=5, pady=2)
            ttk.Label(config_frame, text="目的端口:").grid(row=3, column=2, sticky=tk.W, padx=5, pady=2)
            ttk.Label(config_frame, text=group.base_config.get('dst_port', '8080')).grid(row=3, column=3, sticky=tk.W,
                                                                                         padx=5, pady=2)

        data_frame = ttk.LabelFrame(tab, text="发送数据", padding=10)
        data_frame.pack(fill=tk.X, padx=5, pady=5)
        send_text = scrolledtext.ScrolledText(data_frame, height=4, wrap=tk.WORD)
        send_text.pack(fill=tk.X, padx=5, pady=2)
        send_datas = [f"子连接{idx + 1}: {data}" for idx, data in enumerate(group.send_datas)]
        send_text.insert(1.0, "\n".join(send_datas))
        send_text.config(state=tk.DISABLED)
        self.group_send_texts[group_id] = send_text

        control_frame = ttk.Frame(tab)
        control_frame.pack(fill=tk.X, padx=5, pady=5)
        ttk.Button(control_frame, text="启动组", command=lambda g=group_id: self.start_group(g)).pack(side=tk.LEFT,
                                                                                                      padx=2)
        ttk.Button(control_frame, text="停止组", command=lambda g=group_id: self.stop_group(g)).pack(side=tk.LEFT,
                                                                                                     padx=2)
        ttk.Button(control_frame, text="编辑配置", command=lambda g=group_id: self.edit_group(g)).pack(side=tk.LEFT,
                                                                                                       padx=2)
        ttk.Button(control_frame, text="删除组", command=lambda g=group_id: self.remove_group(g)).pack(side=tk.LEFT,
                                                                                                       padx=2)
        ttk.Button(control_frame, text="重命名", command=lambda g=group_id: self.rename_group(g)).pack(side=tk.LEFT,
                                                                                                       padx=2)

        stats_frame = ttk.LabelFrame(tab, text="实时统计", padding=10)
        stats_frame.pack(fill=tk.X, padx=5, pady=5)
        stats_labels = {
            'sent_bytes': ttk.Label(stats_frame, text="发送字节: 0"),
            'recv_bytes': ttk.Label(stats_frame, text="接收字节: 0"),
            'sent_packets': ttk.Label(stats_frame, text="发送包数: 0"),
            'recv_packets': ttk.Label(stats_frame, text="接收包数: 0"),
            'run_time': ttk.Label(stats_frame, text="运行时间: 0秒"),
            'status': ttk.Label(stats_frame, text="状态: 已停止")
        }
        for i, (key, label) in enumerate(stats_labels.items()):
            label.grid(row=i // 2, column=i % 2, sticky=tk.W, padx=10, pady=2)

        log_frame = ttk.LabelFrame(tab, text="连接日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        log_text = scrolledtext.ScrolledText(log_frame, height=15)
        log_text.pack(fill=tk.BOTH, expand=True)
        ttk.Button(log_frame, text="清空日志", command=lambda g=group_id: self.clear_group_log(g)).pack(anchor=tk.E)
        self.group_log_texts[group_id] = log_text

        return tab

    def load_cache(self):
        if os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                saved_global = cache_data.get('global_config', {})
                self.global_config.update(saved_global)
                self.data_type_var.set(self.global_config.get('data_type', 'hex'))
                self.encoding_var.set(self.global_config.get('encoding', 'utf-8'))
                self.data_text.delete(1.0, tk.END)
                self.data_text.insert(1.0, self.global_config.get('data', ''))
                self.interval_var.set(str(self.global_config.get('interval_ms', 1000)))
                self.log_interval_var.set(str(self.global_config.get('log_interval', 0.2)))

                groups_data = cache_data.get('connection_groups', [])
                self.group_count = max((g['group_id'] for g in groups_data), default=0)
                for gdata in groups_data:
                    group_id = gdata['group_id']
                    group_name = gdata['group_name']
                    base_config = gdata['base_config']
                    group = MultiConnectionGroup(
                        group_id=group_id,
                        group_name=group_name,
                        base_config=base_config,
                        global_config=self.global_config,
                        data_queue=self.data_queue
                    )
                    self.connection_groups[group_id] = group
                    self.create_group_tab(group_id, group_name)
                self.update_group_list()
                self.status_var.set(f"已加载 {len(groups_data)} 个连接组缓存")
            except Exception as e:
                messagebox.showwarning("缓存加载失败", f"无法加载缓存: {str(e)}")
                if os.path.exists(CACHE_FILE):
                    os.remove(CACHE_FILE)
        else:
            self.status_var.set("无历史缓存，启动新会话")

    def save_cache(self):
        try:
            groups_data = []
            for group_id, group in self.connection_groups.items():
                groups_data.append({
                    'group_id': group.group_id,
                    'group_name': group.group_name,
                    'base_config': group.base_config
                })
            cache_data = {
                'global_config': self.global_config,
                'connection_groups': groups_data,
                'group_count': self.group_count
            }
            with open(CACHE_FILE, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            messagebox.showwarning("缓存保存失败", f"无法保存缓存: {str(e)}")

    def add_connection_group(self):
        group_name = simpledialog.askstring("输入名称", "请输入连接组名称:",
                                            initialvalue=f"连接组{self.group_count + 1}")
        if not group_name:
            return
        dialog = ConnectionDialog(self.root, "添加多源连接组")
        config = dialog.show()
        if config:
            if config['protocol'] == 'TCP Server':
                ports = [port.strip() for port in config['src_ports'].split(';') if port.strip()]
                for existing_group in self.connection_groups.values():
                    if existing_group.base_config.get('protocol') == 'TCP Server':
                        existing_ports = [p.strip() for p in existing_group.base_config['src_ports'].split(';') if
                                          p.strip()]
                        common_ports = set(ports) & set(existing_ports)
                        if common_ports:
                            if not messagebox.askyesno("端口冲突",
                                                       f"端口 {', '.join(common_ports)} 已被其他TCP Server组使用，是否继续？"):
                                return
            self.group_count += 1
            group = MultiConnectionGroup(
                group_id=self.group_count,
                group_name=group_name,
                base_config=config,
                global_config=self.global_config,
                data_queue=self.data_queue
            )
            self.connection_groups[self.group_count] = group
            self.create_group_tab(self.group_count, group_name)
            self.update_group_list()
            self.save_cache()
            self.status_var.set(f"已添加连接组 {group_name}")

    def rename_group(self, group_id):
        if group_id not in self.connection_groups:
            return
        group = self.connection_groups[group_id]
        old_name = group.group_name
        new_name = simpledialog.askstring("重命名", f"请输入新名称（当前: {old_name}）:", initialvalue=old_name)
        if new_name and new_name != old_name:
            group.update_group_name(new_name)
            for i in range(self.notebook.index("end")):
                if self.notebook.tab(i, "text") == old_name:
                    self.notebook.tab(i, text=new_name)
                    break
            self.update_group_list()
            self.save_cache()
            self.status_var.set(f"连接组已重命名为 {new_name}")

    def rename_selected_group(self):
        selected = self.conn_listbox.curselection()
        if selected:
            list_item = self.conn_listbox.get(selected[0])
            group_id = int(list_item.split(" - ")[1].split(" ")[1])
            self.rename_group(group_id)
        else:
            messagebox.showinfo("提示", "请先选择一个连接组")

    def start_group(self, group_id):
        if group_id in self.connection_groups:
            group = self.connection_groups[group_id]
            if group.start():
                self.status_var.set(f"连接组 {group.group_name} 已启动")
                self.update_group_stats(group_id)
                self.update_group_list()

    def stop_group(self, group_id):
        if group_id in self.connection_groups:
            group = self.connection_groups[group_id]
            group.stop()
            self.status_var.set(f"连接组 {group.group_name} 已停止")
            self.update_group_stats(group_id)
            self.update_group_list()

    def start_all_groups(self):
        for group_id, group in self.connection_groups.items():
            group.start()
        self.status_var.set("所有连接组已启动")
        self.update_overview_stats()
        self.update_group_list()

    def stop_all_groups(self):
        for group_id, group in self.connection_groups.items():
            group.stop()
        self.status_var.set("所有连接组已停止")
        self.update_overview_stats()
        self.update_group_list()

    def apply_global_config(self):
        try:
            new_global_config = {
                'data_type': self.data_type_var.get(),
                'encoding': self.encoding_var.get(),
                'data': self.data_text.get(1.0, tk.END).strip(),
                'interval_ms': int(self.interval_var.get()),
                'log_interval': float(self.log_interval_var.get())
            }
            if new_global_config['interval_ms'] < 10:
                raise ValueError("发送间隔不能小于10ms")
            if new_global_config['log_interval'] < 0.01:
                raise ValueError("日志频率不能小于0.01秒")
            self.global_config = new_global_config
            for group_id, group in self.connection_groups.items():
                group.update_global_config(new_global_config)
                self.update_group_config_display(group_id)
            self.save_cache()
            self.status_var.set("全局配置已应用到所有连接组")
            self.update_overview_stats()
        except ValueError as e:
            messagebox.showerror("输入错误", f"全局配置无效: {str(e)}")
        except Exception as e:
            messagebox.showerror("错误", f"应用全局配置失败: {str(e)}")

    def apply_log_interval(self):
        try:
            log_interval = float(self.log_interval_var.get())
            if log_interval < 0.01:
                raise ValueError("日志频率不能小于0.01秒")
            self.global_config['log_interval'] = log_interval
            for group in self.connection_groups.values():
                for sub_conn in group.sub_connections:
                    sub_conn.log_interval = log_interval
            self.save_cache()
            self.status_var.set("日志频率设置已应用")
        except ValueError as e:
            messagebox.showerror("输入错误", f"日志频率无效: {str(e)}")

    def edit_group(self, group_id):
        if group_id not in self.connection_groups:
            return
        group = self.connection_groups[group_id]
        dialog = ConnectionDialog(self.root, "编辑连接组", group.base_config)
        new_config = dialog.show()
        if new_config:
            if new_config['protocol'] == 'TCP Server':
                ports = [port.strip() for port in new_config['src_ports'].split(';') if port.strip()]
                for existing_group_id, existing_group in self.connection_groups.items():
                    if existing_group_id != group_id and existing_group.base_config.get('protocol') == 'TCP Server':
                        existing_ports = [p.strip() for p in existing_group.base_config['src_ports'].split(';') if
                                          p.strip()]
                        common_ports = set(ports) & set(existing_ports)
                        if common_ports:
                            if not messagebox.askyesno("端口冲突",
                                                       f"端口 {', '.join(common_ports)} 已被其他TCP Server组使用，是否继续？"):
                                return
            group.base_config = new_config
            group.src_ips = group._parse_list(new_config.get('src_ips', ''))
            group.src_ports = group._parse_list(new_config.get('src_ports', ''))
            group.send_datas = group._parse_hex_datas(new_config.get('send_datas', ''))
            group._validate_and_adjust_lists()
            self.update_group_config_display(group_id)
            if group.running:
                group.stop()
                group.start()
            self.save_cache()
            self.status_var.set(f"连接组 {group.group_name} 配置已更新")

    def remove_group(self, group_id):
        if group_id not in self.connection_groups:
            return
        group = self.connection_groups.pop(group_id)
        group.stop()
        for i in range(self.notebook.index("end")):
            if self.notebook.tab(i, "text") == group.group_name:
                self.notebook.forget(i)
                break
        self.group_send_texts.pop(group_id, None)
        self.group_log_texts.pop(group_id, None)
        self.update_group_list()
        self.save_cache()
        self.status_var.set(f"连接组 {group.group_name} 已删除")

    def update_group_list(self):
        self.conn_listbox.delete(0, tk.END)
        for group_id, group in self.connection_groups.items():
            protocol = group.base_config.get('protocol', 'TCP Client')
            status = "● 运行中" if group.is_running() else "○ 已停止"
            self.conn_listbox.insert(tk.END, f"{status} - {group.group_name} [{protocol}]")

    def on_group_select(self, event):
        selected = self.conn_listbox.curselection()
        if selected:
            list_item = self.conn_listbox.get(selected[0])
            group_name = list_item.split(" - ")[1].split(" [")[0]
            for i in range(self.notebook.index("end")):
                if self.notebook.tab(i, "text") == group_name:
                    self.notebook.select(i)
                    group_id = None
                    for gid, group in self.connection_groups.items():
                        if group.group_name == group_name:
                            group_id = gid
                            break
                    if group_id:
                        self.update_group_stats(group_id)
                    break

    def update_group_config_display(self, group_id):
        if group_id not in self.connection_groups:
            return
        group = self.connection_groups[group_id]
        base_config = group.base_config
        protocol = base_config.get('protocol', 'TCP Client')
        group_name = group.group_name

        for i in range(self.notebook.index("end")):
            if self.notebook.tab(i, "text") == group_name:
                tab = self.notebook.nametowidget(self.notebook.tabs()[i])
                config_frame = tab.winfo_children()[0]
                label_value_map = {
                    "协议:": protocol,
                    "数据类型:": base_config.get('data_type', 'hex'),
                    "编码格式:": base_config.get('encoding', 'utf-8'),
                    "发送间隔(ms):": str(base_config.get('interval_ms', 1000)),
                    "源IP:": "; ".join(group.src_ips),
                    "源端口:": "; ".join(group.src_ports)
                }
                if protocol != 'TCP Server':
                    label_value_map["目的IP:"] = base_config.get('dst_ip', '127.0.0.1')
                    label_value_map["目的端口:"] = base_config.get('dst_port', '8080')

                for child in config_frame.winfo_children():
                    if isinstance(child, ttk.Label) and child["text"] in label_value_map:
                        info = child.grid_info()
                        row = info.get('row')
                        col = info.get('column')
                        if row is not None and col is not None:
                            value_widgets = config_frame.grid_slaves(row=row, column=col + 1)
                            if value_widgets:
                                value_widget = value_widgets[0]
                                if isinstance(value_widget, ttk.Label):
                                    value_widget.config(text=label_value_map[child["text"]])

                send_text = self.group_send_texts.get(group_id)
                if send_text:
                    send_text.config(state=tk.NORMAL)
                    send_text.delete(1.0, tk.END)
                    send_datas = [f"子连接{idx + 1}: {data}" for idx, data in enumerate(group.send_datas)]
                    send_text.insert(1.0, "\n".join(send_datas))
                    send_text.config(state=tk.DISABLED)
                break

    def update_group_stats(self, group_id):
        if group_id not in self.connection_groups:
            return
        group = self.connection_groups[group_id]
        stats = group.get_stats()
        status = "运行中" if group.is_running() else "已停止"
        run_time = 0
        if group.running and group.sub_connections:
            for sub_conn in group.sub_connections:
                if sub_conn.connection_time:
                    run_time = int((datetime.now() - sub_conn.connection_time).total_seconds())
                    break
        group_name = group.group_name
        for i in range(self.notebook.index("end")):
            if self.notebook.tab(i, "text") == group_name:
                tab = self.notebook.nametowidget(self.notebook.tabs()[i])
                stats_frame = tab.winfo_children()[3]
                for child in stats_frame.winfo_children():
                    if "发送字节" in child["text"]:
                        child["text"] = f"发送字节: {stats['bytes_sent']}"
                    elif "接收字节" in child["text"]:
                        child["text"] = f"接收字节: {stats['bytes_received']}"
                    elif "发送包数" in child["text"]:
                        child["text"] = f"发送包数: {stats['packets_sent']}"
                    elif "接收包数" in child["text"]:
                        child["text"] = f"接收包数: {stats['packets_received']}"
                    elif "运行时间" in child["text"]:
                        child["text"] = f"运行时间: {run_time}秒"
                    elif "状态" in child["text"]:
                        child["text"] = f"状态: {status}"
                break

    def update_overview_stats(self):
        total_groups = len(self.connection_groups)
        total_sub_conns = 0
        total_active = 0
        total_sent = 0
        total_received = 0
        log_queue_size = self.data_queue.qsize()
        active_threads = threading.active_count() - 1
        for group in self.connection_groups.values():
            stats = group.get_stats()
            total_sub_conns += stats['total_sub_conns']
            total_active += stats['active_sub_conns']
            total_sent += stats['bytes_sent']
            total_received += stats['bytes_received']
        self.active_connections_var.set(f"活动连接: {total_active}/{total_sub_conns}")
        self.total_sent_var.set(f"总发送: {total_sent} 字节")
        self.total_received_var.set(f"总接收: {total_received} 字节")
        self.log_queue_var.set(f"日志队列: {log_queue_size}")
        self.active_threads_var.set(f"活动线程: {active_threads}")
        for group_id in self.connection_groups.keys():
            self.update_group_stats(group_id)

    def clear_all_logs(self):
        self.global_log_text.delete(1.0, tk.END)
        for group_id in self.connection_groups.keys():
            log_text = self.group_log_texts.get(group_id)
            if log_text:
                log_text.delete(1.0, tk.END)
        self.status_var.set("所有日志已清空")

    def clear_group_log(self, group_id):
        if group_id not in self.connection_groups:
            return
        log_text = self.group_log_texts.get(group_id)
        if log_text:
            log_text.delete(1.0, tk.END)
            self.status_var.set(f"连接组 {self.connection_groups[group_id].group_name} 日志已清空")

    def start_queue_processor(self):
        self.root.after(100, self.process_queue)

    def process_queue(self):
        try:
            processed_count = 0
            while processed_count < self.batch_size:
                try:
                    log_entry = self.data_queue.get_nowait()
                    processed_count += 1
                    direction = "←" if log_entry['is_received'] else "→"
                    group_name = "未知组"
                    group = self.connection_groups.get(log_entry['conn_id'])
                    if group:
                        group_name = group.group_name
                    log_text = f"{log_entry['timestamp']} [{group_name}({log_entry['full_conn_id']})] {direction} {log_entry['message']}"
                    if log_entry['data']:
                        log_text += f"\n数据: {log_entry['data']}"
                    log_text += "\n"
                    self._add_to_log(self.global_log_text, log_text)
                    group_id = log_entry['conn_id']
                    if group_id in self.connection_groups:
                        log_widget = self.group_log_texts.get(group_id)
                        if log_widget:
                            self._add_to_log(log_widget, log_text)
                except queue.Empty:
                    break
        except Exception as e:
            pass

        current_time = time.time()
        if current_time - self.last_stats_update >= self.stats_update_interval:
            self.update_overview_stats()
            self.last_stats_update = current_time

        queue_size = self.data_queue.qsize()
        interval = 50 if queue_size > 500 else 200
        self.root.after(interval, self.process_queue)

    def _add_to_log(self, text_widget, log_text):
        text_widget.insert(tk.END, log_text)
        text_widget.see(tk.END)
        line_count = int(text_widget.index('end-1c').split('.')[0])
        if line_count > self.max_log_lines:
            delete_lines = line_count - self.max_log_lines
            text_widget.delete(1.0, f"{delete_lines + 1}.0")

    def on_closing(self):
        self.stop_all_groups()
        self.save_cache()
        self.root.destroy()


def main():
    root = tb.Window(themename="cosmo")
    app = NetworkTestTool(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()