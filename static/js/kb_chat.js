let currentSessionId = null;
let assistantMode = "knowledge";
let documents = [];
let employee = null;
let documentRefreshTimer = null;
let indexStatusTimer = null;
let wasIndexing = false;
let selectedDocumentIds = new Set();
let activeSessionMenuId = null;
let activeModalCallback = null;

/* ------------------------------------------------------------
   Toast helper
   Shows small production-style notifications instead of alerts.
------------------------------------------------------------ */
function showToast(message, type = "success") {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");

    toast.className = "toast " + type;
    toast.innerText = message;

    container.appendChild(toast);

    setTimeout(() => toast.remove(), 4000);
}

/* ------------------------------------------------------------
   Auth UI helpers
------------------------------------------------------------ */
function setAuthTab(tab) {
    const isLogin = tab === "login";

    document.getElementById("loginForm").style.display = isLogin ? "block" : "none";
    document.getElementById("signupForm").style.display = isLogin ? "none" : "block";

    document.getElementById("loginTabBtn").classList.toggle("active", isLogin);
    document.getElementById("signupTabBtn").classList.toggle("active", !isLogin);
}

/* ------------------------------------------------------------
   Modal helper
   Replaces browser confirm/prompt with app-level modal.
------------------------------------------------------------ */
function openModal(options) {
    const backdrop = document.getElementById("modalBackdrop");
    const title = document.getElementById("modalTitle");
    const message = document.getElementById("modalMessage");
    const input = document.getElementById("modalInput");
    const confirmBtn = document.getElementById("modalConfirmBtn");

    title.innerText = options.title || "Confirm action";
    message.innerText = options.message || "";
    confirmBtn.innerText = options.confirmText || "Yes";

    if (options.input) {
        input.style.display = "block";
        input.value = options.defaultValue || "";
        input.placeholder = options.placeholder || "";
        setTimeout(() => input.focus(), 50);
    } else {
        input.style.display = "none";
        input.value = "";
    }

    activeModalCallback = options.onConfirm || null;

    confirmBtn.onclick = function () {
        const value = input.value.trim();

        if (options.input && !value) {
            showToast("Please enter a value.", "warning");
            return;
        }

        closeModal();

        if (activeModalCallback) {
            activeModalCallback(value);
        }
    };

    backdrop.style.display = "flex";
}

function closeModal() {
    document.getElementById("modalBackdrop").style.display = "none";
}

/* ------------------------------------------------------------
   Basic layout controls
------------------------------------------------------------ */
function toggleSidebar() {
    const sidebar = document.querySelector(".sidebar");

    if (!sidebar) return;

    sidebar.style.display = sidebar.style.display === "none" ? "flex" : "none";
}

function toggleSection(sectionId, arrowId) {
    const section = document.getElementById(sectionId);
    const arrow = document.getElementById(arrowId);

    if (!section || !arrow) return;

    if (section.style.display === "none") {
        section.style.display = "block";
        arrow.innerText = "▼";
    } else {
        section.style.display = "none";
        arrow.innerText = "▶";
    }
}

/* ------------------------------------------------------------
   Login and signup
------------------------------------------------------------ */
async function checkLogin() {
    try {
        const response = await fetch("/me");

        if (!response.ok) {
            showLogin();
            return;
        }

        const data = await response.json();

        employee = data.employee;

        await showApp();

    } catch {
        showLogin();
    }
}

function showLogin() {
    employee = null;
    currentSessionId = null;

    const chatBox = document.getElementById("chatBox");

    if (chatBox) {
        chatBox.innerHTML = "";
    }

    document.getElementById("loginPage").style.display = "flex";
    document.getElementById("appPage").style.display = "none";
}

async function showApp() {
    document.getElementById("loginPage").style.display = "none";
    document.getElementById("appPage").style.display = "flex";

    document.getElementById("profileName").innerText = employee.name || "Employee";
    document.getElementById("profileEmail").innerText = employee.email || "";

    await loadKnowledgeFolder();
    await loadDocuments();
    await loadSessions();

    startAutoRefresh();

    currentSessionId = null;
    newChat();
}

async function login() {
    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value;
    const status = document.getElementById("loginStatus");

    status.innerText = "";

    if (!email || !password) {
        status.innerText = "Please enter email and password.";
        return;
    }

    try {
        const response = await fetch("/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                email,
                password
            })
        });

        if (!response.ok) {
            const error = await response.json();
            status.innerText = error.detail || "Login failed.";
            return;
        }

        const data = await response.json();

        employee = data.employee;

        showToast("Login successful", "success");
        await showApp();

    } catch {
        status.innerText = "Login failed.";
    }
}

async function signup() {
    const name = document.getElementById("signupName").value.trim();
    const email = document.getElementById("signupEmail").value.trim();
    const department = document.getElementById("signupDepartment").value.trim();
    const password = document.getElementById("signupPassword").value;
    const status = document.getElementById("signupStatus");

    status.innerText = "";

    if (!name || !email || !password) {
        status.innerText = "Please fill name, email and password.";
        return;
    }

    try {
        const response = await fetch("/signup", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                name,
                email,
                department,
                password
            })
        });

        const data = await response.json();

        if (!response.ok) {
            status.innerText = data.detail || "Signup failed.";
            return;
        }

        showToast(data.message || "Account created successfully.", "success");
        setAuthTab("login");
        document.getElementById("loginEmail").value = email;

    } catch {
        status.innerText = "Signup failed.";
    }
}

async function logout() {
    try {
        await fetch("/logout", {
            method: "POST"
        });
    } catch {
        // Ignore logout network failure.
    }

    employee = null;
    currentSessionId = null;
    documents = [];
    selectedDocumentIds.clear();

    stopAutoRefresh();
    showLogin();
}

/* ------------------------------------------------------------
   Assistant mode
------------------------------------------------------------ */
function setAssistantMode(mode) {
    assistantMode = mode;

    document.getElementById("knowledgeModeBtn").classList.remove("active");
    document.getElementById("databaseModeBtn").classList.remove("active");

    const documentsSidebarSection = document.getElementById("documentsSidebarSection");
    const uploadSidebarSection = document.getElementById("uploadSidebarSection");
    const folderSidebarSection = document.getElementById("folderSidebarSection");
    const questionInput = document.getElementById("questionInput");

    if (mode === "knowledge") {
        document.getElementById("knowledgeModeBtn").classList.add("active");

        if (documentsSidebarSection) documentsSidebarSection.style.display = "block";
        if (uploadSidebarSection) uploadSidebarSection.style.display = "block";
        if (folderSidebarSection) folderSidebarSection.style.display = "block";

        questionInput.placeholder = "Ask anything from your knowledge base...";
        document.getElementById("systemStatus").innerText = "Knowledge Mode";

    } else {
        document.getElementById("databaseModeBtn").classList.add("active");

        if (documentsSidebarSection) documentsSidebarSection.style.display = "none";
        if (uploadSidebarSection) uploadSidebarSection.style.display = "none";
        if (folderSidebarSection) folderSidebarSection.style.display = "none";

        questionInput.placeholder = "Ask anything from database...";
        document.getElementById("systemStatus").innerText = "Database Mode";
    }

    currentSessionId = null;

    loadSessions();
    newChat();

    showToast(
        mode === "knowledge" ? "Knowledge mode selected" : "Database mode selected",
        "success"
    );
}

/* ------------------------------------------------------------
   Knowledge folder and indexing
------------------------------------------------------------ */
async function loadKnowledgeFolder() {
    try {
        const response = await fetch("/knowledge-folder");

        if (!response.ok) return;

        const data = await response.json();

        document.getElementById("folderInput").value = data.folder_path || "";
        document.getElementById("folderStatus").innerText =
            "Current folder: " + (data.folder_path || "Not set");

    } catch {
        // Silent because folder status is not critical for page load.
    }
}

