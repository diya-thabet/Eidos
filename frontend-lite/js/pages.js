// All page renderers and logic in one file for reliability
// Navigation + theme + connection
function navigate(pg) {
    document.querySelectorAll('.nav-btn').forEach(function(b) { b.classList.remove('active'); });
    var btn = document.querySelector('[data-p="' + pg + '"]');
    if (btn) btn.classList.add('active');
    var pages = { repos: pgRepos, overview: pgOverview, symbols: pgSymbols, health: pgHealth, graph: pgGraph, deadcode: pgDead, coupling: pgCoupling, ask: pgAsk, review: pgReview, docs: pgDocs, search: pgSearch, exports: pgExports, settings: pgSettings };
    if (pages[pg]) pages[pg]();
}

function toggleTheme() {
    var el = document.documentElement;
    var current = el.getAttribute('data-theme');
    var next = current === 'dark' ? 'light' : 'dark';
    el.setAttribute('data-theme', next);
    localStorage.setItem('eidos_theme', next);
    document.getElementById('theme-btn').textContent = next === 'dark' ? '\u2600' : '\u263D';
    if (GE.cvs) GE.paint(); // repaint graph for theme
}

function checkConn() {
    API.get('/health').then(function() {
        document.getElementById('cd').className = 'conn-dot on';
        document.getElementById('ct').textContent = 'Connected';
    }).catch(function() {
        document.getElementById('cd').className = 'conn-dot off';
        document.getElementById('ct').textContent = 'Offline';
    });
}

// =================== REPOS ===================
function pgRepos() {
    html('main', '<div class="page-head between row"><div><h1>Repositories</h1><p>Manage and analyze Git repositories</p></div><button class="btn btn-p" onclick="toggleForm()">+ Add Repo</button></div>' +
        '<div class="card hidden" id="rf"><div class="field"><label>Name</label><input class="inp" id="rn" placeholder="my-project"></div><div class="field"><label>Git URL</label><input class="inp" id="ru" placeholder="https://github.com/user/repo"></div><div class="row g-8"><button class="btn btn-p" onclick="addRepo()">Register & Ingest</button><button class="btn btn-g" onclick="toggleForm()">Cancel</button></div></div>' +
        '<div id="rl"><div class="loader"><span class="spin"></span> Loading...</div></div>');
    loadRepos();
}
function toggleForm() { $('rf').classList.toggle('hidden'); }
function loadRepos() {
    API.get('/repos').then(function(d) {
        var repos = Array.isArray(d) ? d : (d.items || []);
        if (!repos.length) { html('rl', '<div class="empty"><h3>No repos yet</h3><p>Add one above.</p></div>'); return; }
        var h = '<div class="card" style="padding:0;overflow:hidden"><table class="tbl"><thead><tr><th>Name</th><th>URL</th><th>Created</th><th></th></tr></thead><tbody>';
        repos.forEach(function(r) {
            h += '<tr><td><strong>' + esc(r.name) + '</strong></td><td style="font-size:12px;color:var(--text-2)">' + esc(r.url) + '</td><td style="font-size:12px">' + new Date(r.created_at).toLocaleDateString() + '</td><td class="row g-8"><button class="btn btn-s btn-p" onclick="selRepo(\'' + r.id + '\')">Select</button><button class="btn btn-s btn-g" onclick="ingest(\'' + r.id + '\')">Ingest</button><button class="btn btn-s btn-d" onclick="delRepo(\'' + r.id + '\')">Del</button></td></tr>';
        });
        h += '</tbody></table></div>';
        html('rl', h);
    }).catch(function(e) { html('rl', '<div class="empty"><h3>Cannot connect</h3><p>' + esc(e.message) + '</p></div>'); });
}
function addRepo() {
    var n = $('rn').value.trim(), u = $('ru').value.trim();
    if (!n || !u) { toast('Fill both fields', false); return; }
    API.post('/repos', { name: n, url: u }).then(function(r) { toast(r.name + ' registered'); toggleForm(); ingest(r.id); loadRepos(); }).catch(function(e) { toast(e.message, false); });
}
function ingest(id) {
    API.post('/repos/' + id + '/ingest').then(function(r) { toast('Ingestion started'); poll(id, r.snapshot_id); }).catch(function(e) { toast(e.message, false); });
}
function poll(rid, sid) {
    setTimeout(function check() {
        API.get('/repos/' + rid + '/status').then(function(d) {
            var snap = (d.snapshots || []).filter(function(s) { return s.id === sid; })[0];
            if (!snap) return;
            if (snap.status === 'completed') { toast('Done! ' + snap.file_count + ' files'); S.set(rid, sid); loadRepos(); }
            else if (snap.status === 'failed') { toast('Failed: ' + (snap.error_message || ''), false); }
            else setTimeout(check, 3000);
        }).catch(function() { setTimeout(check, 5000); });
    }, 2500);
}
function selRepo(id) {
    API.get('/repos/' + id + '/status').then(function(d) {
        var done = (d.snapshots || []).filter(function(s) { return s.status === 'completed'; });
        if (!done.length) { toast('No completed snapshot', false); return; }
        S.set(id, done[done.length - 1].id);
        toast('Selected: ' + d.name);
        navigate('overview');
    }).catch(function(e) { toast(e.message, false); });
}
function delRepo(id) { if (!confirm('Delete?')) return; API.del('/repos/' + id).then(function() { toast('Deleted'); loadRepos(); }).catch(function(e) { toast(e.message, false); }); }

