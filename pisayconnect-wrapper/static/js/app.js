(function () {
    const PRELOADED_ROUTES = window.__SPA_PRELOADED__ || [];
    const viewCache = new Map();
    const refreshControllers = new Map();

    const NAV_VIEWS = {
        bulletin_board: "bulletin_board",
        dashboard: "dashboard",
        classwall: "classwall",
        bookmarks: "bookmarks",
        assessments: "assessments",
        leave_passes: "leave_passes",
        parent_add: "parent_add",
    };

    const ui = () => window.AppUI;

    function parseAppPath(pathname, search) {
        const params = new URLSearchParams(search || "");
        let path = pathname.replace(/^\/app\/?/, "").replace(/\/$/, "");

        if (!path || path === "dashboard") {
            return { view: "dashboard" };
        }

        if (path === "classwall") {
            const route = {
                view: "classwall",
                page: parseInt(params.get("page") || "1", 10),
            };
            if (params.get("schoolYear")) {
                route.school_year = params.get("schoolYear");
            }
            return route;
        }

        if (path === "bulletin-board") {
            return {
                view: "bulletin_board",
                page: parseInt(params.get("page") || "1", 10),
            };
        }

        if (path === "bookmarks") {
            return { view: "bookmarks" };
        }

        if (path === "assessments") {
            const route = { view: "assessments" };
            if (params.get("archived") === "1") {
                route.archived = true;
            }
            if (params.get("schoolYear")) {
                route.school_year = params.get("schoolYear");
            }
            return route;
        }

        const assessmentMatch = path.match(/^assessments\/(\d+)$/);
        if (assessmentMatch) {
            const period = params.get("period");
            const route = {
                view: "assessment_detail",
                enrollment_class_id: parseInt(assessmentMatch[1], 10),
            };
            if (period) {
                route.period = parseInt(period, 10);
            }
            return route;
        }

        if (path === "leave-passes") {
            const mode = params.get("mode") === "parent" ? "parent" : "student";
            const parent = params.get("parent");
            return {
                view: "leave_passes",
                mode,
                page: parseInt(params.get("page") || "1", 10),
                parent: parent ? parseInt(parent, 10) : null,
                linked: params.get("linked"),
            };
        }

        if (path === "parent/add") {
            return { view: "parent_add" };
        }

        return { view: "dashboard" };
    }

    function routeKey(route) {
        const parts = [route.view];
        const ordered = ["page", "mode", "parent", "enrollment_class_id", "period", "linked", "archived", "school_year"];

        ordered.forEach((key) => {
            if (route[key] !== undefined && route[key] !== null && route[key] !== "") {
                parts.push(`${key}=${route[key]}`);
            }
        });

        return parts.join(":");
    }

    function routeToPath(route) {
        switch (route.view) {
            case "bulletin_board": {
                const page = route.page || 1;
                return page > 1 ? `/app/bulletin-board?page=${page}` : "/app/bulletin-board";
            }
            case "dashboard":
                return "/app/dashboard";
            case "classwall": {
                const params = new URLSearchParams();
                const page = route.page || 1;
                if (page > 1) params.set("page", String(page));
                if (route.school_year) params.set("schoolYear", route.school_year);
                const query = params.toString();
                return query ? `/app/classwall?${query}` : "/app/classwall";
            }
            case "bookmarks":
                return "/app/bookmarks";
            case "assessments": {
                const params = new URLSearchParams();
                if (route.archived) {
                    params.set("archived", "1");
                }
                if (route.school_year) {
                    params.set("schoolYear", route.school_year);
                }
                const query = params.toString();
                return query ? `/app/assessments?${query}` : "/app/assessments";
            }
            case "assessment_detail": {
                const base = `/app/assessments/${route.enrollment_class_id}`;
                return route.period ? `${base}?period=${route.period}` : base;
            }
            case "leave_passes": {
                const params = new URLSearchParams();
                params.set("mode", route.mode || "student");
                params.set("page", String(route.page || 1));
                if (route.parent) {
                    params.set("parent", String(route.parent));
                }
                if (route.linked) {
                    params.set("linked", String(route.linked));
                }
                return `/app/leave-passes?${params}`;
            }
            case "parent_add":
                return "/app/parent/add";
            default:
                return "/app/dashboard";
        }
    }

    function routeToApiQuery(route) {
        const params = new URLSearchParams();
        if (route.page) params.set("page", String(route.page));
        if (route.mode) params.set("mode", route.mode);
        if (route.parent) params.set("parent", String(route.parent));
        if (route.enrollment_class_id) {
            params.set("enrollment_class_id", String(route.enrollment_class_id));
        }
        if (route.period) {
            params.set("period", String(route.period));
        }
        if (route.linked) params.set("linked", String(route.linked));
        if (route.archived) params.set("archived", "1");
        if (route.school_year) params.set("schoolYear", String(route.school_year));
        return params.toString();
    }

    function getAppViewsRoot() {
        return document.getElementById("app-views");
    }

    function ensureDynamicView() {
        const root = getAppViewsRoot();
        if (!root) {
            return null;
        }

        let dynamicEl = document.getElementById("view-dynamic");
        if (!dynamicEl) {
            dynamicEl = document.createElement("section");
            dynamicEl.id = "view-dynamic";
            dynamicEl.className = "app-view";
            dynamicEl.dataset.routeKey = "";
            dynamicEl.hidden = true;
            root.appendChild(dynamicEl);
        }

        return dynamicEl;
    }

    function escapeAttr(value) {
        if (window.CSS && typeof CSS.escape === "function") {
            return CSS.escape(String(value));
        }
        return String(value).replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    }

    function findPreloadedView(key) {
        const root = getAppViewsRoot();
        if (!root) {
            return null;
        }

        return root.querySelector(`.app-view[data-preloaded][data-route-key="${escapeAttr(key)}"]`);
    }

    function seedViewCache() {
        document.querySelectorAll(".app-view[data-preloaded]").forEach((el) => {
            if (el.dataset.routeKey) {
                viewCache.set(el.dataset.routeKey, el.innerHTML);
            }
        });
    }

    function setActiveNav(route) {
        document.querySelectorAll(".sidebar-nav-link").forEach((link) => {
            const href = link.getAttribute("href") || "";
            let active = false;

            if (route.view === "bulletin_board" && href.includes("/app/bulletin-board")) active = true;
            else if (route.view === "dashboard" && href.includes("/app/dashboard")) active = true;
            else if (route.view === "classwall" && href.includes("/app/classwall")) active = true;
            else if (route.view === "bookmarks" && href.includes("/app/bookmarks")) active = true;
            else if (
                (route.view === "assessments" || route.view === "assessment_detail") &&
                href.includes("/app/assessments")
            ) {
                active = true;
            } else if (
                (route.view === "leave_passes" || route.view === "parent_add") &&
                (href.includes("/app/leave-passes") || href.includes("/app/parent/add"))
            ) {
                active = route.view === "parent_add"
                    ? href.includes("/app/parent/add")
                    : href.includes("/app/leave-passes");
            }

            link.classList.toggle("active", active);
        });

        document.body.dataset.view = route.view === "assessment_detail" ? "assessments" : (NAV_VIEWS[route.view] || route.view);
    }

    function toggleSearchBar(route) {
        const searchRow = document.getElementById("spa-search-row");
        if (!searchRow) return;

        const show = route.view === "classwall" || route.view === "bookmarks" || route.view === "bulletin_board";
        searchRow.hidden = !show;
        document.body.dataset.searchScope =
            route.view === "bookmarks"
                ? "bookmarks"
                : route.view === "bulletin_board"
                  ? "bulletin_board"
                  : "classwall";
    }

    function hideAllViews() {
        document.querySelectorAll(".app-view").forEach((el) => {
            el.hidden = true;
            el.classList.remove("is-active");
        });
    }

    function showViewElement(el, key) {
        el.hidden = false;
        el.classList.add("is-active");
        el.dataset.routeKey = key;
    }

    function prefetchAssessmentLinks() {
        document.querySelectorAll('a[href*="/app/assessments/"]').forEach((link) => {
            if (!isSpaLink(link)) {
                return;
            }

            try {
                const url = new URL(link.href);
                prefetchRoute(parseAppPath(url.pathname, url.search));
            } catch {
                /* ignore malformed href */
            }
        });
    }

    function prefetchAssessmentCache(viewEl) {
        const managed = viewEl?.querySelector(".cache-managed[data-cache-refresh]");
        const refreshUrl = managed?.dataset.cacheRefresh;
        if (!refreshUrl) {
            return;
        }

        fetch(refreshUrl, { credentials: "include" })
            .then((res) => res.json())
            .then((data) => {
                if (managed && data && !data.error) {
                    applyRefreshResponse(managed, data);
                }
            })
            .catch(() => {});
    }

    function afterViewRender(route) {
        if (typeof window.initPostCards === "function") {
            window.initPostCards();
        }

        if (route.view === "classwall" || route.view === "bookmarks" || route.view === "bulletin_board") {
            if (typeof window.resetSearchBaseline === "function") {
                window.resetSearchBaseline();
            }
            if (typeof window.initSearch === "function") {
                window.initSearch();
            }
        }

        if (route.view === "assessments") {
            prefetchAssessmentLinks();
        }

        ui()?.refreshSyncBar?.();
        ui()?.updateSyncDisplay("idle");

        const activeEl = document.querySelector(".app-view.is-active");
        if (route.view === "assessment_detail") {
            prefetchAssessmentCache(activeEl);
        }

        if (activeEl) {
            scheduleBackgroundRefresh(activeEl);
        }
    }

    function applyRefreshResponse(managed, data) {
        const targets = data.targets
            ? Object.entries(data.targets)
            : data.target && data.html
              ? [[data.target, data.html]]
              : [];

        const patches = [];

        targets.forEach(([targetId, html]) => {
            const el = managed.querySelector(`#${targetId}`) || document.getElementById(targetId);
            if (!el) return;

            patches.push({
                el,
                expandState: ui()?.collectExpandState(el),
                previousKeys: ui()?.collectItemKeys(el) || new Set(),
                html,
            });
        });

        patches.forEach(({ el, html, previousKeys }) => {
            el.innerHTML = html;
            ui()?.highlightNewItems(el, previousKeys);
        });

        ui()?.finalizeContentPatches(patches);

        if (data.has_next !== undefined) {
            const pagination = managed.querySelector(".pagination");
            if (pagination) {
                pagination.dataset.hasNext = data.has_next ? "1" : "0";
            }
        }
    }

    async function runBackgroundRefresh(managed) {
        const refreshUrl = managed.dataset.cacheRefresh;
        if (!refreshUrl) return;

        const key = managed.closest(".app-view")?.dataset.routeKey || refreshUrl;
        if (refreshControllers.get(key)) return;

        const controller = { cancelled: false };
        refreshControllers.set(key, controller);

        const label = ui()?.getRefreshLabel(managed) || "Content";
        ui()?.updateSyncDisplay("syncing", `Updating ${label.toLowerCase()}`);

        try {
            const res = await fetch(refreshUrl, { credentials: "include" });
            const data = await res.json();

            if (controller.cancelled) return;

            if (!res.ok) {
                throw new Error(data.error || "Refresh failed");
            }

            applyRefreshResponse(managed, data);

            const routeKeyVal = managed.closest(".app-view")?.dataset.routeKey;
            if (routeKeyVal && managed.closest(".app-view")?.classList.contains("is-active")) {
                viewCache.set(routeKeyVal, managed.closest(".app-view").innerHTML);
            }

            ui()?.markSynced(label);
        } catch (err) {
            if (!controller.cancelled) {
                ui()?.updateSyncDisplay("error", err.message || "Update failed");
                ui()?.showToast(err.message || "Update failed", "error");
            }
        } finally {
            refreshControllers.delete(key);
        }
    }

    function scheduleBackgroundRefresh(viewEl) {
        const managed = viewEl.querySelector(".cache-managed[data-cache-refresh]");
        if (managed) {
            window.requestAnimationFrame(() => runBackgroundRefresh(managed));
        }
    }

    function cancelInactiveRefreshes(activeKey) {
        refreshControllers.forEach((controller, key) => {
            if (key !== activeKey) {
                controller.cancelled = true;
            }
        });
    }

    async function fetchViewHtml(route) {
        const query = routeToApiQuery(route);
        const res = await fetch(`/api/view/${route.view}?${query}`, { credentials: "include" });
        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.error || "Failed to load view");
        }

        return data;
    }

    function loadingMarkup(route) {
        const labels = {
            bulletin_board: "Bulletin Board",
            dashboard: "Dashboard",
            classwall: "Class Wall",
            bookmarks: "Bookmarks",
            assessments: "Assessments",
            assessment_detail: "Assessment details",
            leave_passes: "Leave Passes",
            parent_add: "Link parent",
        };
        const label = labels[route.view] || "Page";
        return `
            <div class="view-loading card">
                <div class="view-loading-spinner" aria-hidden="true"></div>
                <p class="view-loading-text">Loading ${label}</p>
                <p class="page-loader-hint">This only has to load once!</p>
            </div>`;
    }

    async function navigate(pathname, search, { replace = false, skipHistory = false } = {}) {
        const route = parseAppPath(pathname, search);
        const key = routeKey(route);
        const targetPath = routeToPath(route);

        if (!getAppViewsRoot()) {
            window.location.assign(targetPath);
            return;
        }

        if (!skipHistory && !replace && `${location.pathname}${location.search}` !== targetPath) {
            history.pushState({ routeKey: key }, "", targetPath);
        } else if (replace) {
            history.replaceState({ routeKey: key }, "", targetPath);
        }

        setActiveNav(route);
        toggleSearchBar(route);
        cancelInactiveRefreshes(key);

        const viewEl = findPreloadedView(key);
        const dynamicEl = ensureDynamicView();

        hideAllViews();

        if (viewEl) {
            showViewElement(viewEl, key);
            afterViewRender(route);
            return;
        }

        if (!dynamicEl) {
            window.location.assign(targetPath);
            return;
        }

        if (viewCache.has(key)) {
            dynamicEl.innerHTML = viewCache.get(key);
            showViewElement(dynamicEl, key);
            afterViewRender(route);
            return;
        }

        dynamicEl.innerHTML = loadingMarkup(route);
        showViewElement(dynamicEl, key);

        try {
            const data = await fetchViewHtml(route);
            dynamicEl.innerHTML = data.html;
            viewCache.set(key, data.html);
            if (data.title) {
                document.title = data.title;
            }
            afterViewRender(route);
        } catch (err) {
            dynamicEl.innerHTML = `<div class="alert alert-error">${err.message || "Could not load page."}</div>`;
            ui()?.showToast(err.message || "Could not load page", "error");
        }
    }

    function isSpaLink(link) {
        if (!link || !link.href) return false;
        if (link.target === "_blank" || link.hasAttribute("download")) return false;
        if (link.dataset.spaLink !== undefined || link.hasAttribute("data-spa-link")) return true;

        try {
            const url = new URL(link.href);
            return url.origin === location.origin && url.pathname.startsWith("/app");
        } catch {
            return false;
        }
    }

    function prefetchRoute(route) {
        const key = routeKey(route);
        if (viewCache.has(key) || PRELOADED_ROUTES.includes(key)) {
            return;
        }

        fetchViewHtml(route)
            .then((data) => {
                viewCache.set(key, data.html);
            })
            .catch(() => {});
    }

    function prefetchMainViews() {
        prefetchRoute({ view: "bulletin_board", page: 1 });
        prefetchRoute({ view: "classwall", page: 1 });
        prefetchRoute({ view: "bookmarks" });
        prefetchRoute({ view: "assessments" });
        prefetchRoute({ view: "leave_passes", mode: "student", page: 1 });
        prefetchRoute({ view: "parent_add" });
    }

    function invalidateSpaRoutes(viewPrefix) {
        for (const key of [...viewCache.keys()]) {
            if (key === viewPrefix || key.startsWith(`${viewPrefix}:`)) {
                viewCache.delete(key);
            }
        }

        document.querySelectorAll(".app-view[data-preloaded]").forEach((el) => {
            const routeKeyVal = el.dataset.routeKey || "";
            if (routeKeyVal === viewPrefix || routeKeyVal.startsWith(`${viewPrefix}:`)) {
                delete el.dataset.preloaded;
            }
        });
    }

    document.addEventListener("change", (event) => {
        const select = event.target.closest(".schoolyear-select");
        if (!select) return;
        if (!getAppViewsRoot()) return;

        const view = select.dataset.view;
        if (view !== "classwall" && view !== "assessments") return;

        const schoolYear = select.value;
        if (!schoolYear) return;

        const params = new URLSearchParams(location.search);
        params.set("schoolYear", schoolYear);

        let pathname = "/app/assessments";
        if (view === "classwall") {
            pathname = "/app/classwall";
            params.delete("page");
        }

        // The chosen year is shared between Assessments and Class Wall, so
        // drop any stale preloaded/cached snapshot of both before refetching.
        if (typeof window.spaInvalidateRoutes === "function") {
            window.spaInvalidateRoutes("classwall");
            window.spaInvalidateRoutes("assessments");
        }

        const query = params.toString();
        navigate(pathname, query ? `?${query}` : "");
    });

    document.addEventListener("click", (event) => {
        const link = event.target.closest("a[href]");
        if (!isSpaLink(link)) return;
        if (!getAppViewsRoot()) return;

        event.preventDefault();
        const url = new URL(link.href);
        navigate(url.pathname, url.search);
    });

    window.addEventListener("popstate", () => {
        if (!getAppViewsRoot()) return;
        navigate(location.pathname, location.search, { replace: true, skipHistory: true });
    });

    document.addEventListener("mouseenter", (event) => {
        const link = event.target.closest("a.assessment-class-card[href]");
        if (!link || !isSpaLink(link)) {
            return;
        }

        try {
            const url = new URL(link.href);
            prefetchRoute(parseAppPath(url.pathname, url.search));
        } catch {
            /* ignore */
        }
    }, true);

    document.addEventListener("DOMContentLoaded", () => {
        if (!getAppViewsRoot()) {
            return;
        }

        seedViewCache();
        navigate(location.pathname, location.search, { replace: true, skipHistory: true });

        if ("requestIdleCallback" in window) {
            requestIdleCallback(prefetchMainViews, { timeout: 3000 });
        } else {
            window.setTimeout(prefetchMainViews, 500);
        }
    });

    window.spaNavigate = navigate;
    window.spaInvalidateRoutes = invalidateSpaRoutes;
})();
