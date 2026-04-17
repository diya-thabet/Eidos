"""
PR review engine.

Modules:
    models            - DiffHunk, ChangedSymbol, ReviewFinding, ReviewReport
    diff_parser       - Unified diff parser + line-to-symbol mapping
    heuristics        - Behavioral risk heuristics (8 detectors)
    impact_analyzer   - Call-graph blast radius analysis
    reviewer          - Pipeline orchestrator
"""
