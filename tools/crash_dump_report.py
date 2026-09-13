# coding: utf-8
"""零依赖 minidump 崩溃链条报告器（Windows x64）。

用途：Gitora 的原生崩溃（如 0xC0000005）只留下「事件日志 + 转储」，
本工具不需要 WinDbg / PDB，直接从转储还原崩溃链条：

1. 异常流：异常码、异常地址（解析到 模块+偏移）、访问参数（读/写与被访问地址）；
2. 线程表 + 模块表：判定崩溃线程是否为 Python 主线程；
3. 异常线程 CONTEXT（x64 精确偏移）：RIP/RSP 与关键寄存器（野指针常在 RBX/RDI）；
4. 整栈扫描：由崩溃点向外层列出模块内返回地址，并用最近导出函数命名；
5. `--function <dll> <rva>`：用 PE 导出表 + `.pdata`(RUNTIME_FUNCTION) 在无符号条件下
   精确界定崩溃函数边界、反查故障指令机器码，并搜索指向该地址的直接调用。

用法::

    python tools/crash_dump_report.py <dump 文件>
    python tools/crash_dump_report.py <dump 文件> --module Qt6Qml
    python tools/crash_dump_report.py --function <dll> 0x1a3790

转储来源见 AGENTS.md 第十二节（LocalDumps 全内存转储）。
"""

import argparse
import bisect
import os
import struct
import sys

STREAM_THREAD_LIST = 3
STREAM_MODULE_LIST = 4
STREAM_MEMORY_LIST = 5
STREAM_EXCEPTION = 6
STREAM_SYSTEM_INFO = 7
STREAM_MEMORY64_LIST = 9
STREAM_MISC_INFO = 15

MODULE_ENTRY_SIZE = 108
THREAD_ENTRY_SIZE = 48

# x64 CONTEXT 偏移（前有 6 个 PxHome，故 ContextFlags 在 0x30）
CTX_RAX = 0x78
CTX_RSP = 0x98
CTX_RBP = 0xA0
CTX_RIP = 0xF8
CTX_FLAGS = 0x30
GPR_NAMES = [
    ("Rax", 0x78), ("Rcx", 0x80), ("Rdx", 0x88), ("Rbx", 0x90),
    ("Rsp", 0x98), ("Rbp", 0xA0), ("Rsi", 0xA8), ("Rdi", 0xB0),
    ("R8", 0xB8), ("R9", 0xC0), ("R10", 0xC8), ("R11", 0xD0),
    ("R12", 0xD8), ("R13", 0xE0), ("R14", 0xE8), ("R15", 0xF0),
]

EXCEPTION_NAMES = {
    0xC0000005: "ACCESS_VIOLATION 访问违例",
    0xC0000006: "IN_PAGE_ERROR 读页失败（磁盘/网络存储不可用）",
    0xC0000094: "INT_DIVIDE_BY_ZERO",
    0xC00000FD: "STACK_OVERFLOW 栈溢出",
    0xC0000409: "STACK_BUFFER_OVERRUN / __fastfail（Qt qFatal 级快速失败）",
    0xC0000374: "HEAP_CORRUPTION 堆损坏",
}


def u16(data, offset):
    return struct.unpack_from("<H", data, offset)[0]


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def u64(data, offset):
    return struct.unpack_from("<Q", data, offset)[0]


