/*
 * script.js — VB Image AI Studio frontend controller
 * Async API calls, loading states, preview actions and session gallery.
 */

"use strict";

const TOKEN_KEY = "vb_image_studio_hf_token";
const $ = (id) => document.getElementById(id);

const state = {
  generating: false,
  current: null,
  gallery: [],
  timerId: null,
  startTime: 0,
};

const els = {
  prompt: $("promptInput"),
  charCount: $("charCount"),
  surprise: $("surpriseBtn"),
  clearPrompt: $("clearPromptBtn"),
  model: $("modelSelect"),
  style: $("styleSelect"),
  seed: $("seedInput"),
  randomSeed: $("randomSeedBtn"),
  batch: $("batchSelect"),
  enhance: $("enhanceToggle"),
  presets: document.querySelectorAll(".preset-btn"),
  tokenDetails: $("tokenDetails"),
  token: $("tokenInput"),
  showToken: $("showTokenBtn"),
  rememberToken: $("rememberTokenToggle"),
  clearToken: $("clearTokenBtn"),
  generate: $("generateBtn"),
  generateLabel: $("generateBtnLabel"),
  status: $("statusText"),
  timer: $("timerText"),
  stage: $("previewStage"),
  placeholder: $("previewPlaceholder"),
  image: $("previewImage"),
  skeleton: $("skeleton"),
  details: $("previewDetails"),
  detailPrompt: $("previewPrompt"),
  detailTags: $("previewTags"),
  note: $("previewNote"),
  download: $("downloadBtn"),
  copyPrompt: $("copyPromptBtn"),
  reuseSeed: $("reuseSeedBtn"),
  galleryGrid: $("galleryGrid"),
  galleryEmpty: $("galleryEmpty"),
  galleryCount: $("galleryCount"),
  refreshGallery: $("refreshGalleryBtn"),
  devBtn: $("devBtn"),
  footerDevBtn: $("footerDevBtn"),
  modal: $("devModal"),
  closeModal: $("closeDevModal"),
  toast: $("toast"),
  cursorGlow: $("cursorGlow"),
  heroRotator: $("heroRotator"),
  engineStatus: $("engineStatus"),
};

/* ----------------------------- Utilities ----------------------------- */

function randomSeed() {
  return Math.floor(Math.random() * 2147483647);
}

function toast(message, isError = false) {
  els.toast.textContent = message;
  els.toast.classList.toggle("error", isError);
  els.toast.hidden = false;
  clearTimeout(toast.timeoutId);
  toast.timeoutId = setTimeout(() => { els.toast.hidden = true; }, 4200);
}

async function fetchJSON(url, options = {}) {
  const response = await fetch(url, options);
  let payload;
  try {
    payload = await response.json();
  } catch (_error) {
    throw new Error("The server returned an invalid response.");
  }
  if (!response.ok || payload.status === "error") {
    throw new Error(payload.error || `Request failed (HTTP ${response.status}).`);
  }
  return payload;
}

function updateCharCount() {
  els.charCount.textContent = `${els.prompt.value.length} / 2000`;
}

function updateEngineStatus() {
  const hfSelected = els.model.value.startsWith("hf-");
  const hasToken = Boolean(els.token.value.trim());
  const label = els.engineStatus.querySelector("span");
  if (hfSelected && hasToken) {
    label.nextSibling.textContent = " Hugging Face token active";
    els.engineStatus.classList.remove("warn");
  } else if (hfSelected) {
    label.nextSibling.textContent = " No HF token · keyless fallback";
    els.engineStatus.classList.add("warn");
  } else {
    label.nextSibling.textContent = " Keyless engine ready";
    els.engineStatus.classList.remove("warn");
  }
}

/* --------------------------- Timer control --------------------------- */

function startTimer() {
  stopTimer();
  state.startTime = Date.now();
  els.timer.textContent = "0.0s";
  state.timerId = setInterval(() => {
    const elapsed = (Date.now() - state.startTime) / 1000;
    els.timer.textContent = `${elapsed.toFixed(1)}s`;
  }, 100);
}

