const root = document.documentElement;
const themeButton = document.querySelector("[data-theme-toggle]");
let theme = "light";
try {
  theme = localStorage.getItem("lab-theme") === "dark" ? "dark" : "light";
} catch {
  /* Storage is optional. */
}

function setTheme(value) {
  root.dataset.theme = value;
  themeButton.setAttribute("aria-pressed", String(value === "dark"));
  themeButton.setAttribute(
    "aria-label",
    value === "dark" ? "Activer le thème clair" : "Activer le thème sombre",
  );
}
setTheme(theme);
themeButton.addEventListener("click", () => {
  theme = root.dataset.theme === "dark" ? "light" : "dark";
  setTheme(theme);
  try {
    localStorage.setItem("lab-theme", theme);
  } catch {
    /* Keep working without storage. */
  }
});

const search = document.querySelector("#service-search");
const clear = document.querySelector("[data-clear]");
const filters = [...document.querySelectorAll("[data-filter]")];
const groups = [...document.querySelectorAll("[data-group]")];
const services = [...document.querySelectorAll("[data-service]")];
const resultCount = document.querySelector("#result-count");
const empty = document.querySelector("#empty-results");
const normalize = (text) =>
  text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
let access = "all";

function filterServices() {
  const terms = normalize(search.value.trim()).split(/\s+/).filter(Boolean);
  let count = 0;
  for (const service of services) {
    const text = normalize(
      `${service.textContent} ${service.dataset.keywords}`,
    );
    const visible =
      (access === "all" || service.dataset.access === access) &&
      terms.every((term) => text.includes(term));
    service.hidden = !visible;
    if (visible) count++;
  }
  for (const group of groups) {
    group.hidden = ![...group.querySelectorAll("[data-service]")].some(
      (service) => !service.hidden,
    );
  }
  resultCount.textContent = `${count} service${count > 1 ? "s" : ""}`;
  empty.hidden = count !== 0;
  clear.hidden = search.value.length === 0;
}
search.addEventListener("input", filterServices);
clear.addEventListener("click", () => {
  search.value = "";
  filterServices();
  search.focus();
});
for (const button of filters) {
  button.addEventListener("click", () => {
    access = button.dataset.filter;
    for (const other of filters)
      other.setAttribute("aria-pressed", String(other === button));
    filterServices();
  });
}
document.querySelector("[data-reset]").addEventListener("click", () => {
  search.value = "";
  filters[0].click();
  search.focus();
});
document.addEventListener("keydown", (event) => {
  if (
    event.key === "/" &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.altKey &&
    !["INPUT", "TEXTAREA"].includes(document.activeElement.tagName) &&
    !document.activeElement.isContentEditable
  ) {
    event.preventDefault();
    search.focus();
  }
  if (event.key === "Escape" && document.activeElement === search) {
    search.value = "";
    filterServices();
    search.blur();
  }
});
document.querySelector(".finder").hidden = false;
filterServices();
