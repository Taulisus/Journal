/* ============================================================
   GROUP SUBJECTS — фильтр, модалки, часы, копирование,
                    клик по карточке
   ============================================================ */
(function(){
    'use strict';

    /* ============================================================
       КЛИК ПО КАРТОЧКЕ ЖУРНАЛА
       — открывает журнал, но игнорирует клики по:
         • кнопке меню (⋮) и её dropdown
         • любым кнопкам, ссылкам, полям внутри карточки
       ============================================================ */
    document.addEventListener('click', function(e){
        var card = e.target.closest('.journal-card');
        if(!card) return;

        // Клик по интерактиву внутри карточки — не открываем
        if(e.target.closest('button, a, input, select, .dropdown, .dropdown-menu')) return;

        var href = card.dataset.href;
        if(!href) return;

        // Если пользователь делал выделение текста — не открываем
        var sel = window.getSelection && window.getSelection();
        if(sel && sel.toString().length > 0) return;

        window.location.href = href;
    });

    /* Клавиатура — Enter / Space на карточке */
    document.addEventListener('keydown', function(e){
        if(e.key !== 'Enter' && e.key !== ' ') return;
        var card = e.target.closest('.journal-card');
        if(!card) return;
        if(e.target !== card) return;
        e.preventDefault();
        var href = card.dataset.href;
        if(href) window.location.href = href;
    });

    /* ============================================================
       ФИЛЬТР
       ============================================================ */
    var search = document.getElementById('jSearch');
    var groupSel = document.getElementById('jGroup');
    var list = document.getElementById('journalsList');
    var emptyBlock = document.getElementById('jEmpty');
    var totalBadge = document.getElementById('totalBadge');

    function applyFilter(){
        if(!list) return;
        var q = (search.value || '').toLowerCase().trim();
        var g = groupSel.value;
        var items = list.querySelectorAll('.journal-card');
        var visible = 0;

        items.forEach(function(item){
            var ds = (item.dataset.search || '').toLowerCase();
            var dg = item.dataset.group || '';
            var ok = (!q || ds.indexOf(q) !== -1) && (!g || dg === g);
            item.style.display = ok ? '' : 'none';
            if(ok) visible++;
        });

        if(visible === 0){
            emptyBlock.style.display = '';
            list.style.display = 'none';
        } else {
            emptyBlock.style.display = 'none';
            list.style.display = '';
        }
        if(totalBadge) totalBadge.textContent = visible;
    }

    if(search) search.addEventListener('input', applyFilter);
    if(groupSel) groupSel.addEventListener('change', applyFilter);

    var resetBtn = document.getElementById('jReset');
    if(resetBtn){
        resetBtn.addEventListener('click', function(){
            search.value = '';
            groupSel.value = '';
            applyFilter();
        });
    }

    /* ============================================================
       FAB — открыть модалку «Создать журнал»
       ============================================================ */
    var fab = document.getElementById('jFab');
    if(fab) fab.addEventListener('click', function(){
        App.openModal('createJournalModal');
    });

    /* ============================================================
       МОДАЛКА «СОЗДАТЬ ЖУРНАЛ» — валидация и пересчёт часов
       ============================================================ */
    var cjForm = document.getElementById('createJournalForm');
    var cjGroup = document.getElementById('cj_group');
    var cjSubject = document.getElementById('cj_subject');
    var cjSubmit = document.getElementById('cjSubmit');

    function cjUpdateTotal(sem){
        var total = 0;
        ['lecture','practice','independent','exam'].forEach(function(k){
            var inp = document.getElementById('cj_h' + sem + '_' + k);
            if(inp) total += parseInt(inp.value || 0, 10) || 0;
        });
        var badge = document.getElementById('cj_total_' + sem);
        if(badge) badge.textContent = total + ' ч';
    }

    function cjValidate(){
        if(!cjForm) return;
        var groupOk = !!cjGroup.value;
        var subjOk = !!cjSubject.value;
        var hasHours = false;
        [1,2,3].forEach(function(sem){
            var cb = document.getElementById('cj_sem_' + sem);
            if(!cb || !cb.checked) return;
            ['lecture','practice','independent','exam'].forEach(function(k){
                var inp = document.getElementById('cj_h' + sem + '_' + k);
                if(inp && (parseInt(inp.value || 0, 10) || 0) > 0) hasHours = true;
            });
        });
        cjSubmit.disabled = !(groupOk && subjOk && hasHours);
    }

    if(cjForm){
        [1,2,3].forEach(function(sem){
            var cb = document.getElementById('cj_sem_' + sem);
            if(!cb) return;
            cb.addEventListener('change', function(){
                var block = document.getElementById('cj_block_' + sem);
                if(block) block.style.display = cb.checked ? '' : 'none';
                if(!cb.checked){
                    ['lecture','practice','independent','exam'].forEach(function(k){
                        var inp = document.getElementById('cj_h' + sem + '_' + k);
                        if(inp) inp.value = 0;
                    });
                    cjUpdateTotal(sem);
                }
                cjValidate();
            });
        });

        document.querySelectorAll('#createJournalForm .semester-hour').forEach(function(inp){
            inp.addEventListener('input', function(){
                cjUpdateTotal(inp.dataset.sem);
                cjValidate();
            });
        });

        cjGroup.addEventListener('change', cjValidate);
        cjSubject.addEventListener('change', cjValidate);
    }

    /* ============================================================
       РЕДАКТИРОВАНИЕ ЧАСОВ
       ============================================================ */
    var ehGsid = document.getElementById('eh_gsid');
    var ehTitle = document.getElementById('eh_title');
    var ehSemesters = document.getElementById('eh_semesters');

    document.querySelectorAll('.edit-hours-btn').forEach(function(btn){
        btn.addEventListener('click', function(){
            var gsid = this.dataset.gsid;
            var group = this.dataset.group;
            var subject = this.dataset.subject;

            ehGsid.value = gsid;
            ehTitle.textContent = group + ' — ' + subject;
            ehSemesters.innerHTML = '<div class="skeleton skeleton--block"></div>';

            App.openModal('editHoursModal');

            fetch('/group-subjects/get-hours/' + gsid)
                .then(function(r){ return r.json(); })
                .then(function(data){
                    if(!data.semesters || !data.semesters.length){
                        ehSemesters.innerHTML = '<div class="alert alert-info">Нет настроенных семестров</div>';
                        return;
                    }

                    var html = '';
                    data.semesters.forEach(function(sem){
                        var h = data.hours[sem] || {
                            lecture_hours: 0, practice_hours: 0,
                            independent_hours: 0, exam_hours: 0
                        };
                        html += '<div class="semester-block">';
                        html += '<div class="semester-block__head"><span>Семестр ' + sem + '</span></div>';
                        html += '<div class="semester-block__body"><div class="hours-grid">';
                        html += '<div><label>Лекции</label><input type="number" min="0" class="form-control" name="hours_' + sem + '_lecture" value="' + h.lecture_hours + '"></div>';
                        html += '<div><label>Практические</label><input type="number" min="0" class="form-control" name="hours_' + sem + '_practice" value="' + h.practice_hours + '"></div>';
                        html += '<div><label>Самостоятельные</label><input type="number" min="0" class="form-control" name="hours_' + sem + '_independent" value="' + h.independent_hours + '"></div>';
                        html += '<div><label>Экзамен</label><input type="number" min="0" class="form-control" name="hours_' + sem + '_exam" value="' + h.exam_hours + '"></div>';
                        html += '</div></div></div>';
                    });
                    ehSemesters.innerHTML = html;
                })
                .catch(function(){
                    ehSemesters.innerHTML = '<div class="alert alert-danger">Ошибка загрузки часов</div>';
                });
        });
    });

    /* ============================================================
       КОПИРОВАНИЕ ЖУРНАЛА
       ============================================================ */
    var cjForm2 = document.getElementById('copyJournalForm');
    var cjSrcTitle = document.getElementById('cj_src_title');
    var cjSrcSubtitle = document.getElementById('cj_src_subtitle');
    var cjGroupsList = document.getElementById('cj_groups_list');
    var cjWarning = document.getElementById('cj_warning');
    var cjWarningText = document.getElementById('cj_warning_text');
    var cjCopyCount = document.getElementById('cj_copy_count');
    var cjCopySubmit = document.getElementById('cj_copy_submit');

    var ALL_PAIRS = [];
    var ALL_GROUPS = [];

    try {
        var pairsEl = document.getElementById('gsAllPairs');
        if(pairsEl) ALL_PAIRS = JSON.parse(pairsEl.textContent) || [];
    } catch(e){}

    try {
        var groupsEl = document.getElementById('gsAllGroups');
        if(groupsEl) ALL_GROUPS = JSON.parse(groupsEl.textContent) || [];
    } catch(e){}

    function buildGroupsList(sourceGsid, sourceSubjectId, sourceGroupName){
        cjGroupsList.innerHTML = '';

        if(!ALL_GROUPS.length){
            cjGroupsList.innerHTML = '<div class="text-muted small">Нет групп</div>';
            updateCount();
            return;
        }

        var busyBySubject = {};
        ALL_PAIRS.forEach(function(p){
            if(p.subject_id === sourceSubjectId) busyBySubject[p.group_id] = true;
        });

        var sourceGroupId = null;
        ALL_PAIRS.forEach(function(p){
            if(p.subject_id === sourceSubjectId && p.group_name === sourceGroupName){
                sourceGroupId = p.group_id;
            }
        });

        ALL_GROUPS.forEach(function(g){
            var isSource = (g.id === sourceGroupId);
            var isBusy = !!busyBySubject[g.id];
            var disabled = isSource || isBusy;

            var reason = '';
            if(isSource) reason = 'Это исходная группа';
            else if(isBusy) reason = 'Журнал по этому предмету уже есть';

            var item = document.createElement('div');
            item.className = 'copy-group-item ' + (disabled ? 'disabled' : '');

            var label = document.createElement('label');
            label.className = 'd-flex align-items-start gap-2 mb-0';
            label.style.cursor = disabled ? 'not-allowed' : 'pointer';

            var cb = document.createElement('input');
            cb.type = 'checkbox';
            cb.className = 'form-check-input copy-group-check';
            cb.value = g.id;
            if(disabled) cb.disabled = true;

            var info = document.createElement('div');
            info.className = 'flex-grow-1 min-width-0';

            var nameDiv = document.createElement('div');
            nameDiv.className = 'fw-semibold small';
            nameDiv.textContent = g.name;
            info.appendChild(nameDiv);

            if(reason){
                var reasonDiv = document.createElement('div');
                reasonDiv.className = 'small';
                reasonDiv.style.color = 'var(--danger)';
                reasonDiv.textContent = reason;
                info.appendChild(reasonDiv);
            }

            label.appendChild(cb);
            label.appendChild(info);
            item.appendChild(label);
            cjGroupsList.appendChild(item);
        });

        cjGroupsList.querySelectorAll('.copy-group-check').forEach(function(cb){
            cb.addEventListener('change', updateCount);
        });

        updateCount();
    }

    function updateCount(){
        var n = cjGroupsList.querySelectorAll('.copy-group-check:checked').length;
        cjCopyCount.textContent = 'Выбрано: ' + n;
        cjCopySubmit.disabled = (n === 0);

        var disabled = cjGroupsList.querySelectorAll('.copy-group-check:disabled').length;
        if(disabled > 0){
            cjWarningText.textContent = disabled + ' групп(ы) недоступны — там уже есть журнал по этому предмету.';
            cjWarning.style.display = '';
        } else {
            cjWarning.style.display = 'none';
        }
    }

    document.querySelectorAll('.copy-journal-btn').forEach(function(btn){
        btn.addEventListener('click', function(){
            var gsid = this.dataset.gsid;
            var group = this.dataset.group;
            var subject = this.dataset.subject;
            var subjectId = parseInt(this.dataset.subjectId, 10);

            cjSrcTitle.textContent = group + ' — ' + subject;
            cjSrcSubtitle.textContent = 'Исходный журнал #' + gsid;
            cjForm2.action = '/group-subjects/' + gsid + '/copy-to-groups';

            document.getElementById('cj_teacher').value = '';
            document.getElementById('cj_copy_hours').checked = true;
            document.getElementById('cj_copy_plan').checked = true;

            buildGroupsList(gsid, subjectId, group);

            App.openModal('copyJournalModal');
        });
    });

    var toggleAll = document.getElementById('cj_copy_toggle_all');
    if(toggleAll){
        toggleAll.addEventListener('click', function(){
            cjGroupsList.querySelectorAll('.copy-group-check:not(:disabled)').forEach(function(cb){
                cb.checked = true;
            });
            updateCount();
        });
    }

    var toggleNone = document.getElementById('cj_copy_toggle_none');
    if(toggleNone){
        toggleNone.addEventListener('click', function(){
            cjGroupsList.querySelectorAll('.copy-group-check').forEach(function(cb){
                cb.checked = false;
            });
            updateCount();
        });
    }

    /* ============================================================
       FAB на десктопе скрываем
       ============================================================ */
    if(fab && window.matchMedia('(min-width: 768px)').matches){
        fab.style.display = 'none';
    }

})();