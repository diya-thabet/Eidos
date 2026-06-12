// ══════════════════════════════════════════════════════════════
// Auth & Token Management (RBAC Integration)
// ══════════════════════════════════════════════════════════════

var Auth = {
    _tokenKey: 'eidos_token',
    _userKey: 'eidos_user',
    _modeKey: 'eidos_auth_mode',
    _user: null,
    _authEnabled: null,

    // --- Token ---
    getToken: function() {
        return localStorage.getItem(this._tokenKey) || null;
    },

    setToken: function(token) {
        if (token) {
            localStorage.setItem(this._tokenKey, token);
        } else {
            localStorage.removeItem(this._tokenKey);
        }
    },

    clearToken: function() {
        localStorage.removeItem(this._tokenKey);
        localStorage.removeItem(this._userKey);
        this._user = null;
    },

    isLoggedIn: function() {
        return !!this.getToken();
    },

    // --- Token Decode (without verification, for expiry check) ---
    decodePayload: function(token) {
        if (!token) return null;
        try {
            var parts = token.split('.');
            if (parts.length !== 3) return null;
            var payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
            var decoded = atob(payload);
            return JSON.parse(decoded);
        } catch (e) {
            return null;
        }
    },

    isTokenExpired: function() {
        var token = this.getToken();
        if (!token) return true;
        var payload = this.decodePayload(token);
        if (!payload || !payload.exp) return false; // No exp = never expires (or can't check)
        var now = Math.floor(Date.now() / 1000);
        return now >= payload.exp;
    },

    // --- User ---
    getUser: function() {
        if (this._user) return this._user;
        try {
            var stored = localStorage.getItem(this._userKey);
            if (stored) {
                this._user = JSON.parse(stored);
                return this._user;
            }
        } catch (e) {}
        return null;
    },

    setUser: function(user) {
        this._user = user;
        if (user) {
            localStorage.setItem(this._userKey, JSON.stringify(user));
        } else {
            localStorage.removeItem(this._userKey);
        }
    },

    getUserRole: function() {
        var u = this.getUser();
        return u ? (u.role || 'user') : 'user';
    },

    // --- Auth Mode Detection ---
    isAuthEnabled: function() {
        if (this._authEnabled !== null) return this._authEnabled;
        var stored = localStorage.getItem(this._modeKey);
        if (stored !== null) {
            this._authEnabled = stored === 'true';
            return this._authEnabled;
        }
        return false; // Default to demo mode until detected
    },

    setAuthEnabled: function(enabled) {
        this._authEnabled = enabled;
        localStorage.setItem(this._modeKey, enabled ? 'true' : 'false');
    },

    // Detect auth mode from backend
    detectAuthMode: function() {
        var self = this;
        return fetch(API.base + '/auth/me', {
            headers: self.getToken() ? { 'Authorization': 'Bearer ' + self.getToken() } : {}
        }).then(function(r) {
            if (r.status === 401) {
                // Auth is enabled but we're not logged in
                self.setAuthEnabled(true);
                return { authEnabled: true, user: null };
            }
            if (r.ok) {
                return r.json().then(function(user) {
                    // If user.id === 'anonymous', auth is disabled (demo mode)
                    var isDemo = user.id === 'anonymous' || user.github_login === 'anonymous';
                    self.setAuthEnabled(!isDemo);
                    if (!isDemo) {
                        self.setUser(user);
                    } else {
                        self.setUser({ id: 'anonymous', name: 'Anonymous', role: 'superadmin', github_login: 'anonymous', avatar_url: '' });
                    }
                    return { authEnabled: !isDemo, user: user };
                });
            }
            // 501 = auth not configured, treat as demo
            if (r.status === 501) {
                self.setAuthEnabled(false);
                self.setUser({ id: 'anonymous', name: 'Anonymous', role: 'superadmin', github_login: 'anonymous', avatar_url: '' });
                return { authEnabled: false, user: null };
            }
            self.setAuthEnabled(false);
            return { authEnabled: false, user: null };
        }).catch(function() {
            // Backend unreachable — keep current state
            return { authEnabled: self.isAuthEnabled(), user: self.getUser() };
        });
    },

    // Fetch and cache current user from backend
    fetchMe: function() {
        var self = this;
        return API.get('/auth/me').then(function(user) {
            self.setUser(user);
            return user;
        }).catch(function(e) {
            // If 401, token is invalid
            if (e.message && e.message.indexOf('401') !== -1) {
                self.clearToken();
            }
            return null;
        });
    },

    // --- Logout ---
    logout: function() {
        this.clearToken();
        this._user = null;
        toast('Logged out');
        navigate('login');
    },

    // --- Scopes (derived from role) ---
    _roleScopes: {
        superadmin: ['*'],
        admin: ['read:repos','write:repos','read:snapshots','write:snapshots','delete:snapshots','read:analysis','read:coverage','write:coverage','read:gates','write:gates','write:reviews','write:docs','read:export','admin:users','admin:plans','admin:audit'],
        employee: ['read:repos','write:repos','read:snapshots','write:snapshots','delete:snapshots','read:analysis','read:coverage','write:coverage','read:gates','write:gates','write:reviews','write:docs','read:export'],
        support: ['read:repos','read:snapshots','read:analysis','read:coverage','read:gates','read:export','admin:audit'],
        user: ['read:repos','write:repos','read:snapshots','write:snapshots','delete:snapshots','read:analysis','read:coverage','write:coverage','read:gates','write:gates','write:reviews','write:docs','read:export']
    },

    hasScope: function(scope) {
        if (!this.isAuthEnabled()) return true; // Demo mode = all access
        var role = this.getUserRole();
        var scopes = this._roleScopes[role] || this._roleScopes.user;
        if (scopes.indexOf('*') !== -1) return true;
        return scopes.indexOf(scope) !== -1;
    },

    hasRole: function(role) {
        if (!this.isAuthEnabled()) return true; // Demo mode
        var hierarchy = { user: 0, support: 1, employee: 2, admin: 3, superadmin: 4 };
        var current = hierarchy[this.getUserRole()] || 0;
        var required = hierarchy[role] || 0;
        return current >= required;
    },

    // --- OAuth URL builders ---
    getGitHubLoginUrl: function() {
        return API.base + '/auth/login';
    },

    getGoogleLoginUrl: function() {
        return API.base + '/auth/google/login';
    },

    // --- Handle OAuth callback token ---
    handleCallback: function() {
        // Check URL params for token (returned from backend callback)
        var params = new URLSearchParams(window.location.search);
        var token = params.get('token');
        if (token) {
            this.setToken(token);
            // Clean URL
            window.history.replaceState({}, '', window.location.pathname + window.location.hash);
            return true;
        }
        return false;
    }
};

// ══════════════════════════════════════════════════════════════
// API Object (with auth interceptor)
// ══════════════════════════════════════════════════════════════

var API = {

    base: localStorage.getItem('eidos_url') || 'http://localhost:8000',

    setBase: function(u) { this.base = u.replace(/\/+$/, ''); localStorage.setItem('eidos_url', this.base); },

    req: function(path, method, body) {

        var opts = { method: method || 'GET', headers: { 'Content-Type': 'application/json' } };

        // Attach auth token if available
        var token = Auth.getToken();
        if (token) {
            opts.headers['Authorization'] = 'Bearer ' + token;
        }

        if (body) opts.body = JSON.stringify(body);

        return fetch(this.base + path, opts).then(function(r) {

            // Global 401 handler: token expired or invalid
            if (r.status === 401 && Auth.isAuthEnabled()) {
                Auth.clearToken();
                toast('Session expired. Please log in again.', false);
                navigate('login');
                return Promise.reject(new Error('Unauthorized'));
            }

            // Global 403 handler: permission denied
            if (r.status === 403) {
                return r.text().then(function(t) {
                    var msg = 'Permission denied';
                    try { var parsed = JSON.parse(t); msg = parsed.detail || msg; } catch(e) {}
                    toast(msg, false);
                    return Promise.reject(new Error(msg));
                });
            }

            if (!r.ok) return r.text().then(function(t) { throw new Error(t || 'HTTP ' + r.status); });

            if (r.status === 204 || r.headers.get('content-length') === '0') return null;

            var ct = r.headers.get('content-type') || '';

            return ct.indexOf('json') !== -1 ? r.json() : r.text();

        });

    },

    get: function(p) { return this.req(p, 'GET'); },

    post: function(p, b) { return this.req(p, 'POST', b); },

    put: function(p, b) { return this.req(p, 'PUT', b); },

    patch: function(p, b) { return this.req(p, 'PATCH', b); },

    del: function(p) { return this.req(p, 'DELETE'); },

    download: function(path, name) {

        var headers = {};
        var token = Auth.getToken();
        if (token) headers['Authorization'] = 'Bearer ' + token;

        return fetch(this.base + path, { headers: headers }).then(function(r) {

            if (r.status === 401 && Auth.isAuthEnabled()) {
                Auth.clearToken();
                toast('Session expired', false);
                navigate('login');
                return Promise.reject(new Error('Unauthorized'));
            }

            if (r.status === 403) {
                toast('Permission denied', false);
                return Promise.reject(new Error('Forbidden'));
            }

            if (!r.ok) throw new Error('HTTP ' + r.status);

            return r.blob();

        }).then(function(blob) {

            var url = URL.createObjectURL(blob);

            var a = document.createElement('a'); a.href = url; a.download = name; a.click();

            URL.revokeObjectURL(url);

        });

    }

};