// =================== OVERVIEW ===================
function pgOverview() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="loader"><span class="spin"></span> Loading...</div>');
    API.get(S.path() + '/overview').then(function(d) {
        var k = d.symbols_by_kind || {}, tot = 0;
        Object.keys(k).forEach(function(x) { tot += k[x]; });
        var h = '<div class="page-head"><h1>Overview</h1><p>Snapshot ' + S.snap.slice(0, 8) + '</p></div>';
        h += '<div class="stat-row"><div class="stat-item"><div class="stat-num">' + d.total_symbols + '</div><div class="stat-txt">Symbols</div></div><div class="stat-item"><div class="stat-num">' + d.total_edges + '</div><div class="stat-txt">Edges</div></div><div class="stat-item"><div class="stat-num">' + d.total_modules + '</div><div class="stat-txt">Modules</div></div><div class="stat-item"><div class="stat-num">' + (k['class'] || 0) + '</div><div class="stat-txt">Classes</div></div><div class="stat-item"><div class="stat-num">' + (k['method'] || 0) + '</div><div class="stat-txt">Methods</div></div><div class="stat-item"><div class="stat-num">' + (k['interface'] || 0) + '</div><div class="stat-txt">Interfaces</div></div></div>';
        h += '<div class="card"><div class="card-hd">Distribution</div><table class="tbl"><thead><tr><th>Kind</th><th>Count</th><th style="width:45%"></th></tr></thead><tbody>';
        Object.keys(k).sort(function(a, b) { return k[b] - k[a]; }).forEach(function(kn) {
            var pct = tot ? (k[kn] / tot * 100).toFixed(1) : 0;
            h += '<tr><td><span class="badge ' + kindBadge(kn) + '">' + kn + '</span></td><td>' + k[kn] + '</td><td><div class="prog"><div class="prog-fill" style="width:' + pct + '%;background:var(--accent)"></div></div></td></tr>';
        });
        h += '</tbody></table></div>';
        html('main', h);
    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });
}