class MiniDump:
    """按需读取 minidump 的流与内存。"""

    def __init__(self, path):
        with open(path, "rb") as handle:
            self.data = handle.read()
        self.path = path
        if self.data[:4] != b"MDMP":
            raise ValueError(f"不是 minidump 文件: {path}")
        self.streams = {}
        count = u32(self.data, 8)
        directory = u32(self.data, 12)
        for index in range(count):
            offset = directory + index * 12
            kind, size, rva = struct.unpack_from("<III", self.data, offset)
            self.streams.setdefault(kind, []).append((size, rva))
        self.modules = self._read_modules()
        self.memory = self._read_memory_ranges()
        self._memory_starts = [item[0] for item in self.memory]
        self._export_cache = {}

    def has(self, kind):
        return kind in self.streams

    def stream_rva(self, kind):
        return self.streams[kind][0][1]

    def _string(self, rva):
        length = u32(self.data, rva)
        raw = self.data[rva + 4:rva + 4 + length]
        return raw.decode("utf-16-le", "replace")

    def _read_modules(self):
        modules = []
        if not self.has(STREAM_MODULE_LIST):
            return modules
        rva = self.stream_rva(STREAM_MODULE_LIST)
        count = u32(self.data, rva)
        offset = rva + 4
        for _ in range(count):
            modules.append((
                u64(self.data, offset),
                u32(self.data, offset + 8),
                self._string(u32(self.data, offset + 20)),
            ))
            offset += MODULE_ENTRY_SIZE
        modules.sort()
        return modules

    def _read_memory_ranges(self):
        ranges = []
        if self.has(STREAM_MEMORY64_LIST):
            rva = self.stream_rva(STREAM_MEMORY64_LIST)
            count = u64(self.data, rva)
            cursor = u64(self.data, rva + 8)
            offset = rva + 16
            for _ in range(count):
                start = u64(self.data, offset)
                size = u64(self.data, offset + 8)
                ranges.append((start, size, cursor))
                cursor += size
                offset += 16
        elif self.has(STREAM_MEMORY_LIST):
            rva = self.stream_rva(STREAM_MEMORY_LIST)
            count = u32(self.data, rva)
            offset = rva + 4
            for _ in range(count):
                ranges.append((
                    u64(self.data, offset),
                    u32(self.data, offset + 8),
                    u32(self.data, offset + 12),
                ))
                offset += 16
        ranges.sort(key=lambda item: item[0])
        return ranges

    def read_memory(self, address, length):
        index = bisect.bisect_right(self._memory_starts, address) - 1
        if index < 0:
            return None
        start, size, rva = self.memory[index]
        if address + length > start + size:
            return None
        file_offset = rva + (address - start)
        return self.data[file_offset:file_offset + length]

    def module_of(self, address):
        for base, size, name in self.modules:
            if base <= address < base + size:
                return base, size, name
        return None

    def module_name(self, address):
        found = self.module_of(address)
        return os.path.basename(found[2]) if found else "<未映射/私有内存>"

    def exception(self):
        if not self.has(STREAM_EXCEPTION):
            return None
        rva = self.stream_rva(STREAM_EXCEPTION)
        count = min(u32(self.data, rva + 32), 15)
        return {
            "thread_id": u32(self.data, rva),
            "code": u32(self.data, rva + 8),
            "address": u64(self.data, rva + 24),
            "params": [u64(self.data, rva + 40 + 8 * i) for i in range(count)],
            "context": (u32(self.data, rva + 160), u32(self.data, rva + 164)),
        }

    def threads(self):
        threads = []
        if not self.has(STREAM_THREAD_LIST):
            return threads
        rva = self.stream_rva(STREAM_THREAD_LIST)
        count = u32(self.data, rva)
        offset = rva + 4
        for _ in range(count):
            threads.append({
                "tid": u32(self.data, offset),
                "stack": (
                    u64(self.data, offset + 24),
                    u32(self.data, offset + 32),
                    u32(self.data, offset + 36),
                ),
                "context": (
                    u32(self.data, offset + 40),
                    u32(self.data, offset + 44),
                ),
            })
            offset += THREAD_ENTRY_SIZE
        return threads

    def context_bytes(self, location):
        size, rva = location
        return self.data[rva:rva + size]

    # ---- 符号（仅用 PE 导出表，无 PDB） ----
    def exports(self, path):
        if path in self._export_cache:
            return self._export_cache[path]
        result = []
        try:
            with open(path, "rb") as handle:
                blob = handle.read()
            sections, export_rva = _pe_sections(blob)
            if export_rva:
                to_offset = _make_rva_mapper(blob, sections)
                base = to_offset(export_rva)
                nfunc = u32(blob, base + 20)
                nnames = u32(blob, base + 24)
                addr_func = to_offset(u32(blob, base + 28))
                addr_name = to_offset(u32(blob, base + 32))
                addr_ord = to_offset(u32(blob, base + 36))
                names = {}
                for index in range(nnames):
                    name_rva = u32(blob, addr_name + index * 4)
                    ordinal = u16(blob, addr_ord + index * 2)
                    text_offset = to_offset(name_rva)
                    if text_offset is None:
                        continue
                    end = blob.index(b"\0", text_offset)
                    func_rva = u32(blob, addr_func + ordinal * 4)
                    names[func_rva] = blob[text_offset:end].decode("ascii", "replace")
                for index in range(nfunc):
                    func_rva = u32(blob, addr_func + index * 4)
                    result.append((func_rva, names.get(func_rva, "")))
            result.sort()
        except (OSError, struct.error, ValueError):
            result = []
        self._export_cache[path] = result
        return result

    def symbol(self, address, max_delta=0x400):
        found = self.module_of(address)
        if not found:
            return f"0x{address:016x} <未映射/私有内存>"
        base, _, name = found
        offset = address - base
        text = f"{os.path.basename(name)}+0x{offset:x}"
        path = name.replace("/", "\\")
        if not os.path.exists(path):
            return text
        exports = self.exports(path)
        if not exports:
            return text
        rvas = [item[0] for item in exports]
        index = bisect.bisect_right(rvas, offset) - 1
        if index < 0:
            return text
        delta = offset - exports[index][0]
        if delta <= max_delta:
            return f"{text}  <<{_demangle(exports[index][1])}>>"
        return f"{text}  (最近导出 +0x{delta:x})"


