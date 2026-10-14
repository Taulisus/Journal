/* ============================================================
   AURORA UI · Jinja-версия (не SPA)
   ============================================================ */
(function(){
    'use strict';

    /* ============================================================
       ТЕМА / АКЦЕНТ / ПЛОТНОСТЬ
       ============================================================ */
    function currentTheme(){
        return document.documentElement.getAttribute('data-theme') || 'light';
    }
    function setTheme(t){
        document.documentElement.setAttribute('data-theme', t);
        try { localStorage.setItem('theme', t); } catch(e){}
        var btn = document.getElementById('themeToggle');
        if(btn){
            var i = btn.querySelector('i');
            if(i) i.className = t === 'dark' ? 'bi bi-sun' : 'bi bi-moon-stars';
        }
    }
    function initTheme(){
        var saved = null;
        try { saved = localStorage.getItem('theme'); } catch(e){}
        if(!saved) saved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', saved);
    }
    initTheme();

    function setAccent(name){
        document.documentElement.setAttribute('data-accent', name);
        try { localStorage.setItem('accent', name); } catch(e){}
        document.querySelectorAll('.accent-swatch').forEach(function(s){
            s.classList.toggle('is-active', s.dataset.accent === name);
        });
    }
    function initAccent(){
        var saved = null;
        try { saved = localStorage.getItem('accent'); } catch(e){}
        document.documentElement.setAttribute('data-accent', saved || 'blue');
    }
    initAccent();

    function setDensity(name){
        document.documentElement.setAttribute('data-density', name);
        try { localStorage.setItem('density', name); } catch(e){}
        document.querySelectorAll('.density-toggle button').forEach(function(b){
            b.classList.toggle('is-active', b.dataset.density === name);
        });
    }
    function initDensity(){
        var saved = null;
        try { saved = localStorage.getItem('density'); } catch(e){}
        document.documentElement.setAttribute('data-density', saved || 'comfortable');
    }
    initDensity();

    /* ============================================================
       ВЕРХНИЙ ПРОГРЕСС-БАР
       ============================================================ */
    var progressTimer = null;
    function startProgress(){
        var bar = document.getElementById('topProgressBar');
        var wrap = document.getElementById('topProgress');
        if(!bar || !wrap) return;
        bar.style.transition = 'none';
        bar.style.width = '0%';
        wrap.classList.add('is-active');
        requestAnimationFrame(function(){
            bar.style.transition = 'width .3s ease';
            bar.style.width = '30%';
        });
        progressTimer = setTimeout(function(){
            bar.style.width = '70%';
        }, 250);
    }
    function finishProgress(){
        var bar = document.getElementById('topProgressBar');
        var wrap = document.getElementById('topProgress');
        if(!bar || !wrap) return;
        clearTimeout(progressTimer);
        bar.style.width = '100%';
        setTimeout(function(){
            wrap.classList.remove('is-active');
            setTimeout(function(){ bar.style.width = '0%'; }, 250);
        }, 220);
    }

    /* Автозапуск прогресса на переходах по внутренним ссылкам */
    document.addEventListener('click', function(e){
        var a = e.target.closest('a[href]');
        if(!a) return;
        var href = a.getAttribute('href');
        if(!href) return;
        if(href.startsWith('#')) return;
        if(href.startsWith('javascript:')) return;
        if(href.startsWith('mailto:')) return;
        if(href.startsWith('tel:')) return;
        if(a.target === '_blank') return;
        if(a.hasAttribute('data-no-progress')) return;
        if(a.hasAttribute('download')) return;
        startProgress();
    });
    window.addEventListener('pageshow', finishProgress);

    /* ============================================================
       DRAWER (мобильное меню)
       ============================================================ */
    function initDrawer(){
        var burger = document.getElementById('burger');
        var drawer = document.getElementById('drawer');
        if(!burger || !drawer) return;

        function openDrawer(){
            drawer.classList.add('is-open');
            drawer.setAttribute('aria-hidden', 'false');
            burger.setAttribute('aria-expanded', 'true');
            document.body.style.overflow = 'hidden';
        }
        function closeDrawer(){
            drawer.classList.remove('is-open');
            drawer.setAttribute('aria-hidden', 'true');
            burger.setAttribute('aria-expanded', 'false');
            document.body.style.overflow = '';
        }

        burger.addEventListener('click', function(){
            if(drawer.classList.contains('is-open')) closeDrawer();
            else openDrawer();
        });

        drawer.addEventListener('click', function(e){
            var link = e.target.closest('.app-drawer__link');
            if(link && link.getAttribute('href')){
                closeDrawer();
                return;
            }
            var toggle = e.target.closest('.app-drawer__toggle');
            if(toggle){
                var sub = toggle.nextElementSibling;
                if(sub){
                    var open = sub.classList.toggle('is-open');
                    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
                }
            }
        });

        document.addEventListener('keydown', function(e){
            if(e.key === 'Escape' && drawer.classList.contains('is-open')){
                closeDrawer();
            }
        });
    }

    /* ============================================================
       ГРАДИЕНТНЫЕ АВАТАРЫ
       ============================================================ */
    function hashHue(str){
        var h = 0;
        for(var i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) | 0;
        return Math.abs(h) % 360;
    }
    function applyAvatarGradients(){
        document.querySelectorAll('[data-avatar]').forEach(function(el){
            var name = el.getAttribute('data-avatar') || '?';
            var h = hashHue(name);
            el.style.background = 'linear-gradient(135deg, hsl(' + h + ',65%,55%), hsl(' + ((h + 40) % 360) + ',70%,42%))';
        });
    }

    /* ============================================================
       МОДАЛЬНЫЕ ОКНА + FOCUS-TRAP
       ============================================================ */
    var focusTraps = {};

    function focusableIn(el){
        return Array.prototype.slice.call(
            el.querySelectorAll(
                'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), ' +
                'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )
        ).filter(function(x){ return x.offsetParent !== null; });
    }

    function openModal(id){
        var m = document.getElementById(id);
        if(!m) return;
        m.classList.add('show');
        m.setAttribute('aria-hidden', 'false');
        m.setAttribute('role', 'dialog');
        m.setAttribute('aria-modal', 'true');
        document.body.style.overflow = 'hidden';

        m.onclick = function(e){ if(e.target === m) closeModal(id); };

        var dlg = m.querySelector('.modal-dialog') || m;
        var prevActive = document.activeElement;
        dlg.setAttribute('tabindex', '-1');
        setTimeout(function(){ try { dlg.focus(); } catch(e){} }, 60);

        var trap = function(e){
            if(e.key === 'Escape'){ closeModal(id); return; }
            if(e.key !== 'Tab') return;
            var f = focusableIn(dlg);
            if(!f.length) return;
            var first = f[0], last = f[f.length - 1];
            if(e.shiftKey && document.activeElement === first){
                e.preventDefault(); last.focus();
            } else if(!e.shiftKey && document.activeElement === last){
                e.preventDefault(); first.focus();
            }
        };
        document.addEventListener('keydown', trap);
        focusTraps[id] = { trap: trap, prevActive: prevActive };
    }

    function closeModal(id){
        var m = document.getElementById(id);
        if(!m) return;
        m.classList.remove('show');
        m.setAttribute('aria-hidden', 'true');
        m.removeAttribute('aria-modal');
        document.body.style.overflow = '';
        m.onclick = null;

        var t = focusTraps[id];
        if(t){
            document.removeEventListener('keydown', t.trap);
            if(t.prevActive && t.prevActive.focus){
                try { t.prevActive.focus(); } catch(e){}
            }
            delete focusTraps[id];
        }
    }

    /* ============================================================
       UNDO-СНАКБАР
       ============================================================ */
    var undoState = { timer: null };
    function showUndo(message, undoFn, ttl){
        ttl = ttl || 6000;
        var bar = document.querySelector('.snackbar');
        if(!bar){
            bar = document.createElement('div');
            bar.className = 'snackbar';
            bar.innerHTML = '<span class="snackbar__msg"></span><button type="button">Отменить</button>';
            document.body.appendChild(bar);
        }
        bar.querySelector('.snackbar__msg').textContent = message;

        clearTimeout(undoState.timer);

        var close = function(){
            bar.classList.remove('show');
            clearTimeout(undoState.timer);
        };
        var btn = bar.querySelector('button');
        btn.onclick = function(){
            if(typeof undoFn === 'function') undoFn();
            close();
        };
        bar.classList.add('show');
        undoState.timer = setTimeout(close, ttl);
    }

    /* ============================================================
       TOAST
       ============================================================ */
    function toast(message, variant){
        variant = variant || 'info';
        var host = document.querySelector('.toast-host');
        if(!host){
            host = document.createElement('div');
            host.className = 'toast-host';
            document.body.appendChild(host);
        }
        var t = document.createElement('div');
        t.className = 'toast toast--' + variant;
        var icons = {
            success: 'bi-check-circle-fill',
            danger:  'bi-exclamation-triangle-fill',
            warning: 'bi-exclamation-circle-fill',
            info:    'bi-info-circle-fill'
        };
        t.innerHTML = '<i class="bi ' + (icons[variant] || icons.info) + '"></i>'
                    + '<span></span>'
                    + '<div class="toast__bar"></div>';
        t.querySelector('span').textContent = message;
        host.appendChild(t);
        setTimeout(function(){
            t.classList.add('is-leaving');
            setTimeout(function(){ t.remove(); }, 200);
        }, 2400);
    }

    /* ============================================================
       Flash-сообщения из Jinja → в toast
       ============================================================ */
    function consumeFlashMessages(){
        var data = document.getElementById('flashData');
        if(!data) return;

        var raw = [];
        try { raw = JSON.parse(data.textContent) || []; } catch(e){ return; }

        // Jinja отдаёт flash-сообщения как массив массивов:
        //   [['success', 'Текст'], ['danger', 'Ошибка']]
        // Приводим к единому виду {category, message}.
        var messages = raw.map(function(item){
            if(Array.isArray(item)){
                return { category: item[0] || 'info', message: item[1] || '' };
            }
            if(item && typeof item === 'object'){
                return {
                    category: item.category || 'info',
                    message: item.message || ''
                };
            }
            return { category: 'info', message: String(item || '') };
        });

        var delay = 0;
        messages.forEach(function(m){
            var variant = (m.category === 'error') ? 'danger' : (m.category || 'info');
            if(variant === 'message') variant = 'info';
            if(!m.message) return;   // пустые не показываем
            setTimeout(function(){ toast(m.message, variant); }, delay);
            delay += 250;
        });
    }

    /* ============================================================
       ДЕЛЕГАТЫ
       ============================================================ */
    document.addEventListener('click', function(e){
        /* Тема */
        var tt = e.target.closest('#themeToggle');
        if(tt){ setTheme(currentTheme() === 'dark' ? 'light' : 'dark'); return; }

        /* Акцент */
        var acc = e.target.closest('.accent-swatch[data-accent]');
        if(acc){ setAccent(acc.dataset.accent); return; }

        /* Плотность */
        var den = e.target.closest('.density-toggle [data-density]');
        if(den){ setDensity(den.dataset.density); return; }

        /* Закрытие alert */
        var closeBtn = e.target.closest('[data-alert-close]');
        if(closeBtn){
            var al = closeBtn.closest('.alert');
            if(al) al.remove();
            return;
        }

        /* Закрытие модалки по data-modal-close */
        var modalClose = e.target.closest('[data-modal-close]');
        if(modalClose){
            e.preventDefault();
            var mid = modalClose.getAttribute('data-modal-close');
            if(mid) closeModal(mid);
            return;
        }

        /* Открытие модалки по data-modal-open */
        var modalOpen = e.target.closest('[data-modal-open]');
        if(modalOpen){
            e.preventDefault();
            var oid = modalOpen.getAttribute('data-modal-open');
            if(oid) openModal(oid);
            return;
        }

        /* Dropdown */
        var dd = e.target.closest('[data-dropdown]');
        if(dd){
            e.preventDefault();
            e.stopPropagation();
            var menu = dd.nextElementSibling;
            if(!menu) return;
            var opened = menu.classList.toggle('show');
            dd.setAttribute('aria-expanded', opened ? 'true' : 'false');
            document.querySelectorAll('.dropdown-menu.show').forEach(function(m){
                if(m !== menu) m.classList.remove('show');
            });
            return;
        }
        if(!e.target.closest('.dropdown')){
            document.querySelectorAll('.dropdown-menu.show').forEach(function(m){
                m.classList.remove('show');
            });
        }
    });

    /* data-confirm на формах */
    document.addEventListener('submit', function(e){
        var msg = e.target.getAttribute('data-confirm');
        if(msg && !window.confirm(msg)) e.preventDefault();
    });

    /* ============================================================
       COUNT-UP
       ============================================================ */
    function animateNumbers(root){
        (root || document).querySelectorAll('[data-count]').forEach(function(el){
            var raw = el.dataset.count || el.textContent;
            var cleaned = String(raw).replace(/[^\d.\-]/g, '');
            var to = parseFloat(cleaned);
            if(isNaN(to)) return;
            var from = 0;
            var start = performance.now();
            var dur = 700;
            var isFloat = cleaned.indexOf('.') !== -1;
            (function tick(now){
                var p = Math.min(1, (now - start) / dur);
                var eased = 1 - Math.pow(1 - p, 3);
                var v = from + (to - from) * eased;
                el.textContent = isFloat ? v.toFixed(1) : Math.round(v);
                if(p < 1) requestAnimationFrame(tick);
            })(start);
        });
    }

    /* ============================================================
       ФИЛЬТРЫ ВВОДА
       ============================================================ */
    document.addEventListener('input', function(e){
        if(e.target.classList.contains('no-emoji')){
            e.target.value = e.target.value.replace(
                /[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2600}-\u{27BF}\u{1F900}-\u{1F9FF}]/gu,
                ''
            );
        }
        if(e.target.classList.contains('phone-input')){
            e.target.value = e.target.value.replace(/[^\d]/g, '').slice(0, 11);
        }
    });

    /* ============================================================
       INIT
       ============================================================ */
    document.addEventListener('DOMContentLoaded', function(){
        initDrawer();
        applyAvatarGradients();
        setTheme(currentTheme());
        setAccent(document.documentElement.getAttribute('data-accent') || 'blue');
        setDensity(document.documentElement.getAttribute('data-density') || 'comfortable');
        consumeFlashMessages();
        animateNumbers();
    });

    /* ============================================================
       ЭКСПОРТ
       ============================================================ */
    window.App = {
        setTheme:       setTheme,
        currentTheme:   currentTheme,
        setAccent:      setAccent,
        setDensity:     setDensity,
        toast:          toast,
        openModal:      openModal,
        closeModal:     closeModal,
        startProgress:  startProgress,
        finishProgress: finishProgress,
        showUndo:       showUndo,
        animateNumbers: animateNumbers,
        hashHue:        hashHue,
        applyAvatarGradients: applyAvatarGradients
    };
})();