async function setKnowledgeFolder() {
    const folderPath = document.getElementById("folderInput").value.trim();
    const status = document.getElementById("folderStatus");

    if (!folderPath) {
        status.innerText = "Please enter folder path.";
        return;
    }

    try {
        const response = await fetch("/set-knowledge-folder", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                folder_path: folderPath
            })
        });

        const data = await response.json();

        status.innerText = data.message;

        if (data.success) {
            showToast("Knowledge folder saved", "success");
            await loadDocuments();
        } else {
            showToast(data.message, "error");
        }

    } catch {
        status.innerText = "Failed to save folder.";
        showToast("Failed to save folder", "error");
    }
}

async function indexNow() {
    const status = document.getElementById("folderStatus");

    status.innerText = "Manual indexing started...";
    wasIndexing = true;

    document.getElementById("systemStatus").innerText = "Indexing...";

    try {
        const response = await fetch("/index-now", {
            method: "POST"
        });

        const data = await response.json();

        status.innerText = data.message;

        showToast("Indexing started", "success");
        startIndexStatusPolling();

    } catch {
        status.innerText = "Failed to start indexing.";
        showToast("Failed to start indexing", "error");
    }
}

async function checkIndexStatus() {
    try {
        const response = await fetch("/index-status");

        if (!response.ok) return;

        const data = await response.json();

        if (data.running) {
            wasIndexing = true;

            document.getElementById("systemStatus").innerText =
                `Indexing... Pending: ${data.pending}, Running: ${data.indexing}`;

            await loadDocuments();

        } else {
            document.getElementById("systemStatus").innerText =
                assistantMode === "knowledge" ? "Knowledge Mode" : "Database Mode";

            if (wasIndexing) {
                showToast("Indexing completed. Documents are ready.", "success");
                wasIndexing = false;
                await loadDocuments();
            }
        }

    } catch {
        // Ignore polling errors.
    }
}

function startIndexStatusPolling() {
    if (indexStatusTimer) {
        clearInterval(indexStatusTimer);
    }

    checkIndexStatus();
    indexStatusTimer = setInterval(checkIndexStatus, 3000);
}

function startAutoRefresh() {
    if (!documentRefreshTimer) {
        documentRefreshTimer = setInterval(loadDocuments, 10000);
    }

    startIndexStatusPolling();
}

function stopAutoRefresh() {
    if (documentRefreshTimer) {
        clearInterval(documentRefreshTimer);
        documentRefreshTimer = null;
    }

    if (indexStatusTimer) {
        clearInterval(indexStatusTimer);
        indexStatusTimer = null;
    }
}

/* ------------------------------------------------------------
   Documents
------------------------------------------------------------ */
async function loadDocuments() {
    try {
        const response = await fetch("/documents");

        if (!response.ok) return;

        const data = await response.json();

        documents = data.documents || [];

        document.getElementById("documentCount").innerText = documents.length;

        renderDocuments();

    } catch {
        // Ignore refresh failures.
    }
}

function renderDocuments() {
    const list = document.getElementById("documentsList");
    const searchInput = document.getElementById("docSearchInput");
    const selectAllInput = document.getElementById("selectAllDocs");

    if (!list) return;

    const search = searchInput ? searchInput.value.toLowerCase() : "";
    const selectAll = selectAllInput ? selectAllInput.checked : true;

    list.innerHTML = "";

    const filteredDocs = documents.filter((doc) =>
        doc.filename.toLowerCase().includes(search)
    );

    if (filteredDocs.length === 0) {
        list.innerHTML = "<div class='empty-state'>No documents found.</div>";
        return;
    }

    filteredDocs.forEach((doc) => {
        const ready = isReady(doc);
        const checked = selectedDocumentIds.has(doc.document_id) ? "checked" : "";
        const disabled = (!ready || selectAll) ? "disabled" : "";

        const div = document.createElement("div");
        div.className = "doc-item";

        div.innerHTML = `
            <div class="doc-row">
                <input type="checkbox"
                       class="doc-check"
                       value="${doc.document_id}"
                       ${checked}
                       ${disabled}
                       onchange="updateSelectedDocument(${doc.document_id}, this.checked)">
                <a class="doc-name"
                   href="/download-document/${doc.document_id}"
                   target="_blank"
                   title="Download document">
                   ${escapeHtml(doc.filename)}
                </a>
            </div>
        `;

        list.appendChild(div);
    });
}

function updateSelectedDocument(documentId, checked) {
    if (checked) {
        selectedDocumentIds.add(documentId);
    } else {
        selectedDocumentIds.delete(documentId);
    }
}

function toggleAllDocuments() {
    const selectAll = document.getElementById("selectAllDocs").checked;

    if (selectAll) {
        selectedDocumentIds.clear();
    }

    renderDocuments();
}

function getSelectedDocumentIds() {
    const selectAll = document.getElementById("selectAllDocs").checked;

    if (selectAll) {
        return [];
    }

    return Array.from(selectedDocumentIds);
}

function isReady(doc) {
    return (doc.indexing_status || "ready") === "ready";
}

function hasReadyDocuments() {
    return documents.some((doc) => isReady(doc));
}

/* ------------------------------------------------------------
   Uploads
------------------------------------------------------------ */
function openComposerFilePicker() {
    document.getElementById("composerFileInput").click();
}

async function uploadComposerFiles() {
    const input = document.getElementById("composerFileInput");

    if (!input.files || input.files.length === 0) return;

    await uploadSelectedFiles(input, "Files uploaded from chat bar.");
}

async function uploadFiles() {
    const input = document.getElementById("fileInput");

    if (!input.files || input.files.length === 0) {
        document.getElementById("uploadStatus").innerText = "Please select files first.";
        return;
    }

    await uploadSelectedFiles(input, "Upload completed.");
}

async function uploadSelectedFiles(input, successMessage) {
    const status = document.getElementById("uploadStatus");
    const formData = new FormData();

    for (const file of input.files) {
        formData.append("files", file);
    }

    if (status) {
        status.innerText = "Uploading...";
    }

    try {
        const response = await fetch("/upload", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (status) {
            status.innerText = buildUploadStatusMessage(data);
        }

        input.value = "";

        showToast(successMessage, "success");

        await loadDocuments();
        startIndexStatusPolling();

    } catch {
        if (status) {
            status.innerText = "Upload failed.";
        }

        showToast("Upload failed", "error");
    }
}

function buildUploadStatusMessage(data) {
    const messages = [];

    if (data.results && data.results.length > 0) {
        data.results.forEach((result) => {
            messages.push(`${result.filename}: ${result.message || result.status}`);
        });
    }

    return messages.length ? messages.join("\\n") : data.message;
}

/* ------------------------------------------------------------
   Production-style clear documents modal
------------------------------------------------------------ */
function openClearDocumentsModal() {
    openModal({
        title: "Clear all documents?",
        message: "This will remove uploaded files and indexed chunks. This action cannot be undone.",
        confirmText: "Yes, clear",
        onConfirm: clearAllDocuments
    });
}

async function clearAllDocuments() {
    try {
        const response = await fetch("/documents/clear", {
            method: "DELETE"
        });

        const data = await response.json();

        if (!response.ok) {
            showToast(data.detail || "Failed to clear documents.", "error");
            return;
        }

        documents = [];
        selectedDocumentIds.clear();

        document.getElementById("documentCount").innerText = "0";
        document.getElementById("documentsList").innerHTML =
            "<div class='empty-state'>No documents found.</div>";

        showToast(data.message, "success");

    } catch {
        showToast("Failed to clear documents.", "error");
    }
}

/* ------------------------------------------------------------
   Chat sending and validation
------------------------------------------------------------ */
function isSmallTalk(question) {
    const q = question
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9\\s]/g, "")
        .replace(/\\s+/g, " ");

    return [
        "hi",
        "hello",
        "hey",
        "hii",
        "hiii",
        "thanks",
        "thank you",
        "thankyou",
        "ok",
        "okay",
        "done",
        "bye"
    ].includes(q);
}

function validateBeforeSend(question) {
    if (assistantMode !== "knowledge") {
        return true;
    }

    if (isSmallTalk(question)) {
        return true;
    }

    const selectAll = document.getElementById("selectAllDocs").checked;
    const selectedIds = getSelectedDocumentIds();

    if (!hasReadyDocuments()) {
        addMessage("Assistant", "No ready documents are available. Please index documents first.", "assistant");
        return false;
    }

    if (!selectAll && selectedIds.length === 0) {
        addMessage("Assistant", "Please select at least one ready document or enable Search all ready documents.", "assistant");
        return false;
    }

    return true;
}

