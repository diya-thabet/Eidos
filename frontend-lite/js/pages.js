// All page renderers and logic in one file for reliability

// Navigation + theme + connection

function navigate(pg) {

    // Phase 6: Remove graph keyboard handler when leaving graph page
    if (window._graphKeyHandler) {
        document.removeEventListener('keydown', window._graphKeyHandler);
        window._graphKeyHandler = null;
    }

    // Phase 8: Performance mark
    Perf.mark('page.render');

    // Restore sidebar/statusbar for non-login pages
    if (pg !== 'login') _restoreAppChrome();

    // Apply permission-based visibility to nav items
    if (pg !== 'login') applyPermissions();

    document.querySelectorAll('.nav-btn').forEach(function(b) { b.classList.remove('active'); });

    var btn = document.querySelector('[data-p="' + pg + '"]');

    if (btn) btn.classList.add('active');

    var main = document.getElementById('main');

    // Phase 8: Announce page change for screen readers
    announce('Navigated to ' + pg);

    // Smooth page exit then render

    main.style.opacity = '0';

    main.style.transform = 'translateY(4px)';

    setTimeout(function() {

        var pages = { login: pgLogin, repos: pgRepos, overview: pgOverview, symbols: pgSymbols, health: pgHealth, graph: pgGraph, deadcode: pgDead, coupling: pgCoupling, deps: pgDeps, clones: pgClones, cycles: pgCycles, hotspots: pgHotspots, ask: pgAsk, review: pgReview, docs: pgDocs, search: pgSearch, exports: pgExports, admin: pgAdmin, settings: pgSettings };

        if (pages[pg]) pages[pg]();

        main.style.opacity = '';

        main.style.transform = '';

        // Phase 8: Measure page render time
        Perf.measure('page.render');

        // Phase 8: Save last visited page
        Prefs.set('lastPage', pg);

        // Phase 9: Update deep link URL and close mobile nav
        if (typeof DeepLink !== 'undefined') DeepLink.push();
        var sidebar = document.querySelector('.sidebar');
        if (sidebar) sidebar.classList.remove('mobile-open');

    }, 60);

}



function toggleTheme() {

    var el = document.documentElement;

    var current = el.getAttribute('data-theme');

    var next = current === 'dark' ? 'light' : 'dark';

    el.setAttribute('data-theme', next);

    localStorage.setItem('eidos_theme', next);

    var btn = document.getElementById('theme-btn');

    btn.textContent = next === 'dark' ? '\u2600' : '\u263D';

    btn.style.transform = 'rotate(180deg) scale(0.85)';

    setTimeout(function() { btn.style.transform = ''; }, 220);

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



// =================== LOGIN ===================

function pgLogin() {
    // If auth is not enabled, skip login
    if (!Auth.isAuthEnabled()) {
        navigate('repos');
        return;
    }

    // If already logged in, go to repos
    if (Auth.isLoggedIn() && !Auth.isTokenExpired()) {
        navigate('repos');
        return;
    }

    // Hide sidebar in login view
    var sidebar = document.querySelector('.sidebar');
    if (sidebar) sidebar.style.display = 'none';
    var statusBar = document.querySelector('.status-bar');
    if (statusBar) statusBar.style.display = 'none';

    var h = '<div class="login-page">';
    h += '<div class="login-card">';
    h += '<div class="login-logo"><img src="images/logo-64.png" alt="Eidos" class="login-logo-img"></div>';
    h += '<h1 class="login-title">Welcome to Eidos</h1>';
    h += '<p class="login-subtitle">Code intelligence platform — sign in to continue</p>';

    // Local email/password form
    h += '<div class="login-form" id="login-form">';
    h += '<div class="login-tabs"><button class="login-tab active" id="tab-signin" onclick="_loginTab(\'signin\')">Sign In</button><button class="login-tab" id="tab-signup" onclick="_loginTab(\'signup\')">Sign Up</button></div>';
    h += '<div id="login-fields">';
    h += '<div class="field" id="signup-name-field" style="display:none"><label>Name</label><input class="inp" id="auth-name" placeholder="Your name" autocomplete="name"></div>';
    h += '<div class="field"><label>Email</label><input class="inp" id="auth-email" type="email" placeholder="you@example.com" autocomplete="email"></div>';
    h += '<div class="field"><label>Password</label><input class="inp" id="auth-pass" type="password" placeholder="Min. 6 characters" autocomplete="current-password"></div>';
    h += '<div id="auth-error" class="login-error"></div>';
    h += '<button class="btn btn-p" style="width:100%" id="auth-submit" onclick="_doLocalAuth()">Sign In</button>';
    h += '</div>';
    h += '</div>';

    h += '<div class="login-divider"><span>or continue with</span></div>';

    // OAuth buttons
    h += '<div class="login-buttons">';
    h += '<a href="' + Auth.getGitHubLoginUrl() + '" class="login-btn login-btn-github"><svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg> GitHub</a>';
    h += '<a href="' + Auth.getGoogleLoginUrl() + '" class="login-btn login-btn-google"><svg viewBox="0 0 24 24" width="20" height="20"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg> Google</a>';
    h += '</div>';

    h += '<div class="login-divider"><span>or</span></div>';
    h += '<div class="login-demo">';
    h += '<button class="btn btn-s btn-g" onclick="Auth.setAuthEnabled(false);Auth.setUser({id:\'anonymous\',name:\'Anonymous\',role:\'superadmin\',github_login:\'anonymous\',avatar_url:\'\'});_restoreAppChrome();navigate(\'repos\')">Continue in Demo Mode</button>';
    h += '<p class="login-demo-note">Demo mode has full access without authentication</p>';
    h += '</div>';
    h += '</div>';
    h += '</div>';

    html('main', h);

    // Enter key handler
    setTimeout(function() {
        var passInput = document.getElementById('auth-pass');
        if (passInput) passInput.addEventListener('keydown', function(e) { if (e.key === 'Enter') _doLocalAuth(); });
    }, 100);
}

var _loginMode = 'signin';

function _loginTab(mode) {
    _loginMode = mode;
    var tabSignin = document.getElementById('tab-signin');
    var tabSignup = document.getElementById('tab-signup');
    var nameField = document.getElementById('signup-name-field');
    var submitBtn = document.getElementById('auth-submit');
    var errEl = document.getElementById('auth-error');
    if (errEl) errEl.textContent = '';

    if (mode === 'signup') {
        if (tabSignin) tabSignin.classList.remove('active');
        if (tabSignup) tabSignup.classList.add('active');
        if (nameField) nameField.style.display = '';
        if (submitBtn) submitBtn.textContent = 'Create Account';
    } else {
        if (tabSignin) tabSignin.classList.add('active');
        if (tabSignup) tabSignup.classList.remove('active');
        if (nameField) nameField.style.display = 'none';
        if (submitBtn) submitBtn.textContent = 'Sign In';
    }
}

function _doLocalAuth() {
    var email = (document.getElementById('auth-email') || {}).value || '';
    var pass = (document.getElementById('auth-pass') || {}).value || '';
    var name = (document.getElementById('auth-name') || {}).value || '';
    var errEl = document.getElementById('auth-error');
    var submitBtn = document.getElementById('auth-submit');

    if (!email || !pass) {
        if (errEl) errEl.textContent = 'Please enter email and password.';
        return;
    }
    if (pass.length < 6) {
        if (errEl) errEl.textContent = 'Password must be at least 6 characters.';
        return;
    }

    if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = 'Please wait...'; }
    if (errEl) errEl.textContent = '';

    var endpoint = _loginMode === 'signup' ? '/auth/signup' : '/auth/login';
    var body = { email: email, password: pass };
    if (_loginMode === 'signup' && name) body.name = name;

    fetch(API.base + endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    }).then(function(r) {
        var status = r.status;
        return r.text().then(function(text) {
            var data = {};
            try { data = JSON.parse(text); } catch(e) {}
            return { status: status, data: data };
        });
    }).then(function(res) {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = _loginMode === 'signup' ? 'Create Account' : 'Sign In'; }

        if (res.status === 200 && res.data.access_token) {
            Auth.setToken(res.data.access_token);
            Auth.setUser(res.data.user);
            toast('Welcome, ' + (res.data.user.name || res.data.user.email));
            _restoreAppChrome();
            navigate('repos');
        } else {
            var msg = res.data.detail || (res.status >= 500 ? 'Server error (' + res.status + '). Please try again.' : 'Authentication failed');
            if (errEl) errEl.textContent = msg;
        }
    }).catch(function(e) {
        if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = _loginMode === 'signup' ? 'Create Account' : 'Sign In'; }
        if (errEl) errEl.textContent = 'Connection error. Is the backend running?';
    });
}

function _restoreAppChrome() {
    var sidebar = document.querySelector('.sidebar');
    if (sidebar) sidebar.style.display = '';
    var statusBar = document.querySelector('.status-bar');
    if (statusBar) statusBar.style.display = '';
}

// =================== REPOS ===================

function pgRepos() {

    // Restore sidebar/statusbar if coming from login
    _restoreAppChrome();

    var addBtn = guardBtn('write:repos', '<button class="btn btn-p" onclick="toggleForm()">+ Add Repo</button>', 'No permission to add repos');

    html('main', '<div class="page-head between row"><div><h1>Repositories</h1><p>Manage and analyze Git repositories</p></div>' + addBtn + '</div>' +

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

            var ingestBtn = guardBtn('write:repos', '<button class="btn btn-s btn-g" onclick="ingest(\'' + r.id + '\')">Ingest</button>', 'No permission to ingest');
            var delBtn = guardBtn('delete:snapshots', '<button class="btn btn-s btn-d" onclick="delRepo(\'' + r.id + '\')">Del</button>', 'No permission to delete');
            h += '<tr><td><strong>' + esc(r.name) + '</strong></td><td style="font-size:12px;color:var(--text-2)">' + esc(r.url) + '</td><td style="font-size:12px">' + new Date(r.created_at).toLocaleDateString() + '</td><td class="row g-8"><button class="btn btn-s btn-p" onclick="selRepo(\'' + r.id + '\')">Select</button>' + ingestBtn + delBtn + '</td></tr>';

        });

        h += '</tbody></table></div>';

        html('rl', h);

    }).catch(function(e) { html('rl', '<div class="empty"><h3>Cannot connect</h3><p>' + esc(e.message) + '</p></div>'); });

}

function addRepo() {

    if (!Auth.hasScope('write:repos')) { toast('Permission denied', false); return; }

    var n = $('rn').value.trim(), u = $('ru').value.trim();

    if (!n || !u) { toast('Fill both fields', false); return; }

    var branch = $('rb') ? $('rb').value : '';

    var payload = { name: n, url: u };

    if (branch) payload.default_branch = branch;

    API.post('/repos', payload).then(function(r) { toast(r.name + ' registered'); toggleForm(); ingest(r.id); loadRepos(); }).catch(function(e) { toast(e.message, false); });

}

function ingest(id) {

    if (!Auth.hasScope('write:repos')) { toast('Permission denied', false); return; }

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

                Recents.add(rid, sid, rid);

                toast('Ingestion complete: ' + (snap.file_count || '') + ' files indexed');

                setTimeout(function() { loadRepos(); }, 1500);

            } else if (snap.status === 'failed') {

                titleEl.textContent = 'Ingestion failed';

                pctEl.style.color = 'var(--red)';

                bar.style.background = 'var(--red)';

                msgEl.textContent = snap.error_message || 'Unknown error';

                toast('Ingestion failed: ' + (snap.error_message || 'Unknown error'), false);

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

        Recents.add(id, done[done.length - 1].id, d.name || id);

        toast('Selected: ' + d.name);

        navigate('overview');

    }).catch(function(e) { toast(e.message, false); });

}

function delRepo(id) { if (!Auth.hasScope('delete:snapshots')) { toast('Permission denied', false); return; } if (!confirm('Delete?')) return; API.del('/repos/' + id).then(function() { if (S.repo === id) S.set(null, null); toast('Deleted'); loadRepos(); }).catch(function(e) { toast(e.message, false); }); }



// =================== OVERVIEW ===================

function pgOverview() {

    if (!S.ok()) { html('main', noSnap()); return; }

    html('main', skelPage());

    Promise.all([

        API.get(S.path() + '/overview'),

        API.get(S.path() + '/files').catch(function() { return []; }),

        API.get(S.path() + '/health-score').catch(function() { return null; })

    ]).then(function(res) {

        var d = res[0], files = Array.isArray(res[1]) ? res[1] : [], hs = res[2];

        var k = d.symbols_by_kind || {}, tot = 0;

        Object.keys(k).forEach(function(x) { tot += k[x]; });

        var fileCount = d.total_files || files.length || 0;

        var h = '<div class="page-head"><div class="page-head-row"><div><h1>Overview</h1><p>Snapshot ' + S.snap.slice(0, 8) + '</p></div><div class="share-bar">' + deepLinkBtn() + '<button class="share-btn" onclick="openPdfDialog()"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M14 14V4.5L9.5 0H4a2 2 0 00-2 2v12a2 2 0 002 2h8a2 2 0 002-2zM9.5 3A1.5 1.5 0 0011 4.5h2V14a1 1 0 01-1 1H4a1 1 0 01-1-1V2a1 1 0 011-1h5.5v2z"/></svg> Report</button></div></div></div>';

        h += '<div class="stat-row"><div class="stat-item"><div class="stat-num">' + d.total_symbols + '</div><div class="stat-txt">Symbols</div></div><div class="stat-item"><div class="stat-num">' + d.total_edges + '</div><div class="stat-txt">Edges</div></div><div class="stat-item"><div class="stat-num">' + d.total_modules + '</div><div class="stat-txt">Modules</div></div><div class="stat-item"><div class="stat-num">' + fileCount + '</div><div class="stat-txt">Files</div></div><div class="stat-item"><div class="stat-num">' + (k['class'] || 0) + '</div><div class="stat-txt">Classes</div></div><div class="stat-item"><div class="stat-num">' + (k['method'] || 0) + '</div><div class="stat-txt">Methods</div></div></div>';



        // Health gauge + symbol donut side by side

        h += '<div class="ch-grid">';

        if (hs && hs.score !== undefined) {

            var sc = hs.score;

            h += '<div class="card" style="display:flex;flex-direction:column;align-items:center;justify-content:center">';

            h += '<div class="card-hd" style="align-self:flex-start">Health Score</div>';

            h += Chart.gauge(sc, 100, { size: 120, label: sc.toFixed(1), sub: grade(sc), color: scoreCol(sc) });

            h += '</div>';

        }

        // Symbol kind donut

        if (tot > 0) {

            var kindItems = Object.keys(k).sort(function(a,b){return k[b]-k[a];}).map(function(kn){return{label:kn,value:k[kn]};});

            h += '<div class="card"><div class="card-hd">Symbol Distribution</div>';

            h += Chart.donut(kindItems, { center: tot, sub: 'total', width: 180, height: 180 });

            h += '</div>';

        }

        h += '</div>';



        // Distribution table

        h += '<div class="card"><div class="card-hd">Distribution by Kind</div><table class="tbl"><thead><tr><th>Kind</th><th>Count</th><th style="width:45%"></th></tr></thead><tbody>';

        Object.keys(k).sort(function(a, b) { return k[b] - k[a]; }).forEach(function(kn) {

            var pct = tot ? (k[kn] / tot * 100).toFixed(1) : 0;

            h += '<tr><td><span class="badge ' + kindBadge(kn) + '">' + kn + '</span></td><td>' + k[kn] + '</td><td><div class="prog"><div class="prog-fill" style="width:' + pct + '%;background:var(--accent)"></div></div></td></tr>';

        });

        h += '</tbody></table></div>';

        // Phase 5: Risk Radar Summary
        h += '<div class="card" id="radar-card"><div class="card-hd">Risk Radar' + tip('Multi-dimensional risk overview. Each axis represents a different analysis dimension. Further from center = higher risk.') + '</div><div id="radar-content"><div class="skel skel-chart"></div></div></div>';

        // Snapshot management
        h += '<div class="card"><div class="card-hd">Snapshot Actions</div><div class="row g-8 flex-wrap"><button class="btn btn-s btn-g" onclick="viewSnapshots()">View All Snapshots</button><button class="btn btn-s btn-g" onclick="viewFiles()">Browse Files</button><button class="btn btn-s btn-d" onclick="delSnap()">Delete This Snapshot</button></div><div id="snap-tl"></div></div>';

        html('main', h);

        // Async: load risk radar data
        loadRiskRadar();
        // Async: load snapshot timeline
        loadSnapTimeline();
        // Phase 7: Load trends and add sparklines
        loadOverviewTrends();

    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });

}

