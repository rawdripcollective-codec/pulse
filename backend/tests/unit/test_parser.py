"""Unit tests for the tree-sitter code parser."""

from pathlib import Path

import pytest

from app.engine.parser import CodeParser


class TestCodeParser:
    def setup_method(self):
        self.parser = CodeParser()

    def test_parses_python_module(self, sample_python_source: str):
        result = self.parser.parse_file(Path("sample.py"), sample_python_source)
        assert result.language == "python"
        names = {e.name for e in result.entities}
        # Module-level function and class with methods
        assert "Widget" in names
        assert "make_widget" in names
        assert "helper" in names
        # Methods
        assert "__init__" in names
        assert "render" in names

    def test_extracts_calls(self, sample_python_source: str):
        result = self.parser.parse_file(Path("sample.py"), sample_python_source)
        helper = next(e for e in result.entities if e.name == "helper")
        # helper() calls make_widget() and .render()
        assert "make_widget" in helper.calls

    def test_extracts_docstrings(self, sample_python_source: str):
        result = self.parser.parse_file(Path("sample.py"), sample_python_source)
        # Class docstrings are extracted on the class entity
        widget_cls = next(e for e in result.entities if e.name == "Widget")
        assert widget_cls.docstring is not None
        assert "widget" in widget_cls.docstring.lower()

    def test_class_methods_have_parent(self, sample_python_source: str):
        result = self.parser.parse_file(Path("sample.py"), sample_python_source)
        methods = [e for e in result.entities if e.kind == "method"]
        for m in methods:
            assert m.parent_name == "Widget"

    def test_unsupported_extension_raises(self):
        with pytest.raises(ValueError, match="Unsupported"):
            self.parser.parse_file(Path("foo.xyz"), "x = 1")

    def test_parsers_are_cached(self, sample_python_source: str):
        # Two parses should reuse the same Parser instance
        r1 = self.parser.parse_file(Path("a.py"), sample_python_source)
        r2 = self.parser.parse_file(Path("b.py"), sample_python_source)
        assert r1.language == r2.language
        # Internal cache should have a single parser for .py
        assert ".py" in self.parser._parsers

    def test_line_numbers_are_one_indexed(self, sample_python_source: str):
        result = self.parser.parse_file(Path("sample.py"), sample_python_source)
        # All start_line values should be >= 1
        assert all(e.start_line >= 1 for e in result.entities)

    def test_code_text_preserved(self, sample_python_source: str):
        result = self.parser.parse_file(Path("sample.py"), sample_python_source)
        widget = next(e for e in result.entities if e.name == "Widget")
        assert "class Widget" in widget.code_text
        assert widget.end_line > widget.start_line


class TestParserMultipleLanguages:
    def test_javascript_parses(self):
        js = """
        function greet(name) {
            return `Hello, ${name}!`;
        }

        class User {
            constructor(name) {
                this.name = name;
            }
        }
        """
        parser = CodeParser()
        result = parser.parse_file(Path("app.js"), js)
        assert result.language == "javascript"
        names = {e.name for e in result.entities}
        assert "greet" in names
        assert "User" in names

    def test_typescript_parses(self):
        ts = """
        interface User {
            id: number;
            name: string;
        }

        function findUser(id: number): User | null {
            return null;
        }
        """
        parser = CodeParser()
        result = parser.parse_file(Path("app.ts"), ts)
        assert result.language == "typescript"
        names = {e.name for e in result.entities}
        assert "User" in names
        assert "findUser" in names
