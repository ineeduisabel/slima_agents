"""Tests for shared language utilities."""

from __future__ import annotations

from slima_agents.lang import detect_language, flatten_paths, format_structure_tree


class TestDetectLanguage:
    def test_chinese(self):
        assert detect_language("建構一個台灣鬼怪世界") == "zh"

    def test_japanese_hiragana(self):
        assert detect_language("ファンタジーの世界を作ってください") == "ja"

    def test_japanese_katakana(self):
        assert detect_language("ファンタジー世界") == "ja"

    def test_korean(self):
        assert detect_language("판타지 세계를 만들어주세요") == "ko"

    def test_english(self):
        assert detect_language("Build a fantasy world") == "en"

    def test_mixed_cjk_no_kana_hangul(self):
        assert detect_language("三國演義") == "zh"

    def test_empty(self):
        assert detect_language("") == "en"

    def test_numbers_only(self):
        assert detect_language("12345") == "en"


class TestFlattenPaths:
    def test_simple_structure(self):
        nodes = [
            {"name": "meta", "kind": "folder", "children": [
                {"name": "overview.md", "kind": "file"},
            ]},
            {"name": "README.md", "kind": "file"},
        ]
        paths = flatten_paths(nodes)
        assert set(paths) == {"meta/overview.md", "README.md"}

    def test_nested_folders(self):
        nodes = [
            {"name": "worldview", "kind": "folder", "children": [
                {"name": "cosmology", "kind": "folder", "children": [
                    {"name": "creation.md", "kind": "file"},
                    {"name": "magic.md", "kind": "file"},
                ]},
                {"name": "overview.md", "kind": "file"},
            ]},
        ]
        paths = flatten_paths(nodes)
        assert set(paths) == {
            "worldview/cosmology/creation.md",
            "worldview/cosmology/magic.md",
            "worldview/overview.md",
        }

    def test_empty(self):
        assert flatten_paths([]) == []

    def test_deep_nesting(self):
        nodes = [
            {"name": "a", "kind": "folder", "children": [
                {"name": "b", "kind": "folder", "children": [
                    {"name": "c", "kind": "folder", "children": [
                        {"name": "deep.md", "kind": "file"},
                    ]},
                ]},
            ]},
        ]
        assert flatten_paths(nodes) == ["a/b/c/deep.md"]


class TestFormatStructureTree:
    def test_simple(self):
        nodes = [
            {"name": "README.md", "kind": "file", "position": 0},
        ]
        tree = format_structure_tree(nodes)
        assert "README.md" in tree
        assert "└──" in tree

    def test_folder_with_children(self):
        nodes = [
            {"name": "meta", "kind": "folder", "position": 0, "children": [
                {"name": "overview.md", "kind": "file", "position": 0},
            ]},
        ]
        tree = format_structure_tree(nodes)
        assert "meta/" in tree
        assert "overview.md" in tree

    def test_empty(self):
        assert format_structure_tree([]) == ""

    def test_folders_before_files(self):
        nodes = [
            {"name": "file.md", "kind": "file", "position": 0},
            {"name": "folder", "kind": "folder", "position": 1, "children": [
                {"name": "inner.md", "kind": "file", "position": 0},
            ]},
        ]
        tree = format_structure_tree(nodes)
        lines = tree.split("\n")
        # Folder should appear before file
        folder_idx = next(i for i, l in enumerate(lines) if "folder/" in l)
        file_idx = next(i for i, l in enumerate(lines) if "file.md" in l)
        assert folder_idx < file_idx
