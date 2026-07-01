// ???????????????????????????????????????????????????????????????????
// LLM Provider Management (Admin Panel Tab)
// ???????????????????????????????????????????????????????????????????

var _llmProviders = [];
var _llmStatus = null;
var _llmModelCache = { loaded: false, providers: [] };

// ---------------------------------------------------------------------------
// LLM Model Selector (reusable widget for Ask, Review, Docs pages)
// ---------------------------------------------------------------------------

function _llmSelectorHTML(idPrefix) {
    var h = '<div class="row g-8" style="margin-top:8px;margin-bottom:4px">';
    h += '<select class="inp" id="' + idPrefix + '-provider" style="flex:1;font-size:12px" title="LLM Provider">';
    h += '<option value="">Default LLM</option>';
    for (var i = 0; i < _llmModelCache.providers.length; i++) {
        var p = _llmModelCache.providers[i];
        if (p.is_active) h += '<option value="' + esc(p.id) + '">' + esc(p.name) + '</option>';
    }
    h += '</select>';
    h += '<input class="inp" id="' + idPrefix + '-model" placeholder="Model (optional)" style="flex:1;font-size:12px" title="Model override">';
    h += '</div>';
    return h;
}

function _llmGetParams(idPrefix) {
    var providerId = (document.getElementById(idPrefix + '-provider') || {}).value || '';
    var model = (document.getElementById(idPrefix + '-model') || {}).value || '';
    var params = '';
    if (providerId) params += (params ? '&' : '?') + 'provider_id=' + encodeURIComponent(providerId);
    if (model.trim()) params += (params ? '&' : '?') + 'model=' + encodeURIComponent(model.trim());
    return params;
}

function _llmLoadProviders() {
    if (_llmModelCache.loaded) return Promise.resolve();
    return API.get('/admin/llm-providers').then(function(providers) {
        _llmModelCache.providers = providers || [];
        _llmModelCache.loaded = true;
    }).catch(function() {
        _llmModelCache.providers = [];
        _llmModelCache.loaded = true;
    });
}

function _adminLLM(el) {
    el.innerHTML = '<div class="loader"><span class="spin"></span> Loading LLM providers...</div>';
    Promise.all([
        API.get('/admin/llm-providers').catch(function() { return []; }),
        API.get('/admin/llm-providers/status').catch(function() { return { configured: false }; })
    ]).then(function(results) {
        _llmProviders = results[0] || [];
        _llmStatus = results[1] || { configured: false };
        _renderLLMAdmin(el);
    }).catch(function(e) {
        el.innerHTML = '<div class="card"><p style="color:var(--red)">Failed to load LLM config: ' + esc(e.message) + '</p></div>';
    });
}

