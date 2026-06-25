// AFAC image browser frontend.
// State is held in module-level consts; we re-render the sidebar on tab change.

const state = {
  manifest: null,            // full manifest from /api/manifest
  currentSubset: null,       // subset key like "train_long"
  currentImages: [],         // filtered list (after search)
  currentIndex: -1,          // index into currentImages (-1 = none selected)
  searchQuery: "",
};

// DOM references
const $tabs = document.getElementById("tabs");
const $sidebarHeader = document.getElementById("sidebar-header");
const $thumbs = document.getElementById("thumbs");
const $searchInput = document.getElementById("search-input");
const $filename = document.getElementById("filename");
const $fileMeta = document.getElementById("file-meta");
const $mainImage = document.getElementById("main-image");
const $positionInfo = document.getElementById("position-info");
const $errorOverlay = document.getElementById("error-overlay");

async function loadManifest() {
  const resp = await fetch("/api/manifest");
  if (!resp.ok) {
    document.getElementById("app").innerHTML =
      '<div style="padding:40px;text-align:center">无法加载 manifest。请先运行 <code>python src/gen_thumbs.py</code>。</div>';
    return;
  }
  state.manifest = await resp.json();
  $searchInput.disabled = false;
  renderTabs();
  selectSubset(Object.keys(state.manifest.subsets)[0]);
}

function renderTabs() {
  $tabs.innerHTML = "";
  for (const [key, subset] of Object.entries(state.manifest.subsets)) {
    const tab = document.createElement("div");
    tab.className = "tab";
    tab.dataset.subset = key;
    if (key === state.currentSubset) tab.classList.add("active");
    tab.innerHTML = `${subset.label}<span class="count">${subset.count}</span>`;
    tab.addEventListener("click", () => selectSubset(key));
    $tabs.appendChild(tab);
  }
}

function selectSubset(key) {
  state.currentSubset = key;
  state.currentIndex = -1;
  state.searchQuery = "";
  $searchInput.value = "";
  renderTabs();
  renderSidebar();
  // Auto-select first image
  if (state.currentImages.length > 0) {
    showImage(0);
  } else {
    clearViewer();
  }
}

function getCurrentImageList() {
  if (!state.currentSubset) return [];
  const subset = state.manifest.subsets[state.currentSubset];
  if (!state.searchQuery) return subset.images;
  const q = state.searchQuery.toLowerCase();
  return subset.images.filter((img) => img.uuid.toLowerCase().includes(q));
}

function renderSidebar() {
  const subset = state.manifest.subsets[state.currentSubset];
  state.currentImages = getCurrentImageList();
  $sidebarHeader.textContent = `${subset.label} · ${state.currentImages.length} 张`;
  $thumbs.innerHTML = "";
  for (let i = 0; i < state.currentImages.length; i++) {
    const img = state.currentImages[i];
    const div = document.createElement("div");
    div.className = "thumb";
    if (i === state.currentIndex) div.classList.add("active");
    div.innerHTML = `
      <img loading="lazy" src="/thumb/${state.currentSubset}/${img.uuid}.jpg" alt="">
      <div class="uuid">${img.uuid.slice(0, 12)}…</div>
    `;
    div.addEventListener("click", () => showImage(i));
    $thumbs.appendChild(div);
  }
}

function showImage(index) {
  if (index < 0 || index >= state.currentImages.length) return;
  state.currentIndex = index;
  const img = state.currentImages[index];
  // Update sidebar highlight
  document.querySelectorAll(".thumb").forEach((el, i) => {
    el.classList.toggle("active", i === index);
  });
  // Update toolbar
  $filename.textContent = `${img.uuid}.jpg`;
  $fileMeta.textContent = formatBytes(img.size_bytes);
  $positionInfo.textContent = `第 ${index + 1} / ${state.currentImages.length} 张 · ${state.manifest.subsets[state.currentSubset].label}`;
  // Load image (zoom/pan reset happens via the load listener installed in Task 12)
  $errorOverlay.hidden = true;
  $mainImage.style.display = "";
  $mainImage.onerror = () => {
    $mainImage.style.display = "none";
    $errorOverlay.hidden = false;
  };
  $mainImage.src = `/image/${state.currentSubset}/${img.uuid}`;
}