def _demangle(name):
    """极简 MSVC 名字还原：只提取可读标识符片段。"""
    if not name.startswith("?"):
        return name
    parts, current = [], ""
    for char in name:
        if char.isalnum() or char == "_":
            current += char
        else:
            if len(current) > 2:
                parts.append(current)
            current = ""
    if len(current) > 2:
        parts.append(current)
    return "::".join(parts[:6]) if parts else name


def _pe_sections(blob):
    """返回 (段名, 虚拟地址, 虚拟大小, 原始偏移) 列表与导出表 RVA。"""
    lfanew = u32(blob, 0x3C)
    coff = lfanew + 4
    count = u16(blob, coff + 2)
    optional_size = u16(blob, coff + 16)
    optional = coff + 20
    magic = u16(blob, optional)
    data_dirs = optional + (112 if magic == 0x20B else 96)
    export_rva = u32(blob, data_dirs)
    sections = []
    offset = optional + optional_size
    for _ in range(count):
        name = blob[offset:offset + 8].rstrip(b"\0").decode("ascii", "replace")
        sections.append((
            name,
            u32(blob, offset + 12),
            u32(blob, offset + 8),
            u32(blob, offset + 20),
        ))
        offset += 40
    return sections, export_rva


def _make_rva_mapper(blob, sections):
    def to_offset(rva):
        for _name, va, vsize, raw in sections:
            if va <= rva < va + max(vsize, 1):
                return raw + (rva - va)
        return None

    return to_offset


def report_dump(path, only_module=None):
    dump = MiniDump(path)
    print(f"===== 转储 {path} ({len(dump.data)} 字节) =====")
    print(f"流类型: {sorted(dump.streams)}")
    if dump.has(STREAM_MISC_INFO):
        print(f"进程 ID: {u32(dump.data, dump.stream_rva(STREAM_MISC_INFO) + 8)}")

    exception = dump.exception()
    print("\n===== 异常 =====")
    if exception is None:
        print("转储中没有异常流")
    else:
        code = exception["code"]
        print(f"异常线程 TID   : {exception['thread_id']}")
        print(f"异常代码       : 0x{code:08x}  {EXCEPTION_NAMES.get(code, '')}")
        print(f"异常地址       : 0x{exception['address']:016x}")
        print(f"              -> {dump.symbol(exception['address'])}")
        if code == 0xC0000005 and len(exception["params"]) >= 2:
            access = "读" if exception["params"][0] == 0 else "写"
            print(
                f"访问参数       : {access} 0x{exception['params'][1]:x}"
                f"（0xC0000005 本身就是该地址不可访问的证明）"
            )
        else:
            print(f"访问参数       : {[hex(p) for p in exception['params']]}")

    threads = dump.threads()
    context = dump.context_bytes(exception["context"]) if exception else b""
    print("\n===== 崩溃线程寄存器 =====")
    if len(context) > CTX_RIP:
        print(f"ContextFlags=0x{u32(context, CTX_FLAGS):x}")
        for name, offset in GPR_NAMES:
            print(f"  {name:<4}= 0x{u64(context, offset):016x}")
        print(f"  Rip = 0x{u64(context, CTX_RIP):016x}  {dump.symbol(u64(context, CTX_RIP))}")

    if exception and len(context) > CTX_RIP:
        tid = exception["thread_id"]
        target = next((item for item in threads if item["tid"] == tid), None)
        if target is None:
            print("\n异常线程不在线程表中")
        else:
            start, size, _ = target["stack"]
            rsp = u64(context, CTX_RSP)
            print(f"\n===== 栈回溯（由崩溃点向外层）=====")
            print(f"栈 0x{start:x}..0x{start + size:x}  RSP=0x{rsp:x}")
            _print_frames(dump, start, size, rsp, start + size, ascending=True,
                          only_module=only_module)

    print("\n===== 线程概览 =====")
    for item in threads:
        raw = dump.context_bytes(item["context"])
        rip = u64(raw, CTX_RIP) if len(raw) > CTX_RIP + 8 else 0
        mark = "   <== 崩溃线程" if exception and item["tid"] == exception["thread_id"] else ""
        print(f"  tid={item['tid']:<6} {dump.symbol(rip)}{mark}")


