"""
Static analysis engine for C# codebases.

Modules:
    models          - Data classes for analysis results
    csharp_parser   - Tree-sitter based C# parser
    graph_builder   - Call graph and module dependency graph
    entry_points    - Controller, Main, Startup detection
    metrics         - LOC, fan-in/out, hotspot detection
"""