// Phase 5: Risk Radar - loads multiple endpoints and builds a radar
function loadRiskRadar() {
    if (!S.ok()) return;
    Promise.all([
        API.get(S.path() + '/hotspots').catch(function() { return { items: [] }; }),
        API.get(S.path() + '/dead-code').catch(function() { return {}; }),
        API.get(S.path() + '/coupling').catch(function() { return { modules: [] }; }),
        API.get(S.path() + '/clones').catch(function() { return {}; }),
        API.get(S.path() + '/call-cycles').catch(function() { return { cycles: [] }; })
    ]).then(function(res) {
        var hotspots = res[0].hotspots || res[0].items || [];
        var dc = res[1];
        var modules = res[2].modules || [];
        var clones = res[3];
        var cycles = res[4].cycles || res[4].sccs || [];

        // Calculate dimension values (0-100 scale, higher = worse)
        var highRisk = hotspots.filter(function(h) { return (h.risk_score||0) > 10; }).length;
        var hotspotRisk = Math.min(100, highRisk * 20);

        var deadPct = dc.total_symbols ? Math.round((dc.unreachable_count || 0) / dc.total_symbols * 100) : 0;

        var avgInst = 0;
        if (modules.length) {
            modules.forEach(function(m) { avgInst += m.instability; });
            avgInst = Math.round((avgInst / modules.length) * 100);
        }

        var dupPct = Math.round(clones.duplication_percentage || 0);

        var cycleRisk = Math.min(100, (cycles.length || 0) * 25);

        var container = $('radar-content');
        if (!container) return;

        var dims = [
            { label: 'Hotspots', value: hotspotRisk, max: 100 },
            { label: 'Dead Code', value: deadPct, max: 100 },
            { label: 'Instability', value: avgInst, max: 100 },
            { label: 'Duplication', value: dupPct, max: 100 },
            { label: 'Cycles', value: cycleRisk, max: 100 }
        ];

        var radarHtml = riskRadar(dims, { size: 220 });

        // Risk dimension pills
        var pills = riskDims([
            { name: 'Hotspots', value: highRisk + ' high-risk', level: highRisk > 3 ? 'bad' : highRisk > 0 ? 'warn' : 'ok' },
            { name: 'Dead Code', value: deadPct + '%', level: deadPct > 30 ? 'bad' : deadPct > 10 ? 'warn' : 'ok' },
            { name: 'Instability', value: avgInst + '%', level: avgInst > 70 ? 'bad' : avgInst > 50 ? 'warn' : 'ok' },
            { name: 'Duplication', value: dupPct + '%', level: dupPct > 15 ? 'bad' : dupPct > 5 ? 'warn' : 'ok' },
            { name: 'Cycles', value: cycles.length + ' found', level: cycles.length > 3 ? 'bad' : cycles.length > 0 ? 'warn' : 'ok' }
        ]);

        container.innerHTML = radarHtml + pills;
    }).catch(function() {
        var container = $('radar-content');
        if (container) container.innerHTML = '<p style="color:var(--text-3);text-align:center;padding:16px">Could not load risk data</p>';
    });
}

// Phase 5: Snapshot Timeline
function loadSnapTimeline() {
    if (!S.repo) return;
    API.get('/repos/' + S.repo + '/snapshots').then(function(d) {
        var snaps = (d.items || d.snapshots || d || []).filter(function(s) { return s.status === 'completed'; });
        if (snaps.length < 2) return;
        var el = $('snap-tl');
        if (!el) return;
        el.innerHTML = '<div style="margin-top:12px"><div class="card-hd" style="font-size:11px;margin-bottom:6px">Snapshot History (' + snaps.length + ')</div>' + snapTimeline(snaps, S.snap) + '</div>';
    }).catch(function() {});
}

// Phase 7: Load trend data and inject sparklines into Overview KPIs
function loadOverviewTrends() {
    if (!S.repo) return;
    TrendData.load(S.repo, function(data) {
        if (!data || data.length < 2) return;
        // Find the stat items on the page and append sparklines
        var statItems = document.querySelectorAll('.stat-item');
        var metrics = ['symbols', 'edges', 'modules', 'files'];
        var labels = ['Symbols', 'Edges', 'Modules', 'Files'];
        statItems.forEach(function(item, i) {
            if (i >= metrics.length) return;
            var values = TrendData.metric(data, metrics[i]);
            if (values.length < 2) return;
            var numEl = item.querySelector('.stat-num');
            var txtEl = item.querySelector('.stat-txt');
            if (!numEl || !txtEl) return;
            var trend = computeTrend(values);
            var col = trend.direction === 'up' ? 'var(--accent)' : trend.direction === 'down' ? 'var(--red,#ef4444)' : 'var(--text-3)';
            // Append sparkline after the number
            numEl.insertAdjacentHTML('afterend', sparkline(values, { color: col, width: 44, height: 16 }));
            // Add trend badge
            if (trend.direction !== 'stable') {
                var badge = trendBadge(trend.direction, (trend.delta > 0 ? '+' : '') + trend.delta, true);
                txtEl.insertAdjacentHTML('afterend', badge);
            }
        });
    });
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

            if (s.status === 'completed') h += '<button class="btn btn-s btn-p" onclick="S.set(\'' + S.repo + '\',\'' + s.id + '\');Recents.add(\'' + S.repo + '\',\'' + s.id + '\',\'' + S.repo + '\');toast(\'Selected\');navigate(\'overview\')">Use</button>';

            h += '<button class="btn btn-s btn-d" onclick="delSnapById(\'' + s.id + '\')">Del</button></td></tr>';

        });

        h += '</tbody></table></div>';

        html('main', h);

    }).catch(function(e) { toast(e.message, false); });

}

/* --- GitHub-style file browser state --- */
var _fbFiles = [];
var _fbPath = '';

function viewFiles(startPath) {
    _fbPath = startPath || '';
    API.get(S.path() + '/files').then(function(d) {
        _fbFiles = Array.isArray(d) ? d : (d.items || []);
        _renderFileBrowser();
    }).catch(function(e) { toast('Failed to load files: ' + e.message, false); });
}

function _renderFileBrowser() {
    var cur = _fbPath;
    var depth = cur ? cur.split('/').length : 0;

    // Compute entries at current level
    var folderSet = {};
    var filesHere = [];
    _fbFiles.forEach(function(f) {
        var p = f.path || f.file_path || '';
        if (cur && p.indexOf(cur + '/') !== 0) return;
        if (!cur && p.indexOf('/') === -1) { filesHere.push(f); return; }
        if (!cur) {
            var top = p.split('/')[0];
            folderSet[top] = true;
            return;
        }
        var rel = p.slice(cur.length + 1);
        if (rel.indexOf('/') === -1) { filesHere.push(f); }
        else { folderSet[rel.split('/')[0]] = true; }
    });

    var folders = Object.keys(folderSet).sort();
    filesHere.sort(function(a, b) { return (a.path || '').localeCompare(b.path || ''); });

    // Breadcrumb
    var h = '<div class="fb-header">';
    h += '<nav class="fb-breadcrumb" aria-label="File path">';
    h += '<a href="#" onclick="_fbNav(\'\');return false" class="fb-crumb-link">root</a>';
    if (cur) {
        var parts = cur.split('/');
        var acc = '';
        parts.forEach(function(p, i) {
            acc += (i > 0 ? '/' : '') + p;
            var path = acc;
            if (i < parts.length - 1) {
                h += ' <span class="fb-sep">/</span> <a href="#" onclick="_fbNav(\'' + esc(path) + '\');return false" class="fb-crumb-link">' + esc(p) + '</a>';
            } else {
                h += ' <span class="fb-sep">/</span> <span class="fb-crumb-cur">' + esc(p) + '</span>';
            }
        });
    }
    h += '</nav>';
    h += '<span class="fb-count">' + _fbFiles.length + ' files total</span>';
    h += '</div>';

    // Table
    h += '<div class="fb-table-wrap"><table class="fb-table"><thead><tr><th class="fb-th-name">Name</th><th class="fb-th-lang">Language</th><th class="fb-th-size">Size</th></tr></thead><tbody>';

    // Back row
    if (cur) {
        var parent = cur.indexOf('/') !== -1 ? cur.slice(0, cur.lastIndexOf('/')) : '';
        h += '<tr class="fb-row fb-row-back" onclick="_fbNav(\'' + esc(parent) + '\')" tabindex="0" role="button" aria-label="Go up"><td class="fb-cell-name"><svg class="fb-icon" viewBox="0 0 16 16" width="16" height="16"><path fill="currentColor" d="M1.75 1A1.75 1.75 0 000 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0016 13.25v-8.5A1.75 1.75 0 0014.25 3H7.5a.25.25 0 01-.2-.1l-.9-1.2A1.75 1.75 0 004.98 1H1.75z"/></svg> ..</td><td></td><td></td></tr>';
    }

    // Folders
    folders.forEach(function(name) {
        var full = cur ? cur + '/' + name : name;
        h += '<tr class="fb-row fb-row-folder" onclick="_fbNav(\'' + esc(full) + '\')" tabindex="0" role="button" aria-label="Open folder ' + esc(name) + '">';
        h += '<td class="fb-cell-name"><svg class="fb-icon fb-icon-folder" viewBox="0 0 16 16" width="16" height="16"><path fill="currentColor" d="M1.75 1A1.75 1.75 0 000 2.75v10.5C0 14.216.784 15 1.75 15h12.5A1.75 1.75 0 0016 13.25v-8.5A1.75 1.75 0 0014.25 3H7.5a.25.25 0 01-.2-.1l-.9-1.2A1.75 1.75 0 004.98 1H1.75z"/></svg> ' + esc(name) + '</td>';
        h += '<td></td><td></td></tr>';
    });

    // Files
    filesHere.forEach(function(f) {
        var name = (f.path || '').split('/').pop();
        var size = f.size_bytes || 0;
        var sizeStr = size > 1024 ? (size / 1024).toFixed(1) + ' KB' : size + ' B';
        h += '<tr class="fb-row fb-row-file" onclick="_fbOpenFile(\'' + esc(f.path || '') + '\')" tabindex="0" role="button" aria-label="View file ' + esc(name) + '">';
        h += '<td class="fb-cell-name"><svg class="fb-icon fb-icon-file" viewBox="0 0 16 16" width="16" height="16"><path fill="currentColor" d="M3.75 1.5a.25.25 0 00-.25.25v12.5c0 .138.112.25.25.25h8.5a.25.25 0 00.25-.25V4.664a.25.25 0 00-.073-.177l-2.914-2.914a.25.25 0 00-.177-.073H3.75zM2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0113.25 16h-8.5A1.75 1.75 0 013 14.25V1.75z"/></svg> ' + esc(name) + '</td>';
        h += '<td><span class="badge b-blue">' + esc(f.language || '-') + '</span></td>';
        h += '<td class="fb-cell-size">' + sizeStr + '</td></tr>';
    });

    if (!folders.length && !filesHere.length) {
        h += '<tr><td colspan="3" class="fb-empty">No files in this directory</td></tr>';
    }

    h += '</tbody></table></div>';

    html('main', h);

    // Enable keyboard Enter/Space on rows
    var rows = document.querySelectorAll('.fb-row');
    rows.forEach(function(row) {
        row.addEventListener('keydown', function(e) {
            if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); row.click(); }
        });
    });
}

function _fbNav(path) {
    _fbPath = path;
    _renderFileBrowser();
}

function _fbOpenFile(filePath) {
    // Fetch symbols for this file to display source code
    API.get(S.path() + '/symbols?file_path=' + encodeURIComponent(filePath) + '&limit=500').then(function(d) {
        var symbols = d.items || d || [];
        var h = '<div class="fb-header">';
        h += '<nav class="fb-breadcrumb" aria-label="File path">';
        h += '<a href="#" onclick="_fbNav(\'\');return false" class="fb-crumb-link">root</a>';
        var parts = filePath.split('/');
        var acc = '';
        parts.forEach(function(p, i) {
            acc += (i > 0 ? '/' : '') + p;
            if (i < parts.length - 1) {
                var path = acc;
                h += ' <span class="fb-sep">/</span> <a href="#" onclick="_fbNav(\'' + esc(path) + '\');return false" class="fb-crumb-link">' + esc(p) + '</a>';
            } else {
                h += ' <span class="fb-sep">/</span> <span class="fb-crumb-cur">' + esc(p) + '</span>';
            }
        });
        h += '</nav>';
        h += '<button class="btn btn-s btn-g" onclick="_fbNav(\'' + esc(_fbPath) + '\')">Back to folder</button>';
        h += '</div>';

        if (symbols.length === 0) {
            h += '<div class="fb-code-wrap"><div class="fb-no-code">No parsed symbols for this file.<br><small>Source code is available for files with recognized symbols.</small></div></div>';
        } else {
            // Sort symbols by start_line
            symbols.sort(function(a, b) { return (a.start_line || 0) - (b.start_line || 0); });
            h += '<div class="fb-code-wrap">';
            symbols.forEach(function(sym) {
                if (!sym.source_code) return;
                h += '<div class="fb-symbol">';
                h += '<div class="fb-symbol-hd"><span class="badge b-purple">' + esc(sym.kind) + '</span> <span class="fb-sym-name">' + esc(sym.fq_name) + '</span><span class="fb-sym-lines">L' + sym.start_line + '-' + sym.end_line + '</span></div>';
                h += '<pre class="fb-code"><code>' + esc(sym.source_code) + '</code></pre>';
                h += '</div>';
            });
            if (symbols.every(function(s) { return !s.source_code; })) {
                h += '<div class="fb-no-code">Symbols found but no source code stored.</div>';
            }
            h += '</div>';
        }

        html('main', h);
    }).catch(function(e) {
        toast('Failed to load file content: ' + e.message, false);
    });
}

function delSnap() {

    if (!Auth.hasScope('delete:snapshots')) { toast('Permission denied', false); return; }

    if (!confirm('Delete current snapshot?')) return;

    API.del(S.path()).then(function() { S.set(S.repo, null); toast('Snapshot deleted'); navigate('repos'); }).catch(function(e) { toast(e.message, false); });

}