function _renderLLMAdmin(el) {
    var h = '';

    // Status card
    h += '<div class="card"><div class="card-hd"><svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg> LLM Status</div>';
    if (_llmStatus.configured) {
        var dp = _llmStatus.default_provider || {};
        h += '<div class="admin-sys-grid">';
        h += _llmStatusTile('connected', 'Status');
        h += _llmStatusTile(esc(dp.name || 'Environment'), 'Provider');
        h += _llmStatusTile(esc(dp.default_model || '—'), 'Model');
        h += _llmStatusTile(_llmStatus.active_providers || 0, 'Active');
        h += '</div>';
        if (_llmStatus.fallback_to_env) {
            h += '<p style="font-size:11px;color:var(--yellow);margin-top:8px">? Using environment variables (no DB provider set as default)</p>';
        }
    } else {
        h += '<p style="color:var(--text-2)">No LLM provider configured. Add one below to enable AI features.</p>';
    }
    h += '</div>';

    // Provider list
    h += '<div class="card"><div class="card-hd"><svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg> Providers (' + _llmProviders.length + ')</div>';
    h += '<div style="margin-bottom:12px"><button class="btn btn-s btn-p" onclick="_llmShowAddForm()"><svg width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> Add Provider</button></div>';
    h += '<div id="llm-add-form" style="display:none"></div>';

    if (_llmProviders.length === 0) {
        h += '<p style="color:var(--text-3);font-size:13px">No providers registered yet.</p>';
    } else {
        h += '<div class="llm-provider-list">';
        for (var i = 0; i < _llmProviders.length; i++) {
            var p = _llmProviders[i];
            h += _renderProviderCard(p);
        }
        h += '</div>';
    }
    h += '</div>';

    // Chat playground
    h += '<div class="card"><div class="card-hd"><svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg> Chat Playground</div>';
    h += '<div class="field"><label>Message</label><textarea class="inp" id="llm-chat-msg" rows="3" placeholder="Type a message to test the LLM..."></textarea></div>';
    h += '<div class="row g-8" style="margin-bottom:8px">';
    h += '<select class="inp" id="llm-chat-provider" style="flex:1"><option value="">Default Provider</option>';
    for (var j = 0; j < _llmProviders.length; j++) {
        if (_llmProviders[j].is_active) {
            h += '<option value="' + esc(_llmProviders[j].id) + '">' + esc(_llmProviders[j].name) + '</option>';
        }
    }
    h += '</select>';
    h += '<input class="inp" id="llm-chat-model" placeholder="Model override (optional)" style="flex:1">';
    h += '<button class="btn btn-s btn-p" onclick="_llmSendChat()">Send</button>';
    h += '</div>';
    h += '<div id="llm-chat-result" style="display:none"></div>';
    h += '</div>';

    el.innerHTML = h;
}

function _llmStatusTile(val, label) {
    var color = 'var(--text-0)';
    if (val === 'connected') { val = '? Connected'; color = 'var(--green)'; }
    return '<div class="admin-sys-tile"><div class="admin-sys-tile-val" style="color:' + color + '">' + val + '</div><div class="admin-sys-tile-label">' + label + '</div></div>';
}

function _renderProviderCard(p) {
    var statusDot = p.is_active ? '<span style="color:var(--green)">?</span>' : '<span style="color:var(--red)">?</span>';
    var defaultBadge = p.is_default ? ' <span style="background:var(--accent);color:#fff;padding:1px 6px;border-radius:4px;font-size:10px">DEFAULT</span>' : '';
    var keyStatus = p.has_api_key ? '<span style="color:var(--green);font-size:11px">? Key set</span>' : '<span style="color:var(--text-3);font-size:11px">? No key</span>';

    var h = '<div class="llm-provider-card" style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:10px">';
    h += '<div class="row" style="justify-content:space-between;align-items:center;margin-bottom:8px">';
    h += '<div><strong>' + statusDot + ' ' + esc(p.name) + '</strong>' + defaultBadge + '</div>';
    h += '<div class="row g-4">';
    if (!p.is_default && p.is_active) h += '<button class="btn btn-xs btn-g" onclick="_llmSetDefault(\'' + p.id + '\')" title="Set as default">? Default</button>';
    h += '<button class="btn btn-xs btn-g" onclick="_llmTestProvider(\'' + p.id + '\')" title="Test connectivity">Test</button>';
    h += '<button class="btn btn-xs btn-g" onclick="_llmListModels(\'' + p.id + '\')" title="List models">Models</button>';
    h += '<button class="btn btn-xs btn-d" onclick="_llmDeleteProvider(\'' + p.id + '\',\'' + esc(p.name) + '\')" title="Delete">?</button>';
    h += '</div></div>';

    h += '<div style="font-size:12px;color:var(--text-2)">';
    h += '<div class="row g-16" style="flex-wrap:wrap">';
    h += '<span>URL: <code style="font-size:11px">' + esc(p.base_url) + '</code></span>';
    h += '<span>Model: <code style="font-size:11px">' + esc(p.default_model || '—') + '</code></span>';
    h += '<span>' + keyStatus + '</span>';
    h += '<span>Temp: ' + p.temperature + '</span>';
    h += '<span>Tokens: ' + p.max_tokens + '</span>';
    h += '</div></div>';

    h += '<div id="llm-prov-detail-' + p.id + '" style="margin-top:8px;display:none"></div>';
    h += '</div>';
    return h;
}

