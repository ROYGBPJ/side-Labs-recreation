/* Browser-only versions of the three tools (no server). Used by the static export. */
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
  const needRights = () => { if (!rights.checked) { showError("Confirm that you have the right to use this content."); return true; } return false; };
  const saveBlob = (blob, name) => {
    const a = el("a", { href: URL.createObjectURL(blob), download: name });
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
  };
  const fmtSize = (b) => (b > 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB");
  const CORS_MSG = "Your browser was blocked from reading that link (the site doesn't allow it). ";

  // ---------------- Video: direct file links ----------------
  if (tool === "video-downloader") {
    form.addEventListener("submit", async (e) => {
      e.preventDefault(); clearError(); result.replaceChildren();
      const url = form.url.value.trim();
      if (!url || !form.url.checkValidity()) return showError("Paste a direct link to a video or audio file (starting with http:// or https://).");
      if (needRights()) return;
      busy(true, "Downloading...");
      try {
        const res = await fetch(url);
        if (!res.ok) throw new Error("Server returned status " + res.status + ".");
        const type = (res.headers.get("Content-Type") || "").split(";")[0];
        if (type.startsWith("text/") || type.includes("html") || type.includes("json")) throw new Error("That link is a web page, not a video file. Paste the direct link to the media file.");
        const blob = await res.blob();
        let name = decodeURIComponent((new URL(url).pathname.split("/").pop() || "video").replace(/[^\w.\- ]+/g, "_")) || "video";
        if (!/\.\w{2,4}$/.test(name)) name += type.startsWith("audio/") ? ".mp3" : ".mp4";
        saveBlob(blob, name);
        result.replaceChildren(el("div", { class: "result-card" }, el("h2", { text: "Saved" }), el("p", { text: name + " (" + fmtSize(blob.size) + ") was downloaded." })));
      } catch (err) {
        const blocked = err instanceof TypeError;
        showError(blocked ? CORS_MSG + "Sites like YouTube and TikTok can't be downloaded without the server version of this tool. Direct media links on sites that allow cross-origin downloads still work." : err.message);
      }
      busy(false);
    });
  }

  // ---------------- Images: link, page source or image links ----------------
  if (tool === "tiktok-image-downloader") {
    const IMG_RE = /https?:\/\/[^"'\s<>\\]+?\.(?:jpe?g|png|webp)(?:[~?][^"'\s<>\\]*)?/gi;
    const SKIP = ["avatar", "logo", "icon", "emoji", "sprite", "favicon"];
    function extract(text, base) {
      const found = [];
      const doc = new DOMParser().parseFromString(text, "text/html");
      const abs = (u) => { try { return new URL(u, base || undefined).href; } catch (_) { return null; } };
      doc.querySelectorAll('meta[property="og:image"]').forEach((m) => found.push(abs(m.getAttribute("content"))));
      doc.querySelectorAll("img").forEach((i) => { const s = i.getAttribute("src") || i.getAttribute("data-src"); if (s && !s.startsWith("data:")) found.push(abs(s)); });
      const blob = text.replace(/\\u002F/g, "/").replace(/\\\//g, "/");
      (blob.match(IMG_RE) || []).forEach((u) => found.push(u));
      const best = new Map();
      for (const u of found) {
        if (!u || SKIP.some((s) => u.toLowerCase().includes(s))) continue;
        const key = u.split(/[~?]/)[0];
        if (!best.has(key) || u.length < best.get(key).length) best.set(key, u);
      }
      return [...best.values()].slice(0, 60);
    }
    const SRC_MSG = CORS_MSG + "Open the product page, press Ctrl+U (Cmd+Option+U on Mac) to view the page source, copy everything and paste it into the box above.";
    form.addEventListener("submit", async (e) => {
      e.preventDefault(); clearError(); result.replaceChildren();
      const input = form.url.value.trim();
      if (!input) return showError("Paste a product link, the page source, or image links.");
      if (needRights()) return;
      busy(true, "Finding images...");
      let text = input, base = null;
      const single = /^https?:\/\/\S+$/.test(input);
      if (single && !/\.(jpe?g|png|webp)([?~]|$)/i.test(input)) {
        try {
          const res = await fetch(input);
          if (!res.ok) throw new Error("status " + res.status);
          text = await res.text(); base = input;
        } catch (_) { busy(false); return showError(SRC_MSG); }
      }
      const urls = extract(text, base);
      busy(false);
      if (!urls.length) return showError("No product images were found in that text.");
      const grid = el("div", { class: "img-grid" });
      urls.forEach((u, i) => {
        const cb = el("input", { type: "checkbox", checked: "", "aria-label": "Select image " + (i + 1) }); cb.dataset.url = u;
        const dl = el("a", { href: u, target: "_blank", rel: "noopener", text: "Download" });
        dl.addEventListener("click", async (ev) => {
          ev.preventDefault();
          try { const r = await fetch(u); if (!r.ok) throw 0; saveBlob(await r.blob(), "product-image-" + (i + 1) + "." + (u.split(/[~?]/)[0].split(".").pop() || "jpg")); }
          catch (_) { window.open(u, "_blank", "noopener"); }
        });
        grid.append(el("div", { class: "img-item" }, el("label", {}, cb), el("img", { src: u, alt: "Product image " + (i + 1), loading: "lazy", referrerpolicy: "no-referrer" }), dl));
      });
      const zip = el("button", { class: "btn btn-primary", type: "button", text: "Download selected as ZIP" });
      const out = el("p", { "aria-live": "polite" });
      zip.addEventListener("click", async () => {
        const sel = [...grid.querySelectorAll("input:checked")].map((c) => c.dataset.url);
        if (!sel.length) return out.replaceChildren(el("span", { class: "alert", role: "alert", text: "Select at least one image." }));
        zip.disabled = true; zip.textContent = "Preparing ZIP...";
        const z = new JSZip(); let ok = 0;
        await Promise.all(sel.map(async (u, i) => {
          try { const r = await fetch(u); if (!r.ok) throw 0; z.file("product-image-" + String(i + 1).padStart(2, "0") + "." + (u.split(/[~?]/)[0].split(".").pop() || "jpg"), await r.blob()); ok++; } catch (_) {}
        }));
        zip.disabled = false; zip.textContent = "Download selected as ZIP";
        if (!ok) return out.replaceChildren(el("span", { class: "alert", role: "alert", text: "The browser couldn't fetch these images for zipping (the host blocks it). Use each image's Download link instead." }));
        saveBlob(await z.generateAsync({ type: "blob" }), "product-images.zip");
        out.textContent = ok + " of " + sel.length + " images zipped.";
      });
      result.replaceChildren(el("div", { class: "result-card" }, el("h2", { text: urls.length + " images found" }), grid, zip, out));
    });
  }

  // ---------------- Watermark: PPTX in the browser ----------------
  if (tool === "notebooklm-watermark-remover") {
    const input = document.getElementById("file");
    const drop = document.getElementById("drop");
    const hint = document.getElementById("drop-hint");
    input.addEventListener("change", () => { hint.textContent = input.files[0] ? input.files[0].name : "Choose a .pptx file or drop it here"; });
    ["dragenter", "dragover"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.add("over")));
    ["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, () => drop.classList.remove("over")));

    const P = "http://schemas.openxmlformats.org/presentationml/2006/main";
    const A = "http://schemas.openxmlformats.org/drawingml/2006/main";
    const R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
    const parse = (s) => new DOMParser().parseFromString(s, "application/xml");
    const isCornerPic = (pic, sw, sh) => {
      const off = pic.getElementsByTagNameNS(A, "off")[0], ext = pic.getElementsByTagNameNS(A, "ext")[0];
      if (!off || !ext) return false;
      const x = +off.getAttribute("x"), y = +off.getAttribute("y"), w = +ext.getAttribute("cx"), h = +ext.getAttribute("cy");
      return w * h < 0.06 * sw * sh && x + w / 2 > 0.6 * sw && y + h / 2 > 0.8 * sh;
    };
    const hasMark = (sp) => [...sp.getElementsByTagNameNS(A, "t")].some((t) => t.textContent.toLowerCase().includes("notebooklm"));
    const relsOf = async (zip, path) => {
      const f = zip.file(path.replace(/([^/]+)$/, "_rels/$1.rels"));
      const map = {};
      if (f) parse(await f.async("string")).querySelectorAll("Relationship").forEach((r) => { map[r.getAttribute("Id")] = r.getAttribute("Target"); });
      return map;
    };
    const picKey = async (zip, path, pic) => {
      const blip = pic.getElementsByTagNameNS(A, "blip")[0];
      const id = blip && blip.getAttributeNS(R, "embed");
      return id ? (await relsOf(zip, path))[id] || null : null;
    };

    async function cleanPptx(file) {
      const zip = await JSZip.loadAsync(await file.arrayBuffer());
      const names = Object.keys(zip.files);
      const by = (re) => names.filter((n) => re.test(n));
      const slides = by(/^ppt\/slides\/slide\d+\.xml$/), others = by(/^ppt\/slide(Layouts\/slideLayout|Masters\/slideMaster)\d+\.xml$/);
      const sz = parse(await zip.file("ppt/presentation.xml").async("string")).getElementsByTagNameNS(P, "sldSz")[0];
      const sw = +sz.getAttribute("cx"), sh = +sz.getAttribute("cy");
      const docs = {}, counts = {};
      for (const path of [...slides, ...others]) docs[path] = parse(await zip.file(path).async("string"));
      for (const path of slides) {
        const seen = new Set();
        for (const pic of docs[path].getElementsByTagNameNS(P, "pic")) if (isCornerPic(pic, sw, sh)) { const k = await picKey(zip, path, pic); if (k) seen.add(k); }
        seen.forEach((k) => { counts[k] = (counts[k] || 0) + 1; });
      }
      const threshold = Math.max(2, Math.ceil(slides.length / 2));
      let removed = 0;
      for (const path of [...slides, ...others]) {
        const doc = docs[path]; let changed = false;
        for (const sp of [...doc.getElementsByTagNameNS(P, "sp")]) if (hasMark(sp)) { sp.parentNode.removeChild(sp); removed++; changed = true; }
        for (const pic of [...doc.getElementsByTagNameNS(P, "pic")]) {
          if (!isCornerPic(pic, sw, sh)) continue;
          const k = await picKey(zip, path, pic);
          if (k && (counts[k] || 0) >= threshold) { pic.parentNode.removeChild(pic); removed++; changed = true; }
        }
        if (changed) zip.file(path, new XMLSerializer().serializeToString(doc));
      }
      if (!removed) return null;
      return { blob: await zip.generateAsync({ type: "blob", compression: "DEFLATE" }), removed };
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault(); clearError(); result.replaceChildren();
      const f = input.files[0];
      if (!f) return showError("Choose a .pptx file.");
      if (/\.pdf$/i.test(f.name)) return showError("PDF files need the server version of this tool. In NotebookLM, export as PPTX instead.");
      if (!/\.pptx$/i.test(f.name)) return showError("Only .pptx files are supported.");
      if (needRights()) return;
      busy(true, "Removing watermark...");
      try {
        const out = await cleanPptx(f);
        if (!out) { showError("No NotebookLM watermark was detected. If it is baked into the slide images, this tool can't remove it."); }
        else {
          const name = f.name.replace(/\.pptx$/i, "") + "-clean.pptx";
          const a = el("a", { class: "btn btn-primary", href: URL.createObjectURL(out.blob), download: name, text: "Download " + name });
          result.replaceChildren(el("div", { class: "result-card" }, el("h2", { text: "Done" }), el("p", { text: "Removed " + out.removed + " watermark element" + (out.removed === 1 ? "" : "s") + ". Your file never left your computer." }), a));
        }
      } catch (_) { showError("This file couldn't be read. Make sure it is a valid, unencrypted .pptx export."); }
      busy(false);
    });
  }
})();
