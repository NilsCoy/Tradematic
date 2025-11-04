// Функция для получения CSRF токена из cookies
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

async function open_auth() {
    // Сначала проверяем авторизацию
    try {
        const response = await fetch('/api/check_auth/', {  // Этот endpoint нужно создать в Django
            method: 'GET',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken'),
            }
        });

        const data = await response.json();

        if (data.authenticated) {
            // Если пользователь авторизован, перенаправляем на другую страницу
            window.location.replace('/panel/');  // Или любой другой URL
            return;
        }

        // Если не авторизован, показываем форму входа
        close();
        document.querySelector('.login-form').style.display = 'flex';
        await delay(100);
        document.addEventListener('click', closeOnClickOutsideLogin);

    } catch (error) {
        console.error('Ошибка при проверке авторизации:', error);
        // В случае ошибки всё равно показываем форму входа
        close();
        document.querySelector('.login-form').style.display = 'flex';
        await delay(100);
        document.addEventListener('click', closeOnClickOutsideLogin);
    }
}

function close_auth() {
    document.querySelector('.login-form').style.display = 'none';
    document.removeEventListener('click', closeOnClickOutsideLogin);
}

async function open_reg() {
    close();
    document.querySelector('.register-form').style.display = 'flex';
    await delay(100);
    document.addEventListener('click', closeOnClickOutsideRegister);
}

function close_reg() {
    document.querySelector('.register-form').style.display = 'none';
    document.removeEventListener('click', closeOnClickOutsideRegister);
}

async function open_reset() {
    close();
    document.querySelector('.reset-form').style.display = 'flex';
    await delay(100);
    document.addEventListener('click', closeOnClickOutsideReset);
}

function close_reset() {
    document.querySelector('.reset-form').style.display = 'none';
    document.removeEventListener('click', closeOnClickOutsideReset);
}

function close() {
    close_auth();
    close_reg();
    close_reset();
}

function closeOnClickOutsideLogin(event) {
    const window = document.querySelector('.login-form');

    if (window.style.display != 'none') {
        if (event.target === window || !window.contains(event.target)) {
            close();
            document.removeEventListener('click', closeOnClickOutsideLogin);
        }
    }
}

function closeOnClickOutsideRegister(event) {
    const window = document.querySelector('.register-form');

    if (window.style.display != 'none') {
        if (event.target === window || !window.contains(event.target)) {
            close();
            document.removeEventListener('click', closeOnClickOutsideRegister);
        }
    }
}

function closeOnClickOutsideReset(event) {
    const window = document.querySelector('.reset-form');

    if (window.style.display != 'none') {
        if (event.target === window || !window.contains(event.target)) {
            close();
            document.removeEventListener('click', closeOnClickOutsideReset);
        }
    }
}









