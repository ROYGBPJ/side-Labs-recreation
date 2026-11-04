(function () {
  const root = document.querySelector("[data-tool]");
  if (!root) return;
  const tool = root.dataset.tool;
  const form = document.getElementById("tool-form");
  const submit = document.getElementById("submit");
  const errBox = document.getElementById("error");
  const result = document.getElementById("result");
  const rights = document.getElementById("rights");
  const labelText = submit.textContent;

  const el = (tag, attrs, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) { if (k === "class") n.className = v; else if (k === "text") n.textContent = v; else n.setAttribute(k, v); }
    kids.forEach((c) => n.append(c));
    return n;
  };
  const showError = (m) => { errBox.textContent = m; errBox.hidden = false; };
  const clearError = () => { errBox.hidden = true; };
  const busy = (on, text) => {
    submit.disabled = on;
    submit.replaceChildren(...(on ? [el("span", { class: "spinner", "aria-hidden": "true" }), document.createTextNode(text || "Working...")] : [document.createTextNode(labelText)]));
  };
  const fmtSize = (b) => (b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB");
  const fmtDur = (s) => (s ? Math.floor(s / 60) + ":" + String(Math.floor(s % 60)).padStart(2, "0") : "");

  function downloadCard(title, data, extra) {
    return el("div", { class: "result-card" },
      el("h2", { text: title }),
      el("p", { text: extra || "" }),
      el("a", { class: "btn btn-primary", href: data.url, download: data.filename, text: "Save " + data.filename + " (" + fmtSize(data.size || 0) + ")" }));
  }

  function needRights() {
    if (!rights.checked) { showError("Confirm that you have the right to use this content."); return true; }
    return false;
  }

  if (tool === "video-downloader") {
    form.addEventListener("submit", async (e) => {
      e.preventDefault(); clearError(); result.replaceChildren();
      const url = form.url.value.trim();
      if (!url || !form.url.checkValidity()) return showError("Paste a valid video link (starting with http:// or https://).");
      if (needRights()) return;
      busy(true, "Fetching video...");
      const r = await postJSON("/api/video/info", { url, confirm_rights: true });
      busy(false);
      if (!r.ok) return showError(r.data && r.data.error || "Could not read that link.");
      const d = r.data;
      const sel = el("select", { id: "quality", "aria-label": "Quality" }, el("option", { value: "best", text: "Best available" }));
      d.heights.forEach((h) => sel.append(el("option", { value: String(h), text: h + "p" })));
      sel.append(el("option", { value: "audio", text: "Audio only (MP3)" }));
      const dl = el("button", { class: "btn btn-primary", type: "button", text: "Download" });
      const out = el("div", { "aria-live": "polite" });
      dl.addEventListener("click", async () => {
        dl.disabled = true; dl.textContent = "Downloading..."; out.replaceChildren();
        const res = await postJSON("/api/video/download", { url, quality: sel.value, confirm_rights: true });
        dl.disabled = false; dl.textContent = "Download";
        if (!res.ok) return out.replaceChildren(el("p", { class: "alert", role: "alert", text: res.data && res.data.error || "Download failed." }));
        out.replaceChildren(downloadCard("Ready", res.data));
      });
      const thumb = d.thumbnail ? el("img", { src: d.thumbnail, alt: "", referrerpolicy: "no-referrer" }) : el("div");
      result.replaceChildren(el("div", { class: "result-card" }, el("div", { class: "vid" }, thumb,
        el("div", {}, el("h2", { text: d.title }), el("p", { text: [d.uploader, fmtDur(d.duration), d.site].filter(Boolean).join(" · ") }),
          el("div", { class: "vid-actions" }, sel, dl), out))));
    });
  }

  if (tool === "tiktok-image-downloader") {
    form.addEventListener("submit", async (e) => {
      e.preventDefault(); clearError(); result.replaceChildren();
      const url = form.url.value.trim();
      if (!url || !form.url.checkValidity()) return showError("Paste a valid TikTok Shop product link.");
      if (needRights()) return;
      busy(true, "Finding images...");
      const r = await postJSON("/api/images/extract", { url, confirm_rights: true });
      busy(false);
      if (!r.ok) return showError(r.data && r.data.error || "Could not load images.");
      const grid = el("div", { class: "img-grid" });
      r.data.images.forEach((im, i) => {
        const cb = el("input", { type: "checkbox", checked: "", "aria-label": "Select image " + (i + 1) }); cb.dataset.token = im.token;
        grid.append(el("div", { class: "img-item" }, el("label", {}, cb),
          el("img", { src: "/api/images/fetch?t=" + encodeURIComponent(im.token), alt: "Product image " + (i + 1), loading: "lazy" }),
          el("a", { href: "/api/images/fetch?download=1&t=" + encodeURIComponent(im.token), text: "Download" })));
      });
      const zip = el("button", { class: "btn btn-primary", type: "button", text: "Download selected as ZIP" });
      const out = el("p", { "aria-live": "polite" });
      zip.addEventListener("click", async () => {
        const tokens = [...grid.querySelectorAll("input:checked")].map((c) => c.dataset.token);
        if (!tokens.length) return out.replaceChildren(el("span", { class: "alert", role: "alert", text: "Select at least one image." }));
        zip.disabled = true; zip.textContent = "Preparing ZIP...";
        const res = await window.api("/api/images/zip", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tokens }) });
        zip.disabled = false; zip.textContent = "Download selected as ZIP";
        if (!res.ok) return out.replaceChildren(el("span", { class: "alert", role: "alert", text: res.data && res.data.error || "ZIP failed." }));
        const blob = await res.res.blob();
        const a = el("a", { href: URL.createObjectURL(blob), download: "product-images.zip" });
        document.body.append(a); a.click(); a.remove();
        out.textContent = "ZIP downloaded.";
      });
      result.replaceChildren(el("div", { class: "result-card" }, el("h2", { text: r.data.count + " images found" }), grid, zip, out));
    });
  }

  if (tool === "notebooklm-watermark-remover") {
    const input = document.getElementById("file");
    const drop = document.getElementById("drop");
    const hint = document.getElementById("drop-hint");
    input.addEventListener("change", () => { hint.textContent = input.files[0] ? input.files[0].name : "Choose a file or drop it here (max 50 MB)"; });
    ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.add("over")));
    ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("over")));
    form.addEventListener("submit", async (e) => {
      e.preventDefault(); clearError(); result.replaceChildren();
      const f = input.files[0];
      if (!f) return showError("Choose a PPTX or PDF file.");
      if (!/\.(pptx|pdf)$/i.test(f.name)) return showError("Only .pptx and .pdf files are supported.");
      if (f.size > 50 * 1024 * 1024) return showError("File is larger than 50 MB.");
      if (needRights()) return;
      const fd = new FormData(); fd.append("file", f); fd.append("confirm_rights", "true");
      busy(true, "Removing watermark...");
      const r = await window.api("/api/watermark", { method: "POST", body: fd });
      busy(false);
      if (!r.ok) return showError(r.data && r.data.error || "Could not process that file.");
      const d = r.data;
      result.replaceChildren(el("div", { class: "result-card" }, el("h2", { text: "Done" }),
        el("p", { text: "Removed " + d.removed + " watermark element" + (d.removed === 1 ? "" : "s") + "." }),
        el("a", { class: "btn btn-primary", href: d.url, download: d.filename, text: "Download " + d.filename })));
    });
  }
})();
