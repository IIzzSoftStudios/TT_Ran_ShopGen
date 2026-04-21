const THEME_STORAGE_KEY = "tt-theme";
const prefersDarkQuery = window.matchMedia("(prefers-color-scheme: dark)");

const getStoredTheme = () => {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY);
  } catch (err) {
    console.warn("Unable to read stored theme", err);
    return null;
  }
};

const storeTheme = (theme) => {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch (err) {
    console.warn("Unable to persist theme", err);
  }
};

const applyTheme = (theme) => {
  const isDark = theme === "dark";
  document.documentElement.classList.toggle("dark-mode", isDark);
  document.documentElement.dataset.theme = theme;

  const toggle = document.querySelector(".theme-toggle");
  if (toggle) {
    toggle.setAttribute("aria-pressed", String(isDark));
    toggle.textContent = isDark ? "☀ Light Mode" : "🌙 Dark Mode";
  }
};

const resolveTheme = () => {
  const stored = getStoredTheme();
  if (stored) {
    return stored;
  }
  return prefersDarkQuery.matches ? "dark" : "light";
};

const ensureToggleButton = () => {
  let toggle = document.querySelector(".theme-toggle");
  if (!toggle) {
    toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "theme-toggle";
    toggle.setAttribute("aria-label", "Toggle dark mode");
    toggle.setAttribute("aria-live", "polite");
    document.body.appendChild(toggle);
  }
  return toggle;
};

const watchSystemPreference = (callback) => {
  if (typeof prefersDarkQuery.addEventListener === "function") {
    prefersDarkQuery.addEventListener("change", callback);
  } else if (typeof prefersDarkQuery.addListener === "function") {
    prefersDarkQuery.addListener(callback);
  }
};

const initThemeToggle = () => {
  let activeTheme = resolveTheme();
  applyTheme(activeTheme);

  const toggle = ensureToggleButton();

  toggle.addEventListener("click", () => {
    const isDark = document.documentElement.classList.contains("dark-mode");
    activeTheme = isDark ? "dark" : "light";
    const nextTheme = isDark ? "light" : "dark";
    activeTheme = nextTheme;
    applyTheme(activeTheme);
    storeTheme(activeTheme);
  });

  watchSystemPreference((event) => {
    const matches = event.matches ?? prefersDarkQuery.matches;
    const stored = getStoredTheme();
    if (stored) {
      return;
    }
    activeTheme = matches ? "dark" : "light";
    applyTheme(activeTheme);
  });
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initThemeToggle);
} else {
  initThemeToggle();
}

