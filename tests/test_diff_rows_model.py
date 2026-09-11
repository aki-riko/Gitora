# coding: utf-8
"""diff_rows 结构化行模型单元测试(纯 Python,无 Qt)。"""
import json
import unittest

from app.common.diff_rows import parse_diff_rows, rows_to_json


SAMPLE_DIFF = """diff --git a/app/demo.py b/app/demo.py
index 1111111..2222222 100644
--- a/app/demo.py
+++ b/app/demo.py
@@ -1,7 +1,8 @@
 import os
-# old comment
+# new comment with detail
 def main(name):
-    print(name)
+    print(f'hello {name}')
+    return os.path.exists(name)
@@ -20,3 +21,4 @@
 def tail():
-    pass
+    pass  # keep
\\ No newline at end of file
diff --git a/readme.md b/readme.md
--- a/readme.md
+++ b/readme.md
@@ -1 +1 @@
-hello world
+hello brave world
"""


class ParseDiffRowsTest(unittest.TestCase):
    def setUp(self):
        self.payload = parse_diff_rows(SAMPLE_DIFF)

    def test_files_match_parse_unified_diff_semantics(self):
        files = self.payload["files"]
        self.assertEqual([f["path"] for f in files], ["app/demo.py", "readme.md"])
        self.assertEqual(files[0]["additions"], 4)
        self.assertEqual(files[0]["deletions"], 3)

    def test_row_types_and_numbering(self):
        rows = self.payload["rows"]
        kinds = [r["t"] for r in rows]
        self.assertIn("file", kinds)
        self.assertIn("hunk", kinds)
        # 文件头/元信息行不参与编号
        self.assertEqual(rows[0]["t"], "file")
        self.assertEqual(rows[0]["o"], -1)
        # --- / +++ 必须识别为元信息而非内容行
        meta_x = [r["x"] for r in rows if r["t"] == "meta"]
        self.assertIn("--- a/app/demo.py", meta_x)
        self.assertIn("+++ b/app/demo.py", meta_x)
        # 首个 hunk 上下文行双行号
        ctx = next(r for r in rows if r["t"] == "ctx")
        self.assertEqual((ctx["o"], ctx["n"]), (1, 1))
        # 第二个 hunk 行号按块头重置(@@ -20,3 +21,4 @@ 首行即 20/21)
        tail_ctx = [r for r in rows if r["t"] == "ctx"][-1]
        self.assertEqual((tail_ctx["o"], tail_ctx["n"]), (20, 21))
        # \\ No newline 元信息行
        self.assertTrue(any(r["x"].startswith("\\ No newline") for r in rows))

    def test_word_level_bg_on_changed_pair(self):
        rows = self.payload["rows"]
        old = next(r for r in rows if r["t"] == "del" and r["x"] == "# old comment")
        new = next(r for r in rows if r["t"] == "add" and r["x"] == "# new comment with detail")
        old_bg = [s for s in old["seg"] if s[3] == "d"]
        new_bg = [s for s in new["seg"] if s[3] == "a"]
        self.assertTrue(old_bg, "删除行应有词级删除底色")
        self.assertTrue(new_bg, "新增行应有词级新增底色")
        # 纯插入行:旧行没有删除底色
        pure_old = next(r for r in rows if r["t"] == "del" and r["x"] == "hello world")
        self.assertFalse([s for s in pure_old.get("seg", []) if s[3] == "d"])
        pure_new = next(r for r in rows if r["t"] == "add" and r["x"] == "hello brave world")
        self.assertTrue([s for s in pure_new.get("seg", []) if s[3] == "a"])

    def test_python_syntax_fg(self):
        rows = self.payload["rows"]
        ctx = next(r for r in rows if r["x"] == "import os")
        self.assertTrue(any(s[2] == "k" for s in ctx["seg"]), "import 应着关键字色")
        comment = next(r for r in rows if r["t"] == "add" and r["x"].startswith("# new"))
        self.assertTrue(any(s[2] == "c" for s in comment["seg"]), "注释应着注释色")
        ret = next(r for r in rows if r["x"] == "    return os.path.exists(name)")
        self.assertTrue(any(s[2] == "k" for s in ret["seg"]), "return 应着关键字色")

    def test_segments_are_sorted_merged_nonoverlapping(self):
        for row in self.payload["rows"]:
            seg = row.get("seg")
            if not seg:
                continue
            for prev, cur in zip(seg, seg[1:]):
                self.assertEqual(prev[1], cur[0], row["x"])

    def test_json_round_trip(self):
        payload = rows_to_json(self.payload)
        decoded = json.loads(payload)
        self.assertEqual(len(decoded["rows"]), len(self.payload["rows"]))
        self.assertEqual(len(decoded["files"]), len(self.payload["files"]))


