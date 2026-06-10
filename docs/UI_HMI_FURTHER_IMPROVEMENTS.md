# Eidos — Further UX / UI / HMI Enhancements: Execution Plan

> This is the continuation plan after Phases 1–5 are complete.
> Every enhancement includes **why** it matters, **what impact** it has on the product, and **what you will see** as a user.

---

## Phase 6 — Graph Intelligence

**Goal:** Make the graph explorer feel like a smart investigation tool, not just a visualization.

---

### 6.1 — Semantic Search in Graph (`/` shortcut)

**What to build**

A search overlay that appears above the graph canvas when the user presses `/`. Type a symbol name and matching nodes get highlighted instantly. Press Enter to fly the viewport to the first match.

**Why**

In a codebase with 200+ symbols, scrolling and scanning is slow. Direct search respects the user's time. HMI research shows that "find" is the most-used power action in any complex spatial UI (maps, IDEs, design tools).

**Impact**

- Navigation speed: **~5× faster** for targeted exploration.
- User confidence: they know they can always find what they're looking for.
- Reduces frustration when graphs are large.

**What you will see as a user**

1. Press `/` ? a slim search bar appears at the top of the graph area.
2. Type `check` ? nodes whose name contains "check" get a pulsing orange ring; non-matches fade to 20% opacity.
3. Press Enter ? the viewport smoothly pans and zooms to center the first highlighted node.
4. Press Escape ? search clears, all nodes return to normal.

---

### 6.2 — Contextual Zoom (Double-Click Module)

**What to build**

Double-clicking a module group circle smoothly animates the viewport to frame only that cluster. A "? Back to full graph" breadcrumb button appears at the top-left.

**Why**

Large graphs overwhelm working memory. Contextual zoom is a standard HMI pattern for complex systems (cockpit MFDs, SCADA displays, IDE outlines). It applies progressive disclosure at the spatial level — you see the whole first, then drill into a section without losing awareness.

**Impact**

- Reduces cognitive load by **~60%** (fewer competing visual elements).
- Exploration becomes structured rather than random panning.
- The minimap continues showing the full layout so context is never lost.

**What you will see as a user**

1. You see the full graph. One module group has 15 nodes packed inside.
2. Double-click the module circle ? the graph smoothly zooms in over 300 ms, centering that cluster.
3. Non-cluster nodes dim and slide out of view.
4. A breadcrumb button `? All modules` appears top-left.
5. The minimap highlights the zoomed region with the viewport box.
6. Click the breadcrumb ? smooth zoom-out back to the full view.

---

### 6.3 — Heatmap Overlay Mode

**What to build**

A toggle strip above the graph: `Color by: Type | Complexity | Churn | Risk`. When switching modes, nodes re-color with a green ? yellow ? red gradient based on the selected metric.

**Why**

Default type-based coloring (class=blue, method=green) is informational but doesn't reveal problems. A heatmap layer gives the user a single glance to spot danger zones. This follows the "pre-attentive processing" principle — warm colors pop before conscious reading.

**Impact**

- Problem identification: **10× faster** than reading a table.
- Bridges graph view with analytics data (connects Phase 3 insights to Phase 5 visualization).
- Makes presentations and code reviews dramatically more compelling.

**What you will see as a user**

1. Graph is displayed with normal type colors.
2. Click "Complexity" ? nodes transition their fill color over 200 ms to a gradient: green (low), yellow (moderate), red (high complexity).
3. A small legend appears: `Low ? High complexity`.
4. You immediately see two bright red nodes in one module — those are your refactoring targets.
5. Click "Type" ? colors revert to the familiar kind-based palette.

---

### 6.4 — Relationship Path Finder

**What to build**

A "Find path" button. User clicks it, then clicks node A, then node B. The system runs BFS on edges and highlights the shortest dependency chain between them.

**Why**

Indirect coupling is invisible in flat views. Understanding how `ModuleA.methodX` reaches `ModuleB.methodY` through three intermediaries is critical for safe refactoring. This answers: "If I change this, what else might break along the chain?"

**Impact**

- Refactoring confidence: developers understand blast radius.
- Architectural visibility: hidden transitive dependencies become obvious.
- Reduces production bugs caused by unnoticed coupling.

**What you will see as a user**

1. Click the "Find path" icon in the graph toolbar.
2. Status text appears: "Click source node…"
3. Click `PlayerController` ? it gets a blue ring. Status: "Click target node…"
4. Click `ScoreManager` ? a highlighted path animates through 3 intermediate nodes.
5. The path breadcrumb appears below: `PlayerController ? GameState ? EventBus ? ScoreManager`.
6. Non-path nodes fade. You see exactly the coupling chain.
7. Press Escape to exit path mode.

