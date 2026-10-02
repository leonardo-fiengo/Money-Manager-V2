document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    const dark = document.documentElement.dataset.theme === "dark";
    const label = dark ? "Switch to light mode" : "Switch to dark mode";
    button.setAttribute("aria-label", label);
    button.title = label;
    button.addEventListener("click", () => {
        const theme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
        try { localStorage.setItem("money-manager-theme", theme); } catch (_) {}
        document.documentElement.dataset.theme = theme;
        window.location.reload();
    });
});
