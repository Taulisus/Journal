/* ============================================================
   STUDENTS — поиск, фильтр, модалки, массовый перевод
   ============================================================ */
(function(){
    'use strict';

    var dataEl = document.getElementById('studentsData');
    var permsEl = document.getElementById('studentsPerms');
    if(!dataEl) return;

    var STUDENTS = JSON.parse(dataEl.textContent);
    var PERMS = permsEl ? JSON.parse(permsEl.textContent) : {};

    var searchInput = document.getElementById('stSearch');
    var groupFilter = document.getElementById('stGroupFilter');
    var tbody = document.getElementById('stBody');
    var mobileList = document.getElementById('stMobileList');
    var emptyBlock = document.getElementById('stEmpty');
    var countEl = document.getElementById('stCount');
    var totalLabel = document.getElementById('stTotalLabel');

    var selectAll = document.getElementById('stSelectAll');
    var btnMass = document.getElementById('btnMassTransfer');
    var massCountBadge = document.getElementById('massCountBadge');
    var massStudentIds = document.getElementById('massStudentIds');
    var massSelectedCount = document.getElementById('massSelectedCount');
    var massNewGroup = document.getElementById('mass_new_group_id');
    var massPreviewBox = document.getElementById('massPreviewBox');
    var massPreviewContent = document.getElementById('massPreviewContent');
    var massTransferDate = document.getElementById('mass_transfer_date');
    var massTransferForm = document.getElementById('massTransferForm');

    /* ============================================================
       РЕНДЕР
       ============================================================ */
    function filtered(){
        var q = (searchInput.value || '').toLowerCase().trim();
        var gid = groupFilter.value;
        return STUDENTS.filter(function(s){
            if(gid && String(s.group_id) !== String(gid)) return false;
            if(q && s.name.toLowerCase().indexOf(q) === -1) return false;
            return true;
        });
    }

    function render(){
        var list = filtered();

        // Desktop
        tbody.innerHTML = list.map(function(s){
            var checkbox = '';
            if(PERMS.manage_users){
                checkbox = '<td class="text-center">' +
                           '<input type="checkbox" class="form-check-input st-checkbox" value="' + s.id + '">' +
                           '</td>';
            }

            var actions = '';
            if(PERMS.add_students){
                actions += '<button type="button" class="btn btn-sm btn-outline-primary edit-student-btn me-1" ' +
                           'data-sid="' + s.id + '" ' +
                           'data-gid="' + s.group_id + '" ' +
                           'data-name="' + escapeHtml(s.name) + '" ' +
                           'data-tooltip="Редактировать">' +
                           '<i class="bi bi-pencil"></i></button>';
            }
            if(PERMS.delete_student){
                actions += '<a href="/students/delete/' + s.id + '" ' +
                           'class="btn btn-sm btn-outline-danger" ' +
                           'data-tooltip="Удалить" ' +
                           'onclick="return confirm(\'Удалить студента «' + escapeHtml(s.name) + '»?\');">' +
                           '<i class="bi bi-trash"></i></a>';
            }

            return '<tr>' +
                   checkbox +
                   '<td><a href="/student/' + s.id + '" style="color:var(--text);font-weight:500;text-decoration:none;">' +
                   escapeHtml(s.name) + '</a></td>' +
                   '<td><span class="badge bg-light">' + escapeHtml(s.group_name || '—') + '</span></td>' +
                   '<td class="text-end">' + actions + '</td>' +
                   '</tr>';
        }).join('');

        // Mobile
        mobileList.innerHTML = list.map(function(s){
            var actions = '';
            if(PERMS.add_students){
                actions += '<button type="button" class="btn btn-sm btn-outline-primary edit-student-btn flex-grow-1" ' +
                           'data-sid="' + s.id + '" ' +
                           'data-gid="' + s.group_id + '" ' +
                           'data-name="' + escapeHtml(s.name) + '">' +
                           '<i class="bi bi-pencil"></i> Изменить</button>';
            }
            if(PERMS.delete_student){
                actions += '<a href="/students/delete/' + s.id + '" ' +
                           'class="btn btn-sm btn-outline-danger flex-grow-1" ' +
                           'onclick="return confirm(\'Удалить студента «' + escapeHtml(s.name) + '»?\');">' +
                           '<i class="bi bi-trash"></i> Удалить</a>';
            }

            return '<div class="student-row-mobile">' +
                   '<div class="d-flex justify-content-between align-items-start gap-2 mb-2">' +
                   '<a href="/student/' + s.id + '" style="color:var(--text);font-weight:600;text-decoration:none;">' +
                   escapeHtml(s.name) + '</a>' +
                   '<span class="badge bg-light">' + escapeHtml(s.group_name || '—') + '</span>' +
                   '</div>' +
                   (actions ? '<div class="d-flex gap-2">' + actions + '</div>' : '') +
                   '</div>';
        }).join('');

        // Пустое состояние
        if(list.length === 0){
            emptyBlock.style.display = '';
            tbody.innerHTML = '';
            mobileList.innerHTML = '';
        } else {
            emptyBlock.style.display = 'none';
        }

        countEl.textContent = 'Найдено: ' + list.length + ' из ' + STUDENTS.length;
        if(totalLabel) totalLabel.textContent = 'всего: ' + STUDENTS.length;

        bindEditButtons();
        bindCheckboxes();
    }

    /* ============================================================
       ПОИСК / ФИЛЬТР
       ============================================================ */
    searchInput.addEventListener('input', render);
    groupFilter.addEventListener('change', render);

    /* ============================================================
       КНОПКА «РЕДАКТИРОВАТЬ»
       ============================================================ */
    function bindEditButtons(){
        document.querySelectorAll('.edit-student-btn').forEach(function(btn){
            btn.addEventListener('click', function(){
                var sid = this.dataset.sid;
                var gid = this.dataset.gid;
                var name = this.dataset.name;

                document.getElementById('edit_full_name').value = name;
                document.getElementById('edit_group_id').value = gid;
                document.getElementById('editStudentForm').action = '/students/edit/' + sid;

                App.openModal('editStudentModal');
            });
        });
    }

    /* ============================================================
       МАССОВЫЙ ПЕРЕВОД
       ============================================================ */
    function selectedIds(){
        var arr = [];
        document.querySelectorAll('.st-checkbox:checked').forEach(function(cb){
            arr.push(parseInt(cb.value, 10));
        });
        return arr;
    }

    function updateMassUI(){
        var ids = selectedIds();
        var n = ids.length;

        massStudentIds.innerHTML = '';
        ids.forEach(function(id){
            var inp = document.createElement('input');
            inp.type = 'hidden';
            inp.name = 'student_ids';
            inp.value = id;
            massStudentIds.appendChild(inp);
        });

        if(massSelectedCount) massSelectedCount.textContent = n;

        if(btnMass){
            btnMass.disabled = (n === 0);
        }
        if(massCountBadge){
            if(n > 0){
                massCountBadge.textContent = n;
                massCountBadge.style.display = '';
            } else {
                massCountBadge.style.display = 'none';
            }
        }

        if(selectAll){
            var all = document.querySelectorAll('.st-checkbox').length;
            selectAll.checked = (n > 0 && n === all);
            selectAll.indeterminate = (n > 0 && n < all);
        }
    }

    function bindCheckboxes(){
        document.querySelectorAll('.st-checkbox').forEach(function(cb){
            cb.addEventListener('change', updateMassUI);
        });
    }

    if(selectAll){
        selectAll.addEventListener('change', function(){
            document.querySelectorAll('.st-checkbox').forEach(function(cb){
                cb.checked = selectAll.checked;
            });
            updateMassUI();
        });
    }

    if(btnMass){
        btnMass.addEventListener('click', function(){
            if(selectedIds().length === 0){
                App.toast('Выберите хотя бы одного студента', 'warning');
                return;
            }
            massPreviewBox.style.display = 'none';
            App.openModal('massTransferModal');
        });
    }

    if(massTransferDate && !massTransferDate.value){
        var today = new Date();
        var y = today.getFullYear();
        var m = String(today.getMonth() + 1).padStart(2, '0');
        var d = String(today.getDate()).padStart(2, '0');
        massTransferDate.value = y + '-' + m + '-' + d;
    }

    /* --- Предпросмотр --- */
    function updateMassPreview(){
        var ids = selectedIds();
        var gid = massNewGroup.value;
        if(!ids.length || !gid){
            massPreviewBox.style.display = 'none';
            return;
        }

        var url = "{{ url_for('students.transfer_info', new_group_id=0) }}".replace('/0', '/' + gid) + '?ids=' + ids.join(',');
        // ↑ url_for не работает в статичном JS — используем относительный путь
        url = '/students/transfer-info/' + gid + '?ids=' + ids.join(',');

        fetch(url)
            .then(function(r){ return r.json(); })
            .then(function(resp){
                if(!resp.success){
                    massPreviewBox.style.display = 'none';
                    return;
                }
                var d = resp.data;
                var html = '';
                html += 'Всего выбрано: <strong>' + d.total + '</strong><br>';
                html += 'Будет переведено: <strong class="text-success">' + d.ok + '</strong><br>';
                if(d.same_group > 0){
                    html += 'Уже в этой группе: <strong class="text-muted">' + d.same_group + '</strong><br>';
                }
                if(d.duplicates > 0){
                    html += 'Однофамильцев в группе: <strong class="text-warning">' + d.duplicates + '</strong>';
                }
                massPreviewContent.innerHTML = html;
                massPreviewBox.style.display = '';
            })
            .catch(function(){
                massPreviewBox.style.display = 'none';
            });
    }

    if(massNewGroup){
        massNewGroup.addEventListener('change', updateMassPreview);
    }

    /* ============================================================
       ESCAPE HTML
       ============================================================ */
    function escapeHtml(s){
        return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){
            return ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' })[c];
        });
    }

    /* ============================================================
       INIT
       ============================================================ */
    render();
    updateMassUI();
})();