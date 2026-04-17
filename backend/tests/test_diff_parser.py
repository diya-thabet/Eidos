"""
Tests for the unified diff parser.

Covers: basic diff parsing, new/deleted/renamed files, multiple hunks,
line number tracking, symbol mapping, and edge cases.
"""

from app.reviews.diff_parser import map_lines_to_symbols, parse_unified_diff

SIMPLE_DIFF = """\
diff --git a/Services/UserService.cs b/Services/UserService.cs
index abc1234..def5678 100644
--- a/Services/UserService.cs
+++ b/Services/UserService.cs
@@ -10,7 +10,8 @@ public class UserService
     public User GetById(int id)
     {
-        if (id <= 0) throw new ArgumentException("Invalid id");
-        return _repo.Find(id);
+        if (id <= 0)
+            throw new ArgumentException("Invalid id", nameof(id));
+        var user = _repo.Find(id);
+        return user;
     }
"""

NEW_FILE_DIFF = """\
diff --git a/Models/Order.cs b/Models/Order.cs
new file mode 100644
--- /dev/null
+++ b/Models/Order.cs
@@ -0,0 +1,8 @@
+namespace MyApp.Models
+{
+    public class Order
+    {
+        public int Id { get; set; }
+        public decimal Total { get; set; }
+    }
+}
"""

DELETED_FILE_DIFF = """\
diff --git a/Legacy/OldService.cs b/Legacy/OldService.cs
deleted file mode 100644
--- a/Legacy/OldService.cs
+++ /dev/null
@@ -1,5 +0,0 @@
-namespace MyApp.Legacy
-{
-    public class OldService { }
-}
-
"""

MULTI_HUNK_DIFF = """\
diff --git a/Foo.cs b/Foo.cs
--- a/Foo.cs
+++ b/Foo.cs
@@ -5,3 +5,3 @@ class Foo
-    int x = 1;
+    int x = 2;
@@ -20,3 +20,4 @@ class Foo
     void Bar()
     {
+        Console.WriteLine("hello");
     }
"""

MULTI_FILE_DIFF = """\
diff --git a/A.cs b/A.cs
--- a/A.cs
+++ b/A.cs
@@ -1,3 +1,3 @@
-old line
+new line
diff --git a/B.cs b/B.cs
--- a/B.cs
+++ b/B.cs
@@ -1,3 +1,4 @@
 unchanged
+added
"""

RENAMED_DIFF = """\
diff --git a/OldName.cs b/NewName.cs
similarity index 90%
rename from OldName.cs
rename to NewName.cs
--- a/OldName.cs
+++ b/NewName.cs
@@ -1,3 +1,3 @@
-old content
+new content
"""


class TestParseDiff:
    def test_simple_diff(self):
        files = parse_unified_diff(SIMPLE_DIFF)
        assert len(files) == 1
        assert files[0].path == "Services/UserService.cs"

    def test_hunks_parsed(self):
        files = parse_unified_diff(SIMPLE_DIFF)
        assert len(files[0].hunks) == 1
        hunk = files[0].hunks[0]
        assert hunk.old_start == 10
        assert hunk.new_start == 10

    def test_added_lines(self):
        files = parse_unified_diff(SIMPLE_DIFF)
        added = files[0].added_lines
        assert len(added) == 4
        assert any("nameof" in ln.content for ln in added)

    def test_removed_lines(self):
        files = parse_unified_diff(SIMPLE_DIFF)
        removed = files[0].removed_lines
        assert len(removed) == 2

    def test_line_numbers(self):
        files = parse_unified_diff(SIMPLE_DIFF)
        added = files[0].added_lines
        # First added line should be at new line 12
        assert added[0].number == 12

    def test_new_file(self):
        files = parse_unified_diff(NEW_FILE_DIFF)
        assert len(files) == 1
        assert files[0].is_new is True
        assert files[0].path == "Models/Order.cs"
        assert len(files[0].added_lines) == 8

    def test_deleted_file(self):
        files = parse_unified_diff(DELETED_FILE_DIFF)
        assert len(files) == 1
        assert files[0].is_deleted is True
        assert len(files[0].removed_lines) == 5

    def test_multi_hunk(self):
        files = parse_unified_diff(MULTI_HUNK_DIFF)
        assert len(files) == 1
        assert len(files[0].hunks) == 2

    def test_multi_file(self):
        files = parse_unified_diff(MULTI_FILE_DIFF)
        assert len(files) == 2
        assert files[0].path == "A.cs"
        assert files[1].path == "B.cs"

    def test_renamed_file(self):
        files = parse_unified_diff(RENAMED_DIFF)
        assert len(files) == 1
        assert files[0].is_renamed is True
        assert files[0].old_path == "OldName.cs"
        assert files[0].path == "NewName.cs"

    def test_changed_line_numbers(self):
        files = parse_unified_diff(SIMPLE_DIFF)
        numbers = files[0].changed_line_numbers
        assert isinstance(numbers, set)
        assert len(numbers) == 4

    def test_empty_diff(self):
        files = parse_unified_diff("")
        assert files == []


class TestMapLinesToSymbols:
    def test_maps_changed_lines_to_symbol(self):
        files = parse_unified_diff(SIMPLE_DIFF)
        symbols = [
            {"fq_name": "MyApp.UserService", "kind": "class", "start_line": 1, "end_line": 30},
            {
                "fq_name": "MyApp.UserService.GetById",
                "kind": "method",
                "start_line": 10,
                "end_line": 16,
            },
        ]
        matched = map_lines_to_symbols(files[0], symbols)
        fq_names = {m["fq_name"] for m in matched}
        assert "MyApp.UserService.GetById" in fq_names

    def test_no_overlap_no_match(self):
        files = parse_unified_diff(SIMPLE_DIFF)
        symbols = [
            {"fq_name": "MyApp.Other", "kind": "class", "start_line": 100, "end_line": 200},
        ]
        matched = map_lines_to_symbols(files[0], symbols)
        assert matched == []

    def test_lines_changed_count(self):
        files = parse_unified_diff(SIMPLE_DIFF)
        symbols = [
            {
                "fq_name": "MyApp.UserService.GetById",
                "kind": "method",
                "start_line": 10,
                "end_line": 16,
            },
        ]
        matched = map_lines_to_symbols(files[0], symbols)
        assert matched[0]["lines_changed"] > 0

    def test_new_file_change_type(self):
        files = parse_unified_diff(NEW_FILE_DIFF)
        symbols = [
            {"fq_name": "MyApp.Models.Order", "kind": "class", "start_line": 3, "end_line": 7},
        ]
        matched = map_lines_to_symbols(files[0], symbols)
        assert matched[0]["change_type"] == "added"

    def test_deduplication(self):
        files = parse_unified_diff(SIMPLE_DIFF)
        # Same symbol listed twice
        symbols = [
            {
                "fq_name": "MyApp.UserService.GetById",
                "kind": "method",
                "start_line": 10,
                "end_line": 16,
            },
            {
                "fq_name": "MyApp.UserService.GetById",
                "kind": "method",
                "start_line": 10,
                "end_line": 16,
            },
        ]
        matched = map_lines_to_symbols(files[0], symbols)
        assert len(matched) == 1
