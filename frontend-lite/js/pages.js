// All page renderers and logic in one file for reliability
// Navigation + theme + connection
function navigate(pg) {
    document.querySelectorAll('.nav-btn').forEach(function(b) { b.classList.remove('active'); });
    var btn = document.querySelector('[data-p="' + pg + '"]');
    if (btn) btn.classList.add('active');
    var pages = { repos: pgRepos, overview: pgOverview, symbols: pgSymbols, health: pgHealth, graph: pgGraph, deadcode: pgDead, coupling: pgCoupling, deps: pgDeps, clones: pgClones, cycles: pgCycles, hotspots: pgHotspots, ask: pgAsk, review: pgReview, docs: pgDocs, search: pgSearch, exports: pgExports, settings: pgSettings };
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
        '<div class="card hidden" id="rf">' +
        '<div class="field"><label>Name</label><input class="inp" id="rn" placeholder="my-project"></div>' +
        '<div class="field"><label>Git URL</label><input class="inp" id="ru" placeholder="https://github.com/user/repo" onblur="fetchBranches()"></div>' +
        '<div class="field" id="rb-wrap" style="display:none"><label>Branch</label><div class="row g-8"><select class="inp" id="rb" style="flex:1"><option value="">default</option></select><button class="btn btn-s btn-g" onclick="fetchBranches()" title="Refresh branches">&#8635;</button></div><span id="rb-status" style="font-size:11px;color:var(--text-3)"></span></div>' +
        '<div class="row g-8"><button class="btn btn-p" onclick="addRepo()">Register & Ingest</button><button class="btn btn-g" onclick="toggleForm()">Cancel</button></div>' +
        '</div>' +
        '<div id="rl"><div class="loader"><span class="spin"></span> Loading...</div></div>');
    loadRepos();
}
function toggleForm() { $('rf').classList.toggle('hidden'); }
function fetchBranches() {
    var u = $('ru').value.trim();
    if (!u) { $('rb-wrap').style.display = 'none'; return; }
    var wrap = $('rb-wrap'), sel = $('rb'), status = $('rb-status');
    wrap.style.display = '';
    sel.innerHTML = '<option value="">loading...</option>';
    sel.disabled = true;
    status.textContent = 'Fetching branches...';
    API.post('/repos/branches', { url: u }).then(function(d) {
        var branches = d.branches || [];
        sel.disabled = false;
        if (!branches.length) {
            sel.innerHTML = '<option value="">default</option>';
            status.textContent = 'Could not detect branches — will use default';
        } else {
            var h = '';
            branches.forEach(function(b) {
                var selected = (b === 'main' || b === 'master') ? ' selected' : '';
                h += '<option value="' + esc(b) + '"' + selected + '>' + esc(b) + '</option>';
            });
            sel.innerHTML = h;
            status.textContent = branches.length + ' branch(es) found';
        }
    }).catch(function() {
        sel.disabled = false;
        sel.innerHTML = '<option value="">default</option>';
        status.textContent = 'Could not fetch branches';
    });
}
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
    var branch = $('rb') ? $('rb').value : '';
    var payload = { name: n, url: u };
    if (branch) payload.default_branch = branch;
    API.post('/repos', payload).then(function(r) { toast(r.name + ' registered'); toggleForm(); ingest(r.id); loadRepos(); }).catch(function(e) { toast(e.message, false); });
}
function ingest(id) {
    API.post('/repos/' + id + '/ingest').then(function(r) {
        showIngestBar(id, r.snapshot_id);
    }).catch(function(e) { toast(e.message, false); });
}
function showIngestBar(rid, sid) {
    // Insert progress overlay below the repos list
    var el = document.getElementById('rl');
    if (!el) return;
    el.innerHTML = '<div class="card" id="ingest-card" style="overflow:hidden;position:relative">' +
        '<div style="position:absolute;top:0;left:0;right:0;height:3px;background:var(--bg-3)"><div id="ig-bar" style="height:100%;width:0%;background:linear-gradient(90deg,var(--accent),var(--blue),var(--purple));transition:width 0.4s ease;border-radius:0 2px 2px 0"></div></div>' +
        '<div style="padding:20px 20px 16px">' +
        '<div class="row between" style="margin-bottom:12px"><div class="row g-8"><div class="ig-pulse"></div><span id="ig-title" style="font-weight:600;color:var(--text-0)">Starting ingestion...</span></div><span id="ig-pct" style="font-size:22px;font-weight:700;color:var(--accent)">0%</span></div>' +
        '<p id="ig-msg" style="font-size:12px;color:var(--text-2);margin-bottom:10px">Preparing...</p>' +
        '<div style="display:flex;gap:4px;margin-bottom:8px" id="ig-steps"></div>' +
        '<div class="row between" style="margin-top:8px"><span id="ig-time" style="font-size:11px;color:var(--text-3)">Elapsed: 0s</span><span id="ig-snap" style="font-size:11px;color:var(--text-3)">Snapshot: ' + sid.slice(0,8) + '</span></div>' +
        '</div></div>';
    var startTime = Date.now();
    pollIngest(rid, sid, startTime);
}
function pollIngest(rid, sid, startTime) {
    var steps = [
        {at:5, label:'Clone'}, {at:15, label:'Scan'}, {at:25, label:'Parse'},
        {at:50, label:'Graph'}, {at:65, label:'Blame'}, {at:70, label:'Index'},
        {at:90, label:'Finalize'}, {at:100, label:'Done'}
    ];
    function update() {
        API.get('/repos/' + rid + '/status').then(function(d) {
            var snap = (d.snapshots || []).filter(function(s) { return s.id === sid; })[0];
            if (!snap) { setTimeout(update, 2000); return; }
            var pct = snap.progress_percent || 0;
            var msg = snap.progress_message || 'Working...';
            var bar = document.getElementById('ig-bar');
            var pctEl = document.getElementById('ig-pct');
            var msgEl = document.getElementById('ig-msg');
            var titleEl = document.getElementById('ig-title');
            var timeEl = document.getElementById('ig-time');
            var stepsEl = document.getElementById('ig-steps');
            if (!bar) return; // page navigated away
            bar.style.width = pct + '%';
            pctEl.textContent = pct + '%';
            msgEl.textContent = msg;
            var elapsed = Math.round((Date.now() - startTime) / 1000);
            timeEl.textContent = 'Elapsed: ' + elapsed + 's';
            // Steps indicator
            var sh = '';
            for (var i = 0; i < steps.length; i++) {
                var s = steps[i], done = pct >= s.at;
                sh += '<div style="flex:1;text-align:center"><div style="height:4px;border-radius:2px;background:' + (done ? 'var(--accent)' : 'var(--bg-3)') + ';margin-bottom:3px"></div><span style="font-size:9px;color:' + (done ? 'var(--accent)' : 'var(--text-3)') + '">' + s.label + '</span></div>';
            }
            stepsEl.innerHTML = sh;
            if (snap.status === 'completed') {
                titleEl.textContent = 'Ingestion complete!';
                pctEl.style.color = 'var(--green)';
                bar.style.background = 'var(--green)';
                S.set(rid, sid);
                toast('Done! ' + (snap.file_count || '') + ' files indexed');
                setTimeout(function() { loadRepos(); }, 1500);
            } else if (snap.status === 'failed') {
                titleEl.textContent = 'Ingestion failed';
                pctEl.style.color = 'var(--red)';
                bar.style.background = 'var(--red)';
                msgEl.textContent = snap.error_message || 'Unknown error';
                toast('Ingestion failed', false);
            } else {
                titleEl.textContent = 'Analyzing codebase...';
                setTimeout(update, 1500);
            }
        }).catch(function() { setTimeout(update, 3000); });
    }
    setTimeout(update, 1000);
}
function poll(rid, sid) { showIngestBar(rid, sid); }
function selRepo(id) {
    API.get('/repos/' + id + '/status').then(function(d) {
        var done = (d.snapshots || []).filter(function(s) { return s.status === 'completed'; });
        if (!done.length) { toast('No completed snapshot', false); return; }
        S.set(id, done[done.length - 1].id);
        toast('Selected: ' + d.name);
        navigate('overview');
    }).catch(function(e) { toast(e.message, false); });
}
function delRepo(id) { if (!confirm('Delete?')) return; API.del('/repos/' + id).then(function() { if (S.repo === id) S.set(null, null); toast('Deleted'); loadRepos(); }).catch(function(e) { toast(e.message, false); }); }

