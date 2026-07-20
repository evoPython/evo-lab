(function () {
    function openModal(modal) {
        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");
    }

    function closeModal(modal) {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");
    }

    async function toggleAssessmentArchive(button) {
        const enrollmentClassId = button.dataset.enrollmentClassId;
        if (!enrollmentClassId || button.disabled) {
            return;
        }

        const currentlyArchived = button.dataset.archived === "1";
        const archived = !currentlyArchived;
        const label = button.querySelector(".assessment-archive-toggle-label");
        const previousText = label ? label.textContent : "";

        button.disabled = true;
        button.classList.add("is-loading");
        button.setAttribute("aria-busy", "true");
        if (label) {
            label.textContent = archived ? "Archiving…" : "Unarchiving…";
        }

        try {
            const res = await fetch(`/api/assessments/${enrollmentClassId}/archive`, {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ archived }),
            });
            const data = await res.json();

            if (!res.ok) {
                throw new Error(data.error || "Could not update archive status.");
            }

            if (typeof window.spaInvalidateRoutes === "function") {
                window.spaInvalidateRoutes("assessments");
                window.spaInvalidateRoutes("assessment_detail");
            }

            if (typeof window.spaNavigate === "function") {
                const target = archived
                    ? "/app/assessments"
                    : `/app/assessments/${enrollmentClassId}`;
                window.spaNavigate(target, "");
            } else {
                window.location.href = archived ? "/app/assessments" : window.location.pathname;
            }
        } catch (error) {
            button.disabled = false;
            button.classList.remove("is-loading");
            button.removeAttribute("aria-busy");
            if (label) {
                label.textContent = previousText;
            }
            window.alert(error.message || "Could not update archive status.");
        }
    }

    function toggleAssessmentEntry(card) {
        if (!window.matchMedia("(max-width: 768px)").matches) {
            return;
        }

        const expanded = !card.classList.contains("is-expanded");
        card.classList.toggle("is-expanded", expanded);
        card.setAttribute("aria-expanded", expanded ? "true" : "false");
    }

    function toggleGradeComponent(row) {
        const componentId = row.dataset.gradeComponent;
        if (componentId === undefined) {
            return;
        }

        const table = row.closest(".grade-table");
        if (!table) {
            return;
        }

        const expanded = !row.classList.contains("is-expanded");
        row.classList.toggle("is-expanded", expanded);
        row.setAttribute("aria-expanded", String(expanded));

        table.querySelectorAll(`.grade-entry-row[data-grade-parent="${componentId}"]`).forEach((entryRow) => {
            entryRow.hidden = !expanded;
        });
    }

    document.addEventListener("click", (event) => {
        const archiveBtn = event.target.closest(".assessment-archive-toggle");
        if (archiveBtn) {
            event.preventDefault();
            toggleAssessmentArchive(archiveBtn);
            return;
        }

        const openBtn = event.target.closest("#grade-summary-open");
        if (openBtn) {
            const modal = document.getElementById("grade-summary-modal");
            if (modal) {
                openModal(modal);
            }
            return;
        }

        const componentRow = event.target.closest(".grade-component-row.has-entries");
        if (componentRow) {
            toggleGradeComponent(componentRow);
            return;
        }

        const entryCard = event.target.closest(".assessment-entry-collapsible");
        if (entryCard) {
            toggleAssessmentEntry(entryCard);
            return;
        }

        const closeEl = event.target.closest("[data-modal-close]");
        if (closeEl) {
            const modal = closeEl.closest(".modal");
            if (modal && modal.id === "grade-summary-modal") {
                closeModal(modal);
            }
        }
    });

    document.addEventListener("keydown", (event) => {
        const entryCard = event.target.closest?.(".assessment-entry-collapsible");
        if (entryCard && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            toggleAssessmentEntry(entryCard);
            return;
        }

        const componentRow = event.target.closest?.(".grade-component-row.has-entries");
        if (componentRow && (event.key === "Enter" || event.key === " ")) {
            event.preventDefault();
            toggleGradeComponent(componentRow);
            return;
        }

        if (event.key !== "Escape") {
            return;
        }

        const modal = document.getElementById("grade-summary-modal");
        if (modal && modal.classList.contains("is-open")) {
            closeModal(modal);
        }
    });
})();
