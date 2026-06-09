var API = {
    base: localStorage.getItem('eidos_url') || 'http://localhost:8000',
    setBase: function(u) { this.base = u.replace(/\/+$/, ''); localStorage.setItem('eidos_url', this.base); },
    req: function(path, method, body) {
        var opts = { method: method || 'GET', headers: { 'Content-Type': 'application/json' } };
        if (body) opts.body = JSON.stringify(body);
        return fetch(this.base + path, opts).then(function(r) {
            if (!r.ok) return r.text().then(function(t) { throw new Error(t || 'HTTP ' + r.status); });
            if (r.status === 204 || r.headers.get('content-length') === '0') return null;
            var ct = r.headers.get('content-type') || '';
            return ct.indexOf('json') !== -1 ? r.json() : r.text();
        });
    },
    get: function(p) { return this.req(p, 'GET'); },
    post: function(p, b) { return this.req(p, 'POST', b); },
    patch: function(p, b) { return this.req(p, 'PATCH', b); },
    del: function(p) { return this.req(p, 'DELETE'); },
    download: function(path, name) {
        return fetch(this.base + path).then(function(r) {
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
    var c = document.getElementById('toasts');
    var d = document.createElement('div');
    d.className = 'toast ' + (ok !== false ? 'toast-ok' : 'toast-err');
    d.textContent = m; c.appendChild(d);
    setTimeout(function() { d.remove(); }, 4000);
}
function $(id) { return document.getElementById(id); }
function html(id, h) { $(id).innerHTML = h; }
function scoreCol(v) { return v >= 80 ? 'var(--green)' : v >= 60 ? 'var(--yellow)' : 'var(--red)'; }
function grade(v) { return v >= 90 ? 'A' : v >= 80 ? 'B' : v >= 70 ? 'C' : v >= 60 ? 'D' : 'F'; }
function kindBadge(k) { var m = { class:'b-blue', method:'b-green', interface:'b-yellow', enum:'b-red', constructor:'b-blue', field:'b-muted', function:'b-green' }; return m[k] || 'b-muted'; }
function noSnap() { return '<div class="empty"><h3>No snapshot selected</h3><p>Go to Repositories and select one first.</p></div>'; }
