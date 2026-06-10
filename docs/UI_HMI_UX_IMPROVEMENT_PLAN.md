# Eidos UI / HMI Improvement Plan

## Goal

Make Eidos feel less like a static technical dashboard and more like a confident, responsive, human-centered code intelligence cockpit.

The UI should help users answer three questions quickly:

1. **What is happening?**
2. **Why does it matter?**
3. **What should I do next?**

This plan focuses on interaction quality, visual hierarchy, motion, trust, perceived performance, and cognitive ergonomics.

---

## Product Experience Principles

### 1. Clarity Before Beauty

**Decision**

Every page should first communicate the most important insight in plain language before showing raw tables or charts.

**Why**

Users scan before they read. If the first screen is too dense, they feel lost even if the data is technically correct. Clear hierarchy reduces cognitive load and increases trust.

**How**

- Add a short page summary under each page title.
- Use one primary insight card per analysis page.
- Put secondary details below charts and tables.
- Avoid showing many equal-weight components at once.

---

### 2. Progressive Disclosure

**Decision**

Show summary first, then allow users to expand into details.

**Why**

People process complex systems better in layers. Too much detail at once creates decision fatigue. Progressive disclosure makes the tool feel intelligent and calm.

**How**

- Collapse advanced tables by default when charts already explain the situation.
- Add `Show details` / `Hide details` controls.
- Use expandable rows for source code, contributors, dependency metadata, and graph neighborhoods.
- Keep the first viewport focused on KPIs + insights.

---

### 3. Motion With Meaning

**Decision**

Use animation only to communicate state, direction, or relationship.

**Why**

Random motion feels decorative and can distract. Meaningful motion improves comprehension by showing continuity: what changed, where the user is, and what is loading.

**How**

- Animate page transitions with a subtle fade + upward motion.
- Animate chart bars and gauges on entry.
- Animate graph node selection with focus rings and smooth side-panel updates.
- Use skeleton loading instead of plain spinners for data-heavy pages.
- Respect `prefers-reduced-motion` for accessibility.

---

### 4. Trust Through Explainability

**Decision**

Every metric should have a visible explanation: what it means, how it is calculated, and when it may be approximate.

**Why**

Users lose trust when numbers do not match their expectations. Explainable metrics prevent confusion, especially for code analytics where terms like churn, complexity, and ownership can be interpreted differently.

**How**

- Add info tooltips beside KPI labels.
- Show formula text for risk scores.
- Label approximated/legacy metrics clearly.
- Add `Data freshness` indicators showing snapshot time, branch, commit SHA, and ingestion status.
- For Hotspots, distinguish:
  - Repository commits
  - Commits touching a symbol
  - Contributors owning current lines

---

### 5. Human Decision Support

**Decision**

Each analysis page should end with recommended next actions.

**Why**

A dashboard that only reports data forces the user to translate metrics into action. Good HMI reduces this gap and helps users feel guided.

**How**

Examples:

- Hotspots: `Add tests around checkCollisions`, `Refactor high-complexity methods`, `Review ownership concentration`.
- Dependencies: `Pin unpinned versions`, `Audit large dependency groups`.
- Coupling: `Reduce efferent coupling in unstable modules`.
- Dead Code: `Remove unreachable methods after confirmation`.
- Cycles: `Break cycle by extracting interface or event boundary`.

---

## Visual Design Improvements

### 1. Stronger Page Hero Sections

**Decision**

Replace plain page headers with compact hero panels containing status, summary, and primary action.

**Why**

A hero section creates orientation. It tells the user where they are, what state the system is in, and what action is expected.

**Implementation**

For each page:

- Title
- One-sentence explanation
- Snapshot badge
- Branch badge
- Last analysis time
- Primary action button if relevant

Example:

```text
Hotspots & Contributors
2 high-risk methods need attention. Repository has 4 commits and 4 contributors.
[main] [snapshot abc123] [completed 2 min ago]
```

---

### 2. Better KPI Cards

**Decision**

Make KPI cards more expressive with icons, trend labels, confidence states, and microcopy.

**Why**

Numbers without context are hard to interpret. A KPI should answer whether the value is good, bad, or neutral.

**Implementation**

Current:

```text
50 Hotspots
```

Improved:

```text
Hotspots
50 detected
Top 2 need review
```

Visual states:

- Green: healthy
- Yellow: watch
- Red: action needed
- Blue/purple: neutral information

---

### 3. Better Empty States

**Decision**

Replace generic empty messages with helpful, contextual empty states.

**Why**

Empty states are part of the user journey. They should explain why there is no data and what to do next.

**Implementation**

Examples:

- No snapshot: `Select a repository snapshot to start analysis.`
- No blame data: `Contributor data requires git history. Re-ingest with full clone enabled.`
- No dependencies: `No supported manifest files found.`
- No dead code: `No unreachable code detected. Nice.`

---

### 4. Consistent Chart Language

**Decision**

Use chart types consistently across pages.

**Why**

Consistency helps users learn the interface faster. A donut should always mean distribution. A scatter should always mean relationship/risk landscape.

**Chart Rules**