function stopTimer() {
  if (state.timerId) clearInterval(state.timerId);
  state.timerId = null;
}

/* -------------------------- Token settings --------------------------- */

function loadToken() {
  try {
    const saved = localStorage.getItem(TOKEN_KEY) || "";
    els.token.value = saved;
    if (saved) {
      els.tokenDetails.open = true;
      els.token.type = "password";
      els.showToken.textContent = "👁";
    }
  } catch (_error) {
    /* localStorage may be disabled; the app still works keylessly. */
  }
}

function saveToken() {
  try {
    if (els.rememberToken.checked && els.token.value.trim()) {
      localStorage.setItem(TOKEN_KEY, els.token.value.trim());
    } else {
      localStorage.removeItem(TOKEN_KEY);
    }
  } catch (_error) {
    /* Ignore storage errors. */
  }
}

/* ---------------------------- Generation ----------------------------- */

function setLoading(loading) {
  state.generating = loading;
  els.generate.disabled = loading;
  els.generateLabel.textContent = loading ? "Generating…" : "Generate image";
  els.skeleton.hidden = !loading;
  els.placeholder.hidden = loading || Boolean(state.current);
  if (loading) {
    els.stage.classList.remove("has-image");
    els.image.hidden = true;
  }
}

async function generateAll() {
  const rawPrompt = els.prompt.value.trim();
  if (!rawPrompt) {
    toast("Please describe the image you want to generate.", true);
    els.prompt.focus();
    return;
  }

  const width = Number(document.querySelector(".preset-btn.active")?.dataset.width || 1024);
  const height = Number(document.querySelector(".preset-btn.active")?.dataset.height || 1024);
  const count = Math.max(1, Math.min(4, Number(els.batch.value) || 1));
  const baseSeed = Number(els.seed.value) || 0;
  const token = els.token.value.trim();

  const body = {
    prompt: rawPrompt,
    model: els.model.value,
    style: els.style.value,
    width,
    height,
    seed: baseSeed,
    enhance: els.enhance.checked,
    hf_token: token,
  };

  setLoading(true);
  startTimer();

  let succeeded = 0;
  for (let index = 0; index < count; index += 1) {
    els.status.textContent = count > 1
      ? `Generating image ${index + 1} of ${count}…`
      : "Contacting free AI engine…";
    try {
      const requestBody = { ...body, seed: baseSeed === 0 ? 0 : baseSeed + index };
      const result = await fetchJSON("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody),
      });
      showPreview(result);
      succeeded += 1;
      await loadGallery();
    } catch (error) {
      toast(error.message || "Generation failed. Please try again.", true);
      if (index === 0 && count > 1) break;
    }
  }

  stopTimer();
  setLoading(false);
  els.status.textContent = succeeded
    ? `${succeeded} image${succeeded > 1 ? "s" : ""} generated successfully.`
    : "Generation failed — check the message and try again.";
}

/* --------------------------- Preview panel --------------------------- */

function showPreview(item) {
  state.current = item;
  els.image.src = item.image_url;
  els.image.alt = `Generated image for: ${(item.prompt || "").slice(0, 100)}`;
  els.image.hidden = false;
  els.placeholder.hidden = true;
  els.stage.classList.add("has-image");

  els.detailPrompt.textContent = item.prompt_used || item.prompt || "";
  els.detailTags.replaceChildren();
  const tags = [
    item.model_used || item.model || "",
    `${item.width || ""}×${item.height || ""}`,
    `seed ${item.seed_used ?? item.seed ?? "—"}`,
    item.engine || "",
  ].filter(Boolean);
  tags.forEach((tagText) => {
    const chip = document.createElement("span");
    chip.textContent = String(tagText);
    els.detailTags.appendChild(chip);
  });
  els.details.hidden = false;

  const noteText = item.note || "";
  els.note.textContent = noteText;
  els.note.hidden = !noteText;

  els.download.disabled = false;
  els.copyPrompt.disabled = false;
  els.reuseSeed.disabled = false;
}