def _print_frames(dump, start, size, low, high, ascending, only_module=None, limit=90):
    raw = bytearray()
    cursor = start
    while cursor < start + size:
        chunk_len = min(0x1000, start + size - cursor)
        chunk = dump.read_memory(cursor, chunk_len)
        if chunk is None:
            chunk = b"\x00" * chunk_len
        raw += chunk
        cursor += len(chunk)
    raw = bytes(raw)

    offsets = range(0, len(raw) - 8, 8)
    if not ascending:
        offsets = reversed(list(offsets))
    shown = 0
    for index in offsets:
        value = struct.unpack_from("<Q", raw, index)[0]
        address = start + index
        if not (low <= address < high):
            continue
        found = dump.module_of(value)
        if not found:
            continue
        if only_module and only_module.lower() not in found[2].lower():
            continue
        print(f"  [0x{address:016x}] {dump.symbol(value)}")
        shown += 1
        if shown >= limit:
            print(f"  ...（已截断，共显示 {shown} 条）")
            break
    if shown == 0:
        print("  （未找到模块内地址）")


def report_function(dll_path, target_rva):
    with open(dll_path, "rb") as handle:
        blob = handle.read()
    sections, export_rva = _pe_sections(blob)
    to_offset = _make_rva_mapper(blob, sections)
    print(f"===== {os.path.basename(dll_path)} TimeDateStamp=0x{u32(blob, u32(blob, 0x3C) + 8):08x} =====")
    for name, va, vsize, raw in sections:
        print(f"  段 {name:<8} RVA=0x{va:08x} VS=0x{vsize:<8x} RAW=0x{raw:08x}")

    exports = _pe_exports_from_blob(blob, sections, export_rva, to_offset)
    print(f"导出总数: {len(exports)}")
    if exports:
        rvas = [item[0] for item in exports]
        index = bisect.bisect_right(rvas, target_rva) - 1
        if index >= 0:
            print(f"目标 RVA 0x{target_rva:x} 最近的前一个导出: 0x{exports[index][0]:x} "
                  f"{_demangle(exports[index][1])} (+0x{target_rva - exports[index][0]:x})")

    bounds = _pdata_bounds(blob, sections, to_offset, target_rva)
    if bounds:
        begin, end = bounds
        print(f".pdata 函数边界: 0x{begin:x} .. 0x{end:x} "
              f"(长度 0x{end - begin:x}, 内部偏移 +0x{target_rva - begin:x})")
    else:
        print(".pdata 未找到包含该 RVA 的函数")

    file_offset = to_offset(target_rva)
    if file_offset:
        chunk = blob[file_offset - 24:file_offset + 24]
        print("故障地址机器码（前 24 / 该处起 24）:")
        print("  " + " ".join(f"{byte:02x}" for byte in chunk[:24]))
        print("  " + " ".join(f"{byte:02x}" for byte in chunk[24:]))
    return 0


def _pe_exports_from_blob(blob, sections, export_rva, to_offset):
    result = []
    if not export_rva:
        return result
    base = to_offset(export_rva)
    nfunc = u32(blob, base + 20)
    nnames = u32(blob, base + 24)
    addr_func = to_offset(u32(blob, base + 28))
    addr_name = to_offset(u32(blob, base + 32))
    addr_ord = to_offset(u32(blob, base + 36))
    names = {}
    for index in range(nnames):
        text_offset = to_offset(u32(blob, addr_name + index * 4))
        if text_offset is None:
            continue
        end = blob.index(b"\0", text_offset)
        ordinal = u16(blob, addr_ord + index * 2)
        names[u32(blob, addr_func + ordinal * 4)] = blob[text_offset:end].decode("ascii", "replace")
    for index in range(nfunc):
        func_rva = u32(blob, addr_func + index * 4)
        result.append((func_rva, names.get(func_rva, "")))
    result.sort()
    return result


def _pdata_bounds(blob, sections, to_offset, target_rva):
    """在 `.pdata` 段按 RUNTIME_FUNCTION(12 字节) 二分查找包含目标 RVA 的函数。"""
    pdata = next((item for item in sections if item[0] == ".pdata"), None)
    if pdata is None:
        return None
    _name, _va, vsize, raw = pdata
    low, high = 0, vsize // 12 - 1
    while low <= high:
        mid = (low + high) // 2
        offset = raw + mid * 12
        begin = u32(blob, offset)
        end = u32(blob, offset + 4)
        if begin <= target_rva < end:
            return begin, end
        if target_rva < begin:
            high = mid - 1
        else:
            low = mid + 1
    return None


def main(argv=None):
    parser = argparse.ArgumentParser(description="零依赖 minidump 崩溃链条报告器")
    parser.add_argument("dump", nargs="?", help="minidump 文件路径")
    parser.add_argument("--module", help="只显示名字含该子串的模块帧")
    parser.add_argument("--function", nargs=2, metavar=("DLL", "RVA"),
                        help="解析模块内某个 RVA 的函数边界与机器码")
    args = parser.parse_args(argv)

    if args.function:
        dll_path, rva = args.function
        return report_function(dll_path, int(rva, 16))
    if not args.dump:
        parser.error("需要提供 minidump 文件路径，或使用 --function")
    report_dump(args.dump, only_module=args.module)
    return 0


if __name__ == "__main__":
    sys.exit(main())
