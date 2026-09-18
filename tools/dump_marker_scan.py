# coding: utf-8
"""minidump 身份与引擎来源标记扫描（零依赖，流式）。

拿到一个 GB 级全内存转储时，先回答两个问题，再谈崩溃点：

1. **这个转储是不是目标应用？** —— 同机可能同时跑着别的 Qt/QML 应用，
   它们的崩溃同样是 ``python.exe.*.dmp``，不加区分就会把结论串台。
2. **它加载的是 dev 源码树还是 venv 安装版引擎？** —— 两者日志前缀可能相同，
   但加载路径不同，归因方向完全不同。

实现要点：按块流式读取，不把转储整体读入内存；ASCII 与 UTF-16LE 两种编码都扫。

用法::

    python tools/dump_marker_scan.py <dump> [<dump> ...]
    python tools/dump_marker_scan.py <dump> --marker 幻灵匣 --marker SomeOtherApp
    python tools/dump_marker_scan.py <dump> --engine-root D:\\path\\to\\prismqml-tree

``--engine-root`` 的默认值从本仓库位置推导（同级 ``PrismQML`` 源码树与 ``.venv`` 安装版），
不写死开发机路径。
"""

import argparse
import os
import sys
from pathlib import Path

# 目标应用自身的默认标记（可用 --marker 追加别的应用名做对照）
DEFAULT_MARKERS = ("Gitora", "gitess", "app_qml", "RepoScanner", "main_qml.py")

CHUNK_SIZE = 8 * 1024 * 1024


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _dedupe(pairs):
    """按真实路径去重：Windows 上 Lib 与 lib 是同一目录，否则同一个树会被计入两次。"""
    seen = set()
    unique = []
    for label, path in pairs:
        key = os.path.normcase(os.path.realpath(str(path)))
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, path))
    return unique


def default_engine_roots() -> list:
    """推导候选引擎树：(标签, 路径)。不硬编码开发机路径。"""
    repo_root = _repo_root()
    found = []

    dev_tree = repo_root.parent / "PrismQML" / "prismqml"
    if dev_tree.is_dir():
        found.append(("dev-source-tree", dev_tree))

    venv_root = repo_root / ".venv"
    for candidate in (
        venv_root / "Lib" / "site-packages" / "prismqml",
        venv_root / "lib" / "site-packages" / "prismqml",
    ):
        if candidate.is_dir():
            found.append(("venv-installed", candidate))
    if venv_root.is_dir():
        for candidate in sorted(venv_root.glob("lib/python*/site-packages/prismqml")):
            if candidate.is_dir():
                found.append(("venv-installed", candidate))
    return _dedupe(found)


def build_needles(markers, engine_roots):
    needles = []

    def add(label, text):
        if not text:
            return
        # 非 ASCII 文本按 ascii 编码会得到空字节串，而空 needle 会逐字节命中，
        # 必须显式跳过，否则会出现接近文件大小的假命中。
        ascii_bytes = text.encode("ascii", "ignore")
        if ascii_bytes:
            needles.append((ascii_bytes, label + ".ascii"))
        utf16_bytes = text.encode("utf-16-le")
        if utf16_bytes:
            needles.append((utf16_bytes, label + ".utf16"))

    for marker in markers:
        add(marker, marker)
    for label, path in engine_roots:
        add(label, str(path))
    return needles


def scan(path, needles):
    counts = {label: 0 for _, label in needles}
    # 空 needle 会让 find 每次都成功并退化成逐字节扫描，直接剔除。
    needles = [(needle, label) for needle, label in needles if needle]
    if not needles:
        return counts
    overlap = max(len(needle) for needle, _ in needles) + 16
    tail = b""
    with open(path, "rb") as handle:
        while True:
            block = handle.read(CHUNK_SIZE)
            if not block:
                break
            data = tail + block
            for needle, label in needles:
                start = 0
                while True:
                    index = data.find(needle, start)
                    if index < 0:
                        break
                    counts[label] += 1
                    start = index + 1
            tail = data[-overlap:]
    return counts


def report(path, needles):
    counts = scan(path, needles)
    print("=== %s ===" % path)
    for _, label in needles:
        print("  %-28s %d" % (label, counts[label]))
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description="minidump 身份与引擎来源标记扫描")
    parser.add_argument("dumps", nargs="+", help="一个或多个 minidump 路径")
    parser.add_argument(
        "--marker",
        action="append",
        default=[],
        help="追加身份标记（可重复），用于对照同机其他应用",
    )
    parser.add_argument(
        "--engine-root",
        action="append",
        default=[],
        help="追加引擎树根路径（可重复）；默认从本仓库位置推导",
    )
    parser.add_argument(
        "--no-default-engine-roots",
        action="store_true",
        help="不自动推导引擎树路径，只用 --engine-root 显式给出的",
    )
    args = parser.parse_args(argv)

    markers = list(DEFAULT_MARKERS) + list(args.marker)
    if args.no_default_engine_roots:
        engine_roots = []
    else:
        engine_roots = default_engine_roots()
    engine_roots += [
        ("engine-root(给定)", Path(item)) for item in args.engine_root
    ]

    if not engine_roots:
        print("[提示] 未推导到引擎树路径，可显式传 --engine-root", file=sys.stderr)
    else:
        for label, path in engine_roots:
            print("[引擎树] %-16s %s" % (label, path))

    needles = build_needles(markers, engine_roots)
    for dump in args.dumps:
        if not Path(dump).is_file():
            print("[跳过] 不存在: %s" % dump, file=sys.stderr)
            continue
        report(dump, needles)
    return 0


if __name__ == "__main__":
    sys.exit(main())