| Chart | Use For | Why |
|---|---|---|
| Donut | Distribution | Quick proportional understanding |
| Bar | Ranking | Easy comparison between items |
| Scatter | Risk relationship | Shows correlation and outliers |
| Gauge | Single score | Fast status perception |
| Timeline | Real historical data only | Prevents fake confidence |
| Heatmap | Density / file activity | Good for spotting concentration |

---

## Interaction Improvements

### 1. Page Transitions

**Decision**

Add subtle animated transitions when navigating between sections.

**Why**

Transitions help preserve spatial continuity. Users feel the app is responsive and polished.

**Implementation**

- Fade in main content.
- Slight `translateY(6px -> 0)` animation.
- Duration: `160-220ms`.
- Disable under `prefers-reduced-motion`.

---

### 2. Skeleton Loading

**Decision**

Use skeleton placeholders instead of centered spinners for tables, charts, and cards.

**Why**

Skeletons improve perceived performance. Users understand the page structure before data arrives.

**Implementation**

- KPI skeleton cards.
- Chart skeleton blocks.
- Table skeleton rows.
- Keep spinner only for small inline actions.

---

### 3. Hover and Focus Feedback

**Decision**

Improve hover/focus states for cards, rows, buttons, and graph nodes.

**Why**

Good feedback makes the UI feel alive and reduces interaction uncertainty.

**Implementation**

- Cards lift slightly on hover when clickable.
- Table rows highlight with subtle background.
- Buttons use scale/brightness changes.
- Keyboard focus states must be visible.

---

### 4. Command Palette

**Decision**

Add a `Ctrl+K` command palette.

**Why**

Power users need fast navigation. A command palette makes the app feel professional and efficient.

**Commands**

- Go to Overview
- Open Hotspots
- Search Symbols
- Export Report
- Re-ingest Repo
- Toggle Theme
- Open Settings

---

### 5. Guided Drill-Down

**Decision**

Make every chart item clickable and connected to a detail panel.

**Why**

Users naturally ask “why is this high?” after seeing a chart. Drill-down keeps the flow continuous.

**Implementation**

- Clicking a hotspot bubble opens symbol details.
- Clicking a contributor opens files/modules owned.
- Clicking a module in coupling opens dependency relationships.
- Clicking a dependency ecosystem filters the dependency table.

---

## Hotspots Page Specific Improvements

### 1. Separate Real Repository Metrics From Derived Metrics

**Decision**

Display repository-level metrics separately from symbol-level metrics.

**Why**

This avoids confusion like `50 commits` when the repo has only `4` commits. Repository commits and symbol churn are different concepts.

**Implementation**

Sections:

1. Repository facts
   - Repo commits
   - Contributors
   - Indexed files
   - Snapshot SHA

2. Hotspot analysis
   - Hotspot count
   - Average risk
   - High-risk methods
   - Churn per hotspot

3. Ownership analysis
   - Lines currently owned
   - Modules owned
   - Bus factor warnings

---

### 2. Metric Explanation Tooltips

**Decision**

Add tooltips to every hotspot KPI.

**Why**

Hotspot analytics can be misunderstood. Tooltips help users trust the numbers.

**Tooltip examples**

- `Repo Commits`: Number of commits reachable from HEAD in the ingested repository.
- `Hotspots`: Methods/constructors with non-zero churn and complexity.
- `Risk`: Symbol commit count × cyclomatic complexity.
- `Lines Owned`: Current lines attributed by git blame, counted on leaf symbols to avoid class/method overlap.

---

### 3. Confidence Badge

**Decision**

Show a data confidence badge.

**Why**

Some analytics depend on git history and parser quality. A confidence badge communicates reliability honestly.

**States**

- High: full git history + blame available
- Medium: partial blame or legacy data
- Low: no blame / shallow history / parser fallback

---

### 4. Action Panel

**Decision**

Add a `Recommended Actions` panel above the table.

**Why**

Users need next steps, not only diagnostics.

**Example actions**

- `Add tests around checkCollisions before refactoring.`
- `Split PlayingState responsibilities.`
- `Review methods with complexity > 10.`
- `Confirm ownership distribution with team.`

---

## Graph Explorer Improvements

### 1. Smooth Node Selection

**Decision**

Animate node selection and side-panel transitions.

**Why**

Graph exploration is spatial. Smooth transitions help users track context.

**Implementation**

- Selected node pulse ring.
- Neighbor nodes brighten.
- Non-neighbor nodes fade.
- Side panel slides in with code/actions.

---

### 2. Breadcrumb Context

**Decision**

Add graph navigation breadcrumbs.

**Why**

Users can get lost in graphs. Breadcrumbs preserve orientation.

**Example**

```text
GameEngine ? PlayingState ? checkCollisions
```

---

### 3. Mini Map

**Decision**

Add a small minimap for large graphs.

**Why**

Large visual spaces need overview + detail. This follows classic HMI principles for complex system monitoring.

---

## Accessibility Improvements

### 1. Reduced Motion Support

**Decision**

Respect `prefers-reduced-motion`.

**Why**

