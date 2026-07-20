const COLLAPSE_HEIGHT = 160;

let lightboxImages = [];
let lightboxIndex = 0;
let lightboxReady = false;
let lightboxLoadToken = 0;

const imageCache = new Map();

function initPostCards() {
    document.querySelectorAll(".post-card:not([data-initialized])").forEach((card) => {
        card.dataset.initialized = "true";
        initPostCollapse(card);
    });
}

function initPostCollapse(card) {
    const content = card.querySelector(".post-collapsible-content");
    const toggle = card.querySelector(".post-toggle");

    if (!content || !toggle) {
        return;
    }

    const needsCollapse = content.scrollHeight > COLLAPSE_HEIGHT;

    if (!needsCollapse) {
        toggle.remove();
        return;
    }

    card.classList.add("is-collapsed");
    toggle.hidden = false;

    toggle.addEventListener("click", () => {
        const collapsed = card.classList.toggle("is-collapsed");
        toggle.textContent = collapsed ? "See more" : "Show less";
        toggle.setAttribute("aria-expanded", String(!collapsed));
    });
}

function getImagesFromGrid(grid) {
    return [...grid.querySelectorAll(".message-image-thumb")].map((btn) => ({
        src: btn.dataset.lightboxSrc || "",
        alt: btn.dataset.lightboxAlt || "Image",
    }));
}

function cleanImageUrl(url) {
    return (url || "").split("#")[0];
}

function preloadImage(url) {
    const clean = cleanImageUrl(url);
    if (!clean || imageCache.has(clean)) {
        return imageCache.get(clean);
    }

    const promise = new Promise((resolve) => {
        const img = new Image();
        img.decoding = "async";
        img.onload = () => resolve(clean);
        img.onerror = () => resolve(clean);
        img.src = clean;
    });

    imageCache.set(clean, promise);
    return promise;
}

function setLightboxLoading(isLoading) {
    const lightbox = document.getElementById("lightbox");
    if (!lightbox) {
        return;
    }

    lightbox.classList.toggle("is-loading", isLoading);
}

function initLightbox() {
    if (lightboxReady) {
        return;
    }

    const lightbox = document.getElementById("lightbox");
    if (!lightbox) {
        return;
    }

    lightboxReady = true;

    lightbox.addEventListener("click", (e) => {
        if (e.target.classList.contains("lightbox-backdrop")) {
            closeLightbox();
        }
    });

    lightbox.querySelector(".lightbox-prev").addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        stepLightbox(-1);
    });

    lightbox.querySelector(".lightbox-next").addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        stepLightbox(1);
    });

    lightbox.querySelector(".lightbox-download").addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        downloadLightboxImage();
    });

    lightbox.querySelector(".lightbox-panel").addEventListener("click", (e) => {
        e.stopPropagation();
    });

    document.addEventListener("click", (e) => {
        const thumb = e.target.closest(".message-image-thumb");
        if (!thumb) {
            return;
        }

        e.preventDefault();
        const grid = thumb.closest(".message-image-grid");
        if (!grid) {
            return;
        }

        const buttons = [...grid.querySelectorAll(".message-image-thumb")];
        const index = buttons.indexOf(thumb);
        openLightbox(getImagesFromGrid(grid), index);
    });

    document.addEventListener(
        "pointerenter",
        (e) => {
            const thumb = e.target.closest?.(".message-image-thumb");
            if (!thumb) {
                return;
            }

            const src = thumb.dataset.lightboxSrc;
            if (src) {
                preloadImage(src);
            }
        },
        true
    );

    document.addEventListener("keydown", (e) => {
        const activeLightbox = document.getElementById("lightbox");
        if (!activeLightbox || !activeLightbox.classList.contains("is-open")) {
            return;
        }

        if (e.key === "Escape") {
            e.preventDefault();
            closeLightbox();
        } else if (e.key === "ArrowLeft") {
            e.preventDefault();
            stepLightbox(-1);
        } else if (e.key === "ArrowRight") {
            e.preventDefault();
            stepLightbox(1);
        }
    });
}

