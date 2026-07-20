async function toggleBookmark(btn) {
    const postId = btn.dataset.postId;
    const source = btn.dataset.bookmarkSource || "classwall";

    try {
        const res = await fetch(`/bookmark/${source}/${postId}`, {
            method: "POST",
            credentials: "include",
        });

        if (!res.ok) {
            throw new Error("Failed to update bookmark");
        }

        const data = await res.json();
        const card = btn.closest(".post-card");
        const onBookmarksPage = document.body.dataset.view === "bookmarks";
        const label = btn.querySelector(".btn-bookmark-label");

        if (data.status === "added") {
            btn.classList.add("bookmarked");
            btn.setAttribute("aria-pressed", "true");
            if (label) label.textContent = "Bookmarked";
        } else {
            btn.classList.remove("bookmarked");
            btn.setAttribute("aria-pressed", "false");
            if (label) label.textContent = "Bookmark";

            if (onBookmarksPage && card) {
                card.remove();
                const list = document.getElementById("post-list");
                if (list && !list.querySelector(".post-card")) {
                    list.innerHTML = `
                        <div class="empty-state">
                            <p>No bookmarks yet.</p>
                            <a href="/app/classwall" data-spa-link>Browse the class wall</a>
                        </div>`;
                }
            }
        }
    } catch (err) {
        window.AppUI?.showToast("Could not update bookmark", "error");
    }
}

function downloadAll(el) {
    const files = JSON.parse(el.dataset.files);
    files.forEach((f, i) => {
        setTimeout(() => {
            const a = document.createElement("a");
            a.href = `/download/${f.id}`;
            a.target = "_blank";
            document.body.appendChild(a);
            a.click();
            a.remove();
        }, i * 600);
    });
}

window.toggleBookmark = toggleBookmark;
window.downloadAll = downloadAll;