Some users experience discomfort with motion. Accessibility improves usability for everyone.

---

### 2. Keyboard Navigation

**Decision**

Ensure all interactive elements are keyboard accessible.

**Why**

A professional UI should not require a mouse.

**Implementation**

- Visible focus outlines.
- `Tab` order matches layout.
- `Enter` / `Space` activates cards and rows.
- `Esc` closes panels/modals.

---

### 3. Color Is Not the Only Signal

**Decision**

Use icons, labels, and text with colors.

**Why**

Color-only feedback fails for color-blind users and low-quality displays.

**Implementation**

- Red + `High Risk`
- Yellow + `Watch`
- Green + `Healthy`

---

## Animation Guidelines

### Motion Timing

| Interaction | Duration | Why |
|---|---:|---|
| Hover feedback | 80-120ms | Feels instant |
| Page transition | 160-220ms | Smooth but not slow |
| Chart entrance | 300-500ms | Helps comprehension |
| Modal/panel open | 180-260ms | Feels responsive |
| Toast | 200ms in / 150ms out | Lightweight feedback |

### Easing

Use:

```css
cubic-bezier(0.2, 0.8, 0.2, 1)
```

**Why**

This easing starts quickly and settles softly, which feels responsive without being abrupt.

---

## Execution Plan

## Phase 1 — Trust & Reliability UI

**Goal**

Make data meaning obvious and prevent metric confusion.

**Tasks**

1. Add tooltip helper component.
2. Add metric explanations to Hotspots KPIs.
3. Split Hotspots KPIs into `Repository Facts`, `Hotspot Analysis`, and `Ownership`.
4. Add snapshot metadata badges.
5. Add data confidence badge.

**Why first**

Trust is more important than decoration. If users doubt the numbers, animations will not help.

**Expected Result**

Users understand exactly why a metric appears and whether it is reliable.

---

## Phase 2 — Motion & Perceived Performance

**Goal**

Make the app feel faster and more polished.

**Tasks**

1. Add page transition animation.
2. Add skeleton loaders for major pages.
3. Animate KPI cards and chart entry.
4. Add hover/focus microinteractions.
5. Add `prefers-reduced-motion` CSS guard.

**Why second**

Once data is trustworthy, motion improves emotional perception and usability.

**Expected Result**

Navigation feels smoother, loading feels shorter, and the UI feels more alive.

---

## Phase 3 — Guided Analysis

**Goal**

Turn dashboards into decision support.

**Tasks**

1. Add `Recommended Actions` panels.
2. Make chart elements clickable.
3. Add detail drawer for hotspot/contributor/module drill-down.
4. Add filter chips from chart selections.
5. Add export action from insight panels.

**Why third**

After users trust the data and enjoy the interaction, the next improvement is helping them act.

**Expected Result**

Users can move from insight ? evidence ? action without losing context.

---

## Phase 4 — Power User Experience

**Goal**

Make advanced workflows fast.

**Tasks**

1. Add `Ctrl+K` command palette.
2. Add saved filters per page.
3. Add recent repositories/snapshots.
4. Add keyboard shortcuts.
5. Add quick compare between snapshots.

**Why fourth**

Power-user features are valuable after the main experience is stable and understandable.

**Expected Result**

Frequent users navigate faster and feel in control.

---

## Phase 5 — Advanced HMI Layer

**Goal**

Make Eidos feel like an intelligent cockpit.

**Tasks**

1. Add global system status bar.
2. Add analysis timeline across snapshots.
3. Add graph minimap.
4. Add live ingestion progress timeline.
5. Add risk radar summary for all analysis dimensions.

**Why fifth**

These features create a high-end HMI experience, but they depend on stable foundations.

**Expected Result**

The UI feels like a professional code intelligence platform, not a basic dashboard.

---

## Suggested Implementation Order

1. Hotspots metric tooltips and page restructuring.
2. Page transitions and skeleton loaders.
3. Clickable charts + detail drawer.
4. Recommended action panels.
5. Command palette.
6. Graph minimap and advanced cockpit layer.

---

## Success Criteria

The UI is better when:

- Users understand metrics without asking for clarification.
- The first viewport of each page gives a clear summary.
- No chart contains fake/simulated data.
- Every warning includes a recommended action.
- Loading feels structured, not empty.
- Motion improves comprehension and never distracts.
- Keyboard and reduced-motion users can still use everything.
- A new user can identify the main problem in under 10 seconds.

---

## Non-Negotiable Rules

1. Do not animate fake data.
2. Do not hide uncertainty.
3. Do not use color alone to communicate risk.
4. Do not overload the first screen.
5. Do not make tables the first thing users see when a summary is possible.
6. Do not sacrifice reliability for visual appeal.
7. Every visual decision must answer: `Does this help the user understand or act?`

---

## Final Direction

The best version of Eidos should feel like:

- **A cockpit** for system awareness.
- **A microscope** for drilling into code evidence.
- **A coach** for suggesting next actions.
- **A trustworthy analyst** that explains every metric.

The UI should be beautiful, but more importantly, it should feel calm, confident, responsive, and honest.