// =================== SYMBOLS ===================
var _sOff = 0;
function pgSymbols() {
    if (!S.ok()) { html('main', noSnap()); return; }
    _sOff = 0;
    html('main', '<div class="page-head"><h1>Symbols</h1><p>Browse code entities</p></div><div class="card"><div class="row g-8" style="margin-bottom:12px"><select class="inp" id="sk" onchange="_sOff=0;loadSym()" style="width:130px"><option value="">All</option><option value="class">Class</option><option value="method">Method</option><option value="interface">Interface</option><option value="field">Field</option><option value="enum">Enum</option></select><input class="inp" id="sq" placeholder="Filter..." style="width:180px" oninput="loadSym()"></div><div id="st"></div><div class="row between mt"><span id="sc" style="font-size:11px;color:var(--text-3)"></span><div class="row g-8"><button class="btn btn-s btn-g" id="sp" onclick="_sOff=Math.max(0,_sOff-40);loadSym()" disabled>Prev</button><button class="btn btn-s btn-g" id="sn" onclick="_sOff+=40;loadSym()">Next</button></div></div></div>');
    loadSym();
}
function loadSym() {
    var kind = $('sk').value, q = $('sq').value.trim();
    var p = S.path() + '/symbols?limit=40&offset=' + _sOff;
    if (kind) p += '&kind=' + kind;
    API.get(p).then(function(d) {
        var items = d.items || [];
        $('sc').textContent = d.total + ' total';
        $('sp').disabled = _sOff === 0;
        $('sn').disabled = !d.has_more;
        if (!items.length) { html('st', '<p style="color:var(--text-3)">No results</p>'); return; }
        var filtered = q ? items.filter(function(s) { return s.name.toLowerCase().indexOf(q.toLowerCase()) >= 0; }) : items;
        var h = '<table class="tbl"><thead><tr><th>Kind</th><th>Name</th><th>Namespace</th><th>File</th><th>Lines</th></tr></thead><tbody>';
        filtered.forEach(function(s) { h += '<tr><td><span class="badge ' + kindBadge(s.kind) + '">' + s.kind + '</span></td><td><strong>' + esc(s.name) + '</strong></td><td style="font-size:11px;color:var(--text-3)">' + esc(s.namespace) + '</td><td style="font-size:11px">' + esc((s.file_path || '').split('/').pop()) + '</td><td>' + s.start_line + '-' + s.end_line + '</td></tr>'; });
        h += '</tbody></table>';
        html('st', h);
    }).catch(function(e) { html('st', '<p style="color:var(--red)">' + esc(e.message) + '</p>'); });
}

// =================== HEALTH ===================
function pgHealth() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="loader"><span class="spin"></span> Running 66 health rules...</div>');
    API.post(S.path() + '/health', {}).then(function(d) {
        var s = d.overall_score || 0, col = scoreCol(s);
        var h = '<div class="page-head"><h1>Code Health</h1><p>66 rules, 13 categories</p></div>';
        h += '<div class="stat-row"><div class="stat-item"><div class="score-ring" style="border-color:' + col + '"><span class="v" style="color:' + col + '">' + s.toFixed(1) + '</span><span class="g" style="color:' + col + '">' + grade(s) + '</span></div><div class="stat-txt">Score</div></div><div class="stat-item"><div class="stat-num" style="color:var(--red)">' + (d.summary && d.summary.error || 0) + '</div><div class="stat-txt">Errors</div></div><div class="stat-item"><div class="stat-num" style="color:var(--yellow)">' + (d.summary && d.summary.warning || 0) + '</div><div class="stat-txt">Warnings</div></div><div class="stat-item"><div class="stat-num" style="color:var(--blue)">' + (d.summary && d.summary.info || 0) + '</div><div class="stat-txt">Info</div></div></div>';
        if (d.category_scores) {
            h += '<div class="card"><div class="card-hd">Categories</div><table class="tbl"><thead><tr><th>Category</th><th>Score</th><th style="width:40%"></th></tr></thead><tbody>';
            Object.keys(d.category_scores).sort(function(a, b) { return d.category_scores[a] - d.category_scores[b]; }).forEach(function(c) {
                var v = d.category_scores[c], cl = scoreCol(v);
                h += '<tr><td style="text-transform:capitalize">' + c.replace(/_/g, ' ') + '</td><td style="color:' + cl + ';font-weight:600">' + v.toFixed(1) + '</td><td><div class="prog"><div class="prog-fill" style="width:' + v + '%;background:' + cl + '"></div></div></td></tr>';
            });
            h += '</tbody></table></div>';
        }
        var findings = d.findings || [];
        if (findings.length) {
            h += '<div class="card"><div class="card-hd">Findings (' + findings.length + ')</div>';
            findings.slice(0, 35).forEach(function(f) {
                var dc = f.severity === 'error' ? 'var(--red)' : f.severity === 'warning' ? 'var(--yellow)' : 'var(--blue)';
                h += '<div class="finding"><div class="dot" style="background:' + dc + '"></div><div style="flex:1"><div class="msg">' + esc(f.message) + '</div><div class="sub">' + esc(f.rule_id) + ' &middot; ' + esc(f.file || '') + ':' + (f.line || '') + '</div></div><span class="badge ' + (f.severity === 'error' ? 'b-red' : f.severity === 'warning' ? 'b-yellow' : 'b-blue') + '">' + f.severity + '</span></div>';
            });
            if (findings.length > 35) h += '<p style="padding:8px;font-size:11px;color:var(--text-3)">+ ' + (findings.length - 35) + ' more</p>';
            h += '</div>';
        }
        html('main', h);
    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });
}