function _llmShowAddForm() {
    var el = document.getElementById('llm-add-form');
    if (!el) return;
    if (el.style.display !== 'none') { el.style.display = 'none'; return; }

    var h = '<div style="border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:12px;background:var(--bg-1)">';
    h += '<div class="row g-8 flex-wrap" style="margin-bottom:8px">';
    h += '<input class="inp" id="llm-add-name" placeholder="Provider name (e.g. Fanar)" style="flex:1;min-width:140px">';
    h += '<input class="inp" id="llm-add-url" placeholder="Base URL (e.g. https://api.fanar.qa/v1)" style="flex:2;min-width:200px">';
    h += '</div>';
    h += '<div class="row g-8 flex-wrap" style="margin-bottom:8px">';
    h += '<input class="inp" id="llm-add-key" placeholder="API Key (optional)" type="password" style="flex:1;min-width:140px">';
    h += '<input class="inp" id="llm-add-model" placeholder="Default model (e.g. Fanar-C-2-27B)" style="flex:1;min-width:160px">';
    h += '</div>';
    h += '<div class="row g-8 flex-wrap" style="margin-bottom:8px">';
    h += '<input class="inp" id="llm-add-tokens" placeholder="Max tokens" type="number" value="4096" style="width:100px">';
    h += '<input class="inp" id="llm-add-temp" placeholder="Temperature" type="number" step="0.1" value="0.1" style="width:100px">';
    h += '<input class="inp" id="llm-add-timeout" placeholder="Timeout (s)" type="number" value="60" style="width:100px">';
    h += '<input class="inp" id="llm-add-rpm" placeholder="Rate limit RPM" type="number" value="50" style="width:120px">';
    h += '</div>';
    h += '<div class="row g-8"><button class="btn btn-s btn-p" onclick="_llmAddProvider()">Register Provider</button><button class="btn btn-s btn-g" onclick="document.getElementById(\'llm-add-form\').style.display=\'none\'">Cancel</button></div>';
    h += '</div>';
    el.innerHTML = h;
    el.style.display = 'block';
}

function _llmAddProvider() {
    var name = (document.getElementById('llm-add-name') || {}).value || '';
    var url = (document.getElementById('llm-add-url') || {}).value || '';
    var key = (document.getElementById('llm-add-key') || {}).value || '';
    var model = (document.getElementById('llm-add-model') || {}).value || '';
    var tokens = parseInt((document.getElementById('llm-add-tokens') || {}).value) || 4096;
    var temp = parseFloat((document.getElementById('llm-add-temp') || {}).value) || 0.1;
    var timeout = parseInt((document.getElementById('llm-add-timeout') || {}).value) || 60;
    var rpm = parseInt((document.getElementById('llm-add-rpm') || {}).value) || 50;

    if (!name.trim()) { toast('Provider name is required', false); return; }
    if (!url.trim()) { toast('Base URL is required', false); return; }

    API.post('/admin/llm-providers', {
        name: name.trim(),
        base_url: url.trim(),
        api_key: key,
        default_model: model.trim(),
        max_tokens: tokens,
        temperature: temp,
        timeout: timeout,
        rate_limit_rpm: rpm
    }).then(function(data) {
        toast('Provider "' + data.name + '" registered');
        _llmProviders.push(data);
        _renderLLMAdmin(document.getElementById('admin-content'));
    }).catch(function(e) {
        toast('Failed: ' + e.message, false);
    });
}

function _llmSetDefault(pid) {
    API.post('/admin/llm-providers/' + pid + '/set-default').then(function() {
        toast('Default provider updated');
        _adminLLM(document.getElementById('admin-content'));
    }).catch(function(e) { toast('Failed: ' + e.message, false); });
}

