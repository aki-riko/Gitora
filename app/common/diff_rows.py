# coding: utf-8
"""Unified diff -> DiffViewer 结构化行模型。

把 git unified diff 一次性解析成 QML 可直接虚拟化渲染的行数组:

- 行类型/双行号/行文本,供窗口化虚拟渲染(替代旧的大 HTML 表格);
- 词级高亮段:同一对删除/新增行做字符级比对(SequenceMatcher),
  行内真正变化的部分打上 bg 标记;
- 轻量语法着色段:零依赖的正则 tokenizer(关键字/字符串/注释/数字),
  支持块注释与三引号跨行状态。

输出由 GitBridge.requestDiffRows 序列化为 JSON 传给 QML:

    {
      "files": [ {path, old_path, new_path, status, additions, deletions}, ... ],
      "rows":  [
        {"t": "ctx", "o": 12, "n": 12, "x": "text", "fi": 0, "seg": [[s,e,fg,bg], ...]},
        ...
      ]
    }

行类型 t: file=文件头(diff --git) hunk=块头(@@) add/del/ctx=内容 meta=其他。
seg: 按字符区间排序合并的渲染段; fg: ""|"k"(关键字)|"s"(字符串)|"c"(注释)|"n"(数字);
     bg: ""|"a"(行内新增)|"d"(行内删除)。缺省 seg 时整行按行类型默认色渲染。
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

__all__ = ["parse_diff_rows", "rows_to_json"]

# 词级比对的单行长度上限:SequenceMatcher 最坏 O(n^2),超长行(压缩 JSON 等)跳过比对。
_WORD_DIFF_MAX_CHARS = 3000

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")

# 文件元信息行:必须先于 +/- 内容行判定(与 parse_unified_diff / 旧 DiffViewer 同口径)
_FILE_META_PREFIXES = (
    "--- ", "+++ ", "index ", "new file mode", "deleted file mode",
    "old mode ", "new mode ", "similarity index ", "rename from ",
    "rename to ", "copy from ", "copy to ", "Binary files ",
    "GIT binary patch",
)

# ==================== 语言识别 ====================

_CLIKE_EXTS = frozenset({
    "c", "h", "cpp", "hpp", "cc", "cxx", "hxx", "hh", "cs", "java",
    "js", "jsx", "ts", "tsx", "mjs", "cjs", "swift", "kt", "kts",
    "go", "rs", "php", "dart", "qml", "m", "mm", "groovy", "scala",
})
_PYTHON_EXTS = frozenset({"py", "pyw", "pyi"})
_SHELL_EXTS = frozenset({"sh", "bash", "zsh", "fish", "ps1"})
_JSON_EXTS = frozenset({"json"})
_YAML_EXTS = frozenset({"yml", "yaml", "toml", "ini", "cfg"})
_MARKUP_EXTS = frozenset({"xml", "html", "htm", "svg", "xaml", "ui", "plist"})
_CSS_EXTS = frozenset({"css", "scss", "less"})
_SQL_EXTS = frozenset({"sql"})

_CLIKE_KEYWORDS = frozenset("""
abstract as assert async await base bool break byte case catch char class
const constexpr continue debugger default defer delegate delete do double
dynamic else enum event explicit export extends extern false final finally
fixed float for foreach friend func function global goto if impl implements
import in inline instanceof int interface internal is lambda let lock long
match module mutable namespace new nil none not null nullptr operator or
override package params private protected public raise readonly ref register
require return sealed self short signed sizeof static struct super switch
synchronized template this throw throws trait transient true try type
typedef typename typealias typeof union unsafe unsigned use using var
virtual void volatile when where while with yield and xor event data id
property signal alias component end then
""".split())

_PYTHON_KEYWORDS = frozenset("""
and as assert async await break class continue def del elif else except
False finally for from global if import in is lambda None nonlocal not or
pass raise return True try while with yield match case self cls
""".split())

_SHELL_KEYWORDS = frozenset("""
if then else elif fi for while until do done case esac in function select
time return exit export local readonly set unset source alias echo cd eval
exec shift trap true false break continue
""".split())

_JSON_KEYWORDS = frozenset({"true", "false", "null"})
_YAML_KEYWORDS = frozenset({"true", "false", "null", "yes", "no", "on", "off"})

_SQL_KEYWORDS = frozenset("""
select from where insert into values update set delete create table drop
alter index view join left right inner outer on group by order having limit
and or not null primary key foreign references distinct as commit rollback
begin union all exists between like asc desc
""".split())


def _lang_family(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext in _CLIKE_EXTS:
        return "clike"
    if ext in _PYTHON_EXTS:
        return "python"
    if ext in _SHELL_EXTS:
        return "shell"
    if ext in _JSON_EXTS:
        return "json"
    if ext in _YAML_EXTS:
        return "yaml"
    if ext in _MARKUP_EXTS:
        return "markup"
    if ext in _CSS_EXTS:
        return "css"
    if ext in _SQL_EXTS:
        return "sql"
    return "default"


# ==================== 逐行 tokenizer(产出 fg 区间) ====================

_CLIKE_TOKEN_RE = re.compile(
    r"//[^\n]*"                                      # 行注释
    r'|(?:[bBrRfUu]{0,2})"(?:[^"\\\n]|\\.)*"?'       # 双引号串
    r"|(?:[bBrRfUu]{0,2})'(?:[^'\\\n]|\\.)*'?"       # 单引号串
    r"|`(?:[^`\\\n]|\\.)*`?"                         # 反引号串(模板字符串)
    r"|\b(?:0[xX][0-9a-fA-F_]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)[fFuUlL]*\b"
    r"|[A-Za-z_]\w*"
)
_PYTHON_TOKEN_RE = re.compile(
    r'(?:[rRbBFfUu]{0,3})"(?:[^"\\\n]|\\.)*"?'
    r"|(?:[rRbBFfUu]{0,3})'(?:[^'\\\n]|\\.)*'?"
    r"|\b(?:0[xXoO][0-9a-fA-F_]+|\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?)[jJlL]*\b"
    r"|[A-Za-z_]\w*"
)
_SHELL_TOKEN_RE = re.compile(
    r'"(?:[^"\\\n]|\\.)*"?'
    r"|'(?:[^'\\\n]|\\.)*'?"
    r"|\$\{[^}\n]*\}"
    r"|\b\d+\b"
    r"|[A-Za-z_]\w*"
)
_MARKUP_TOKEN_RE = re.compile(
    r'"[^"\n]*"?'
    r"|</?[A-Za-z][\w:.-]*"
    r"|\b\d+(?:\.\d+)?\b"
)
_CSS_TOKEN_RE = re.compile(
    r'"(?:[^"\\\n]|\\.)*"?'
    r"|'(?:[^'\\\n]|\\.)*'?"
    r"|#[0-9a-fA-F]{3,8}\b"
    r"|\b\d+(?:\.\d+)?(?:px|em|rem|vh|vw|s|ms|pt|%)?\b"
    r"|@[A-Za-z-]+"
    r"|[A-Za-z-]+(?=\s*[:{])"
)
_SQL_TOKEN_RE = re.compile(
    r"'(?:[^'\\\n]|\\.)*'?"
    r'|"(?:[^"\\\n]|\\.)*"?'
    r"|\b\d+(?:\.\d+)?\b"
    r"|[A-Za-z_]\w*"
)
_DEFAULT_TOKEN_RE = re.compile(
    r'"(?:[^"\\\n]|\\.)*"?'
    r"|'(?:[^'\\\n]|\\.)*'?"
    r"|\b\d+(?:\.\d+)?\b"
    r"|[A-Za-z_]\w*"
)

_TRIPLE_RE = re.compile(r"(?:[rRbBFfUu]{0,3})(\"\"\"|''')")


def _push(out: list, start: int, end: int, kind: str) -> None:
    if end > start:
        out.append((start, end, kind))


def _scan_block_comment_line(
    text: str, out: list, state: dict, close_tok: str,
) -> tuple[int, bool]:
    """处理处于块注释中的行前缀(整行或行首到闭合符)。

    返回 (扫描起始位置, 是否整行都在注释里)。
    """
    length = len(text)
    close = text.find(close_tok)
    if close < 0:
        _push(out, 0, length, "c")
        return length, True
    _push(out, 0, close + len(close_tok), "c")
    state["block"] = False
    return close + len(close_tok), False


def _scan_clike(text: str, state: dict) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    length = len(text)
    pos, whole = _scan_block_comment_line(text, out, state, "*/")
    if whole:
        return out

    while pos < length:
        if text.startswith("//", pos):
            _push(out, pos, length, "c")
            break
        if text.startswith("/*", pos):
            close = text.find("*/", pos + 2)
            if close < 0:
                _push(out, pos, length, "c")
                state["block"] = True
                break
            _push(out, pos, close + 2, "c")
            pos = close + 2
            continue
        break

    if state.get("block"):
        return out

    for m in _CLIKE_TOKEN_RE.finditer(text, pos):
        token = m.group(0)
        first = token[0]
        if first in "\"'`":
            _push(out, m.start(), m.end(), "s")
        elif first.isdigit():
            _push(out, m.start(), m.end(), "n")
        elif token in _CLIKE_KEYWORDS:
            _push(out, m.start(), m.end(), "k")
    return out


def _scan_python(text: str, state: dict) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    length = len(text)
    pos = 0
    pending = state.get("py_triple")
    if pending:
        close = text.find(pending)
        if close < 0:
            _push(out, 0, length, "s")
            return out
        _push(out, 0, close + 3, "s")
        pos = close + 3
        state["py_triple"] = None

    # 三引号状态机(先于行注释:字符串里可能有 #)
    while pos < length:
        triple = _TRIPLE_RE.search(text, pos)
        if triple is None:
            break
        quote = triple.group(1)
        close = text.find(quote, triple.end())
        if close < 0:
            _push(out, triple.start(), length, "s")
            state["py_triple"] = quote
            break
        _push(out, triple.start(), close + 3, "s")
        pos = close + 3

    # 行注释:仅在非字符串前缀中(# 前的引号数为偶)才视为注释
    if not state.get("py_triple"):
        hash_pos = -1
        in_single = in_double = False
        for idx in range(pos, length):
            ch = text[idx]
            if ch == "'" and not in_double:
                in_single = not in_single
            elif ch == '"' and not in_single:
                in_double = not in_double
            elif ch == "#" and not in_single and not in_double:
                hash_pos = idx
                break
        if hash_pos >= 0:
            _push(out, hash_pos, length, "c")
            text = text[:hash_pos]
            length = hash_pos

    if state.get("py_triple"):
        return out

    for m in _PYTHON_TOKEN_RE.finditer(text, pos):
        token = m.group(0)
        first = token[0]
        if first in "\"'":
            _push(out, m.start(), m.end(), "s")
        elif first.isdigit():
            _push(out, m.start(), m.end(), "n")
        elif token in _PYTHON_KEYWORDS:
            _push(out, m.start(), m.end(), "k")
    return out


def _scan_shell(text: str, state: dict) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    in_single = in_double = False
    hash_pos = -1
    for idx, ch in enumerate(text):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            hash_pos = idx
            break
    if hash_pos >= 0:
        _push(out, hash_pos, len(text), "c")
        text = text[:hash_pos]
    for m in _SHELL_TOKEN_RE.finditer(text):
        token = m.group(0)
        first = token[0]
        if first in "\"'":
            _push(out, m.start(), m.end(), "s")
        elif first == "$":
            continue
        elif first.isdigit():
            _push(out, m.start(), m.end(), "n")
        elif token in _SHELL_KEYWORDS:
            _push(out, m.start(), m.end(), "k")
    return out


def _scan_markup(text: str, state: dict) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    length = len(text)
    pos = 0
    if state.get("block"):
        close = text.find("-->")
        if close < 0:
            _push(out, 0, length, "c")
            return out
        _push(out, 0, close + 3, "c")
        pos = close + 3
        state["block"] = False

    while pos < length:
        comment = text.find("<!--", pos)
        if comment < 0:
            break
        close = text.find("-->", comment + 4)
        if close < 0:
            _push(out, comment, length, "c")
            state["block"] = True
            break
        _push(out, comment, close + 3, "c")
        pos = close + 3

    if state.get("block"):
        return out

    for m in _MARKUP_TOKEN_RE.finditer(text, pos):
        token = m.group(0)
        first = token[0]
        if first == '"':
            _push(out, m.start(), m.end(), "s")
        elif first == "<":
            _push(out, m.start(), m.end(), "k")
        elif first.isdigit():
            _push(out, m.start(), m.end(), "n")
    return out


def _scan_css(text: str, state: dict) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    length = len(text)
    pos, whole = _scan_block_comment_line(text, out, state, "*/")
    if whole:
        return out

    if text.startswith("/*", pos):
        close = text.find("*/", pos + 2)
        if close < 0:
            _push(out, pos, length, "c")
            state["block"] = True
            return out
        _push(out, pos, close + 2, "c")
        pos = close + 2

    for m in _CSS_TOKEN_RE.finditer(text, pos):
        token = m.group(0)
        first = token[0]
        if first in "\"'":
            _push(out, m.start(), m.end(), "s")
        elif first == "#":
            _push(out, m.start(), m.end(), "n")
        elif first == "@":
            _push(out, m.start(), m.end(), "k")
        elif first.isdigit():
            _push(out, m.start(), m.end(), "n")
        else:
            _push(out, m.start(), m.end(), "k")  # 属性/选择器名
    return out


def _scan_sql(text: str, state: dict) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    length = len(text)
    pos, whole = _scan_block_comment_line(text, out, state, "*/")
    if whole:
        return out

    while pos < length:
        if text.startswith("--", pos):
            _push(out, pos, length, "c")
            break
        if text.startswith("/*", pos):
            close = text.find("*/", pos + 2)
            if close < 0:
                _push(out, pos, length, "c")
                state["block"] = True
                break
            _push(out, pos, close + 2, "c")
            pos = close + 2
            continue
        break

    if state.get("block"):
        return out

    for m in _SQL_TOKEN_RE.finditer(text, pos):
        token = m.group(0)
        first = token[0]
        if first in "\"'":
            _push(out, m.start(), m.end(), "s")
        elif first.isdigit():
            _push(out, m.start(), m.end(), "n")
        elif token.lower() in _SQL_KEYWORDS:
            _push(out, m.start(), m.end(), "k")
    return out


def _scan_simple(text: str, family: str) -> list[tuple[int, int, str]]:
    """json/yaml/default:字符串 + 数字 + 关键字,无块注释。"""
    out: list[tuple[int, int, str]] = []
    keywords = _JSON_KEYWORDS if family == "json" else (
        _YAML_KEYWORDS if family == "yaml" else frozenset())
    for m in _DEFAULT_TOKEN_RE.finditer(text):
        token = m.group(0)
        first = token[0]
        if first in "\"'":
            _push(out, m.start(), m.end(), "s")
        elif first.isdigit():
            _push(out, m.start(), m.end(), "n")
        elif token in keywords:
            _push(out, m.start(), m.end(), "k")
    return out


def _tokenize_line(text: str, family: str, state: dict) -> list[tuple[int, int, str]]:
    if family == "clike":
        return _scan_clike(text, state)
    if family == "python":
        return _scan_python(text, state)
    if family == "shell":
        return _scan_shell(text, state)
    if family == "markup":
        return _scan_markup(text, state)
    if family == "css":
        return _scan_css(text, state)
    if family == "sql":
        return _scan_sql(text, state)
    return _scan_simple(text, family)


# ==================== fg/bg 合并为渲染段 ====================

def _merge_segments(
    fg_ranges: list[tuple[int, int, str]], bg_ranges: list[tuple[int, int, str]]
) -> list[list]:
    """把互不重叠的 fg/bg 区间合并成 [start, end, fg, bg] 渲染段。"""
    if not fg_ranges and not bg_ranges:
        return []
    bounds: set[int] = set()
    for start, end, _ in fg_ranges:
        bounds.add(start)
        bounds.add(end)
    for start, end, _ in bg_ranges:
        bounds.add(start)
        bounds.add(end)
    ordered = sorted(bounds)
    segments: list[list] = []
    for idx in range(len(ordered) - 1):
        start, end = ordered[idx], ordered[idx + 1]
        fg = ""
        for fs, fe, fk in fg_ranges:
            if fs <= start and end <= fe:
                fg = fk
                break
        bg = ""
        for bs, be, bk in bg_ranges:
            if bs <= start and end <= be:
                bg = bk
                break
        if segments and segments[-1][1] == start \
                and segments[-1][2] == fg and segments[-1][3] == bg:
            segments[-1][1] = end
        else:
            segments.append([start, end, fg, bg])
    return segments


# ==================== 词级比对(产出 bg 区间) ====================

def _word_bg_pair(old_text: str, new_text: str) -> tuple[list, list]:
    """一对删除/新增行的字符级比对,返回 (旧行bg区间, 新行bg区间)。"""
    old_len, new_len = len(old_text), len(new_text)
    if old_len == 0 or new_len == 0:
        return [], []
    if max(old_len, new_len) > _WORD_DIFF_MAX_CHARS:
        return [], []
    if old_text == new_text:
        return [], []
    matcher = SequenceMatcher(None, old_text, new_text, autojunk=False)
    old_bg: list[tuple[int, int, str]] = []
    new_bg: list[tuple[int, int, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("delete", "replace"):
            old_bg.append((i1, i2, "d"))
        if tag in ("insert", "replace"):
            new_bg.append((j1, j2, "a"))
    return old_bg, new_bg


# ==================== 主解析 ====================

def parse_diff_rows(raw_diff: str) -> dict:
    """解析 unified diff 为结构化行模型(见模块 docstring)。"""
    from app.common.git_service import GitService  # 延迟导入避免环

    raw = raw_diff or ""
    file_diffs = GitService.parse_unified_diff(raw)

    # 第一趟:行分类 + 双行号(与 GitService.parse_unified_diff 的文件切分口径一致:
    # 仅 "diff --git " 开启新文件,fi 与 files 下标对齐)
    rows: list[dict] = []
    fi = -1
    old_no = new_no = 0
    for line in raw.splitlines():
        if line.startswith("diff --git "):
            fi += 1
            rows.append({"t": "file", "o": -1, "n": -1, "x": line, "fi": fi})
            old_no = new_no = 0
            continue
        if fi < 0:
            rows.append({"t": "meta", "o": -1, "n": -1, "x": line, "fi": 0})
            continue
        if line.startswith("@@"):
            match = _HUNK_RE.match(line)
            if match:
                old_no = int(match.group(1))
                new_no = int(match.group(2))
            rows.append({"t": "hunk", "o": -1, "n": -1, "x": line, "fi": fi})
            continue
        if line.startswith(_FILE_META_PREFIXES):
            rows.append({"t": "meta", "o": -1, "n": -1, "x": line, "fi": fi})
            continue
        prefix = line[:1]
        if prefix == "+":
            rows.append({"t": "add", "o": -1, "n": new_no, "x": line[1:], "fi": fi})
            new_no += 1
        elif prefix == "-":
            rows.append({"t": "del", "o": old_no, "n": -1, "x": line[1:], "fi": fi})
            old_no += 1
        elif prefix == " ":
            rows.append({"t": "ctx", "o": old_no, "n": new_no, "x": line[1:], "fi": fi})
            old_no += 1
            new_no += 1
        elif prefix == "\\":
            rows.append({"t": "meta", "o": -1, "n": -1, "x": line, "fi": fi})
        elif line != "":
            rows.append({"t": "meta", "o": -1, "n": -1, "x": line, "fi": fi})

    # 文件路径表(供 QML 过滤按钮按文件名匹配,口径同 filter_unified_diff)
    files = [
        {
            "path": f.path,
            "old_path": f.old_path,
            "new_path": f.new_path,
            "status": f.status,
            "additions": f.additions,
            "deletions": f.deletions,
        }
        for f in file_diffs
    ]

    # 每个文件的语言:优先 new_path,退化 old_path(来自 +++/--- 行,已是剥前缀路径)
    families: list[str] = []
    for f in files:
        lang_path = f.get("new_path") or f.get("old_path") or f.get("path") or ""
        families.append(_lang_family(lang_path))

    # 第二趟:语法着色 fg(每文件一个状态机,块注释/三引号跨行)
    states: dict[int, dict] = {}
    for row in rows:
        if row["t"] not in ("add", "del", "ctx"):
            continue
        index = row["fi"]
        state = states.setdefault(index, {})
        row["fg"] = _tokenize_line(row["x"], families[index] if 0 <= index < len(families) else "default", state)

    # 第三趟:词级比对 bg(删除队列跨 hunk 保留,遇文件边界清空;
    # 与旧 JS 分栏配对同策略:第 i 个删除行配第 i 个新增行)
    del_queue: list[dict] = []
    for row in rows:
        if row["t"] == "file":
            del_queue.clear()
            continue
        if row["t"] == "del":
            del_queue.append(row)
        elif row["t"] == "add":
            if del_queue:
                old_row = del_queue.pop(0)
                old_bg, new_bg = _word_bg_pair(old_row["x"], row["x"])
                old_row["bg"] = old_bg
                row["bg"] = new_bg

    # 第四趟:合并 fg+bg 为渲染段;清理中间字段
    for row in rows:
        fg = row.pop("fg", None) or []
        bg = row.pop("bg", None) or []
        segments = _merge_segments(fg, bg)
        if segments:
            row["seg"] = segments

    return {"files": files, "rows": rows}


def rows_to_json(payload: dict) -> str:
    """行模型序列化为紧凑 JSON(跨 bridge 传 QML)。"""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
