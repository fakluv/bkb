# -*- coding: utf-8 -*-
import os
import re

# 待校验SQL文件列表
sql_file_list = [
    "./data/base_update.sql",
    "./data/ftp_update.sql",
    "./data/mms_update.sql",
    "./data/sms_update.sql"
]

# BD300排除表清单
bd300_exclude_tables = {
    "alarm_dealing_cphm",
    "alarm_history_cphm",
    "axle_station_health_cp",
    "axle_voltage_status_history_cphm",
    "device_induction_install_height_cphm",
    "axle_device_health_cphm",
    "dic_device_cphm",
    "dic_health_standard",
    "system_report_content",
    "t_switch_currentvalue",
    "axle_voltage_status_history_cp",
    "ci_ats_operator",
    "dic_health_analysis",
    "dic_trainruninfo_history",
    "vobc_stop_precision_report_data",
    "alarm_current_limiting",
    "alarm_blocking_history",
    "dic_device_alarm_user",
    "alarm_history",
    "alarm_picture",
    "t_switchvalue_history",
    "t_switch_historyvalue_axle",
    "t_switch_historyvalue_pcs",
    "t_switch_historyvalue_crb",
    "t_switch_historyvalue_ats",
    "t_switch_historyvalue_ci",
    "t_switch_historyvalue_ssm",
    "t_switch_historyvalue_power",
    "t_switch_historyvalue_mms",
    "t_switch_historyvalue_psd",
    "t_switch_historyvalue_toc",
    "vobc_stop_precision_report",
    "software_tab",
    "vobc_stop_precision",
    "dic_ats_earlylatestati"
}

# 增强正则：兼容任意空格、换行、反引号包裹表名
drop_table_pattern = re.compile(
    r"drop\s+table\s+(?:if\s+exists\s+)?[`']?([\w_]+)[`']?",
    re.IGNORECASE | re.DOTALL
)

# 存储所有抓取到的drop表名（全局去重）
all_drop_tables = set()

def scan_sql_file(file_path):
    if not os.path.exists(file_path):
        print(f"\n[警告] 文件不存在: {file_path}")
        return
    try:
        # 方案：二进制读取，用errors='replace'忽略所有非法编码字节，彻底解决文件编码报错
        with open(file_path, "rb") as f:
            raw_bytes = f.read()
        # 强制用utf-8解码，无法识别的字符自动替换为�，不会抛异常
        content = raw_bytes.decode("utf-8", errors="replace")

        # 匹配所有DROP表语句
        raw_matches = drop_table_pattern.findall(content)
        table_names = []
        for tbl in raw_matches:
            tbl_clean = tbl.strip().strip("`'")
            # 过滤视图v_开头，只保留真实数据表
            if tbl_clean and not tbl_clean.startswith("v_"):
                table_names.append(tbl_clean)

        # 写入全局集合去重
        for tbl in table_names:
            all_drop_tables.add(tbl)

        print(f"\n===== 文件: {file_path} =====")
        if table_names:
            for t in table_names:
                mark = "[命中排除清单]" if t in bd300_exclude_tables else ""
                print(f"DROP TABLE 找到: {t} {mark}")
        else:
            print("未找到任何DROP TABLE数据表语句")

    except Exception as e:
        print(f"\n[读取跳过] 文件 {file_path} 解析异常，跳过该文件: {str(e)}")

if __name__ == "__main__":
    # 遍历所有目标SQL文件，单个文件报错不中断整体流程
    for sql_file in sql_file_list:
        scan_sql_file(sql_file)

    # 汇总比对结果
    print("\n" + "="*60)
    print("                全局汇总比对结果（去重后）")
    print("="*60)

    if not all_drop_tables:
        print("全部文件均未检测到DROP TABLE数据表语句")
    else:
        print(f"本次扫描共检测到 {len(all_drop_tables)} 个待删除数据表：\n")
        hit_exclude = []
        risk_tables = []
        for tbl in sorted(all_drop_tables):
            if tbl in bd300_exclude_tables:
                hit_exclude.append(tbl)
            else:
                risk_tables.append(tbl)

        # 输出命中排除清单的表（纯文本标记，无emoji）
        print(f"一、命中 bd300_exclude_tables 排除清单的表（共{len(hit_exclude)}个）：")
        if hit_exclude:
            for t in sorted(hit_exclude):
                print(f"  [允许删除] {t}")
        else:
            print("  无")

        # 输出不在排除清单的风险表
        print(f"\n二、不在排除清单内的风险表（共{len(risk_tables)}个，需重点核查）：")
        if risk_tables:
            for t in sorted(risk_tables):
                print(f"  [风险] {t}")
        else:
            print("  无")
