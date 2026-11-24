字节工具集 · macOS 打包说明
================================

这个文件夹必须在 Mac 上使用（Windows 无法生成 macOS 的 .app）。

⚠️ 打开后是「纯白窗口」？
------------------------------
原因：打包用的 Python 链接了 Apple 自带的 Tk 8.5。
      macOS 的 /usr/bin/python3（常见版本 3.9.6）就是这种，
      它带的 Tk 8.5.9 在 macOS 11 以上渲染有 bug，
      用它 PyInstaller 打出来的 .app 只会显示一个空白窗体。
      终端里那句 “The system version of Tk is deprecated” 就是信号。

解决办法：换一个自带 Tk 8.6 的 Python（python.org 安装包或 Homebrew），
      删掉旧的构建产物，重新打包：

      rm -rf .venv build dist
      bash build_mac.sh          # 新版脚本会自动挑 Tk 8.6 的 Python

先体检（可选，只读不改东西）：
      bash check_env.sh

打包步骤
------------------------------
1. 装 Python 3：https://www.python.org/downloads/macos/ （自带 Tk 8.6）
   装完关掉终端重新打开
2. 打开「终端」，cd 到本文件夹
3. 执行：bash check_env.sh        # 看有没有可用解释器
4. 执行：bash build_mac.sh        # 得到 dist/字节工具集.app
5. 先自己试：open dist/字节工具集.app

发给朋友
------------------------------
· 右键 dist/字节工具集.app →「压缩」，把 zip 发过去
· 对方解压后拖到「应用程序」；第一次打开请右键 →「打开」
· 若提示「已损坏，无法打开」，让对方在终端执行：
      xattr -dr com.apple.quarantine /Applications/字节工具集.app
· 注意：在 Apple 芯片 Mac 上打的包不能给 Intel Mac 用，反之亦然
  （找一台和对方同架构的 Mac 打包，或让对方在自己机器上打一次）

文件说明
------------------------------
tool.py        — 程序主体（Windows / macOS 通用）
tool.ico       — Windows 窗口图标
appicon.png    — macOS 窗口图标（源码直接运行时用）
icon.icns      — macOS .app 的图标（打包时写入应用包）
build_mac.sh   — 一键打包脚本（自动挑 Tk 8.6 的 Python）
check_env.sh   — 环境体检（只读，看哪几个 Python 能用来打包）

不想打包也能用
------------------------------
Mac 上装好 Python 3 后，直接执行：
      cd 本文件夹
      python3 tool.py

可选：连数据库
------------------------------
「设备校验」页要用数据库驱动。想让 .app 自带驱动，先执行：
      source .venv/bin/activate
      pip install pymysql            # 按需：psycopg2-binary / oracledb / pyodbc
      bash build_mac.sh
脚本会自动把这些驱动打进包里（没装就跳过，其余功能不受影响）。

常见问题
------------------------------
· 白屏 / 只有标题栏没内容 → 见最上面「打开后是纯白窗口」，
  基本就是 Tk 8.5，换 python.org 的 Python 重打
· 提示「python3 缺少 tkinter」→ 装 python.org 的正式安装包
· 提示「无法验证开发者」→ 右键 .app →「打开」；或系统设置 →
  隐私与安全性 → 仍要打开
· 提示「已损坏」→ xattr -dr com.apple.quarantine 应用路径
· 双击闪退 → 终端执行 dist/字节工具集.app/Contents/MacOS/字节工具集 看报错
