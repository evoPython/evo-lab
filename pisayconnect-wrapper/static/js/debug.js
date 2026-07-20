(function () {
    const panel = document.getElementById("debug-panel");
    if (!panel) return;

    const body = document.getElementById("debug-panel-body");
    const toggleBtn = document.getElementById("debug-panel-toggle");
    const expandAllBtn = document.getElementById("debug-expand-all");
    const collapseAllBtn = document.getElementById("debug-collapse-all");

    function setPanelOpen(open) {
        document.body.classList.toggle("debug-collapsed", !open);
        if (toggleBtn) {
            toggleBtn.textContent = open ? "Hide" : "Show";
            toggleBtn.setAttribute("aria-expanded", open ? "true" : "false");
        }
    }

    toggleBtn?.addEventListener("click", () => {
        const collapsed = document.body.classList.contains("debug-collapsed");
        setPanelOpen(collapsed);
    });

    expandAllBtn?.addEventListener("click", () => {
        panel.querySelectorAll(".debug-entry").forEach((entry) => {
            entry.open = true;
        });
    });

    collapseAllBtn?.addEventListener("click", () => {
        panel.querySelectorAll(".debug-entry").forEach((entry) => {
            entry.open = false;
        });
    });

    body?.addEventListener("toggle", (event) => {
        const entry = event.target;
        if (!(entry instanceof HTMLDetailsElement) || !entry.classList.contains("debug-entry")) {
            return;
        }
        if (entry.open) {
            entry.scrollIntoView({ block: "nearest", behavior: "smooth" });
        }
    }, true);
})();