async function sendMessage() {
    const input = document.getElementById("questionInput");
    const sendBtn = document.getElementById("sendBtn");
    const question = input.value.trim();

    if (!question) return;

    if (!validateBeforeSend(question)) return;

    const selectedIds = getSelectedDocumentIds();

    addMessage("You", question, "user");

    input.value = "";
    resizeQuestionInput();

    sendBtn.disabled = true;

    addThinkingMessage();

    try {
        let response;

        if (assistantMode === "knowledge") {
            response = await fetch("/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    question,
                    session_id: currentSessionId,
                    document_ids: selectedIds
                })
            });
        } else {
            response = await fetch("/db-chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    question,
                    session_id: currentSessionId
                })
            });
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Request failed");
        }

        if (data.session_id) {
            currentSessionId = data.session_id;
        }

        removeThinkingMessage();
        addAssistantAnswer(data.answer, data.sources || [], data);

        await loadSessions();

    } catch {
        removeThinkingMessage();
        addMessage("Assistant", "Something went wrong while generating the answer.", "assistant");
        showToast("Answer generation failed", "error");

    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}

/* ------------------------------------------------------------
   Chat rendering
------------------------------------------------------------ */
function removeWelcome() {
    const welcome = document.getElementById("welcomeCard");

    if (welcome) {
        welcome.remove();
    }
}

