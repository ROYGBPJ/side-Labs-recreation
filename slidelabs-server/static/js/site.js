(function () {
  const toggle = document.querySelector(".nav-toggle");
  const menu = document.getElementById("nav-menu");
  if (toggle && menu) {
    toggle.addEventListener("click", () => {
      const open = menu.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });
  }
  const dd = document.querySelector(".dropdown");
  if (dd) {
    const btn = dd.querySelector(".dropdown-btn");
    const set = (v) => { dd.classList.toggle("open", v); btn.setAttribute("aria-expanded", String(v)); };
    btn.addEventListener("click", (e) => { e.stopPropagation(); set(!dd.classList.contains("open")); });
    document.addEventListener("click", (e) => { if (!dd.contains(e.target)) set(false); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") set(false); });
  }

  window.api = async function (url, opts) {
    try {
      const res = await fetch(url, opts);
      let data = null;
      const type = res.headers.get("Content-Type") || "";
      if (type.includes("application/json")) data = await res.json();
      return { ok: res.ok, status: res.status, data, res };
    } catch (_) {
      return { ok: false, status: 0, data: { error: "Network error. Check your connection and try again." } };
    }
  };
  window.postJSON = (url, body) => window.api(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

})();