function clearPreview() {
  state.current = null;
  els.image.removeAttribute("src");
  els.image.hidden = true;
  els.placeholder.hidden = false;
  els.stage.classList.remove("has-image");
  els.details.hidden = true;
  els.note.hidden = true;
  els.download.disabled = true;
  els.copyPrompt.disabled = true;
  els.reuseSeed.disabled = true;
}

/* ------------------------------ Gallery ------------------------------ */

async function loadGallery() {
  try {
    const data = await fetchJSON("/api/gallery?limit=60");
    state.gallery = data.images || [];
  } catch (error) {
    toast(error.message, true);
    return;
  }
  renderGallery();
}

function renderGallery() {
  els.galleryGrid.replaceChildren();
  els.galleryCount.textContent = `${state.gallery.length} image${state.gallery.length === 1 ? "" : "s"}`;
  els.galleryEmpty.hidden = state.gallery.length > 0;

  const activeName = state.current?.filename || "";

  state.gallery.forEach((image) => {
    const card = document.createElement("article");
    card.className = "gallery-card";
    if (activeName && image.filename === activeName) card.classList.add("active");

    const openButton = document.createElement("button");
    openButton.type = "button";
    openButton.className = "gallery-card-button";
    openButton.title = "Click to preview";

    const thumb = document.createElement("img");
    thumb.src = image.image_url;
    thumb.alt = image.prompt || "Generated image";
    thumb.loading = "lazy";

    const body = document.createElement("div");
    body.className = "gallery-card-body";

    const caption = document.createElement("p");
    caption.textContent = image.original_prompt || image.prompt || "Untitled prompt";

    const meta = document.createElement("small");
    meta.textContent = `${image.model || image.engine || "AI"} · seed ${image.seed ?? "—"}`;

    body.append(caption, meta);
    openButton.append(thumb, body);
    openButton.addEventListener("click", () => {
      showPreview({ ...image, prompt_used: image.prompt });
      els.status.textContent = "Previewing an image from your gallery.";
    });

    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "gallery-delete";
    deleteButton.title = "Delete image";
    deleteButton.textContent = "✕";
    deleteButton.addEventListener("click", async () => {
      if (!window.confirm("Delete this image permanently?")) return;
      try {
        await fetchJSON(`/api/gallery/${encodeURIComponent(image.filename)}`, { method: "DELETE" });
        if (state.current?.filename === image.filename) clearPreview();
        toast("Image deleted.");
        await loadGallery();
      } catch (error) {
        toast(error.message, true);
      }
    });

    card.append(openButton, deleteButton);
    els.galleryGrid.appendChild(card);
  });
}

/* --------------------------- Modal control --------------------------- */

function openModal() {
  els.modal.hidden = false;
  els.closeModal.focus();
}

function closeModal() {
  els.modal.hidden = true;
}

/* -------------------------- Event listeners -------------------------- */

els.prompt.addEventListener("input", updateCharCount);

els.surprise.addEventListener("click", () => {
  els.prompt.value = SUGGESTED_PROMPTS[Math.floor(Math.random() * SUGGESTED_PROMPTS.length)];
  updateCharCount();
  els.prompt.focus();
});

els.clearPrompt.addEventListener("click", () => {
  els.prompt.value = "";
  updateCharCount();
  els.prompt.focus();
});

els.presets.forEach((button) => {
  button.addEventListener("click", () => {
    els.presets.forEach((other) => other.classList.remove("active"));
    button.classList.add("active");
  });
});

els.randomSeed.addEventListener("click", () => { els.seed.value = String(randomSeed()); });

els.showToken.addEventListener("click", () => {
  const visible = els.token.type === "text";
  els.token.type = visible ? "password" : "text";
  els.showToken.textContent = visible ? "👁" : "🙈";
});

els.token.addEventListener("input", () => { saveToken(); updateEngineStatus(); });
els.model.addEventListener("change", updateEngineStatus);
els.rememberToken.addEventListener("change", saveToken);
els.clearToken.addEventListener("click", () => {
  els.token.value = "";
  try { localStorage.removeItem(TOKEN_KEY); } catch (_error) { /* ignore */ }
  toast("Stored API token removed.");
});