---

### 6.5 — Adaptive Density Control

**What to build**

When the graph has more than 120 visible leaf nodes and the user is zoomed out beyond 0.5×, automatically collapse low-importance nodes into aggregate dots. As the user zooms in, progressively reveal them.

**Why**

Humans process 7±2 items consciously. A screen with 300 circles of similar size creates "visual soup" where nothing stands out. Adaptive density respects cognitive bandwidth and makes important nodes visible by removing noise.

**Impact**

- Large codebases become navigable without manual filtering.
- Performance improves (fewer draw calls at low zoom).
- The tool feels intelligent — it adapts to what you need to see.

**What you will see as a user**

1. Load a large snapshot (200+ symbols). Graph appears with ~40 visible nodes and small grey aggregate circles labeled "12 more…" inside each module.
2. Zoom into a module ? the aggregate circle dissolves and individual nodes fade in smoothly.
3. Zoom back out ? low-importance nodes fade out and re-aggregate.
4. The minimap always shows all nodes regardless of density level.

---

## Phase 7 — Temporal Awareness & Trends

**Goal:** Help users understand not just the current state but the trajectory — are things getting better or worse?

---

### 7.1 — Predictive Risk Trending

**What to build**

On KPI cards, show a small sparkline representing the metric across the last N snapshots, with a trend arrow (`? Increasing` / `? Decreasing` / `? Stable`).

**Why**

A single number is a point in time. Without trend, users cannot tell if their refactoring helped or if risk is accumulating. Trend awareness is a core HMI principle in control rooms and flight decks — operators must see rate of change, not just current value.

**Impact**

- Motivation: seeing risk decrease after a refactoring sprint is rewarding.
- Early warning: spotting an upward trend before a threshold breach.
- Decision support: knowing whether to prioritize debt or features.

**What you will see as a user**

1. Open the Hotspots page. The "High Risk Methods" KPI shows `3`.
2. Below the number, a tiny sparkline shows [5, 4, 4, 3] across 4 snapshots.
3. A green badge says `? Decreasing`.
4. Another KPI "Avg Complexity" shows a flat sparkline and `? Stable`.
5. If complexity had spiked, you'd see a red `? Increasing` badge — an immediate signal to investigate.

---

### 7.2 — Snapshot Diff View

**What to build**

A "Compare" mode on the Overview page where the user picks two snapshots side by side. KPIs show delta values, and the graph can overlay added/removed nodes.

**Why**

Code evolves sprint by sprint. The most natural question after an analysis is: "Did things improve since last time?" A diff view answers this directly instead of forcing the user to mentally compare two separate page loads.

**Impact**

- Sprint retrospective value: concrete proof of improvement.
- Regression detection: new risk introduced by recent work.
- Stakeholder communication: visual before/after for non-technical leads.

**What you will see as a user**

1. On Overview, click "Compare snapshots".
2. A dropdown lets you pick Snapshot A and Snapshot B.
3. KPI cards now show: `Hotspots: 50 ? 47 (?3 ?)` with green delta.
4. Another shows: `Complexity: 8.2 ? 9.1 (+0.9 ?)` with red delta.
5. In the graph view (optional), newly added nodes glow with a blue halo; removed nodes appear as faded ghosts with a strikethrough label.
6. A summary sentence at the top: "Risk decreased overall. 2 new methods introduced, 1 dead code item removed."

---

### 7.3 — Notification Center

**What to build**

A bell icon in the status bar. Clicking it opens a dropdown with timestamped messages: ingestion completions, threshold alerts, and new findings.

**Why**

Analysis pipelines run asynchronously. If the user navigates to another page or walks away, they need to know when results are ready. Notification centers prevent the "is it done yet?" refresh loop and reduce anxiety about long-running tasks.

**Impact**

- No more manual polling — the system tells you when it's ready.
- Threshold alerts catch regressions you might miss.
- Feels professional (Slack, GitHub, VS Code all use this pattern).

**What you will see as a user**

1. You trigger a re-ingestion and navigate to the Graph Explorer.
2. After 30 seconds, a small red badge appears on the bell icon: `1`.
3. Click the bell ? a dropdown shows: `? Ingestion complete — main@abc1234 — 45 symbols indexed — 12s ago`.
4. If a hotspot exceeded risk threshold: `? checkCollisions risk score increased to 42 (threshold: 30)`.
5. Dismiss messages individually or click "Clear all".

