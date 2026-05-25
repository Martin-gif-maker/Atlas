/* theme.js — light/dark toggle for Atlas.
 * Persists choice in localStorage and injects a sun/moon button into
 * either the app nav (when signed in) or the landing page topnav.
 */
(() => {
  const KEY = "atlas.theme";
  const root = document.documentElement;

  // Apply saved theme immediately to avoid a flash of the wrong colors.
  const saved = localStorage.getItem(KEY) || "dark";
  root.dataset.theme = saved;

  function toggle() {
    const next = root.dataset.theme === "light" ? "dark" : "light";
    root.dataset.theme = next;
    localStorage.setItem(KEY, next);
  }

  function injectButton() {
    if (document.querySelector(".theme-toggle")) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "theme-toggle";
    btn.title = "Toggle light / dark mode";
    btn.setAttribute("aria-label", "Toggle theme");
    btn.innerHTML = `
      <svg class="icon-sun" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="4"/>
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
      </svg>
      <svg class="icon-moon" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
      </svg>
    `;
    btn.addEventListener("click", toggle);

    const target =
      document.querySelector(".app-nav-right") ||
      document.querySelector(".nav-cta");
    if (target) target.insertBefore(btn, target.firstChild);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", injectButton);
  } else {
    injectButton();
  }
})();