function clearViewer() {
  state.currentIndex = -1;
  $filename.textContent = "未选择";
  $fileMeta.textContent = "";
  $positionInfo.textContent = "—";
  $mainImage.removeAttribute("src");
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

// Wire up search input
$searchInput.addEventListener("input", (e) => {
  state.searchQuery = e.target.value;
  renderSidebar();
  if (state.currentImages.length > 0) {
    showImage(0);
  } else {
    clearViewer();
  }
});

// === Zoom / Pan / Rotate ===
const zoomState = {
  scale: 1,        // 1 = fit-to-window (we treat as 100%)
  rotation: 0,     // degrees, 0/90/180/270
  offsetX: 0,
  offsetY: 0,
  // Track natural image dimensions for fit calculation
  naturalW: 0,
  naturalH: 0,
  // Track the "fit" scale so we can compute actual pixel scale for display
  fitScale: 1,
};

const MIN_SCALE = 0.1;
const MAX_SCALE = 4.0;
const $zoomPct = document.getElementById("zoom-pct");
const $btnZoomIn = document.getElementById("zoom-in");
const $btnZoomOut = document.getElementById("zoom-out");
const $btnRotate = document.getElementById("rotate");
const $btnFit = document.getElementById("fit");
const $btnPrev = document.getElementById("prev");
const $btnNext = document.getElementById("next");

$mainImage.addEventListener("load", () => {
  zoomState.naturalW = $mainImage.naturalWidth;
  zoomState.naturalH = $mainImage.naturalHeight;
  resetView();
});

function resetView() {
  zoomState.scale = 1;
  zoomState.rotation = 0;
  zoomState.offsetX = 0;
  zoomState.offsetY = 0;
  applyTransform();
}

function computeFitScale() {
  // The displayed image (without zoom) already fits the canvas via CSS max-width/height.
  // We treat scale=1 as "fit". Display percentage reflects zoomState.scale directly.
  return zoomState.scale;
}

function setScale(newScale) {
  zoomState.scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, newScale));
  applyTransform();
}

function applyTransform() {
  $mainImage.style.transform =
    `translate(${zoomState.offsetX}px, ${zoomState.offsetY}px) ` +
    `scale(${zoomState.scale}) rotate(${zoomState.rotation}deg)`;
  $zoomPct.textContent = `${Math.round(zoomState.scale * 100)}%`;
  // Cursor logic
  if (zoomState.scale > 1) {
    $mainImage.classList.add("grabbable");
    $mainImage.classList.remove("grabbing");
  } else {
    $mainImage.classList.remove("grabbable", "grabbing");
    zoomState.offsetX = 0;
    zoomState.offsetY = 0;
    $mainImage.style.transform =
      `scale(${zoomState.scale}) rotate(${zoomState.rotation}deg)`;
  }
}

$btnZoomIn.addEventListener("click", () => setScale(zoomState.scale + 0.1));
$btnZoomOut.addEventListener("click", () => setScale(zoomState.scale - 0.1));
$btnFit.addEventListener("click", resetView);
$btnRotate.addEventListener("click", () => {
  zoomState.rotation = (zoomState.rotation + 90) % 360;
  applyTransform();
});

// Wheel zoom (cursor-centric)
document.getElementById("canvas").addEventListener(
  "wheel",
  (e) => {
    if (state.currentIndex < 0) return;
    e.preventDefault();
    const delta = -Math.sign(e.deltaY) * 0.1;
    setScale(zoomState.scale + delta);
  },
  { passive: false }
);

// Drag pan
let dragState = null;
$mainImage.addEventListener("mousedown", (e) => {
  if (zoomState.scale <= 1) return;
  dragState = {
    startX: e.clientX,
    startY: e.clientY,
    origX: zoomState.offsetX,
    origY: zoomState.offsetY,
  };
  $mainImage.classList.add("grabbing");
  e.preventDefault();
});
window.addEventListener("mousemove", (e) => {
  if (!dragState) return;
  zoomState.offsetX = dragState.origX + (e.clientX - dragState.startX);
  zoomState.offsetY = dragState.origY + (e.clientY - dragState.startY);
  applyTransform();
});
window.addEventListener("mouseup", () => {
  if (dragState) {
    dragState = null;
    $mainImage.classList.remove("grabbing");
  }
});

// === Navigation ===
function gotoOffset(delta) {
  if (state.currentImages.length === 0) return;
  // Wrap around
  const n = state.currentImages.length;
  const newIndex = (state.currentIndex + delta + n) % n;
  showImage(newIndex);
}
$btnPrev.addEventListener("click", () => gotoOffset(-1));
$btnNext.addEventListener("click", () => gotoOffset(1));

window.addEventListener("keydown", (e) => {
  // Don't hijack typing in the search box
  if (document.activeElement === $searchInput) return;
  if (e.key === "ArrowLeft") gotoOffset(-1);
  else if (e.key === "ArrowRight") gotoOffset(1);
});

// Reset zoom/pan whenever a new image finishes loading.
// (Installed above via `$mainImage.addEventListener("load", ...)` which calls
// resetView(). The load listener also fires for cached images, so this covers
// both fresh loads and quick navigation between already-seen images.)

// Boot
loadManifest().catch((err) => console.error("boot failed:", err));
