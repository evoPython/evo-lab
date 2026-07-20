(function () {
    const VIEW_LABELS = {
        bulletin_board: "Bulletin Board",
        dashboard: "Dashboard",
        classwall: "Class Wall",
        bookmarks: "Bookmarks",
        assessments: "Assessments",
        assessment_detail: "Assessment details",
        leave_passes: "Leave Passes",
        parent_add: "Link parent",
    };

    const HIGHLIGHT_SELECTORS = [
        "[data-post-id]",
        "[data-bulletin-id]",
        "[data-pass-id]",
        "[data-enrollment-class-id]",
        "[data-entry-id]",
    ].join(", ");

    let syncBar = null;
    let syncText = null;
    let syncIndicator = null;
    let toastRoot = null;
    let lastSyncAt = null;
    let relativeTimer = null;

    function resolveSyncBar() {
        const active = document.querySelector(".app-view.is-active .sync-status");
        if (active) {
            return active;
        }

        return document.querySelector(".cache-managed .sync-status");
    }

    function bindSyncBar() {
        syncBar = resolveSyncBar();
        syncText = syncBar?.querySelector(".sync-status-text");
        syncIndicator = syncBar?.querySelector(".sync-status-indicator");
    }

    function initMobileNav() {
        const toggle = document.querySelector(".sidebar-toggle");
        const sidebar = document.getElementById("app-sidebar");
        const backdrop = document.querySelector(".sidebar-backdrop");
        if (!toggle || !sidebar) {
            return;
        }

        const desktopQuery = window.matchMedia("(min-width: 769px)");

        function setSidebarOpen(open) {
            document.body.classList.toggle("sidebar-open", open);
            toggle.setAttribute("aria-expanded", open ? "true" : "false");
            toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
            if (backdrop) {
                backdrop.hidden = !open;
                backdrop.setAttribute("aria-hidden", open ? "false" : "true");
            }
        }

        toggle.addEventListener("click", () => {
            setSidebarOpen(!document.body.classList.contains("sidebar-open"));
        });

        backdrop?.addEventListener("click", () => setSidebarOpen(false));

        sidebar.querySelectorAll(".sidebar-nav-link[data-spa-link], .sidebar-brand-link[data-spa-link]").forEach((link) => {
            link.addEventListener("click", () => setSidebarOpen(false));
        });

        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
                setSidebarOpen(false);
            }
        });

        desktopQuery.addEventListener("change", (event) => {
            if (event.matches) {
                setSidebarOpen(false);
            }
        });
    }

    function init() {
        bindSyncBar();
        toastRoot = document.getElementById("toast-root");

        initTheme();
        initMobileNav();
        startRelativeTimer();
        updateSyncDisplay("idle");
    }

    function initTheme() {
        const stored = localStorage.getItem("theme");
        const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
        const theme = stored === "light" || stored === "dark" ? stored : prefersDark ? "dark" : "light";
        applyTheme(theme);

        document.addEventListener("click", (event) => {
            const toggle = event.target.closest(".theme-toggle");
            if (!toggle) return;

            event.preventDefault();
            const current = document.documentElement.getAttribute("data-theme") || "light";
            const next = current === "dark" ? "light" : "dark";
            applyTheme(next);
            localStorage.setItem("theme", next);
        });
    }

    function applyTheme(theme) {
        document.documentElement.setAttribute("data-theme", theme);
        document.querySelectorAll(".theme-toggle").forEach((toggle) => {
            const label = toggle.querySelector(".theme-toggle-label");
            if (label) {
                label.textContent = theme === "dark" ? "Light mode" : "Dark mode";
            }
            toggle.setAttribute("aria-label", theme === "dark" ? "Switch to light mode" : "Switch to dark mode");
            toggle.dataset.theme = theme;
        });
    }

    function formatRelativeTime(date) {
        const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
        if (seconds < 10) return "just now";
        if (seconds < 60) return `${seconds}s ago`;
        const minutes = Math.floor(seconds / 60);
        if (minutes < 60) return `${minutes}m ago`;
        const hours = Math.floor(minutes / 60);
        if (hours < 24) return `${hours}h ago`;
        return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    }

    function startRelativeTimer() {
        if (relativeTimer) {
            clearInterval(relativeTimer);
        }
        relativeTimer = window.setInterval(() => {
            bindSyncBar();
            if (lastSyncAt && syncBar?.dataset.state === "idle" && syncText) {
                syncText.textContent = `Last updated ${formatRelativeTime(lastSyncAt)}`;
            }
        }, 30000);
    }

    function updateSyncDisplay(state, message) {
        bindSyncBar();
        if (!syncBar || !syncText) return;

        syncBar.dataset.state = state;
        syncBar.classList.toggle("is-syncing", state === "syncing");
        syncBar.classList.toggle("is-error", state === "error");

        if (state === "syncing") {
            syncText.textContent = message || "Updating";
            return;
        }

        if (state === "error") {
            syncText.textContent = message || "Update failed";
            return;
        }

        if (lastSyncAt) {
            syncText.textContent = `Last updated ${formatRelativeTime(lastSyncAt)}`;
        } else {
            syncText.textContent = message || "Up to date";
        }
    }

    function markSynced(label) {
        lastSyncAt = new Date();
        updateSyncDisplay("idle");
        if (label) {
            showToast(`${label} updated`, "success", 2800);
        }
    }

    function showToast(message, type = "info", duration = 4000) {
        if (!toastRoot) return;

        const toast = document.createElement("div");
        toast.className = `toast toast-${type}`;
        toast.setAttribute("role", "status");
        toast.textContent = message;
        toastRoot.appendChild(toast);

        requestAnimationFrame(() => toast.classList.add("is-visible"));

        window.setTimeout(() => {
            toast.classList.remove("is-visible");
            window.setTimeout(() => toast.remove(), 250);
        }, duration);
    }

    function collectItemKeys(container) {
        const keys = new Set();
        if (!container) return keys;

        container.querySelectorAll(HIGHLIGHT_SELECTORS).forEach((el) => {
            const key =
                el.dataset.postId ||
                el.dataset.bulletinId ||
                el.dataset.passId ||
                el.dataset.enrollmentClassId ||
                el.dataset.entryId;
            if (key) keys.add(String(key));
        });

        return keys;
    }

    function highlightNewItems(container, previousKeys) {
        if (!container || !previousKeys.size) return;

        container.querySelectorAll(HIGHLIGHT_SELECTORS).forEach((el) => {
            const key =
                el.dataset.postId ||
                el.dataset.bulletinId ||
                el.dataset.passId ||
                el.dataset.enrollmentClassId ||
                el.dataset.entryId;
            if (key && !previousKeys.has(String(key))) {
                el.classList.add("content-highlight");
                el.addEventListener(
                    "animationend",
                    () => el.classList.remove("content-highlight"),
                    { once: true }
                );
            }
        });
    }

    function gradePeriodKey(periodCard) {
        const code = periodCard.querySelector(".grade-period-code")?.textContent?.trim();
        if (code) {
            return code;
        }

        return periodCard.querySelector(".grade-period-title")?.textContent?.trim() || "";
    }

    function gradeComponentKey(row) {
        const code = row.querySelector(".grade-component-code")?.textContent?.trim();
        if (code) {
            return code;
        }

        return row.querySelector(".grade-component-name")?.textContent?.trim() || "";
    }

    function collectGradeExpandState(container) {
        const expandedComponents = new Set();
        const openDetails = new Set();

        if (!container) {
            return { expandedComponents, openDetails };
        }

        container.querySelectorAll(".grade-period-card").forEach((periodCard) => {
            const periodKey = gradePeriodKey(periodCard);

            periodCard.querySelectorAll(".grade-component-row.is-expanded[data-grade-component]").forEach((row) => {
                expandedComponents.add(`${periodKey}::${gradeComponentKey(row)}`);
            });

            if (periodCard.querySelector("details.grade-computation-details[open]")) {
                openDetails.add(periodKey);
            }
        });

        return { expandedComponents, openDetails };
    }

    function restoreGradeExpandState(container, gradeState) {
        if (!container || !gradeState) {
            return;
        }

        const { expandedComponents, openDetails } = gradeState;

        container.querySelectorAll(".grade-period-card").forEach((periodCard) => {
            const periodKey = gradePeriodKey(periodCard);

            periodCard.querySelectorAll(".grade-component-row.has-entries[data-grade-component]").forEach((row) => {
                const key = `${periodKey}::${gradeComponentKey(row)}`;
                if (!expandedComponents.has(key)) {
                    return;
                }

                row.classList.add("is-expanded");
                row.setAttribute("aria-expanded", "true");

                const componentId = row.dataset.gradeComponent;
                periodCard.querySelectorAll(`.grade-entry-row[data-grade-parent="${componentId}"]`).forEach((entryRow) => {
                    entryRow.hidden = false;
                });
            });

            if (openDetails.has(periodKey)) {
                const details = periodCard.querySelector("details.grade-computation-details");
                if (details) {
                    details.open = true;
                }
            }
        });
    }

    function collectExpandState(container) {
        const expandedPosts = new Set();

        if (container) {
            container.querySelectorAll(".post-card").forEach((card) => {
                const key = card.dataset.postId || card.dataset.bulletinId;
                const toggle = card.querySelector(".post-toggle");
                if (key && toggle && !card.classList.contains("is-collapsed")) {
                    expandedPosts.add(String(key));
                }
            });
        }

        return {
            expandedPosts,
            grade: collectGradeExpandState(container),
        };
    }

    function restoreExpandState(container, state) {
        if (!container || !state) {
            return;
        }

        if (state.expandedPosts?.size) {
            container.querySelectorAll(".post-card").forEach((card) => {
                const key = card.dataset.postId || card.dataset.bulletinId;
                if (!key || !state.expandedPosts.has(String(key))) {
                    return;
                }

                card.classList.remove("is-collapsed");
                const toggle = card.querySelector(".post-toggle");
                if (toggle) {
                    toggle.textContent = "Show less";
                    toggle.setAttribute("aria-expanded", "true");
                }
            });
        }

        restoreGradeExpandState(container, state.grade);
    }

    function finalizeContentPatches(patches) {
        if (!patches?.length) {
            return;
        }

        const hasPosts = patches.some(({ el }) => el.querySelector(".post-card"));
        if (hasPosts && typeof window.initPostCards === "function") {
            window.initPostCards();
        }

        patches.forEach(({ el, expandState }) => {
            restoreExpandState(el, expandState);
        });
    }

    function getRefreshLabel(managed) {
        const view = managed.closest(".app-view")?.dataset.routeKey || "";
        if (view.startsWith("bulletin_board")) return "Bulletin Board";
        if (view.startsWith("classwall")) return "Class Wall";
        if (view.startsWith("dashboard")) return "Dashboard";
        if (view.startsWith("bookmarks")) return "Bookmarks";
        if (view.startsWith("assessments")) return "Assessments";
        if (view.startsWith("leave_passes")) return "Leave Passes";
        return "Content";
    }

    window.AppUI = {
        init,
        showToast,
        updateSyncDisplay,
        refreshSyncBar: bindSyncBar,
        markSynced,
        collectItemKeys,
        highlightNewItems,
        collectExpandState,
        restoreExpandState,
        finalizeContentPatches,
        getRefreshLabel,
        formatRelativeTime,
    };

    document.addEventListener("DOMContentLoaded", init);
})();
