# 一、Linux常用命令

### 1、查看进程

- ps -ef | grep 名称，例如：ps -ef | grep tomcat
- ps -ef|grep **apache-tomcat** |grep -v grep|awk '{print $2}'|xargs kill -9（查看进程并终止）
- ps -ef | grep mss-app-test | grep -v grep | awk '{print $2}' | xargs kill -9（查看mss-app-test进程并终止）
- ps -ef | grep mss-app | grep -v grep | awk '{print $2}' | xargs kill -9（查看mss-app进程并终止）
- ps -ef|grep nginx |grep -v grep|awk '{print $2}'|xargs kill -9

### 2、查看中间件是否运行成功（nginx、mysql等）

- systmctl status nginx
- systemctl stauts mysql
- systmctl stauts activemq

### 3、监听端口

- netstat -ntlp   //查看当前所有tcp端口
- netstat -ntulp |grep 80   //查看所有80端口使用情况
- netstat -an | grep 3306   //查看所有3306端口使用情况
- netstat -nlp |grep LISTEN   //查看当前所有监听端口