// =================== GRAPH EXPLORER ===================
var _mermaid = '';
function pgGraph() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="page-head"><h1>Graph Explorer</h1><p>Interactive architecture visualization</p></div>' +
        '<div class="g-bar"><button class="btn btn-s btn-p" data-gv="class" onclick="gLoad(\'class\')">Classes</button><button class="btn btn-s btn-g" data-gv="module" onclick="gLoad(\'module\')">Modules</button><button class="btn btn-s btn-g" data-gv="calls" onclick="gLoad(\'calls\')">Calls</button><div class="sep"></div><button class="btn btn-s btn-g" onclick="GE.shuffle()">Reset</button><button class="btn btn-s btn-g" onclick="GE.fitAll()">Fit</button><button class="btn btn-s btn-g" onclick="GE.exportPNG();toast(\'PNG saved\')">PNG</button><button class="btn btn-s btn-g" onclick="toggleMermaid()">Mermaid</button></div>' +
        '<div class="graph-area" id="ga"><canvas id="gc"></canvas>' +
        '<div class="g-ctrl"><button onclick="GE.sc*=1.2;GE.paint()">+</button><button onclick="GE.sc*=0.8;GE.paint()">&minus;</button><button onclick="GE.fitAll()">\u2922</button></div>' +
        '<div class="g-legend"><h6>Nodes</h6><div class="lr"><div class="ld" style="background:#2563eb"></div>Class</div><div class="lr"><div class="ld" style="background:#7c3aed"></div>Interface</div><div class="lr"><div class="ld" style="background:#16a34a"></div>Method</div><div class="lr"><div class="ld" style="background:#dc2626"></div>Enum</div><h6>Edges</h6><div class="lr"><div class="ll" style="background:#6246ea"></div>Calls</div><div class="lr"><div class="ll" style="background:#ca8a04"></div>Inherits</div><div class="lr"><div class="ll" style="background:#7c3aed"></div>Implements</div></div>' +
        '<div class="g-info" id="gi"><span class="x" onclick="$(\'gi\').classList.remove(\'show\')">&times;</span><h4 id="gin"></h4><div class="ir"><b>Kind:</b> <span id="gik"></span></div><div class="ir"><b>File:</b> <span id="gif"></span></div><div class="ir"><b>Lines:</b> <span id="gil"></span></div><div class="ir"><b>Edges:</b> <span id="gie"></span></div></div>' +
        '<div class="g-stats"><span id="gsn">0</span> nodes &middot; <span id="gse">0</span> edges</div></div>' +
        '<div class="card hidden" id="mc" style="margin-top:14px"><div class="row between"><div class="card-hd" style="margin:0">Mermaid Source</div><button class="btn btn-s btn-g" onclick="navigator.clipboard.writeText(_mermaid);toast(\'Copied\')">Copy</button></div><div class="code" id="mcs"></div></div>');
    GE.init($('gc'));
    GE.onSelect = function(n) { $('gi').classList.add('show'); $('gin').textContent = n.name; $('gik').textContent = n.kind; $('gif').textContent = n.file || '-'; $('gil').textContent = n.sl ? n.sl + '-' + n.el : '-'; $('gie').textContent = GE.edges.filter(function(e) { return e.s === n || e.t === n; }).length; };
    GE.onDeselect = function() { $('gi').classList.remove('show'); };
    gLoad('class');
}
function gLoad(view) {
    document.querySelectorAll('[data-gv]').forEach(function(b) { b.className = 'btn btn-s btn-g'; });
    var ab = document.querySelector('[data-gv="' + view + '"]');
    if (ab) ab.className = 'btn btn-s btn-p';

    if (view === 'module') {
        API.get(S.path() + '/coupling').then(function(d) {
            GE.buildModules(d.modules || []);
            updGStats();
        }).catch(function(e) { toast(e.message, false); });
    } else {
        Promise.all([
            API.get(S.path() + '/symbols?limit=500'),
            API.get(S.path() + '/edges?limit=1000')
        ]).then(function(res) {
            var syms = res[0].items || [], edges = res[1].items || [];
            if (view === 'class') {
                syms = syms.filter(function(s) { return s.kind === 'class' || s.kind === 'interface' || s.kind === 'enum'; });
                edges = edges.filter(function(e) { return e.edge_type === 'inherits' || e.edge_type === 'implements'; });
            } else {
                syms = syms.filter(function(s) { return s.kind === 'method' || s.kind === 'constructor'; });
                edges = edges.filter(function(e) { return e.edge_type === 'calls'; });
                var conn = {}; edges.forEach(function(e) { conn[e.source_fq_name] = 1; conn[e.target_fq_name] = 1; });
                syms = syms.filter(function(s) { return conn[s.fq_name]; }).slice(0, 100);
                var fqs = {}; syms.forEach(function(s) { fqs[s.fq_name] = 1; });
                edges = edges.filter(function(e) { return fqs[e.source_fq_name] && fqs[e.target_fq_name]; });
            }
            GE.build(syms, edges);
            updGStats();
        }).catch(function(e) { toast(e.message, false); });
    }
    // Mermaid
    var mt = view === 'calls' ? 'class' : view;
    API.get(S.path() + '/diagram?diagram_type=' + mt).then(function(d) { _mermaid = d.mermaid || ''; }).catch(function() { _mermaid = ''; });
}
function updGStats() { $('gsn').textContent = GE.nodes.length; $('gse').textContent = GE.edges.length; }
function toggleMermaid() { $('mc').classList.toggle('hidden'); $('mcs').textContent = _mermaid || 'No source'; }

