#!/usr/bin/env bash
# ============================================================
# 体检脚本（只读，不改任何文件）
# 作用：告诉你这台 Mac 上哪些 Python 能用来打包，
#       以及为什么系统自带的 python3 打出来是白屏。
#
# 用法：bash check_env.sh
# ============================================================
set -uo pipefail

echo "系统：macOS $(sw_vers -productVersion 2>/dev/null || echo '?') / 架构 $(uname -m)"
echo "命令行工具：$(xcode-select -p 2>/dev/null || echo '未安装')"
echo "Homebrew：$(command -v brew 2>/dev/null || echo '未安装')"
echo ""

probe() {
    "$1" -c 'import sys, tkinter; print(sys.version.split()[0], tkinter.TkVersion, sep="|")' 2>/dev/null
}

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
for p in /Library/Frameworks/Python.framework/Versions/*/bin/python3; do
    add_candidate "$p"
done
for v in 9 10 11 12 13 14; do
    add_candidate "/opt/homebrew/bin/python3.$v"
    add_candidate "/usr/local/bin/python3.$v"
done

printf '%-54s %-8s %-8s %s\n' "解释器" "Python" "Tk" "能不能用来打包"
printf '%.0s-' {1..92}
echo ""
OK_COUNT=0
OLD_IFS=$IFS
IFS='
'
for py in $CANDIDATES; do
    info=$(probe "$py" || true)
    if [ -z "$info" ]; then
        printf '%-54s %-8s %-8s %s\n' "$py" "-" "-" "缺 tkinter，不能用"
        continue
    fi
    ver=${info%%|*}
    tk=${info##*|}
    verdict="✔ 可以"
    case "$py" in
        /usr/bin/python3*|/Applications/Xcode*.app/*|/Library/Developer/CommandLineTools/*)
            verdict="✘ 系统自带 Tk 8.5，会白屏" ;;
        *)
            case "$tk" in
                8.5*) verdict="✘ Tk 8.5，会白屏" ;;
            esac ;;
    esac
    case "$verdict" in
        "✔"*) OK_COUNT=$((OK_COUNT + 1)) ;;
    esac
    printf '%-54s %-8s %-8s %s\n' "$py" "$ver" "$tk" "$verdict"
done
IFS=$OLD_IFS

echo ""
if [ "$OK_COUNT" -gt 0 ]; then
    echo "结论：有 $OK_COUNT 个可用的解释器，直接执行 bash build_mac.sh 即可（脚本会自动挑对的）。"
else
    echo "结论：没有可用的解释器。系统自带的 python3 用 Apple Tk 8.5，打出来一定是白屏。"
    echo "      请安装 python.org 的 Python 3（自带 Tk 8.6）："
    echo "      https://www.python.org/downloads/macos/"
fi