// =================== OVERVIEW ===================
function pgOverview() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="loader"><span class="spin"></span> Loading...</div>');
    Promise.all([
        API.get(S.path() + '/overview'),
        API.get(S.path() + '/files?limit=5').catch(function() { return { items: [], total: 0 }; }),
        API.get(S.path() + '/health-score').catch(function() { return null; })
    ]).then(function(res) {
        var d = res[0], files = res[1], hs = res[2];
        var k = d.symbols_by_kind || {}, tot = 0;
        Object.keys(k).forEach(function(x) { tot += k[x]; });
        var h = '<div class="page-head"><h1>Overview</h1><p>Snapshot ' + S.snap.slice(0, 8) + '</p></div>';
        h += '<div class="stat-row"><div class="stat-item"><div class="stat-num">' + d.total_symbols + '</div><div class="stat-txt">Symbols</div></div><div class="stat-item"><div class="stat-num">' + d.total_edges + '</div><div class="stat-txt">Edges</div></div><div class="stat-item"><div class="stat-num">' + d.total_modules + '</div><div class="stat-txt">Modules</div></div><div class="stat-item"><div class="stat-num">' + (d.total_files || files.total || 0) + '</div><div class="stat-txt">Files</div></div><div class="stat-item"><div class="stat-num">' + (k['class'] || 0) + '</div><div class="stat-txt">Classes</div></div><div class="stat-item"><div class="stat-num">' + (k['method'] || 0) + '</div><div class="stat-txt">Methods</div></div></div>';
        if (hs && hs.score !== undefined) {
            var sc = hs.score, col = scoreCol(sc);
            h += '<div class="card"><div class="row between"><div class="card-hd" style="margin:0">Health Score</div><span style="font-size:28px;font-weight:700;color:' + col + '">' + sc.toFixed(1) + ' <span style="font-size:14px">' + grade(sc) + '</span></span></div></div>';
        }
        h += '<div class="card"><div class="card-hd">Distribution</div><table class="tbl"><thead><tr><th>Kind</th><th>Count</th><th style="width:45%"></th></tr></thead><tbody>';
        Object.keys(k).sort(function(a, b) { return k[b] - k[a]; }).forEach(function(kn) {
            var pct = tot ? (k[kn] / tot * 100).toFixed(1) : 0;
            h += '<tr><td><span class="badge ' + kindBadge(kn) + '">' + kn + '</span></td><td>' + k[kn] + '</td><td><div class="prog"><div class="prog-fill" style="width:' + pct + '%;background:var(--accent)"></div></div></td></tr>';
        });
        h += '</tbody></table></div>';
        // Snapshot management
        h += '<div class="card"><div class="card-hd">Snapshot Actions</div><div class="row g-8 flex-wrap"><button class="btn btn-s btn-g" onclick="viewSnapshots()">View All Snapshots</button><button class="btn btn-s btn-g" onclick="viewFiles()">Browse Files</button><button class="btn btn-s btn-d" onclick="delSnap()">Delete This Snapshot</button></div></div>';
        html('main', h);
    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });
}
function viewSnapshots() {
    API.get('/repos/' + S.repo + '/snapshots').then(function(d) {
        var snaps = d.items || d.snapshots || d || [];
        if (!Array.isArray(snaps)) snaps = [];
        var h = '<div class="page-head"><h1>Snapshots</h1><p>All snapshots for this repository</p></div>';
        h += '<div class="card" style="padding:0;overflow:hidden"><table class="tbl"><thead><tr><th>ID</th><th>Status</th><th>Files</th><th>Created</th><th></th></tr></thead><tbody>';
        snaps.forEach(function(s) {
            var col = s.status === 'completed' ? 'b-green' : s.status === 'failed' ? 'b-red' : 'b-yellow';
            h += '<tr><td style="font-family:monospace;font-size:11px">' + (s.id || '').slice(0, 8) + '</td><td><span class="badge ' + col + '">' + esc(s.status) + '</span></td><td>' + (s.file_count || 0) + '</td><td style="font-size:11px">' + (s.created_at ? new Date(s.created_at).toLocaleString() : '-') + '</td><td class="row g-8">';
            if (s.status === 'completed') h += '<button class="btn btn-s btn-p" onclick="S.set(\'' + S.repo + '\',\'' + s.id + '\');toast(\'Selected\');navigate(\'overview\')">Use</button>';
            h += '<button class="btn btn-s btn-d" onclick="delSnapById(\'' + s.id + '\')">Del</button></td></tr>';
        });
        h += '</tbody></table></div>';
        html('main', h);
    }).catch(function(e) { toast(e.message, false); });
}
function viewFiles() {
    API.get(S.path() + '/files?limit=200').then(function(d) {
        var files = d.items || [];
        var h = '<div class="page-head"><h1>Files</h1><p>' + (d.total || files.length) + ' files in snapshot</p></div>';
        h += '<div class="card" style="padding:0;overflow:hidden"><table class="tbl"><thead><tr><th>Path</th><th>Language</th><th>Lines</th></tr></thead><tbody>';
        files.forEach(function(f) {
            h += '<tr><td style="font-size:12px">' + esc(f.path || f.file_path || '') + '</td><td><span class="badge b-blue">' + esc(f.language || '-') + '</span></td><td>' + (f.line_count || 0) + '</td></tr>';
        });
        h += '</tbody></table></div>';
        html('main', h);
    }).catch(function(e) { toast(e.message, false); });
}
function delSnap() {
    if (!confirm('Delete current snapshot?')) return;
    API.del(S.path()).then(function() { S.set(S.repo, null); toast('Snapshot deleted'); navigate('repos'); }).catch(function(e) { toast(e.message, false); });
}
function delSnapById(sid) {
    if (!confirm('Delete snapshot ' + sid.slice(0, 8) + '?')) return;
    API.del('/repos/' + S.repo + '/snapshots/' + sid).then(function() {
        if (S.snap === sid) S.set(S.repo, null);
        toast('Deleted'); viewSnapshots();
    }).catch(function(e) { toast(e.message, false); });
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
        var h = '<table class="tbl"><thead><tr><th>Kind</th><th>Name</th><th>Namespace</th><th>File</th><th>Lines</th><th></th></tr></thead><tbody>';
        filtered.forEach(function(s, i) {
            h += '<tr><td><span class="badge ' + kindBadge(s.kind) + '">' + s.kind + '</span></td><td><strong>' + esc(s.name) + '</strong></td><td style="font-size:11px;color:var(--text-3)">' + esc(s.namespace) + '</td><td style="font-size:11px">' + esc((s.file_path || '').split('/').pop()) + '</td><td>' + s.start_line + '-' + s.end_line + '</td>';
            h += '<td class="row g-4"><button class="btn btn-s btn-g sym-code-btn" onclick="viewSymCode(\'' + esc(s.fq_name).replace(/'/g, "\\'") + '\',' + i + ')" title="View source code">&#128196;</button><button class="btn btn-s btn-g sym-code-btn" onclick="viewSymCallers(\'' + esc(s.fq_name).replace(/'/g, "\\'") + '\',' + i + ')" title="View callers">&#128279;</button></td></tr>';
            h += '<tr class="sym-code-row hidden" id="scr-' + i + '"><td colspan="6"><div class="sym-code-block"><pre><code id="scc-' + i + '"></code></pre></div></td></tr>';
        });
        h += '</tbody></table>';
        html('st', h);
    }).catch(function(e) { html('st', '<p style="color:var(--red)">' + esc(e.message) + '</p>'); });
}
function viewSymCode(fq, idx) {
    var row = document.getElementById('scr-' + idx);
    var code = document.getElementById('scc-' + idx);
    if (!row) return;
    if (!row.classList.contains('hidden')) { row.classList.add('hidden'); return; }
    code.textContent = 'Loading...';
    row.classList.remove('hidden');
    API.get(S.path() + '/symbols/' + encodeURIComponent(fq)).then(function(sym) {
        if (sym.source_code) {
            code.textContent = sym.source_code;
        } else {
            code.textContent = '// No source code stored for this symbol';
        }
    }).catch(function(e) {
        code.textContent = '// Error: ' + e.message;
    });
}
function viewSymCallers(fq, idx) {
    var row = document.getElementById('scr-' + idx);
    var code = document.getElementById('scc-' + idx);
    if (!row) return;
    if (!row.classList.contains('hidden')) { row.classList.add('hidden'); return; }
    code.textContent = 'Loading callers...';
    row.classList.remove('hidden');
    API.get(S.path() + '/symbols/' + encodeURIComponent(fq) + '/callers').then(function(d) {
        var callers = d.callers || d.items || [];
        if (!callers.length) { code.textContent = '// No callers found for ' + fq; return; }
        var txt = '// Callers of ' + fq + ':\n';
        callers.forEach(function(c) { txt += '\n  ' + (c.fq_name || c.name || c) + '  (' + (c.file_path || '') + ':' + (c.start_line || '') + ')'; });
        code.textContent = txt;
    }).catch(function(e) {
        code.textContent = '// Error: ' + e.message;
    });
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
        '<div class="g-bar"><button class="btn btn-s btn-p" data-gv="class" onclick="gLoad(\'class\')">Classes</button><button class="btn btn-s btn-g" data-gv="all" onclick="gLoad(\'all\')">All</button><button class="btn btn-s btn-g" data-gv="module" onclick="gLoad(\'module\')">Modules</button><button class="btn btn-s btn-g" data-gv="calls" onclick="gLoad(\'calls\')">Calls</button><div class="sep"></div><button class="btn btn-s btn-g" onclick="GE.fitAll()">Fit</button><button class="btn btn-s btn-g" onclick="GE.exportPNG();toast(\'PNG saved\')">PNG</button><button class="btn btn-s btn-g" onclick="toggleMermaid()">Mermaid</button></div>' +
        '<div class="graph-area" id="ga"><canvas id="gc"></canvas>' +
        '<div class="g-ctrl"><button onclick="GE.sc*=1.2;GE.paint()">+</button><button onclick="GE.sc*=0.8;GE.paint()">&minus;</button><button onclick="GE.fitAll()">\u2922</button></div>' +
        '<div class="g-legend"><h6>Nodes</h6><div class="lr"><div class="ld" style="background:#2563eb"></div>Class</div><div class="lr"><div class="ld" style="background:#7c3aed"></div>Interface</div><div class="lr"><div class="ld" style="background:#16a34a"></div>Method</div><div class="lr"><div class="ld" style="background:#dc2626"></div>Enum</div><h6>Edges</h6><div class="lr"><div class="ll" style="background:#6246ea"></div>Calls</div><div class="lr"><div class="ll" style="background:#ca8a04"></div>Inherits</div><div class="lr"><div class="ll" style="background:#7c3aed"></div>Implements</div><div class="lr"><div class="ll" style="background:#2563eb"></div>Uses</div></div>' +
        '<div class="g-info" id="gi"><span class="x" onclick="$(\'gi\').classList.remove(\'show\');$(\'gic\').classList.add(\'hidden\')">&times;</span><h4 id="gin"></h4><div class="ir"><b>Kind:</b> <span id="gik"></span></div><div class="ir"><b>File:</b> <span id="gif"></span></div><div class="ir"><b>Lines:</b> <span id="gil"></span></div><div class="ir"><b>Edges:</b> <span id="gie"></span></div><button class="btn btn-s btn-p gi-code-btn" id="gib" onclick="showNodeCode()">&#9654; View Code</button><div class="gi-code hidden" id="gic"><pre><code id="gics"></code></pre></div></div>' +
        '<div class="g-stats"><span id="gsn">0</span> nodes &middot; <span id="gse">0</span> edges</div></div>' +
        '<div class="card hidden" id="mc" style="margin-top:14px"><div class="row between"><div class="card-hd" style="margin:0">Mermaid Source</div><button class="btn btn-s btn-g" onclick="navigator.clipboard.writeText(_mermaid);toast(\'Copied\')">Copy</button></div><div class="code" id="mcs"></div></div>');
    GE.init($('gc'));
    GE.onSelect = function(n) { $('gi').classList.add('show'); $('gin').textContent = n.name; $('gik').textContent = n.kind; $('gif').textContent = n.file || '-'; $('gil').textContent = n.sl ? n.sl + '-' + n.el : '-'; $('gie').textContent = GE.edges.filter(function(e) { return e.srcId === n.id || e.tgtId === n.id; }).length; window._selNodeFq = n.id; $('gic').classList.add('hidden'); $('gics').textContent = ''; };
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
                // Show all classes/interfaces/enums with their inheritance + composition + uses edges
                syms = syms.filter(function(s) { return s.kind === 'class' || s.kind === 'interface' || s.kind === 'enum'; });
                edges = edges.filter(function(e) { return e.edge_type === 'inherits' || e.edge_type === 'implements' || e.edge_type === 'uses'; });
            } else if (view === 'calls') {
                syms = syms.filter(function(s) { return s.kind === 'method' || s.kind === 'constructor'; });
                edges = edges.filter(function(e) { return e.edge_type === 'calls'; });
                var conn = {}; edges.forEach(function(e) { conn[e.source_fq_name] = 1; conn[e.target_fq_name] = 1; });
                syms = syms.filter(function(s) { return conn[s.fq_name]; }).slice(0, 120);
                var fqs = {}; syms.forEach(function(s) { fqs[s.fq_name] = 1; });
                edges = edges.filter(function(e) { return fqs[e.source_fq_name] && fqs[e.target_fq_name]; });
            } else {
                // 'all' view: everything
            }
            // If no symbols match the filter, show all
            if (syms.length === 0) { syms = res[0].items || []; }
            GE.build(syms, edges);
            updGStats();
        }).catch(function(e) { toast(e.message, false); });
    }
    // Mermaid
    var mt = view === 'calls' ? 'class' : view;
    API.get(S.path() + '/diagram?diagram_type=' + mt).then(function(d) { _mermaid = d.mermaid || ''; }).catch(function() { _mermaid = ''; });
}
function updGStats() { $('gsn').textContent = GE.flatNodes.length; $('gse').textContent = GE.edges.length; }
function showNodeCode() {
    var fq = window._selNodeFq;
    if (!fq || !S.ok()) { toast('No symbol selected', false); return; }
    var viewer = $('gic'), pre = $('gics'), btn = $('gib');
    if (!viewer.classList.contains('hidden')) { viewer.classList.add('hidden'); return; }
    btn.textContent = '\u23F3 Loading...';
    API.get(S.path() + '/symbols/' + encodeURIComponent(fq)).then(function(sym) {
        btn.textContent = '\u25B6 View Code';
        if (sym.source_code) {
            pre.textContent = sym.source_code;
            viewer.classList.remove('hidden');
        } else {
            toast('No source code stored for this symbol', false);
        }
    }).catch(function(e) {
        btn.textContent = '\u25B6 View Code';
        toast('Failed to load code: ' + e.message, false);
    });
}
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

