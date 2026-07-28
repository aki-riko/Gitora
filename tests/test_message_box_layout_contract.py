# coding: utf-8
"""禁止 MessageBox 内建标题与自定义表单同级重叠的项目级契约测试。"""
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MESSAGE_BOX_RE = re.compile(r"(?:(?:Fluent\.)?MessageBox)\s*\{")
OBJECT_RE = re.compile(r"^([A-Za-z_][\w.]*)\s*\{")
EMPTY_TITLE_RE = re.compile(r'^title\s*:\s*""\s*;?$')
NON_VISUAL_TYPES = {
    "Binding",
    "Component",
    "Connections",
    "FolderDialog",
    "ListModel",
    "Timer",
}


def _strip_qml_line(line: str) -> str:
    """去除字符串和行尾注释，保留用于计算大括号的 QML 结构。"""
    output: list[str] = []
    quote = ""
    escaped = False
    index = 0
    while index < len(line):
        char = line[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            output.append(" ")
            index += 1
            continue
        if char in ('"', "'"):
            quote = char
            output.append(" ")
            index += 1
            continue
        if char == "/" and index + 1 < len(line) and line[index + 1] == "/":
            break
        output.append(char)
        index += 1
    return "".join(output)


def _find_violations(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    violations: list[str] = []
    index = 0
    while index < len(lines):
        if not MESSAGE_BOX_RE.search(_strip_qml_line(lines[index])):
            index += 1
            continue

        start = index
        depth = 0
        began = False
        title_line = ""
        visual_children: list[str] = []
        cursor = index
        while cursor < len(lines):
            code = _strip_qml_line(lines[cursor])
            before = depth
            source_line = lines[cursor].strip()
            if began and before == 1:
                if source_line.startswith("title:"):
                    title_line = source_line
                match = OBJECT_RE.match(source_line)
                if match and match.group(1).split(".")[-1] not in NON_VISUAL_TYPES:
                    visual_children.append(f"{cursor + 1}:{source_line}")

            opens = code.count("{")
            closes = code.count("}")
            began = began or opens > 0
            depth += opens - closes
            if began and depth == 0:
                break
            cursor += 1

        if title_line and not EMPTY_TITLE_RE.fullmatch(title_line) and visual_children:
            display_path = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
            violations.append(
                f"{display_path}:{start + 1}: "
                f"{title_line}; child={visual_children[0]}"
            )
        index = cursor + 1
    return violations


def test_all_message_boxes_keep_titles_inside_form_layout() -> None:
    violations = [
        violation
        for path in sorted((ROOT / "app_qml" / "qml").rglob("*.qml"))
        for violation in _find_violations(path)
    ]
    assert not violations, "发现 MessageBox 标题与自定义子项同级: " + "; ".join(violations)


def test_contract_detects_builtin_title_next_to_visual_form(tmp_path: Path) -> None:
    unsafe = tmp_path / "UnsafeDialog.qml"
    unsafe.write_text(
        """Fluent.MessageBox {
    title: "会重叠"
    ColumnLayout { }
}
""",
        encoding="utf-8",
    )

    violations = _find_violations(unsafe)

    assert len(violations) == 1
    assert 'title: "会重叠"' in violations[0]
    assert "ColumnLayout" in violations[0]


def test_contract_allows_content_and_non_visual_children(tmp_path: Path) -> None:
    safe = tmp_path / "SafeDialog.qml"
    safe.write_text(
        """Fluent.MessageBox {
    title: "仅使用内建内容"
    content: "不会增加同级可视子项"
    ListModel { id: model }
    Connections { target: null }
}
""",
        encoding="utf-8",
    )

    assert _find_violations(safe) == []


def test_contract_rejects_conditional_title_with_empty_branch(tmp_path: Path) -> None:
    unsafe = tmp_path / "ConditionalTitleDialog.qml"
    unsafe.write_text(
        """Fluent.MessageBox {
    title: enabled ? "" : "仍会重叠"
    ColumnLayout { }
}
""",
        encoding="utf-8",
    )

    violations = _find_violations(unsafe)

    assert len(violations) == 1
    assert "仍会重叠" in violations[0]