// =================== DEAD CODE ===================
function pgDead() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="loader"><span class="spin"></span> Analyzing...</div>');
    API.get(S.path() + '/dead-code').then(function(d) {
        var h = '<div class="page-head"><h1>Dead Code</h1><p>BFS from entry points</p></div>';
        h += '<div class="stat-row"><div class="stat-item"><div class="stat-num">' + d.total_symbols + '</div><div class="stat-txt">Total</div></div><div class="stat-item"><div class="stat-num" style="color:var(--green)">' + d.reachable_count + '</div><div class="stat-txt">Reachable</div></div><div class="stat-item"><div class="stat-num" style="color:var(--red)">' + d.unreachable_count + '</div><div class="stat-txt">Dead</div></div><div class="stat-item"><div class="stat-num">' + d.entry_point_count + '</div><div class="stat-txt">Entry Pts</div></div></div>';
        (d.unreachable_functions || []).forEach(function(f) { h += '<div class="finding"><div class="dot" style="background:var(--red)"></div><div style="flex:1"><div class="msg">' + esc(f.name) + '</div><div class="sub">' + esc(f.file_path) + ' : ' + f.start_line + '-' + f.end_line + '</div></div></div>'; });
        (d.unreachable_classes || []).forEach(function(c) { h += '<div class="finding"><div class="dot" style="background:var(--yellow)"></div><div style="flex:1"><div class="msg">' + esc(c.name) + '</div><div class="sub">' + esc(c.file_path) + '</div></div></div>'; });
        if (!d.unreachable_count) h += '<div class="card" style="text-align:center;padding:36px;color:var(--green)"><h3>All reachable!</h3></div>';
        html('main', h);
    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });
}