// =================== DEPENDENCIES ===================
function pgDeps() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="loader"><span class="spin"></span></div>');
    API.get(S.path() + '/dependencies').then(function(d) {
        var deps = d.dependencies || d.items || [];
        var h = '<div class="page-head"><h1>Dependencies</h1><p>External and internal dependencies detected from manifest files</p></div>';
        if (!deps.length) { h += '<div class="card" style="text-align:center;padding:30px;color:var(--text-3)">No dependencies detected</div>'; }
        else {
            var ecosystems = {};
            deps.forEach(function(dep) { var e = dep.ecosystem || 'unknown'; ecosystems[e] = (ecosystems[e] || 0) + 1; });
            h += '<div class="stat-row"><div class="stat-item"><div class="stat-num">' + deps.length + '</div><div class="stat-txt">Total Deps</div></div>';
            Object.keys(ecosystems).forEach(function(e) { h += '<div class="stat-item"><div class="stat-num">' + ecosystems[e] + '</div><div class="stat-txt">' + esc(e) + '</div></div>'; });
            h += '</div>';
            h += '<div class="card" style="padding:0;overflow:hidden"><table class="tbl"><thead><tr><th>Name</th><th>Version</th><th>Ecosystem</th><th>Dev?</th><th>Source File</th></tr></thead><tbody>';
            deps.forEach(function(dep) {
                var pinned = dep.is_pinned ? 'var(--green)' : 'var(--text-3)';
                h += '<tr><td><strong>' + esc(dep.name || '') + '</strong></td><td style="font-size:12px;color:' + pinned + '">' + esc(dep.version || '*') + '</td><td><span class="badge b-blue">' + esc(dep.ecosystem || '-') + '</span></td><td>' + (dep.is_dev ? '<span class="badge b-yellow">dev</span>' : '') + '</td><td style="font-size:11px;color:var(--text-3)">' + esc(dep.file_path || '') + '</td></tr>';
            });
            h += '</tbody></table></div>';
        }
        html('main', h);
    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });
}