function addMessage(role, text, type, isThinking = false) {
    removeWelcome();

    const chatBox = document.getElementById("chatBox");
    const wrap = document.createElement("div");

    wrap.className = "message-wrap";

    if (isThinking) {
        wrap.setAttribute("data-thinking", "true");
    }

    const label = document.createElement("div");
    label.className = "role-label";
    label.innerText = role;

    const msg = document.createElement("div");
    msg.className = "message " + (type === "user" ? "user-message" : "assistant-message");

    if (isThinking) {
        msg.classList.add("typing");
    }

    msg.innerText = text;

    wrap.appendChild(label);
    wrap.appendChild(msg);

    chatBox.appendChild(wrap);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function addThinkingMessage() {
    removeWelcome();

    const chatBox = document.getElementById("chatBox");
    const wrap = document.createElement("div");

    wrap.className = "message-wrap";
    wrap.setAttribute("data-thinking", "true");

    const label = document.createElement("div");
    label.className = "role-label";
    label.innerText = "Assistant";

    const msg = document.createElement("div");
    msg.className = "message assistant-message typing";
    msg.innerHTML = `
        <span class="typing-dots">
            <span></span><span></span><span></span>
        </span>
        Thinking...
    `;

    wrap.appendChild(label);
    wrap.appendChild(msg);
    chatBox.appendChild(wrap);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function addAssistantAnswer(answer, sources, data = {}) {
    removeWelcome();

    const chatBox = document.getElementById("chatBox");
    const wrap = document.createElement("div");

    wrap.className = "message-wrap";

    const label = document.createElement("div");
    label.className = "role-label";
    label.innerText = "Assistant";

    const msg = document.createElement("div");
    msg.className = "message assistant-message";

    const answerDiv = document.createElement("div");
    answerDiv.innerText = answer || "";
    msg.appendChild(answerDiv);

    if (assistantMode === "database" || data.columns || data.rows) {
        renderDatabaseResult(msg, data);
    }

    const copyBtn = document.createElement("button");
    copyBtn.className = "copy-btn";
    copyBtn.innerText = "Copy";

    copyBtn.onclick = () => {
        navigator.clipboard.writeText(answer || "");
        copyBtn.innerText = "Copied";
        setTimeout(() => {
            copyBtn.innerText = "Copy";
        }, 1200);
    };

    msg.appendChild(copyBtn);

    const feedback = document.createElement("span");
    feedback.className = "feedback-row";
    feedback.innerHTML = `
        <button onclick="submitFeedback('like')">👍</button>
        <button onclick="submitFeedback('dislike')">👎</button>
    `;
    msg.appendChild(feedback);

    if (sources.length > 0) {
        renderSources(msg, sources);
    }

    wrap.appendChild(label);
    wrap.appendChild(msg);

    chatBox.appendChild(wrap);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function renderSources(container, sources) {
    const sourcesBox = document.createElement("div");
    sourcesBox.className = "sources-box";

    const title = document.createElement("div");
    title.className = "sources-title";
    title.innerText = "Sources used";

    sourcesBox.appendChild(title);

    sources.forEach((source) => {
        const link = document.createElement("a");

        link.className = "source-link";
        link.href = source.download_url;
        link.target = "_blank";
        link.innerText = "📄 " + source.filename;

        sourcesBox.appendChild(link);
    });

    container.appendChild(sourcesBox);
}

function renderDatabaseResult(container, data = {}) {
    const payload = data.payload || data;
    const columns = payload.columns || [];
    const rows = payload.rows || [];

    if (payload.execution_time !== undefined) {
        const meta = document.createElement("div");
        meta.className = "db-result-meta";
        meta.innerText = `Execution time: ${payload.execution_time}s`;
        container.appendChild(meta);
    }

    if (columns.length === 0 || rows.length === 0) {
        return;
    }

    const tableWrapper = document.createElement("div");
    tableWrapper.className = "table-wrapper";

    const table = document.createElement("table");
    table.className = "result-table";

    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    columns.forEach((column) => {
        const th = document.createElement("th");
        th.innerText = column;
        headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");

    rows.forEach((row) => {
        const tr = document.createElement("tr");

        row.forEach((cell) => {
            const td = document.createElement("td");
            td.innerText = cell;
            tr.appendChild(td);
        });

        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    tableWrapper.appendChild(table);
    container.appendChild(tableWrapper);
}

function removeThinkingMessage() {
    const thinking = document.querySelector("[data-thinking='true']");

    if (thinking) {
        thinking.remove();
    }
}

function submitFeedback(type) {
    showToast(type === "like" ? "Feedback saved." : "Thanks, we will improve this.", "success");
}

/* ------------------------------------------------------------
   Session history with menu actions
------------------------------------------------------------ */
let sessions = [];

async function loadSessions() {
    try {
        const response = await fetch(`/sessions?mode=${assistantMode}`);

        if (!response.ok) return;

        const data = await response.json();

        sessions = data.sessions || [];

        renderSessions();

    } catch {
        // Ignore session load failure.
    }
}

function renderSessions() {
    const list = document.getElementById("sessionsList");
    const searchInput = document.getElementById("sessionSearchInput");
    const search = searchInput ? searchInput.value.toLowerCase() : "";

    list.innerHTML = "";

    const filteredSessions = sessions.filter((session) =>
        session.title.toLowerCase().includes(search)
    );

    if (filteredSessions.length === 0) {
        list.innerHTML = "<div class='empty-state'>No chat history found.</div>";
        return;
    }

    const pinnedSessions = filteredSessions.filter((session) => session.is_pinned);
    const recentSessions = filteredSessions.filter((session) => !session.is_pinned);

    if (pinnedSessions.length > 0) {
        list.appendChild(createSessionGroupTitle("Pinned"));
        pinnedSessions.forEach((session) => list.appendChild(createSessionItem(session)));
    }

    if (recentSessions.length > 0) {
        list.appendChild(createSessionGroupTitle("Recents"));
        recentSessions.forEach((session) => list.appendChild(createSessionItem(session)));
    }
}

function createSessionGroupTitle(title) {
    const div = document.createElement("div");
    div.className = "session-group-title";
    div.innerText = title;
    return div;
}

function createSessionItem(session) {
    const div = document.createElement("div");

    div.className = "session-item";

    div.innerHTML = `
        <span class="session-icon">
            ${session.is_pinned ? "📌" : "○"}
        </span>

        <span class="session-title">
            ${escapeHtml(session.title)}
        </span>

        <button class="session-menu-btn"
            onclick="openSessionMenu(event, ${session.session_id}, '${escapeForAttribute(session.title)}', ${session.is_pinned})">
            <i class="fa-solid fa-ellipsis"></i>
        </button>
    `;

    div.onclick = (event) => {
        if (
            event.target.closest(".session-menu-btn")
        ) {
            return;
        }

        loadSessionMessages(session.session_id);
    };

    return div;
}

function openSessionMenu(event, sessionId, title, isPinned) {
    event.stopPropagation();

    closeSessionMenu();

    activeSessionMenuId = sessionId;

    const menu = document.createElement("div");
    menu.className = "session-menu";
    menu.id = "sessionMenu";

    menu.innerHTML = `
        <button onclick="openShareSessionModal(${sessionId})">
            <i class="fa-solid fa-arrow-up-right-from-square"></i>
            Share
        </button>

        <button onclick="openRenameSessionModal(${sessionId}, '${escapeForAttribute(title)}')">
            <i class="fa-solid fa-pen"></i>
            Rename
        </button>

        <button onclick="pinSession(${sessionId}, ${!isPinned})">
            <i class="fa-solid fa-thumbtack"></i>
            ${isPinned ? "Unpin chat" : "Pin chat"}
        </button>

        <button onclick="archiveSession(${sessionId})">
            <i class="fa-solid fa-box-archive"></i>
            Archive
        </button>

        <button class="danger" onclick="openDeleteSessionModal(${sessionId})">
            <i class="fa-solid fa-trash"></i>
            Delete
        </button>
    `;

    document.body.appendChild(menu);

    const rect = event.target.getBoundingClientRect();

    menu.style.left = Math.min(rect.left, window.innerWidth - 260) + "px";
    menu.style.top = rect.bottom + 8 + "px";
    menu.style.display = "block";
}
let currentSessionId = null;
let assistantMode = "knowledge";
let documents = [];
let employee = null;
let documentRefreshTimer = null;
let indexStatusTimer = null;
let wasIndexing = false;
let selectedDocumentIds = new Set();
let activeSessionMenuId = null;
let activeModalCallback = null;

/* ------------------------------------------------------------
   Toast helper
   Shows small production-style notifications instead of alerts.
------------------------------------------------------------ */
function showToast(message, type = "success") {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");

    toast.className = "toast " + type;
    toast.innerText = message;

    container.appendChild(toast);

    setTimeout(() => toast.remove(), 4000);
}

/* ------------------------------------------------------------
   Auth UI helpers
------------------------------------------------------------ */
function setAuthTab(tab) {
    const isLogin = tab === "login";

    document.getElementById("loginForm").style.display = isLogin ? "block" : "none";
    document.getElementById("signupForm").style.display = isLogin ? "none" : "block";

    document.getElementById("loginTabBtn").classList.toggle("active", isLogin);
    document.getElementById("signupTabBtn").classList.toggle("active", !isLogin);
}

/* ------------------------------------------------------------
   Modal helper
   Replaces browser confirm/prompt with app-level modal.
------------------------------------------------------------ */
function openModal(options) {
    const backdrop = document.getElementById("modalBackdrop");
    const title = document.getElementById("modalTitle");
    const message = document.getElementById("modalMessage");
    const input = document.getElementById("modalInput");
    const confirmBtn = document.getElementById("modalConfirmBtn");

    title.innerText = options.title || "Confirm action";
    message.innerText = options.message || "";
    confirmBtn.innerText = options.confirmText || "Yes";

    if (options.input) {
        input.style.display = "block";
        input.value = options.defaultValue || "";
        input.placeholder = options.placeholder || "";
        setTimeout(() => input.focus(), 50);
    } else {
        input.style.display = "none";
        input.value = "";
    }

    activeModalCallback = options.onConfirm || null;

    confirmBtn.onclick = function () {
        const value = input.value.trim();

        if (options.input && !value) {
            showToast("Please enter a value.", "warning");
            return;
        }

        closeModal();

        if (activeModalCallback) {
            activeModalCallback(value);
        }
    };

    backdrop.style.display = "flex";
}

function closeModal() {
    document.getElementById("modalBackdrop").style.display = "none";
}

/* ------------------------------------------------------------
   Basic layout controls
------------------------------------------------------------ */
function toggleSidebar() {
    const sidebar = document.querySelector(".sidebar");

    if (!sidebar) return;

    sidebar.style.display = sidebar.style.display === "none" ? "flex" : "none";
}

function toggleSection(sectionId, arrowId) {
    const section = document.getElementById(sectionId);
    const arrow = document.getElementById(arrowId);

    if (!section || !arrow) return;

    if (section.style.display === "none") {
        section.style.display = "block";
        arrow.innerText = "▼";
    } else {
        section.style.display = "none";
        arrow.innerText = "▶";
    }
}

/* ------------------------------------------------------------
   Login and signup
------------------------------------------------------------ */
async function checkLogin() {
    try {
        const response = await fetch("/me");

        if (!response.ok) {
            showLogin();
            return;
        }

        const data = await response.json();

        employee = data.employee;

        await showApp();

    } catch {
        showLogin();
    }
}

function showLogin() {
    employee = null;
    currentSessionId = null;

    const chatBox = document.getElementById("chatBox");

    if (chatBox) {
        chatBox.innerHTML = "";
    }

    document.getElementById("loginPage").style.display = "flex";
    document.getElementById("appPage").style.display = "none";
}

async function showApp() {
    document.getElementById("loginPage").style.display = "none";
    document.getElementById("appPage").style.display = "flex";

    document.getElementById("profileName").innerText = employee.name || "Employee";
    document.getElementById("profileEmail").innerText = employee.email || "";

    await loadKnowledgeFolder();
    await loadDocuments();
    await loadSessions();

    startAutoRefresh();

    currentSessionId = null;
    newChat();
}

async function login() {
    const email = document.getElementById("loginEmail").value.trim();
    const password = document.getElementById("loginPassword").value;
    const status = document.getElementById("loginStatus");

    status.innerText = "";

    if (!email || !password) {
        status.innerText = "Please enter email and password.";
        return;
    }

    try {
        const response = await fetch("/login", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                email,
                password
            })
        });

        if (!response.ok) {
            const error = await response.json();
            status.innerText = error.detail || "Login failed.";
            return;
        }

        const data = await response.json();

        employee = data.employee;

        showToast("Login successful", "success");
        await showApp();

    } catch {
        status.innerText = "Login failed.";
    }
}

async function signup() {
    const name = document.getElementById("signupName").value.trim();
    const email = document.getElementById("signupEmail").value.trim();
    const department = document.getElementById("signupDepartment").value.trim();
    const password = document.getElementById("signupPassword").value;
    const status = document.getElementById("signupStatus");

    status.innerText = "";

    if (!name || !email || !password) {
        status.innerText = "Please fill name, email and password.";
        return;
    }

    try {
        const response = await fetch("/signup", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                name,
                email,
                department,
                password
            })
        });

        const data = await response.json();

        if (!response.ok) {
            status.innerText = data.detail || "Signup failed.";
            return;
        }

        showToast(data.message || "Account created successfully.", "success");
        setAuthTab("login");
        document.getElementById("loginEmail").value = email;

    } catch {
        status.innerText = "Signup failed.";
    }
}

async function logout() {
    try {
        await fetch("/logout", {
            method: "POST"
        });
    } catch {
        // Ignore logout network failure.
    }

    employee = null;
    currentSessionId = null;
    documents = [];
    selectedDocumentIds.clear();

    stopAutoRefresh();
    showLogin();
}

/* ------------------------------------------------------------
   Assistant mode
------------------------------------------------------------ */
function setAssistantMode(mode) {
    assistantMode = mode;

    document.getElementById("knowledgeModeBtn").classList.remove("active");
    document.getElementById("databaseModeBtn").classList.remove("active");

    const documentsSidebarSection = document.getElementById("documentsSidebarSection");
    const uploadSidebarSection = document.getElementById("uploadSidebarSection");
    const folderSidebarSection = document.getElementById("folderSidebarSection");
    const questionInput = document.getElementById("questionInput");

    if (mode === "knowledge") {
        document.getElementById("knowledgeModeBtn").classList.add("active");

        if (documentsSidebarSection) documentsSidebarSection.style.display = "block";
        if (uploadSidebarSection) uploadSidebarSection.style.display = "block";
        if (folderSidebarSection) folderSidebarSection.style.display = "block";

        questionInput.placeholder = "Ask anything from your knowledge base...";
        document.getElementById("systemStatus").innerText = "Knowledge Mode";

    } else {
        document.getElementById("databaseModeBtn").classList.add("active");

        if (documentsSidebarSection) documentsSidebarSection.style.display = "none";
        if (uploadSidebarSection) uploadSidebarSection.style.display = "none";
        if (folderSidebarSection) folderSidebarSection.style.display = "none";

        questionInput.placeholder = "Ask anything from database...";
        document.getElementById("systemStatus").innerText = "Database Mode";
    }

    currentSessionId = null;

    loadSessions();
    newChat();

    showToast(
        mode === "knowledge" ? "Knowledge mode selected" : "Database mode selected",
        "success"
    );
}

/* ------------------------------------------------------------
   Knowledge folder and indexing
------------------------------------------------------------ */
async function loadKnowledgeFolder() {
    try {
        const response = await fetch("/knowledge-folder");

        if (!response.ok) return;

        const data = await response.json();

        document.getElementById("folderInput").value = data.folder_path || "";
        document.getElementById("folderStatus").innerText =
            "Current folder: " + (data.folder_path || "Not set");

    } catch {
        // Silent because folder status is not critical for page load.
    }
}

async function setKnowledgeFolder() {
    const folderPath = document.getElementById("folderInput").value.trim();
    const status = document.getElementById("folderStatus");

    if (!folderPath) {
        status.innerText = "Please enter folder path.";
        return;
    }

    try {
        const response = await fetch("/set-knowledge-folder", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                folder_path: folderPath
            })
        });

        const data = await response.json();

        status.innerText = data.message;

        if (data.success) {
            showToast("Knowledge folder saved", "success");
            await loadDocuments();
        } else {
            showToast(data.message, "error");
        }

    } catch {
        status.innerText = "Failed to save folder.";
        showToast("Failed to save folder", "error");
    }
}