var S = {

    repo: localStorage.getItem('eidos_r') || null,

    snap: localStorage.getItem('eidos_s') || null,

    set: function(r, s) { this.repo = r; this.snap = s; localStorage.setItem('eidos_r', r || ''); localStorage.setItem('eidos_s', s || ''); },

    ok: function() { return this.repo && this.snap; },

    path: function() { return '/repos/' + this.repo + '/snapshots/' + this.snap; }

};



function esc(s) { if (!s) return ''; var d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

function toast(m, ok) {
    var icon = ok !== false ? '\u2705' : '\u274C';
    Notif.push(icon, m);
}

// ══════════════════════════════════════════════════════════════
// Permission-Aware UI Helpers
// ══════════════════════════════════════════════════════════════

// Scope-to-page mapping for sidebar nav buttons
var _navScopes = {
    repos: 'read:repos',
    overview: 'read:analysis',
    symbols: 'read:analysis',
    health: 'read:analysis',
    graph: 'read:analysis',
    deadcode: 'read:analysis',
    coupling: 'read:analysis',
    deps: 'read:analysis',
    clones: 'read:analysis',
    cycles: 'read:analysis',
    hotspots: 'read:analysis',
    ask: 'read:analysis',
    review: 'write:reviews',
    docs: 'write:docs',
    search: 'read:analysis',
    exports: 'read:export',
    settings: null // always visible
};

/**
 * Apply permission-based visibility to sidebar nav items.
 * Called after login and on every navigate() to keep UI in sync.
 */
function applyPermissions() {
    // Skip in demo mode — everything visible
    if (!Auth.isAuthEnabled()) {
        document.querySelectorAll('.nav-btn').forEach(function(btn) {
            btn.classList.remove('perm-hidden', 'perm-disabled');
            btn.removeAttribute('aria-disabled');
            btn.title = '';
        });
        return;
    }

    document.querySelectorAll('.nav-btn[data-p]').forEach(function(btn) {
        var page = btn.getAttribute('data-p');
        var scope = _navScopes[page];
        if (scope === null || scope === undefined) {
            // Always visible (settings, etc.)
            btn.classList.remove('perm-hidden', 'perm-disabled');
            btn.removeAttribute('aria-disabled');
            btn.title = '';
            return;
        }
        if (Auth.hasScope(scope)) {
            btn.classList.remove('perm-hidden', 'perm-disabled');
            btn.removeAttribute('aria-disabled');
            btn.title = '';
        } else {
            btn.classList.add('perm-disabled');
            btn.setAttribute('aria-disabled', 'true');
            btn.title = 'Insufficient permissions';
        }
    });
}

/**
 * Returns HTML for a button only if the user has the required scope.
 * If not permitted, returns a disabled button with a lock icon.
 * @param {string} scope - Required scope (e.g. 'write:repos')
 * @param {string} html - Button HTML to render if permitted
 * @param {string} [label] - Optional label for the disabled state
 */
function guardBtn(scope, btnHtml, label) {
    if (!Auth.isAuthEnabled() || Auth.hasScope(scope)) return btnHtml;
    var lbl = label || 'No permission';
    return '<button class="btn btn-s btn-g perm-locked" disabled title="' + esc(lbl) + '"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg></button>';
}

/**
 * Check if the current user can access a page. If not, show a permission denied screen.
 * Returns true if access is allowed, false if blocked.
 * @param {string} scope - Required scope
 */
function guardPage(scope) {
    if (!Auth.isAuthEnabled() || Auth.hasScope(scope)) return true;
    html('main', '<div class="empty perm-denied-page"><div class="perm-denied-icon"><svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg></div><h3>Access Restricted</h3><p>You don\'t have permission to view this page.</p><p class="perm-denied-detail">Required: <code>' + esc(scope) + '</code><br>Your role: <code>' + esc(Auth.getUserRole()) + '</code></p><button class="btn btn-p" onclick="navigate(\'repos\')">Go to Repositories</button></div>');
    return false;
}

function $(id) { return document.getElementById(id); }

function html(id, h) {

    var el = $(id);

    el.innerHTML = h;

    // trigger stagger animations on fresh content

    el.querySelectorAll('.stat-row').forEach(function(r) { r.classList.add('anim-stagger'); });

}

function scoreCol(v) { return v >= 80 ? 'var(--green)' : v >= 60 ? 'var(--yellow)' : 'var(--red)'; }

function grade(v) { return v >= 90 ? 'A' : v >= 80 ? 'B' : v >= 70 ? 'C' : v >= 60 ? 'D' : 'F'; }

function kindBadge(k) { var m = { class:'b-blue', method:'b-green', interface:'b-yellow', enum:'b-red', constructor:'b-blue', field:'b-muted', function:'b-green' }; return m[k] || 'b-muted'; }

function noSnap() { return '<div class="empty"><h3>No snapshot selected</h3><p>Go to Repositories and select one first.</p></div>'; }



// Phase 1 helpers

function tip(text) { return '<span class="tip-wrap"><span class="tip-icon">?</span><span class="tip-bubble">' + esc(text) + '</span></span>'; }

function snapMeta() {

    if (!S.ok()) return '';

    return '<div class="snap-meta">' +

        '<span class="snap-tag"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>' + S.snap.slice(0, 8) + '</span>' +

        '</div>';

}

function confBadge(contribs, hotspots) {

    var hasBlame = contribs && contribs.length > 0 && contribs[0].line_count > 0;

    var hasChurn = hotspots && hotspots.length > 0 && hotspots[0].commit_count > 0;

    if (hasBlame && hasChurn) return '<span class="conf-badge conf-high"><span class="conf-dot"></span>High confidence</span>';

    if (hasBlame || hasChurn) return '<span class="conf-badge conf-medium"><span class="conf-dot"></span>Medium confidence</span>';

    return '<span class="conf-badge conf-low"><span class="conf-dot"></span>Low confidence</span>';

}

function skelKPI(n) {

    var h = '<div class="skel-grid">'; for (var i = 0; i < (n||4); i++) h += '<div class="skel skel-kpi"></div>'; h += '</div>';

    return h;

}

function skelRows(n) { var h = ''; for (var i = 0; i < (n||5); i++) h += '<div class="skel skel-line" style="width:' + (60 + Math.random()*30) + '%"></div>'; return h; }

function skelPage() { return skelKPI(6) + '<div class="skel skel-chart"></div><div style="margin-top:16px">' + skelRows(6) + '</div>'; }



// Phase 3 helpers — Guided Analysis



// Drawer management

function openDrawer(title, bodyHtml, footerHtml) {

    $('drawer-title').textContent = title || 'Details';

    $('drawer-body').innerHTML = bodyHtml || '';

    $('drawer-footer').innerHTML = footerHtml || '';

    $('drawer').classList.add('open');

    $('drawer-overlay').classList.add('open');

    document.addEventListener('keydown', _drawerEsc);

}

function closeDrawer() {

    $('drawer').classList.remove('open');

    $('drawer-overlay').classList.remove('open');

    document.removeEventListener('keydown', _drawerEsc);

}

function _drawerEsc(e) { if (e.key === 'Escape') closeDrawer(); }



// Recommended actions builder

function actionsPanel(actions) {

    if (!actions || !actions.length) return '';

    var h = '<div class="actions-panel"><div class="actions-panel-head"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg><h4>Recommended Actions</h4></div>';

    actions.forEach(function(a) {

        var iconCls = a.icon || 'act-review';

        var pri = a.priority || 'med';

        h += '<div class="action-item" ' + (a.onclick ? 'onclick="' + a.onclick + '"' : '') + '>';

        h += '<div class="action-icon ' + iconCls + '">' + (a.emoji || '\u25B6') + '</div>';

        h += '<div class="action-body"><strong>' + esc(a.title) + '</strong><p>' + esc(a.desc || '') + '</p></div>';

        h += '<span class="action-badge priority-' + pri + '">' + pri + '</span>';

        h += '</div>';

    });

    h += '</div>';

    return h;

}



// Filter chips builder

var _activeFilters = {};

function filterBar(pageId) {

    var filters = _activeFilters[pageId] || [];

    if (!filters.length) return '';

    var h = '<div class="filter-bar">';

    filters.forEach(function(f, i) {

        h += '<span class="filter-chip">' + esc(f.label) + '<span class="chip-x" onclick="removeFilter(\'' + pageId + '\',' + i + ')">×</span></span>';

    });

    h += '<span class="filter-clear" onclick="clearFilters(\'' + pageId + '\')">Clear all</span>';

    h += '</div>';

    return h;

}

function addFilter(pageId, label, value) {

    if (!_activeFilters[pageId]) _activeFilters[pageId] = [];

    var exists = _activeFilters[pageId].some(function(f) { return f.value === value; });

    if (!exists) _activeFilters[pageId].push({ label: label, value: value });

}

function removeFilter(pageId, idx) {

    if (_activeFilters[pageId]) _activeFilters[pageId].splice(idx, 1);

    navigate(document.querySelector('.nav-btn.active').getAttribute('data-p'));

}

function clearFilters(pageId) {

    _activeFilters[pageId] = [];

    navigate(document.querySelector('.nav-btn.active').getAttribute('data-p'));

}

function getFilters(pageId) { return _activeFilters[pageId] || []; }



// Drawer content builders for drill-down

function drawerMeta(items) {

    var h = '<div class="drawer-meta">';

    items.forEach(function(it) {

        h += '<div class="drawer-meta-item"><div class="label">' + esc(it.label) + '</div><div class="value">' + esc(String(it.value)) + '</div></div>';

    });

    h += '</div>';

    return h;

}



// Export insight panel helper

function exportBtn(format, onclick) {

    return '<button class="insight-export" onclick="' + onclick + '"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>' + esc(format) + '</button>';

}

// ══════════════════════════════════════════════════════════════
// Phase 4 — Power User Experience
// Command Palette, Keyboard Shortcuts, Recents
// ══════════════════════════════════════════════════════════════

// ── Recent repos/snapshots ───────────────────────────────────
var Recents = {
    _key: 'eidos_recents',
    _max: 8,
    get: function() {
        try { return JSON.parse(localStorage.getItem(this._key)) || []; }
        catch(e) { return []; }
    },
    add: function(repoId, snapId, label) {
        var list = this.get();
        list = list.filter(function(r) { return !(r.repo === repoId && r.snap === snapId); });
        list.unshift({ repo: repoId, snap: snapId, label: label || repoId, time: Date.now() });
        if (list.length > this._max) list = list.slice(0, this._max);
        localStorage.setItem(this._key, JSON.stringify(list));
    },
    clear: function() { localStorage.removeItem(this._key); }
};

// ── Command Palette ──────────────────────────────────────────
var CMD = {
    _open: false,
    _idx: 0,
    _items: [],

    commands: function() {
        var cmds = [
            { group: 'Navigation', title: 'Go to Repositories', icon: '\uD83D\uDCC1', action: function() { navigate('repos'); }, shortcut: 'G R' },
            { group: 'Navigation', title: 'Go to Overview', icon: '\uD83D\uDCCA', action: function() { navigate('overview'); }, shortcut: 'G O' },
            { group: 'Navigation', title: 'Go to Symbols', icon: '\u2329\u232A', action: function() { navigate('symbols'); } },
            { group: 'Navigation', title: 'Go to Health', icon: '\uD83D\uDCC8', action: function() { navigate('health'); } },
            { group: 'Navigation', title: 'Go to Graph Explorer', icon: '\uD83D\uDD78\uFE0F', action: function() { navigate('graph'); }, shortcut: 'G G' },
            { group: 'Navigation', title: 'Go to Dead Code', icon: '\u274C', action: function() { navigate('deadcode'); } },
            { group: 'Navigation', title: 'Go to Coupling', icon: '\uD83D\uDD17', action: function() { navigate('coupling'); } },
            { group: 'Navigation', title: 'Go to Dependencies', icon: '\uD83D\uDCE6', action: function() { navigate('deps'); } },
            { group: 'Navigation', title: 'Go to Clones', icon: '\uD83D\uDCC4', action: function() { navigate('clones'); } },
            { group: 'Navigation', title: 'Go to Cycles', icon: '\uD83D\uDD04', action: function() { navigate('cycles'); } },
            { group: 'Navigation', title: 'Go to Hotspots', icon: '\uD83D\uDD25', action: function() { navigate('hotspots'); }, shortcut: 'G H' },
            { group: 'Navigation', title: 'Go to Settings', icon: '\u2699\uFE0F', action: function() { navigate('settings'); }, shortcut: 'G S' },
            { group: 'Actions', title: 'Toggle Theme', icon: '\uD83C\uDF13', action: function() { toggleTheme(); }, shortcut: 'T' },
            { group: 'Actions', title: 'Export Report', icon: '\uD83D\uDCE5', action: function() { navigate('exports'); } },
            { group: 'Actions', title: 'Generate PDF Report', icon: '\uD83D\uDCC4', action: function() { openPdfDialog(); } },
            { group: 'Actions', title: 'Copy Share Link', icon: '\uD83D\uDD17', action: function() { DeepLink.copy(); } },
            { group: 'Actions', title: 'Search Symbols', icon: '\uD83D\uDD0D', action: function() { navigate('search'); }, shortcut: '/' },
            { group: 'Actions', title: 'Clear Active Snapshot', icon: '\uD83D\uDDD1\uFE0F', action: function() { S.set(null, null); toast('Cleared selection'); navigate('repos'); } },
            { group: 'Actions', title: 'Clear Recent History', icon: '\uD83E\uDDF9', action: function() { Recents.clear(); toast('Recents cleared'); } }
        ];
        // Auth actions
        if (Auth.isAuthEnabled()) {
            if (Auth.isLoggedIn()) {
                cmds.push({ group: 'Account', title: 'Sign Out', icon: '\uD83D\uDEAA', action: function() { Auth.logout(); } });
            } else {
                cmds.push({ group: 'Account', title: 'Sign In', icon: '\uD83D\uDD11', action: function() { navigate('login'); } });
            }
        }
        // Add recents
        var recents = Recents.get();
        recents.forEach(function(r) {
            cmds.push({ group: 'Recent', title: r.label, icon: '\uD83D\uDD52', sub: r.snap ? r.snap.slice(0, 8) : '', action: function() { S.set(r.repo, r.snap); toast('Loaded ' + r.label); navigate('overview'); } });
        });
        return cmds;
    },

    open: function() {
        this._open = true;
        this._idx = 0;
        var overlay = $('cmd-overlay');
        overlay.classList.add('open');
        var input = $('cmd-input');
        input.value = '';
        input.focus();
        this.render('');
    },

    close: function() {
        this._open = false;
        $('cmd-overlay').classList.remove('open');
        $('cmd-input').blur();
    },

    render: function(query) {
        var cmds = this.commands();
        var q = (query || '').toLowerCase().trim();
        var filtered = q ? cmds.filter(function(c) {
            return c.title.toLowerCase().indexOf(q) !== -1 ||
                   (c.sub && c.sub.toLowerCase().indexOf(q) !== -1) ||
                   c.group.toLowerCase().indexOf(q) !== -1;
        }) : cmds;
        this._items = filtered;
        if (this._idx >= filtered.length) this._idx = Math.max(0, filtered.length - 1);

        var container = $('cmd-results');
        if (!filtered.length) {
            container.innerHTML = '<div class="cmd-empty">No matching commands</div>';
            return;
        }
        var h = '';
        var lastGroup = '';
        var self = this;
        filtered.forEach(function(c, i) {
            if (c.group !== lastGroup) {
                lastGroup = c.group;
                h += '<div class="cmd-group-label">' + esc(c.group) + '</div>';
            }
            h += '<div class="cmd-item' + (i === self._idx ? ' active' : '') + '" data-ci="' + i + '" onmouseenter="CMD.hover(' + i + ')" onclick="CMD.exec(' + i + ')">';
            h += '<div class="cmd-item-icon">' + c.icon + '</div>';
            h += '<div class="cmd-item-body"><div class="cmd-item-title">' + esc(c.title) + '</div>';
            if (c.sub) h += '<div class="cmd-item-sub">' + esc(c.sub) + '</div>';
            h += '</div>';
            if (c.shortcut) h += '<span class="cmd-item-shortcut">' + esc(c.shortcut) + '</span>';
            h += '</div>';
        });
        container.innerHTML = h;
        // Scroll active into view
        var active = container.querySelector('.cmd-item.active');
        if (active) active.scrollIntoView({ block: 'nearest' });
    },

    hover: function(i) {
        this._idx = i;
        this.render($('cmd-input').value);
    },

    exec: function(i) {
        var item = this._items[i];
        if (item && item.action) {
            this.close();
            item.action();
        }
    },

    handleKey: function(e) {
        if (!this._open) return;
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            this._idx = Math.min(this._idx + 1, this._items.length - 1);
            this.render($('cmd-input').value);
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            this._idx = Math.max(this._idx - 1, 0);
            this.render($('cmd-input').value);
        } else if (e.key === 'Enter') {
            e.preventDefault();
            this.exec(this._idx);
        } else if (e.key === 'Escape') {
            e.preventDefault();
            this.close();
        }
    }
};

