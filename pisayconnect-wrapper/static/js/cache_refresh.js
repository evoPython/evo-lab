(function () {
    const managed = document.querySelector(".cache-managed[data-cache-refresh]");
    if (!managed) return;

    const refreshUrl = managed.dataset.cacheRefresh;
    const ui = () => window.AppUI;

    function applyResponse(data) {
        const targets = data.targets
            ? Object.entries(data.targets)
            : data.target && data.html
              ? [[data.target, data.html]]
              : [];

        const patches = targets
            .map(([targetId, html]) => {
                const el = document.getElementById(targetId);
                if (!el) return null;

                return {
                    el,
                    html,
                    expandState: ui()?.collectExpandState(el),
                    previousKeys: ui()?.collectItemKeys(el) || new Set(),
                };
            })
            .filter(Boolean);

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

    async function refresh() {
        const label = ui()?.getRefreshLabel(managed) || "Content";
        ui()?.updateSyncDisplay("syncing", `Updating ${label.toLowerCase()}`);

        try {
            const res = await fetch(refreshUrl, { credentials: "include" });
            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.error || "Refresh failed");
            }

            applyResponse(data);
            ui()?.markSynced(label);
        } catch (err) {
            ui()?.updateSyncDisplay("error", err.message || "Update failed");
            ui()?.showToast(err.message || "Update failed", "error");
        }
    }

    refresh();
})();