// =================== COUPLING ===================
function pgCoupling() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="loader"><span class="spin"></span></div>');
    API.get(S.path() + '/coupling').then(function(d) {
        var h = '<div class="page-head"><h1>Module Coupling</h1><p>Instability, abstractness, cohesion</p></div><div class="coup-grid">';
        (d.modules || []).forEach(function(m) {
            h += '<div class="coup-card"><h4>' + esc(m.name) + '</h4><div class="m"><span>Symbols</span><b>' + m.symbol_count + '</b></div><div class="m"><span>Ca</span><b>' + m.afferent_coupling + '</b></div><div class="m"><span>Ce</span><b>' + m.efferent_coupling + '</b></div><div class="m"><span>Instability</span><b style="color:' + (m.instability > 0.7 ? 'var(--red)' : 'var(--green)') + '">' + m.instability.toFixed(2) + '</b></div><div class="m"><span>Abstractness</span><b>' + m.abstractness.toFixed(2) + '</b></div><div class="m"><span>Cohesion</span><b style="color:' + (m.cohesion < 0.3 ? 'var(--red)' : 'var(--green)') + '">' + m.cohesion.toFixed(2) + '</b></div></div>';
        });
        h += '</div>';
        html('main', h);
    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });
}

// =================== ASK ===================
function pgAsk() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="page-head"><h1>Ask</h1><p>Natural language questions about the code</p></div><div class="card"><div class="chat-box" id="cb"></div><div class="row g-8"><input class="inp" id="ai" placeholder="What does this codebase do?" onkeydown="if(event.key===\'Enter\')sendQ()"><button class="btn btn-p" onclick="sendQ()">Ask</button></div></div>');
}
function sendQ() {
    var q = $('ai').value.trim(); if (!q) return;
    var cb = $('cb');
    cb.innerHTML += '<div class="bubble bubble-u">' + esc(q) + '</div>';
    $('ai').value = '';
    cb.innerHTML += '<div class="bubble bubble-b" id="al"><span class="spin"></span></div>';
    cb.scrollTop = cb.scrollHeight;
    API.post(S.path() + '/ask', { question: q }).then(function(d) {
        var el = $('al'); if (el) el.remove();
        var ans = d.answer_text || '<em>No LLM configured. Evidence below.</em>';
        var ev = '';
        if (d.evidence && d.evidence.length) { ev = '<br><strong style="font-size:10px;color:var(--text-3)">Evidence:</strong><ul style="font-size:11px;color:var(--text-3);padding-left:14px;margin-top:3px">'; d.evidence.slice(0, 4).forEach(function(e) { ev += '<li>' + esc(e.file_path) + '</li>'; }); ev += '</ul>'; }
        cb.innerHTML += '<div class="bubble bubble-b">' + ans + ev + '<br><span class="badge ' + (d.confidence === 'high' ? 'b-green' : d.confidence === 'medium' ? 'b-yellow' : 'b-red') + '" style="margin-top:6px">' + (d.confidence || 'low') + '</span></div>';
        cb.scrollTop = cb.scrollHeight;
    }).catch(function(e) { var el = $('al'); if (el) el.remove(); cb.innerHTML += '<div class="bubble bubble-b" style="color:var(--red)">' + esc(e.message) + '</div>'; });
}