function cmdOpen() { CMD.open(); }
function cmdClose() { CMD.close(); }

// ── Global Keyboard Shortcuts ────────────────────────────────
(function() {
    var _goBuf = '';
    var _goTimer = null;

    document.addEventListener('keydown', function(e) {
        // Don't trigger shortcuts when typing in inputs
        var tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select') {
            // But still handle palette keys inside cmd-input
            if (e.target.id === 'cmd-input') CMD.handleKey(e);
            return;
        }

        // Ctrl+K / Cmd+K — Command Palette
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (CMD._open) CMD.close(); else CMD.open();
            return;
        }

        // Escape closes palette or drawer
        if (e.key === 'Escape') {
            if (CMD._open) { CMD.close(); return; }
            if ($('drawer').classList.contains('open')) { closeDrawer(); return; }
        }

        // "/" to focus search
        if (e.key === '/' && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            navigate('search');
            setTimeout(function() {
                var inp = document.querySelector('#main input');
                if (inp) inp.focus();
            }, 100);
            return;
        }

        // "T" to toggle theme
        if (e.key === 't' || e.key === 'T') {
            if (!e.ctrlKey && !e.metaKey && !e.altKey) {
                toggleTheme();
                return;
            }
        }

        // "G" + second key navigation (vim-style)
        if (e.key === 'g' || e.key === 'G') {
            if (!_goBuf) {
                _goBuf = 'g';
                clearTimeout(_goTimer);
                _goTimer = setTimeout(function() { _goBuf = ''; }, 800);
                return;
            }
        }
        if (_goBuf === 'g') {
            _goBuf = '';
            clearTimeout(_goTimer);
            var goMap = { r: 'repos', o: 'overview', h: 'hotspots', g: 'graph', s: 'settings', d: 'deadcode', c: 'coupling', e: 'exports' };
            var target = goMap[e.key.toLowerCase()];
            if (target) { navigate(target); return; }
        }

        // "?" to open command palette (alternative)
        if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            CMD.open();
            return;
        }
    });

    // Input handler for command palette filtering
    document.addEventListener('input', function(e) {
        if (e.target.id === 'cmd-input') {
            CMD._idx = 0;
            CMD.render(e.target.value);
        }
    });

    // Show shortcut hint on first visit
    if (!localStorage.getItem('eidos_hint_shown')) {
        setTimeout(function() {
            var hint = $('shortcut-hint');
            if (hint) {
                hint.classList.add('show');
                setTimeout(function() { hint.classList.remove('show'); }, 5000);
            }
            localStorage.setItem('eidos_hint_shown', '1');
        }, 2000);
    }
})();