---

### 7.4 — Micro-Animations for Data Updates

**What to build**

When KPI values change (snapshot switch, refresh), numbers interpolate from old to new with a count-up/down animation. Charts morph bar heights and donut segments smoothly.

**Why**

Abrupt number jumps are jarring and invisible. The eye doesn't track a `50` becoming `47` instantly — but a smooth countdown from 50 to 47 draws attention to the delta. This is the same principle used in sports scoreboards and financial tickers.

**Impact**

- Users notice what changed without reading diff labels.
- The UI feels alive and data-aware.
- Reinforces trust: the system is clearly updating, not stuck.

**What you will see as a user**

1. Switch from Snapshot A to Snapshot B.
2. The "Hotspots" number smoothly counts from 50 down to 47 over 400 ms.
3. The bar chart morphs heights — two bars shrink, one grows — smoothly over 350 ms.
4. The donut chart rotates its segments to the new proportions.
5. A brief green flash appears on values that improved; a red flash on values that worsened.

---

### 7.5 — Guided Onboarding Tour

**What to build**

On first visit (no `eidos_onboarded` in localStorage), show a 5-step tooltip walkthrough pointing at key UI areas.

**Why**

Complex dashboards have 40–60% first-session abandonment if users don't understand the first screen within 10 seconds. A lightweight tour closes this gap. Users who complete onboarding retain 3× better.

**Impact**

- New user activation: dramatically faster time-to-value.
- Reduces support questions.
- The user immediately knows where to click and what things mean.

**What you will see as a user**

1. First visit ? a translucent overlay appears with a spotlight on the sidebar.
2. Tooltip: "Navigate between analysis views here. Start with Overview for a summary."
3. Click "Next" ? spotlight moves to the snapshot selector: "Select your repository and snapshot to begin."
4. Next ? KPI area: "These cards show the key metrics. Hover the ? icon for explanations."
5. Next ? Graph nav button: "Explore code relationships visually in the Graph Explorer."
6. Next ? `Ctrl+K` hint: "Press Ctrl+K anytime to open the command palette."
7. Click "Done" ? tour closes, `eidos_onboarded = true` saved.
8. Re-trigger anytime from Settings ? "Restart tour".

---

## Phase 8 — Accessibility & Performance Hardening

**Goal:** Ensure the tool is usable by everyone and stays fast as features grow.

---

### 8.1 — Full ARIA Audit & Screen Reader Support

**What to build**

Add proper ARIA roles, landmarks, live regions, and accessible labels to all interactive elements. Provide accessible table alternatives for charts.

**Why**

Professional developer tools must be usable by blind and low-vision developers. WCAG 2.1 AA compliance is also a legal requirement in many organizations. Beyond compliance, good semantics improve the experience for everyone using keyboard navigation.

**Impact**

- Opens the tool to 100% of potential users.
- Legal compliance for enterprise environments.
- Keyboard-only users get proper focus management.
- Screen readers can announce KPI changes, toast messages, and navigation state.

**What you will see as a user**

1. Using a screen reader: navigating with Tab announces "Navigation, Sidebar, 7 items". Arrow keys move between nav items with spoken labels.
2. KPI cards announce: "Hotspots, 50 detected, status: action needed".
3. Toast notifications are read aloud without focus change: "Success: export complete".
4. Charts have a hidden summary table that screen readers find: "Complexity distribution: Low 60%, Medium 30%, High 10%".
5. Focus outlines are clear and visible on every interactive element.

---

### 8.2 — Performance Budget Enforcement

**What to build**

Add `performance.mark()`/`performance.measure()` instrumentation around key operations. Log warnings when thresholds are exceeded. In dev mode, show an FPS counter on the graph canvas.

**Why**

As features accumulate, performance silently degrades. A performance budget makes regressions visible immediately. This follows the principle: "You can only improve what you measure."

**Budgets**

| Operation | Threshold | Why |
|---|---|---|
| Initial page paint | < 1.2 s | Users perceive > 1 s as "slow" |
| Interaction response | < 100 ms | Feels instant to humans |
| Graph paint cycle | < 16 ms | Maintains 60 FPS |
| Minimap repaint | < 4 ms | Should never block main paint |
| Page transition | < 250 ms total | Perceived as smooth |

**Impact**

- Prevents "death by a thousand cuts" performance regression.
- Developers get immediate console warnings when budgets are exceeded.
- Users always experience a responsive tool regardless of codebase size.

**What you will see as a user**