function _llmDeleteProvider(pid, name) {
    if (!confirm('Delete provider "' + name + '"?')) return;
    API.del('/admin/llm-providers/' + pid).then(function() {
        toast('Provider deleted');
        _llmProviders = _llmProviders.filter(function(p) { return p.id !== pid; });
        _renderLLMAdmin(document.getElementById('admin-content'));
    }).catch(function(e) { toast('Failed: ' + e.message, false); });
}

function _llmTestProvider(pid) {
    var detailEl = document.getElementById('llm-prov-detail-' + pid);
    if (detailEl) {
        detailEl.style.display = 'block';
        detailEl.innerHTML = '<span class="spin" style="display:inline-block;width:14px;height:14px"></span> Testing...';
    }
    API.post('/admin/llm-providers/' + pid + '/test').then(function(data) {
        if (!detailEl) return;
        if (data.status === 'ok') {
            detailEl.innerHTML = '<span style="color:var(--green)">? Connected</span> — Models: <code>' + (data.models || []).join(', ') + '</code>';
        } else {
            detailEl.innerHTML = '<span style="color:var(--red)">? Error</span>: ' + esc(data.detail || 'Unknown error');
        }
    }).catch(function(e) {
        if (detailEl) detailEl.innerHTML = '<span style="color:var(--red)">? Error</span>: ' + esc(e.message);
    });
}

function _llmListModels(pid) {
    var detailEl = document.getElementById('llm-prov-detail-' + pid);
    if (detailEl) {
        detailEl.style.display = 'block';
        detailEl.innerHTML = '<span class="spin" style="display:inline-block;width:14px;height:14px"></span> Fetching models...';
    }
    API.get('/admin/llm-providers/' + pid + '/models').then(function(data) {
        if (!detailEl) return;
        if (data.status === 'ok' && data.models) {
            var ml = data.models.map(function(m) {
                var badge = m.is_default ? ' <span style="background:var(--accent);color:#fff;padding:0 4px;border-radius:3px;font-size:9px">default</span>' : '';
                return '<code>' + esc(m.id) + '</code>' + badge;
            }).join(', ');
            detailEl.innerHTML = '<strong>Models:</strong> ' + ml;
        } else {
            detailEl.innerHTML = '<span style="color:var(--red)">? Error</span>: ' + esc(data.detail || 'Failed to fetch models');
        }
    }).catch(function(e) {
        if (detailEl) detailEl.innerHTML = '<span style="color:var(--red)">? Error</span>: ' + esc(e.message);
    });
}

function _llmSendChat() {
    var msg = (document.getElementById('llm-chat-msg') || {}).value || '';
    if (!msg.trim()) { toast('Enter a message', false); return; }

    var providerId = (document.getElementById('llm-chat-provider') || {}).value || null;
    var model = (document.getElementById('llm-chat-model') || {}).value || null;

    var resultEl = document.getElementById('llm-chat-result');
    if (resultEl) {
        resultEl.style.display = 'block';
        resultEl.innerHTML = '<span class="spin" style="display:inline-block;width:14px;height:14px"></span> Sending...';
    }

    var body = { message: msg.trim() };
    if (providerId) body.provider_id = providerId;
    if (model && model.trim()) body.model = model.trim();

    API.post('/admin/llm-providers/chat', body).then(function(data) {
        if (!resultEl) return;
        if (data.error) {
            resultEl.innerHTML = '<div style="border:1px solid var(--red);border-radius:6px;padding:10px;background:var(--bg-1)"><strong style="color:var(--red)">Error:</strong> ' + esc(data.error) + '</div>';
        } else {
            resultEl.innerHTML = '<div style="border:1px solid var(--border);border-radius:6px;padding:10px;background:var(--bg-1)">' +
                '<div style="font-size:11px;color:var(--text-3);margin-bottom:4px">Model: ' + esc(data.model || '—') + '</div>' +
                '<div style="white-space:pre-wrap;font-size:13px">' + esc(data.response || '') + '</div></div>';
        }
    }).catch(function(e) {
        if (resultEl) resultEl.innerHTML = '<div style="color:var(--red)">Error: ' + esc(e.message) + '</div>';
    });
}
