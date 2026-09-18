# coding: utf-8
"""按 ``file:///`` URL 字符长度反查 QML/JS 源文件（零依赖）。

原理
----
当 Qt 的 QML 诊断里源文件 QUrl 的字符串内容被读成 N 个 ``U+0000`` 时，
其百分号编码形式会在日志中留下 **N 组 ``%00``**（例如
``[QML] %00%00…%00:52: ReferenceError: [QtContext] category=default file=%00…``）。
因此 **N 恰好等于原始 URL 的字符数**，可用来把"文件名已被清零"的报错反查回具体文件。

注意
----
- ``file=`` 段可能被日志层按字符数截断（PrismQML 为 240 字符 ⇒ 恰好 80 组 ``%00`` 加 ``...``），
  所以**以未被截断的 message 段组数为准**。
- 反查得到的是**候选集**；同一长度可能命中多个文件，需再结合 ``line=`` 与引擎树收敛。

用法::

    python tools/qml_url_length_lookup.py 57
    python tools/qml_url_length_lookup.py 102 84 --root D:\\extra\\qml

``--root`` 省略时，从本仓库位置推导：应用自身 QML、同级 ``PrismQML`` 源码树的 QML、
``.venv`` 安装版引擎的 QML。
"""

import argparse
import os
import sys
from pathlib import Path

SOURCE_SUFFIXES = (".qml", ".js", ".mjs")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _dedupe(pairs):
    """按真实路径去重：Windows 上 Lib 与 lib 是同一目录，否则会被扫两遍。"""
    seen = set()
    unique = []
    for label, path in pairs:
        key = os.path.normcase(os.path.realpath(str(path)))
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, path))
    return unique


def default_roots() -> list:
    """推导候选根目录：(标签, 路径)。不硬编码开发机路径。"""
    repo_root = _repo_root()
    found = []

    app_qml = repo_root / "app_qml" / "qml"
    if app_qml.is_dir():
        found.append(("app-qml", app_qml))

    dev_qml = repo_root.parent / "PrismQML" / "prismqml" / "PrismQML"
    if dev_qml.is_dir():
        found.append(("dev-source-tree", dev_qml))

    venv_root = repo_root / ".venv"
    venv_qml_candidates = [
        venv_root / "Lib" / "site-packages" / "prismqml" / "PrismQML",
        venv_root / "lib" / "site-packages" / "prismqml" / "PrismQML",
    ]
    if venv_root.is_dir():
        venv_qml_candidates += sorted(
            venv_root.glob("lib/python*/site-packages/prismqml/PrismQML")
        )
    for candidate in venv_qml_candidates:
        if candidate.is_dir():
            found.append(("venv-installed", candidate))
    return _dedupe(found)


def url_of(path) -> str:
    """与 Qt 一致的本地文件 URL 形式。"""
    return "file:///" + str(path).replace("\\", "/")


def collect(roots, lengths):
    hits = {length: [] for length in lengths}
    scanned = 0
    for label, root in roots:
        for path in Path(root).rglob("*"):
            if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            scanned += 1
            size = len(url_of(path))
            if size in hits:
                hits[size].append((label, path))
    return hits, scanned


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="按 file:/// URL 字符长度反查 QML/JS 文件"
    )
    parser.add_argument(
        "lengths",
        nargs="+",
        type=int,
        help="NUL 组数，即日志中连续的 %%00 组数（= 原始 URL 字符数）",
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help="追加搜索根目录（可重复）；默认从本仓库位置推导",
    )
    parser.add_argument(
        "--no-default-roots",
        action="store_true",
        help="不自动推导根目录，只用 --root 显式给出的",
    )
    args = parser.parse_args(argv)

    roots = [] if args.no_default_roots else default_roots()
    roots += [("给定", Path(item)) for item in args.root]
    if not roots:
        parser.error("没有可搜索的根目录，请用 --root 指定")

    for label, root in roots:
        print("[搜索根] %-16s %s" % (label, root))

    hits, scanned = collect(roots, set(args.lengths))
    print("扫描文件数: %d" % scanned)
    for length in args.lengths:
        entries = hits.get(length, [])
        print("=== 长度 %d -> %d 个候选 ===" % (length, len(entries)))
        for label, path in entries:
            print("    [%s] %s" % (label, path))
        if not entries:
            print("    （无命中）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
