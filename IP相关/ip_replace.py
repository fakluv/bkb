"""
自动生成并执行 UPDATE 语句的图形界面工具
功能：连接数据库，执行查询，为查询结果中的记录按顺序分配递增 IP，并执行更新。
使用 ttkbootstrap 提供现代化界面。
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import ttkbootstrap as tb
from ttkbootstrap.constants import *
import pymysql
from pymysql import err


def ip_increment(ip_str, increment):
    """将IP地址字符串按指定增量递增，返回新IP字符串"""
    parts = list(map(int, ip_str.split('.')))
    total = parts[0] * 256 ** 3 + parts[1] * 256 ** 2 + parts[2] * 256 + parts[3]
    total += increment
    # 限制最大IP为 192.168.255.254，避免溢出到其他网段
    if total > (192 << 24) + (168 << 16) + (255 << 8) + 254:
        raise ValueError(f"IP地址超出范围 (最大 192.168.255.254): {ip_str}")
    new_parts = [
        (total >> 24) & 255,
        (total >> 16) & 255,
        (total >> 8) & 255,
        total & 255
    ]
    return f"{new_parts[0]}.{new_parts[1]}.{new_parts[2]}.{new_parts[3]}"


class App(tb.Window):
    def __init__(self):
        super().__init__(themename="cosmo")  # 使用 ttkbootstrap 主题
        self.title("IP 批量更新工具")
        self.geometry("900x700")

        # 数据库连接对象
        self.conn = None
        # 存储查询结果 (列名列表, 数据行列表)
        self.columns = []
        self.rows = []

        # 创建界面组件
        self.create_widgets()

    def create_widgets(self):
        # 主框架，使用 Notebook 分页？为了简洁，直接使用垂直布局
        main_frame = ttk.Frame(self, padding=10)
        main_frame.pack(fill=BOTH, expand=YES)

        # ---------- 连接信息区域 ----------
        conn_frame = ttk.LabelFrame(main_frame, text="数据库连接", padding=10)
        conn_frame.pack(fill=X, pady=5)

        # 使用网格布局
        row = 0
        ttk.Label(conn_frame, text="主机:").grid(row=row, column=0, sticky=W, padx=5, pady=2)
        self.host_entry = ttk.Entry(conn_frame, width=20)
        self.host_entry.grid(row=row, column=1, sticky=W, padx=5, pady=2)
        self.host_entry.insert(0, "192.168.1.237")

        ttk.Label(conn_frame, text="端口:").grid(row=row, column=2, sticky=W, padx=5, pady=2)
        self.port_entry = ttk.Entry(conn_frame, width=8)
        self.port_entry.grid(row=row, column=3, sticky=W, padx=5, pady=2)
        self.port_entry.insert(0, "3306")

        row += 1
        ttk.Label(conn_frame, text="用户名:").grid(row=row, column=0, sticky=W, padx=5, pady=2)
        self.user_entry = ttk.Entry(conn_frame, width=20)
        self.user_entry.grid(row=row, column=1, sticky=W, padx=5, pady=2)
        self.user_entry.insert(0, "root")

        ttk.Label(conn_frame, text="密码:").grid(row=row, column=2, sticky=W, padx=5, pady=2)
        self.pwd_entry = ttk.Entry(conn_frame, width=20, show="*")
        self.pwd_entry.grid(row=row, column=3, sticky=W, padx=5, pady=2)
        self.pwd_entry.insert(0, "mysql")

        row += 1
        ttk.Label(conn_frame, text="数据库:").grid(row=row, column=0, sticky=W, padx=5, pady=2)
        self.db_entry = ttk.Entry(conn_frame, width=20)
        self.db_entry.grid(row=row, column=1, sticky=W, padx=5, pady=2)
        self.db_entry.insert(0, "base")

        # 连接按钮
        self.connect_btn = ttk.Button(conn_frame, text="测试连接", command=self.connect_db, bootstyle=PRIMARY)
        self.connect_btn.grid(row=row, column=2, columnspan=2, pady=5, sticky=W)

        # ---------- 查询区域 ----------
        query_frame = ttk.LabelFrame(main_frame, text="查询语句", padding=10)
        query_frame.pack(fill=X, pady=5)

        # SQL 输入框
        self.sql_text = scrolledtext.ScrolledText(query_frame, height=4, font=("Courier", 10))
        self.sql_text.pack(fill=X, pady=5)
        self.sql_text.insert("1.0", "SELECT * FROM dic_mss_netaddress_config")

        # 按钮行
        btn_frame = ttk.Frame(query_frame)
        btn_frame.pack(fill=X, pady=5)
        self.exec_btn = ttk.Button(btn_frame, text="执行查询", command=self.execute_query, bootstyle=SUCCESS)
        self.exec_btn.pack(side=LEFT, padx=5)
        self.status_label = ttk.Label(btn_frame, text="就绪", foreground="gray")
        self.status_label.pack(side=LEFT, padx=20)

        # ---------- 结果展示区域 ----------
        result_frame = ttk.LabelFrame(main_frame, text="查询结果", padding=10)
        result_frame.pack(fill=BOTH, expand=YES, pady=5)

        # Treeview 带滚动条
        tree_frame = ttk.Frame(result_frame)
        tree_frame.pack(fill=BOTH, expand=YES)
        self.tree = ttk.Treeview(tree_frame, show="headings")
        vsb = ttk.Scrollbar(tree_frame, orient=VERTICAL, command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(side=LEFT, fill=BOTH, expand=YES)
        vsb.pack(side=RIGHT, fill=Y)
        hsb.pack(side=BOTTOM, fill=X)

        # ---------- 更新设置区域 ----------
        update_frame = ttk.LabelFrame(main_frame, text="IP 更新设置", padding=10)
        update_frame.pack(fill=X, pady=5)

        ttk.Label(update_frame, text="起始 IP:").pack(side=LEFT, padx=5)
        self.start_ip_entry = ttk.Entry(update_frame, width=18)
        self.start_ip_entry.pack(side=LEFT, padx=5)
        self.start_ip_entry.insert(0, "192.168.2.131")

        self.update_btn = ttk.Button(update_frame, text="更新 IP (按顺序)", command=self.update_ip, bootstyle=WARNING)
        self.update_btn.pack(side=LEFT, padx=20)

        # ---------- 日志区域 ----------
        log_frame = ttk.LabelFrame(main_frame, text="操作日志", padding=10)
        log_frame.pack(fill=X, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=6, font=("Consolas", 9), state="disabled")
        self.log_text.pack(fill=X)

    def log(self, msg, level="info"):
        """在日志区域添加消息"""
        self.log_text.config(state="normal")
        if level == "error":
            tag = "error"
            self.log_text.tag_config("error", foreground="red")
        elif level == "success":
            tag = "success"
            self.log_text.tag_config("success", foreground="green")
        else:
            tag = "info"
            self.log_text.tag_config("info", foreground="black")
        self.log_text.insert(tk.END, msg + "\n", tag)
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def connect_db(self):
        """测试数据库连接"""
        try:
            host = self.host_entry.get().strip()
            port = int(self.port_entry.get().strip())
            user = self.user_entry.get().strip()
            password = self.pwd_entry.get().strip()
            database = self.db_entry.get().strip()
            self.conn = pymysql.connect(
                host=host, port=port, user=user, password=password,
                database=database, charset='utf8mb4'
            )
            self.log(f"数据库连接成功: {user}@{host}:{port}/{database}", "success")
            messagebox.showinfo("成功", "数据库连接成功！")
        except Exception as e:
            self.log(f"连接失败: {e}", "error")
            messagebox.showerror("错误", f"连接失败:\n{e}")

    def execute_query(self):
        """执行查询并显示结果"""
        if not self.conn:
            messagebox.showerror("错误", "请先连接数据库！")
            return
        sql = self.sql_text.get("1.0", tk.END).strip()
        if not sql:
            messagebox.showerror("错误", "请输入 SQL 查询语句！")
            return
        try:
            cursor = self.conn.cursor()
            cursor.execute(sql)
            # 获取列信息
            self.columns = [desc[0] for desc in cursor.description]
            self.rows = cursor.fetchall()
            cursor.close()

            # 更新 Treeview
            self.tree.delete(*self.tree.get_children())
            self.tree["columns"] = self.columns
            for col in self.columns:
                self.tree.heading(col, text=col)
                self.tree.column(col, width=100, anchor="center")
            for row in self.rows:
                self.tree.insert("", tk.END, values=row)

            count = len(self.rows)
            self.status_label.config(text=f"共 {count} 条记录", foreground="blue")
            self.log(f"查询成功，返回 {count} 条记录", "success")
        except Exception as e:
            self.log(f"查询失败: {e}", "error")
            messagebox.showerror("错误", f"查询失败:\n{e}")

    def update_ip(self):
        """根据查询结果更新 IP"""
        if not self.conn:
            messagebox.showerror("错误", "请先连接数据库！")
            return
        if not self.rows:
            messagebox.showerror("错误", "没有可更新的记录，请先执行查询！")
            return

        # 检查结果中是否包含 SYS_NO 和 STATION_NO 列
        required_cols = ["SYS_NO", "STATION_NO"]
        for col in required_cols:
            if col not in self.columns:
                messagebox.showerror("错误", f"查询结果中缺少 '{col}' 列，无法作为更新条件！")
                return

        # 获取列索引
        idx_sys = self.columns.index("SYS_NO")
        idx_station = self.columns.index("STATION_NO")

        start_ip = self.start_ip_entry.get().strip()
        if not start_ip:
            messagebox.showerror("错误", "请输入起始 IP！")
            return
        # 验证IP格式简单检查
        try:
            parts = list(map(int, start_ip.split('.')))
            if len(parts) != 4 or any(p < 0 or p > 255 for p in parts):
                raise ValueError("无效IP")
        except:
            messagebox.showerror("错误", "起始 IP 格式无效，请使用 xxx.xxx.xxx.xxx")
            return

        # 确认是否继续
        if not messagebox.askyesno("确认", f"将更新 {len(self.rows)} 条记录的 IP，起始为 {start_ip}，是否继续？"):
            return

        try:
            cursor = self.conn.cursor()
            # 关闭自动提交，以便回滚
            self.conn.autocommit(False)

            success_count = 0
            for i, row in enumerate(self.rows):
                SYS_NO = row[idx_sys]
                STATION_NO = row[idx_station]
                try:
                    new_ip = ip_increment(start_ip, i)
                except ValueError as e:
                    self.log(f"IP 生成错误: {e}", "error")
                    self.conn.rollback()
                    messagebox.showerror("错误", f"IP 生成失败: {e}")
                    return

                # 执行 UPDATE，使用参数化查询防止注入
                update_sql = "UPDATE dic_mss_netaddress_config SET ip = %s WHERE SYS_NO = %s AND STATION_NO = %s"
                try:
                    cursor.execute(update_sql, (new_ip, SYS_NO, STATION_NO))
                    success_count += 1
                except Exception as e:
                    self.log(f"更新失败 (SYS_NO={SYS_NO}, STATION_NO={STATION_NO}): {e}", "error")
                    self.conn.rollback()
                    messagebox.showerror("错误", f"更新失败，已回滚:\n{e}")
                    return

            self.conn.commit()
            self.log(f"更新完成！成功更新 {success_count} 条记录。", "success")
            messagebox.showinfo("完成", f"成功更新 {success_count} 条记录。")
            # 刷新查询结果以显示最新 IP
            self.execute_query()
        except Exception as e:
            self.log(f"更新过程发生异常: {e}", "error")
            self.conn.rollback()
            messagebox.showerror("错误", f"更新失败:\n{e}")
        finally:
            self.conn.autocommit(True)
            cursor.close()


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()