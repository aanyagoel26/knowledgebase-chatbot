let currentSessionId = null;
let assistantMode = "knowledge";
let documents = [];
let employee = null;
let documentRefreshTimer = null;
let indexStatusTimer = null;
let wasIndexing = false;
let selectedDocumentIds = new Set();

function showToast(message, type = "success") {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");

    toast.className = "toast " + type;
    toast.innerText = message;

    container.appendChild(toast);

    setTimeout(() => {
        toast.remove();
    }, 4000);
}

function toggleSidebar() {
    const sidebar = document.getElementById("sidebar");

    if (!sidebar) return;

    if (sidebar.style.display === "none") {
        sidebar.style.display = "flex";
    } else {
        sidebar.style.display = "none";
    }
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

function loginEnter(event) {
    if (event.key === "Enter") {
        login();
    }
}

async function checkLogin() {
    try {
        const response = await fetch("/me");

        if (!response.ok) {
            showLogin();
            return;
        }

        const data = await response.json();
        employee = data.employee;

        showApp();

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

    await loadSessions();
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
        showApp();

    } catch {
        status.innerText = "Login failed.";
    }
}

async function logout() {
    try {
        await fetch("/logout", {
            method: "POST"
        });
    } catch {
        // ignore logout network error
    }

    employee = null;
    currentSessionId = null;
    documents = [];
    selectedDocumentIds.clear();

    stopAutoRefresh();

    const chatBox = document.getElementById("chatBox");
    const sessionsList = document.getElementById("sessionsList");

    if (chatBox) {
        chatBox.innerHTML = "";
    }

    if (sessionsList) {
        sessionsList.innerHTML = "";
    }

    showLogin();
}