// ══════════════════════════════════════════════════════════════
// Phase 5 - Advanced HMI Layer
// Status bar, risk radar, minimap helper, ingestion timeline
// ══════════════════════════════════════════════════════════════

// -- Global Status Bar Updater --------------------------------
function updateStatusBar() {
    var dot = $('sb-dot');
    var conn = $('sb-conn');
    var repo = $('sb-repo');
    var snap = $('sb-snap');
    if (!dot) return;
    // Connection state is set by checkConn, mirror it
    var cdEl = $('cd');
    if (cdEl && cdEl.classList.contains('on')) {
        dot.className = 'sb-dot on';
        conn.textContent = 'Connected';
    } else {
        dot.className = 'sb-dot off';
        conn.textContent = 'Offline';
    }
    repo.textContent = S.repo ? S.repo.slice(0, 12) : 'none';
    snap.textContent = S.snap ? S.snap.slice(0, 8) : 'none';

    // Update user badge in sidebar
    _renderAuthBadge();
}

function _renderAuthBadge() {
    var container = $('auth-badge');
    if (!container) return;
    var user = Auth.getUser();
    if (!user || user.id === 'anonymous') {
        if (!Auth.isAuthEnabled()) {
            container.innerHTML = '<div class="auth-badge-wrap"><div class="demo-badge"><svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg> DEMO MODE</div></div>';
        } else {
            container.innerHTML = '<div class="auth-badge-wrap auth-badge-signin"><a href="#" onclick="navigate(\'login\');return false" class="auth-signin-link"><svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 012 2v14a2 2 0 01-2 2h-4"/><polyline points="10 17 15 12 10 7"/><line x1="15" y1="12" x2="3" y2="12"/></svg> Sign in</a></div>';
        }
        return;
    }
    var avatarHtml = '';
    if (user.avatar_url) {
        avatarHtml = '<div class="auth-avatar"><img src="' + esc(user.avatar_url) + '" alt=""></div>';
    } else {
        var initials = (user.name || user.github_login || 'U').split(' ').map(function(w) { return w[0]; }).join('').toUpperCase().slice(0, 2);
        avatarHtml = '<div class="auth-avatar">' + initials + '</div>';
    }
    var roleClass = 'role-' + (user.role || 'user');
    var provider = user.auth_provider || 'oauth';
    var providerIcon = provider === 'local' ? '<svg viewBox="0 0 24 24" width="10" height="10" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>'
        : provider === 'google' ? '<svg viewBox="0 0 24 24" width="10" height="10" fill="currentColor"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/></svg>'
        : '<svg viewBox="0 0 24 24" width="10" height="10" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>';
    var emailLine = user.email ? '<div class="auth-email">' + esc(user.email) + '</div>' : '';
    var h = '<div class="auth-badge-wrap">';
    h += '<div class="auth-user-badge" onclick="_toggleProfileMenu()">';
    h += avatarHtml;
    h += '<div class="auth-info">';
    h += '<div class="auth-name">' + esc(user.name || user.github_login) + '</div>';
    h += emailLine;
    h += '</div>';
    h += '<svg class="auth-chevron" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>';
    h += '</div>';
    h += '<div class="auth-profile-menu" id="auth-profile-menu">';
    h += '<div class="apm-header">';
    h += '<span class="auth-role-badge ' + roleClass + '">' + esc(user.role || 'user') + '</span>';
    h += '<span class="apm-provider">' + providerIcon + ' ' + esc(provider) + '</span>';
    h += '</div>';
    h += '<button class="apm-item" onclick="navigate(\'settings\');_closeProfileMenu()"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 11-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33"/></svg> Settings</button>';
    h += '<button class="apm-item apm-signout" onclick="Auth.logout()"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg> Sign Out</button>';
    h += '</div>';
    h += '</div>';
    container.innerHTML = h;
}

function _toggleProfileMenu() {
    var menu = document.getElementById('auth-profile-menu');
    if (!menu) return;
    var isOpen = menu.classList.contains('apm-visible');
    if (isOpen) {
        _closeProfileMenu();
        return;
    }
    // Position the menu above the badge
    var badge = document.querySelector('.auth-user-badge');
    if (!badge) return;
    var rect = badge.getBoundingClientRect();
    menu.style.left = rect.left + 'px';
    menu.style.bottom = (window.innerHeight - rect.top + 6) + 'px';
    menu.style.top = 'auto';
    menu.classList.add('apm-visible');
    document.querySelector('.auth-badge-wrap').classList.add('open');
    setTimeout(function() {
        document.addEventListener('click', _profileOutsideClick);
    }, 0);
}

function _closeProfileMenu() {
    var menu = document.getElementById('auth-profile-menu');
    if (menu) menu.classList.remove('apm-visible');
    var wrap = document.querySelector('.auth-badge-wrap');
    if (wrap) wrap.classList.remove('open');
    document.removeEventListener('click', _profileOutsideClick);
}

function _profileOutsideClick(e) {
    var menu = document.getElementById('auth-profile-menu');
    var badge = document.querySelector('.auth-user-badge');
    if (menu && !menu.contains(e.target) && badge && !badge.contains(e.target)) {
        _closeProfileMenu();
    }
}

// -- Risk Radar SVG Builder -----------------------------------
function riskRadar(dimensions, opts) {
    opts = opts || {};
    var size = opts.size || 200;
    var cx = size / 2, cy = size / 2;
    var r = size / 2 - 28;
    var n = dimensions.length;
    if (n < 3) return '';

    var angleStep = (2 * Math.PI) / n;
    var startAngle = -Math.PI / 2;

    var svg = '<svg width="' + size + '" height="' + size + '" viewBox="0 0 ' + size + ' ' + size + '">';

    // Background rings
    [0.25, 0.5, 0.75, 1].forEach(function(pct) {
        var pr = r * pct;
        var pts = [];
        for (var i = 0; i < n; i++) {
            var a = startAngle + i * angleStep;
            pts.push((cx + pr * Math.cos(a)).toFixed(1) + ',' + (cy + pr * Math.sin(a)).toFixed(1));
        }
        svg += '<polygon points="' + pts.join(' ') + '" fill="none" stroke="var(--border)" stroke-width="0.7" opacity="0.6"/>';
    });

    // Axis lines
    for (var i = 0; i < n; i++) {
        var a = startAngle + i * angleStep;
        var ex = cx + r * Math.cos(a), ey = cy + r * Math.sin(a);
        svg += '<line x1="' + cx + '" y1="' + cy + '" x2="' + ex.toFixed(1) + '" y2="' + ey.toFixed(1) + '" stroke="var(--border)" stroke-width="0.5" opacity="0.4"/>';
    }

    // Data polygon
    var dataPts = [];
    dimensions.forEach(function(d, i) {
        var val = Math.max(0, Math.min(1, (d.value || 0) / (d.max || 100)));
        var a = startAngle + i * angleStep;
        dataPts.push((cx + r * val * Math.cos(a)).toFixed(1) + ',' + (cy + r * val * Math.sin(a)).toFixed(1));
    });
    svg += '<polygon points="' + dataPts.join(' ') + '" fill="var(--accent)" fill-opacity="0.15" stroke="var(--accent)" stroke-width="2" stroke-linejoin="round"/>';

    // Data dots + labels
    dimensions.forEach(function(d, i) {
        var val = Math.max(0, Math.min(1, (d.value || 0) / (d.max || 100)));
        var a = startAngle + i * angleStep;
        var dx = cx + r * val * Math.cos(a), dy = cy + r * val * Math.sin(a);
        var lx = cx + (r + 14) * Math.cos(a), ly = cy + (r + 14) * Math.sin(a);
        var col = val > 0.7 ? 'var(--red)' : val > 0.4 ? 'var(--yellow)' : 'var(--green)';
        svg += '<circle cx="' + dx.toFixed(1) + '" cy="' + dy.toFixed(1) + '" r="4" fill="' + col + '" stroke="var(--bg-1)" stroke-width="1.5"/>';
        var anchor = Math.abs(Math.cos(a)) < 0.3 ? 'middle' : Math.cos(a) > 0 ? 'start' : 'end';
        svg += '<text x="' + lx.toFixed(1) + '" y="' + (ly + 3).toFixed(1) + '" text-anchor="' + anchor + '" fill="var(--text-2)" font-size="9">' + esc(d.label) + '</text>';
    });

    svg += '</svg>';
    return '<div class="radar-wrap">' + svg + '</div>';
}