class TokenizerStateTest(unittest.TestCase):
    def _fg_kinds(self, lines, path):
        raw_lines = ["diff --git a/%s b/%s" % (path, path),
                     "--- a/%s" % path, "+++ b/%s" % path,
                     "@@ -1,%d +1,%d @@" % (len(lines), len(lines))]
        raw_lines += [" " + ln if ln else " " for ln in lines]
        payload = parse_diff_rows("\n".join(raw_lines) + "\n")
        return [r for r in payload["rows"] if r["t"] == "ctx"]

    def test_clike_block_comment_spans_lines(self):
        rows = self._fg_kinds(
            ["int main() {", "/* start", "still comment", "end */ int x;"], "a.c")
        self.assertTrue(all(any(s[2] == "c" for s in r["seg"]) for r in rows[1:3]))
        # 块注释闭合后恢复着色
        self.assertTrue(any(s[2] == "k" for s in rows[3]["seg"]))

    def test_python_triple_string_spans_lines(self):
        rows = self._fg_kinds(
            ["x = 1", 's = """start', "middle line", 'end"""'], "a.py")
        self.assertTrue(any(s[2] == "s" for s in rows[1]["seg"]))
        self.assertTrue(all(any(s[2] == "s" for s in r["seg"]) for r in rows[2:4]))

    def test_json_keywords(self):
        rows = self._fg_kinds(['{"a": true, "b": null}'], "a.json")
        self.assertTrue(any(s[2] == "k" for s in rows[0]["seg"]))
        self.assertTrue(any(s[2] == "s" for s in rows[0]["seg"]))

    def test_shell_comment_and_keyword(self):
        rows = self._fg_kinds(["#!/bin/bash", "export PATH=1"], "a.sh")
        self.assertTrue(any(s[2] == "c" for s in rows[0]["seg"]))
        self.assertTrue(any(s[2] == "k" for s in rows[1]["seg"]))


class EdgeCaseTest(unittest.TestCase):
    def test_empty_diff(self):
        payload = parse_diff_rows("")
        self.assertEqual(payload, {"files": [], "rows": []})

    def test_binary_file_marker(self):
        raw = ("diff --git a/blob.bin b/blob.bin\n"
               "Binary files a/blob.bin and b/blob.bin differ\n")
        payload = parse_diff_rows(raw)
        self.assertEqual(len(payload["files"]), 1)
        self.assertTrue(all(r["t"] in ("file", "meta") for r in payload["rows"]))

    def test_truncation_banner_passthrough(self):
        raw = ("diff --git a/x.txt b/x.txt\n"
               "index 1111111..2222222 100644\n"
               "--- a/x.txt\n"
               "+++ b/x.txt\n"
               "@@ -1 +1 @@\n"
               "-a\n"
               "+b\n"
               "\n"
               "==================================================\n"
               "⚠️ Diff过大，已截断（完整大小: 120.0KB）\n")
        payload = parse_diff_rows(raw)
        kinds = {r["t"] for r in payload["rows"]}
        self.assertIn("meta", kinds)
        self.assertFalse(any(r["t"] == "add" and "截断" in r["x"] for r in payload["rows"]))

    def test_interleaved_pairing_keeps_leftovers(self):
        raw = ("diff --git a/x.txt b/x.txt\n"
               "--- a/x.txt\n"
               "+++ b/x.txt\n"
               "@@ -1,3 +1,2 @@\n"
               "-one\n"
               "-two\n"
               "+ONE\n")
        payload = parse_diff_rows(raw)
        dels = [r for r in payload["rows"] if r["t"] == "del"]
        self.assertEqual(len(dels), 2)
        # 未配对的删除行保留(分栏视图左半仍有内容),无词级底色
        self.assertTrue(dels[1].get("seg") is None or
                        not [s for s in dels[1]["seg"] if s[3] == "d"])


if __name__ == "__main__":
    unittest.main()