els.generate.addEventListener("click", generateAll);

els.download.addEventListener("click", () => {
  if (!state.current?.image_url) return;
  const link = document.createElement("a");
  link.href = state.current.image_url;
  link.download = state.current.filename || "vb-image.png";
  document.body.appendChild(link);
  link.click();
  link.remove();
});

els.copyPrompt.addEventListener("click", async () => {
  const text = state.current?.prompt_used || state.current?.prompt || "";
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    toast("Prompt copied to clipboard.");
  } catch (_error) {
    const temporary = document.createElement("textarea");
    temporary.value = text;
    document.body.appendChild(temporary);
    temporary.select();
    document.execCommand("copy");
    temporary.remove();
    toast("Prompt copied to clipboard.");
  }
});

els.reuseSeed.addEventListener("click", () => {
  if (state.current?.seed_used === undefined && state.current?.seed === undefined) return;
  els.seed.value = String(state.current.seed_used ?? state.current.seed);
  toast("Seed loaded into the controls.");
  els.seed.scrollIntoView({ behavior: "smooth", block: "center" });
});

els.refreshGallery.addEventListener("click", loadGallery);
els.devBtn.addEventListener("click", openModal);
els.footerDevBtn.addEventListener("click", openModal);
els.closeModal.addEventListener("click", closeModal);

els.modal.addEventListener("click", (event) => {
  if (event.target.hasAttribute("data-close-modal")) closeModal();
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !els.modal.hidden) closeModal();
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !state.generating) {
    event.preventDefault();
    generateAll();
  }
});

/* ---------------------- Dynamic interface effects -------------------- */

function initCursorGlow() {
  if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches) return;
  let frame = 0;
  document.body.classList.add("has-pointer");
  window.addEventListener("mousemove", (event) => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      document.documentElement.style.setProperty("--mx", `${event.clientX}px`);
      document.documentElement.style.setProperty("--my", `${event.clientY}px`);
      frame = 0;
    });
  });
}

function initRevealAndCounters() {
  const targets = document.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) {
    targets.forEach((node) => node.classList.add("visible"));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add("visible");
      entry.target.querySelectorAll("[data-count]").forEach((node) => countUp(node));
      observer.unobserve(entry.target);
    });
  }, { threshold: 0.12 });
  targets.forEach((node) => observer.observe(node));
}

function countUp(node) {
  const target = Number(node.dataset.count || 0);
  const suffix = node.dataset.suffix || "";
  const started = performance.now();
  const duration = 1100;
  function step(now) {
    const progress = Math.min((now - started) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    node.textContent = `${Math.round(target * eased)}${suffix}`;
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function initRotator() {
  const phrases = [
    "cinematic portraits",
    "neon cityscapes",
    "dreamy product shots",
    "fantasy worlds",
    "editorial photography",
  ];
  let index = 0;
  setInterval(() => {
    els.heroRotator.classList.add("fade");
    setTimeout(() => {
      index = (index + 1) % phrases.length;
      els.heroRotator.textContent = phrases[index];
      els.heroRotator.classList.remove("fade");
    }, 260);
  }, 3200);
}

/* ------------------------------- Init -------------------------------- */

const SUGGESTED_PROMPTS = [
  "a quiet lighthouse at sunrise with waves crashing against the rocks",
  "a futuristic cyberpunk street market in the rain at night",
  "an astronaut sitting on a wooden chair in a vast lavender field",
  "a cozy bookshop interior with warm golden light and tall bookshelves",
  "a majestic snow leopard standing on a cliff in the Himalayas",
  "a vintage sports car parked in front of a neon motel at dusk",
  "a floating crystal island above a sea of clouds at golden hour",
  "a robotic gardener tending to glowing flowers in a glass greenhouse",
];

els.seed.value = String(randomSeed());
updateCharCount();
loadToken();
updateEngineStatus();
initCursorGlow();
initRevealAndCounters();
initRotator();
loadGallery();
