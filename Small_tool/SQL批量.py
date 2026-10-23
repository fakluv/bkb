#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量生成 base.pre_alarm_history 数据（40000 条）

规则：
  - id 从 1 自增到 40000
  - device_name 在原有 35 条记录的 device_name 之间循环
  - 其余字段固定取第一条模板记录
切换 MODE = "row_cycle" 可改为整行（含 device_no/alarm_content 等）循环
"""

DB_TYPE = "mysql"          # "postgres" 或 "mysql"

DB_CONF = dict(
    host="192.168.1.134",
    port=3306,                # MySQL 一般 3306
    database="base",
    user="root",
    password="mysql",
)

TABLE       = "base.pre_alarm_history"
TOTAL       = 200000           # 总条数
TPL_LIMIT   = 35              # 模板条数
BATCH       = 1000            # 每批提交条数
MODE        = "name_only"     # "name_only" | "row_cycle"
APPEND      = True           # True: 保留原 35 条，追加到 40035 条；False: 先清空

# 除 id 外的字段顺序
DATA_COLUMNS = [
    "device_no", "sys_no", "station_no", "train_no", "head_tail",
    "alarm_time", "recover_time", "alarm_level", "device_name", "sys_name",
    "alarm_content", "device_type_no", "stamp_src", "remark",
    "pre_alarm_bgn_date", "pre_alarm_end_date", "is_current",
]
ALL_COLUMNS = ["id"] + DATA_COLUMNS


# ---------- 连接 ----------
def get_conn():
    if DB_TYPE == "postgres":
        import psycopg2
        from psycopg2.extras import RealDictCursor
        conn = psycopg2.connect(**DB_CONF)
        return conn, RealDictCursor
    elif DB_TYPE == "mysql":
        import pymysql
        from pymysql.cursors import DictCursor
        conn = pymysql.connect(charset="utf8mb4", autocommit=False, **DB_CONF)
        return conn, DictCursor
    raise ValueError(f"不支持的 DB_TYPE: {DB_TYPE}")


# ---------- 读取 35 条模板 ----------
def fetch_templates(cursor):
    sql = f"""
        SELECT {", ".join(DATA_COLUMNS)}
        FROM {TABLE}
        ORDER BY id
        LIMIT {TPL_LIMIT}
    """
    cursor.execute(sql)
    rows = cursor.fetchall()
    if len(rows) < TPL_LIMIT:
        print(f"[警告] 只查到 {len(rows)} 条模板记录，期望 {TPL_LIMIT} 条")
    return rows


# ---------- 生成 40000 条记录 ----------
def build_rows(templates, start_id):
    base = dict(templates[0])
    end_id = start_id + TOTAL - 1

    rows = []
    for new_id in range(start_id, end_id + 1):
        tpl = templates[(new_id - 1) % len(templates)]
        if MODE == "row_cycle":
            rec = dict(tpl)
        else:
            rec = dict(base)
            rec["device_name"] = tpl["device_name"]
        rec["id"] = new_id
        rows.append(tuple(rec[c] for c in ALL_COLUMNS))
    return rows, end_id


# ---------- 主流程 ----------
def main():
    conn, cursor_cls = get_conn()
    try:
        cursor = conn.cursor(cursor_cls)

        if not APPEND:
            cursor.execute(f"TRUNCATE TABLE {TABLE}")
            print(f"已清空 {TABLE}")
            start_id = 1
        else:
            cursor.execute(f"SELECT COALESCE(MAX(id), 0) AS m FROM {TABLE}")
            start_id = cursor.fetchone()["m"] + 1
            print(f"当前最大 id = {start_id - 1}，本次从 {start_id} 开始")

        templates = fetch_templates(cursor)
        rows, max_id = build_rows(templates, start_id)
        print(f"模板 {len(templates)} 条，生成 {len(rows)} 条，id {rows[0][0]}~{max_id}")

        placeholders = ", ".join(["%s"] * len(ALL_COLUMNS))
        insert_sql = (
            f"INSERT INTO {TABLE} ({', '.join(ALL_COLUMNS)}) "
            f"VALUES ({placeholders})"
        )

        for i in range(0, len(rows), BATCH):
            cursor.executemany(insert_sql, rows[i:i + BATCH])
            print(f"  已插入 {min(i + BATCH, len(rows))}/{len(rows)}")

        if DB_TYPE == "postgres":
            cursor.execute(
                "SELECT setval(pg_get_serial_sequence(%s, 'id'), %s, true)",
                (TABLE, max_id),
            )
        else:
            cursor.execute(f"ALTER TABLE {TABLE} AUTO_INCREMENT = {max_id + 1}")

        conn.commit()
        print(f"[完成] {TABLE} 共插入 {len(rows)} 条，当前最大 id = {max_id}")

        cursor.execute(f"SELECT COUNT(*) AS c FROM {TABLE}")
        print("表内总条数:", cursor.fetchone()["c"])
        cursor.execute(f"SELECT COUNT(DISTINCT device_name) AS c FROM {TABLE}")
        print("不同 device_name 数:", cursor.fetchone()["c"])

        cursor.close()
    except Exception:
        conn.rollback()
        print("[失败] 已回滚")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()