async function indexNow() {
    const status = document.getElementById("folderStatus");

    status.innerText = "Manual indexing started...";
    wasIndexing = true;

    document.getElementById("systemStatus").innerText = "Indexing...";

    try {
        const response = await fetch("/index-now", {
            method: "POST"
        });

        const data = await response.json();

        status.innerText = data.message;

        showToast("Indexing started", "success");
        startIndexStatusPolling();

    } catch {
        status.innerText = "Failed to start indexing.";
        showToast("Failed to start indexing", "error");
    }
}

async function checkIndexStatus() {
    try {
        const response = await fetch("/index-status");

        if (!response.ok) return;

        const data = await response.json();

        if (data.running) {
            wasIndexing = true;

            document.getElementById("systemStatus").innerText =
                `Indexing... Pending: ${data.pending}, Running: ${data.indexing}`;

            await loadDocuments();

        } else {
            document.getElementById("systemStatus").innerText =
                assistantMode === "knowledge" ? "Knowledge Mode" : "Database Mode";

            if (wasIndexing) {
                showToast("Indexing completed. Documents are ready.", "success");
                wasIndexing = false;
                await loadDocuments();
            }
        }

    } catch {
        // Ignore polling errors.
    }
}

function startIndexStatusPolling() {
    if (indexStatusTimer) {
        clearInterval(indexStatusTimer);
    }

    checkIndexStatus();
    indexStatusTimer = setInterval(checkIndexStatus, 3000);
}

function startAutoRefresh() {
    if (!documentRefreshTimer) {
        documentRefreshTimer = setInterval(loadDocuments, 10000);
    }

    startIndexStatusPolling();
}

function stopAutoRefresh() {
    if (documentRefreshTimer) {
        clearInterval(documentRefreshTimer);
        documentRefreshTimer = null;
    }

    if (indexStatusTimer) {
        clearInterval(indexStatusTimer);
        indexStatusTimer = null;
    }
}

/* ------------------------------------------------------------
   Documents
------------------------------------------------------------ */
async function loadDocuments() {
    try {
        const response = await fetch("/documents");

        if (!response.ok) return;

        const data = await response.json();

        documents = data.documents || [];

        document.getElementById("documentCount").innerText = documents.length;

        renderDocuments();

    } catch {
        // Ignore refresh failures.
    }
}

function renderDocuments() {
    const list = document.getElementById("documentsList");
    const searchInput = document.getElementById("docSearchInput");
    const selectAllInput = document.getElementById("selectAllDocs");

    if (!list) return;

    const search = searchInput ? searchInput.value.toLowerCase() : "";
    const selectAll = selectAllInput ? selectAllInput.checked : true;

    list.innerHTML = "";

    const filteredDocs = documents.filter((doc) =>
        doc.filename.toLowerCase().includes(search)
    );

    if (filteredDocs.length === 0) {
        list.innerHTML = "<div class='empty-state'>No documents found.</div>";
        return;
    }

    filteredDocs.forEach((doc) => {
        const ready = isReady(doc);
        const checked = selectedDocumentIds.has(doc.document_id) ? "checked" : "";
        const disabled = (!ready || selectAll) ? "disabled" : "";

        const div = document.createElement("div");
        div.className = "doc-item";

        div.innerHTML = `
            <div class="doc-row">
                <input type="checkbox"
                       class="doc-check"
                       value="${doc.document_id}"
                       ${checked}
                       ${disabled}
                       onchange="updateSelectedDocument(${doc.document_id}, this.checked)">
                <a class="doc-name"
                   href="/download-document/${doc.document_id}"
                   target="_blank"
                   title="Download document">
                   ${escapeHtml(doc.filename)}
                </a>
            </div>
        `;

        list.appendChild(div);
    });
}

function updateSelectedDocument(documentId, checked) {
    if (checked) {
        selectedDocumentIds.add(documentId);
    } else {
        selectedDocumentIds.delete(documentId);
    }
}

function toggleAllDocuments() {
    const selectAll = document.getElementById("selectAllDocs").checked;

    if (selectAll) {
        selectedDocumentIds.clear();
    }

    renderDocuments();
}

function getSelectedDocumentIds() {
    const selectAll = document.getElementById("selectAllDocs").checked;

    if (selectAll) {
        return [];
    }

    return Array.from(selectedDocumentIds);
}

function isReady(doc) {
    return (doc.indexing_status || "ready") === "ready";
}

function hasReadyDocuments() {
    return documents.some((doc) => isReady(doc));
}

/* ------------------------------------------------------------
   Uploads
------------------------------------------------------------ */
function openComposerFilePicker() {
    document.getElementById("composerFileInput").click();
}

async function uploadComposerFiles() {
    const input = document.getElementById("composerFileInput");

    if (!input.files || input.files.length === 0) return;

    await uploadSelectedFiles(input, "Files uploaded from chat bar.");
}

async function uploadFiles() {
    const input = document.getElementById("fileInput");

    if (!input.files || input.files.length === 0) {
        document.getElementById("uploadStatus").innerText = "Please select files first.";
        return;
    }

    await uploadSelectedFiles(input, "Upload completed.");
}