// -- Risk Dimension Pills -------------------------------------
function riskDims(dims) {
    var h = '<div class="risk-dims">';
    dims.forEach(function(d) {
        var cls = d.level === 'bad' ? 'risk-bad' : d.level === 'warn' ? 'risk-warn' : 'risk-ok';
        h += '<div class="risk-dim ' + cls + '"><span class="rd-name">' + esc(d.name) + '</span><span class="rd-val">' + esc(d.value) + '</span></div>';
    });
    h += '</div>';
    return h;
}

// -- Ingestion Timeline Builder -------------------------------
function ingestTimeline(steps) {
    var doneCount = steps.filter(function(s) { return s.state === 'done'; }).length;
    var total = steps.length;
    var pct = total ? Math.round((doneCount / total) * 100) : 0;
    var h = '<div class="ingest-timeline"><div class="it-line"><div class="it-line-fill" style="width:' + pct + '%"></div></div>';
    steps.forEach(function(s) {
        var cls = s.state === 'done' ? 'done' : s.state === 'active' ? 'active' : s.state === 'failed' ? 'failed' : '';
        var icon = s.state === 'done' ? '\u2713' : s.state === 'active' ? '\u25CF' : s.state === 'failed' ? '\u2717' : '\u25CB';
        h += '<div class="it-step ' + cls + '"><div class="it-dot">' + icon + '</div><div class="it-label">' + esc(s.label) + '</div></div>';
    });
    h += '</div>';
    return h;
}

// -- Snapshot Timeline Builder --------------------------------
function snapTimeline(snapshots, currentId) {
    if (!snapshots || snapshots.length < 2) return '';
    var maxFiles = 1;
    snapshots.forEach(function(s) { if ((s.file_count || 0) > maxFiles) maxFiles = s.file_count; });
    var h = '<div class="snap-timeline">';
    snapshots.forEach(function(s) {
        var pct = Math.max(15, Math.round(((s.file_count || 1) / maxFiles) * 100));
        var cls = s.id === currentId ? ' current' : '';
        var tip = (s.id || '').slice(0, 8) + ' - ' + (s.file_count || 0) + ' files';
        h += '<div class="st-bar' + cls + '" style="height:' + pct + '%" onclick="S.set(S.repo,\'' + s.id + '\');Recents.add(S.repo,\'' + s.id + '\',S.repo);toast(\'Switched\');navigate(\'overview\')" title="' + esc(tip) + '"><div class="st-tip">' + esc(tip) + '</div></div>';
    });
    h += '</div>';
    return h;
}

// -- Graph Minimap Helper (Real Implementation) ---------------
// Derives all geometry from GE's actual world coordinates (_wx, _wy)
// and the real viewport transform (GE.ox, GE.oy, GE.sc, GE.W, GE.H).
var Minimap = {
    cvs: null, ctx: null, wrap: null, vp: null,
    MW: 160, MH: 110,
    _dragging: false,
    _bounds: null,

    init: function(container) {
        if (!container) return;
        var existing = container.querySelector('.g-minimap');
        if (existing) existing.remove();
        var wrap = document.createElement('div');
        wrap.className = 'g-minimap';
        wrap.innerHTML = '<canvas></canvas><div class="mm-viewport"></div>';
        container.appendChild(wrap);
        this.cvs = wrap.querySelector('canvas');
        this.ctx = this.cvs.getContext('2d');
        this.wrap = wrap;
        this.vp = wrap.querySelector('.mm-viewport');
        this.cvs.width = this.MW;
        this.cvs.height = this.MH;
        var self = this;

        // Click to pan
        wrap.addEventListener('mousedown', function(e) {
            if (!GE || !GE.flatNodes || !GE.flatNodes.length) return;
            e.preventDefault();
            self._dragging = true;
            self._handlePan(e);
        });
        document.addEventListener('mousemove', function(e) {
            if (self._dragging) { e.preventDefault(); self._handlePan(e); }
        });
        document.addEventListener('mouseup', function() { self._dragging = false; });
    },

    // Compute world-space bounding box from actual rendered positions
    _worldBounds: function() {
        var nodes = GE.flatNodes;
        if (!nodes || !nodes.length) return null;
        var minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (var i = 0; i < nodes.length; i++) {
            var n = nodes[i];
            if (n._wx === undefined || n._wy === undefined) continue;
            var l = n._wx - n.r, r = n._wx + n.r;
            var t = n._wy - n.r, b = n._wy + n.r;
            if (l < minX) minX = l;
            if (r > maxX) maxX = r;
            if (t < minY) minY = t;
            if (b > maxY) maxY = b;
        }
        if (minX === Infinity) return null;
        // Add padding
        var pad = 20;
        return { x: minX - pad, y: minY - pad, w: (maxX - minX) + pad * 2, h: (maxY - minY) + pad * 2 };
    },

    // Map world coordinate to minimap pixel
    _toMini: function(wx, wy, bounds) {
        var scaleX = (this.MW - 12) / bounds.w;
        var scaleY = (this.MH - 12) / bounds.h;
        var s = Math.min(scaleX, scaleY);
        var offX = (this.MW - bounds.w * s) / 2;
        var offY = (this.MH - bounds.h * s) / 2;
        return { x: offX + (wx - bounds.x) * s, y: offY + (wy - bounds.y) * s, s: s };
    },

    paint: function() {
        if (!this.ctx || !GE || !GE.flatNodes) return;
        var ctx = this.ctx;
        var w = this.MW, h = this.MH;
        ctx.clearRect(0, 0, w, h);
        var nodes = GE.flatNodes;
        if (!nodes.length) return;

        var bounds = this._worldBounds();
        if (!bounds) return;
        this._bounds = bounds;

        var dark = document.documentElement.getAttribute('data-theme') === 'dark';

        // Draw module circles (non-leaf groups) from the tree
        if (GE.circles) { this._drawGroups(ctx, GE.circles, 0, 0, bounds, dark, 0); }

        // Draw edges
        ctx.lineWidth = 0.5;
        ctx.globalAlpha = 0.25;
        ctx.strokeStyle = dark ? 'rgba(124,106,255,0.4)' : 'rgba(98,70,234,0.35)';
        for (var i = 0; i < GE.edges.length; i++) {
            var e = GE.edges[i];
            var src = GE._find(e.srcId), tgt = GE._find(e.tgtId);
            if (!src || !tgt || src._wx === undefined || tgt._wx === undefined) continue;
            var sp = this._toMini(src._wx, src._wy, bounds);
            var tp = this._toMini(tgt._wx, tgt._wy, bounds);
            ctx.beginPath(); ctx.moveTo(sp.x, sp.y); ctx.lineTo(tp.x, tp.y); ctx.stroke();
        }
        ctx.globalAlpha = 1;

        // Draw leaf nodes
        for (var j = 0; j < nodes.length; j++) {
            var n = nodes[j];
            if (n._wx === undefined || n._wy === undefined) continue;
            var p = this._toMini(n._wx, n._wy, bounds);
            var nr = Math.max(1.5, n.r * p.s);
            nr = Math.min(nr, 5); // cap for readability
            ctx.beginPath();
            ctx.arc(p.x, p.y, nr, 0, Math.PI * 2);
            var isSel = (n === GE.sel);
            if (isSel) {
                ctx.fillStyle = dark ? '#a78bfa' : '#6246ea';
                ctx.fill();
                ctx.strokeStyle = '#fff'; ctx.lineWidth = 1; ctx.stroke();
            } else {
                ctx.fillStyle = dark ? 'rgba(148,163,184,0.7)' : 'rgba(71,85,105,0.6)';
                ctx.fill();
            }
        }

        // Draw viewport indicator
        this._drawViewport(bounds, dark);
    },

    // Draw non-leaf group circles faintly
    _drawGroups: function(ctx, node, px, py, bounds, dark, depth) {
        var x = px + node.x, y = py + node.y;
        if (!node.isLeaf && depth > 0) {
            var p = this._toMini(node._wx !== undefined ? node._wx : x, node._wy !== undefined ? node._wy : y, bounds);
            var gr = Math.max(3, node.r * p.s);
            ctx.beginPath(); ctx.arc(p.x, p.y, gr, 0, Math.PI * 2);
            ctx.strokeStyle = dark ? 'rgba(100,150,230,0.18)' : 'rgba(50,80,160,0.12)';
            ctx.lineWidth = 0.7; ctx.stroke();
        }
        if (!node.isLeaf && node.children) {
            for (var i = 0; i < node.children.length; i++) {
                this._drawGroups(ctx, node.children[i], x, y, bounds, dark, depth + 1);
            }
        }
    },

    // Draw the viewport rectangle showing what's visible on main canvas
    _drawViewport: function(bounds, dark) {
        if (!this.vp || !GE) return;
        var sc = GE.sc || 1;
        var viewW = GE.W || 800, viewH = GE.H || 600;

        // Visible world-space region
        var worldLeft = -GE.ox / sc;
        var worldTop = -GE.oy / sc;
        var worldRight = (viewW - GE.ox) / sc;
        var worldBottom = (viewH - GE.oy) / sc;

        // Map to minimap coordinates
        var tl = this._toMini(worldLeft, worldTop, bounds);
        var br = this._toMini(worldRight, worldBottom, bounds);

        var vpL = Math.max(0, tl.x);
        var vpT = Math.max(0, tl.y);
        var vpW = Math.min(this.MW, br.x) - vpL;
        var vpH = Math.min(this.MH, br.y) - vpT;

        // If viewport covers everything, hide indicator
        if (vpW >= this.MW - 2 && vpH >= this.MH - 2) {
            this.vp.style.display = 'none';
            return;
        }

        this.vp.style.display = '';
        this.vp.style.left = vpL + 'px';
        this.vp.style.top = vpT + 'px';
        this.vp.style.width = Math.max(12, vpW) + 'px';
        this.vp.style.height = Math.max(10, vpH) + 'px';
    },

    // Handle pan from minimap click/drag
    _handlePan: function(e) {
        if (!this._bounds || !GE) return;
        var rect = this.wrap.getBoundingClientRect();
        var mx = e.clientX - rect.left;
        var my = e.clientY - rect.top;

        var bounds = this._bounds;
        var scaleX = (this.MW - 12) / bounds.w;
        var scaleY = (this.MH - 12) / bounds.h;
        var s = Math.min(scaleX, scaleY);
        var offX = (this.MW - bounds.w * s) / 2;
        var offY = (this.MH - bounds.h * s) / 2;

        // Convert minimap pixel back to world coords
        var worldX = bounds.x + (mx - offX) / s;
        var worldY = bounds.y + (my - offY) / s;

        // Center the main graph viewport on this world position
        var viewW = GE.W || 800, viewH = GE.H || 600;
        GE.ox = viewW / 2 - worldX * GE.sc;
        GE.oy = viewH / 2 - worldY * GE.sc;
        GE.paint();
    }
};

