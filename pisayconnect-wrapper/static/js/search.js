const SEARCH_DEBOUNCE_MS = 350;
const MIN_QUERY_LENGTH = 2;

let searchTimer = null;
let originalListHtml = "";
let searchAbort = null;
let searchInitialized = false;
let boundInput = null;

function getSearchScope() {
    return document.body.dataset.searchScope || "classwall";
}

function getSearchListEl() {
    const view = document.body.dataset.view;
    if (view === "bulletin_board") {
        return document.getElementById("bulletin-list");
    }
    return document.getElementById("post-list");
}

function getSearchPaginationEl() {
    const view = document.body.dataset.view;
    const activeView = document.querySelector(".app-view.is-active");
    if (!activeView) {
        return document.getElementById("pagination");
    }
    return activeView.querySelector(".pagination");
}

function restoreDefaultView(listEl, status, pagination) {
    if (searchAbort) {
        searchAbort.abort();
        searchAbort = null;
    }

    if (listEl) {
        listEl.innerHTML = originalListHtml;
        listEl.classList.remove("is-searching");
    }

    if (status) {
        status.hidden = true;
        status.textContent = "";
    }

    if (pagination) {
        pagination.hidden = false;
    }

    window.initPostCards?.();
}

function resetSearchBaseline() {
    const listEl = getSearchListEl();
    const input = document.getElementById("post-search");
    const status = document.getElementById("search-status");
    const pagination = getSearchPaginationEl();

    if (listEl) {
        originalListHtml = listEl.innerHTML;
    }

    if (input && input.value.trim()) {
        input.value = "";
        restoreDefaultView(listEl, status, pagination);
    }
}

function initSearch() {
    const input = document.getElementById("post-search");
    const listEl = getSearchListEl();
    const status = document.getElementById("search-status");
    const pagination = getSearchPaginationEl();

    if (!input || !listEl) {
        return;
    }

    if (searchInitialized && boundInput === input) {
        resetSearchBaseline();
        return;
    }

    searchInitialized = true;
    boundInput = input;
    originalListHtml = listEl.innerHTML;

    input.replaceWith(input.cloneNode(true));
    const freshInput = document.getElementById("post-search");

    freshInput.addEventListener("input", () => {
        const query = freshInput.value.trim();

        if (searchTimer) {
            clearTimeout(searchTimer);
        }

        if (query.length < MIN_QUERY_LENGTH) {
            restoreDefaultView(
                getSearchListEl(),
                status,
                getSearchPaginationEl()
            );
            return;
        }

        searchTimer = setTimeout(() => runSearch(query), SEARCH_DEBOUNCE_MS);
    });

    freshInput.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            freshInput.value = "";
            restoreDefaultView(
                getSearchListEl(),
                status,
                getSearchPaginationEl()
            );
        }
    });
}

async function runSearch(query) {
    const listEl = getSearchListEl();
    const status = document.getElementById("search-status");
    const pagination = getSearchPaginationEl();
    const scope = getSearchScope();

    if (!listEl) {
        return;
    }

    if (searchAbort) {
        searchAbort.abort();
    }

    searchAbort = new AbortController();
    listEl.classList.add("is-searching");

    if (status) {
        status.hidden = false;
        status.textContent = "Searching…";
    }

    if (pagination) {
        pagination.hidden = true;
    }

    try {
        const params = new URLSearchParams({ q: query, scope });
        const res = await fetch(`/api/search?${params}`, {
            credentials: "include",
            signal: searchAbort.signal,
        });

        if (!res.ok) {
            throw new Error("Search request failed");
        }

        const data = await res.json();

        if (data.html) {
            if (scope === "bulletin_board" || scope === "bookmarks") {
                listEl.innerHTML = `<div class="post-list">${data.html}</div>`;
            } else {
                listEl.innerHTML = data.html.includes("post-list")
                    ? data.html
                    : `<div class="post-list">${data.html}</div>`;
            }
        } else {
            listEl.innerHTML = `
                <div class="empty-state">
                    <p>No posts match "${escapeHtml(data.query)}".</p>
                    <p class="search-hint">Try fewer words, fuzzy spelling, or regex like <code>/homework|quiz/i</code></p>
                </div>`;
        }

        if (status) {
            status.hidden = false;
            status.textContent = `Found ${data.count} result${data.count === 1 ? "" : "s"} for "${data.query}"`;
        }

        window.initPostCards?.();
    } catch (err) {
        if (err.name === "AbortError") {
            return;
        }

        if (status) {
            status.textContent = "Search failed. Please try again.";
        }
    } finally {
        listEl.classList.remove("is-searching");
        searchAbort = null;
    }
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

window.resetSearchBaseline = resetSearchBaseline;
window.initSearch = initSearch;

document.addEventListener("DOMContentLoaded", initSearch);
