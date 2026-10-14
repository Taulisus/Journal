/* ============================================================
   ADD LESSON — быстрый выбор времени, работа с планом,
                массовая отметка
   ============================================================ */
(function(){
    'use strict';

    var TIME_INTERVALS = JSON.parse((document.getElementById('addLessonTimeData') || {}).textContent || '{}');
    var DAY_NAMES = JSON.parse((document.getElementById('addLessonDayNames') || {}).textContent || '[]');
    var PLAN_UNUSED = JSON.parse((document.getElementById('addLessonPlanData') || {}).textContent || '[]');
    var LESSON_TYPE_NAMES = JSON.parse((document.getElementById('addLessonTypesData') || {}).textContent || '{}');
    var DEFAULT_DAY = '1';

    /* ============================================================
       УТИЛИТЫ
       ============================================================ */
    function getWeekdayFromDate(dateStr){
        if(!dateStr) return null;
        var parts = dateStr.split('-');
        if(parts.length !== 3) return null;
        var d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        if(isNaN(d.getTime())) return null;
        var wd = d.getDay();
        return wd === 0 ? '6' : String(wd - 1);
    }

    function splitInterval(v){
        var m = v.match(/^(\d{2})(\d{2})-(\d{2})(\d{2})$/);
        if(!m) return ['',''];
        return [m[1] + ':' + m[2], m[3] + ':' + m[4]];
    }

    /* '0830-1000' → '08:30 – 10:00' */
    function formatHHMM(v){
        var m = v.match(/^(\d{2})(\d{2})-(\d{2})(\d{2})$/);
        return m ? m[1] + ':' + m[2] + ' – ' + m[3] + ':' + m[4] : v;
    }

    /* '0830-1000' → '08:30–10:00' (без пробелов) */
    function formatHHMMShort(v){
        var m = v.match(/^(\d{2})(\d{2})-(\d{2})(\d{2})$/);
        return m ? m[1] + ':' + m[2] + '–' + m[3] + ':' + m[4] : v;
    }

    /* '8:30-10:00' → '0830-1000'; '0930-1100' → '0930-1100' */
    function normalizeTime(value){
        if(!value) return value;
        value = value.trim().replace(/\s+/g, '');

        var m = value.match(/^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$/);
        if(m){
            var h1 = ('0' + m[1]).slice(-2);
            var h2 = ('0' + m[3]).slice(-2);
            return h1 + m[2] + '-' + h2 + m[4];
        }

        m = value.match(/^(\d{1,2})\.(\d{2})-(\d{1,2})\.(\d{2})$/);
        if(m){
            var h1b = ('0' + m[1]).slice(-2);
            var h2b = ('0' + m[3]).slice(-2);
            return h1b + m[2] + '-' + h2b + m[4];
        }

        m = value.match(/^(\d{3})-(\d{4})$/);
        if(m) return '0' + m[1] + '-' + m[2];

        m = value.match(/^(\d{4})(\d{4})$/);
        if(m) return m[1] + '-' + m[2];

        return value;
    }

    /* ============================================================
       ВРЕМЯ — перерисовка
       ============================================================ */
    function rebuildTimeOptions(dateStr){
        if(!dateStr) return;

        var wd = getWeekdayFromDate(dateStr);
        if(wd === null || !TIME_INTERVALS[wd]) wd = DEFAULT_DAY;

        var intervals = TIME_INTERVALS[wd] || TIME_INTERVALS[DEFAULT_DAY] || [];

        /* --- Datalist: value = '0900-1030', label = '08:30 – 10:00' --- */
        var datalist = document.getElementById('timeIntervalOptions');
        if(datalist){
            datalist.innerHTML = '';
            intervals.forEach(function(pair){
                var opt = document.createElement('option');
                opt.value = pair[0];
                opt.label = formatHHMM(pair[0]);
                datalist.appendChild(opt);
            });
        }

        /* --- Кнопки быстрого выбора: '1 пара · 08:30 – 10:00' --- */
        var buttons = document.getElementById('quickTimeButtons');
        if(buttons){
            buttons.innerHTML = '';
            intervals.forEach(function(pair, idx){
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn btn-sm btn-outline-secondary quick-time';
                btn.setAttribute('data-time', pair[0]);
                btn.title = formatHHMM(pair[0]);

                /* Номер пары — жирным, время — серым */
                btn.innerHTML =
                    '<span style="font-weight:600;">' + (idx + 1) + ' пара</span>' +
                    '<span style="margin-left:6px;opacity:.8;font-weight:400;">' +
                        formatHHMMShort(pair[0]) +
                    '</span>';

                buttons.appendChild(btn);
            });

            buttons.querySelectorAll('.quick-time').forEach(function(btn){
                btn.addEventListener('click', function(){
                    var t = this.getAttribute('data-time');
                    var input = document.getElementById('timeInterval');
                    if(input){
                        input.value = t;
                        input.focus();
                    }

                    buttons.querySelectorAll('.quick-time').forEach(function(b){
                        b.classList.remove('btn-primary');
                        b.classList.add('btn-outline-secondary');
                    });
                    this.classList.remove('btn-outline-secondary');
                    this.classList.add('btn-primary');
                });
            });
        }

        var label = document.getElementById('quickTimeDayLabel');
        if(label){
            label.textContent = DAY_NAMES[parseInt(wd, 10)] || '—';
        }
    }

    /* ============================================================
       ПЛАН — темы
       ============================================================ */
    function rebuildPlanTopics(){
        var lt = document.getElementById('lessonType');
        var select = document.getElementById('planTopicSelect');
        var hint = document.getElementById('planHint');
        if(!lt || !select) return;

        var type = lt.value;

        /* Очищаем select полностью */
        while(select.firstChild) select.removeChild(select.firstChild);

        var filtered = (PLAN_UNUSED || []).filter(function(p){
            return p.lesson_type === type;
        });

        if(filtered.length === 0){
            var optEmpty = document.createElement('option');
            optEmpty.value = '';
            optEmpty.textContent = '— Своя тема (введите ниже) —';
            select.appendChild(optEmpty);

            select.disabled = false;
            select.value = '';

            if(hint){
                hint.textContent =
                    'В плане нет неиспользованных тем для этого типа занятия. ' +
                    'Введите тему вручную или добавьте её в план.';
            }
        } else {
            var optOwn = document.createElement('option');
            optOwn.value = '';
            optOwn.textContent = '— Своя тема (введите ниже) —';
            select.appendChild(optOwn);

            filtered.forEach(function(p){
                var opt = document.createElement('option');
                opt.value = String(p.id);
                opt.textContent =
                    (p.order_number ? '№' + p.order_number + '. ' : '') + p.topic;
                opt.dataset.topic = p.topic;
                select.appendChild(opt);
            });

            select.disabled = false;
            select.value = '';

            if(hint){
                hint.textContent = 'Доступно тем из плана: ' + filtered.length + '.';
            }
        }

        var planIdInput = document.getElementById('planIdInput');
        if(planIdInput) planIdInput.value = '';
    }

    function onPlanTopicChange(){
        var select = document.getElementById('planTopicSelect');
        var topicInput = document.getElementById('topicInput');
        var planIdInput = document.getElementById('planIdInput');
        if(!select || !topicInput || !planIdInput) return;

        var opt = select.options[select.selectedIndex];

        if(select.value){
            topicInput.value = opt.dataset.topic;
            planIdInput.value = select.value;
        } else {
            topicInput.value = '';
            planIdInput.value = '';
        }
    }

    /* ============================================================
       МАССОВАЯ ОТМЕТКА
       ============================================================ */
    function bindMassAttendance(){
        var btnAllPresent = document.getElementById('btnAllPresent');
        var btnAllAbsent = document.getElementById('btnAllAbsent');

        if(btnAllPresent){
            btnAllPresent.addEventListener('click', function(){
                document.querySelectorAll('input[type="radio"][id^="att_p_"]').forEach(function(r){
                    r.checked = true;
                });
            });
        }

        if(btnAllAbsent){
            btnAllAbsent.addEventListener('click', function(){
                document.querySelectorAll('input[type="radio"][id^="att_a_"]').forEach(function(r){
                    r.checked = true;
                });
            });
        }
    }

    /* ============================================================
       INIT
       ============================================================ */
    document.addEventListener('DOMContentLoaded', function(){
        var dateInput = document.getElementById('lessonDate');

        if(dateInput && !dateInput.value){
            var today = new Date();
            var y = today.getFullYear();
            var m = String(today.getMonth() + 1).padStart(2, '0');
            var d = String(today.getDate()).padStart(2, '0');
            dateInput.value = y + '-' + m + '-' + d;
        }

        if(dateInput){
            rebuildTimeOptions(dateInput.value);
            dateInput.addEventListener('change', function(){
                rebuildTimeOptions(this.value);
            });
        }

        var timeInput = document.getElementById('timeInterval');
        if(timeInput){
            timeInput.addEventListener('blur', function(){
                this.value = normalizeTime(this.value);
            });
        }

        var lt = document.getElementById('lessonType');
        if(lt) lt.addEventListener('change', rebuildPlanTopics);

        var planSel = document.getElementById('planTopicSelect');
        if(planSel) planSel.addEventListener('change', onPlanTopicChange);

        rebuildPlanTopics();
        bindMassAttendance();
    });

})();