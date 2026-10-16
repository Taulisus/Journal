/* ============================================================
   JOURNAL — drag-scroll, grade-popover, модалки, фильтр по месяцам,
             изменение занятия (дата + время + тип + тема)
   ============================================================ */
(function(){
    'use strict';

    var dataEl = document.getElementById('journalDataScript');
    if(!dataEl) return;

    var JOURNAL = JSON.parse(dataEl.textContent);
    var TIME_INTERVALS = JSON.parse((document.getElementById('journalTimeData') || {}).textContent || '{}');
    var DAY_NAMES = JSON.parse((document.getElementById('journalDayNames') || {}).textContent || '[]');
    var STUDENTS = JSON.parse((document.getElementById('journalStudentsData') || {}).textContent || '[]');

    var DEFAULT_DAY = '1';
    var sc = document.getElementById('journalScroll');

    /* ============================================================
       ВОССТАНОВЛЕНИЕ СКРОЛЛА
       ============================================================ */
    function restoreScroll(){
        if(!sc) return;
        var left = 0, top = 0;
        try {
            left = parseInt(sessionStorage.getItem('journal_scroll_left') || '0', 10) || 0;
            top  = parseInt(sessionStorage.getItem('journal_scroll_top')  || '0', 10) || 0;
            sessionStorage.removeItem('journal_scroll_left');
            sessionStorage.removeItem('journal_scroll_top');
        } catch(e){}
        if(left > 0) sc.scrollLeft = left;
        if(top > 0) window.scrollTo(0, top);
    }

    function saveScrollAndReload(){
        if(sc){
            try {
                sessionStorage.setItem('journal_scroll_left', String(sc.scrollLeft));
                sessionStorage.setItem('journal_scroll_top', String(window.scrollY));
            } catch(e){}
        }
        location.reload();
    }

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

    function formatHHMM(v){
        var m = v.match(/^(\d{2})(\d{2})-(\d{2})(\d{2})$/);
        return m ? m[1] + ':' + m[2] + '–' + m[3] + ':' + m[4] : v;
    }

    function formatDateRu(iso){
        if(!iso) return '';
        var p = iso.split('-');
        if(p.length !== 3) return iso;
        return p[2] + '.' + p[1] + '.' + p[0];
    }

    /**
     * Нормализует время к формату '0900-1030'.
     */
    function normalizeTimeStr(timeStr){
        if(!timeStr) return '';
        var t = timeStr.trim().replace(/\s+/g, '');
        var m = t.match(/^(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})$/);
        if(m){
            return ('0' + m[1]).slice(-2) + m[2] + '-' + ('0' + m[3]).slice(-2) + m[4];
        }
        return t;
    }

    /**
     * Определяет номер пары по дате и времени.
     * Ищет timeStr в списке интервалов для дня недели dateStr.
     * Возвращает 1..7 или null.
     */
    function getPairNumber(dateStr, timeStr){
        if(!dateStr || !timeStr) return null;

        var wd = getWeekdayFromDate(dateStr) || DEFAULT_DAY;
        var intervals = TIME_INTERVALS[wd] || TIME_INTERVALS[DEFAULT_DAY] || [];

        var t = normalizeTimeStr(timeStr);

        for(var i = 0; i < intervals.length; i++){
            if(intervals[i][0] === t){
                return i + 1;
            }
        }
        return null;
    }

    /* ============================================================
       DRAG-SCROLL + клик vs drag
       ============================================================ */
    if(sc){
        var isDown = false;
        var startX, scrollLeft;
        var downPageX = 0, downPageY = 0;
        var moved = false;

        sc.addEventListener('mousedown', function(e){
            if(e.target.closest('button, select, a, input, .dropdown, .lesson-head__btn')) return;
            isDown = true;
            startX = e.pageX - sc.offsetLeft;
            scrollLeft = sc.scrollLeft;
            downPageX = e.pageX;
            downPageY = e.pageY;
            moved = false;
        });

        sc.addEventListener('mousemove', function(e){
            if(!isDown) return;
            var dx = Math.abs(e.pageX - downPageX);
            var dy = Math.abs(e.pageY - downPageY);
            if(dx > 5 || dy > 5){
                moved = true;
                sc.classList.add('is-dragging');
            }
            if(moved){
                e.preventDefault();
                sc.scrollLeft = scrollLeft - (e.pageX - sc.offsetLeft - startX) * 1.5;
            }
        });

        ['mouseup','mouseleave'].forEach(function(ev){
            sc.addEventListener(ev, function(){
                isDown = false;
                setTimeout(function(){ sc.classList.remove('is-dragging'); }, 0);
            });
        });

        sc.addEventListener('click', function(e){
            if(moved){
                moved = false;
                return;
            }
            var cell = e.target.closest('.journal-cell-clickable');
            if(!cell) return;
            if(e.target.closest('button, select, a, input, .dropdown, .lesson-head__btn')) return;
            openPopover(cell);
        });

        sc.addEventListener('keydown', function(e){
            var cell = e.target.closest('.journal-cell-clickable');
            if(!cell) return;
            if(e.key === 'Enter' || e.key === ' '){
                e.preventDefault();
                openPopover(cell);
            }
        });
    }

    /* ============================================================
       ФИЛЬТР ПО МЕСЯЦАМ
       ============================================================ */
    if(sc){
        var months = {};
        JOURNAL.lessons.forEach(function(l, i){
            var mm = l.date.substring(5, 7);
            if(!months[mm]) months[mm] = [];
            months[mm].push(i);
        });

        var monthNames = {
            '01': 'Янв', '02': 'Фев', '03': 'Мар', '04': 'Апр',
            '05': 'Май', '06': 'Июн', '07': 'Июл', '08': 'Авг',
            '09': 'Сен', '10': 'Окт', '11': 'Ноя', '12': 'Дек'
        };

        var nav = document.getElementById('monthNav');
        var sortedMonths = Object.keys(months).sort();

        sortedMonths.forEach(function(mm){
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-sm btn-outline-primary';
            btn.dataset.month = mm;
            btn.textContent = monthNames[mm] || mm;
            nav.appendChild(btn);
        });

        function applyMonthFilter(mm){
            var ths = document.querySelectorAll('th.lesson-head');
            var tds = document.querySelectorAll('.journal-cell-clickable');

            if(mm === 'all'){
                ths.forEach(function(th){ th.classList.remove('is-month-hidden'); });
                tds.forEach(function(td){ td.classList.remove('lesson-cell-hidden'); });
            } else {
                ths.forEach(function(th){
                    var m = th.dataset.lessonMonth;
                    th.classList.toggle('is-month-hidden', m !== mm);
                });
                tds.forEach(function(td){
                    var m = td.dataset.lessonMonth;
                    td.classList.toggle('lesson-cell-hidden', m !== mm);
                });
            }

            nav.querySelectorAll('.btn').forEach(function(b){
                b.classList.remove('is-active');
                b.classList.remove('btn-primary');
                b.classList.add('btn-outline-primary');
            });
            var activeBtn = nav.querySelector('[data-month="' + mm + '"]');
            if(activeBtn){
                activeBtn.classList.remove('btn-outline-primary');
                activeBtn.classList.add('btn-primary');
                activeBtn.classList.add('is-active');
            }
        }

        nav.addEventListener('click', function(e){
            var btn = e.target.closest('[data-month]');
            if(!btn) return;
            applyMonthFilter(btn.dataset.month);
        });

        applyMonthFilter('all');

        var dateSearch = document.getElementById('dateSearchInput');
        var dateStatus = document.getElementById('dateSearchStatus');
        if(dateSearch){
            dateSearch.addEventListener('keydown', function(e){
                if(e.key !== 'Enter') return;
                e.preventDefault();
                var query = this.value.trim();
                if(!query){
                    dateStatus.textContent = '';
                    return;
                }

                var found = -1;
                for(var i = 0; i < JOURNAL.lessons.length; i++){
                    var l = JOURNAL.lessons[i];
                    if(l.dateFormatted === query ||
                       l.dateFormatted.indexOf(query) !== -1 ||
                       l.dateFormatted.replace(/\./g, '').indexOf(query.replace(/\./g, '')) !== -1){
                        found = i;
                        break;
                    }
                }

                if(found >= 0){
                    var mm = JOURNAL.lessons[found].date.substring(5, 7);
                    applyMonthFilter(mm);
                    dateStatus.textContent = '✓ ' + JOURNAL.lessons[found].dateFormatted;
                    dateStatus.className = 'small text-success';
                } else {
                    dateStatus.textContent = '✗ Не найдено';
                    dateStatus.className = 'small text-danger';
                }
            });
        }
    }

    /* ============================================================
       GRADE POPOVER
       ============================================================ */
    var popover = null;

    function openPopover(cell){
        closePopover();

        var entryId = cell.dataset.entryId;
        if(!entryId) return;

        var parts = (cell.dataset.current || '').split('|');
        var curA = parts[0], curG = parts[1] || '';

        var html = '<div class="grade-popover">'
                 + '<button type="button" data-grade="5" class="grade-5' + (curG === '5' ? ' is-current' : '') + '">5</button>'
                 + '<button type="button" data-grade="4" class="grade-4' + (curG === '4' ? ' is-current' : '') + '">4</button>'
                 + '<button type="button" data-grade="3" class="grade-3' + (curG === '3' ? ' is-current' : '') + '">3</button>'
                 + '<button type="button" data-grade="2" class="grade-2' + (curG === '2' ? ' is-current' : '') + '">2</button>'
                 + '<button type="button" data-grade="passed" class="grade-5' + (curG === 'passed' ? ' is-current' : '') + '">З</button>'
                 + '<button type="button" data-attendance="absent"' + (curA === 'absent' ? ' class="is-current"' : '') + '>Н</button>'
                 + '<button type="button" data-clear="1"' + (!curG && curA !== 'absent' ? ' class="is-current"' : '') + '>—</button>'
                 + '</div>';

        var wrap = document.createElement('div');
        wrap.innerHTML = html;
        popover = wrap.firstElementChild;
        document.body.appendChild(popover);

        var r = cell.getBoundingClientRect();
        var pw = popover.offsetWidth, ph = popover.offsetHeight;
        var left = Math.min(window.innerWidth - pw - 8, Math.max(8, r.left + r.width / 2 - pw / 2));
        var top = r.top - ph - 8;
        if(top < 8) top = r.bottom + 8;
        popover.style.left = left + 'px';
        popover.style.top = top + 'px';

        popover.addEventListener('click', function(e){
            var b = e.target.closest('button');
            if(!b) return;

            var prev = cell.dataset.current;
            var attendance = 'present';
            var grade = '';

            if(b.dataset.clear){
                attendance = 'present';
                grade = '';
            } else if(b.dataset.attendance === 'absent'){
                attendance = 'absent';
                grade = '';
            } else if(b.dataset.grade){
                attendance = 'present';
                grade = b.dataset.grade;
            }

            saveEntry(cell, attendance, grade, prev);
            closePopover();
        });
    }

    function closePopover(){
        if(popover){ popover.remove(); popover = null; }
    }

    function renderCellMark(cell, attendance, grade){
        var newHtml;
        if(attendance === 'absent'){
            newHtml = '<span class="mark mark-absent" title="Отсутствовал">✗</span>';
        } else if(grade){
            newHtml = '<span class="mark mark-' + grade + '">' +
                      (grade === 'passed' ? 'З' : grade) +
                      '</span>';
        } else {
            newHtml = '<span class="mark mark-present" title="Присутствовал">✓</span>';
        }
        cell.innerHTML = newHtml;
        cell.dataset.current = attendance + '|' + (grade || '');
    }

    function saveEntry(cell, attendance, grade, prev){
        var entryId = cell.dataset.entryId;
        if(!entryId) return;

        var formData = new FormData();
        formData.append('entry_id', entryId);
        formData.append('attendance', attendance);
        formData.append('grade', grade);

        fetch('/journal/' + JOURNAL.gsid + '/update-entry', {
            method: 'POST',
            body: formData
        })
        .then(function(r){ return r.json(); })
        .then(function(result){
            if(result.success){
                renderCellMark(cell, attendance, grade);
                App.showUndo('Отметка сохранена', function(){
                    var pp = (prev || '').split('|');
                    saveEntry(cell, pp[0] || 'present', pp[1] || '', prev);
                });
            } else {
                App.toast('Ошибка: ' + result.message, 'danger');
            }
        })
        .catch(function(){
            App.toast('Ошибка соединения', 'danger');
        });
    }

    document.addEventListener('click', function(e){
        if(!popover) return;
        if(e.target.closest('.grade-popover')) return;
        if(e.target.closest('.journal-cell-clickable')) return;
        closePopover();
    });
    document.addEventListener('keydown', function(e){
        if(e.key === 'Escape' && popover) closePopover();
    });

    /* ============================================================
       ОБНОВЛЕНИЕ ЯЧЕЕК БЕЗ ПЕРЕЗАГРУЗКИ (массовые оценки)
       ============================================================ */
    function reloadLessonCellsFromUpdates(updates){
        var byId = {};
        updates.forEach(function(u){ byId[u.entry_id] = u; });

        document.querySelectorAll('.journal-cell-clickable').forEach(function(cell){
            var entryId = parseInt(cell.dataset.entryId, 10);
            if(!entryId) return;
            var upd = byId[entryId];
            if(!upd) return;
            renderCellMark(cell, upd.attendance, upd.grade || '');
        });
    }

    /* ============================================================
       МОДАЛКА: ИЗМЕНИТЬ ЗАНЯТИЕ (дата + время + тип + тема)
       ============================================================ */
    var elCurrentLessonIdx = null;
    var elPlanItems = [];   // все темы из плана, полученные с сервера

    function rebuildQuickTimes(dateStr){
        var wd = getWeekdayFromDate(dateStr) || DEFAULT_DAY;
        var intervals = TIME_INTERVALS[wd] || TIME_INTERVALS[DEFAULT_DAY] || [];

        var dayLabel = document.getElementById('elDayLabel');
        if(dayLabel) dayLabel.textContent = DAY_NAMES[parseInt(wd, 10)] || '—';

        var datalist = document.getElementById('elTimeDatalist');
        if(datalist){
            datalist.innerHTML = '';
            intervals.forEach(function(pair){
                var opt = document.createElement('option');
                opt.value = pair[0];
                opt.label = pair[1];
                datalist.appendChild(opt);
            });
        }

        var buttons = document.getElementById('elQuickTimes');
        if(buttons){
            buttons.innerHTML = '';
            intervals.forEach(function(pair, idx){
                var btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn btn-sm btn-outline-secondary';
                btn.setAttribute('data-time', pair[0]);
                btn.innerHTML = '<span style="font-weight:600;">' + (idx + 1) + ' пара</span>'
                              + '<span style="margin-left:6px;opacity:.8;font-weight:400;">'
                              + formatHHMM(pair[0]) + '</span>';
                btn.addEventListener('click', function(){
                    var t = this.getAttribute('data-time');
                    document.getElementById('elTime').value = t;
                    document.getElementById('elPair').value = idx + 1;

                    buttons.querySelectorAll('.btn').forEach(function(b){
                        b.classList.remove('btn-primary');
                        b.classList.add('btn-outline-secondary');
                    });
                    this.classList.remove('btn-outline-secondary');
                    this.classList.add('btn-primary');
                });
                buttons.appendChild(btn);
            });
        }
    }

    /**
     * Пересобирает селект «Тема из плана» по текущему типу занятия.
     */
    function rebuildPlanTopics(keepSelectedId){
        var typeSelect = document.getElementById('elType');
        var select = document.getElementById('elPlanSelect');
        var hint = document.getElementById('elPlanHint');
        if(!typeSelect || !select) return;

        var currentType = typeSelect.value;

        while(select.firstChild) select.removeChild(select.firstChild);

        var optOwn = document.createElement('option');
        optOwn.value = '';
        optOwn.textContent = '— Своя тема (введите ниже) —';
        select.appendChild(optOwn);

        var filtered = (elPlanItems || []).filter(function(it){
            return it.lesson_type === currentType;
        });

        filtered.forEach(function(it){
            var opt = document.createElement('option');
            opt.value = String(it.id);
            var label = (it.order_number ? '№' + it.order_number + '. ' : '') + it.topic;
            if(it.used_lesson_id && it.used_date){
                label += '  ·  занята ' + formatDateRu(it.used_date);
            }
            opt.textContent = label;
            opt.dataset.topic = it.topic;
            if(it.used_lesson_id && it.used_date){
                opt.dataset.usedDate = it.used_date;
            }
            select.appendChild(opt);
        });

        if(hint){
            if(filtered.length === 0){
                hint.textContent = 'В плане нет тем для выбранного типа занятия. ' +
                    'Введите свою тему или выберите другой тип.';
            } else {
                hint.textContent = 'Доступно тем для этого типа: ' + filtered.length + '.';
            }
        }

        if(keepSelectedId){
            select.value = String(keepSelectedId);
        } else {
            select.value = '';
        }
    }

    document.querySelectorAll('.edit-lesson-btn').forEach(function(btn){
        btn.addEventListener('click', function(){
            var idx = parseInt(this.dataset.lessonIdx, 10);
            var l = JOURNAL.lessons[idx];
            if(!l) return;

            elCurrentLessonIdx = idx;
            elPlanItems = [];

            document.getElementById('elCurrentInfo').textContent =
                l.dateFormatted + ' · ' + formatHHMM(l.time) +
                (l.typeName ? ' · ' + l.typeName : '') +
                (l.topic ? ' · «' + l.topic + '»' : '');

            document.getElementById('elOldDate').value = l.date;
            document.getElementById('elOldTime').value = l.time;
            document.getElementById('elDate').value = l.date;
            document.getElementById('elTime').value = l.time;
            document.getElementById('elType').value = l.type;
            document.getElementById('elTopic').value = l.topic || '';
            document.getElementById('elPlanId').value = '';

            // Заполняем номер пары из времени
            var pairNum = getPairNumber(l.date, l.time);
            document.getElementById('elPair').value = pairNum || '';

            // Сбрасываем селект тем
            var select = document.getElementById('elPlanSelect');
            var hint = document.getElementById('elPlanHint');
            while(select.firstChild) select.removeChild(select.firstChild);
            var optOwn = document.createElement('option');
            optOwn.value = '';
            optOwn.textContent = '— Своя тема (введите ниже) —';
            select.appendChild(optOwn);
            if(hint) hint.textContent = 'Загружаем темы…';

            rebuildQuickTimes(l.date);

            App.openModal('editLessonModal');

            fetch('/journal/' + JOURNAL.gsid + '/plan-list'
                  + '?date=' + encodeURIComponent(l.date)
                  + '&time_interval=' + encodeURIComponent(l.time)
                  + '&semester=' + encodeURIComponent(JOURNAL.semester))
                .then(function(r){ return r.json(); })
                .then(function(data){
                    if(!data.success){
                        if(hint) hint.textContent = 'Не удалось загрузить план.';
                        return;
                    }

                    elPlanItems = data.items || [];

                    // Пытаемся найти пункт плана с той же темой
                    var currentTopic = (l.topic || '').trim();
                    var matchedId = null;
                    if(currentTopic){
                        var found = elPlanItems.find(function(it){
                            return (it.topic || '').trim() === currentTopic;
                        });
                        if(found) matchedId = found.id;
                    }

                    rebuildPlanTopics(matchedId);

                    if(matchedId){
                        document.getElementById('elPlanId').value = String(matchedId);
                    }
                })
                .catch(function(){
                    if(hint) hint.textContent = 'Ошибка загрузки плана.';
                });
        });
    });

    // Смена типа занятия → пересобираем список тем
    var elType = document.getElementById('elType');
    if(elType){
        elType.addEventListener('change', function(){
            var currentPlanId = document.getElementById('elPlanId').value || null;

            var keepId = null;
            if(currentPlanId){
                var found = (elPlanItems || []).find(function(it){
                    return String(it.id) === String(currentPlanId) &&
                           it.lesson_type === elType.value;
                });
                if(found) keepId = found.id;
            }

            rebuildPlanTopics(keepId);

            if(!keepId){
                document.getElementById('elPlanId').value = '';

                var currentTopic = document.getElementById('elTopic').value.trim();
                var topicExists = (elPlanItems || []).some(function(it){
                    return (it.topic || '').trim() === currentTopic;
                });
                if(!topicExists){
                    document.getElementById('elTopic').value = '';
                }
            }
        });
    }

    // Выбор темы из плана → подставляем в input
    var elPlanSelect = document.getElementById('elPlanSelect');
    if(elPlanSelect){
        elPlanSelect.addEventListener('change', function(){
            var opt = this.options[this.selectedIndex];
            var input = document.getElementById('elTopic');
            var hidden = document.getElementById('elPlanId');

            if(this.value){
                input.value = opt.dataset.topic || '';
                hidden.value = this.value;
            } else {
                input.value = '';
                hidden.value = '';
            }
        });
    }

    // Смена даты — обновляем быстрый выбор + пересчитываем номер пары
    var elDate = document.getElementById('elDate');
    if(elDate){
        elDate.addEventListener('change', function(){
            rebuildQuickTimes(this.value);

            var currentTime = document.getElementById('elTime').value;
            var pairNum = getPairNumber(this.value, currentTime);
            document.getElementById('elPair').value = pairNum || '';
        });
    }

    // Нормализация времени + пересчёт номера пары
    var elTime = document.getElementById('elTime');
    if(elTime){
        elTime.addEventListener('blur', function(){
            var normalized = normalizeTimeStr(this.value);
            if(normalized) this.value = normalized;

            var currentDate = document.getElementById('elDate').value;
            var pairNum = getPairNumber(currentDate, this.value);
            document.getElementById('elPair').value = pairNum || '';
        });
    }

    // Отправка формы
    var elForm = document.getElementById('editLessonForm');
    if(elForm){
        elForm.addEventListener('submit', function(e){
            e.preventDefault();

            var formData = new FormData(elForm);
            var topic = (formData.get('new_topic') || '').toString().trim();
            if(!topic){
                App.toast('Введите тему занятия', 'warning');
                return;
            }

            fetch('/journal/' + JOURNAL.gsid + '/update-lesson-full', {
                method: 'POST',
                body: formData
            })
            .then(function(r){ return r.json(); })
            .then(function(result){
                if(result.success){
                    App.closeModal('editLessonModal');
                    App.toast(result.message || 'Занятие обновлено', 'success');
                    saveScrollAndReload();
                } else {
                    App.toast('Ошибка: ' + result.message, 'danger');
                }
            })
            .catch(function(){
                App.toast('Ошибка соединения', 'danger');
            });
        });
    }

    /* ============================================================
       МОДАЛКА: МАССОВЫЕ ОЦЕНКИ
       ============================================================ */
    var mgCurrentLessonIdx = null;

    function mgGradeButtonsHtml(currentGrade){
        var buttons = [
            { value: '5', label: '5', cls: 'success' },
            { value: '4', label: '4', cls: 'info' },
            { value: '3', label: '3', cls: 'warning' },
            { value: '2', label: '2', cls: 'danger' },
            { value: 'passed', label: 'З', cls: 'success' },
            { value: '', label: '—', cls: 'secondary' }
        ];

        return '<div class="d-flex gap-1 flex-wrap justify-content-center">' +
            buttons.map(function(b){
                var active = (b.value === currentGrade);
                var cls = active
                    ? 'btn btn-sm btn-' + b.cls
                    : 'btn btn-sm btn-outline-' + b.cls;
                return '<button type="button" class="' + cls + ' mg-grade-btn" ' +
                       'data-grade="' + b.value + '" style="min-width:38px;">' + b.label + '</button>';
            }).join('') +
            '</div>';
    }

    function mgBuildTable(lesson){
        var tbody = document.getElementById('mgStudentsBody');
        tbody.innerHTML = '';

        var order = {};
        STUDENTS.forEach(function(s, i){ order[s.id] = i; });

        var studentIds = Object.keys(lesson.entries);
        studentIds.sort(function(a, b){
            return (order[a] !== undefined ? order[a] : 999) -
                   (order[b] !== undefined ? order[b] : 999);
        });

        studentIds.forEach(function(sid){
            var entry = lesson.entries[sid];
            var student = STUDENTS.find(function(s){ return String(s.id) === String(sid); });
            var name = student ? student.name : '#' + sid;

            var tr = document.createElement('tr');
            tr.dataset.studentId = sid;
            tr.dataset.entryId = entry.id;
            tr.dataset.attendance = entry.attendance;
            tr.dataset.grade = entry.grade || '';

            tr.innerHTML =
                '<td class="text-center"><input type="checkbox" class="form-check-input mg-student-check" checked></td>' +
                '<td class="small">' + name + '</td>' +
                '<td class="text-center">' +
                    (entry.attendance === 'present'
                        ? '<span class="badge bg-success">✓</span>'
                        : '<span class="badge bg-danger">✗</span>') +
                '</td>' +
                '<td class="text-center">' + mgGradeButtonsHtml(entry.grade || '') + '</td>';

            tbody.appendChild(tr);
        });

        mgAttachHandlers();
    }

    function mgAttachHandlers(){
        document.querySelectorAll('#mgStudentsBody .mg-grade-btn').forEach(function(btn){
            btn.addEventListener('click', function(){
                var tr = this.closest('tr');
                var newGrade = this.dataset.grade;
                tr.dataset.grade = newGrade;
                var tdGrade = tr.querySelector('td:last-child');
                tdGrade.innerHTML = mgGradeButtonsHtml(newGrade);
                mgAttachHandlers();
            });
        });

        document.querySelectorAll('.mg-student-check').forEach(function(cb){
            cb.addEventListener('change', mgUpdateSelection);
        });
    }

    function mgUpdateSelection(){
        var checks = document.querySelectorAll('.mg-student-check');
        var checked = document.querySelectorAll('.mg-student-check:checked').length;
        var selectAll = document.getElementById('mgSelectAll');
        if(selectAll){
            selectAll.checked = (checked === checks.length);
            selectAll.indeterminate = (checked > 0 && checked < checks.length);
        }
    }

    document.querySelectorAll('.mass-grade-btn').forEach(function(btn){
        btn.addEventListener('click', function(){
            var idx = parseInt(this.dataset.lessonIdx, 10);
            mgCurrentLessonIdx = idx;
            var lesson = JOURNAL.lessons[idx];
            if(!lesson) return;

            document.getElementById('mgLessonTitle').textContent =
                lesson.dateFormatted + (lesson.dayOfWeek ? ' · ' + lesson.dayOfWeek : '') +
                (lesson.time ? ' · ' + formatHHMM(lesson.time) : '');
            document.getElementById('mgLessonSubtitle').textContent =
                lesson.typeName + (lesson.topic ? ' · ' + lesson.topic : '');
            document.getElementById('mgCountBadge').textContent =
                Object.keys(lesson.entries).length + ' студентов';
            document.getElementById('mgStatus').textContent = '';
            document.getElementById('mgFilterAll').checked = true;

            mgBuildTable(lesson);
            App.openModal('massGradeModal');
        });
    });

    var mgSelectAll = document.getElementById('mgSelectAll');
    if(mgSelectAll){
        mgSelectAll.addEventListener('change', function(){
            document.querySelectorAll('.mg-student-check').forEach(function(cb){
                cb.checked = mgSelectAll.checked;
            });
            mgUpdateSelection();
        });
    }

    document.querySelectorAll('.mg-set-all').forEach(function(btn){
        btn.addEventListener('click', function(){
            var grade = this.dataset.grade;
            document.querySelectorAll('#mgStudentsBody tr').forEach(function(tr){
                var check = tr.querySelector('.mg-student-check');
                if(!check || !check.checked) return;
                var attendance = tr.dataset.attendance;
                if(attendance !== 'present') return;
                tr.dataset.grade = grade;
                var tdGrade = tr.querySelector('td:last-child');
                tdGrade.innerHTML = mgGradeButtonsHtml(grade);
            });
            mgAttachHandlers();
        });
    });

    document.querySelectorAll('input[name="mgFilter"]').forEach(function(radio){
        radio.addEventListener('change', function(){
            var val = this.value;
            document.querySelectorAll('#mgStudentsBody tr').forEach(function(tr){
                if(val === 'all'){
                    tr.style.display = '';
                } else if(val === 'present'){
                    tr.style.display = tr.dataset.attendance === 'present' ? '' : 'none';
                } else if(val === 'absent'){
                    tr.style.display = tr.dataset.attendance === 'absent' ? '' : 'none';
                }
            });
        });
    });

    var mgSaveBtn = document.getElementById('mgSaveBtn');
    if(mgSaveBtn){
        mgSaveBtn.addEventListener('click', function(){
            if(mgCurrentLessonIdx === null) return;

            var updates = [];
            document.querySelectorAll('#mgStudentsBody tr').forEach(function(tr){
                var check = tr.querySelector('.mg-student-check');
                if(!check || !check.checked) return;
                updates.push({
                    entry_id: parseInt(tr.dataset.entryId, 10),
                    attendance: tr.dataset.attendance,
                    grade: tr.dataset.grade || null
                });
            });

            if(!updates.length){
                App.toast('Не выбрано ни одного студента', 'warning');
                return;
            }

            var btn = this;
            var origHtml = btn.innerHTML;
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Сохранение...';

            fetch('/journal/' + JOURNAL.gsid + '/update-grades-batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ updates: updates })
            })
            .then(function(r){ return r.json(); })
            .then(function(result){
                if(result.success){
                    App.toast(result.message || 'Оценки сохранены', 'success');
                    App.closeModal('massGradeModal');
                    reloadLessonCellsFromUpdates(updates);
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                } else {
                    App.toast('Ошибка: ' + result.message, 'danger');
                    btn.disabled = false;
                    btn.innerHTML = origHtml;
                }
            })
            .catch(function(){
                App.toast('Ошибка соединения', 'danger');
                btn.disabled = false;
                btn.innerHTML = origHtml;
            });
        });
    }

    /* ============================================================
       МОДАЛКА: ОЦЕНКИ ЗА СЕМЕСТР
       ============================================================ */
    var btnSemester = document.getElementById('btnSemesterGrades');
    if(btnSemester){
        btnSemester.addEventListener('click', function(){
            var gsid = this.dataset.gsid;
            var semester = this.dataset.semester;

            document.getElementById('semGradeSemester').textContent = semester;
            document.getElementById('semGradeStatus').textContent = '';

            var tbody = document.getElementById('semGradesBody');
            tbody.innerHTML = '<tr><td colspan="2" class="text-center">'
                + '<div class="skeleton skeleton--block"></div></td></tr>';

            App.openModal('semesterGradesModal');

            fetch('/journal/' + gsid + '/semester-grades?semester=' + semester)
                .then(function(r){ return r.text(); })
                .then(function(html){
                    tbody.innerHTML = html;
                    sgAttachHandlers();
                })
                .catch(function(){
                    tbody.innerHTML = '<tr><td colspan="2" class="text-center text-danger">'
                        + 'Ошибка загрузки</td></tr>';
                });
        });
    }

    function sgAttachHandlers(){
        document.querySelectorAll('#semGradesBody .sem-grade-btn').forEach(function(btn){
            btn.addEventListener('click', function(){
                var studentId = this.dataset.studentId;
                var semester = this.dataset.semester;
                var gsid = this.dataset.gsid;
                var value = this.dataset.value;

                var formData = new FormData();
                formData.append('student_id', studentId);
                formData.append('semester', semester);
                formData.append('grade', value);

                fetch('/journal/' + gsid + '/set-semester-grade', {
                    method: 'POST',
                    body: formData
                })
                .then(function(r){ return r.json(); })
                .then(function(result){
                    if(result.success){
                        var tr = btn.closest('tr');
                        tr.querySelectorAll('.sem-grade-btn').forEach(function(b){
                            b.classList.remove('btn-primary');
                            b.classList.add('btn-outline-secondary');
                        });
                        btn.classList.remove('btn-outline-secondary');
                        btn.classList.add('btn-primary');

                        document.getElementById('semGradeStatus').textContent =
                            '✓ Оценка сохранена';
                        setTimeout(function(){
                            document.getElementById('semGradeStatus').textContent = '';
                        }, 2000);
                    } else {
                        App.toast('Ошибка сохранения', 'danger');
                    }
                })
                .catch(function(){
                    App.toast('Ошибка соединения', 'danger');
                });
            });
        });
    }

    /* ============================================================
       МОБИЛЬНАЯ ВЕРСИЯ
       ============================================================ */
    var selectedMobileLessonIdx = null;

    window.filterMobileLessons = function(){
        var typeFilter = document.getElementById('mobileTypeFilter').value;
        var searchText = document.getElementById('mobileLessonSearch').value.toLowerCase().trim();
        var cards = document.querySelectorAll('.mobile-lesson-card');

        cards.forEach(function(card){
            var type = card.dataset.type;
            var searchData = card.dataset.search.toLowerCase();
            var matchesType = !typeFilter || type === typeFilter;
            var matchesSearch = !searchText || searchData.indexOf(searchText) !== -1;
            card.style.display = (matchesType && matchesSearch) ? '' : 'none';
        });
    };

    var mtf = document.getElementById('mobileTypeFilter');
    if(mtf) mtf.addEventListener('change', window.filterMobileLessons);
    var mls = document.getElementById('mobileLessonSearch');
    if(mls) mls.addEventListener('input', window.filterMobileLessons);

    document.querySelectorAll('.mobile-lesson-card').forEach(function(card){
        card.addEventListener('click', function(){
            var idx = parseInt(this.dataset.index, 10);
            selectMobileLesson(idx, this);
        });
    });

    function selectMobileLesson(index, card){
        document.querySelectorAll('.mobile-lesson-card').forEach(function(c){
            c.style.background = '';
        });
        card.style.background = 'var(--brand-50)';

        selectedMobileLessonIdx = index;
        var lesson = JOURNAL.lessons[index];
        if(!lesson) return;

        document.getElementById('selectedLessonTitle').textContent =
            lesson.dateFormatted + (lesson.dayOfWeek ? ' • ' + lesson.dayOfWeek : '') +
            (lesson.time ? ' • ' + formatHHMM(lesson.time) : '');
        document.getElementById('selectedLessonType').textContent = lesson.typeName;
        document.getElementById('selectedLessonTopic').textContent = lesson.topic || '—';

        document.getElementById('selectedLessonCard').style.display = '';
        document.getElementById('mobileStudentsList').style.display = '';

        document.querySelectorAll('.attendance-buttons').forEach(function(container){
            var studentId = container.dataset.studentId;
            var entry = lesson.entries[studentId];

            if(!entry){
                container.innerHTML = '<span class="text-muted small">Нет записи</span>';
                return;
            }

            var html = '';
            html += '<button class="btn btn-sm ' +
                    (entry.attendance === 'present' && !entry.grade ? 'btn-success' : 'btn-outline-success') +
                    '" onclick="quickMark(' + entry.id + ', \'present\', \'\', this)">' +
                    '<i class="bi bi-check-lg"></i></button>';

            html += '<button class="btn btn-sm ' +
                    (entry.attendance === 'absent' ? 'btn-danger' : 'btn-outline-danger') +
                    '" onclick="quickMark(' + entry.id + ', \'absent\', \'\', this)">' +
                    '<i class="bi bi-x-lg"></i></button>';

            html += '<div style="width:1px;background:var(--border);margin:0 4px;"></div>';

            ['2', '3', '4', '5'].forEach(function(grade){
                html += '<button class="btn btn-sm ' +
                        (entry.grade === grade ? 'btn-primary' : 'btn-outline-primary') +
                        '" onclick="quickMark(' + entry.id + ', \'present\', \'' + grade + '\', this)">' +
                        grade + '</button>';
            });

            html += '<button class="btn btn-sm ' +
                    (entry.grade === 'passed' ? 'btn-success' : 'btn-outline-success') +
                    '" onclick="quickMark(' + entry.id + ', \'present\', \'passed\', this)">З</button>';

            container.innerHTML = html;
        });

        setTimeout(function(){
            var el = document.getElementById('mobileStudentsList');
            if(el) el.scrollIntoView({ behavior:'smooth', block:'start' });
        }, 100);
    }

    window.clearMobileSelection = function(){
        selectedMobileLessonIdx = null;
        document.querySelectorAll('.mobile-lesson-card').forEach(function(c){
            c.style.background = '';
        });
        document.getElementById('selectedLessonCard').style.display = 'none';
        document.getElementById('mobileStudentsList').style.display = 'none';
    };

    window.quickMark = function(entryId, attendance, grade, btn){
        var formData = new FormData();
        formData.append('entry_id', entryId);
        formData.append('attendance', attendance);
        formData.append('grade', grade);

        fetch('/journal/' + JOURNAL.gsid + '/update-entry', {
            method: 'POST',
            body: formData
        })
        .then(function(r){ return r.json(); })
        .then(function(result){
            if(result.success){
                var container = btn.closest('.attendance-buttons');
                if(container){
                    container.querySelectorAll('.btn').forEach(function(b){
                        b.classList.remove('btn-success', 'btn-danger', 'btn-primary');
                        b.classList.remove('btn-outline-success', 'btn-outline-danger', 'btn-outline-primary');
                        var text = b.textContent.trim();
                        if(text === '') b.classList.add('btn-outline-success');
                        else if(text === '') b.classList.add('btn-outline-danger');
                        else if(text === 'З') b.classList.add('btn-outline-success');
                        else if(['2','3','4','5'].indexOf(text) !== -1) b.classList.add('btn-outline-primary');
                    });

                    if(attendance === 'absent'){
                        btn.className = 'btn btn-sm btn-danger';
                    } else if(grade){
                        btn.className = grade === 'passed'
                            ? 'btn btn-sm btn-success'
                            : 'btn btn-sm btn-primary';
                    } else {
                        btn.className = 'btn btn-sm btn-success';
                    }
                }

                if(selectedMobileLessonIdx !== null){
                    var lesson = JOURNAL.lessons[selectedMobileLessonIdx];
                    Object.keys(lesson.entries).forEach(function(key){
                        if(lesson.entries[key].id === entryId){
                            lesson.entries[key].attendance = attendance;
                            lesson.entries[key].grade = grade;
                        }
                    });
                }

                App.toast('Сохранено', 'success');
            } else {
                App.toast('Ошибка: ' + result.message, 'danger');
            }
        })
        .catch(function(){
            App.toast('Ошибка соединения', 'danger');
        });
    };

    /* ============================================================
       ВОССТАНОВЛЕНИЕ СКРОЛЛА
       ============================================================ */
    if(document.readyState === 'loading'){
        document.addEventListener('DOMContentLoaded', restoreScroll);
    } else {
        restoreScroll();
    }

})();