// =================== REVIEW ===================
function pgReview() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="page-head"><h1>PR Review</h1><p>Paste a unified diff for risk analysis</p></div><div class="card"><div class="field"><label>Diff</label><textarea class="inp" id="rd" placeholder="--- a/file.py\n+++ b/file.py\n@@ ...\n-old\n+new"></textarea></div><button class="btn btn-p" onclick="doReview()">Analyze</button></div><div id="rr"></div>');
}
function doReview() {
    var diff = $('rd').value.trim(); if (!diff) { toast('Paste a diff', false); return; }
    html('rr', '<div class="loader"><span class="spin"></span></div>');
    API.post(S.path() + '/review', { diff: diff }).then(function(d) {
        var col = d.risk_level === 'high' || d.risk_level === 'critical' ? 'var(--red)' : d.risk_level === 'medium' ? 'var(--yellow)' : 'var(--green)';
        var h = '<div class="card"><div class="stat-row"><div class="stat-item"><div class="stat-num" style="color:' + col + '">' + d.risk_score + '</div><div class="stat-txt">Risk</div></div><div class="stat-item"><div class="stat-num" style="color:' + col + '">' + (d.risk_level || '-') + '</div><div class="stat-txt">Level</div></div><div class="stat-item"><div class="stat-num">' + ((d.findings || []).length) + '</div><div class="stat-txt">Findings</div></div></div>';
        (d.findings || []).forEach(function(f) { h += '<div class="finding"><div class="dot" style="background:var(--yellow)"></div><div style="flex:1"><div class="msg">' + esc(f.title || f.description) + '</div><div class="sub">' + esc(f.category || '') + ' &middot; ' + esc(f.file_path || '') + '</div></div></div>'; });
        h += '</div>';
        html('rr', h);
    }).catch(function(e) { html('rr', '<div class="empty"><p style="color:var(--red)">' + esc(e.message) + '</p></div>'); });
}

// =================== DOCS ===================
function pgDocs() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="page-head"><h1>Documentation</h1><p>Auto-generate from code graph</p></div><div class="row g-8" style="margin-bottom:16px"><button class="btn btn-p" onclick="genDocs()">Generate</button><button class="btn btn-g" onclick="loadDocs()">Load Existing</button></div><div id="dc"></div>');
}
function genDocs() { html('dc', '<div class="loader"><span class="spin"></span></div>'); API.post(S.path() + '/docs', {}).then(function(d) { showDocs(d.documents || []); }).catch(function(e) { html('dc', '<p style="color:var(--red)">' + esc(e.message) + '</p>'); }); }
function loadDocs() { html('dc', '<div class="loader"><span class="spin"></span></div>'); API.get(S.path() + '/docs').then(function(d) { showDocs(d.documents || d.items || []); }).catch(function(e) { html('dc', '<p style="color:var(--red)">' + esc(e.message) + '</p>'); }); }
function showDocs(docs) { if (!docs.length) { html('dc', '<div class="empty"><p>No docs. Generate first.</p></div>'); return; } var h = ''; docs.forEach(function(d) { h += '<div class="card"><div class="row between" style="margin-bottom:10px"><div class="card-hd" style="margin:0">' + esc(d.title || d.doc_type) + '</div><span class="badge b-blue">' + esc(d.doc_type) + '</span></div><div class="code">' + esc(d.markdown || '') + '</div></div>'; }); html('dc', h); }