// ══════════════════════════════════════════════════════════════
// Phase 7 — Temporal Awareness & Trends
// Sparklines, trend badges, notifications, number animation, onboarding
// ══════════════════════════════════════════════════════════════

// -- Sparkline SVG Builder ------------------------------------
function sparkline(values, opts) {
    if (!values || values.length < 2) return '';
    opts = opts || {};
    var w = opts.width || 48, h = opts.height || 18;
    var min = Infinity, max = -Infinity;
    for (var i = 0; i < values.length; i++) {
        if (values[i] < min) min = values[i];
        if (values[i] > max) max = values[i];
    }
    var range = max - min || 1;
    var pad = 2;
    var pts = [];
    for (var j = 0; j < values.length; j++) {
        var x = pad + (j / (values.length - 1)) * (w - pad * 2);
        var y = h - pad - ((values[j] - min) / range) * (h - pad * 2);
        pts.push(x.toFixed(1) + ',' + y.toFixed(1));
    }
    var col = opts.color || 'var(--accent)';
    var svg = '<svg width="' + w + '" height="' + h + '" viewBox="0 0 ' + w + ' ' + h + '" fill="none">';
    svg += '<polyline points="' + pts.join(' ') + '" stroke="' + col + '" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" fill="none"/>';
    // End dot
    var lastPt = pts[pts.length - 1].split(',');
    svg += '<circle cx="' + lastPt[0] + '" cy="' + lastPt[1] + '" r="2" fill="' + col + '"/>';
    svg += '</svg>';
    return '<span class="sparkline">' + svg + '</span>';
}

// -- Trend Badge Builder --------------------------------------
// direction: 'up' | 'down' | 'stable'
// inverted: true means "up is good" (e.g. health score)
function trendBadge(direction, label, inverted) {
    var cls = 'trend-badge trend-' + direction;
    if (inverted) cls += ' inverted';
    var arrow = direction === 'up' ? '\u2191' : direction === 'down' ? '\u2193' : '\u2192';
    return '<div class="' + cls + '">' + arrow + ' ' + esc(label) + '</div>';
}

// Compute trend from array of numbers
function computeTrend(values) {
    if (!values || values.length < 2) return { direction: 'stable', delta: 0 };
    var first = values[0], last = values[values.length - 1];
    var delta = last - first;
    if (Math.abs(delta) < 0.5) return { direction: 'stable', delta: 0 };
    return { direction: delta > 0 ? 'up' : 'down', delta: delta };
}

// -- Diff Delta Badge -----------------------------------------
function diffDelta(oldVal, newVal, inverted) {
    var delta = newVal - oldVal;
    if (delta === 0) return '<span class="diff-delta dd-neutral">\u2192 0</span>';
    var isGood = inverted ? delta > 0 : delta < 0;
    var cls = isGood ? 'dd-good' : 'dd-bad';
    var arrow = delta > 0 ? '\u2191+' : '\u2193';
    return '<span class="diff-delta ' + cls + '">' + arrow + Math.abs(delta) + '</span>';
}

// -- Animated Number Updater ----------------------------------
function animateNumber(el, targetVal, duration) {
    if (!el) return;
    var startVal = parseFloat(el.textContent) || 0;
    if (startVal === targetVal) return;
    duration = duration || 400;
    var start = performance.now();
    var isInt = Number.isInteger(targetVal);
    var improved = targetVal < startVal; // fewer = better for most metrics
    function step(now) {
        var t = Math.min(1, (now - start) / duration);
        var ease = 1 - Math.pow(1 - t, 3);
        var current = startVal + (targetVal - startVal) * ease;
        el.textContent = isInt ? Math.round(current) : current.toFixed(1);
        if (t < 1) requestAnimationFrame(step);
        else {
            el.textContent = isInt ? targetVal : targetVal.toFixed(1);
            el.classList.add(improved ? 'flash-good' : 'flash-bad');
            setTimeout(function() { el.classList.remove('flash-good', 'flash-bad'); }, 700);
        }
    }
    el.classList.add('num-animate');
    requestAnimationFrame(step);
}

// -- Notification Center --------------------------------------
var Notif = {
    items: [],
    _loaded: false,

    _load: function() {
        if (this._loaded) return;
        this._loaded = true;
        try {
            var raw = localStorage.getItem('eidos_notifs');
            if (raw) this.items = JSON.parse(raw);
        } catch(e) { this.items = []; }
    },

    _save: function() {
        localStorage.setItem('eidos_notifs', JSON.stringify(this.items.slice(0, 30)));
    },

    _updateBadge: function() {
        var ct = $('notif-count');
        if (!ct) return;
        var unread = this.items.filter(function(n) { return !n.read; }).length;
        ct.textContent = unread;
        ct.classList.toggle('visible', unread > 0);
    },

    push: function(icon, title, body) {
        this._load();
        this.items.unshift({ icon: icon, title: title, body: body || '', time: Date.now(), read: false });
        this._save();
        this._updateBadge();
        this._render();
    },

    toggle: function() {
        var panel = $('notif-panel');
        if (!panel) return;
        var isOpen = panel.classList.contains('open');
        if (isOpen) {
            panel.classList.remove('open');
        } else {
            this._load();
            this._markRead();
            this._render();
            panel.classList.add('open');
        }
    },

    _markRead: function() {
        var changed = false;
        this.items.forEach(function(n) { if (!n.read) { n.read = true; changed = true; } });
        if (changed) { this._save(); this._updateBadge(); }
    },

    clear: function() {
        this.items = [];
        this._save();
        this._updateBadge();
        this._render();
    },

    _render: function() {
        var list = $('notif-list');
        if (!list) return;
        if (!this.items.length) {
            list.innerHTML = '<div class="np-empty">No notifications yet</div>';
            return;
        }
        var h = '';
        this.items.slice(0, 20).forEach(function(n) {
            var ago = Notif._ago(n.time);
            h += '<div class="np-item"><span class="np-icon">' + (n.icon || '\u2139\uFE0F') + '</span><div class="np-body"><div class="np-title">' + esc(n.title) + '</div>';
            if (n.body) h += '<div style="font-size:11px;color:var(--text-3)">' + esc(n.body) + '</div>';
            h += '<div class="np-time">' + ago + '</div></div></div>';
        });
        list.innerHTML = h;
    },

    _ago: function(ts) {
        var diff = Math.round((Date.now() - ts) / 1000);
        if (diff < 60) return diff + 's ago';
        if (diff < 3600) return Math.round(diff / 60) + 'm ago';
        if (diff < 86400) return Math.round(diff / 3600) + 'h ago';
        return Math.round(diff / 86400) + 'd ago';
    },

    init: function() {
        this._load();
        this._updateBadge();
    }
};