function delSnapById(sid) {

    if (!Auth.hasScope('delete:snapshots')) { toast('Permission denied', false); return; }

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

        var h = '<div class="page-head"><div class="page-head-row"><div><h1>Code Health</h1><p>66 rules, 13 categories</p></div><div class="share-bar">' + deepLinkBtn() + '</div></div></div>';

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

    html('main', '<div class="page-head"><div class="page-head-row"><div><h1>Graph Explorer</h1><p>Interactive architecture visualization</p></div><div class="share-bar">' + deepLinkBtn({page:'graph'}) + '</div></div></div>' +

        '<div class="g-bar"><button class="btn btn-s btn-p" data-gv="class" onclick="gLoad(\'class\')">Classes</button><button class="btn btn-s btn-g" data-gv="all" onclick="gLoad(\'all\')">All</button><button class="btn btn-s btn-g" data-gv="module" onclick="gLoad(\'module\')">Modules</button><button class="btn btn-s btn-g" data-gv="calls" onclick="gLoad(\'calls\')">Calls</button><div class="sep"></div><button class="btn btn-s btn-g" onclick="GE.fitAll();gHideBreadcrumb()">Fit</button><button class="btn btn-s btn-g" onclick="gToggleSearch()" title="Search (/)">&#128269;</button><button class="btn btn-s btn-g" onclick="gStartPath()" title="Find path (P)">&#8644;</button><button class="btn btn-s btn-g" onclick="GE.exportPNG();toast(\'PNG saved\')">PNG</button><button class="btn btn-s btn-g" onclick="toggleMermaid()">Mermaid</button></div>' +

        '<div class="graph-area" id="ga"><canvas id="gc"></canvas>' +

        '<div class="g-search" id="gsearch"><span class="gs-icon">&#128269;</span><input id="gsearchIn" type="text" placeholder="Search symbols..." autocomplete="off"><span class="gs-count" id="gsearchCt"></span><span class="gs-close" onclick="gCloseSearch()">&times;</span></div>' +

        '<div class="g-heatbar" id="gheatbar"><span class="hb-label">Color:</span><button class="active" onclick="gHeat(\'type\')">Type</button><button onclick="gHeat(\'complexity\')">Complexity</button><button onclick="gHeat(\'churn\')">Churn</button><button onclick="gHeat(\'risk\')">Risk</button></div>' +

        '<div class="g-heat-legend" id="gheatleg"><span>Low</span><div class="hl-bar"></div><span>High</span></div>' +

        '<div class="g-breadcrumb" id="gbreadcrumb" onclick="GE.fitAll();gHideBreadcrumb()"><span class="bc-icon">&#8592;</span><span>All modules</span></div>' +

        '<div class="g-pathbar" id="gpathbar"><span class="pb-step" id="gpathstep">Click source node...</span><span class="pb-node" id="gpathsrc" style="display:none"></span><span class="pb-arrow" id="gpatharrow" style="display:none">&#8594;</span><span class="pb-node" id="gpathtgt" style="display:none"></span><span class="pb-cancel" onclick="gCancelPath()">&times; Cancel</span></div>' +

        '<div class="g-ctrl"><button onclick="GE.sc*=1.2;GE.paint()">+</button><button onclick="GE.sc*=0.8;GE.paint()">&minus;</button><button onclick="GE.fitAll();gHideBreadcrumb()">\u2922</button></div>' +

        '<div class="g-legend"><h6>Nodes</h6><div class="lr"><div class="ld" style="background:#2563eb"></div>Class</div><div class="lr"><div class="ld" style="background:#7c3aed"></div>Interface</div><div class="lr"><div class="ld" style="background:#16a34a"></div>Method</div><div class="lr"><div class="ld" style="background:#dc2626"></div>Enum</div><h6>Edges</h6><div class="lr"><div class="ll" style="background:#6246ea"></div>Calls</div><div class="lr"><div class="ll" style="background:#ca8a04"></div>Inherits</div><div class="lr"><div class="ll" style="background:#7c3aed"></div>Implements</div><div class="lr"><div class="ll" style="background:#2563eb"></div>Uses</div></div>' +

        '<div class="g-info" id="gi"><span class="x" onclick="$(\'gi\').classList.remove(\'show\');$(\'gic\').classList.add(\'hidden\')">&times;</span><h4 id="gin"></h4><div class="ir"><b>Kind:</b> <span id="gik"></span></div><div class="ir"><b>File:</b> <span id="gif"></span></div><div class="ir"><b>Lines:</b> <span id="gil"></span></div><div class="ir"><b>Edges:</b> <span id="gie"></span></div><button class="btn btn-s btn-p gi-code-btn" id="gib" onclick="showNodeCode()">&#9654; View Code</button><div class="gi-code hidden" id="gic"><pre><code id="gics"></code></pre></div></div>' +

        '<div class="g-stats"><span id="gsn">0</span> nodes &middot; <span id="gse">0</span> edges</div></div>' +

        '<div class="card hidden" id="mc" style="margin-top:14px"><div class="row between"><div class="card-hd" style="margin:0">Mermaid Source</div><button class="btn btn-s btn-g" onclick="navigator.clipboard.writeText(_mermaid);toast(\'Copied\')">Copy</button></div><div class="code" id="mcs"></div></div>');

    GE.init($('gc'));

    // Phase 5: Initialize minimap
    Minimap.init($('ga'));
    var _origPaint = GE.paint.bind(GE);
    GE.paint = function() { _origPaint(); Minimap.paint(); };

    // Phase 6: Contextual zoom callback
    GE.onZoomGroup = function(group) { gShowBreadcrumb(group.name); };

    // Phase 6: Path finder callbacks
    GE.onPathStep = function(step, node) { gPathStep(step, node); };
    GE.onPathDone = function(path) { gPathDone(path); };

    GE.onSelect = function(n) { $('gi').classList.add('show'); $('gin').textContent = n.name; $('gik').textContent = n.kind; $('gif').textContent = n.file || '-'; $('gil').textContent = n.sl ? n.sl + '-' + n.el : '-'; $('gie').textContent = GE.edges.filter(function(e) { return e.srcId === n.id || e.tgtId === n.id; }).length; window._selNodeFq = n.id; $('gic').classList.add('hidden'); $('gics').textContent = ''; };

    GE.onDeselect = function() { $('gi').classList.remove('show'); };

    // Phase 6: Keyboard shortcuts for graph
    window._graphKeyHandler = function(e) {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
        if (e.key === '/' || e.key === 'f' && !e.ctrlKey && !e.metaKey) { e.preventDefault(); gToggleSearch(); }
        else if (e.key === 'p' || e.key === 'P') { gStartPath(); }
        else if (e.key === 'Escape') { gCloseSearch(); gCancelPath(); }
        else if (e.key === 'F' || (e.key === 'f' && (e.ctrlKey || e.metaKey))) { /* skip browser find */ }
    };
    document.addEventListener('keydown', window._graphKeyHandler);

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

// =================== PHASE 6: GRAPH INTELLIGENCE HELPERS ===================

// --- Search ---
function gToggleSearch() {
    var el = $('gsearch');
    if (!el) return;
    if (el.classList.contains('open')) { gCloseSearch(); return; }
    el.classList.add('open');
    var inp = $('gsearchIn');
    if (inp) { inp.value = ''; inp.focus(); }
    $('gsearchCt').textContent = '';
    // Live search on input
    if (!inp._bound) {
        inp._bound = true;
        inp.addEventListener('input', function() {
            var matches = GE.search(inp.value);
            $('gsearchCt').textContent = inp.value ? matches.length + ' found' : '';
        });
        inp.addEventListener('keydown', function(e) {
            if (e.key === 'Enter') {
                var matches = GE.searchMatches;
                if (matches && matches.length > 0) GE.flyToNode(matches[0]);
            } else if (e.key === 'Escape') {
                gCloseSearch();
            }
        });
    }
}

function gCloseSearch() {
    var el = $('gsearch');
    if (el) el.classList.remove('open');
    GE.clearSearch();
    $('gsearchCt').textContent = '';
}

// --- Heatmap ---
var _heatCache = {};

function gHeat(mode) {
    var bar = $('gheatbar');
    if (!bar) return;
    var btns = bar.querySelectorAll('button');
    btns.forEach(function(b) { b.classList.remove('active'); });
    var clicked = bar.querySelector('button[onclick="gHeat(\'' + mode + '\')"]');
    if (clicked) clicked.classList.add('active');

    var legend = $('gheatleg');

    if (mode === 'type') {
        GE.clearHeatmap();
        if (legend) legend.classList.remove('visible');
        return;
    }

    if (legend) legend.classList.add('visible');

    // Use cached hotspot data if available
    if (_heatCache[mode]) {
        GE.setHeatmap(mode, _heatCache[mode]);
        return;
    }

    // Fetch hotspot data to compute metric values
    if (!S.ok()) { toast('No snapshot selected', false); return; }
    API.get(S.path() + '/hotspots').then(function(data) {
        var items = data.items || data.hotspots || [];
        var maxVal = 1;
        var raw = {};
        items.forEach(function(h) {
            var val = 0;
            if (mode === 'complexity') val = h.complexity || 0;
            else if (mode === 'churn') val = h.commit_count || h.churn || 0;
            else if (mode === 'risk') val = (h.complexity || 1) * (h.commit_count || h.churn || 1);
            raw[h.fq_name || h.symbol_name] = val;
            if (val > maxVal) maxVal = val;
        });
        var normalized = {};
        Object.keys(raw).forEach(function(k) { normalized[k] = raw[k] / maxVal; });
        _heatCache[mode] = normalized;
        GE.setHeatmap(mode, normalized);
    }).catch(function() {
        toast('Could not load hotspot data for heatmap', false);
    });
}

// --- Path Finder ---
function gStartPath() {
    GE.startPathMode();
    var bar = $('gpathbar');
    if (bar) {
        bar.classList.add('open');
        $('gpathstep').textContent = 'Click source node...';
        $('gpathsrc').style.display = 'none';
        $('gpatharrow').style.display = 'none';
        $('gpathtgt').style.display = 'none';
    }
}

function gCancelPath() {
    GE.cancelPathMode();
    var bar = $('gpathbar');
    if (bar) bar.classList.remove('open');
}

function gPathStep(step, node) {
    if (step === 'pick-target') {
        $('gpathstep').textContent = 'Click target node...';
        $('gpathsrc').textContent = node.name;
        $('gpathsrc').style.display = '';
        $('gpatharrow').style.display = '';
    }
}

function gPathDone(path) {
    if (!path || path.length === 0) {
        toast('No path found between these nodes', false);
        gCancelPath();
        return;
    }
    $('gpathstep').textContent = 'Path (' + path.length + ' nodes):';
    $('gpathsrc').textContent = path[0].split('.').pop();
    $('gpathsrc').style.display = '';
    $('gpatharrow').style.display = '';
    $('gpathtgt').textContent = path[path.length - 1].split('.').pop();
    $('gpathtgt').style.display = '';
    // Fly to midpoint
    if (path.length > 1) {
        var midId = path[Math.floor(path.length / 2)];
        var midNode = GE._find(midId);
        if (midNode) GE.flyToNode(midNode);
    }
}

// --- Contextual Zoom Breadcrumb ---
function gShowBreadcrumb(name) {
    var el = $('gbreadcrumb');
    if (!el) return;
    el.classList.add('visible');
    el.querySelector('span:last-child').textContent = '\u2190 ' + name;
}

function gHideBreadcrumb() {
    var el = $('gbreadcrumb');
    if (el) el.classList.remove('visible');
    GE.zoomedGroup = null;
}



// =================== DEAD CODE ===================

function pgDead() {

    if (!S.ok()) { html('main', noSnap()); return; }

    html('main', skelPage());

    API.get(S.path() + '/dead-code').then(function(d) {

        var h = '<div class="page-head"><h1>Dead Code</h1><p>BFS reachability from entry points</p></div>';

        h += '<div class="stat-row"><div class="stat-item"><div class="stat-num">' + d.total_symbols + '</div><div class="stat-txt">Total</div></div><div class="stat-item"><div class="stat-num" style="color:var(--green)">' + d.reachable_count + '</div><div class="stat-txt">Reachable</div></div><div class="stat-item"><div class="stat-num" style="color:var(--red)">' + d.unreachable_count + '</div><div class="stat-txt">Dead</div></div><div class="stat-item"><div class="stat-num">' + d.entry_point_count + '</div><div class="stat-txt">Entry Pts</div></div></div>';



        // Gauge + insights

        var deadPct = d.total_symbols ? (d.unreachable_count / d.total_symbols) : 0;

        h += '<div class="ch-grid">';

        h += '<div class="card" style="display:flex;flex-direction:column;align-items:center;justify-content:center">';

        h += '<div class="card-hd" style="align-self:flex-start">Dead Code Ratio</div>';

        h += Chart.gauge(d.unreachable_count, d.total_symbols, { size: 110, sub: 'unreachable', color: deadPct > 0.3 ? 'var(--red)' : deadPct > 0.15 ? 'var(--yellow)' : 'var(--green)' });

        h += '</div>';

        h += '<div class="card"><div class="card-hd">Reachability Breakdown</div>';

        h += Chart.donut([{ label: 'Reachable', value: d.reachable_count, color: 'var(--green)' }, { label: 'Dead', value: d.unreachable_count, color: 'var(--red)' }], { center: d.total_symbols, sub: 'symbols', width: 160, height: 160 });

        h += '</div>';

        h += '</div>';



        // Insights

        h += '<div class="ch-section">';

        if (d.unreachable_count === 0) h += Chart.insight('\u2705', 'All Code Reachable', 'No dead code detected from ' + d.entry_point_count + ' entry points. Clean!', 'good');

        else if (deadPct > 0.3) h += Chart.insight('\u26A0\uFE0F', Math.round(deadPct * 100) + '% Dead Code', d.unreachable_count + ' symbols are unreachable. Major cleanup opportunity.', 'warn');

        else if (d.unreachable_count > 0) h += Chart.insight('\uD83D\uDDD1\uFE0F', d.unreachable_count + ' Unreachable Symbols', 'Consider removing dead code to reduce maintenance burden.', 'info');

        h += '</div>';



        // Phase 3: Recommended Actions for Dead Code

        var dcActions = [];

        if (d.unreachable_count > 0) {

            dcActions.push({ emoji:'\uD83D\uDDD1\uFE0F', icon:'act-remove', title:'Remove unreachable code', desc:d.unreachable_count + ' symbols are dead. Remove after team confirmation.', priority: deadPct > 0.3 ? 'high' : 'med' });

            dcActions.push({ emoji:'\uD83D\uDD0D', icon:'act-review', title:'Verify entry points', desc:'Confirm that all entry points are indexed. Missing entry points may cause false positives.', priority:'med' });

        }

        if (d.unreachable_count > 10)

            dcActions.push({ emoji:'\uD83D\uDCCB', icon:'act-refactor', title:'Batch cleanup sprint', desc:'Schedule a cleanup session to remove ' + d.unreachable_count + ' dead symbols.', priority:'low' });

        h += actionsPanel(dcActions);



        (d.unreachable_functions || []).forEach(function(f) { h += '<div class="finding"><div class="dot" style="background:var(--red)"></div><div style="flex:1"><div class="msg">' + esc(f.name) + '</div><div class="sub">' + esc(f.file_path) + ' : ' + f.start_line + '-' + f.end_line + '</div></div></div>'; });

        (d.unreachable_classes || []).forEach(function(c) { h += '<div class="finding"><div class="dot" style="background:var(--yellow)"></div><div style="flex:1"><div class="msg">' + esc(c.name) + '</div><div class="sub">' + esc(c.file_path) + '</div></div></div>'; });

        if (!d.unreachable_count) h += '<div class="card" style="text-align:center;padding:36px;color:var(--green)"><h3>All reachable!</h3></div>';

        html('main', h);

    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });

}



// =================== COUPLING ===================

function pgCoupling() {

    if (!S.ok()) { html('main', noSnap()); return; }

    html('main', skelPage());

    API.get(S.path() + '/coupling').then(function(d) {

        var modules = d.modules || [];

        var h = '<div class="page-head"><div class="page-head-row"><div><h1>Module Coupling</h1><p>Instability, abstractness, cohesion — architectural health</p></div><div class="share-bar">' + deepLinkBtn() + '</div></div></div>';



        // KPI row

        var avgInst = 0, avgCoh = 0, badCount = 0;

        modules.forEach(function(m) { avgInst += m.instability; avgCoh += m.cohesion; if (m.instability > 0.7 || m.cohesion < 0.3) badCount++; });

        if (modules.length) { avgInst /= modules.length; avgCoh /= modules.length; }

        h += '<div class="ch-kpi">';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + modules.length + '</div><div class="ch-kpi-lbl">Modules</div></div>';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num" style="color:' + (avgInst > 0.6 ? 'var(--yellow)' : 'var(--green)') + '">' + avgInst.toFixed(2) + '</div><div class="ch-kpi-lbl">Avg Instability</div></div>';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num" style="color:' + (avgCoh < 0.4 ? 'var(--yellow)' : 'var(--green)') + '">' + avgCoh.toFixed(2) + '</div><div class="ch-kpi-lbl">Avg Cohesion</div></div>';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num" style="color:' + (badCount > 0 ? 'var(--red)' : 'var(--green)') + '">' + badCount + '</div><div class="ch-kpi-lbl">At-Risk</div></div>';

        h += '</div>';



        // Insights

        h += '<div class="ch-section"><div class="ch-section-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12" y2="8"/></svg>Architecture Insights</div>';

        if (badCount === 0 && modules.length) h += Chart.insight('\u2705', 'Healthy Architecture', 'All modules have stable coupling and good cohesion.', 'good');

        if (badCount > 0) h += Chart.insight('\u26A0\uFE0F', badCount + ' Module' + (badCount > 1 ? 's' : '') + ' At Risk', 'High instability or low cohesion detected. Consider reducing dependencies or extracting concerns.', 'warn');

        h += '</div>';



        // Phase 3: Recommended Actions for Coupling

        var coupActions = [];

        modules.forEach(function(m) {

            if (m.instability > 0.7 && m.efferent_coupling > 3 && coupActions.length < 3)

                coupActions.push({ emoji:'\uD83D\uDD17', icon:'act-refactor', title:'Reduce coupling in ' + m.name, desc:'Efferent coupling is ' + m.efferent_coupling + ' with instability ' + m.instability.toFixed(2) + '. Extract interfaces or use events.', priority:'high', onclick:"openCouplingDrawer('" + esc(m.name) + "')" });

            if (m.cohesion < 0.3 && coupActions.length < 4)

                coupActions.push({ emoji:'\uD83E\uDDE9', icon:'act-refactor', title:'Improve cohesion in ' + m.name, desc:'Cohesion is ' + m.cohesion.toFixed(2) + '. Split module into focused responsibilities.', priority:'med', onclick:"openCouplingDrawer('" + esc(m.name) + "')" });

        });

        if (!coupActions.length && modules.length)

            coupActions.push({ emoji:'\u2705', icon:'act-review', title:'Architecture is healthy', desc:'No modules require immediate attention.', priority:'low' });

        h += actionsPanel(coupActions);

        window._coupData = modules;



        // Instability vs Abstractness scatter (main sequence analysis)

        if (modules.length > 1) {

            h += '<div class="card"><div class="card-hd">Instability vs Abstractness (Main Sequence)</div>';

            var coupPts = modules.map(function(m) {

                return { x: m.instability, y: m.abstractness, size: m.symbol_count || 5, risk: (m.instability > 0.7 && m.abstractness < 0.3) ? 12 : 0, label: m.name };

            });

            h += Chart.scatter(coupPts, { xLabel: 'Instability (I)', yLabel: 'Abstractness (A)', width: 400, height: 230 });

            h += '<p style="font-size:10px;color:var(--text-3);text-align:center;margin-top:4px">Modules in the top-right are abstract and unstable (zone of uselessness); bottom-left are concrete and stable (zone of pain)</p>';

            h += '</div>';

        }



        // Cohesion bar chart

        if (modules.length) {

            h += '<div class="card"><div class="card-hd">Module Cohesion</div>';

            var cohItems = modules.slice().sort(function(a,b){return a.cohesion - b.cohesion;}).slice(0, 10).map(function(m) {

                return { label: m.name, value: Math.round(m.cohesion * 100), color: m.cohesion < 0.3 ? 'var(--red)' : m.cohesion < 0.6 ? 'var(--yellow)' : 'var(--green)' };

            });

            h += Chart.bar(cohItems, { limit: 10 });

            h += '</div>';

        }



        // Module cards

        h += '<div class="coup-grid">';

        modules.forEach(function(m) {

            h += '<div class="coup-card" style="cursor:pointer" onclick="openCouplingDrawer(\'' + esc(m.name) + '\')"><h4>' + esc(m.name) + '</h4><div class="m"><span>Symbols</span><b>' + m.symbol_count + '</b></div><div class="m"><span>Ca</span><b>' + m.afferent_coupling + '</b></div><div class="m"><span>Ce</span><b>' + m.efferent_coupling + '</b></div><div class="m"><span>Instability</span><b style="color:' + (m.instability > 0.7 ? 'var(--red)' : 'var(--green)') + '">' + m.instability.toFixed(2) + '</b></div><div class="m"><span>Abstractness</span><b>' + m.abstractness.toFixed(2) + '</b></div><div class="m"><span>Cohesion</span><b style="color:' + (m.cohesion < 0.3 ? 'var(--red)' : 'var(--green)') + '">' + m.cohesion.toFixed(2) + '</b></div></div>';

        });

        h += '</div>';

        html('main', h);

    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });

}



// ?? Coupling Drill-Down Drawer ??

function openCouplingDrawer(modName) {

    var m = (window._coupData || []).find(function(x) { return x.name === modName; });

    if (!m) { toast('Module not found', false); return; }

    var body = '<div class="drawer-section"><div class="drawer-section-title">Module Metrics</div>';

    body += drawerMeta([

        { label: 'Module', value: m.name },

        { label: 'Symbols', value: m.symbol_count || 0 },

        { label: 'Afferent (Ca)', value: m.afferent_coupling || 0 },

        { label: 'Efferent (Ce)', value: m.efferent_coupling || 0 },

        { label: 'Instability', value: m.instability.toFixed(2) },

        { label: 'Abstractness', value: m.abstractness.toFixed(2) },

        { label: 'Cohesion', value: m.cohesion.toFixed(2) },

        { label: 'Distance', value: (Math.abs(m.instability + m.abstractness - 1)).toFixed(2) }

    ]);

    body += '</div>';

    body += '<div class="drawer-section"><div class="drawer-section-title">Assessment</div>';

    if (m.instability > 0.7) body += '<p style="font-size:12px;color:var(--yellow)">\u26A0\uFE0F High instability — this module depends on many others and is fragile to change.</p>';

    if (m.cohesion < 0.3) body += '<p style="font-size:12px;color:var(--yellow);margin-top:4px">\u26A0\uFE0F Low cohesion — symbols in this module are not closely related. Consider splitting.</p>';

    if (m.instability <= 0.7 && m.cohesion >= 0.3) body += '<p style="font-size:12px;color:var(--green)">\u2705 This module is well-structured.</p>';

    body += '</div>';

    body += '<div class="drawer-section"><div class="drawer-section-title">Suggested Actions</div>';

    if (m.efferent_coupling > 3) body += '<div class="action-item"><div class="action-icon act-break">\uD83D\uDD17</div><div class="action-body"><strong>Reduce outgoing dependencies</strong><p>Ce=' + m.efferent_coupling + '. Use dependency inversion or event-driven patterns.</p></div></div>';

    if (m.cohesion < 0.3) body += '<div class="action-item"><div class="action-icon act-refactor">\uD83E\uDDE9</div><div class="action-body"><strong>Split into focused modules</strong><p>Low cohesion means mixed responsibilities. Extract sub-modules.</p></div></div>';

    if (m.instability <= 0.7 && m.cohesion >= 0.3) body += '<div class="action-item"><div class="action-icon act-review">\u2705</div><div class="action-body"><strong>No action needed</strong><p>Module is healthy.</p></div></div>';

    body += '</div>';

    var footer = '<button class="btn btn-s btn-g" onclick="closeDrawer()">Close</button>';

    openDrawer(m.name, body, footer);

}



// =================== DEPENDENCIES ===================

function pgDeps() {

    if (!S.ok()) { html('main', noSnap()); return; }

    html('main', skelPage());

    API.get(S.path() + '/dependencies').then(function(d) {

        var deps = d.dependencies || d.items || [];

        var h = '<div class="page-head"><div class="page-head-row"><div><h1>Dependencies</h1><p>External and internal dependencies detected from manifest files</p></div><div class="share-bar">' + deepLinkBtn() + '</div></div></div>';

        if (!deps.length) { h += '<div class="card" style="text-align:center;padding:30px;color:var(--text-3)">No dependencies detected</div>'; }

        else {

            var ecosystems = {}, devCount = 0, pinnedCount = 0;

            deps.forEach(function(dep) { var eco = dep.ecosystem || 'unknown'; ecosystems[eco] = (ecosystems[eco] || 0) + 1; if (dep.is_dev) devCount++; if (dep.is_pinned) pinnedCount++; });



            // KPI

            h += '<div class="ch-kpi">';

            h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + deps.length + '</div><div class="ch-kpi-lbl">Total Deps</div></div>';

            h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + Object.keys(ecosystems).length + '</div><div class="ch-kpi-lbl">Ecosystems</div></div>';

            h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + devCount + '</div><div class="ch-kpi-lbl">Dev Only</div></div>';

            h += '<div class="ch-kpi-item"><div class="ch-kpi-num" style="color:' + (pinnedCount < deps.length * 0.5 ? 'var(--yellow)' : 'var(--green)') + '">' + pinnedCount + '</div><div class="ch-kpi-lbl">Pinned</div></div>';

            h += '</div>';



            // Insights

            h += '<div class="ch-section"><div class="ch-section-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/></svg>Dependency Insights</div>';

            if (pinnedCount < deps.length * 0.5) h += Chart.insight('\u26A0\uFE0F', 'Low Version Pinning', 'Only ' + pinnedCount + '/' + deps.length + ' dependencies have pinned versions. Consider locking versions for reproducibility.', 'warn');

            else h += Chart.insight('\u2705', 'Good Version Pinning', pinnedCount + '/' + deps.length + ' dependencies are pinned.', 'good');

            if (deps.length > 50) h += Chart.insight('\uD83D\uDCE6', 'Large Dependency Tree', deps.length + ' dependencies detected. Consider auditing for unused packages.', 'info');

            h += '</div>';



            // Phase 3: Recommended Actions for Dependencies

            var depActions = [];

            var unpinned = deps.filter(function(d) { return !d.is_pinned; });

            if (unpinned.length > 0)

                depActions.push({ emoji:'\uD83D\uDCCC', icon:'act-pin', title:'Pin ' + unpinned.length + ' unpinned dependencies', desc:'Lock versions in manifest to prevent unexpected breaking changes.', priority: unpinned.length > deps.length * 0.5 ? 'high' : 'med' });

            if (deps.length > 50)

                depActions.push({ emoji:'\uD83D\uDDD1\uFE0F', icon:'act-remove', title:'Audit for unused packages', desc:deps.length + ' total dependencies. Remove unused ones to reduce attack surface.', priority:'med' });

            if (Object.keys(ecosystems).length > 3)

                depActions.push({ emoji:'\uD83D\uDD0D', icon:'act-review', title:'Review multi-ecosystem complexity', desc:Object.keys(ecosystems).length + ' ecosystems detected. Standardize where possible.', priority:'low' });

            h += actionsPanel(depActions);

            window._depData = deps;



            // Ecosystem donut

            h += '<div class="ch-grid">';

            h += '<div class="card"><div class="card-hd">By Ecosystem</div>';

            var ecoItems = Object.keys(ecosystems).sort(function(a,b){return ecosystems[b]-ecosystems[a];}).map(function(eco){return{label:eco,value:ecosystems[eco]};});

            h += Chart.donut(ecoItems, { center: deps.length, sub: 'total', width: 180, height: 180 });

            h += '</div>';

            // Dev vs Prod bar

            h += '<div class="card"><div class="card-hd">Dev vs Production</div>';

            h += Chart.bar([{ label: 'Production', value: deps.length - devCount, color: 'var(--accent)' }, { label: 'Dev Only', value: devCount, color: 'var(--yellow)' }], { limit: 2 });

            h += '</div>';

            h += '</div>';



            // Table

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

    html('main', skelPage());

    API.get(S.path() + '/clones').then(function(d) {

        var clones = d.clone_groups || d.clones || [];

        var dupPct = d.duplication_percentage || 0;

        var h = '<div class="page-head"><h1>Clone Detection</h1><p>AST fingerprint-based duplicate detection</p></div>';

        h += '<div class="ch-kpi">';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + clones.length + '</div><div class="ch-kpi-lbl">Clone Groups</div></div>';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + (d.total_duplicated_lines || 0) + '</div><div class="ch-kpi-lbl">Dup Lines</div></div>';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num" style="color:' + (dupPct > 15 ? 'var(--red)' : dupPct > 5 ? 'var(--yellow)' : 'var(--green)') + '">' + (dupPct.toFixed ? dupPct.toFixed(1) : dupPct) + '%</div><div class="ch-kpi-lbl">Duplication</div></div>';

        h += '</div>';



        // Gauge + insights

        h += '<div class="ch-grid">';

        h += '<div class="card" style="display:flex;flex-direction:column;align-items:center;justify-content:center">';

        h += '<div class="card-hd" style="align-self:flex-start">Duplication Ratio</div>';

        h += Chart.gauge(dupPct, 100, { size: 110, sub: 'duplicated', color: dupPct > 15 ? 'var(--red)' : dupPct > 5 ? 'var(--yellow)' : 'var(--green)' });

        h += '</div>';

        h += '<div class="card"><div class="card-hd">Insights</div>';

        if (clones.length === 0) h += Chart.insight('\u2705', 'No Clones Detected', 'Code is DRY — no significant duplication found.', 'good');

        else if (dupPct > 15) h += Chart.insight('\u26A0\uFE0F', 'High Duplication', dupPct.toFixed(1) + '% of the codebase is duplicated. Refactor shared logic into utilities.', 'warn');

        else h += Chart.insight('\uD83D\uDCC4', clones.length + ' Clone Groups', 'Some duplication detected but within acceptable levels.', 'info');

        h += '</div></div>';



        // Phase 3: Recommended Actions for Clones

        var cloneActions = [];

        if (clones.length > 0 && dupPct > 15)

            cloneActions.push({ emoji:'\u2702\uFE0F', icon:'act-refactor', title:'Extract shared utilities', desc:'Consolidate ' + clones.length + ' clone groups into reusable functions.', priority:'high' });

        else if (clones.length > 0)

            cloneActions.push({ emoji:'\uD83D\uDCCB', icon:'act-review', title:'Review clone groups', desc:'Check if duplicated code can be consolidated. ' + clones.length + ' groups found.', priority:'med' });

        if (clones.length > 5)

            cloneActions.push({ emoji:'\uD83D\uDD0D', icon:'act-review', title:'Investigate largest clone groups first', desc:'Start with groups having the most instances for maximum DRY impact.', priority:'low' });

        h += actionsPanel(cloneActions);



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

    html('main', skelPage());

    API.get(S.path() + '/call-cycles').then(function(d) {

        var cycles = d.cycles || d.sccs || [];

        var fnsInCycles = d.total_functions_in_cycles || 0;

        var h = '<div class="page-head"><div class="page-head-row"><div><h1>Call Cycles</h1><p>Strongly connected components in the call graph</p></div><div class="share-bar">' + deepLinkBtn() + '</div></div></div>';

        h += '<div class="ch-kpi">';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num" style="color:' + (cycles.length > 0 ? 'var(--red)' : 'var(--green)') + '">' + cycles.length + '</div><div class="ch-kpi-lbl">Cycles</div></div>';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + fnsInCycles + '</div><div class="ch-kpi-lbl">Functions in Cycles</div></div>';

        h += '</div>';



        // Insight

        h += '<div class="ch-section">';

        if (!cycles.length) h += Chart.insight('\u2705', 'No Circular Dependencies', 'The call graph is acyclic. Excellent architecture!', 'good');

        else h += Chart.insight('\u26A0\uFE0F', cycles.length + ' Cycle' + (cycles.length > 1 ? 's' : '') + ' Detected', fnsInCycles + ' functions participate in circular call chains. Break cycles to improve testability.', 'warn');

        h += '</div>';



        // Phase 3: Recommended Actions for Cycles

        var cycActions = [];

        if (cycles.length > 0) {

            cycActions.push({ emoji:'\u2702\uFE0F', icon:'act-break', title:'Break largest cycle', desc:'Extract interface or event boundary to decouple the ' + ((cycles[0].members||cycles[0].nodes||cycles[0]).length || '?') + ' functions in Cycle 1.', priority:'high' });

            if (cycles.length > 2)

                cycActions.push({ emoji:'\uD83D\uDCCB', icon:'act-review', title:'Prioritize cycle removal', desc:cycles.length + ' cycles found. Start with the largest and work down.', priority:'med' });

            cycActions.push({ emoji:'\uD83E\uDDEA', icon:'act-test', title:'Add integration tests', desc:'Cycles make unit testing hard. Add integration tests covering cyclic paths.', priority:'med' });

        }

        h += actionsPanel(cycActions);



        // Cycle size bar chart

        if (cycles.length > 1) {

            h += '<div class="card"><div class="card-hd">Cycle Sizes</div>';

            var cBarItems = cycles.slice(0, 12).map(function(c, i) {

                var m = c.members || c.nodes || c;

                return { label: 'Cycle ' + (i + 1), value: Array.isArray(m) ? m.length : 0, color: 'var(--red)' };

            });

            h += Chart.bar(cBarItems, { limit: 12 });

            h += '</div>';

        }



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

    html('main', skelPage());

    Promise.all([

        API.get(S.path() + '/hotspots').catch(function() { return { items: [] }; }),

        API.get(S.path() + '/contributors').catch(function() { return { contributors: [] }; })

    ]).then(function(res) {

        var hotspots = res[0].hotspots || res[0].items || [];

        var contribs = res[1].contributors || res[1].items || [];

        var totalAuthors = res[1].total_authors || contribs.length;

        var totalCommits = res[1].total_commits || 0;

        var totalLines = res[1].total_lines || 0;

        if (!totalCommits) contribs.forEach(function(c) { totalCommits += (c.commit_count||0); });

        if (!totalLines) contribs.forEach(function(c) { totalLines += (c.line_count||0); });

        var totalRisk = 0, highRisk = 0;

        hotspots.forEach(function(hs) { totalRisk += (hs.risk_score||0); if((hs.risk_score||0)>10) highRisk++; });

        var avgRisk = hotspots.length ? (totalRisk / hotspots.length) : 0;

        // Phase 9: Update ambient risk indicator
        if (typeof Ambient !== 'undefined') {
            if (highRisk > 3) Ambient.setRisk('high');
            else if (highRisk > 0) Ambient.setRisk('medium');
            else Ambient.setRisk('low');
        }

        // Page header with metadata and confidence badge

        var h = '<div class="page-head"><div class="row between flex-wrap g-8"><div><h1>Hotspots &amp; Contributors</h1><p>Risk analysis: churn × complexity with git blame attribution</p>' + snapMeta() + '</div><div class="row g-8">' + deepLinkBtn() + confBadge(contribs, hotspots) + '</div></div></div>';



        // ??? SECTION 1: Repository Facts ???

        h += '<div class="ch-section"><div class="ch-section-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18"/></svg>Repository Facts</div></div>';

        h += '<div class="ch-kpi">';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + totalCommits + '</div><div class="ch-kpi-lbl">Repo Commits' + tip('Total commits reachable from HEAD in the ingested repository history.') + '</div></div>';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + totalAuthors + '</div><div class="ch-kpi-lbl">Contributors' + tip('Unique authors identified by git blame across all indexed symbols.') + '</div></div>';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + (totalLines > 0 ? (totalLines >= 1000 ? (totalLines/1000).toFixed(1) + 'K' : totalLines) : '\u2014') + '</div><div class="ch-kpi-lbl">Lines Owned' + tip('Current lines attributed by git blame. Counted on leaf symbols (methods/functions) to avoid class overlap.') + '</div></div>';

        h += '</div>';



        // ??? SECTION 2: Hotspot Analysis ???

        h += '<hr class="section-divider">';

        h += '<div class="ch-section"><div class="ch-section-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"/><circle cx="12" cy="12" r="4"/></svg>Hotspot Analysis</div></div>';

        h += '<div class="ch-kpi">';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + hotspots.length + '</div><div class="ch-kpi-lbl">Hotspots' + tip('Methods/constructors with non-zero churn AND complexity. More commits to complex code = higher risk.') + '</div></div>';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num" style="color:' + (highRisk > 3 ? 'var(--red)' : highRisk > 0 ? 'var(--yellow)' : 'var(--green)') + '">' + highRisk + '</div><div class="ch-kpi-lbl">High Risk' + tip('Symbols with risk score > 10. Risk = commit_count × cyclomatic_complexity.') + '</div></div>';

        h += '<div class="ch-kpi-item"><div class="ch-kpi-num">' + avgRisk.toFixed(1) + '</div><div class="ch-kpi-lbl">Avg Risk' + tip('Mean risk score across all detected hotspots.') + '</div></div>';

        h += '</div>';



        // Insights

        h += '<div class="ch-section"><div class="ch-section-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4m0 12v4m-7-7H1m22 0h-4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/></svg>Insights</div>';

        if (highRisk > 0) h += Chart.insight('\u26A0\uFE0F', highRisk + ' High-Risk Hotspot' + (highRisk>1?'s':''), 'These symbols have risk > 10 (high churn × complexity). Consider refactoring or adding tests.', 'warn');

        if (contribs.length === 1 && hotspots.length > 3) h += Chart.insight('\uD83D\uDC64', 'Single Contributor Risk', 'Only 1 author owns all code. Bus factor risk \u2014 consider knowledge sharing.', 'warn');

        else if (contribs.length > 1) { var topPct = contribs[0] && totalLines ? (contribs[0].line_count/totalLines*100).toFixed(0) : 0; if (topPct > 70) h += Chart.insight('\uD83D\uDCCA', 'Ownership Concentration', 'Top contributor owns ' + topPct + '% of lines. Consider distributing ownership.', 'warn'); else h += Chart.insight('\u2705', 'Healthy Distribution', 'Ownership is distributed across ' + totalAuthors + ' contributors.', 'good'); }

        if (hotspots.length === 0) h += Chart.insight('\uD83C\uDF89', 'No Hotspots', 'No high-churn complex code detected. Great job!', 'good');

        else if (avgRisk < 5) h += Chart.insight('\u2705', 'Low Average Risk', 'Avg risk is ' + avgRisk.toFixed(1) + ' \u2014 codebase is in good shape.', 'good');

        h += '</div>';



        // ??? Phase 3: Recommended Actions ???

        var hsActions = [];

        if (highRisk > 0) {

            var topHs = hotspots.filter(function(hs){return (hs.risk_score||0)>10;}).slice(0,2);

            topHs.forEach(function(hs) {

                hsActions.push({ emoji:'\uD83E\uDDEA', icon:'act-test', title:'Add tests around ' + ((hs.name||hs.fq_name||'').split('.').pop()), desc:'High risk ('+((hs.risk_score||0).toFixed(1))+') — protect before refactoring.', priority:'high', onclick:"openHotspotDrawer('"+esc(hs.fq_name||hs.name||'')+"')" });

            });

        }

        hotspots.slice(0,5).forEach(function(hs) {

            if ((hs.cyclomatic_complexity||0) > 10 && hsActions.length < 4)

                hsActions.push({ emoji:'\u2702\uFE0F', icon:'act-refactor', title:'Refactor ' + ((hs.name||hs.fq_name||'').split('.').pop()), desc:'Complexity is ' + (hs.cyclomatic_complexity||0) + '. Extract helper methods.', priority:'med' });

        });

        if (contribs.length === 1 && hotspots.length > 2)

            hsActions.push({ emoji:'\uD83D\uDC65', icon:'act-review', title:'Distribute knowledge', desc:'Single author owns all code. Pair program or rotate ownership.', priority:'med' });

        if (hsActions.length < 4 && hotspots.length > 5)

            hsActions.push({ emoji:'\uD83D\uDCCB', icon:'act-review', title:'Review methods with complexity > 10', desc:'Systematic review reduces surprise bugs.', priority:'low' });

        h += actionsPanel(hsActions);



        // Charts: contributor donut + risk scatter

        h += '<div class="ch-grid">';

        h += '<div class="card"><div class="card-hd">Ownership Distribution</div>';

        if (contribs.length) {

            var donutItems = contribs.slice(0, 8).map(function(c) { return { label: c.author || c.name || '?', value: c.line_count || 0 }; });

            h += Chart.donut(donutItems, { center: totalAuthors, sub: 'authors', width: 190, height: 190 });

            h += '<p style="font-size:10px;color:var(--text-3);margin-top:6px;text-align:center">Click a contributor name for details</p>';

        } else { h += '<p style="color:var(--text-3);text-align:center;padding:20px">No contributor data</p>'; }

        h += '</div>';

        h += '<div class="card"><div class="card-hd">Risk Landscape' + tip('Each bubble is a hotspot. X = commits touching it, Y = cyclomatic complexity. Larger = higher risk. Click a bubble for details.') + '</div>';

        if (hotspots.length) {

            var scatterPts = hotspots.slice(0, 40).map(function(hs) {

                return { x: hs.commit_count||0, y: hs.cyclomatic_complexity||0, size: hs.risk_score||1, risk: hs.risk_score||0, label: (hs.name||hs.fq_name||'').split('.').pop() };

            });

            h += Chart.scatter(scatterPts, { xLabel: 'Commits (Churn)', yLabel: 'Complexity', width: 380, height: 220 });

        } else { h += '<p style="color:var(--text-3);text-align:center;padding:20px">No hotspot data</p>'; }

        h += '</div>';

        h += '</div>';



        // Store hotspots/contribs data for drill-down

        window._hsData = hotspots;

        window._contribData = contribs;



        // Churn profile bar chart

        if (hotspots.length > 2) {

            h += '<div class="card"><div class="card-hd">Hotspot Churn Profile' + tip('Number of unique git commits that touched each hotspot method.') + '</div>';

            var churnItems = hotspots.slice(0, 10).map(function(hs, i) {

                return { label: (hs.name||hs.fq_name||'').split('.').pop(), value: hs.commit_count || 0, color: Chart._col(i) };

            });

            h += Chart.bar(churnItems, { limit: 10 });

            h += '</div>';

        }



        // ??? SECTION 3: Ownership Analysis ???

        h += '<hr class="section-divider">';

        h += '<div class="ch-section"><div class="ch-section-title"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/></svg>Ownership Analysis</div></div>';



        // Contributor bar chart

        if (contribs.length > 1) {

            h += '<div class="card"><div class="card-hd">Top Contributors by Lines Owned' + tip('Lines attributed to each author by git blame on leaf symbols.') + '</div>';

            var barItems = contribs.slice(0, 10).map(function(c) { return { label: c.author || c.name || '?', value: c.line_count || 0 }; });

            h += Chart.bar(barItems, { limit: 10 });

            h += '</div>';

        }



        // Hotspot risk gauges

        if (hotspots.length) {

            h += '<div class="card"><div class="card-hd">Top Hotspot Risk Gauges</div><div style="display:flex;flex-wrap:wrap;gap:16px;justify-content:center;padding:8px 0">';

            hotspots.slice(0, 6).forEach(function(hs) {

                var rsk = hs.risk_score || 0;

                var maxR = hotspots[0].risk_score || 20;

                h += '<div style="text-align:center">' + Chart.gauge(rsk, maxR, { size: 90, sub: (hs.name||hs.fq_name||'').split('.').pop().slice(0, 12), label: rsk.toFixed(1) }) + '</div>';

            });

            h += '</div></div>';

        }



        // Contributors table

        h += '<div class="card"><div class="card-hd">Contributors (' + totalAuthors + ' authors)</div>';

        if (!contribs.length) { h += '<p style="color:var(--text-3)">No contributor data. Re-ingest with full git history for accurate blame.</p>'; }

        else {

            h += '<table class="tbl"><thead><tr><th>Author</th><th>Lines</th><th>Symbols</th><th>Functions</th><th>Files</th><th>Modules</th></tr></thead><tbody>';

            contribs.forEach(function(c, ci) {

                h += '<tr style="cursor:pointer" onclick="openContribDrawer(' + ci + ')" title="Click for details"><td><strong>' + esc(c.author || c.name || '') + '</strong></td><td><strong>' + (c.line_count || 0) + '</strong></td><td>' + (c.symbol_count || 0) + '</td><td>' + (c.function_count || 0) + '</td><td>' + (c.file_count || 0) + '</td><td style="font-size:11px;color:var(--text-3)">' + (c.modules || []).slice(0, 3).join(', ') + (c.modules && c.modules.length > 3 ? ' +' + (c.modules.length - 3) : '') + '</td></tr>';

            });

            h += '</tbody></table>';

        }

        h += '</div>';



        // Hotspots table

        h += '<div class="card"><div class="card-hd">Hotspots (Churn × Complexity)' + tip('Risk = commit_count × cyclomatic_complexity. Only methods/constructors with non-zero values appear. Click a row for details.') + '</div>';

        if (!hotspots.length) { h += '<p style="color:var(--text-3)">No hotspot data</p>'; }

        else {

            h += '<table class="tbl"><thead><tr><th>Symbol</th><th>File</th><th>Risk</th><th>Complexity</th><th>Commits</th><th>Authors</th></tr></thead><tbody>';

            hotspots.slice(0, 30).forEach(function(hs, hi) {

                var risk = hs.risk_score || 0;

                h += '<tr style="cursor:pointer" onclick="openHotspotDrawer(\'' + esc(hs.fq_name||hs.name||'') + '\')" title="Click for details"><td><strong>' + esc(hs.name || hs.fq_name || '') + '</strong></td><td style="font-size:11px">' + esc((hs.file_path || '').split('/').pop()) + '</td><td><span style="color:' + (risk > 10 ? 'var(--red)' : risk > 5 ? 'var(--yellow)' : 'var(--green)') + ';font-weight:600">' + risk.toFixed(1) + '</span></td><td>' + (hs.cyclomatic_complexity || 0) + '</td><td>' + (hs.commit_count || 0) + '</td><td>' + (hs.author_count || 0) + '</td></tr>';

            });

            h += '</tbody></table>';

        }

        h += '</div>';

        // Export action

        h += '<div style="text-align:right;margin-top:8px">' + exportBtn('Export Hotspots JSON', "API.download(S.path()+'/hotspots','hotspots.json')") + '</div>';

        html('main', h);

    }).catch(function(e) { html('main', '<div class="empty"><h3>Error</h3><p>' + esc(e.message) + '</p></div>'); });

}



// ?? Hotspot Drill-Down Drawer ??

function openHotspotDrawer(fqName) {

    var hs = (window._hsData || []).find(function(h) { return (h.fq_name||h.name) === fqName; });

    if (!hs) { toast('Symbol not found', false); return; }

    var body = '<div class="drawer-section"><div class="drawer-section-title">Symbol Info</div>';

    body += drawerMeta([

        { label: 'Name', value: hs.name || hs.fq_name || '' },

        { label: 'File', value: (hs.file_path || '').split('/').pop() },

        { label: 'Risk Score', value: (hs.risk_score||0).toFixed(1) },

        { label: 'Complexity', value: hs.cyclomatic_complexity || 0 },

        { label: 'Commits', value: hs.commit_count || 0 },

        { label: 'Authors', value: hs.author_count || 0 }

    ]);

    body += '</div>';

    if (hs.file_path) {

        body += '<div class="drawer-section"><div class="drawer-section-title">Location</div>';

        body += '<p style="font-size:12px;color:var(--text-2);font-family:var(--mono)">' + esc(hs.file_path) + '</p>';

        if (hs.start_line) body += '<p style="font-size:11px;color:var(--text-3)">Lines ' + hs.start_line + '-' + (hs.end_line||'?') + '</p>';

        body += '</div>';

    }

    body += '<div class="drawer-section"><div class="drawer-section-title">Suggested Actions</div>';

    body += '<div class="action-item"><div class="action-icon act-test">\uD83E\uDDEA</div><div class="action-body"><strong>Add tests</strong><p>Protect this hotspot with unit tests before refactoring.</p></div></div>';

    if ((hs.cyclomatic_complexity||0) > 8)

        body += '<div class="action-item"><div class="action-icon act-refactor">\u2702\uFE0F</div><div class="action-body"><strong>Reduce complexity</strong><p>Extract helper methods to bring cyclomatic complexity below 10.</p></div></div>';

    if ((hs.author_count||0) <= 1)

        body += '<div class="action-item"><div class="action-icon act-review">\uD83D\uDC65</div><div class="action-body"><strong>Spread knowledge</strong><p>Only 1 author has touched this. Add a second reviewer.</p></div></div>';

    body += '</div>';

    var footer = '<button class="btn btn-s btn-g" onclick="closeDrawer()">Close</button>';

    if (hs.fq_name) footer += '<button class="btn btn-s btn-p" onclick="closeDrawer();navigate(\'graph\')">View in Graph</button>';

    openDrawer((hs.name||hs.fq_name||'').split('.').pop(), body, footer);

}



// ?? Contributor Drill-Down Drawer ??

function openContribDrawer(idx) {

    var c = (window._contribData || [])[idx];

    if (!c) { toast('Contributor not found', false); return; }

    var body = '<div class="drawer-section"><div class="drawer-section-title">Contributor</div>';

    body += drawerMeta([

        { label: 'Author', value: c.author || c.name || '' },

        { label: 'Lines Owned', value: c.line_count || 0 },

        { label: 'Symbols', value: c.symbol_count || 0 },

        { label: 'Functions', value: c.function_count || 0 },

        { label: 'Files', value: c.file_count || 0 },

        { label: 'Commits', value: c.commit_count || 0 }

    ]);

    body += '</div>';

    if (c.modules && c.modules.length) {

        body += '<div class="drawer-section"><div class="drawer-section-title">Modules Owned</div>';

        c.modules.forEach(function(m) {

            body += '<span class="badge b-blue" style="margin:2px 4px 2px 0">' + esc(m) + '</span>';

        });

        body += '</div>';

    }

    body += '<div class="drawer-section"><div class="drawer-section-title">Ownership Assessment</div>';

    var totalLines = 0; (window._contribData||[]).forEach(function(ct) { totalLines += (ct.line_count||0); });

    var pct = totalLines ? ((c.line_count||0)/totalLines*100).toFixed(1) : 0;

    body += '<p style="font-size:12px;color:var(--text-1)">Owns <strong>' + pct + '%</strong> of total lines.</p>';

    if (pct > 70) body += '<p style="font-size:11px;color:var(--yellow);margin-top:4px">\u26A0\uFE0F High ownership concentration — bus factor risk.</p>';

    else if (pct > 40) body += '<p style="font-size:11px;color:var(--text-3);margin-top:4px">Moderate ownership share.</p>';

    else body += '<p style="font-size:11px;color:var(--green);margin-top:4px">\u2705 Healthy ownership distribution.</p>';

    body += '</div>';

    var footer = '<button class="btn btn-s btn-g" onclick="closeDrawer()">Close</button>';

    openDrawer(c.author || c.name || 'Contributor', body, footer);

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

    if (!guardPage('write:reviews')) return;

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

    if (!guardPage('write:docs')) return;

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

    if (!guardPage('read:export')) return;

    if (!S.ok()) { html('main', noSnap()); return; }

    html('main', '<div class="page-head"><div class="page-head-row"><div><h1>Exports</h1><p>Download analysis in various formats</p></div><div class="share-bar">' + deepLinkBtn() + '</div></div></div><div class="export-grid"><div class="export-card" onclick="openPdfDialog()"><div class="ico">\uD83D\uDCC4</div><h4>PDF Report</h4><p>Shareable analysis summary</p></div><div class="export-card" onclick="doExp(\'json\')"><div class="ico">{ }</div><h4>JSON</h4><p>Full analysis data</p></div><div class="export-card" onclick="doExp(\'portable\')"><div class="ico">\uD83D\uDCE6</div><h4>Portable .eidos</h4><p>Compact archive</p></div><div class="export-card" onclick="doExp(\'sarif\')"><div class="ico">\u26A0</div><h4>SARIF</h4><p>Code scanning format</p></div><div class="export-card" onclick="doExp(\'csv\')"><div class="ico">\uD83D\uDCCA</div><h4>CSV</h4><p>Spreadsheet data</p></div><div class="export-card" onclick="doExp(\'sbom\')"><div class="ico">\uD83D\uDCCB</div><h4>SBOM</h4><p>Bill of Materials</p></div><div class="export-card" onclick="doExp(\'md\')"><div class="ico">\uD83D\uDCDD</div><h4>Markdown</h4><p>Health report</p></div></div>');

}

function doExp(fmt) {

    var map = { json: ['/export', 'export.json'], portable: ['/portable', 'snapshot.eidos'], sarif: ['/export/sarif', 'results.sarif'], csv: ['/export/csv', 'data.zip'], sbom: ['/export/sbom', 'sbom.json'], md: ['/export/markdown', 'report.md'] };

    var m = map[fmt]; if (!m) return;

    API.download(S.path() + m[0], m[1]).then(function() { toast(m[1] + ' downloaded'); }).catch(function(e) { toast('Export failed: ' + e.message, false); });

}



// =================== ADMIN PANEL ===================

var _adminUsersCache = [];
var _adminUserFilter = { search: '', role: '', sort: 'name' };
var _adminPlansCache = [];

function pgAdmin() {
    if (!Auth.isAuthEnabled() || !Auth.isLoggedIn()) {
        html('main', '<div class="page-head"><h1>Admin Panel</h1><p>Manage users, plans, and system</p></div>' +
            '<div class="card"><p style="color:var(--text-2)">Sign in with an admin account to access this panel.</p>' +
            '<button class="btn btn-s btn-p mt" onclick="navigate(\'login\')">Sign In</button></div>');
        return;
    }

    var role = Auth.getUserRole();
    if (role !== 'superadmin' && role !== 'admin' && role !== 'support') {
        html('main', '<div class="page-head"><h1>Admin Panel</h1><p>Manage users, plans, and system</p></div>' +
            '<div class="perm-denied-page"><svg width="48" height="48" fill="none" stroke="var(--text-3)" stroke-width="1.5" viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>' +
            '<h2>Access Restricted</h2><p>You need <b>admin</b> or <b>superadmin</b> role to access this panel.</p>' +
            '<p style="font-size:12px;color:var(--text-3)">Your role: <code>' + esc(role) + '</code></p></div>');
        return;
    }

    // Hero section
    var h = '<div class="admin-hero">';
    h += '<div class="admin-hero-left"><h1>Admin Panel</h1><p>Manage users, plans, and system configuration</p></div>';
    h += '<div class="admin-hero-right">';
    h += '<div class="admin-role-indicator"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/></svg> ' + esc(role) + '</div>';
    h += '<button class="btn btn-xs btn-g" onclick="adminExportUsers()" title="Export Users CSV"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg> Export</button>';
    h += '<button class="btn btn-xs btn-p" onclick="adminInviteUser()" title="Invite a new user"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg> Invite</button>';
    h += '</div></div>';

    // Tabs
    h += '<div class="admin-tabs" id="admin-tabs">';
    h += '<button class="admin-tab active" onclick="adminTab(\'users\',this)"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87M16 3.13a4 4 0 010 7.75"/></svg> Users <span class="admin-tab-badge" id="admin-tab-users-count">…</span></button>';
    h += '<button class="admin-tab" onclick="adminTab(\'plans\',this)"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3h-8l-2 4h12l-2-4z"/></svg> Plans <span class="admin-tab-badge" id="admin-tab-plans-count">…</span></button>';
    h += '<button class="admin-tab" onclick="adminTab(\'activity\',this)"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M12 20V10M18 20V4M6 20v-4"/></svg> Activity</button>';
    h += '<button class="admin-tab" onclick="adminTab(\'system\',this)"><svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 11-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 11-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15H3a2 2 0 110-4h.09"/></svg> System</button>';
    h += '</div>';

    h += '<div id="admin-content"><div class="loader"><span class="spin"></span> Loading...</div></div>';

    html('main', h);
    adminTab('users');

    // Load counts for tab badges
    API.get('/admin/users').then(function(users) {
        _adminUsersCache = users || [];
        var badge = document.getElementById('admin-tab-users-count');
        if (badge) badge.textContent = _adminUsersCache.length;
    });
    API.get('/admin/plans').then(function(plans) {
        _adminPlansCache = plans || [];
        var badge = document.getElementById('admin-tab-plans-count');
        if (badge) badge.textContent = _adminPlansCache.length;
    });
}

function adminTab(tab, btn) {
    if (btn) {
        document.querySelectorAll('.admin-tab').forEach(function(t) { t.classList.remove('active'); });
        btn.classList.add('active');
    } else {
        // Auto-select the correct tab button
        var tabs = document.querySelectorAll('.admin-tab');
        var tabNames = ['users', 'plans', 'activity', 'system'];
        for (var i = 0; i < tabs.length; i++) {
            tabs[i].classList.toggle('active', tabNames[i] === tab);
        }
    }
    var el = document.getElementById('admin-content');
    if (!el) return;
    el.innerHTML = '<div class="loader"><span class="spin"></span> Loading...</div>';

    if (tab === 'users') _adminUsers(el);
    else if (tab === 'plans') _adminPlans(el);
    else if (tab === 'activity') _adminActivity(el);
    else if (tab === 'system') _adminSystem(el);
}

function _adminUsers(el) {
    if (_adminUsersCache.length) {
        _adminUserFilter.search = '';
        _adminUserFilter.role = '';
        _adminUserFilter.sort = 'name';
        _renderAdminUsers(el);
        return;
    }
    API.get('/admin/users').then(function(users) {
        _adminUsersCache = users || [];
        _adminUserFilter = { search: '', role: '', sort: 'name' };
        _renderAdminUsers(el);
        var badge = document.getElementById('admin-tab-users-count');
        if (badge) badge.textContent = _adminUsersCache.length;
    }).catch(function(e) {
        el.innerHTML = '<div class="card"><p style="color:var(--red)">Failed to load users: ' + esc(e.message) + '</p></div>';
    });
}

function _renderAdminUsers(el) {
    var users = _adminUsersCache;

    // Role stats
    var totalUsers = users.length;
    var roleCounts = {};
    for (var i = 0; i < users.length; i++) {
        var r = users[i].role || 'user';
        roleCounts[r] = (roleCounts[r] || 0) + 1;
    }

    var roleColors = { superadmin: 'var(--red)', admin: 'var(--accent)', employee: 'var(--green)', support: 'var(--yellow, #f59e0b)', user: 'var(--text-3)' };
    var roleList = ['superadmin', 'admin', 'employee', 'support', 'user'];

    var h = '';

    // Invite form (inline, hidden by default)
    h += '<div class="admin-invite-form" id="admin-invite-form" style="display:none">';
    h += '<svg width="14" height="14" fill="none" stroke="var(--text-3)" stroke-width="2" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>';
    h += '<input class="inp" id="invite-email" placeholder="Email address" type="email">';
    h += '<input class="inp" id="invite-name" placeholder="Display name (optional)">';
    h += '<select class="inp admin-filter-select" id="invite-role">';
    for (var ir = 0; ir < roleList.length; ir++) {
        h += '<option value="' + roleList[ir] + '"' + (roleList[ir] === 'user' ? ' selected' : '') + '>' + roleList[ir] + '</option>';
    }
    h += '</select>';
    h += '<button class="btn btn-xs btn-p" onclick="adminDoInvite()">Send Invite</button>';
    h += '<button class="btn btn-xs btn-g" onclick="document.getElementById(\'admin-invite-form\').style.display=\'none\'">Cancel</button>';
    h += '</div>';

    // Stats bar
    h += '<div class="admin-stats-bar">';
    h += '<div class="admin-stat-pill"><span class="admin-stat-num">' + totalUsers + '</span> Total Users</div>';
    for (var ri = 0; ri < roleList.length; ri++) {
        var rn = roleList[ri];
        if (roleCounts[rn]) {
            h += '<div class="admin-stat-pill" style="cursor:pointer" onclick="document.getElementById(\'admin-role-filter\').value=\'' + rn + '\';adminFilterUsers()"><span style="color:' + roleColors[rn] + '">●</span> ' + roleCounts[rn] + ' ' + rn + '</div>';
        }
    }
    h += '</div>';

    // Search, filter, sort toolbar
    h += '<div class="admin-toolbar">';
    h += '<div class="admin-search-box"><svg width="14" height="14" fill="none" stroke="var(--text-3)" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>';
    h += '<input class="admin-search-inp" id="admin-user-search" placeholder="Search by name, email, or login..." value="' + esc(_adminUserFilter.search) + '" oninput="adminFilterUsers()"></div>';
    h += '<select class="admin-filter-select" id="admin-role-filter" onchange="adminFilterUsers()">';
    h += '<option value="">All roles</option>';
    for (var fi = 0; fi < roleList.length; fi++) {
        h += '<option value="' + roleList[fi] + '"' + (_adminUserFilter.role === roleList[fi] ? ' selected' : '') + '>' + roleList[fi] + '</option>';
    }
    h += '</select>';
    h += '<select class="admin-sort-select" id="admin-sort" onchange="adminFilterUsers()">';
    h += '<option value="name"' + (_adminUserFilter.sort === 'name' ? ' selected' : '') + '>Sort: Name</option>';
    h += '<option value="role"' + (_adminUserFilter.sort === 'role' ? ' selected' : '') + '>Sort: Role</option>';
    h += '<option value="newest"' + (_adminUserFilter.sort === 'newest' ? ' selected' : '') + '>Sort: Newest</option>';
    h += '<option value="oldest"' + (_adminUserFilter.sort === 'oldest' ? ' selected' : '') + '>Sort: Oldest</option>';
    h += '</select>';
    h += '<button class="btn btn-xs btn-g" onclick="adminRefreshUsers()" title="Refresh users list"><svg width="13" height="13" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/></svg></button>';
    h += '</div>';

    // Filter + sort users
    var filtered = _filterAdminUsers(users);
    var showing = filtered.length;

    if (showing < totalUsers) {
        h += '<p style="font-size:11px;color:var(--text-3);margin-bottom:8px">Showing ' + showing + ' of ' + totalUsers + ' users';
        if (_adminUserFilter.search || _adminUserFilter.role) {
            h += ' &mdash; <a href="#" onclick="document.getElementById(\'admin-user-search\').value=\'\';document.getElementById(\'admin-role-filter\').value=\'\';adminFilterUsers();return false" style="color:var(--accent)">Clear filters</a>';
        }
        h += '</p>';
    }

    if (!filtered.length) {
        h += '<div class="admin-empty"><svg width="32" height="32" fill="none" stroke="var(--text-3)" stroke-width="1.5" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg><p>No users match your search</p>';
        h += '<p style="font-size:11px;margin-top:8px"><a href="#" onclick="document.getElementById(\'admin-user-search\').value=\'\';document.getElementById(\'admin-role-filter\').value=\'\';adminFilterUsers();return false" style="color:var(--accent)">Clear filters</a></p></div>';
        el.innerHTML = h;
        return;
    }

    h += '<div class="admin-user-grid">';
    for (var ui = 0; ui < filtered.length; ui++) {
        var u = filtered[ui];
        var joined = u.created_at ? new Date(u.created_at).toLocaleDateString() : '—';
        var initials = (u.name || u.github_login || '??').slice(0, 2).toUpperCase();
        var roleColor = roleColors[u.role] || 'var(--text-3)';

        h += '<div class="admin-user-card" onclick="adminViewUser(\'' + esc(u.id) + '\')" style="cursor:pointer">';
        h += '<div class="admin-user-card-header">';
        h += '<div class="admin-user-avatar">' + initials + '</div>';
        h += '<div class="admin-user-info">';
        h += '<div class="admin-user-name">' + esc(u.name || u.github_login || 'Unnamed') + '</div>';
        h += '<div class="admin-user-email">' + esc(u.email || '—') + '</div>';
        h += '</div>';
        h += '<span class="admin-role-badge" style="--role-color:' + roleColor + '">' + esc(u.role || 'user') + '</span>';
        h += '</div>';
        h += '<div class="admin-user-card-body">';
        h += '<div class="admin-user-meta"><span>Joined: ' + joined + '</span><span>' + esc(u.auth_provider || 'local') + '</span></div>';
        h += '<div class="admin-user-actions" onclick="event.stopPropagation()">';
        h += '<select class="admin-role-select" data-uid="' + esc(u.id) + '">';
        for (var rx = 0; rx < roleList.length; rx++) {
            h += '<option value="' + roleList[rx] + '"' + (u.role === roleList[rx] ? ' selected' : '') + '>' + roleList[rx] + '</option>';
        }
        h += '</select>';
        h += '<button class="btn btn-xs btn-p" onclick="adminChangeRole(\'' + esc(u.id) + '\')">Update</button>';
        h += '<button class="btn btn-xs btn-g" onclick="adminAssignPlan(\'' + esc(u.id) + '\',\'' + esc(u.name || u.github_login || 'User') + '\')" title="Assign plan">Plan</button>';
        h += '</div></div></div>';
    }
    h += '</div>';

    el.innerHTML = h;
}

function _filterAdminUsers(users) {
    var s = _adminUserFilter.search.toLowerCase();
    var r = _adminUserFilter.role;
    var sort = _adminUserFilter.sort;

    var filtered = users.filter(function(u) {
        if (r && u.role !== r) return false;
        if (s) {
            var haystack = ((u.name || '') + ' ' + (u.email || '') + ' ' + (u.github_login || '') + ' ' + (u.id || '')).toLowerCase();
            return haystack.indexOf(s) !== -1;
        }
        return true;
    });

    // Sort
    filtered.sort(function(a, b) {
        if (sort === 'name') return (a.name || a.github_login || '').localeCompare(b.name || b.github_login || '');
        if (sort === 'role') return (a.role || '').localeCompare(b.role || '');
        if (sort === 'newest') return (b.created_at || '').localeCompare(a.created_at || '');
        if (sort === 'oldest') return (a.created_at || '').localeCompare(b.created_at || '');
        return 0;
    });

    return filtered;
}

function adminFilterUsers() {
    _adminUserFilter.search = (document.getElementById('admin-user-search') || {}).value || '';
    _adminUserFilter.role = (document.getElementById('admin-role-filter') || {}).value || '';
    _adminUserFilter.sort = (document.getElementById('admin-sort') || {}).value || 'name';
    var el = document.getElementById('admin-content');
    if (el) _renderAdminUsers(el);
}

function adminRefreshUsers() {
    _adminUsersCache = [];
    var el = document.getElementById('admin-content');
    if (el) {
        el.innerHTML = '<div class="loader"><span class="spin"></span> Refreshing...</div>';
        API.get('/admin/users').then(function(users) {
            _adminUsersCache = users || [];
            _adminUserFilter = { search: '', role: '', sort: 'name' };
            _renderAdminUsers(el);
            var badge = document.getElementById('admin-tab-users-count');
            if (badge) badge.textContent = _adminUsersCache.length;
        }).catch(function(e) {
            el.innerHTML = '<div class="card"><p style="color:var(--red)">Failed to load users: ' + esc(e.message) + '</p></div>';
        });
    }
}

function adminInviteUser() {
    var form = document.getElementById('admin-invite-form');
    if (form) {
        form.style.display = form.style.display === 'none' ? 'flex' : 'none';
        if (form.style.display !== 'none') {
            var inp = document.getElementById('invite-email');
            if (inp) inp.focus();
        }
    }
}

function adminDoInvite() {
    var email = (document.getElementById('invite-email') || {}).value || '';
    var name = (document.getElementById('invite-name') || {}).value || '';
    var role = (document.getElementById('invite-role') || {}).value || 'user';
    if (!email.trim()) { toast('Email is required', false); return; }
    // Create user via signup-like endpoint or admin endpoint
    API.post('/auth/signup', { email: email.trim(), name: name.trim() || email.split('@')[0], password: 'changeme123', role: role }).then(function() {
        toast('User invited: ' + email);
        document.getElementById('admin-invite-form').style.display = 'none';
        adminRefreshUsers();
    }).catch(function(e) {
        toast(e.message || 'Failed to invite user', false);
    });
}

function adminViewUser(userId) {
    var u = null;
    for (var i = 0; i < _adminUsersCache.length; i++) {
        if (_adminUsersCache[i].id === userId) { u = _adminUsersCache[i]; break; }
    }
    if (!u) return;

    var roleColors = { superadmin: 'var(--red)', admin: 'var(--accent)', employee: 'var(--green)', support: 'var(--yellow, #f59e0b)', user: 'var(--text-3)' };
    var roleColor = roleColors[u.role] || 'var(--text-3)';
    var joined = u.created_at ? new Date(u.created_at).toLocaleString() : '—';
    var initials = (u.name || u.github_login || '??').slice(0, 2).toUpperCase();

    var m = '<div class="admin-modal-overlay" id="admin-user-modal" onclick="if(event.target===this)this.remove()">';
    m += '<div class="admin-modal" style="max-width:520px">';
    m += '<div style="display:flex;align-items:center;gap:12px;margin-bottom:16px">';
    m += '<div class="admin-user-avatar" style="width:48px;height:48px;font-size:16px">' + initials + '</div>';
    m += '<div><div style="font-size:16px;font-weight:600;color:var(--text-0)">' + esc(u.name || u.github_login || 'Unnamed') + '</div>';
    m += '<div style="font-size:12px;color:var(--text-3)">' + esc(u.email || '—') + '</div></div>';
    m += '<span class="admin-role-badge" style="--role-color:' + roleColor + ';margin-left:auto">' + esc(u.role || 'user') + '</span>';
    m += '</div>';

    m += '<div class="admin-detail-grid">';
    m += '<div class="admin-detail-item"><div class="admin-detail-item-label">User ID</div><div class="admin-detail-item-val">' + esc(u.id || '—') + '</div></div>';
    m += '<div class="admin-detail-item"><div class="admin-detail-item-label">Provider</div><div class="admin-detail-item-val">' + esc(u.auth_provider || 'local') + '</div></div>';
    m += '<div class="admin-detail-item"><div class="admin-detail-item-label">GitHub Login</div><div class="admin-detail-item-val">' + esc(u.github_login || '—') + '</div></div>';
    m += '<div class="admin-detail-item"><div class="admin-detail-item-label">Joined</div><div class="admin-detail-item-val">' + joined + '</div></div>';
    m += '<div class="admin-detail-item"><div class="admin-detail-item-label">Role</div><div class="admin-detail-item-val">' + esc(u.role || 'user') + '</div></div>';
    m += '<div class="admin-detail-item"><div class="admin-detail-item-label">Email</div><div class="admin-detail-item-val">' + esc(u.email || '—') + '</div></div>';
    m += '</div>';

    // Quick actions
    m += '<div style="border-top:1px solid var(--border);padding-top:14px;margin-top:14px">';
    m += '<div style="font-size:12px;font-weight:600;margin-bottom:8px;color:var(--text-1)">Quick Actions</div>';
    m += '<div class="row g-8 flex-wrap">';
    m += '<button class="btn btn-xs btn-p" onclick="adminAssignPlan(\'' + esc(u.id) + '\',\'' + esc(u.name || u.github_login || 'User') + '\')">Assign Plan</button>';
    m += '<button class="btn btn-xs btn-g" onclick="adminResetPassword(\'' + esc(u.id) + '\')">Reset Password</button>';
    m += '<button class="btn btn-xs btn-d" onclick="adminDeleteUser(\'' + esc(u.id) + '\',\'' + esc(u.name || u.email || '') + '\')">Delete User</button>';
    m += '</div></div>';

    m += '<div style="text-align:right;margin-top:16px"><button class="btn btn-xs btn-g" onclick="document.getElementById(\'admin-user-modal\').remove()">Close</button></div>';
    m += '</div></div>';

    document.body.insertAdjacentHTML('beforeend', m);
}

function adminChangeRole(userId) {
    var sel = document.querySelector('.admin-role-select[data-uid="' + userId + '"]');
    if (!sel) return;
    var newRole = sel.value;
    API.put('/admin/users/' + userId + '/role', { role: newRole }).then(function(u) {
        toast('Role updated to "' + u.role + '"');
        for (var i = 0; i < _adminUsersCache.length; i++) {
            if (_adminUsersCache[i].id === userId) { _adminUsersCache[i].role = u.role; break; }
        }
        var badge = document.getElementById('admin-tab-users-count');
        if (badge) badge.textContent = _adminUsersCache.length;
    }).catch(function(e) {
        toast(e.message || 'Failed to update role', false);
    });
}

function adminResetPassword(userId) {
    if (!confirm('Reset password for this user? They will need to set a new one.')) return;
    API.put('/admin/users/' + userId + '/role', { password_reset: true }).then(function() {
        toast('Password reset initiated');
    }).catch(function(e) {
        toast(e.message || 'Failed to reset password', false);
    });
}

function adminDeleteUser(userId, userName) {
    if (!confirm('Delete user "' + userName + '"? This action cannot be undone.')) return;
    API.del('/admin/users/' + userId).then(function() {
        toast('User deleted');
        _adminUsersCache = _adminUsersCache.filter(function(u) { return u.id !== userId; });
        var el = document.getElementById('admin-content');
        if (el) _renderAdminUsers(el);
        var badge = document.getElementById('admin-tab-users-count');
        if (badge) badge.textContent = _adminUsersCache.length;
        var modal = document.getElementById('admin-user-modal');
        if (modal) modal.remove();
    }).catch(function(e) {
        toast(e.message || 'Failed to delete user', false);
    });
}

function adminAssignPlan(userId, userName) {
    API.get('/admin/plans').then(function(plans) {
        if (!plans || !plans.length) { toast('No plans available. Create one first.', false); return; }
        var opts = plans.map(function(p) { return '<option value="' + esc(p.id) + '">' + esc(p.name) + (p.description ? ' — ' + esc(p.description) : '') + '</option>'; }).join('');
        var modal = '<div class="admin-modal-overlay" id="admin-plan-modal" onclick="if(event.target===this)this.remove()">';
        modal += '<div class="admin-modal">';
        modal += '<div class="admin-modal-hd">Assign Plan to ' + esc(userName) + '</div>';
        modal += '<div class="field"><label>Select Plan</label><select class="inp" id="assign-plan-id">' + opts + '</select></div>';
        modal += '<div class="field" style="margin-top:10px"><label>Expires (optional)</label><input class="inp" id="assign-plan-expires" type="date"></div>';
        modal += '<div class="row g-8" style="margin-top:14px"><button class="btn btn-s btn-p" onclick="adminDoAssignPlan(\'' + esc(userId) + '\')">Assign</button>';
        modal += '<button class="btn btn-s btn-g" onclick="document.getElementById(\'admin-plan-modal\').remove()">Cancel</button></div>';
        modal += '</div></div>';
        document.body.insertAdjacentHTML('beforeend', modal);
    }).catch(function(e) { toast(e.message || 'Failed to load plans', false); });
}

function adminDoAssignPlan(userId) {
    var planId = (document.getElementById('assign-plan-id') || {}).value;
    var expires = (document.getElementById('assign-plan-expires') || {}).value;
    if (!planId) { toast('Select a plan', false); return; }
    var body = { plan_id: planId };
    if (expires) body.expires_at = expires + 'T23:59:59Z';
    API.put('/admin/users/' + userId + '/subscription', body).then(function(res) {
        toast('Plan "' + (res.plan || 'assigned') + '" assigned');
        var modal = document.getElementById('admin-plan-modal');
        if (modal) modal.remove();
    }).catch(function(e) { toast(e.message || 'Failed to assign plan', false); });
}

function _adminPlans(el) {
    var renderPlans = function(plans) {
        _adminPlansCache = plans || [];
        var h = '';

        // Create plan form
        h += '<div class="card"><div class="card-hd"><svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Create New Plan</div>';
        h += '<div class="admin-plan-form">';
        h += '<div class="row g-8 flex-wrap">';
        h += '<input class="inp" id="plan-name" placeholder="Plan name (e.g. Pro, Enterprise)" style="flex:1;min-width:140px">';
        h += '<input class="inp" id="plan-desc" placeholder="Short description" style="flex:2;min-width:180px">';
        h += '</div>';
        h += '<div class="row g-8 flex-wrap" style="margin-top:8px">';
        h += '<div class="field" style="flex:1;min-width:100px"><label style="font-size:10px">Max Repos</label><input class="inp" id="plan-repos" placeholder="∞" type="number" min="0"></div>';
        h += '<div class="field" style="flex:1;min-width:100px"><label style="font-size:10px">Max Snapshots</label><input class="inp" id="plan-snaps" placeholder="∞" type="number" min="0"></div>';
        h += '<div class="field" style="flex:1;min-width:100px"><label style="font-size:10px">Tokens/Day</label><input class="inp" id="plan-tokens" placeholder="∞" type="number" min="0"></div>';
        h += '<div class="field" style="flex:1;min-width:100px"><label style="font-size:10px">Users</label><input class="inp" id="plan-users" placeholder="∞" type="number" min="0"></div>';
        h += '</div>';
        h += '<button class="btn btn-s btn-p mt" onclick="adminCreatePlan()">Create Plan</button>';
        h += '</div></div>';

        // Plans grid
        h += '<div class="card"><div class="card-hd">Active Plans <span style="font-weight:400;color:var(--text-3);font-size:12px">(' + plans.length + ')</span></div>';
        if (!plans.length) {
            h += '<div class="admin-empty"><svg width="32" height="32" fill="none" stroke="var(--text-3)" stroke-width="1.5" viewBox="0 0 24 24"><rect x="2" y="7" width="20" height="14" rx="2"/><path d="M16 3h-8l-2 4h12l-2-4z"/></svg><p>No plans configured yet. Create your first plan above.</p></div></div>';
            el.innerHTML = h;
            return;
        }

        h += '<div class="admin-plans-grid">';
        for (var i = 0; i < plans.length; i++) {
            var p = plans[i];
            var limits = {};
            try { limits = typeof p.limits === 'string' ? JSON.parse(p.limits) : (p.limits || {}); } catch(e) {}
            h += '<div class="admin-plan-card' + (p.is_active !== false ? '' : ' inactive') + '">';
            h += '<div class="admin-plan-card-hd">';
            h += '<span class="admin-plan-name">' + esc(p.name) + '</span>';
            h += '<span class="admin-plan-status">' + (p.is_active !== false ? '<span style="color:var(--green)">● Active</span>' : '<span style="color:var(--text-3)">○ Inactive</span>') + '</span>';
            h += '</div>';
            if (p.description) h += '<p class="admin-plan-desc">' + esc(p.description) + '</p>';
            h += '<div class="admin-plan-limits">';
            var limitKeys = Object.keys(limits);
            if (limitKeys.length) {
                for (var li = 0; li < limitKeys.length; li++) {
                    var lk = limitKeys[li];
                    var lv = limits[lk];
                    var label = lk.replace(/_/g, ' ').replace(/max /i, '');
                    h += '<div class="admin-plan-limit"><span class="admin-plan-limit-val">' + lv + '</span><span class="admin-plan-limit-label">' + esc(label) + '</span></div>';
                }
            } else {
                h += '<div class="admin-plan-limit"><span class="admin-plan-limit-val">∞</span><span class="admin-plan-limit-label">Unlimited</span></div>';
            }
            h += '</div></div>';
        }
        h += '</div></div>';

        el.innerHTML = h;
    };

    if (_adminPlansCache.length) {
        renderPlans(_adminPlansCache);
    } else {
        API.get('/admin/plans').then(renderPlans).catch(function(e) {
            el.innerHTML = '<div class="card"><p style="color:var(--red)">Failed to load plans: ' + esc(e.message) + '</p></div>';
        });
    }
}

function adminCreatePlan() {
    var name = (document.getElementById('plan-name') || {}).value || '';
    var desc = (document.getElementById('plan-desc') || {}).value || '';
    var repos = parseInt((document.getElementById('plan-repos') || {}).value) || 0;
    var snaps = parseInt((document.getElementById('plan-snaps') || {}).value) || 0;
    var tokens = parseInt((document.getElementById('plan-tokens') || {}).value) || 0;
    var usersLimit = parseInt((document.getElementById('plan-users') || {}).value) || 0;

    if (!name.trim()) { toast('Plan name is required', false); return; }

    var limits = {};
    if (repos > 0) limits.max_repos = repos;
    if (snaps > 0) limits.max_snapshots = snaps;
    if (tokens > 0) limits.max_tokens_per_day = tokens;
    if (usersLimit > 0) limits.max_users = usersLimit;

    API.post('/admin/plans', { name: name.trim(), description: desc, limits: limits }).then(function() {
        toast('Plan "' + name + '" created');
        _adminPlansCache = [];
        adminTab('plans');
        var badge = document.getElementById('admin-tab-plans-count');
        API.get('/admin/plans').then(function(plans) {
            _adminPlansCache = plans || [];
            if (badge) badge.textContent = _adminPlansCache.length;
        });
    }).catch(function(e) {
        toast(e.message || 'Failed to create plan', false);
    });
}

function _adminActivity(el) {
    API.get('/admin/usage?limit=50').then(function(records) {
        var h = '<div class="card"><div class="card-hd"><svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M12 20V10M18 20V4M6 20v-4"/></svg> Recent Activity</div>';

        if (!records || !records.length) {
            h += '<div class="admin-empty"><svg width="32" height="32" fill="none" stroke="var(--text-3)" stroke-width="1.5" viewBox="0 0 24 24"><path d="M12 20V10M18 20V4M6 20v-4"/></svg>';
            h += '<p>No activity recorded yet.</p><p style="font-size:11px;margin-top:6px;color:var(--text-3)">Usage records will appear here after API calls with token tracking.</p></div></div>';
            el.innerHTML = h;
            return;
        }

        h += '<table class="tbl admin-tbl"><thead><tr><th>User</th><th>Action</th><th>Tokens</th><th>Time</th></tr></thead><tbody>';
        for (var i = 0; i < records.length; i++) {
            var r = records[i];
            var time = r.created_at ? new Date(r.created_at).toLocaleString() : '—';
            h += '<tr>';
            h += '<td><code style="font-size:11px">' + esc((r.user_id || '').slice(0, 12)) + '</code></td>';
            h += '<td style="font-size:12px">' + esc(r.action || '—') + '</td>';
            h += '<td style="font-size:12px;font-weight:500">' + (r.tokens_used || 0) + '</td>';
            h += '<td style="font-size:11px;color:var(--text-3)">' + time + '</td>';
            h += '</tr>';
        }
        h += '</tbody></table></div>';
        el.innerHTML = h;
    }).catch(function(e) {
        el.innerHTML = '<div class="card"><p style="color:var(--red)">Failed to load activity: ' + esc(e.message) + '</p></div>';
    });
}

function _adminSystem(el) {
    API.get('/admin/system').then(function(sys) {
        var h = '';

        // System health overview
        h += '<div class="card"><div class="card-hd"><svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg> System Health</div>';
        h += '<div class="admin-sys-grid">';
        h += _adminSysTile(sys.version || '—', 'Version', 'var(--accent)');
        h += _adminSysTile(sys.edition || '—', 'Edition', 'var(--text-1)');
        h += _adminSysTile(sys.auth_enabled ? '✓ Enabled' : '✗ Disabled', 'Auth', sys.auth_enabled ? 'var(--green)' : 'var(--red)');
        h += _adminSysTile((sys.parsers || 0) + ' langs', 'Parsers', 'var(--accent)');
        h += _adminSysTile(sys.users || 0, 'Users', 'var(--text-0)');
        h += _adminSysTile(sys.repos || 0, 'Repositories', 'var(--text-0)');
        h += '</div></div>';

        // Quick actions
        h += '<div class="card"><div class="card-hd"><svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Quick Actions</div>';
        h += '<div class="row g-8 flex-wrap">';
        h += '<button class="btn btn-s btn-g" onclick="navigate(\'settings\')"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06"/></svg> Settings</button>';
        h += '<button class="btn btn-s btn-g" onclick="adminTab(\'users\')"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/></svg> Manage Users</button>';
        h += '<button class="btn btn-s btn-g" onclick="API.get(\'/health\').then(function(d){toast(\'Backend: \'+d.status)}).catch(function(){toast(\'Backend unreachable\',false)})"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg> Ping Backend</button>';
        h += '<button class="btn btn-s btn-g" onclick="adminExportUsers()"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg> Export Users</button>';
        h += '<button class="btn btn-s btn-g" onclick="adminTab(\'activity\')"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 20V10M18 20V4M6 20v-4"/></svg> View Activity</button>';
        h += '</div></div>';

        // Configuration info
        h += '<div class="card"><div class="card-hd"><svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> Configuration</div>';
        h += '<div class="admin-detail-grid">';
        if (sys.demo_mode !== undefined) h += '<div class="admin-detail-item"><div class="admin-detail-item-label">Demo Mode</div><div class="admin-detail-item-val">' + (sys.demo_mode ? 'Yes' : 'No') + '</div></div>';
        if (sys.rate_limit_enabled !== undefined) h += '<div class="admin-detail-item"><div class="admin-detail-item-label">Rate Limiting</div><div class="admin-detail-item-val">' + (sys.rate_limit_enabled ? 'Enabled' : 'Disabled') + '</div></div>';
        if (sys.superadmin_email) h += '<div class="admin-detail-item"><div class="admin-detail-item-label">Superadmin Email</div><div class="admin-detail-item-val">' + esc(sys.superadmin_email) + '</div></div>';
        if (sys.python_version) h += '<div class="admin-detail-item"><div class="admin-detail-item-label">Python</div><div class="admin-detail-item-val">' + esc(sys.python_version) + '</div></div>';
        h += '</div></div>';

        el.innerHTML = h;
    }).catch(function(e) {
        el.innerHTML = '<div class="card"><p style="color:var(--red)">Failed to load system info: ' + esc(e.message) + '</p></div>';
    });
}

function _adminSysTile(value, label, color) {
    return '<div class="admin-sys-tile">' +
        '<div class="admin-sys-tile-val" style="color:' + (color || 'var(--text-0)') + '">' + esc(String(value)) + '</div>' +
        '<div class="admin-sys-tile-label">' + label + '</div></div>';
}

function adminExportUsers() {
    if (!_adminUsersCache.length) { toast('No users to export', false); return; }
    var csv = 'Name,Email,Role,Login,Provider,Joined\n';
    for (var i = 0; i < _adminUsersCache.length; i++) {
        var u = _adminUsersCache[i];
        csv += '"' + (u.name || '').replace(/"/g, '""') + '","' + (u.email || '') + '","' + (u.role || '') + '","' + (u.github_login || '') + '","' + (u.auth_provider || 'local') + '","' + (u.created_at || '') + '"\n';
    }
    var blob = new Blob([csv], { type: 'text/csv' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url; a.download = 'eidos_users_' + new Date().toISOString().slice(0, 10) + '.csv';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
    toast('Users exported as CSV');
}


// =================== SETTINGS ===================

function pgSettings() {

    // Build auth section based on mode
    var authSection = '';
    if (Auth.isAuthEnabled()) {
        var user = Auth.getUser();
        authSection = '<div class="card"><div class="card-hd">Account</div>';
        if (user && user.id !== 'anonymous') {
            authSection += '<div class="row g-12" style="align-items:center;margin-bottom:12px">';
            if (user.avatar_url) {
                authSection += '<img src="' + esc(user.avatar_url) + '" style="width:40px;height:40px;border-radius:50%">';
            }
            authSection += '<div><p style="font-size:14px;font-weight:600;color:var(--text-0)">' + esc(user.name || user.github_login) + '</p>';
            authSection += '<p style="font-size:12px;color:var(--text-2)">' + esc(user.email || '') + '</p></div>';
            authSection += '<span class="auth-role-badge role-' + (user.role || 'user') + '" style="margin-left:auto">' + esc(user.role || 'user') + '</span>';
            authSection += '</div>';
            authSection += '<p style="font-size:12px;color:var(--text-3);margin-bottom:12px">Provider: ' + esc(user.auth_provider || 'github') + ' &middot; ID: ' + esc((user.id || '').slice(0, 12)) + '</p>';
            authSection += '<button class="btn btn-s btn-d" onclick="Auth.logout()">Sign Out</button>';
        } else {
            authSection += '<p style="font-size:13px;color:var(--text-2);margin-bottom:8px">Not signed in</p>';
            authSection += '<button class="btn btn-s btn-p" onclick="navigate(\'login\')">Sign In</button>';
        }
        authSection += '</div>';
    } else {
        authSection = '<div class="card"><div class="card-hd">Authentication</div><p style="font-size:13px;color:var(--text-2)">Auth is disabled. Running in <span class="demo-badge">DEMO MODE</span></p><p style="font-size:11px;color:var(--text-3);margin-top:6px">Set EIDOS_AUTH_ENABLED=true on the backend to enable login and RBAC.</p></div>';
    }

    html('main', '<div class="page-head"><h1>Settings</h1><p>Configure connection, AI, auth, and system</p></div>' +

        authSection +

        '<div class="card" id="apikeys-card"><div class="card-hd">API Keys</div>' +
        (Auth.isAuthEnabled() && Auth.isLoggedIn()
            ? '<p style="font-size:13px;color:var(--text-2);margin-bottom:12px">Create keys for CI/CD pipelines and programmatic access. Keys are shown <b>once</b> at creation.</p>' +
              '<div id="apikeys-form" class="row g-8 flex-wrap" style="margin-bottom:14px">' +
              '<input class="inp" id="ak-name" placeholder="Key name (e.g. CI Pipeline)" style="flex:1;min-width:160px">' +
              '<input class="inp" id="ak-scopes" placeholder="Scopes: * or read:repos,write:repos" style="flex:1;min-width:180px" value="*">' +
              '<select class="inp" id="ak-expiry" style="width:130px"><option value="">No expiry</option><option value="7">7 days</option><option value="30">30 days</option><option value="90">90 days</option><option value="365">1 year</option></select>' +
              '<button class="btn btn-s btn-p" onclick="createApiKey()">Create Key</button></div>' +
              '<div id="apikeys-list"><div class="loader"><span class="spin"></span> Loading keys...</div></div>'
            : '<p style="font-size:13px;color:var(--text-3)">Sign in to manage API keys.</p>') +
        '</div>' +

        '<div class="card"><div class="card-hd">API Connection</div><div class="field"><label>Backend URL</label><input class="inp" id="su" value="' + esc(API.base) + '"></div><div class="row g-8"><button class="btn btn-p" onclick="saveUrl()">Save & Test</button></div><div id="ss" class="mt"></div></div>' +

        '<div class="card"><div class="card-hd">Active Context</div><p style="font-size:13px;color:var(--text-2)">Repo: <b style="color:var(--text-0)">' + (S.repo || 'none') + '</b></p><p style="font-size:13px;color:var(--text-2)">Snap: <b style="color:var(--text-0)">' + (S.snap || 'none') + '</b></p><button class="btn btn-s btn-g mt" onclick="S.set(null,null);toast(\'Cleared\');pgSettings()">Clear Selection</button></div>' +

        '<div class="card"><div class="card-hd">User Experience</div><div class="row g-8 flex-wrap"><button class="btn btn-s btn-g" onclick="Tour.restart()">Restart Onboarding Tour</button><button class="btn btn-s btn-g" onclick="Notif.clear();toast(\'Notifications cleared\')">Clear Notifications</button><button class="btn btn-s btn-g" onclick="Perf.toggle()">Toggle Perf Monitor</button><button class="btn btn-s btn-g" onclick="Prefs.reset();toast(\'Preferences reset\')">Reset Preferences</button><button class="btn btn-s btn-d" onclick="localStorage.clear();toast(\'All local data cleared\');location.reload()">Reset All Data</button></div></div>' +

        '<div id="cfg"><div class="loader"><span class="spin"></span> Loading configuration...</div></div>');

    if (Auth.isAuthEnabled() && Auth.isLoggedIn()) loadApiKeys();
    loadCfg();

}

// =================== API KEY MANAGEMENT ===================

function loadApiKeys() {
    API.get('/auth/api-keys').then(function(keys) {
        var el = document.getElementById('apikeys-list');
        if (!el) return;
        if (!keys || keys.length === 0) {
            el.innerHTML = '<p style="font-size:13px;color:var(--text-3)">No API keys yet. Create one above.</p>';
            return;
        }
        var h = '<table class="tbl"><thead><tr><th>Name</th><th>Prefix</th><th>Scopes</th><th>Expires</th><th>Last Used</th><th>Uses</th><th></th></tr></thead><tbody>';
        for (var i = 0; i < keys.length; i++) {
            var k = keys[i];
            var exp = k.expires_at ? new Date(k.expires_at).toLocaleDateString() : '<span style="color:var(--text-3)">Never</span>';
            var lastUsed = k.last_used_at ? _timeAgo(new Date(k.last_used_at)) : '<span style="color:var(--text-3)">Never</span>';
            var scopes = (k.scopes || ['*']).join(', ');
            h += '<tr>';
            h += '<td><b style="color:var(--text-0)">' + esc(k.name) + '</b></td>';
            h += '<td><code style="font-size:11px;color:var(--accent)">' + esc(k.prefix) + '...</code></td>';
            h += '<td style="font-size:11px;max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + esc(scopes) + '">' + esc(scopes) + '</td>';
            h += '<td style="font-size:12px">' + exp + '</td>';
            h += '<td style="font-size:12px">' + lastUsed + '</td>';
            h += '<td style="font-size:12px">' + (k.usage_count || 0) + '</td>';
            h += '<td><button class="btn btn-xs btn-d" onclick="revokeApiKey(\'' + esc(k.id) + '\',\'' + esc(k.name) + '\')">Revoke</button></td>';
            h += '</tr>';
        }
        h += '</tbody></table>';
        el.innerHTML = h;
    }).catch(function(e) {
        var el = document.getElementById('apikeys-list');
        if (el) el.innerHTML = '<p style="font-size:12px;color:var(--red)">Could not load API keys: ' + esc(e.message) + '</p>';
    });
}

function createApiKey() {
    var nameEl = document.getElementById('ak-name');
    var scopesEl = document.getElementById('ak-scopes');
    var expiryEl = document.getElementById('ak-expiry');
    var name = (nameEl && nameEl.value || '').trim();
    if (!name) { toast('Please enter a key name', false); return; }
    var scopes = (scopesEl && scopesEl.value || '*').trim();
    var expiry = expiryEl && expiryEl.value ? parseInt(expiryEl.value) : null;

    var url = '/auth/api-keys?name=' + encodeURIComponent(name) + '&scopes=' + encodeURIComponent(scopes);
    if (expiry) url += '&expires_in_days=' + expiry;

    API.post(url).then(function(data) {
        // Show the raw key once in a prominent way
        var listEl = document.getElementById('apikeys-list');
        var keyHtml = '<div class="apikey-created-banner">' +
            '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">' +
            '<svg width="18" height="18" fill="none" stroke="var(--green)" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/></svg>' +
            '<b style="color:var(--text-0)">Key created! Copy it now — it won\'t be shown again.</b></div>' +
            '<div class="apikey-raw-display">' +
            '<code id="ak-raw-value">' + esc(data.key) + '</code>' +
            '<button class="btn btn-xs btn-g" onclick="copyApiKey()" title="Copy to clipboard">Copy</button>' +
            '</div></div>';
        if (listEl) listEl.innerHTML = keyHtml;

        // Clear form
        if (nameEl) nameEl.value = '';
        if (expiryEl) expiryEl.value = '';

        toast('API key "' + name + '" created');

        // Reload the key list after a moment
        setTimeout(loadApiKeys, 2500);
    }).catch(function(e) {
        toast(e.message || 'Failed to create API key', false);
    });
}

function copyApiKey() {
    var code = document.getElementById('ak-raw-value');
    if (!code) return;
    var text = code.textContent || code.innerText;
    if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(function() { toast('Copied to clipboard'); });
    } else {
        // Fallback
        var ta = document.createElement('textarea');
        ta.value = text;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        toast('Copied to clipboard');
    }
}

function revokeApiKey(id, name) {
    if (!confirm('Revoke API key "' + name + '"? This cannot be undone.')) return;
    API.del('/auth/api-keys/' + id).then(function() {
        toast('Key "' + name + '" revoked');
        loadApiKeys();
    }).catch(function(e) {
        toast(e.message || 'Failed to revoke key', false);
    });
}

function _timeAgo(date) {
    var seconds = Math.floor((Date.now() - date.getTime()) / 1000);
    if (seconds < 60) return 'just now';
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) return minutes + 'm ago';
    var hours = Math.floor(minutes / 60);
    if (hours < 24) return hours + 'h ago';
    var days = Math.floor(hours / 24);
    if (days < 30) return days + 'd ago';
    return date.toLocaleDateString();
}

// =================== SETTINGS CONFIG ===================

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