async function uploadSelectedFiles(input, successMessage) {
    const status = document.getElementById("uploadStatus");
    const formData = new FormData();

    for (const file of input.files) {
        formData.append("files", file);
    }

    if (status) {
        status.innerText = "Uploading...";
    }

    try {
        const response = await fetch("/upload", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (status) {
            status.innerText = buildUploadStatusMessage(data);
        }

        input.value = "";

        showToast(successMessage, "success");

        await loadDocuments();
        startIndexStatusPolling();

    } catch {
        if (status) {
            status.innerText = "Upload failed.";
        }

        showToast("Upload failed", "error");
    }
}

function buildUploadStatusMessage(data) {
    const messages = [];

    if (data.results && data.results.length > 0) {
        data.results.forEach((result) => {
            messages.push(`${result.filename}: ${result.message || result.status}`);
        });
    }

    return messages.length ? messages.join("\\n") : data.message;
}

/* ------------------------------------------------------------
   Production-style clear documents modal
------------------------------------------------------------ */
function openClearDocumentsModal() {
    openModal({
        title: "Clear all documents?",
        message: "This will remove uploaded files and indexed chunks. This action cannot be undone.",
        confirmText: "Yes, clear",
        onConfirm: clearAllDocuments
    });
}

async function clearAllDocuments() {
    try {
        const response = await fetch("/documents/clear", {
            method: "DELETE"
        });

        const data = await response.json();

        if (!response.ok) {
            showToast(data.detail || "Failed to clear documents.", "error");
            return;
        }

        documents = [];
        selectedDocumentIds.clear();

        document.getElementById("documentCount").innerText = "0";
        document.getElementById("documentsList").innerHTML =
            "<div class='empty-state'>No documents found.</div>";

        showToast(data.message, "success");

    } catch {
        showToast("Failed to clear documents.", "error");
    }
}

/* ------------------------------------------------------------
   Chat sending and validation
------------------------------------------------------------ */
function isSmallTalk(question) {
    const q = question
        .trim()
        .toLowerCase()
        .replace(/[^a-z0-9\\s]/g, "")
        .replace(/\\s+/g, " ");

    return [
        "hi",
        "hello",
        "hey",
        "hii",
        "hiii",
        "thanks",
        "thank you",
        "thankyou",
        "ok",
        "okay",
        "done",
        "bye"
    ].includes(q);
}

function validateBeforeSend(question) {
    if (assistantMode !== "knowledge") {
        return true;
    }

    if (isSmallTalk(question)) {
        return true;
    }

    const selectAll = document.getElementById("selectAllDocs").checked;
    const selectedIds = getSelectedDocumentIds();

    if (!hasReadyDocuments()) {
        addMessage("Assistant", "No ready documents are available. Please index documents first.", "assistant");
        return false;
    }

    if (!selectAll && selectedIds.length === 0) {
        addMessage("Assistant", "Please select at least one ready document or enable Search all ready documents.", "assistant");
        return false;
    }

    return true;
}

async function sendMessage() {
    const input = document.getElementById("questionInput");
    const sendBtn = document.getElementById("sendBtn");
    const question = input.value.trim();

    if (!question) return;

    if (!validateBeforeSend(question)) return;

    const selectedIds = getSelectedDocumentIds();

    addMessage("You", question, "user");

    input.value = "";
    resizeQuestionInput();

    sendBtn.disabled = true;

    addThinkingMessage();

    try {
        let response;

        if (assistantMode === "knowledge") {
            response = await fetch("/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    question,
                    session_id: currentSessionId,
                    document_ids: selectedIds
                })
            });
        } else {
            response = await fetch("/db-chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json"
                },
                body: JSON.stringify({
                    question,
                    session_id: currentSessionId
                })
            });
        }

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || "Request failed");
        }

        if (data.session_id) {
            currentSessionId = data.session_id;
        }

        removeThinkingMessage();
        addAssistantAnswer(data.answer, data.sources || [], data);

        await loadSessions();

    } catch {
        removeThinkingMessage();
        addMessage("Assistant", "Something went wrong while generating the answer.", "assistant");
        showToast("Answer generation failed", "error");

    } finally {
        sendBtn.disabled = false;
        input.focus();
    }
}

/* ------------------------------------------------------------
   Chat rendering
------------------------------------------------------------ */
function removeWelcome() {
    const welcome = document.getElementById("welcomeCard");

    if (welcome) {
        welcome.remove();
    }
}

