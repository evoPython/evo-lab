(function () {
    const modal = document.getElementById("approve-return-modal");
    const form = document.getElementById("approve-return-form");
    const studentLabel = document.getElementById("approve-return-student");
    const departureInput = document.getElementById("departure_datetime");

    if (!modal || !form) return;

    const approveUrlTemplate = form.action.replace(/\/0\/approve-return$/, "/PASS_ID/approve-return");

    function openModal(passId, studentName) {
        form.action = approveUrlTemplate.replace("PASS_ID", String(passId));
        studentLabel.textContent = studentName
            ? `Signing return slip for ${studentName} (pass #${passId})`
            : `Signing return slip for pass #${passId}`;

        if (!departureInput.value) {
            const now = new Date();
            now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
            departureInput.value = now.toISOString().slice(0, 16);
        }

        modal.classList.add("is-open");
        modal.setAttribute("aria-hidden", "false");
        document.body.classList.add("modal-open");
        departureInput.focus();
    }

    function closeModal() {
        modal.classList.remove("is-open");
        modal.setAttribute("aria-hidden", "true");
        document.body.classList.remove("modal-open");
    }

    document.addEventListener("click", (event) => {
        const btn = event.target.closest(".approve-return-btn");
        if (!btn) return;
        openModal(btn.dataset.passId, btn.dataset.studentName || "");
    });

    modal.querySelectorAll("[data-modal-close]").forEach((el) => {
        el.addEventListener("click", closeModal);
    });

    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && modal.classList.contains("is-open")) {
            closeModal();
        }
    });

    form.addEventListener("submit", () => {
        const submitBtn = form.querySelector('button[type="submit"]');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.textContent = "Submitting";
        }
    });
})();
