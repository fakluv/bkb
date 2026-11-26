#!/usr/bin/env bash
# ============================================================
# 在 macOS 上把「字节工具集」打包成 .app（必须在 Mac 上运行）
#
# 用法：
#   1. 把整个 mac_package 文件夹拷到 Mac
#   2. 打开「终端」，cd 进这个文件夹
#   3. 执行：bash build_mac.sh
#   4. 产物：dist/字节工具集.app，拖进「应用程序」即可
#
# 【v2 修复】必须在「自带 Tk 8.6」的 Python 上打包。
#   macOS 自带的 /usr/bin/python3（如 3.9.6）链接 Apple Tk 8.5.9，
#   用它打出来的 .app 打开是纯白窗口 —— 不是程序的问题，是 Apple Tk 的老毛病。
#   本脚本会自动跳过这类解释器，只挑 Tk >= 8.6 的。
# ============================================================
set -uo pipefail

cd "$(dirname "$0")"

APP_NAME="字节工具集"
BUNDLE_ID="com.bkb.bytetool"

# ---------- 小工具 ----------
probe() {  # 输出 "python版本|Tk版本"，导入失败则无输出
    "$1" -c 'import sys, tkinter; print(sys.version.split()[0], tkinter.TkVersion, sep="|")' 2>/dev/null
}

is_system_py() {  # Apple 自带的 python3（链接系统 Tk 8.5）
    case "$1" in
        /usr/bin/python3*) return 0 ;;
        /Applications/Xcode*.app/*) return 0 ;;
        /Library/Developer/CommandLineTools/*) return 0 ;;
        *) return 1 ;;
    esac
}

echo "==> 系统：macOS $(sw_vers -productVersion 2>/dev/null || echo '?') / 架构 $(uname -m)"
echo "==> 检查可用的 Python（需要 Tk >= 8.6）："

# ---------- 收集候选解释器 ----------
CANDIDATES=""
add_candidate() {
    if [ -n "${1:-}" ] && [ -x "$1" ]; then
        case "$CANDIDATES" in
            *"$1"*) : ;;
            *) CANDIDATES="$CANDIDATES
$1" ;;
        esac
    fi
}

for name in python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
    add_candidate "$(command -v "$name" 2>/dev/null || true)"
done
# python.org 安装包（即使没进 PATH）
for p in /Library/Frameworks/Python.framework/Versions/*/bin/python3; do
    add_candidate "$p"
done
# Homebrew（只取解释器本体，避开 *-config 之类的脚本）
for v in 9 10 11 12 13 14; do
    add_candidate "/opt/homebrew/bin/python3.$v"
    add_candidate "/usr/local/bin/python3.$v"
done

# ---------- 逐个体检，挑第一个合格的 ----------
PICK=""
OLD_IFS=$IFS
IFS='
'
for py in $CANDIDATES; do
    info=$(probe "$py" || true)
    if [ -z "$info" ]; then
        printf '    %-52s 缺 tkinter，跳过\n' "$py"
        continue
    fi
    ver=${info%%|*}
    tk=${info##*|}
    if is_system_py "$py"; then
        printf '    %-52s %-6s Tk %-5s ← 系统自带，Tk 8.5 会白屏，跳过\n' "$py" "$ver" "$tk"
        continue
    fi
    case "$tk" in
        8.5*)
            printf '    %-52s %-6s Tk %-5s ← Tk 8.5 会白屏，跳过\n' "$py" "$ver" "$tk"
            continue
            ;;
    esac
    printf '    %-52s %-6s Tk %-5s ✔ 使用\n' "$py" "$ver" "$tk"
    if [ -z "$PICK" ]; then
        PICK="$py"
    fi
done
IFS=$OLD_IFS

if [ -z "$PICK" ]; then
    cat <<'EOT'

✘ 没有找到能用来打包的 Python（需要自带 Tk 8.6）。

  原因：macOS 自带的 /usr/bin/python3（例如 3.9.6）链接的是 Apple 的 Tk 8.5.9，
        PyInstaller 用它打出的 .app 打开就是白屏。苹果的 Tk 8.5 在
        macOS 11+ / 14+ 上还有一堆渲染问题，官方也标了 deprecated。

  解决办法（任选一种）：
    ① 装 python.org 的正式安装包（推荐，自带 Tk 8.6）
       https://www.python.org/downloads/macos/
       装完关掉终端重新打开，再执行 bash build_mac.sh
    ② 用 Homebrew：
       brew install python@3.12 python-tk@3.12
EOT
    exit 1
fi

echo "==> 将使用：$PICK"

# ---------- 建/重建虚拟环境（解释器变了就重建） ----------
if [ -d .venv ]; then
    BASE=$(sed -n 's/^executable = //p' .venv/pyvenv.cfg 2>/dev/null | head -1)
    if [ "$BASE" != "$PICK" ]; then
        echo "==> 旧 .venv 用的不是这个 Python（${BASE:-未知}），重建"
        rm -rf .venv
    fi
fi
if [ ! -d .venv ]; then
    "$PICK" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip >/dev/null
python -m pip install pyinstaller

echo "==> 打包用 Tk 版本：$(python -c 'import tkinter; print(tkinter.TkVersion)')"

# 可选：装了哪个数据库驱动，「设备校验」页就能连哪种库，打包时一并带上
EXTRA=()
for mod in pymysql psycopg2 oracledb pyodbc; do
    if python -c "import $mod" >/dev/null 2>&1; then
        EXTRA+=(--hidden-import "$mod")
        echo "    带上数据库驱动：$mod"
    fi
done

rm -rf build dist

echo "==> 开始打包（首次约 1~3 分钟）"
pyinstaller \
    --noconfirm --clean --windowed \
    --name "$APP_NAME" \
    --osx-bundle-identifier "$BUNDLE_ID" \
    --icon icon.icns \
    --add-data "tool.ico:." \
    --add-data "appicon.png:." \
    ${EXTRA[@]+"${EXTRA[@]}"} \
    tool.py

APP="dist/$APP_NAME.app"

if [ ! -d "$APP" ]; then
    echo "✘ 没找到 $APP，dist 里实际是："
    ls -la dist 2>/dev/null || true
    exit 1
fi

# 本地临时签名 + 去隔离属性，减少「已损坏 / 无法验证开发者」的拦截
xattr -cr "$APP" 2>/dev/null || true
codesign --force --deep --sign - "$APP" 2>/dev/null || true

echo ""
echo "==> 应用包自检："
if [ -x "$APP/Contents/MacOS/$APP_NAME" ]; then
    echo "    可执行文件：OK"
else
    echo "    可执行文件：缺失（打包可能不完整）"
fi
if [ -d "$APP/Contents/Frameworks" ]; then
    echo "    内置 Tk：$(ls "$APP/Contents/Frameworks" 2>/dev/null | grep -i '^Tk' | head -1)"
fi

echo ""
echo "✔ 打包完成：$(pwd)/$APP"
echo "  架构：$(uname -m) —— 只能运行在同架构的 Mac 上"
echo "  现在可以直接试：open \"$APP\""
echo "  发给朋友：右键 .app →「压缩」，把 zip 发过去"
echo "  对方首次打开：右键 .app →「打开」；若提示已损坏，执行"
echo "        xattr -dr com.apple.quarantine \"$APP\""