function addMessage(role, text, type, isThinking = false) {
    removeWelcome();

    const chatBox = document.getElementById("chatBox");
    const wrap = document.createElement("div");

    wrap.className = "message-wrap";

    if (isThinking) {
        wrap.setAttribute("data-thinking", "true");
    }

    const label = document.createElement("div");
    label.className = "role-label";
    label.innerText = role;

    const msg = document.createElement("div");
    msg.className = "message " + (type === "user" ? "user-message" : "assistant-message");

    if (isThinking) {
        msg.classList.add("typing");
    }

    msg.innerText = text;

    wrap.appendChild(label);
    wrap.appendChild(msg);

    chatBox.appendChild(wrap);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function addThinkingMessage() {
    removeWelcome();

    const chatBox = document.getElementById("chatBox");
    const wrap = document.createElement("div");

    wrap.className = "message-wrap";
    wrap.setAttribute("data-thinking", "true");

    const label = document.createElement("div");
    label.className = "role-label";
    label.innerText = "Assistant";

    const msg = document.createElement("div");
    msg.className = "message assistant-message typing";
    msg.innerHTML = `
        <span class="typing-dots">
            <span></span><span></span><span></span>
        </span>
        Thinking...
    `;

    wrap.appendChild(label);
    wrap.appendChild(msg);
    chatBox.appendChild(wrap);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function addAssistantAnswer(answer, sources, data = {}) {
    removeWelcome();

    const chatBox = document.getElementById("chatBox");
    const wrap = document.createElement("div");

    wrap.className = "message-wrap";

    const label = document.createElement("div");
    label.className = "role-label";
    label.innerText = "Assistant";

    const msg = document.createElement("div");
    msg.className = "message assistant-message";

    const answerDiv = document.createElement("div");
    answerDiv.innerText = answer || "";
    msg.appendChild(answerDiv);

    if (assistantMode === "database" || data.columns || data.rows) {
        renderDatabaseResult(msg, data);
    }

    const copyBtn = document.createElement("button");
    copyBtn.className = "copy-btn";
    copyBtn.innerText = "Copy";

    copyBtn.onclick = () => {
        navigator.clipboard.writeText(answer || "");
        copyBtn.innerText = "Copied";
        setTimeout(() => {
            copyBtn.innerText = "Copy";
        }, 1200);
    };

    msg.appendChild(copyBtn);

    const feedback = document.createElement("span");
    feedback.className = "feedback-row";
    feedback.innerHTML = `
        <button onclick="submitFeedback('like')">👍</button>
        <button onclick="submitFeedback('dislike')">👎</button>
    `;
    msg.appendChild(feedback);

    if (sources.length > 0) {
        renderSources(msg, sources);
    }

    wrap.appendChild(label);
    wrap.appendChild(msg);

    chatBox.appendChild(wrap);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function renderSources(container, sources) {
    const sourcesBox = document.createElement("div");
    sourcesBox.className = "sources-box";

    const title = document.createElement("div");
    title.className = "sources-title";
    title.innerText = "Sources used";

    sourcesBox.appendChild(title);

    sources.forEach((source) => {
        const link = document.createElement("a");

        link.className = "source-link";
        link.href = source.download_url;
        link.target = "_blank";
        link.innerText = "📄 " + source.filename;

        sourcesBox.appendChild(link);
    });

    container.appendChild(sourcesBox);
}

function renderDatabaseResult(container, data = {}) {
    const payload = data.payload || data;
    const columns = payload.columns || [];
    const rows = payload.rows || [];

    if (payload.execution_time !== undefined) {
        const meta = document.createElement("div");
        meta.className = "db-result-meta";
        meta.innerText = `Execution time: ${payload.execution_time}s`;
        container.appendChild(meta);
    }

    if (columns.length === 0 || rows.length === 0) {
        return;
    }

    const tableWrapper = document.createElement("div");
    tableWrapper.className = "table-wrapper";

    const table = document.createElement("table");
    table.className = "result-table";

    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    columns.forEach((column) => {
        const th = document.createElement("th");
        th.innerText = column;
        headerRow.appendChild(th);
    });

    thead.appendChild(headerRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");

    rows.forEach((row) => {
        const tr = document.createElement("tr");

        row.forEach((cell) => {
            const td = document.createElement("td");
            td.innerText = cell;
            tr.appendChild(td);
        });

        tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    tableWrapper.appendChild(table);
    container.appendChild(tableWrapper);
}

function removeThinkingMessage() {
    const thinking = document.querySelector("[data-thinking='true']");

    if (thinking) {
        thinking.remove();
    }
}

function submitFeedback(type) {
    showToast(type === "like" ? "Feedback saved." : "Thanks, we will improve this.", "success");
}

/* ------------------------------------------------------------
   Session history with menu actions
------------------------------------------------------------ */
let sessions = [];

async function loadSessions() {
    try {
        const response = await fetch(`/sessions?mode=${assistantMode}`);

        if (!response.ok) return;

        const data = await response.json();

        sessions = data.sessions || [];

        renderSessions();

    } catch {
        // Ignore session load failure.
    }
}

function renderSessions() {
    const list = document.getElementById("sessionsList");
    const searchInput = document.getElementById("sessionSearchInput");
    const search = searchInput ? searchInput.value.toLowerCase() : "";

    list.innerHTML = "";

    const filteredSessions = sessions.filter((session) =>
        session.title.toLowerCase().includes(search)
    );

    if (filteredSessions.length === 0) {
        list.innerHTML = "<div class='empty-state'>No chat history found.</div>";
        return;
    }

    const pinnedSessions = filteredSessions.filter((session) => session.is_pinned);
    const recentSessions = filteredSessions.filter((session) => !session.is_pinned);

    if (pinnedSessions.length > 0) {
        list.appendChild(createSessionGroupTitle("Pinned"));
        pinnedSessions.forEach((session) => list.appendChild(createSessionItem(session)));
    }

    if (recentSessions.length > 0) {
        list.appendChild(createSessionGroupTitle("Recents"));
        recentSessions.forEach((session) => list.appendChild(createSessionItem(session)));
    }
}

function createSessionGroupTitle(title) {
    const div = document.createElement("div");
    div.className = "session-group-title";
    div.innerText = title;
    return div;
}

function createSessionItem(session) {
    const div = document.createElement("div");

    div.className = "session-item";

    div.innerHTML = `
        <span class="session-icon">
            ${session.is_pinned ? "📌" : "○"}
        </span>

        <span class="session-title">
            ${escapeHtml(session.title)}
        </span>

        <button class="session-menu-btn"
            onclick="openSessionMenu(event, ${session.session_id}, '${escapeForAttribute(session.title)}', ${session.is_pinned})">
            <i class="fa-solid fa-ellipsis"></i>
        </button>
    `;

    div.onclick = (event) => {
        if (
            event.target.closest(".session-menu-btn")
        ) {
            return;
        }

        loadSessionMessages(session.session_id);
    };

    return div;
}

function openSessionMenu(event, sessionId, title, isPinned) {
    event.stopPropagation();

    closeSessionMenu();

    activeSessionMenuId = sessionId;

    const menu = document.createElement("div");
    menu.className = "session-menu";
    menu.id = "sessionMenu";

    menu.innerHTML = `
        <button onclick="openShareSessionModal(${sessionId})">
            <i class="fa-solid fa-arrow-up-right-from-square"></i>
            Share
        </button>

        <button onclick="openRenameSessionModal(${sessionId}, '${escapeForAttribute(title)}')">
            <i class="fa-solid fa-pen"></i>
            Rename
        </button>

        <button onclick="pinSession(${sessionId}, ${!isPinned})">
            <i class="fa-solid fa-thumbtack"></i>
            ${isPinned ? "Unpin chat" : "Pin chat"}
        </button>

        <button onclick="archiveSession(${sessionId})">
            <i class="fa-solid fa-box-archive"></i>
            Archive
        </button>

        <button class="danger" onclick="openDeleteSessionModal(${sessionId})">
            <i class="fa-solid fa-trash"></i>
            Delete
        </button>
    `;

    document.body.appendChild(menu);

    const rect = event.target.getBoundingClientRect();

    menu.style.left = Math.min(rect.left, window.innerWidth - 260) + "px";
    menu.style.top = rect.bottom + 8 + "px";
    menu.style.display = "block";
}

function closeSessionMenu() {
    const menu = document.getElementById("sessionMenu");

    if (menu) {
        menu.remove();
    }
}

function shareSession(sessionId) {
    navigator.clipboard.writeText(`${window.location.origin}/?session=${sessionId}`);
    closeSessionMenu();
    showToast("Chat link copied.", "success");
}

function openRenameSessionModal(sessionId, title) {
    closeSessionMenu();

    openModal({
        title: "Rename chat",
        message: "Enter a new name for this chat.",
        input: true,
        defaultValue: title,
        confirmText: "Save",
        onConfirm: (value) => renameSession(sessionId, value)
    });
}

async function renameSession(sessionId, title) {
    try {
        const response = await fetch(`/sessions/${sessionId}/rename`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                title
            })
        });

        if (!response.ok) throw new Error();

        showToast("Chat renamed.", "success");
        await loadSessions();

    } catch {
        showToast("Failed to rename chat.", "error");
    }
}

async function pinSession(sessionId, isPinned) {
    closeSessionMenu();

    try {
        const response = await fetch(`/sessions/${sessionId}/pin`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                is_pinned: isPinned
            })
        });

        if (!response.ok) throw new Error();

        showToast(isPinned ? "Chat pinned." : "Chat unpinned.", "success");
        await loadSessions();

    } catch {
        showToast("Failed to update pin.", "error");
    }
}

async function archiveSession(sessionId) {
    closeSessionMenu();

    try {
        const response = await fetch(`/sessions/${sessionId}/archive`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                is_archived: true
            })
        });

        if (!response.ok) throw new Error();

        if (currentSessionId === sessionId) {
            newChat();
        }

        showToast("Chat archived.", "success");
        await loadSessions();

    } catch {
        showToast("Failed to archive chat.", "error");
    }
}

function openDeleteSessionModal(sessionId) {
    closeSessionMenu();

    openModal({
        title: "Delete chat?",
        message: "This chat will be permanently deleted.",
        confirmText: "Delete",
        onConfirm: () => deleteSession(sessionId)
    });
}

async function deleteSession(sessionId) {
    try {
        const response = await fetch(`/sessions/${sessionId}`, {
            method: "DELETE"
        });

        if (!response.ok) throw new Error();

        if (currentSessionId === sessionId) {
            newChat();
        }

        showToast("Chat deleted.", "success");
        await loadSessions();

    } catch {
        showToast("Failed to delete chat.", "error");
    }
}

async function loadSessionMessages(sessionId) {
    currentSessionId = sessionId;

    try {
        const response = await fetch(`/sessions/${sessionId}/messages`);

        if (!response.ok) return;

        const data = await response.json();
        const chatBox = document.getElementById("chatBox");

        chatBox.innerHTML = "";

        data.messages.forEach((msg) => {
            if (msg.role === "assistant") {
                addAssistantAnswer(
                    msg.message,
                    msg.sources || [],
                    msg.payload || {}
                );
            } else {
                addMessage("You", msg.message, "user");
            }
        });

    } catch {
        showToast("Failed to load chat", "error");
    }
}

/* ------------------------------------------------------------
   New chat and welcome
------------------------------------------------------------ */
function newChat() {
    currentSessionId = null;
    selectedDocumentIds.clear();

    if (assistantMode === "knowledge" && documents.length > 0) {
        renderDocuments();
    }

    const chatBox = document.getElementById("chatBox");
    const name = employee && employee.name ? employee.name.split(" ")[0] : "";

    const title = name
        ? `Good to see you, ${escapeHtml(name)}.`
        : "Good to see you.";

    const subtitle = assistantMode === "database"
        ? "Ask questions from PostgreSQL data. Results will be shown as a clean answer and table when available."
        : "Ask from indexed documents, upload files, or manually index your selected knowledge folder.";

    chatBox.innerHTML = `
        <div class="welcome-card" id="welcomeCard">
            <div class="welcome-title">${title}</div>
            <div class="welcome-subtitle">${subtitle}</div>
        </div>
    `;
}

/* ------------------------------------------------------------
   Voice search
------------------------------------------------------------ */
function startVoiceSearch() {
    const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        showToast("Voice search is not supported in this browser.", "warning");
        return;
    }

    const recognition = new SpeechRecognition();
    const input = document.getElementById("questionInput");

    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    document.getElementById("voiceBtn").innerHTML =
        '<i class="fa-solid fa-wave-square"></i>';

    recognition.onresult = function (event) {
        const transcript = event.results[0][0].transcript;
        input.value = transcript;
        resizeQuestionInput();
        input.focus();
    };

    recognition.onerror = function () {
        showToast("Could not capture voice.", "error");
    };

    recognition.onend = function () {
        document.getElementById("voiceBtn").innerHTML =
            '<i class="fa-solid fa-microphone"></i>';
    };

    recognition.start();
}

