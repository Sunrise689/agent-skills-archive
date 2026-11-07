"""Evaluate report quality rules from a JSON file using a restricted expression context."""

import argparse
import ast
import json
import re
import sys
from pathlib import Path


_DEFAULT_RULES_PATH = (
    Path.home()
    / "Desktop"
    / "hd"
    / "basic-memory"
    / "记忆库"
    / "user"
    / "dispatch-repair-20261010"
    / "reports"
    / "content_gate_rules.json"
)
_SAFE_BUILTINS = {"len": len, "any": any, "max": max, "set": set}
_ALLOWED_NODES = {
    ast.Expression,
    ast.BoolOp,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.Call,
    ast.Name,
    ast.Attribute,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.SetComp,
    ast.ListComp,
    ast.GeneratorExp,
    ast.comprehension,
    ast.Load,
    ast.Store,
    ast.And,
    ast.Or,
    ast.Not,
    ast.Invert,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Mod,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.In,
    ast.NotIn,
    ast.IfExp,
    ast.keyword,
}
_EXPRESSION_NAMES = {"text", "paragraphs", "sentences", "url_paragraph_ratio", "re"}
_COMPREHENSION_NAMES = {"h", "x", "s"}


def load_rules(path: str) -> list[dict]:
    """Load the rule list from a UTF-8 JSON file."""
    with Path(path).open("r", encoding="utf-8") as rules_file:
        payload = json.load(rules_file)
    rules = payload.get("rules") if isinstance(payload, dict) else payload
    if not isinstance(rules, list) or any(not isinstance(rule, dict) for rule in rules):
        raise ValueError("rules JSON must contain a list of rule objects")
    return rules


def _validate_expression(tree: ast.AST) -> None:
    """Reject syntax outside the small expression language used by the rule file."""
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    if not names <= (_EXPRESSION_NAMES | set(_SAFE_BUILTINS) | _COMPREHENSION_NAMES):
        raise ValueError("expression uses an unavailable name")

    for node in ast.walk(tree):
        if type(node) not in _ALLOWED_NODES:
            raise ValueError(f"expression syntax is not allowed: {type(node).__name__}")
        if isinstance(node, ast.Attribute) and not (
            isinstance(node.value, ast.Name)
            and node.value.id == "text"
            and node.attr in {"count", "lower"}
        ):
            raise ValueError("only text.count and text.lower are allowed")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in _SAFE_BUILTINS:
                    raise ValueError("function is not allowed")
            elif isinstance(node.func, ast.Attribute):
                if not (
                    isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "text"
                    and node.func.attr in {"count", "lower"}
                ):
                    raise ValueError("method call is not allowed")
            else:
                raise ValueError("call target is not allowed")
        if isinstance(node, ast.keyword) and node.arg != "default":
            raise ValueError("keyword argument is not allowed")


def _evaluate_rule(expr: str, context: dict) -> bool:
    tree = ast.parse(expr, mode="eval")
    _validate_expression(tree)
    code = compile(tree, "<content-gate-rule>", "eval")
    safe_globals = {"__builtins__": _SAFE_BUILTINS, **context}
    return bool(eval(code, safe_globals))


def evaluate(
    text: str,
    rules: list[dict] | None = None,
    rules_path: str | None = None,
) -> dict:
    """Evaluate content rules; a faulty rule is reported and treated as non-matching."""
    active_rules = rules if rules is not None else load_rules(str(rules_path or _DEFAULT_RULES_PATH))
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text.strip()) if part.strip()]
    sentences = [part.strip() for part in re.split(r"[。.!?！？\r\n]+", text) if part.strip()]
    url_paragraphs = sum(bool(re.search(r"(?:https?://|www\.)\S+", part, re.IGNORECASE)) for part in paragraphs)
    url_paragraph_ratio = url_paragraphs / len(paragraphs) if paragraphs else 1.0
    context = {
        "text": text,
        "paragraphs": paragraphs,
        "sentences": sentences,
        "url_paragraph_ratio": url_paragraph_ratio,
        "re": re,
    }

    blocked_by = []
    warned_by = []
    errors = []
    for index, rule in enumerate(active_rules):
        name = str(rule.get("name", f"rule-{index + 1}"))
        severity = rule.get("severity")
        expr = rule.get("expr")
        if severity not in {"block", "warn"} or not isinstance(expr, str):
            errors.append({"name": name, "error": "invalid rule: expected expr and block/warn severity"})
            continue
        try:
            matched = _evaluate_rule(expr, context)
        except Exception as error:
            errors.append({"name": name, "error": f"{type(error).__name__}: {error}"})
            continue
        if matched:
            (blocked_by if severity == "block" else warned_by).append(name)

    return {
        "ok": not blocked_by,
        "score": len(warned_by),
        "blocked_by": blocked_by,
        "warned_by": warned_by,
        "stats": {
            "chars": len(text),
            "paragraphs": len(paragraphs),
            "url_paragraph_ratio": url_paragraph_ratio,
        },
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check a Markdown report with content quality rules.")
    parser.add_argument("report", help="report file path")
    parser.add_argument("--rules", help="rules JSON path")
    args = parser.parse_args(argv)
    try:
        report_text = Path(args.report).read_text(encoding="utf-8")
        result = evaluate(report_text, rules_path=args.rules)
    except Exception as error:
        print(f"ERROR: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    print(f"ok: {result['ok']}")
    print(f"score: {result['score']}")
    print(f"blocked_by: {result['blocked_by']}")
    print(f"warned_by: {result['warned_by']}")
    print(f"stats: {result['stats']}")
    if result["errors"]:
        print(f"errors: {result['errors']}")
    return 2 if not result["ok"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
