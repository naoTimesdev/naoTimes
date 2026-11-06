#!/usr/bin/env python3
"""Validate naoTimes translation catalogs and the keys referenced from code."""

from __future__ import annotations

import argparse
import ast
import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).absolute().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from naotimes.i18n import I18nDictionary, I18nError, load_i18n  # ruff: ignore[module-import-not-at-top-of-file]

SCAN_DIRECTORIES = ("cogs", "naotimes")
FALLBACK_LANGUAGE = "id"
SKIP_DIRECTORIES = frozenset({"__pycache__", ".venv", "venv"})
MAX_LISTED_ISSUES = 50


@dataclass
class Issue:
    """One problem found by the checker."""

    severity: str
    code: str
    message: str
    file: str | None = None
    line: int | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.file is not None:
            payload["file"] = self.file
        if self.line is not None:
            payload["line"] = self.line
        return payload


@dataclass
class Reference:
    """A translation key referenced from source code."""

    key: str
    file: str
    line: int
    source: str


class _ErrorLogCollector(logging.Handler):
    """Collect ERROR records emitted while loading the catalogs."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def _string_value(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _relative_path(path: Path) -> str:
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def _module_for_file(path: Path) -> str:
    try:
        relative = path.relative_to(REPO_ROOT)
    except ValueError:
        return "common"
    parts = relative.parts
    if parts and parts[0] == "cogs":
        if len(parts) >= 3:
            return parts[1]
        if len(parts) == 2:
            return path.stem
    return "common"


def _class_module_override(tree: ast.Module) -> str | None:
    """Return a ``module = "..."`` attribute set on a cog class, if any."""
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for statement in node.body:
            if isinstance(statement, ast.Assign):
                for target in statement.targets:
                    if isinstance(target, ast.Name) and target.id == "module":
                        value = _string_value(statement.value)
                        if value:
                            return value
            elif isinstance(statement, ast.AnnAssign):
                if not isinstance(statement.target, ast.Name) or statement.target.id != "module":
                    continue
                value = _string_value(statement.value) if statement.value is not None else None
                if value:
                    return value
    return None


def _bound_module(node: ast.Call) -> str | None:
    """Return the literal module passed to a preceding ``i18n_for(..., module)`` call."""
    if not isinstance(node.func, ast.Attribute):
        return None
    target = node.func.value
    if not isinstance(target, ast.Call):
        return None
    callee = target.func
    if isinstance(callee, ast.Attribute):
        name = callee.attr
    elif isinstance(callee, ast.Name):
        name = callee.id
    else:
        return None
    if name != "i18n_for":
        return None
    if len(target.args) >= 2:
        module = _string_value(target.args[1])
        if module:
            return module
    for keyword in target.keywords:
        if keyword.arg == "module":
            module = _string_value(keyword.value)
            if module:
                return module
    return None


def _relative_key(raw: str, owner_module: str, bound_module: str | None, known_modules: frozenset[str]) -> str:
    """Resolve a relative ``ctx.t()`` key against the owning module."""
    head, separator, _ = raw.partition(".")
    if separator and head in known_modules:
        return raw
    return f"{bound_module or owner_module}.{raw}"


def _t_reference(node: ast.Call, owner_module: str, known_modules: frozenset[str], file: str) -> Reference | None:
    if not node.args:
        return None
    raw = _string_value(node.args[0])
    if raw is None:
        return None
    if len(node.args) >= 2:
        second = _string_value(node.args[1])
        if second is not None and "." not in raw and raw in known_modules and "." in second:
            return Reference(f"{raw}.{second}", file, node.lineno, "t(module, key)")
    bound = _bound_module(node)
    return Reference(_relative_key(raw, owner_module, bound, known_modules), file, node.lineno, "t()")


def _locale_str_reference(node: ast.Call, file: str) -> Reference | None:
    for keyword in node.keywords:
        if keyword.arg != "key":
            continue
        key = _string_value(keyword.value)
        if key is not None:
            return Reference(key, file, node.lineno, "locale_str()")
    return None


def _helper_reference(node: ast.Call, helper: str, file: str, known_modules: frozenset[str]) -> Reference | None:
    """Resolve a local helper such as ``_t(ctx, "errors.owner_only")``."""
    if len(node.args) < 2:
        return None
    raw = _string_value(node.args[1])
    if raw is None:
        return None
    head, separator, _ = raw.partition(".")
    if helper == "_translate_interaction" and separator and head in known_modules:
        # This helper takes an already qualified key.
        return Reference(raw, file, node.lineno, f"{helper}()")
    return Reference(f"common.{raw}", file, node.lineno, f"{helper}()")


def _references_from_tree(
    tree: ast.Module, path: Path, owner_module: str, known_modules: frozenset[str]
) -> list[Reference]:
    file = _relative_path(path)
    references: list[Reference] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id in {"_t", "_translate_interaction"}:
            reference = _helper_reference(node, func.id, file, known_modules)
            if reference is not None:
                references.append(reference)
            continue
        if isinstance(func, ast.Attribute) and func.attr == "_t":
            reference = _helper_reference(node, "_t", file, known_modules)
            if reference is not None:
                references.append(reference)
            continue
        if isinstance(func, ast.Attribute):
            attribute = func.attr
            if attribute == "t":
                reference = _t_reference(node, owner_module, known_modules, file)
                if reference is not None:
                    references.append(reference)
            elif attribute == "resolve_key":
                raw = _string_value(node.args[0]) if node.args else None
                if raw is not None:
                    references.append(Reference(raw, file, node.lineno, "resolve_key()"))
            elif attribute == "resolve":
                if len(node.args) >= 2:
                    module = _string_value(node.args[0])
                    key = _string_value(node.args[1])
                    if module is not None and key is not None:
                        references.append(Reference(f"{module}.{key}", file, node.lineno, "resolve()"))
            elif attribute == "locale_str":
                reference = _locale_str_reference(node, file)
                if reference is not None:
                    references.append(reference)
        elif isinstance(func, ast.Name) and func.id == "locale_str":
            reference = _locale_str_reference(node, file)
            if reference is not None:
                references.append(reference)
    return references


def _validate_reference(reference: Reference, default_module: Any, known_modules: frozenset[str]) -> Issue | None:
    module, separator, key = reference.key.partition(".")
    if not separator or not module or not key:
        return Issue(
            "error",
            "invalid-key",
            f"{reference.key!r} is not a dotted 'module.key' reference used by {reference.source}",
            reference.file,
            reference.line,
        )
    if module not in known_modules:
        return Issue(
            "error",
            "unknown-module",
            f"unknown i18n module {module!r} referenced by {reference.source}",
            reference.file,
            reference.line,
        )
    internal = default_module.get_optional(module)
    if internal is None or key not in internal.strings:
        return Issue(
            "error",
            "unknown-key",
            f"unknown translation key {reference.key!r} referenced by {reference.source}",
            reference.file,
            reference.line,
        )
    return None


def _check_layout(dictionary: I18nDictionary, loader_errors: list[str]) -> list[Issue]:
    issues = [Issue("error", "layout", message) for message in loader_errors]
    i18n_root = REPO_ROOT / "i18n"
    if not i18n_root.is_dir():
        issues.append(Issue("error", "layout", f"i18n directory not found at {i18n_root}"))
        return issues
    loaded = set(dictionary.languages)
    try:
        entries = sorted(path for path in i18n_root.iterdir() if path.is_dir() and not path.name.startswith("."))
    except OSError as exc:
        issues.append(Issue("error", "layout", f"could not list {i18n_root}: {exc}"))
        return issues
    for path in entries:
        language = path.name.lower()
        if language not in loaded:
            issues.append(Issue("error", "layout", f"language directory {path.name!r} produced no valid translations"))
    return issues


def _check_parity(dictionary: I18nDictionary) -> tuple[dict[str, Any], list[Issue]]:
    default_language = dictionary.default_language
    default_module = dictionary.getdefault()
    report: dict[str, Any] = {}
    issues: list[Issue] = []
    for language in dictionary.languages:
        module = dictionary.get(language)
        entry: dict[str, Any] = {
            "missing_modules": {},
            "extra_modules": [],
            "missing_keys": {},
            "extra_keys": {},
            "placeholder_mismatches": [],
        }
        if module is not None and language != default_language:
            for module_name, internal in sorted(default_module.modules.items()):
                translated = module.get_optional(module_name)
                if translated is None:
                    entry["missing_modules"][module_name] = sorted(internal.strings)
                    issues.append(
                        Issue(
                            "warning",
                            "missing-module",
                            f"module {module_name!r} from {default_language!r} is missing in {language!r} "
                            f"({len(internal.strings)} key(s))",
                        )
                    )
                    continue
                for key in sorted(internal.strings.keys() - translated.strings.keys()):
                    entry["missing_keys"].setdefault(module_name, []).append(key)
                    issues.append(Issue("warning", "missing-key", f"{module_name}.{key} is missing in {language!r}"))
                for key in sorted(translated.strings.keys() - internal.strings.keys()):
                    entry["extra_keys"].setdefault(module_name, []).append(key)
                    issues.append(
                        Issue(
                            "error",
                            "extra-key",
                            f"{module_name}.{key} exists in {language!r} but not in {default_language!r}",
                        )
                    )
                for key in sorted(internal.strings.keys() & translated.strings.keys()):
                    expected = internal.strings[key].placeholders
                    actual = translated.strings[key].placeholders
                    if expected == actual:
                        continue
                    entry["placeholder_mismatches"].append({
                        "key": f"{module_name}.{key}",
                        "language": language,
                        "expected": sorted(expected),
                        "actual": sorted(actual),
                    })
                    issues.append(
                        Issue(
                            "error",
                            "placeholder-mismatch",
                            f"{module_name}.{key} in {language!r} uses placeholders {sorted(actual)} "
                            f"but {default_language!r} uses {sorted(expected)}",
                        )
                    )
            for module_name in sorted(module.modules.keys() - default_module.modules.keys()):
                entry["extra_modules"].append(module_name)
                issues.append(
                    Issue(
                        "error",
                        "extra-module",
                        f"module {module_name!r} exists in {language!r} but not in {default_language!r}",
                    )
                )
        report[language] = entry
    return report, issues


def _scan_references(dictionary: I18nDictionary) -> tuple[list[Issue], set[str], int, int]:
    known_modules = dictionary.known_modules
    default_module = dictionary.getdefault()
    issues: list[Issue] = []
    used: set[str] = set()
    files_scanned = 0
    reference_count = 0
    for directory in SCAN_DIRECTORIES:
        base = REPO_ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if any(part in SKIP_DIRECTORIES for part in path.parts):
                continue
            files_scanned += 1
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except (OSError, SyntaxError, UnicodeDecodeError) as exc:
                issues.append(Issue("error", "parse-error", f"could not parse file: {exc}", _relative_path(path)))
                continue
            owner_module = _class_module_override(tree) or _module_for_file(path)
            for reference in _references_from_tree(tree, path, owner_module, known_modules):
                reference_count += 1
                used.add(reference.key)
                problem = _validate_reference(reference, default_module, known_modules)
                if problem is not None:
                    issues.append(problem)
    return issues, used, files_scanned, reference_count


def _unused_keys(dictionary: I18nDictionary, used: set[str]) -> list[Issue]:
    issues: list[Issue] = []
    for module_name, internal in sorted(dictionary.getdefault().modules.items()):
        for key in sorted(internal.strings):
            canonical = f"{module_name}.{key}"
            if canonical not in used:
                issues.append(Issue("warning", "unused-key", f"{canonical} is defined but never referenced"))
    return issues


def _load_catalog(default_language: str) -> tuple[I18nDictionary, list[str]]:
    logger = logging.getLogger("naotimes.i18n")
    collector = _ErrorLogCollector()
    previous_level = logger.level
    previous_propagate = logger.propagate
    logger.addHandler(collector)
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    try:
        dictionary = load_i18n(default_language=default_language)
    finally:
        logger.removeHandler(collector)
        logger.setLevel(previous_level)
        logger.propagate = previous_propagate
    return dictionary, collector.messages


def _parity_summary(entry: dict[str, Any]) -> str:
    missing_modules = len(entry["missing_modules"])
    missing_keys = sum(len(keys) for keys in entry["missing_modules"].values())
    missing_keys += sum(len(keys) for keys in entry["missing_keys"].values())
    extra_modules = len(entry["extra_modules"])
    extra_keys = sum(len(keys) for keys in entry["extra_keys"].values())
    mismatches = len(entry["placeholder_mismatches"])
    parts: list[str] = []
    if missing_modules:
        parts.append(f"{missing_modules} missing module(s)")
    if missing_keys:
        parts.append(f"{missing_keys} missing key(s)")
    if extra_modules:
        parts.append(f"{extra_modules} extra module(s)")
    if extra_keys:
        parts.append(f"{extra_keys} extra key(s)")
    if mismatches:
        parts.append(f"{mismatches} placeholder mismatch(es)")
    return "ok" if not parts else ", ".join(parts)


def _format_issue(issue: dict[str, Any]) -> str:
    location = ""
    if issue.get("file"):
        if issue.get("line"):
            location = f"{issue['file']}:{issue['line']}: "
        else:
            location = f"{issue['file']}: "
    return f"[{issue['code']}] {location}{issue['message']}"


def _print_report(report: dict[str, Any], *, strict: bool) -> None:
    summary = report["summary"]
    print("i18n check")
    print(f"  default language: {summary['default_language']}")
    print(f"  languages: {', '.join(summary['languages']) or '(none)'}")
    print(f"  modules: {', '.join(summary['modules']) or '(none)'}")
    print(f"  keys in default: {summary['keys']}")
    print()
    print(f"Key parity against {summary['default_language']!r}:")
    for language, entry in report["parity"].items():
        print(f"  {language}: {_parity_summary(entry)}")
    print()
    print("Code references:")
    print(f"  files scanned: {summary['files_scanned']}")
    print(f"  references: {summary['references']}")
    print(f"  unknown references: {summary['unknown_references']}")
    print(f"  defined-but-unused keys: {summary['unused_keys']}")
    for title, items in (("Errors", report["errors"]), ("Warnings", report["warnings"])):
        print()
        print(f"{title} ({len(items)}):")
        if not items:
            print("  none")
            continue
        for issue in items[:MAX_LISTED_ISSUES]:
            print(f"  {_format_issue(issue)}")
        remaining = len(items) - MAX_LISTED_ISSUES
        if remaining > 0:
            print(f"  ... and {remaining} more (use --json for the full list)")
    print()
    result = "FAILED" if summary["errors"] else "OK"
    print(f"Result: {result} ({summary['errors']} error(s), {summary['warnings']} warning(s))")
    if summary["errors"] and not strict:
        print("Errors do not fail the check without --strict.")


def _report_fatal(args: argparse.Namespace, default_language: str, exc: Exception) -> int:
    message = f"could not load the {default_language!r} catalog: {exc}"
    if args.json:
        report = {
            "summary": {
                "default_language": default_language,
                "languages": [],
                "modules": [],
                "keys": 0,
                "files_scanned": 0,
                "references": 0,
                "unknown_references": 0,
                "unused_keys": 0,
                "errors": 1,
                "warnings": 0,
            },
            "parity": {},
            "errors": [{"code": "load-failed", "message": message}],
            "warnings": [],
        }
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        print(f"i18n check: FAILED - {message}", file=sys.stderr)
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the naoTimes i18n catalogs (layout, per-language key parity and placeholders) "
            "and report translation keys referenced from code that do not exist."
        ),
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit with status 1 when any error is found (warnings never fail the check)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print a machine-readable JSON report instead of the human-readable summary",
    )
    parser.add_argument(
        "--default-language",
        metavar="CODE",
        default=None,
        help="source/default language to validate against (default: $I18N_DEFAULT or 'id')",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    default_language = args.default_language or os.environ.get("I18N_DEFAULT", FALLBACK_LANGUAGE)

    try:
        dictionary, loader_errors = _load_catalog(default_language)
    except (I18nError, ValueError) as exc:
        return _report_fatal(args, default_language, exc)

    layout_issues = _check_layout(dictionary, loader_errors)
    parity_report, parity_issues = _check_parity(dictionary)
    reference_issues, used_keys, files_scanned, reference_count = _scan_references(dictionary)
    unused_issues = _unused_keys(dictionary, used_keys)

    issues = [*layout_issues, *parity_issues, *reference_issues, *unused_issues]
    errors = [issue for issue in issues if issue.severity == "error"]
    warnings = [issue for issue in issues if issue.severity == "warning"]

    default_module = dictionary.getdefault()
    summary = {
        "default_language": dictionary.default_language,
        "languages": list(dictionary.languages),
        "modules": sorted(default_module.modules),
        "keys": sum(len(internal.strings) for internal in default_module.modules.values()),
        "files_scanned": files_scanned,
        "references": reference_count,
        "unknown_references": sum(
            1 for issue in reference_issues if issue.code in {"unknown-key", "unknown-module", "invalid-key"}
        ),
        "unused_keys": len(unused_issues),
        "errors": len(errors),
        "warnings": len(warnings),
    }
    report = {
        "summary": summary,
        "parity": parity_report,
        "errors": [issue.as_dict() for issue in errors],
        "warnings": [issue.as_dict() for issue in warnings],
    }

    if args.json:
        json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        _print_report(report, strict=args.strict)

    if args.strict and errors:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
