SELECT
		device_no AS "设备编号",
    DEVICE_NAME AS "设备名称",
    STATION_NAME AS "站点名称",
		a.DEVICE_TYPE_NO AS "报警编号",
    CONCAT(DEVICE_NAME,STATUS_NAME) AS "报警内容"
FROM dic_device a
LEFT JOIN dic_device_alarm b ON a.DEVICE_TYPE_NO = b.DEVICE_TYPE_NO
INNER JOIN dic_station c on a.STATION_NO = c.STATION_NO
WHERE a.sys_no = 1 AND a.DEVICE_TYPE_NO is not NULL
--     AND DEVICE_NAME LIKE "%CC%"
-- 		AND STATION_NO <=20
-- 		AND STATUS_NAME LIKE "%告警%"

-- - LEU-1
-- - DSU-2
-- - ZC-3
-- - AXLE-4
-- - DCS-5
-- - POWER-6
-- - VOBC-7
-- - ATS-8
-- - CI-9
-- - MMS-10
-- - SWITCH-11
-- - aimTMC-27
-- - aimRC-28
-- 