// -- Onboarding Tour ------------------------------------------
var Tour = {
    steps: [
        { target: '.sidebar-nav', title: 'Navigation', body: 'Switch between analysis views here. Start with Repositories to set up your project.' },
        { target: '.nav-btn[data-p="overview"]', title: 'Overview', body: 'Get a high-level summary of your codebase: symbols, health score, and risk radar.' },
        { target: '.nav-btn[data-p="graph"]', title: 'Graph Explorer', body: 'Visualize code relationships. Search nodes, find paths, and color by complexity.' },
        { target: '.nav-btn[data-p="hotspots"]', title: 'Hotspots', body: 'Identify risky code: high churn combined with high complexity. KPIs explain every metric.' },
        { target: '#notif-bell', title: 'Notifications', body: 'Get alerted when ingestion completes or risk thresholds are crossed.' },
        { target: '.shortcut-hint', title: 'Command Palette', body: 'Press Ctrl+K anytime for quick navigation and actions. Press / in Graph for search.' }
    ],
    current: -1,

    start: function() {
        this.current = 0;
        $('tour-overlay').classList.add('active');
        this._show();
    },

    next: function() {
        this.current++;
        if (this.current >= this.steps.length) { this.finish(); return; }
        this._show();
    },

    skip: function() {
        this.finish();
    },

    finish: function() {
        $('tour-overlay').classList.remove('active');
        $('tour-tip').classList.remove('active');
        this.current = -1;
        localStorage.setItem('eidos_onboarded', '1');
    },

    restart: function() {
        localStorage.removeItem('eidos_onboarded');
        this.start();
    },

    _show: function() {
        var step = this.steps[this.current];
        if (!step) { this.finish(); return; }
        var tip = $('tour-tip');
        $('tt-title').textContent = step.title;
        $('tt-body').textContent = step.body;
        $('tt-step').textContent = (this.current + 1) + ' / ' + this.steps.length;
        $('tt-next').textContent = this.current === this.steps.length - 1 ? 'Done' : 'Next';

        // Position near target
        var target = document.querySelector(step.target);
        if (target) {
            var rect = target.getBoundingClientRect();
            var tipEl = tip;
            tipEl.classList.add('active');
            // Position to the right of target, or below if no space
            var left = rect.right + 12;
            var top = rect.top;
            if (left + 320 > window.innerWidth) {
                left = Math.max(12, rect.left);
                top = rect.bottom + 10;
            }
            if (top + 180 > window.innerHeight) {
                top = Math.max(12, rect.top - 180);
            }
            tipEl.style.left = left + 'px';
            tipEl.style.top = top + 'px';
        } else {
            // Fallback: center
            tip.classList.add('active');
            tip.style.left = '50%';
            tip.style.top = '50%';
            tip.style.transform = 'translate(-50%, -50%)';
        }
    }
};

// -- Trend Data Loader ----------------------------------------
// Fetches metrics across multiple snapshots for trend sparklines
var TrendData = {
    _cache: null,
    _repoId: null,

    load: function(repoId, callback) {
        if (this._cache && this._repoId === repoId) { callback(this._cache); return; }
        this._repoId = repoId;
        var self = this;
        API.get('/repos/' + repoId + '/snapshots').then(function(d) {
            var snaps = (d.items || d.snapshots || d || []).filter(function(s) { return s.status === 'completed'; });
            if (snaps.length < 2) { self._cache = null; callback(null); return; }
            // Take last 8 snapshots max for trend
            snaps = snaps.slice(-8);
            // Fetch overview for each snapshot to get comparable metrics
            var promises = snaps.map(function(snap) {
                return API.get('/repos/' + repoId + '/snapshots/' + snap.id + '/overview').then(function(ov) {
                    return { id: snap.id, symbols: ov.total_symbols || 0, edges: ov.total_edges || 0, modules: ov.total_modules || 0, files: ov.total_files || snap.file_count || 0 };
                }).catch(function() {
                    return { id: snap.id, symbols: 0, edges: 0, modules: 0, files: snap.file_count || 0 };
                });
            });
            Promise.all(promises).then(function(results) {
                self._cache = results;
                callback(results);
            }).catch(function() { self._cache = null; callback(null); });
        }).catch(function() { self._cache = null; callback(null); });
    },

    // Get array of values for a metric across snapshots
    metric: function(data, key) {
        if (!data) return [];
        return data.map(function(d) { return d[key] || 0; });
    }
};

// ══════════════════════════════════════════════════════════════
// Phase 8 — Accessibility & Performance Hardening
// Perf budget, preferences, ARIA announcements, keyboard nav
// ══════════════════════════════════════════════════════════════

// -- ARIA Live Announcements ----------------------------------
function announce(msg) {
    var el = document.getElementById('aria-live');
    if (el) { el.textContent = ''; setTimeout(function() { el.textContent = msg; }, 50); }
}

// -- Performance Budget Instrumentation -----------------------
var Perf = {
    enabled: localStorage.getItem('eidos_perf') === '1',
    budgets: {
        'page.render': 1200,
        'graph.paint': 16,
        'api.call': 3000
    },
    _badge: null,
    _marks: {},

    toggle: function() {
        this.enabled = !this.enabled;
        localStorage.setItem('eidos_perf', this.enabled ? '1' : '0');
        if (this._badge) this._badge.classList.toggle('visible', this.enabled);
        toast(this.enabled ? 'Perf monitoring ON' : 'Perf monitoring OFF');
    },

    mark: function(name) {
        if (!this.enabled) return;
        this._marks[name] = performance.now();
    },

    measure: function(name) {
        if (!this.enabled || !this._marks[name]) return;
        var duration = performance.now() - this._marks[name];
        delete this._marks[name];
        var budget = this.budgets[name];
        var exceeded = budget && duration > budget;
        if (exceeded) {
            console.warn('[Perf] \u26A0 ' + name + ': ' + duration.toFixed(1) + 'ms exceeded ' + budget + 'ms budget');
        } else {
            console.log('[Perf] \u2713 ' + name + ': ' + duration.toFixed(1) + 'ms');
        }
        this._updateBadge(name, duration, exceeded);
        return duration;
    },

    _updateBadge: function(name, duration, exceeded) {
        if (!this._badge) {
            this._badge = document.createElement('div');
            this._badge.className = 'perf-badge' + (this.enabled ? ' visible' : '');
            document.body.appendChild(this._badge);
        }
        this._badge.textContent = name.split('.').pop() + ': ' + duration.toFixed(0) + 'ms';
        this._badge.classList.toggle('warn', exceeded);
        var badge = this._badge;
        setTimeout(function() { badge.textContent = ''; badge.classList.remove('warn'); }, 3000);
    },

    init: function() {
        if (this.enabled) {
            this._badge = document.createElement('div');
            this._badge.className = 'perf-badge visible';
            document.body.appendChild(this._badge);
        }
    }
};

// -- Persistent User Preferences ------------------------------
var Prefs = {
    _key: 'eidos_prefs',
    _data: null,

    _load: function() {
        if (this._data) return;
        try {
            this._data = JSON.parse(localStorage.getItem(this._key)) || {};
        } catch(e) { this._data = {}; }
    },

    get: function(key, fallback) {
        this._load();
        return this._data[key] !== undefined ? this._data[key] : fallback;
    },

    set: function(key, value) {
        this._load();
        this._data[key] = value;
        localStorage.setItem(this._key, JSON.stringify(this._data));
    },

    remove: function(key) {
        this._load();
        delete this._data[key];
        localStorage.setItem(this._key, JSON.stringify(this._data));
    },

    reset: function() {
        this._data = {};
        localStorage.removeItem(this._key);
    }
};

// -- Keyboard Navigation Helpers ------------------------------
// Make table rows navigable with J/K keys when focused inside a table
function initTableKeyNav(tableEl) {
    if (!tableEl) return;
    var rows = tableEl.querySelectorAll('tbody tr');
    rows.forEach(function(row) { row.setAttribute('tabindex', '0'); });
    tableEl.addEventListener('keydown', function(e) {
        if (e.target.tagName !== 'TR') return;
        var rows = Array.from(tableEl.querySelectorAll('tbody tr'));
        var idx = rows.indexOf(e.target);
        if (e.key === 'j' || e.key === 'ArrowDown') {
            e.preventDefault();
            if (idx < rows.length - 1) rows[idx + 1].focus();
        } else if (e.key === 'k' || e.key === 'ArrowUp') {
            e.preventDefault();
            if (idx > 0) rows[idx - 1].focus();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            e.target.click();
        }
    });
}

// ══════════════════════════════════════════════════════════════
// Phase 9 — Platform & Sharing
// ══════════════════════════════════════════════════════════════

// ── 9.1 Deep-Link URLs ────────────────────────────────────────
var DeepLink = {
    // Encode current state into URL hash
    encode: function(extra) {
        var params = {};
        if (S.repo) params.repo = S.repo;
        if (S.snap) params.snap = S.snap;
        // Get current page from active nav button
        var activeBtn = document.querySelector('.nav-btn.active');
        if (activeBtn) params.page = activeBtn.getAttribute('data-p');
        // Merge any extra state
        if (extra) {
            Object.keys(extra).forEach(function(k) {
                if (extra[k] !== undefined && extra[k] !== null && extra[k] !== '') {
                    params[k] = extra[k];
                }
            });
        }
        var hash = Object.keys(params).map(function(k) {
            return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
        }).join('&');
        return hash;
    },

    // Update the URL hash silently (no page reload)
    push: function(extra) {
        var hash = this.encode(extra);
        if (hash) {
            history.replaceState(null, '', '#' + hash);
        }
    },

    // Parse the current URL hash into an object
    parse: function() {
        var hash = window.location.hash.slice(1);
        if (!hash) return null;
        var params = {};
        hash.split('&').forEach(function(pair) {
            var parts = pair.split('=');
            if (parts.length === 2) {
                params[decodeURIComponent(parts[0])] = decodeURIComponent(parts[1]);
            }
        });
        return Object.keys(params).length ? params : null;
    },

    // Restore state from URL hash on page load
    restore: function() {
        var p = this.parse();
        if (!p) return false;
        if (p.repo) S.set(p.repo, p.snap || null);
        if (p.page) {
            setTimeout(function() { navigate(p.page); }, 100);
        }
        return true;
    },

    // Get a full shareable URL
    getUrl: function(extra) {
        var base = window.location.origin + window.location.pathname;
        var hash = this.encode(extra);
        return base + '#' + hash;
    },

    // Copy current deep link to clipboard
    copy: function(extra) {
        var url = this.getUrl(extra);
        if (navigator.clipboard) {
            navigator.clipboard.writeText(url).then(function() {
                toast('Link copied to clipboard');
            }).catch(function() {
                _fallbackCopy(url);
            });
        } else {
            _fallbackCopy(url);
        }
    }
};