// =================== CLONES ===================
function pgClones() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="loader"><span class="spin"></span> Detecting code clones...</div>');
    API.get(S.path() + '/clones').then(function(d) {
        var clones = d.clone_groups || d.clones || [];
        var h = '<div class="page-head"><h1>Clone Detection</h1><p>AST fingerprint-based duplicate detection</p></div>';
        h += '<div class="stat-row"><div class="stat-item"><div class="stat-num">' + clones.length + '</div><div class="stat-txt">Clone Groups</div></div><div class="stat-item"><div class="stat-num">' + (d.total_duplicated_lines || 0) + '</div><div class="stat-txt">Duplicated Lines</div></div><div class="stat-item"><div class="stat-num">' + ((d.duplication_percentage || 0).toFixed ? (d.duplication_percentage || 0).toFixed(1) : (d.duplication_percentage || 0)) + '%</div><div class="stat-txt">Duplication</div></div></div>';
        if (!clones.length) { h += '<div class="card" style="text-align:center;padding:30px;color:var(--green)"><h3>No clones detected!</h3></div>'; }
        else {
            clones.slice(0, 30).forEach(function(g, i) {
                var instances = g.instances || g.fragments || [];
                h += '<div class="card"><div class="card-hd">Clone Group ' + (i + 1) + ' <span class="badge b-yellow">' + instances.length + ' instances</span> <span style="font-size:11px;color:var(--text-3)">' + (g.lines || g.line_count || '?') + ' lines</span></div>';
                instances.forEach(function(inst) {
                    h += '<div class="finding"><div class="dot" style="background:var(--yellow)"></div><div style="flex:1"><div class="msg">' + esc(inst.file_path || inst.file || '') + '</div><div class="sub">Lines ' + (inst.start_line || '') + '-' + (inst.end_line || '') + '</div></div></div>';
                });
                h += '</div>';
            });
        }
        html('main', h);
    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });
}

