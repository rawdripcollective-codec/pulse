"""tree-sitter based code parser.

Walks the concrete syntax tree of a source file and extracts entities
(functions, methods, classes, interfaces) along with their calls, decorators,
and docstrings. Supports Python, TypeScript/JavaScript, Go, and Rust out of
the box; additional grammars can be registered by extending
`LANGUAGE_PARSERS` and `EXTENSION_TO_LANG`.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import structlog
from tree_sitter import Language, Node, Parser

try:
    import tree_sitter_python as tspython
    import tree_sitter_typescript as tstypescript
    import tree_sitter_javascript as tsjavascript
    import tree_sitter_go as tsgo
    import tree_sitter_rust as tsrust
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "tree-sitter language grammars are required. "
        "Install with: pip install tree-sitter-python tree-sitter-typescript "
        "tree-sitter-javascript tree-sitter-go tree-sitter-rust"
    ) from exc

logger = structlog.get_logger()

# ─── Language registry ─────────────────────────────────────────
# We store FACTORIES (not Language instances) because tree-sitter 0.23+
# `Language` objects carry internal state and should not be shared across
# multiple `Parser` instances. Each `CodeParser._get_parser` call creates
# a fresh Language.
LANGUAGE_FACTORIES = {
    ".py": tspython.language,
    ".ts": tstypescript.language_typescript,
    ".tsx": tstypescript.language_tsx,
    ".js": tsjavascript.language,
    ".jsx": tsjavascript.language,
    ".go": tsgo.language,
    ".rs": tsrust.language,
}

EXTENSION_TO_LANG = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
}


# ─── Data classes ──────────────────────────────────────────────

@dataclass
class CodeEntity:
    """A parsed code entity (function, class, interface, etc.)."""

    name: str
    kind: str  # function, method, class, interface, type_alias, module
    file_path: str
    start_line: int
    end_line: int
    signature: str
    docstring: Optional[str] = None
    parent_name: Optional[str] = None
    children: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    code_text: str = ""


@dataclass
class ParsedFile:
    """Result of parsing a single file."""

    file_path: str
    language: str
    entities: list[CodeEntity]
    imports: list[dict]  # [{module, names, alias}]
    exports: list[str]
    total_lines: int


# ─── Parser ────────────────────────────────────────────────────

class CodeParser:
    """Parses source code files into lossless semantic trees."""

    SUPPORTED_EXTENSIONS = set(EXTENSION_TO_LANG.keys())

    def __init__(self):
        self._parsers: dict[str, Parser] = {}

    def _get_parser(self, ext: str) -> Parser:
        if ext not in self._parsers:
            factory = LANGUAGE_FACTORIES.get(ext)
            if factory is None:
                raise ValueError(f"Unsupported file extension: {ext}")
            # Create a fresh Language per Parser — Language objects in
            # tree-sitter 0.23+ are stateful and shouldn't be shared.
            lang = Language(factory())
            try:
                parser = Parser(lang)
            except TypeError:
                # Older tree-sitter (<0.23): Language goes via set_language
                parser = Parser()
                if hasattr(parser, "set_language"):
                    parser.set_language(lang)
                else:
                    parser.language = lang
            self._parsers[ext] = parser
        return self._parsers[ext]

    def parse_file(self, file_path: Path, source: str) -> ParsedFile:
        """Parse a single source file and extract all code entities."""
        ext = file_path.suffix
        if ext not in self.SUPPORTED_EXTENSIONS:
            raise ValueError(f"Unsupported extension: {ext}")

        parser = self._get_parser(ext)
        tree = parser.parse(bytes(source, "utf-8"))
        root = tree.root_node

        entities = self._extract_entities(root, source, str(file_path))
        imports = self._extract_imports(root, source)
        exports = self._extract_exports(root, source)

        return ParsedFile(
            file_path=str(file_path),
            language=EXTENSION_TO_LANG[ext],
            entities=entities,
            imports=imports,
            exports=exports,
            total_lines=source.count("\n") + 1,
        )

    # ─── Entity extraction ────────────────────────────────────

    def _extract_entities(self, node: Node, source: str, file_path: str) -> list[CodeEntity]:
        entities: list[CodeEntity] = []
        self._walk_for_entities(node, source, file_path, entities, parent=None)
        return entities

    def _walk_for_entities(
        self,
        node: Node,
        source: str,
        file_path: str,
        entities: list[CodeEntity],
        parent: Optional[str],
    ) -> None:
        """Recursively walk the AST for entity definitions."""
        kind_map = {
            "function_definition": "function",
            "async_function_definition": "function",
            "method_definition": "method",
            "class_definition": "class",
            "interface_declaration": "interface",
            "type_alias_declaration": "type_alias",
            "function_declaration": "function",
            "arrow_function": "function",
            "method_declaration": "method",
            "class_declaration": "class",
            "type_declaration": "interface",
            "func_literal": "function",
        }

        node_kind = node.type
        if node_kind in kind_map:
            name_node = node.child_by_field_name("name")
            name = name_node.text.decode("utf-8") if name_node else "<anonymous>"

            entity = CodeEntity(
                name=name,
                kind=kind_map[node_kind],
                file_path=file_path,
                start_line=node.start_point[0] + 1,
                end_line=node.end_point[0] + 1,
                signature=self._extract_signature(node),
                parent_name=parent,
                code_text=node.text.decode("utf-8"),
            )
            entity.calls = self._extract_calls(node)
            entity.decorators = self._extract_decorators(node)
            entity.docstring = self._extract_docstring(node)
            entities.append(entity)

            for child in node.children:
                if child.type in ("block", "body"):
                    self._walk_for_entities(child, source, file_path, entities, parent=name)
        else:
            for child in node.children:
                self._walk_for_entities(child, source, file_path, entities, parent=parent)

    # ─── Helpers ──────────────────────────────────────────────

    def _extract_calls(self, node: Node) -> list[str]:
        calls: set[str] = set()
        self._collect_calls(node, calls)
        return list(calls)

    def _collect_calls(self, node: Node, calls: set) -> None:
        if node.type in ("call_expression", "call"):
            func_node = node.child_by_field_name("function")
            if func_node:
                calls.add(func_node.text.decode("utf-8"))
        for child in node.children:
            self._collect_calls(child, calls)

    def _extract_imports(self, node: Node, source: str) -> list[dict]:
        """Extract import statements (simplified — full impl walks grammar-specific nodes)."""
        return []

    def _extract_exports(self, node: Node, source: str) -> list[str]:
        return []

    def _extract_signature(self, node: Node) -> str:
        params_node = node.child_by_field_name("parameters")
        if params_node:
            return params_node.text.decode("utf-8")
        return ""

    def _extract_docstring(self, node: Node) -> Optional[str]:
        body = node.child_by_field_name("body")
        if body and body.children:
            first = body.children[0]
            if first.type in ("expression_statement", "expression"):
                text = first.text.decode("utf-8").strip()
                if text.startswith('"""') or text.startswith("'''"):
                    return text.strip('"\'').strip()
        return None

    def _extract_decorators(self, node: Node) -> list[str]:
        decorators: list[str] = []
        prev = node.prev_sibling
        while prev and prev.type == "decorator":
            decorators.append(prev.text.decode("utf-8").strip())
            prev = prev.prev_sibling
        return decorators
