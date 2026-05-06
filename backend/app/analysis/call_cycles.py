"""
Function-level cycle detection using Tarjan's SCC algorithm.

Detects:
- Direct recursion (size-1 SCC)
- Mutual recursion / circular call chains (size-2+ SCC)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CallCycle:
    """A single call cycle (strongly connected component)."""

    members: list[str]
    size: int
    cycle_path: list[str]
    files: list[str]


@dataclass
class CallCycleReport:
    """Full cycle detection report for a snapshot."""

    total_cycles: int = 0
    direct_recursion_count: int = 0
    mutual_recursion_count: int = 0
    largest_cycle_size: int = 0
    cycles: list[CallCycle] = field(default_factory=list)
    direct_recursions: list[str] = field(default_factory=list)


def detect_call_cycles(
    callees: dict[str, list[str]],
    symbol_files: dict[str, str] | None = None,
) -> CallCycleReport:
    """Find call cycles using Tarjan's strongly connected components algorithm.

    Args:
        callees: Adjacency list mapping fq_name -> list of called fq_names.
        symbol_files: Optional mapping of fq_name -> file_path for context.

    Returns:
        CallCycleReport with all detected cycles.
    """
    symbol_files = symbol_files or {}

    # Build the set of all nodes
    all_nodes: set[str] = set()
    for src, targets in callees.items():
        all_nodes.add(src)
        all_nodes.update(targets)

    # Detect direct recursion (self-loops) before SCC
    direct_recursions: list[str] = []
    for src, targets in callees.items():
        if src in targets:
            direct_recursions.append(src)

    # Tarjan's algorithm
    sccs = _tarjan_scc(callees, all_nodes)

    report = CallCycleReport()
    report.direct_recursion_count = len(direct_recursions)
    report.direct_recursions = sorted(direct_recursions)

    for scc in sccs:
        if len(scc) < 2:
            continue
        # Non-trivial SCC = mutual recursion cycle
        report.mutual_recursion_count += 1
        files = sorted({symbol_files.get(m, "") for m in scc if m in symbol_files})
        cycle_path = _find_cycle_path(scc, callees)

        report.cycles.append(CallCycle(
            members=sorted(scc),
            size=len(scc),
            cycle_path=cycle_path,
            files=[f for f in files if f],
        ))

    report.total_cycles = report.mutual_recursion_count
    if report.cycles:
        report.largest_cycle_size = max(c.size for c in report.cycles)

    # Sort cycles by size descending
    report.cycles.sort(key=lambda c: c.size, reverse=True)

    return report


def _tarjan_scc(adj: dict[str, list[str]], nodes: set[str]) -> list[list[str]]:
    """Tarjan's algorithm for finding strongly connected components.

    Returns all SCCs (including trivial ones of size 1).
    Time complexity: O(V + E).
    """
    index_counter = [0]
    stack: list[str] = []
    on_stack: set[str] = set()
    indices: dict[str, int] = {}
    lowlinks: dict[str, int] = {}
    result: list[list[str]] = []

    def strongconnect(v: str) -> None:
        indices[v] = index_counter[0]
        lowlinks[v] = index_counter[0]
        index_counter[0] += 1
        stack.append(v)
        on_stack.add(v)

        for w in adj.get(v, []):
            if w not in nodes:
                continue  # Skip edges to unknown nodes
            if w not in indices:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif w in on_stack:
                lowlinks[v] = min(lowlinks[v], indices[w])

        # Root of SCC
        if lowlinks[v] == indices[v]:
            scc: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                scc.append(w)
                if w == v:
                    break
            result.append(scc)

    for node in sorted(nodes):  # Sorted for determinism
        if node not in indices:
            strongconnect(node)

    return result


def _find_cycle_path(scc: list[str], adj: dict[str, list[str]]) -> list[str]:
    """Find one example cycle path through the SCC members.

    Uses BFS from the first member to find a path back to itself.
    """
    scc_set = set(scc)
    start = scc[0]

    # BFS to find path from start back to start using only SCC members
    visited: dict[str, str | None] = {start: None}
    queue = [start]

    while queue:
        current = queue.pop(0)
        for neighbor in adj.get(current, []):
            if neighbor not in scc_set:
                continue
            if neighbor == start and current != start:
                # Found cycle back to start
                path = [start]
                node = current
                # Reconstruct path backwards
                reverse_path = [current]
                while node != start:
                    node = visited[node]  # type: ignore[assignment]
                    if node is not None:
                        reverse_path.append(node)
                reverse_path.reverse()
                path = reverse_path + [start]
                return path
            if neighbor not in visited:
                visited[neighbor] = current
                queue.append(neighbor)

    # Fallback: just list members as cycle
    return scc[:3] + [scc[0]]