// =================== CALL CYCLES ===================
function pgCycles() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="loader"><span class="spin"></span> Detecting call cycles (Tarjan SCC)...</div>');
    API.get(S.path() + '/call-cycles').then(function(d) {
        var cycles = d.cycles || d.sccs || [];
        var h = '<div class="page-head"><h1>Call Cycles</h1><p>Strongly connected components in the call graph</p></div>';
        h += '<div class="stat-row"><div class="stat-item"><div class="stat-num">' + cycles.length + '</div><div class="stat-txt">Cycles Found</div></div><div class="stat-item"><div class="stat-num">' + (d.total_functions_in_cycles || 0) + '</div><div class="stat-txt">Functions in Cycles</div></div></div>';
        if (!cycles.length) { h += '<div class="card" style="text-align:center;padding:30px;color:var(--green)"><h3>No call cycles!</h3></div>'; }
        else {
            cycles.slice(0, 25).forEach(function(c, i) {
                var members = c.members || c.nodes || c;
                if (!Array.isArray(members)) members = [];
                h += '<div class="card"><div class="card-hd">Cycle ' + (i + 1) + ' <span class="badge b-red">' + members.length + ' functions</span></div><div style="display:flex;flex-wrap:wrap;gap:6px">';
                members.forEach(function(m) { h += '<span class="badge b-muted" style="font-size:11px">' + esc(typeof m === 'string' ? m.split('.').pop() : (m.name || '')) + '</span>'; });
                h += '</div></div>';
            });
        }
        html('main', h);
    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });
}

