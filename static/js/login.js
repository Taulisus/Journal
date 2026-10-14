/* ============================================================
   LOGIN — показать/скрыть пароль
   ============================================================ */
(function(){
    'use strict';

    var btn = document.getElementById('togglePassword');
    var input = document.getElementById('password');

    if(!btn || !input) return;

    btn.addEventListener('click', function(){
        var isPassword = input.type === 'password';
        input.type = isPassword ? 'text' : 'password';

        var icon = btn.querySelector('i');
        if(icon){
            icon.className = isPassword ? 'bi bi-eye-slash' : 'bi bi-eye';
        }
        btn.setAttribute('aria-label',
            isPassword ? 'Скрыть пароль' : 'Показать пароль');
    });

})();