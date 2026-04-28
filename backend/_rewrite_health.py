import pathlib, re

lines = pathlib.Path('app/analysis/code_health.py').read_text('utf-8').splitlines(keepends=True)

# Find first rule class (LongMethodRule) and its preceding comment block
first_rule_line = None
for i, line in enumerate(lines):
    if 'class LongMethodRule(HealthRule):' in line:
        # Go back to find the section comment
        for j in range(i-1, max(0, i-10), -1):
            if '# ====' in lines[j] and j > 2 and '# ====' in lines[j-2]:
                first_rule_line = j - 2  # start of "# ==== CLEAN CODE ===="
                break
        if first_rule_line is None:
            first_rule_line = i
        break

# Find run_health_check function and its preceding comment block
runner_line = None
for i, line in enumerate(lines):
    if 'def run_health_check(' in line:
        for j in range(i-1, max(0, i-10), -1):
            if '# ---' in lines[j]:
                runner_line = j
                break
        if runner_line is None:
            runner_line = i
        break

print(f'Rule classes: lines {first_rule_line+1} to {runner_line}')
print(f'Runner: line {runner_line+1} to {len(lines)}')

# Build new code_health.py: header + import + runner
header = lines[:first_rule_line]
import_block = [
    "\n",
    "# Import all 40 rules from category modules\n",
    "from app.analysis.health_rules import *  # noqa: F401,F403\n",
    "\n",
    "\n",
]
runner = lines[runner_line:]

new_content = ''.join(header + import_block + runner)
pathlib.Path('app/analysis/code_health.py').write_text(new_content, 'utf-8')
print(f'Rewrote: {len(new_content.splitlines())} lines (was {len(lines)})')
