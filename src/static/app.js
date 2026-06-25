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

// Boot
loadManifest().catch((err) => console.error("boot failed:", err));