1. Everything feels fast. Page loads never stutter.
2. (Dev mode) A tiny FPS badge in the graph corner shows `60` in green. If it drops below 30, it turns red.
3. Console shows: `[Perf] graph.paint: 11ms ?` or `[Perf] ? graph.paint: 23ms exceeded 16ms budget`.

---

### 8.3 — Persistent User Preferences

**What to build**

Remember per-page state in localStorage: sort orders, chart view selection, sidebar collapse, preferred graph view (class/module), and theme choice.

**Why**

Forcing users to re-select their preferences every session wastes time and creates frustration. Persistence makes the tool feel like it knows you. This is expected behavior in all modern applications.

**Impact**

- Repeat visits start exactly where the user left off.
- Reduces clicks-to-insight by 3–5 actions per session.
- The tool feels intelligent and personal.

**What you will see as a user**

1. You set the Hotspots table to sort by "Risk (high to low)" and switch the graph to "Module" view.
2. Close the browser and return next day.
3. Everything is exactly as you left it — sort order, view mode, collapsed panels.
4. Go to Settings ? "Reset layout" to return to defaults if needed.

---

### 8.4 — Contextual Keyboard Shortcut Sheet

**What to build**

Pressing `?` on any page shows a translucent overlay listing shortcuts available on that specific page.

**Why**

Generic shortcut documentation is buried and forgotten. Contextual sheets appear when relevant, making shortcuts discoverable through natural curiosity rather than memorization.

**Impact**

- Shortcut adoption increases (users learn by doing).
- Reduces mouse dependency over time.
- Feels professional (GitHub, Figma, Google Docs all do this).

**What you will see as a user**

1. On the Graph page, press `?`.
2. A translucent overlay appears:
   ```
   Graph Explorer Shortcuts
   ?????????????????????????
   /       Search nodes
   F       Fit all
   +/-     Zoom in/out
   Esc     Deselect / exit search
   P       Find path mode
   H       Toggle heatmap
   ```
3. Press `?` again or `Esc` ? overlay dismisses.
4. On the Hotspots page, press `?` ? shows Hotspots-specific shortcuts.

---

## Phase 9 — Platform & Sharing

**Goal:** Make Eidos valuable beyond a single developer's screen.

---

### 9.1 — Deep-Link URLs

**What to build**

Encode the current state (repo, snapshot, page, filters, selected node) into the URL hash. Sharing that URL opens Eidos in the exact same view.

**Why**

Analysis insights need to be shared in code reviews, PRs, and meetings. "Look at this thing I found" requires a shareable pointer. Without deep links, every conversation requires "go to page X, select Y, filter by Z" instructions.

**Impact**

- Collaboration speed: paste a link in Slack, teammate sees exactly what you see.
- Code review integration: link directly to a hotspot or coupling finding.
- Reduces meeting time explaining what to look at.

**What you will see as a user**

1. Navigate to Hotspots, filter by "High risk", click on `checkCollisions`.
2. The URL updates to: `#repo=myapp&snap=abc12&page=hotspots&risk=high&sel=checkCollisions`
3. Copy the URL and paste it in a PR comment.
4. Your colleague clicks it ? Eidos opens with the same filters and selection visible.

---

### 9.2 — PDF Export Report

**What to build**

A "Generate Report" action that produces a clean PDF summarizing the current analysis state: KPIs, top risks, recommended actions, and key charts.

**Why**

Not everyone has access to the live tool. Architects, managers, and auditors need offline reports. A well-formatted PDF makes the analysis portable and professional.

**Impact**

- Executive communication: share findings without tool access.
- Audit compliance: timestamped evidence of analysis.
- Team alignment: everyone works from the same data snapshot.

**What you will see as a user**

1. Click "Export" ? select "PDF Report".
2. A loading indicator shows: "Generating report…"
3. After 2–3 seconds, a PDF downloads with:
   - Cover page: repo name, snapshot, branch, date.
   - Page 2: KPI summary with color-coded risk levels.
   - Page 3: Top 5 hotspots with complexity/churn details.
   - Page 4: Dependency health summary.
   - Page 5: Recommended actions list.
4. The PDF uses the same visual language as the UI (colors, typography, badges).

---

### 9.3 — Responsive Tablet Layout

**What to build**

Adapt the layout for screens between 768px and 1024px (tablets). Sidebar collapses to icons; KPI cards stack; graph remains functional with touch gestures.

**Why**

Developers often review analysis during stand-ups (iPad on the desk), commutes, or code reviews on smaller screens. A responsive layout prevents the tool from being locked to desktop-only usage.

**Impact**

- Usable in meetings without a laptop.
- Touch-friendly graph exploration.
- No horizontal scrolling or overflow issues.