function _fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); toast('Link copied'); }
    catch(e) { toast('Failed to copy link', false); }
    document.body.removeChild(ta);
}

// Generate the deep-link button HTML
function deepLinkBtn(extra) {
    var extraJson = extra ? JSON.stringify(extra).replace(/'/g, "\\'") : 'null';
    return '<button class="deeplink-btn" onclick="event.stopPropagation();DeepLink.copy(' + extraJson + ');this.classList.add(\'deeplink-copied\');var _b=this;setTimeout(function(){_b.classList.remove(\'deeplink-copied\')},1200)" title="Copy shareable link"><svg viewBox="0 0 16 16" fill="currentColor"><path d="M4.715 6.542L3.343 7.914a3 3 0 104.243 4.243l1.828-1.829A3 3 0 008.586 5.5L8 6.086a1 1 0 00-.154.199 2 2 0 01.861 3.337L6.88 11.45a2 2 0 11-2.83-2.83l.793-.792a4.018 4.018 0 01-.128-1.287z"/><path d="M6.586 4.672A3 3 0 007.414 9.5l.775-.776a2 2 0 01-.896-3.346L9.12 3.55a2 2 0 112.83 2.83l-.793.792c.112.42.155.855.128 1.287l1.372-1.372a3 3 0 10-4.243-4.243L6.586 4.672z"/></svg> Share</button>';
}

// ── 9.2 PDF Report Generation ─────────────────────────────────
function openPdfDialog() {
    var overlay = $('pdf-overlay');
    if (overlay) overlay.classList.add('open');
}

function closePdfDialog() {
    var overlay = $('pdf-overlay');
    if (overlay) overlay.classList.remove('open');
    // Reset progress
    var prog = $('pdf-progress');
    if (prog) prog.classList.remove('active');
}

function generatePdfReport() {
    var prog = $('pdf-progress');
    var fill = $('pdf-progress-fill');
    var text = $('pdf-progress-text');
    var btn = $('pdf-generate-btn');
    if (!prog || !fill || !text || !btn) return;

    btn.disabled = true;
    btn.textContent = 'Generating...';
    prog.classList.add('active');
    fill.style.width = '10%';
    text.textContent = 'Collecting data...';

    // Gather report data
    var sections = {
        kpis: $('pdf-kpis') && $('pdf-kpis').checked,
        hotspots: $('pdf-hotspots') && $('pdf-hotspots').checked,
        deps: $('pdf-deps') && $('pdf-deps').checked,
        actions: $('pdf-actions') && $('pdf-actions').checked,
        graph: $('pdf-graph') && $('pdf-graph').checked
    };

    // Simulate progressive generation (real impl would call backend export)
    var steps = [
        { pct: 25, msg: 'Fetching analysis data...', delay: 400 },
        { pct: 50, msg: 'Building report structure...', delay: 600 },
        { pct: 75, msg: 'Rendering content...', delay: 500 },
        { pct: 100, msg: 'Finalizing...', delay: 300 }
    ];

    var stepIdx = 0;
    function nextStep() {
        if (stepIdx >= steps.length) {
            // Try backend markdown export as printable report
            _downloadReport(sections);
            return;
        }
        var step = steps[stepIdx++];
        fill.style.width = step.pct + '%';
        text.textContent = step.msg;
        setTimeout(nextStep, step.delay);
    }
    nextStep();
}

function _downloadReport(sections) {
    // Use the markdown export endpoint as the report source
    if (S.ok()) {
        API.download(S.path() + '/export/markdown', 'eidos-report.md').then(function() {
            toast('Report downloaded (Markdown format)');
            closePdfDialog();
            var btn = $('pdf-generate-btn');
            if (btn) { btn.disabled = false; btn.textContent = 'Generate Report'; }
        }).catch(function(e) {
            // Fallback: generate a client-side text report
            _generateClientReport(sections);
        });
    } else {
        _generateClientReport(sections);
    }
}

function _generateClientReport(sections) {
    var report = '# Eidos Analysis Report\n\n';
    report += '**Generated:** ' + new Date().toLocaleString() + '\n';
    report += '**Repository:** ' + (S.repo || 'N/A') + '\n';
    report += '**Snapshot:** ' + (S.snap ? S.snap.slice(0, 8) : 'N/A') + '\n\n';
    report += '---\n\n';

    if (sections.kpis) {
        report += '## Summary\n\n';
        report += 'This report contains the current analysis state for the selected snapshot.\n\n';
    }
    if (sections.hotspots) {
        report += '## Hotspots\n\n';
        report += 'See the Hotspots page for detailed method-level risk analysis.\n\n';
    }
    if (sections.deps) {
        report += '## Dependencies\n\n';
        report += 'See the Dependencies page for package health details.\n\n';
    }
    if (sections.actions) {
        report += '## Recommended Actions\n\n';
        report += '- Review high-risk hotspots\n';
        report += '- Address coupling concerns\n';
        report += '- Remove identified dead code\n\n';
    }
    report += '---\n\n*Generated by Eidos Code Intelligence Platform*\n';

    // Download as file
    var blob = new Blob([report], { type: 'text/markdown' });
    var url = URL.createObjectURL(blob);
    var a = document.createElement('a');
    a.href = url;
    a.download = 'eidos-report.md';
    a.click();
    URL.revokeObjectURL(url);

    toast('Report generated (Markdown)');
    closePdfDialog();
    var btn = $('pdf-generate-btn');
    if (btn) { btn.disabled = false; btn.textContent = 'Generate Report'; }
}

// ── 9.3 Mobile Navigation Toggle ─────────────────────────────
function toggleMobileNav() {
    var sidebar = document.querySelector('.sidebar');
    if (sidebar) sidebar.classList.toggle('mobile-open');
}

// Close mobile nav when navigating
var _origNavigate = typeof navigate === 'function' ? navigate : null;

// ── 9.4 Ambient Status Indicators ────────────────────────────
var Ambient = {
    _interval: null,

    init: function() {
        this._interval = setInterval(this.update.bind(this), 5000);
        this.update();
    },

    update: function() {
        var border = $('ambient-border');
        if (!border) return;

        // Determine risk level based on available page data
        // This is a lightweight ambient cue
        if (!S.ok()) {
            border.setAttribute('data-risk', 'neutral');
            return;
        }

        // Check status bar for ingestion state
        var statusBar = document.querySelector('.status-bar');
        var sbSnap = $('sb-snap');
        if (sbSnap && sbSnap.textContent.indexOf('ingesting') !== -1) {
            if (statusBar) statusBar.classList.add('ingesting');
        } else {
            if (statusBar) statusBar.classList.remove('ingesting');
        }

        // Use stored risk preference if available
        var storedRisk = Prefs.get('ambientRisk');
        if (storedRisk) {
            border.setAttribute('data-risk', storedRisk);
        }
    },

    setRisk: function(level) {
        Prefs.set('ambientRisk', level);
        var border = $('ambient-border');
        if (border) border.setAttribute('data-risk', level);
    }
};

// ── 9.5 Presence (Scaffold for future WebSocket collab) ──────
var Presence = {
    _users: [],

    init: function() {
        // Scaffold: In production this would connect via WebSocket
        // For now, show empty presence unless manually set for demo
    },

    setUsers: function(users) {
        this._users = users || [];
        this._render();
    },

    _render: function() {
        var container = document.querySelector('.presence-group');
        if (!container) return;
        if (!this._users.length) {
            container.innerHTML = '';
            return;
        }
        var h = '';
        this._users.forEach(function(u) {
            var initials = (u.name || 'U').split(' ').map(function(w) { return w[0]; }).join('').toUpperCase().slice(0, 2);
            h += '<div class="presence-avatar" data-tooltip="' + esc(u.name + (u.page ? ' viewing ' + u.page : '')) + '" style="background:' + (u.color || 'var(--accent)') + '">' + initials + '</div>';
        });
        container.innerHTML = h;
    }
};

// ── Update navigate to push deep links ───────────────────────
(function() {
    // Patch navigate to update URL hash on page change
    var _patchInterval = setInterval(function() {
        if (typeof navigate !== 'function') return;
        clearInterval(_patchInterval);

        var _originalNav = navigate;
        // We can't easily override navigate since it's declared with function keyword
        // Instead, let's use a MutationObserver on the nav buttons to track page changes
        document.addEventListener('click', function(e) {
            var btn = e.target.closest('.nav-btn');
            if (btn) {
                var page = btn.getAttribute('data-p');
                if (page) {
                    setTimeout(function() { DeepLink.push(); }, 150);
                }
            }
        });
    }, 50);
})();

// ── Init Phase 9 on load ─────────────────────────────────────
(function() {
    // Ambient indicators start after a short delay
    setTimeout(function() {
        Ambient.init();
    }, 300);

    // Periodic token expiry check (every 60s)
    setInterval(function() {
        if (Auth.isAuthEnabled() && Auth.isLoggedIn() && Auth.isTokenExpired()) {
            Auth.clearToken();
            toast('Session expired. Please sign in again.', false);
            navigate('login');
        }
    }, 60000);
})();

