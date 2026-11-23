(function () {
    const root = document.querySelector("[data-chat], [data-admin-chat]");
    if (!root || root.hasAttribute("data-no-customer")) return;
    const messagesBox = root.querySelector("[data-chat-messages]");
    const form = root.querySelector("[data-chat-form]");
    const errorBox = root.querySelector("[data-chat-error]");
    const csrf = root.dataset.csrfToken;
    const isAdmin = root.hasAttribute("data-admin-chat");
    const url = root.dataset.chatUrl;

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
            article.className = "chat-message " + ((isAdmin ? message.sender_type === "STAFF" : message.sender_type === "CUSTOMER") ? "chat-message-me" : "");
            const meta = document.createElement("small");
            meta.textContent = `${message.sender_name} · ${new Date(message.created_at).toLocaleString("vi-VN")}`;
            const body = document.createElement("p");
            body.textContent = message.text;
            article.append(meta, body);
            messagesBox.append(article);
        });
        messagesBox.scrollTop = messagesBox.scrollHeight;
    }

    async function load() {
        try {
            const response = await fetch(url, { headers: { Accept: "application/json" } });
            if (!response.ok) throw new Error("Không thể tải tin nhắn.");
            render((await response.json()).messages || []);
        } catch (error) { errorBox.textContent = error.message; }
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const textarea = form.elements.message;
        const message = textarea.value.trim();
        if (!message) return;
        errorBox.textContent = "";
        const sendUrl = isAdmin ? url : url;
        try {
            const response = await fetch(sendUrl, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify({ message }) });
            const payload = await response.json();
            if (!response.ok) throw new Error(payload.error?.message || "Không thể gửi tin nhắn.");
            textarea.value = "";
            render(payload.messages || []);
        } catch (error) { errorBox.textContent = error.message; }
    });

    load();
    window.setInterval(load, 5000);
})();