**What you will see as a user**

1. Open Eidos on an iPad.
2. Sidebar shows only icons (hover/tap to see labels).
3. KPI cards stack in a 2-column grid instead of 4-column.
4. Charts resize responsively.
5. Graph supports pinch-to-zoom and two-finger pan.
6. Command palette becomes a full-screen overlay with larger touch targets.

---

### 9.4 — Ambient Status Indicators

**What to build**

Subtle environmental cues: status bar background warmth during ingestion, sidebar micro-dots for pages with new findings, and a nearly-invisible content border accent that reflects overall risk level.

**Why**

Loud alerts demand attention and create fatigue. Calm technology communicates state through peripheral awareness — the user senses something changed without being interrupted. This follows Mark Weiser's "calm computing" principles and is used in control rooms, hospital monitors, and smart home interfaces.

**Impact**

- Users develop intuition about system state without conscious checking.
- Reduces notification fatigue.
- Creates a sense of ambient intelligence — the tool is aware and communicating subtly.

**What you will see as a user**

1. During ingestion: the status bar background subtly warms from neutral grey to a gentle amber — you sense activity without reading text.
2. After ingestion completes, the Hotspots nav icon shows a tiny blue dot — there are new findings to review.
3. If overall risk is high, the main content area has a nearly-invisible warm left-border accent (2px, very subtle). When risk is low, it's cool-toned. You don't consciously notice it, but you sense the state.

---

### 9.5 — Real-Time Collaboration Indicators

**What to build**

If multi-user backend is available, show who else is viewing the same repository/snapshot via WebSocket presence broadcasting.

**Why**

In team settings, knowing that a colleague is currently analyzing the same code prevents duplicate effort and creates opportunities for spontaneous collaboration ("Hey, I see you're looking at the same module — want to pair?").

**Impact**

- Team awareness without meetings.
- Prevents duplicate investigation effort.
- Creates a sense of shared workspace.

**What you will see as a user**

1. In the status bar, you see a small avatar: "DT" (your colleague).
2. Hover ? tooltip: "Diya is viewing Hotspots on snapshot abc1234".
3. Optionally (togglable): in the graph view, a faint cursor ghost shows where your colleague is exploring.
4. If nobody else is active, the avatar area is empty and takes no space.

---

## Execution Priority Summary

| Phase | Theme | Key Deliverables | Effort | Impact on User |
|---|---|---|---|---|
| **6** | Graph Intelligence | Search, contextual zoom, heatmap, path finder, density | 3–4 weeks | "The graph is now my primary investigation tool" |
| **7** | Temporal Awareness | Trends, diff, notifications, micro-animations, onboarding | 3–4 weeks | "I can see if things are improving and get alerted when they're not" |
| **8** | Accessibility & Perf | ARIA, perf budget, preferences, shortcut sheets | 2–3 weeks | "It's fast, remembers me, and works without a mouse" |
| **9** | Platform & Sharing | Deep links, PDF, responsive, ambient, collab | 4–5 weeks | "I can share findings and use it anywhere with my team" |

---

## Guiding Principles (Unchanged)

Every enhancement must still satisfy:

1. **Never animate fake data.** All visuals come from real analysis results.
2. **Never hide uncertainty.** If data is approximate, say so.
3. **Never use color alone.** Icons + text + color together.
4. **Every decision answers:** "Does this help the user understand or act?"
5. **Respect `prefers-reduced-motion`.** All motion is optional.
6. **Keyboard-first.** Everything works without a mouse.
7. **First viewport = summary.** Details are one action away, never forced.

---

## Success Criteria (Updated)

After all phases:

- A new user identifies the main problem in under 10 seconds.
- A power user navigates to any insight in under 3 seconds.
- Graph exploration feels like a structured investigation, not random panning.
- Trends and diffs answer "are we getting better?" instantly.
- Reports and links work in team communication without explanation.
- Screen reader users can access all insights.
- The tool runs at 60 FPS on modest hardware.
- The UI feels calm, confident, responsive, and honest.

---

## Final Vision

After these phases, Eidos becomes:

- **A cockpit** — ambient awareness of system health.
- **A microscope** — deep drill into code evidence.
- **A time machine** — tracking improvement or degradation across snapshots.
- **A coach** — suggesting next actions with confidence.
- **A team tool** — shareable, collaborative, and accessible to all.
- **An honest analyst** — every metric explained, every uncertainty visible.

The interface should feel like a trusted colleague who is always prepared, never noisy, and always ready to help you make the right decision.
