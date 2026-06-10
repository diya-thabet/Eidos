// Eidos – Lightweight inline SVG chart utilities (no dependencies)
var Chart = (function() {
    'use strict';
    var PAL = ['#6246ea','#34d399','#60a5fa','#fbbf24','#f87171','#a78bfa','#fb923c','#38bdf8','#4ade80','#e879f9'];
    function col(i) { return PAL[i % PAL.length]; }
    function e(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
    function tr(s,n) { n=n||20; return s.length>n ? s.slice(0,n-1)+'\u2026' : s; }
    function fm(n) { return n>=1e6?(n/1e6).toFixed(1)+'M':n>=1e3?(n/1e3).toFixed(1)+'K':String(Math.round(n*10)/10); }

    // Donut chart (returns HTML string)
    function donut(items, opts) {
        opts=opts||{};
        var w=opts.width||220, h=opts.height||220;
        var r=w/2-14, inner=r*0.58, cx=w/2, cy=h/2;
        var total=0; items.forEach(function(it){total+=it.value||0;});
        if(!total) return '<div style="text-align:center;color:var(--text-3);padding:24px">No data</div>';
        var svg='<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'">';
        var angle=-Math.PI/2;
        items.forEach(function(it,i){
            var pct=it.value/total, a1=angle, a2=angle+pct*2*Math.PI;
            if(pct<=0) return;
            var large=pct>0.5?1:0;
            var x1=cx+r*Math.cos(a1),y1=cy+r*Math.sin(a1);
            var x2=cx+r*Math.cos(a2),y2=cy+r*Math.sin(a2);
            var ix1=cx+inner*Math.cos(a1),iy1=cy+inner*Math.sin(a1);
            var ix2=cx+inner*Math.cos(a2),iy2=cy+inner*Math.sin(a2);
            var c=it.color||col(i);
            svg+='<path d="M'+ix1+','+iy1+' L'+x1+','+y1+' A'+r+','+r+' 0 '+large+' 1 '+x2+','+y2+' L'+ix2+','+iy2+' A'+inner+','+inner+' 0 '+large+' 0 '+ix1+','+iy1+'" fill="'+c+'" opacity="0.88"><title>'+e(it.label)+': '+it.value+' ('+(pct*100).toFixed(1)+'%)</title></path>';
            angle=a2;
        });
        if(opts.center){
            svg+='<text x="'+cx+'" y="'+(cy-4)+'" text-anchor="middle" fill="var(--text-0)" font-size="18" font-weight="700">'+e(opts.center)+'</text>';
            if(opts.sub) svg+='<text x="'+cx+'" y="'+(cy+13)+'" text-anchor="middle" fill="var(--text-3)" font-size="9" text-transform="uppercase">'+e(opts.sub)+'</text>';
        }
        svg+='</svg>';
        var leg='<div class="ch-legend">';
        items.slice(0,8).forEach(function(it,i){
            leg+='<div class="ch-leg-row"><span class="ch-dot" style="background:'+(it.color||col(i))+'"></span><span class="ch-leg-lbl">'+e(tr(it.label,18))+'</span><span class="ch-leg-val">'+fm(it.value)+'</span></div>';
        });
        if(items.length>8) leg+='<div class="ch-leg-row" style="color:var(--text-3)">+'+(items.length-8)+' more</div>';
        leg+='</div>';
        return '<div class="ch-donut">'+svg+leg+'</div>';
    }

    // Horizontal bar chart
    function bar(items, opts) {
        opts=opts||{};
        var max=0; items.forEach(function(it){if(it.value>max) max=it.value;});
        if(!max) return '<div style="text-align:center;color:var(--text-3);padding:24px">No data</div>';
        var h='';
        items.slice(0,opts.limit||10).forEach(function(it,i){
            var pct=(it.value/max*100).toFixed(1);
            var c=it.color||col(i);
            h+='<div class="ch-bar-row"><span class="ch-bar-lbl" title="'+e(it.label)+'">'+e(tr(it.label,24))+'</span><div class="ch-bar-track"><div class="ch-bar-fill" style="width:'+pct+'%;background:'+c+'"></div></div><span class="ch-bar-val">'+fm(it.value)+'</span></div>';
        });
        return '<div class="ch-bars">'+h+'</div>';
    }

    // Scatter/bubble chart
    function scatter(pts, opts) {
        opts=opts||{};
        var w=opts.width||420, h=opts.height||240;
        var pad={t:20,r:18,b:34,l:44};
        var pw=w-pad.l-pad.r, ph=h-pad.t-pad.b;
        var xMax=0,yMax=0;
        pts.forEach(function(p){if(p.x>xMax)xMax=p.x;if(p.y>yMax)yMax=p.y;});
        if(!xMax)xMax=1;if(!yMax)yMax=1;
        xMax*=1.1;yMax*=1.1;
        var svg='<svg width="100%" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="xMidYMid meet" style="display:block;max-width:'+w+'px">';
        // Grid
        for(var gi=0;gi<=4;gi++){
            var gy=pad.t+ph-(gi/4)*ph;
            svg+='<line x1="'+pad.l+'" y1="'+gy+'" x2="'+(w-pad.r)+'" y2="'+gy+'" stroke="var(--border)" stroke-dasharray="2,3"/>';
            svg+='<text x="'+(pad.l-5)+'" y="'+(gy+3)+'" text-anchor="end" fill="var(--text-3)" font-size="8">'+fm(yMax*gi/4)+'</text>';
        }
        // Danger zone overlay
        svg+='<rect x="'+(pad.l+pw*0.5)+'" y="'+pad.t+'" width="'+(pw*0.5)+'" height="'+(ph*0.5)+'" fill="var(--red)" opacity="0.04" rx="4"/>';
        svg+='<text x="'+(pad.l+pw*0.75)+'" y="'+(pad.t+12)+'" text-anchor="middle" fill="var(--red)" font-size="8" opacity="0.6">High Risk Zone</text>';
        // Axes labels
        if(opts.xLabel) svg+='<text x="'+(pad.l+pw/2)+'" y="'+(h-4)+'" text-anchor="middle" fill="var(--text-3)" font-size="9">'+e(opts.xLabel)+'</text>';
        if(opts.yLabel) svg+='<text x="10" y="'+(pad.t+ph/2)+'" text-anchor="middle" fill="var(--text-3)" font-size="9" transform="rotate(-90,10,'+(pad.t+ph/2)+')">'+e(opts.yLabel)+'</text>';
        // Points
        pts.forEach(function(p,i){
            var px=pad.l+(p.x/xMax)*pw;
            var py_=pad.t+ph-(p.y/yMax)*ph;
            var sz=Math.max(5,Math.min(16,5+(p.size||0)/10));
            var c=p.color||(p.risk>10?'var(--red)':p.risk>5?'var(--yellow)':'var(--green)');
            svg+='<circle cx="'+px.toFixed(1)+'" cy="'+py_.toFixed(1)+'" r="'+sz+'" fill="'+c+'" opacity="0.72" stroke="'+c+'" stroke-width="1"><title>'+e(p.label)+'\n'+(opts.xLabel||'x')+': '+p.x+'\n'+(opts.yLabel||'y')+': '+p.y+'</title></circle>';
        });
        svg+='</svg>';
        return '<div class="ch-scatter">'+svg+'</div>';
    }

    // Line / timeline chart
    function timeline(series, opts) {
        opts=opts||{};
        var w=opts.width||480, h=opts.height||180;
        var pad={t:14,r:14,b:30,l:38};
        var pw=w-pad.l-pad.r, ph=h-pad.t-pad.b;
        var maxY=0;
        series.forEach(function(s){s.points.forEach(function(p){if(p>maxY)maxY=p;});});
        if(!maxY)maxY=1;maxY*=1.1;
        var svg='<svg width="100%" viewBox="0 0 '+w+' '+h+'" preserveAspectRatio="xMidYMid meet" style="display:block">';
        for(var gi=0;gi<=3;gi++){
            var gy=pad.t+ph-(gi/3)*ph;
            svg+='<line x1="'+pad.l+'" y1="'+gy+'" x2="'+(w-pad.r)+'" y2="'+gy+'" stroke="var(--border)" stroke-dasharray="2,3"/>';
            svg+='<text x="'+(pad.l-4)+'" y="'+(gy+3)+'" text-anchor="end" fill="var(--text-3)" font-size="8">'+fm(maxY*gi/3)+'</text>';
        }
        series.forEach(function(s,si){
            var pts=s.points,c=s.color||col(si);
            if(!pts.length) return;
            var path='';
            for(var pi=0;pi<pts.length;pi++){
                var x=pad.l+(pi/Math.max(1,pts.length-1))*pw;
                var y=pad.t+ph-(pts[pi]/maxY)*ph;
                path+=(pi===0?'M':'L')+x.toFixed(1)+','+y.toFixed(1);
            }
            svg+='<path d="'+path+'" fill="none" stroke="'+c+'" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>';
            // Area fill
            svg+='<path d="'+path+' L'+(pad.l+((pts.length-1)/Math.max(1,pts.length-1))*pw)+','+(pad.t+ph)+' L'+pad.l+','+(pad.t+ph)+' Z" fill="'+c+'" opacity="0.06"/>';
            var lx=pad.l+((pts.length-1)/Math.max(1,pts.length-1))*pw;
            var ly=pad.t+ph-(pts[pts.length-1]/maxY)*ph;
            svg+='<circle cx="'+lx.toFixed(1)+'" cy="'+ly.toFixed(1)+'" r="3.5" fill="'+c+'"/>';
        });
        if(opts.labels){
            var every=Math.max(1,Math.floor(opts.labels.length/6));
            for(var li=0;li<opts.labels.length;li++){
                if(li%every===0||li===opts.labels.length-1){
                    var lx=pad.l+(li/Math.max(1,opts.labels.length-1))*pw;
                    svg+='<text x="'+lx+'" y="'+(h-5)+'" text-anchor="middle" fill="var(--text-3)" font-size="8">'+e(opts.labels[li])+'</text>';
                }
            }
        }
        svg+='</svg>';
        if(series.length>1){
            svg+='<div class="ch-tl-legend">';
            series.forEach(function(s,si){svg+='<span class="ch-leg-row" style="gap:4px"><span class="ch-dot" style="background:'+(s.color||col(si))+'"></span><span style="font-size:11px">'+e(s.name)+'</span></span>';});
            svg+='</div>';
        }
        return '<div class="ch-timeline">'+svg+'</div>';
    }

    // Gauge (radial progress)
    function gauge(value, max, opts) {
        opts=opts||{};
        var sz=opts.size||110;
        var r=sz/2-12;
        var pct=Math.min(1,value/(max||1));
        var circ=2*Math.PI*r;
        var color=opts.color||(pct>0.7?'var(--red)':pct>0.4?'var(--yellow)':'var(--green)');
        var svg='<svg width="'+sz+'" height="'+sz+'" viewBox="0 0 '+sz+' '+sz+'">';
        svg+='<circle cx="'+(sz/2)+'" cy="'+(sz/2)+'" r="'+r+'" fill="none" stroke="var(--border)" stroke-width="7" stroke-dasharray="'+(circ*0.75)+' '+circ+'" stroke-linecap="round" transform="rotate(135,'+(sz/2)+','+(sz/2)+')"/>';
        svg+='<circle cx="'+(sz/2)+'" cy="'+(sz/2)+'" r="'+r+'" fill="none" stroke="'+color+'" stroke-width="7" stroke-dasharray="'+(pct*circ*0.75)+' '+circ+'" stroke-linecap="round" transform="rotate(135,'+(sz/2)+','+(sz/2)+')"/>';
        svg+='<text x="'+(sz/2)+'" y="'+(sz/2+2)+'" text-anchor="middle" fill="var(--text-0)" font-size="16" font-weight="700">'+(opts.label||Math.round(pct*100)+'%')+'</text>';
        if(opts.sub) svg+='<text x="'+(sz/2)+'" y="'+(sz/2+15)+'" text-anchor="middle" fill="var(--text-3)" font-size="8">'+e(opts.sub)+'</text>';
        svg+='</svg>';
        return svg;
    }

    // Sparkline (inline mini chart)
    function spark(values, opts) {
        opts=opts||{};
        var w=opts.width||140, h=opts.height||32;
        var max=0; values.forEach(function(v){if(v>max)max=v;});
        if(!max) return '';
        var step=w/Math.max(1,values.length-1);
        var pts=[]; values.forEach(function(v,i){pts.push((i*step).toFixed(1)+','+(h-2-(v/max)*(h-4)).toFixed(1));});
        var c=opts.color||'var(--accent)';
        return '<svg width="'+w+'" height="'+h+'" viewBox="0 0 '+w+' '+h+'" style="display:block"><polyline points="'+pts.join(' ')+'" fill="none" stroke="'+c+'" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><polygon points="0,'+h+' '+pts.join(' ')+' '+((values.length-1)*step)+','+h+'" fill="'+c+'" opacity="0.07"/></svg>';
    }

    // Insight card builder
    function insight(icon, title, text, type) {
        var cls = type==='warn'?'ch-insight-warn':type==='good'?'ch-insight-good':'ch-insight-info';
        return '<div class="ch-insight '+cls+'"><span class="ch-insight-icon">'+icon+'</span><div><strong>'+e(title)+'</strong><p>'+e(text)+'</p></div></div>';
    }

    return { donut:donut, bar:bar, scatter:scatter, timeline:timeline, gauge:gauge, spark:spark, insight:insight, _col:col };
})();
