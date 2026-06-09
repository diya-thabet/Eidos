// Reliable force-directed graph engine using HTML5 Canvas
// Handles: physics simulation, node dragging, pan, zoom, selection, rendering
var GE = {
    nodes: [], edges: [],
    cvs: null, ctx: null,
    W: 0, H: 0,
    ox: 0, oy: 0, sc: 1,
    drag: null, pan: false, pm: null,
    hover: null, sel: null,
    running: true, raf: null, iter: 0,
    onSelect: null, onDeselect: null,

    init: function(canvas) {
        this.cvs = canvas;
        this.ctx = canvas.getContext('2d');
        var self = this;
        this.sizeCanvas();
        window.addEventListener('resize', function() { self.sizeCanvas(); });
        canvas.addEventListener('mousedown', function(e) { self.mdown(e); });
        canvas.addEventListener('mousemove', function(e) { self.mmove(e); });
        canvas.addEventListener('mouseup', function() { self.mup(); });
        canvas.addEventListener('mouseleave', function() { self.mup(); });
        canvas.addEventListener('wheel', function(e) {
            e.preventDefault();
            self.sc *= e.deltaY < 0 ? 1.1 : 0.9;
            self.sc = Math.max(0.15, Math.min(4, self.sc));
            self.paint();
        }, { passive: false });
    },

    sizeCanvas: function() {
        var p = this.cvs.parentElement;
        this.W = p.clientWidth; this.H = p.clientHeight;
        var dpr = window.devicePixelRatio || 1;
        this.cvs.width = this.W * dpr; this.cvs.height = this.H * dpr;
        this.cvs.style.width = this.W + 'px'; this.cvs.style.height = this.H + 'px';
        this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        this.paint();
    },

    clear: function() { this.nodes = []; this.edges = []; this.sel = null; this.hover = null; },

    build: function(symbols, edges) {
        this.clear();
        var map = {};
        for (var i = 0; i < symbols.length; i++) {
            var s = symbols[i];
            var n = {
                id: s.fq_name, name: s.name, kind: s.kind,
                file: s.file_path || '', sl: s.start_line, el: s.end_line, ns: s.namespace || '',
                x: (Math.random() - 0.5) * 600, y: (Math.random() - 0.5) * 450,
                vx: 0, vy: 0,
                r: s.kind === 'class' ? 16 : s.kind === 'interface' ? 14 : 9
            };
            this.nodes.push(n);
            map[s.fq_name] = n;
        }
        for (var j = 0; j < edges.length; j++) {
            var e = edges[j];
            var src = map[e.source_fq_name], tgt = map[e.target_fq_name];
            if (src && tgt && src !== tgt) this.edges.push({ s: src, t: tgt, type: e.edge_type });
        }
        this.ox = 0; this.oy = 0; this.sc = 1;
        this.iter = 0; this.running = true;
        this.simulate();
    },

    buildModules: function(modules) {
        this.clear();
        var map = {};
        for (var i = 0; i < modules.length; i++) {
            var m = modules[i];
            var parts = m.name.split('.');
            var n = {
                id: m.name, name: parts[parts.length - 1], kind: 'class',
                file: '', sl: 0, el: 0, ns: m.name,
                x: (Math.random() - 0.5) * 500, y: (Math.random() - 0.5) * 400,
                vx: 0, vy: 0,
                r: Math.max(12, Math.min(32, 8 + (m.symbol_count || 0) * 0.35))
            };
            this.nodes.push(n); map[m.name] = n;
        }
        for (var j = 0; j < modules.length; j++) {
            var deps = modules[j].depends_on || [];
            for (var k = 0; k < deps.length; k++) {
                var src = map[modules[j].name], tgt = map[deps[k]];
                if (src && tgt && src !== tgt) this.edges.push({ s: src, t: tgt, type: 'calls' });
            }
        }
        this.ox = 0; this.oy = 0; this.sc = 1;
        this.iter = 0; this.running = true;
        this.simulate();
    },

    simulate: function() {
        if (this.raf) cancelAnimationFrame(this.raf);
        var self = this;
        (function tick() {
            if (!self.running || self.iter > 300) { self.paint(); return; }
            self.iter++;
            self.step();
            self.paint();
            self.raf = requestAnimationFrame(tick);
        })();
    },

    step: function() {
        var nodes = this.nodes, edges = this.edges, N = nodes.length;
        if (N === 0) return;
        var k = Math.sqrt((800 * 600) / N) * 0.8;

        for (var i = 0; i < N; i++) { nodes[i].fx = 0; nodes[i].fy = 0; }

        // Repulsion
        for (var i = 0; i < N; i++) {
            for (var j = i + 1; j < N; j++) {
                var dx = nodes[i].x - nodes[j].x, dy = nodes[i].y - nodes[j].y;
                var d = Math.sqrt(dx * dx + dy * dy) || 0.1;
                var f = (k * k) / d;
                var fx = (dx / d) * f, fy = (dy / d) * f;
                nodes[i].fx += fx; nodes[i].fy += fy;
                nodes[j].fx -= fx; nodes[j].fy -= fy;
            }
        }

        // Attraction
        for (var e = 0; e < edges.length; e++) {
            var edge = edges[e];
            var dx = edge.t.x - edge.s.x, dy = edge.t.y - edge.s.y;
            var d = Math.sqrt(dx * dx + dy * dy) || 0.1;
            var f = (d * d) / k * 0.004;
            var fx = (dx / d) * f, fy = (dy / d) * f;
            edge.s.fx += fx; edge.s.fy += fy;
            edge.t.fx -= fx; edge.t.fy -= fy;
        }

        // Apply + center gravity
        var cool = Math.max(0.05, 1 - this.iter / 350);
        var maxD = k * 0.4 * cool;
        for (var i = 0; i < N; i++) {
            var n = nodes[i];
            if (n === this.drag) continue;
            n.fx -= n.x * 0.002; n.fy -= n.y * 0.002;
            var mag = Math.sqrt(n.fx * n.fx + n.fy * n.fy) || 0.01;
            n.x += Math.min(maxD, Math.abs(n.fx)) * (n.fx / mag);
            n.y += Math.min(maxD, Math.abs(n.fy)) * (n.fy / mag);
        }
    },

    paint: function() {
        var ctx = this.ctx, W = this.W, H = this.H;
        if (!ctx) return;
        ctx.clearRect(0, 0, W, H);
        ctx.save();
        ctx.translate(W / 2 + this.ox, H / 2 + this.oy);
        ctx.scale(this.sc, this.sc);

        var dark = document.documentElement.getAttribute('data-theme') === 'dark';

        // Draw edges
        for (var i = 0; i < this.edges.length; i++) {
            var e = this.edges[i];
            var dim = this.sel && e.s !== this.sel && e.t !== this.sel;
            ctx.globalAlpha = dim ? 0.05 : 0.5;
            ctx.beginPath();
            ctx.moveTo(e.s.x, e.s.y); ctx.lineTo(e.t.x, e.t.y);
            ctx.strokeStyle = this.edgeCol(e.type, dark);
            ctx.lineWidth = (e.type === 'inherits' || e.type === 'implements') ? 1.5 : 0.8;
            ctx.setLineDash(e.type === 'implements' ? [3, 3] : []);
            ctx.stroke();

            // Arrow
            var ang = Math.atan2(e.t.y - e.s.y, e.t.x - e.s.x);
            var ax = e.t.x - Math.cos(ang) * (e.t.r + 2), ay = e.t.y - Math.sin(ang) * (e.t.r + 2);
            ctx.beginPath();
            ctx.moveTo(ax, ay);
            ctx.lineTo(ax - 5.5 * Math.cos(ang - 0.3), ay - 5.5 * Math.sin(ang - 0.3));
            ctx.lineTo(ax - 5.5 * Math.cos(ang + 0.3), ay - 5.5 * Math.sin(ang + 0.3));
            ctx.closePath();
            ctx.fillStyle = this.edgeCol(e.type, dark);
            ctx.fill();
        }
        ctx.setLineDash([]);

        // Draw nodes
        for (var i = 0; i < this.nodes.length; i++) {
            var n = this.nodes[i];
            var isSel = n === this.sel, isHov = n === this.hover;
            var isConn = this.sel && this.connected(n, this.sel);
            var dim = this.sel && !isSel && !isConn;
            ctx.globalAlpha = dim ? 0.1 : 1;

            var col = this.nodeCol(n.kind, dark);
            if (isSel || isHov) { ctx.shadowColor = col; ctx.shadowBlur = 12; }

            ctx.beginPath();
            ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2);
            ctx.fillStyle = col;
            ctx.fill();
            ctx.shadowBlur = 0;

            ctx.strokeStyle = isSel ? '#fff' : isHov ? 'rgba(255,255,255,0.4)' : (dark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.08)');
            ctx.lineWidth = isSel ? 2.2 : 0.8;
            ctx.stroke();

            // Letter
            ctx.fillStyle = '#fff';
            ctx.font = 'bold ' + Math.max(7, n.r * 0.5) + 'px system-ui,sans-serif';
            ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
            ctx.fillText(n.kind.charAt(0).toUpperCase(), n.x, n.y);

            // Label
            if (this.sc > 0.42 || isSel || isHov) {
                ctx.font = (isSel ? '600 ' : '400 ') + '9px system-ui,sans-serif';
                ctx.fillStyle = dim ? 'rgba(150,150,150,0.2)' : (dark ? 'rgba(200,205,220,0.8)' : 'rgba(40,50,70,0.8)');
                ctx.fillText(n.name, n.x, n.y + n.r + 10);
            }
        }
        ctx.globalAlpha = 1;
        ctx.restore();
    },

    nodeCol: function(k, dark) {
        if (dark) return { class:'#60a5fa', interface:'#a78bfa', method:'#34d399', constructor:'#fbbf24', field:'#6b7280', enum:'#f87171', function:'#34d399' }[k] || '#6b7280';
        return { class:'#2563eb', interface:'#7c3aed', method:'#16a34a', constructor:'#ca8a04', field:'#9ca3af', enum:'#dc2626', function:'#16a34a' }[k] || '#9ca3af';
    },

    edgeCol: function(t, dark) {
        if (dark) return { calls:'#7c6aff', inherits:'#fbbf24', implements:'#a78bfa', contains:'#374151', uses:'#60a5fa' }[t] || '#4b5563';
        return { calls:'#6246ea', inherits:'#ca8a04', implements:'#7c3aed', contains:'#d1d5db', uses:'#2563eb' }[t] || '#d1d5db';
    },

    connected: function(a, b) {
        for (var i = 0; i < this.edges.length; i++) {
            var e = this.edges[i];
            if ((e.s === a && e.t === b) || (e.t === a && e.s === b)) return true;
        }
        return false;
    },

    toWorld: function(cx, cy) { return { x: (cx - this.W / 2 - this.ox) / this.sc, y: (cy - this.H / 2 - this.oy) / this.sc }; },

    hitNode: function(wx, wy) {
        for (var i = this.nodes.length - 1; i >= 0; i--) {
            var n = this.nodes[i], dx = n.x - wx, dy = n.y - wy;
            if (dx * dx + dy * dy <= (n.r + 2) * (n.r + 2)) return n;
        }
        return null;
    },

    mdown: function(e) {
        var r = this.cvs.getBoundingClientRect();
        var w = this.toWorld(e.clientX - r.left, e.clientY - r.top);
        var node = this.hitNode(w.x, w.y);
        if (node) { this.drag = node; this.sel = node; if (this.onSelect) this.onSelect(node); }
        else { this.pan = true; this.pm = { x: e.clientX - this.ox, y: e.clientY - this.oy }; this.sel = null; if (this.onDeselect) this.onDeselect(); }
        this.paint();
    },

    mmove: function(e) {
        var r = this.cvs.getBoundingClientRect();
        var w = this.toWorld(e.clientX - r.left, e.clientY - r.top);
        if (this.drag) { this.drag.x = w.x; this.drag.y = w.y; this.paint(); }
        else if (this.pan && this.pm) { this.ox = e.clientX - this.pm.x; this.oy = e.clientY - this.pm.y; this.paint(); }
        else { var n = this.hitNode(w.x, w.y); if (n !== this.hover) { this.hover = n; this.cvs.style.cursor = n ? 'pointer' : 'grab'; this.paint(); } }
    },

    mup: function() { this.drag = null; this.pan = false; this.pm = null; },

    fitAll: function() {
        if (!this.nodes.length) return;
        var x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
        for (var i = 0; i < this.nodes.length; i++) {
            var n = this.nodes[i];
            x0 = Math.min(x0, n.x - n.r); x1 = Math.max(x1, n.x + n.r);
            y0 = Math.min(y0, n.y - n.r); y1 = Math.max(y1, n.y + n.r);
        }
        var pw = (x1 - x0) + 60, ph = (y1 - y0) + 60;
        this.sc = Math.min(this.W / pw, this.H / ph, 2.2);
        this.ox = -((x0 + x1) / 2) * this.sc;
        this.oy = -((y0 + y1) / 2) * this.sc;
        this.paint();
    },

    shuffle: function() {
        for (var i = 0; i < this.nodes.length; i++) {
            this.nodes[i].x = (Math.random() - 0.5) * 600;
            this.nodes[i].y = (Math.random() - 0.5) * 450;
        }
        this.iter = 0; this.running = true; this.simulate();
        var self = this; setTimeout(function() { self.fitAll(); }, 550);
    },

    exportPNG: function() { var a = document.createElement('a'); a.download = 'eidos-graph.png'; a.href = this.cvs.toDataURL('image/png'); a.click(); }
};