/* ------------------------------------------------------------
   Textarea behavior
------------------------------------------------------------ */
function setupQuestionInput() {
    const input = document.getElementById("questionInput");

    if (!input) return;

    input.addEventListener("input", resizeQuestionInput);

    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });

    resizeQuestionInput();
}

function resizeQuestionInput() {
    const input = document.getElementById("questionInput");

    if (!input) return;

    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
}

/* ------------------------------------------------------------
   String escaping helpers
------------------------------------------------------------ */
function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function escapeForAttribute(value) {
    return String(value)
        .replaceAll("\\", "\\\\")
        .replaceAll("'", "\\'")
        .replaceAll('"', "&quot;");
}

/* ------------------------------------------------------------
   Bootstrap
------------------------------------------------------------ */
document.addEventListener("DOMContentLoaded", () => {
    setupQuestionInput();

    const loginPassword = document.getElementById("loginPassword");
    const signupPassword = document.getElementById("signupPassword");

    if (loginPassword) {
        loginPassword.addEventListener("keydown", (event) => {
            if (event.key === "Enter") login();
        });
    }

    if (signupPassword) {
        signupPassword.addEventListener("keydown", (event) => {
            if (event.key === "Enter") signup();
        });
    }

    document.addEventListener("click", (event) => {
        const menu = document.getElementById("sessionMenu");

        if (menu && !menu.contains(event.target) && !event.target.classList.contains("session-menu-btn")) {
            closeSessionMenu();
        }
    });

    checkLogin();
});

function closeSessionMenu() {
    const menu = document.getElementById("sessionMenu");

    if (menu) {
        menu.remove();
    }
}

function shareSession(sessionId) {
    navigator.clipboard.writeText(`${window.location.origin}/?session=${sessionId}`);
    closeSessionMenu();
    showToast("Chat link copied.", "success");
}

function openRenameSessionModal(sessionId, title) {
    closeSessionMenu();

    openModal({
        title: "Rename chat",
        message: "Enter a new name for this chat.",
        input: true,
        defaultValue: title,
        confirmText: "Save",
        onConfirm: (value) => renameSession(sessionId, value)
    });
}

async function renameSession(sessionId, title) {
    try {
        const response = await fetch(`/sessions/${sessionId}/rename`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                title
            })
        });

        if (!response.ok) throw new Error();

        showToast("Chat renamed.", "success");
        await loadSessions();

    } catch {
        showToast("Failed to rename chat.", "error");
    }
}

async function pinSession(sessionId, isPinned) {
    closeSessionMenu();

    try {
        const response = await fetch(`/sessions/${sessionId}/pin`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                is_pinned: isPinned
            })
        });

        if (!response.ok) throw new Error();

        showToast(isPinned ? "Chat pinned." : "Chat unpinned.", "success");
        await loadSessions();

    } catch {
        showToast("Failed to update pin.", "error");
    }
}

async function archiveSession(sessionId) {
    closeSessionMenu();

    try {
        const response = await fetch(`/sessions/${sessionId}/archive`, {
            method: "PATCH",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                is_archived: true
            })
        });

        if (!response.ok) throw new Error();

        if (currentSessionId === sessionId) {
            newChat();
        }

        showToast("Chat archived.", "success");
        await loadSessions();

    } catch {
        showToast("Failed to archive chat.", "error");
    }
}

function openDeleteSessionModal(sessionId) {
    closeSessionMenu();

    openModal({
        title: "Delete chat?",
        message: "This chat will be permanently deleted.",
        confirmText: "Delete",
        onConfirm: () => deleteSession(sessionId)
    });
}

async function deleteSession(sessionId) {
    try {
        const response = await fetch(`/sessions/${sessionId}`, {
            method: "DELETE"
        });

        if (!response.ok) throw new Error();

        if (currentSessionId === sessionId) {
            newChat();
        }

        showToast("Chat deleted.", "success");
        await loadSessions();

    } catch {
        showToast("Failed to delete chat.", "error");
    }
}

async function loadSessionMessages(sessionId) {
    currentSessionId = sessionId;

    try {
        const response = await fetch(`/sessions/${sessionId}/messages`);

        if (!response.ok) return;

        const data = await response.json();
        const chatBox = document.getElementById("chatBox");

        chatBox.innerHTML = "";

        data.messages.forEach((msg) => {
            if (msg.role === "assistant") {
                addAssistantAnswer(
                    msg.message,
                    msg.sources || [],
                    msg.payload || {}
                );
            } else {
                addMessage("You", msg.message, "user");
            }
        });

    } catch {
        showToast("Failed to load chat", "error");
    }
}

/* ------------------------------------------------------------
   New chat and welcome
------------------------------------------------------------ */
function newChat() {
    currentSessionId = null;
    selectedDocumentIds.clear();

    if (assistantMode === "knowledge" && documents.length > 0) {
        renderDocuments();
    }

    const chatBox = document.getElementById("chatBox");
    const name = employee && employee.name ? employee.name.split(" ")[0] : "";

    const title = name
        ? `Good to see you, ${escapeHtml(name)}.`
        : "Good to see you.";

    const subtitle = assistantMode === "database"
        ? "Ask questions from PostgreSQL data. Results will be shown as a clean answer and table when available."
        : "Ask from indexed documents, upload files, or manually index your selected knowledge folder.";

    chatBox.innerHTML = `
        <div class="welcome-card" id="welcomeCard">
            <div class="welcome-title">${title}</div>
            <div class="welcome-subtitle">${subtitle}</div>
        </div>
    `;
}

/* ------------------------------------------------------------
   Voice search
------------------------------------------------------------ */
function startVoiceSearch() {
    const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
        showToast("Voice search is not supported in this browser.", "warning");
        return;
    }

    const recognition = new SpeechRecognition();
    const input = document.getElementById("questionInput");

    recognition.lang = "en-IN";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    document.getElementById("voiceBtn").innerHTML =
        '<i class="fa-solid fa-wave-square"></i>';

    recognition.onresult = function (event) {
        const transcript = event.results[0][0].transcript;
        input.value = transcript;
        resizeQuestionInput();
        input.focus();
    };

    recognition.onerror = function () {
        showToast("Could not capture voice.", "error");
    };

    recognition.onend = function () {
        document.getElementById("voiceBtn").innerHTML =
            '<i class="fa-solid fa-microphone"></i>';
    };

    recognition.start();
}

/* ------------------------------------------------------------
   Textarea behavior
------------------------------------------------------------ */
function setupQuestionInput() {
    const input = document.getElementById("questionInput");

    if (!input) return;

    input.addEventListener("input", resizeQuestionInput);

    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            sendMessage();
        }
    });

    resizeQuestionInput();
}

function resizeQuestionInput() {
    const input = document.getElementById("questionInput");

    if (!input) return;

    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 160) + "px";
}

/* ------------------------------------------------------------
   String escaping helpers
------------------------------------------------------------ */
function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function escapeForAttribute(value) {
    return String(value)
        .replaceAll("\\", "\\\\")
        .replaceAll("'", "\\'")
        .replaceAll('"', "&quot;");
}

/* ------------------------------------------------------------
   Bootstrap
------------------------------------------------------------ */
document.addEventListener("DOMContentLoaded", () => {
    setupQuestionInput();

    const loginPassword = document.getElementById("loginPassword");
    const signupPassword = document.getElementById("signupPassword");

    if (loginPassword) {
        loginPassword.addEventListener("keydown", (event) => {
            if (event.key === "Enter") login();
        });
    }

    if (signupPassword) {
        signupPassword.addEventListener("keydown", (event) => {
            if (event.key === "Enter") signup();
        });
    }

    document.addEventListener("click", (event) => {
        const menu = document.getElementById("sessionMenu");

        if (menu && !menu.contains(event.target) && !event.target.classList.contains("session-menu-btn")) {
            closeSessionMenu();
        }
    });

    checkLogin();
});
