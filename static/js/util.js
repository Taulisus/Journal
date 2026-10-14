window.U = (function(){
    'use strict';
    function esc(s){
        return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
            return ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[c];
        });
    }
    function bind(root, sel, ev, fn){
        (root||document).querySelectorAll(sel).forEach(function(n){ n.addEventListener(ev, fn); });
    }
    function on(root, sel, ev, fn){
        (root||document).addEventListener(ev, function(e){
            var t = e.target.closest(sel);
            if(t) fn.call(t, e);
        });
    }
    function crumbs(items){
        return '<ol class="breadcrumbs">'+items.map(function(x,i){
            var last = i === items.length-1;
            return '<li>'+(last || !x.href
                ? '<span class="'+(last?'current':'')+'">'+esc(x.label)+'</span>'
                : '<a href="'+esc(x.href)+'">'+esc(x.label)+'</a>')+'</li>';
        }).join('')+'</ol>';
    }
    function pageHead(icon, title, actions){
        return '<div class="page-head">'
             + '<h2><i class="bi '+icon+' text-primary me-2"></i>'+esc(title)+'</h2>'
             + (actions ? '<div class="page-head__actions">'+actions+'</div>' : '')
             + '</div>';
    }
    function empty(icon, title, desc, actions){
        return '<div class="card"><div class="empty">'
             + '<div class="empty__icon"><i class="bi '+icon+'"></i></div>'
             + '<div class="empty__title">'+esc(title)+'</div>'
             + (desc ? '<div class="empty__desc">'+esc(desc)+'</div>' : '')
             + (actions||'')
             + '</div></div>';
    }
    function badge(text, variant){ return '<span class="badge bg-'+variant+'">'+esc(text)+'</span>'; }
    function confirmForm(msg, btnHtml){
        return '<form style="display:inline" data-confirm="'+esc(msg)+'" action="#">'+btnHtml+'</form>';
    }
    function fmtDate(iso){
        if(!iso) return '';
        var p = iso.split('-'); if(p.length !== 3) return iso;
        return p[2]+'.'+p[1]+'.'+p[0];
    }
    return { esc:esc, bind:bind, on:on, crumbs:crumbs, pageHead:pageHead, empty:empty, badge:badge, confirmForm:confirmForm, fmtDate:fmtDate };
})();