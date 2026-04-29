"""
Cyclomatic and cognitive complexity from tree-sitter AST nodes.

Works for ALL 9 supported languages. The calculator walks the AST subtree
of a function/method node and counts decision points.

Cyclomatic complexity (McCabe):
    CC = 1 + number_of_decision_points

Cognitive complexity (Sonar-style):
    Increments for each control flow break.
    Extra increment for each nesting level.
    Extra increment for recursion.
"""

from __future__ import annotations

from tree_sitter import Node

# -----------------------------------------------------------------------
# Node types that count as decision points, by category
# -----------------------------------------------------------------------

# Branching: each adds +1 to cyclomatic complexity
_BRANCH_TYPES: frozenset[str] = frozenset({
    # Conditionals
    "if_statement",
    "if_expression",
    "elif_clause",              # Python
    "else_if_clause",           # Rust
    "elif",                     # alias
    "conditional_expression",   # ternary (C, Java, TS, C#, C++)
    "ternary_expression",       # some grammars
    # Loops
    "for_statement",
    "for_in_statement",
    "enhanced_for_statement",   # Java for-each
    "for_range_loop",           # Rust
    "while_statement",
    "do_statement",             # do-while
    "loop_expression",          # Rust loop {}
    # Exception handling
    "catch_clause",
    "except_clause",            # Python
    "rescue",                   # Ruby (future)
    # Pattern matching / switch
    "switch_case",
    "case_clause",
    "switch_expression_arm",    # C#
    "match_arm",                # Rust
    "type_switch_case",         # Go
    "expression_case",          # Go
    "default_case",             # Go
    "communication_case",       # Go select
    "switch_block_statement_group",  # Java
    "switch_label",             # Java (case: / default:)
    # Go-specific
    "select_statement",
    # Short-circuit boolean operators (counted in _count_boolean_ops)
})

# Types that increase nesting depth (for cognitive complexity)
_NESTING_TYPES: frozenset[str] = frozenset({
    "if_statement",
    "for_statement",
    "for_in_statement",
    "enhanced_for_statement",
    "for_range_loop",
    "while_statement",
    "do_statement",
    "loop_expression",
    "switch_statement",
    "switch_expression",
    "match_expression",
    "try_statement",
    "try_expression",
    "select_statement",
    "lambda",
    "lambda_expression",
    "arrow_function",
    "closure_expression",       # Rust
})

# Boolean operators that add to cyclomatic complexity
_BOOLEAN_OPS: frozenset[str] = frozenset({"&&", "||", "and", "or"})


def cyclomatic_complexity(node: Node) -> int:
    """
    Compute McCabe cyclomatic complexity for a function AST node.

    CC = 1 + (branches) + (boolean operators)

    Args:
        node: tree-sitter Node for a function/method body.

    Returns:
        Integer complexity score. Minimum is 1 (straight-line code).
    """
    count = 1  # base complexity
    count += _count_branches(node)
    count += _count_boolean_ops(node)
    return count


def cognitive_complexity(node: Node, func_name: str = "") -> int:
    """
    Compute cognitive complexity (Sonar-style) for a function AST node.

    Rules:
    - +1 for each control flow break (if, for, while, catch, etc.)
    - +1 extra for each level of nesting
    - +1 for each sequence of same boolean operator that changes
    - +1 for recursion (calling own name)

    Args:
        node: tree-sitter Node for a function/method.
        func_name: the function name (for recursion detection).

    Returns:
        Integer cognitive complexity score. Minimum is 0.
    """
    total = _cognitive_walk(node, depth=0, func_name=func_name)
    return total


# -----------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------


def _count_branches(node: Node) -> int:
    """Count all branching nodes in the subtree."""
    count = 0
    if node.type in _BRANCH_TYPES:
        count += 1
    for child in node.children:
        count += _count_branches(child)
    return count


def _count_boolean_ops(node: Node) -> int:
    """Count && and || operators in binary expressions."""
    count = 0
    if node.type in ("binary_expression", "boolean_operator"):
        for child in node.children:
            if not child.is_named and child.type in _BOOLEAN_OPS:
                count += 1
    for child in node.children:
        count += _count_boolean_ops(child)
    return count


def _cognitive_walk(node: Node, depth: int, func_name: str) -> int:
    """Recursive walk computing cognitive complexity with nesting."""
    total = 0

    # Structural increment: +1 for control flow, +depth for nesting
    if node.type in _BRANCH_TYPES:
        total += 1 + depth

    # Check for else/elif (fundamental increment only, no nesting)
    if node.type in ("else_clause", "else"):
        total += 1

    # Boolean operator sequences
    if node.type in ("binary_expression", "boolean_operator"):
        for child in node.children:
            if not child.is_named and child.type in _BOOLEAN_OPS:
                total += 1

    # Recursion detection
    if (
        func_name
        and node.type in ("call_expression", "call", "invocation_expression")
    ):
        # Check if the called function name matches
        for child in node.children:
            text = _node_text(child)
            if text == func_name:
                total += 1
                break

    # Walk children, increasing depth for nesting structures
    for child in node.children:
        child_depth = depth + 1 if node.type in _NESTING_TYPES else depth
        total += _cognitive_walk(child, child_depth, func_name)

    return total


def _node_text(node: Node) -> str:
    """Extract text from a node, safely."""
    try:
        if node.text is not None:
            return node.text.decode("utf-8", errors="replace")
    except Exception:
        pass
    return ""