// =================== HOTSPOTS ===================
function pgHotspots() {
    if (!S.ok()) { html('main', noSnap()); return; }
    html('main', '<div class="loader"><span class="spin"></span> Loading hotspots &amp; contributors...</div>');
    Promise.all([
        API.get(S.path() + '/hotspots').catch(function() { return { items: [] }; }),
        API.get(S.path() + '/contributors').catch(function() { return { contributors: [] }; })
    ]).then(function(res) {
        var hotspots = res[0].hotspots || res[0].items || [];
        var contribs = res[1].contributors || res[1].items || [];
        var h = '<div class="page-head"><h1>Hotspots &amp; Contributors</h1><p>Churn × complexity hotspots and git blame analysis</p></div>';
        // Contributors
        h += '<div class="card"><div class="card-hd">Contributors (' + (res[1].total_authors || contribs.length) + ' authors)</div>';
        if (!contribs.length) { h += '<p style="color:var(--text-3)">No contributor data (requires git blame during ingestion)</p>'; }
        else {
            h += '<table class="tbl"><thead><tr><th>Author</th><th>Lines</th><th>Symbols</th><th>Functions</th><th>Files</th><th>Modules</th></tr></thead><tbody>';
            contribs.forEach(function(c) {
                h += '<tr><td><strong>' + esc(c.author || c.name || '') + '</strong></td><td><strong>' + (c.line_count || 0) + '</strong></td><td>' + (c.symbol_count || 0) + '</td><td>' + (c.function_count || 0) + '</td><td>' + (c.file_count || 0) + '</td><td style="font-size:11px;color:var(--text-3)">' + (c.modules || []).slice(0, 3).join(', ') + (c.modules && c.modules.length > 3 ? ' +' + (c.modules.length - 3) : '') + '</td></tr>';
            });
            h += '</tbody></table>';
        }
        h += '</div>';
        // Hotspots
        h += '<div class="card"><div class="card-hd">Hotspots (Churn × Complexity)</div>';
        if (!hotspots.length) { h += '<p style="color:var(--text-3)">No hotspot data</p>'; }
        else {
            h += '<table class="tbl"><thead><tr><th>Symbol</th><th>File</th><th>Risk</th><th>Complexity</th><th>Commits</th><th>Authors</th></tr></thead><tbody>';
            hotspots.slice(0, 30).forEach(function(hs) {
                var risk = hs.risk_score || 0;
                h += '<tr><td><strong>' + esc(hs.name || hs.fq_name || '') + '</strong></td><td style="font-size:11px">' + esc((hs.file_path || '').split('/').pop()) + '</td><td><span style="color:' + (risk > 10 ? 'var(--red)' : risk > 5 ? 'var(--yellow)' : 'var(--green)') + ';font-weight:600">' + risk.toFixed(1) + '</span></td><td>' + (hs.cyclomatic_complexity || 0) + '</td><td>' + (hs.commit_count || 0) + '</td><td>' + (hs.author_count || 0) + '</td></tr>';
            });
            h += '</tbody></table>';
        }
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
    html('main', '<div class="page-head"><h1>Settings</h1><p>Configure connection, AI, auth, and system</p></div>' +
        '<div class="card"><div class="card-hd">API Connection</div><div class="field"><label>Backend URL</label><input class="inp" id="su" value="' + esc(API.base) + '"></div><div class="row g-8"><button class="btn btn-p" onclick="saveUrl()">Save & Test</button></div><div id="ss" class="mt"></div></div>' +
        '<div class="card"><div class="card-hd">Active Context</div><p style="font-size:13px;color:var(--text-2)">Repo: <b style="color:var(--text-0)">' + (S.repo || 'none') + '</b></p><p style="font-size:13px;color:var(--text-2)">Snap: <b style="color:var(--text-0)">' + (S.snap || 'none') + '</b></p><button class="btn btn-s btn-g mt" onclick="S.set(null,null);toast(\'Cleared\');pgSettings()">Clear Selection</button></div>' +
        '<div id="cfg"><div class="loader"><span class="spin"></span> Loading configuration...</div></div>');
    loadCfg();
}
function loadCfg() {
    API.get('/settings').then(function(d) {
        var h = '';
        h += cfgSection('LLM / AI Provider', 'llm', [
            {k:'llm_base_url', l:'Base URL', t:'text', v:d.llm.llm_base_url, ph:'https://api.openai.com/v1'},
            {k:'llm_api_key', l:'API Key', t:'password', v:d.llm.llm_api_key, ph:'sk-...'},
            {k:'openai_api_key', l:'OpenAI Key (legacy)', t:'password', v:d.llm.openai_api_key, ph:'sk-...'},
            {k:'llm_model', l:'Model', t:'text', v:d.llm.llm_model, ph:'gpt-4o-mini'},
            {k:'llm_temperature', l:'Temperature', t:'number', v:d.llm.llm_temperature, ph:'0.1'},
            {k:'llm_max_tokens', l:'Max Tokens', t:'number', v:d.llm.llm_max_tokens, ph:'2048'},
            {k:'llm_timeout', l:'Timeout (s)', t:'number', v:d.llm.llm_timeout, ph:'60'}
        ]);
        h += cfgSection('Authentication', 'auth', [
            {k:'auth_enabled', l:'Enabled', t:'bool', v:d.auth.auth_enabled},
            {k:'secret_key', l:'JWT Secret', t:'password', v:d.auth.secret_key, ph:'32+ chars'},
            {k:'jwt_expire_seconds', l:'Token Expiry (s)', t:'number', v:d.auth.jwt_expire_seconds, ph:'86400'},
            {k:'github_client_id', l:'GitHub Client ID', t:'text', v:d.auth.github_client_id, ph:''},
            {k:'github_client_secret', l:'GitHub Client Secret', t:'password', v:d.auth.github_client_secret, ph:''},
            {k:'github_redirect_uri', l:'GitHub Redirect URI', t:'text', v:d.auth.github_redirect_uri, ph:'http://localhost:8000/auth/callback'},
            {k:'google_client_id', l:'Google Client ID', t:'text', v:d.auth.google_client_id, ph:''},
            {k:'google_client_secret', l:'Google Client Secret', t:'password', v:d.auth.google_client_secret, ph:''},
            {k:'google_redirect_uri', l:'Google Redirect URI', t:'text', v:d.auth.google_redirect_uri, ph:''},
            {k:'superadmin_email', l:'Superadmin Email', t:'text', v:d.auth.superadmin_email, ph:'admin@example.com'}
        ]);
        h += cfgSection('Infrastructure', 'infra', [
            {k:'qdrant_url', l:'Qdrant URL', t:'text', v:d.connection.qdrant_url, ph:'http://localhost:6333'},
            {k:'redis_url', l:'Redis URL', t:'text', v:d.connection.redis_url, ph:'redis://localhost:6379/0'},
            {k:'repos_data_dir', l:'Repos Data Dir', t:'text', v:d.connection.repos_data_dir, ph:'/data/repos'}
        ]);
        h += cfgSection('Rate Limiting', 'rate', [
            {k:'rate_limit_enabled', l:'Enabled', t:'bool', v:d.limits.rate_limit_enabled},
            {k:'rate_limit_per_second', l:'Requests/sec', t:'number', v:d.limits.rate_limit_per_second, ph:'10'},
            {k:'rate_limit_burst', l:'Burst', t:'number', v:d.limits.rate_limit_burst, ph:'500'}
        ]);
        h += cfgSection('System', 'sys', [
            {k:'delete_clones_after_indexing', l:'Delete Clones After Indexing', t:'bool', v:d.system.delete_clones_after_indexing},
            {k:'db_echo', l:'DB Echo (SQL logging)', t:'bool', v:d.system.db_echo},
            {k:'webhook_secret', l:'Webhook Secret', t:'password', v:d.webhooks.webhook_secret, ph:''}
        ]);
        h += '<div class="card" style="background:var(--bg-2)"><div class="card-hd">Read-Only Info</div>';
        h += '<div class="row g-12" style="flex-wrap:wrap">';
        h += '<div class="stat-item" style="flex:1;min-width:120px"><div class="stat-num" style="font-size:16px">' + esc(d.system.version) + '</div><div class="stat-txt">Version</div></div>';
        h += '<div class="stat-item" style="flex:1;min-width:120px"><div class="stat-num" style="font-size:16px">' + esc(d.system.edition) + '</div><div class="stat-txt">Edition</div></div>';
        h += '<div class="stat-item" style="flex:1;min-width:120px"><div class="stat-num" style="font-size:16px">' + (d.system.demo_mode ? 'Yes' : 'No') + '</div><div class="stat-txt">Demo Mode</div></div>';
        h += '<div class="stat-item" style="flex:1;min-width:120px"><div class="stat-num" style="font-size:14px;word-break:break-all">' + esc(d.connection.database_url) + '</div><div class="stat-txt">Database</div></div>';
        h += '</div></div>';
        html('cfg', h);
    }).catch(function(e) {
        html('cfg', '<div class="card"><p style="color:var(--red)">Could not load settings: ' + esc(e.message) + '</p></div>');
    });
}
function cfgSection(title, id, fields) {
    var h = '<div class="card"><div class="card-hd">' + title + '</div><div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:10px">';
    for (var i = 0; i < fields.length; i++) {
        var f = fields[i];
        if (f.t === 'bool') {
            h += '<div class="field"><label>' + f.l + '</label><select class="inp" data-cfg="' + f.k + '"><option value="true"' + (f.v ? ' selected' : '') + '>Enabled</option><option value="false"' + (!f.v ? ' selected' : '') + '>Disabled</option></select></div>';
        } else {
            h += '<div class="field"><label>' + f.l + '</label><input class="inp" type="' + f.t + '" data-cfg="' + f.k + '" value="' + esc(String(f.v || '')) + '" placeholder="' + esc(f.ph || '') + '"' + (f.t === 'number' ? ' step="any"' : '') + '></div>';
        }
    }
    h += '</div><button class="btn btn-s btn-p mt" onclick="saveCfg(this)">Save ' + title + '</button></div>';
    return h;
}
function saveCfg(btn) {
    var card = btn.closest('.card');
    var inputs = card.querySelectorAll('[data-cfg]');
    var body = {};
    inputs.forEach(function(el) {
        var k = el.getAttribute('data-cfg'), v = el.value;
        if (el.type === 'number') v = parseFloat(v);
        else if (el.tagName === 'SELECT') v = v === 'true';
        if (v !== '' && v !== null) body[k] = v;
    });
    API.patch('/settings', body).then(function(d) { toast(d.count + ' setting(s) saved'); }).catch(function(e) { toast(e.message, false); });
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
