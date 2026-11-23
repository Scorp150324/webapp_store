(function () {
    const root = document.querySelector("[data-chat], [data-admin-chat]");
    if (!root) return;
    const search = root.querySelector("[data-chat-search]");
    if (search) {
        search.addEventListener("input", () => {
            const query = search.value.trim().toLowerCase();
            root.querySelectorAll("[data-customer-name]").forEach((customer) => {
                customer.hidden = query && !customer.dataset.customerName.includes(query);
            });
        });
    }
    if (root.hasAttribute("data-no-customer")) return;
    const messagesBox = root.querySelector("[data-chat-messages]");
    const form = root.querySelector("[data-chat-form]");
    const errorBox = root.querySelector("[data-chat-error]");
    const csrf = root.dataset.csrfToken;
    const isAdmin = root.hasAttribute("data-admin-chat");
    const url = root.dataset.chatUrl;
    const POLL_INTERVAL_MS = 2000;
    const REQUEST_TIMEOUT_MS = 12000;
    let pollTimer = null;
    let pollFailures = 0;
    let pollInFlight = false;

    function render(messages) {
        messagesBox.replaceChildren();
        if (!messages.length) {
            const empty = document.createElement("p");
            empty.className = "chat-empty";
            empty.textContent = "Chưa có tin nhắn.";
            messagesBox.append(empty);
            return;
        }
        messages.forEach((message) => {
            const article = document.createElement("article");
            const senderClass = message.sender_type === "STAFF"
                ? (isAdmin ? "chat-message-staff" : "chat-message-other")
                : message.sender_type === "CUSTOMER"
                    ? (isAdmin ? "chat-message-customer" : "chat-message-me")
                    : message.sender_type === "BOT" ? "chat-message-bot" : "";
            article.className = "chat-message " + senderClass;
            const meta = document.createElement("small");
            meta.textContent = `${message.sender_name} · ${new Date(message.created_at).toLocaleString("vi-VN")}`;
            const body = document.createElement("p");
            body.textContent = message.text;
            article.append(meta, body);
            messagesBox.append(article);
        });
        messagesBox.scrollTop = messagesBox.scrollHeight;
    }

    function renderCustomerStatus(isOnline) {
        if (!isAdmin || typeof isOnline !== "boolean") return;
        const selectedId = root.dataset.selectedCustomerId;
        root.querySelectorAll(`[data-customer-id="${selectedId}"] [data-customer-status], [data-selected-customer-status] [data-customer-status]`).forEach((label) => {
            label.textContent = isOnline ? "Online" : "Offline";
        });
        root.querySelectorAll(`[data-customer-id="${selectedId}"] [data-customer-status-dot], [data-selected-customer-status] [data-customer-status-dot]`).forEach((dot) => {
            dot.classList.toggle("is-offline", !isOnline);
        });
    }

    async function requestJson(options = {}) {
        const controller = new AbortController();
        const timeout = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
        try {
            const response = await fetch(url, {
                ...options,
                cache: "no-store",
                credentials: "same-origin",
                signal: controller.signal,
                headers: { Accept: "application/json", ...options.headers },
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.error?.message || payload.message || `Máy chủ phản hồi ${response.status}.`);
            }
            return payload;
        } finally {
            window.clearTimeout(timeout);
        }
    }

    async function load() {
        if (pollInFlight) return;
        if (document.hidden) {
            pollTimer = window.setTimeout(load, POLL_INTERVAL_MS);
            return;
        }
        pollInFlight = true;
        let nextDelay = POLL_INTERVAL_MS;
        try {
            const payload = await requestJson();
            render(payload.messages || []);
            renderCustomerStatus(payload.customer_online);
            errorBox.textContent = "";
            pollFailures = 0;
        } catch (error) {
            errorBox.textContent = error.name === "AbortError"
                ? "Kết nối đang chậm. Đang tự kết nối lại…"
                : `${error.message} Đang thử kết nối lại…`;
            pollFailures += 1;
            nextDelay = Math.min(15000, POLL_INTERVAL_MS * (2 ** Math.min(pollFailures, 3)));
        } finally {
            pollInFlight = false;
            pollTimer = window.setTimeout(load, nextDelay);
        }
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const textarea = form.elements.message;
        const message = textarea.value.trim();
        if (!message) return;
        errorBox.textContent = "";
        const submitButton = form.querySelector("button[type='submit'], button:not([type])");
        if (submitButton) submitButton.disabled = true;
        try {
            const payload = await requestJson({
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
                body: JSON.stringify({ message }),
            });
            textarea.value = "";
            render(payload.messages || []);
        } catch (error) {
            errorBox.textContent = error.name === "AbortError"
                ? "Gửi tin quá thời hạn. Hãy kiểm tra kết nối rồi thử lại."
                : error.message;
        } finally {
            if (submitButton) submitButton.disabled = false;
        }
    });

    load();
    document.addEventListener("visibilitychange", () => {
        if (!document.hidden && !pollInFlight) {
            window.clearTimeout(pollTimer);
            load();
        }
    });
})();
