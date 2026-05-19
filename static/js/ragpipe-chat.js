function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        for (const cookie of document.cookie.split(';')) {
            const trimmed = cookie.trim();
            if (trimmed.substring(0, name.length + 1) === `${name}=`) {
                cookieValue = decodeURIComponent(trimmed.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

function appendRagMessage(container, text, sender) {
    const message = document.createElement('div');
    message.className = `rag-chat-message ${sender}`;
    message.textContent = text;
    container.appendChild(message);
    message.scrollIntoView({ block: 'end' });
    return message;
}

document.addEventListener('DOMContentLoaded', () => {
    const root = document.body;
    const toggle = document.querySelector('.rag-chat-toggle');
    const box = document.querySelector('.rag-chat-box');
    const closeButton = document.querySelector('.rag-chat-close');
    const form = document.querySelector('.rag-chat-form');
    const input = document.querySelector('.rag-chat-input');
    const messages = document.querySelector('.rag-chat-messages');

    if (!toggle || !box || !form || !input || !messages) {
        return;
    }

    const endpoint = form.dataset.endpoint || '/chat/';

    if (root.dataset.chatOpen === 'true') {
        box.hidden = false;
        input.focus();
    }

    toggle.addEventListener('click', () => {
        box.hidden = !box.hidden;
        if (!box.hidden) {
            input.focus();
        }
    });

    closeButton?.addEventListener('click', () => {
        box.hidden = true;
    });

    form.addEventListener('submit', async (event) => {
        event.preventDefault();
        const text = input.value.trim();
        if (!text) {
            return;
        }

        appendRagMessage(messages, text, 'user');
        input.value = '';
        const pending = appendRagMessage(messages, 'Думаю...', 'bot');

        try {
            const response = await fetch(endpoint, {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCookie('csrftoken'),
                },
                body: JSON.stringify({ message: text }),
            });
            const data = await response.json();
            pending.remove();
            const errorText = data.detail ? `${data.error}: ${data.detail}` : data.error || 'Ошибка запроса';
            appendRagMessage(messages, response.ok ? data.response : errorText, 'bot');
        } catch (error) {
            pending.remove();
            appendRagMessage(messages, `Ошибка соединения: ${error}`, 'bot');
        }
    });
});