// =================== SEARCH ===================
function pgSearch() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="page-head"><h1>Search</h1><p>Find symbols, summaries, docs</p></div><div class="card"><div class="row g-8" style="margin-bottom:12px"><input class="inp" id="si" placeholder="Type something..." style="flex:1" onkeydown="if(event.key===\'Enter\')doSearch()"><button class="btn btn-p" onclick="doSearch()">Search</button></div><div id="sr"></div></div>');
}
function doSearch() {
    var q = $('si').value.trim(); if (!q) return;
    html('sr', '<div class="loader"><span class="spin"></span></div>');
    API.get(S.path() + '/search?q=' + encodeURIComponent(q)).then(function(d) {
        var items = d.items || [];
        if (!items.length) { html('sr', '<p style="color:var(--text-3)">No results</p>'); return; }
        var h = '<p style="font-size:11px;color:var(--text-3);margin-bottom:10px">' + d.total + ' results</p>';
        items.slice(0, 30).forEach(function(it) {
            var tb = it.entity_type === 'symbol' ? 'b-blue' : it.entity_type === 'summary' ? 'b-green' : 'b-yellow';
            h += '<div class="finding"><div style="flex:1"><div class="msg"><strong>' + esc(it.title || it.entity_id) + '</strong></div><div class="sub">' + esc(it.snippet || '') + '</div></div><span class="badge ' + tb + '">' + it.entity_type + '</span></div>';
        });
        html('sr', h);
    }).catch(function(e) { html('sr', '<p style="color:var(--red)">' + esc(e.message) + '</p>'); });
}

// =================== EXPORTS ===================
function pgExports() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="page-head"><h1>Exports</h1><p>Download analysis in various formats</p></div><div class="export-grid"><div class="export-card" onclick="doExp(\'json\')"><div class="ico">{ }</div><h4>JSON</h4><p>Full analysis data</p></div><div class="export-card" onclick="doExp(\'portable\')"><div class="ico">\uD83D\uDCE6</div><h4>Portable .eidos</h4><p>Compact archive</p></div><div class="export-card" onclick="doExp(\'sarif\')"><div class="ico">\u26A0</div><h4>SARIF</h4><p>Code scanning format</p></div><div class="export-card" onclick="doExp(\'csv\')"><div class="ico">\uD83D\uDCCA</div><h4>CSV</h4><p>Spreadsheet data</p></div><div class="export-card" onclick="doExp(\'sbom\')"><div class="ico">\uD83D\uDCCB</div><h4>SBOM</h4><p>Bill of Materials</p></div><div class="export-card" onclick="doExp(\'md\')"><div class="ico">\uD83D\uDCDD</div><h4>Markdown</h4><p>Health report</p></div></div>');
}
function doExp(fmt) {
    var map = { json: ['/export', 'export.json'], portable: ['/portable', 'snapshot.eidos'], sarif: ['/export/sarif', 'results.sarif'], csv: ['/export/csv', 'data.zip'], sbom: ['/export/sbom', 'sbom.json'], md: ['/export/markdown', 'report.md'] };
    var m = map[fmt]; if (!m) return;
    API.download(S.path() + m[0], m[1]).then(function() { toast(m[1] + ' downloaded'); }).catch(function(e) { toast('Export failed: ' + e.message, false); });
}

// =================== SETTINGS ===================
function pgSettings() {
    html('main', '<div class="page-head"><h1>Settings</h1><p>Backend connection</p></div><div class="card"><div class="field"><label>API URL</label><input class="inp" id="su" value="' + esc(API.base) + '"></div><button class="btn btn-p" onclick="saveUrl()">Save & Test</button><div id="ss" class="mt"></div></div><div class="card"><div class="card-hd">Context</div><p style="font-size:13px;color:var(--text-2)">Repo: <b style="color:var(--text-0)">' + (S.repo || 'none') + '</b></p><p style="font-size:13px;color:var(--text-2)">Snap: <b style="color:var(--text-0)">' + (S.snap || 'none') + '</b></p><button class="btn btn-s btn-g mt" onclick="S.set(null,null);toast(\'Cleared\');pgSettings()">Clear</button></div>');
}
function saveUrl() {
    var u = $('su').value.trim(); if (!u) return;
    API.setBase(u);
    html('ss', '<span class="spin"></span>');
    API.get('/health').then(function(d) {
        if (d.status === 'ok') { html('ss', '<span class="conn-dot on" style="display:inline-block"></span> Connected'); toast('Connected'); checkConn(); }
        else html('ss', '<span class="conn-dot off" style="display:inline-block"></span> Unexpected');
    }).catch(function(e) { html('ss', '<span class="conn-dot off" style="display:inline-block"></span> ' + esc(e.message)); toast('Failed', false); });
}
