(() => {
  const storageKey = "tickethive-theme";
  const root = document.documentElement;
  const toggle = document.getElementById("theme-toggle");

  function updateButton(theme) {
    const isDark = theme === "dark";
    toggle.setAttribute("aria-label", `Switch to ${isDark ? "light" : "dark"} theme`);
    toggle.title = `Switch to ${isDark ? "light" : "dark"} theme`;
    toggle.querySelector(".theme-icon").textContent = isDark ? "☀" : "☾";
    toggle.querySelector(".theme-label").textContent = isDark ? "Light" : "Dark";
  }

  const activeTheme = root.getAttribute("data-bs-theme") || "light";
  updateButton(activeTheme);

  toggle.addEventListener("click", () => {
    const nextTheme = root.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-bs-theme", nextTheme);
    localStorage.setItem(storageKey, nextTheme);
    updateButton(nextTheme);
  });
})();