function openLightbox(images, index) {
    const lightbox = document.getElementById("lightbox");
    const validImages = images.filter((img) => img.src);

    if (!lightbox || !validImages.length) {
        return;
    }

    lightboxImages = validImages.map((img) => ({ src: img.src, alt: img.alt || "Image" }));
    lightboxIndex = Math.min(Math.max(index, 0), lightboxImages.length - 1);
    renderLightboxImage();

    lightbox.classList.add("is-open");
    lightbox.setAttribute("aria-hidden", "false");
    document.body.classList.add("lightbox-open");
}

function closeLightbox() {
    const lightbox = document.getElementById("lightbox");
    if (!lightbox) {
        return;
    }

    lightboxLoadToken += 1;
    lightbox.classList.remove("is-open", "is-loading");
    lightbox.setAttribute("aria-hidden", "true");
    document.body.classList.remove("lightbox-open");

    const img = lightbox.querySelector(".lightbox-image");
    img.removeAttribute("src");
    img.alt = "";
    img.classList.remove("is-visible");

    lightboxImages = [];
    lightboxIndex = 0;
}

async function renderLightboxImage() {
    const lightbox = document.getElementById("lightbox");
    const img = lightbox.querySelector(".lightbox-image");
    const caption = lightbox.querySelector(".lightbox-caption");
    const downloadBtn = lightbox.querySelector(".lightbox-download");
    const prevBtn = lightbox.querySelector(".lightbox-prev");
    const nextBtn = lightbox.querySelector(".lightbox-next");
    const counter = lightbox.querySelector(".lightbox-counter");

    const current = lightboxImages[lightboxIndex];
    if (!current) {
        return;
    }

    const loadToken = ++lightboxLoadToken;
    const src = cleanImageUrl(current.src);

    caption.textContent = current.alt;
    downloadBtn.href = src;

    const filename = filenameFromUrl(current.src, current.alt);
    downloadBtn.download = filename;

    const multiple = lightboxImages.length > 1;
    prevBtn.hidden = !multiple;
    nextBtn.hidden = !multiple;
    counter.hidden = !multiple;
    counter.textContent = `${lightboxIndex + 1} / ${lightboxImages.length}`;

    setLightboxLoading(true);
    img.classList.remove("is-visible");

    await preloadImage(src);

    if (loadToken !== lightboxLoadToken) {
        return;
    }

    img.onload = () => {
        if (loadToken !== lightboxLoadToken) {
            return;
        }
        img.classList.add("is-visible");
        setLightboxLoading(false);
    };

    img.onerror = () => {
        if (loadToken !== lightboxLoadToken) {
            return;
        }
        img.classList.add("is-visible");
        setLightboxLoading(false);
    };

    if (img.src === src && img.complete && img.naturalWidth > 0) {
        img.classList.add("is-visible");
        setLightboxLoading(false);
    } else {
        img.src = src;
    }
}

function stepLightbox(delta) {
    if (lightboxImages.length <= 1) {
        return;
    }

    lightboxIndex = (lightboxIndex + delta + lightboxImages.length) % lightboxImages.length;
    renderLightboxImage();
}

function filenameFromUrl(url, fallback) {
    const cleanUrl = cleanImageUrl(url);

    try {
        const pathname = new URL(cleanUrl, window.location.origin).pathname;
        const base = pathname.split("/").pop();
        if (base && base.includes(".")) {
            return base;
        }
    } catch {
        /* use fallback */
    }

    const safe = (fallback || "image").replace(/[^\w.-]+/g, "_").slice(0, 80);
    return safe.includes(".") ? safe : `${safe}.jpg`;
}

async function downloadLightboxImage() {
    const current = lightboxImages[lightboxIndex];
    if (!current) {
        return;
    }

    const filename = filenameFromUrl(current.src, current.alt);
    const url = cleanImageUrl(current.src);

    try {
        const res = await fetch(url, { mode: "cors" });
        if (!res.ok) {
            throw new Error("fetch failed");
        }

        const blob = await res.blob();
        const objectUrl = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = objectUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(objectUrl);
    } catch {
        window.open(url, "_blank", "noopener");
    }
}

window.initPostCards = initPostCards;

document.addEventListener("DOMContentLoaded", () => {
    initLightbox();
    initPostCards();
});
