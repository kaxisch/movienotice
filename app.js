document.addEventListener("keydown", function(e) {
  if (e.key === "Escape") {
    var infoWasOpen = document.getElementById("site-info-panel") && !document.getElementById("site-info-panel").hidden;
    closeSiteInfo();
    if (infoWasOpen) {
      var infoButton = document.getElementById("site-info-btn");
      if (infoButton) infoButton.focus();
    }
  }
});

document.addEventListener("click", function(e) {
  var mobileCardInfo = e.target.closest(".movie-card .card-info");
  if (mobileCardInfo && window.matchMedia("(max-width: 1024px) and (pointer: coarse)").matches) {
    e.preventDefault();
    return;
  }
  if (e.target.closest(".movie-link")) holdPinnedTabBarForMobileReturn();
  var infoPanel = document.getElementById("site-info-panel");
  if (infoPanel && !infoPanel.hidden && !e.target.closest(".site-info-wrap")) closeSiteInfo();
  var panel = document.getElementById("filter-panel");
  if (panel.style.display !== "block") return;
  if (panel.contains(e.target)) return;
  if (e.target.closest("#mobile-search-toggle, .filter-btn")) return;
  toggleFilter();
});

document.addEventListener("DOMContentLoaded", function() {
  requestAnimationFrame(function() { moveTabIndicator(currentTab); });
  bindSearchInput(document.getElementById("tab-search"));
  var mSearch = document.getElementById("mobile-tab-search");
  if (mSearch) {
    var mComposing = false;
    mSearch.addEventListener("compositionstart", function() { mComposing = true; });
    mSearch.addEventListener("compositionend", function() {
      mComposing = false;
      document.getElementById("tab-search").value = mSearch.value;
      setClearBtn("mobile-search-clear", mSearch.value);
      applyFilters();
    });
    mSearch.addEventListener("input", function() {
      if (mComposing) return;
      document.getElementById("tab-search").value = mSearch.value;
      setClearBtn("mobile-search-clear", mSearch.value);
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(function() { applyFilters(); }, 300);
    });
  }
});

function scrollToResults() {
  var navbar = document.getElementById("navbar");
  var navH = navbar ? navbar.offsetHeight : 0;
  if (window.pageYOffset > navH) {
    try {
      window.scrollTo({ top: navH, behavior: "smooth" });
    } catch(e) {
      window.scrollTo(0, navH);
    }
  }
}

function applyLoadedMoviePayload(payload) {
  movieDataMeta.generated_at = payload.generated_at || "";
  payload = normalizeMoviePayload(payload);
  allMovies = payload.movies || { now: [], soon: [] };
  rebucketMoviesByReleaseDate();
  filtered = { now: allMovies.now.slice(), soon: allMovies.soon.slice() };
  // Loading fresh data can finish while Safari is restoring a page from its
  // back-forward cache. Do not compete with the restored scroll position.
  sortMovies(false, true);
  buildGenreFilters();
  updateDataStatus(payload.generated_at || "");
  updateReleaseTicker();
  return payload;
}

function loadData(forceRefresh) {
  var errBanner = document.getElementById("error-banner");
  errBanner.classList.remove("show");
  var cached = null;
  if (!forceRefresh) {
    cached = loadCache();
    if (cached) {
      applyLoadedMoviePayload(cached);
    }
  }
  if (!cached) showSkeletons();
  fetch(STATIC_DATA_PATH, { cache: "no-store" }).then(function(r) {
    if (!r.ok) throw new Error("STATIC " + r.status);
    return r.json();
  }).then(function(payload) {
    payload = applyLoadedMoviePayload(payload);
    saveCache(payload);
  }).catch(function(e) {
    errBanner.textContent = "⚠️ 資料載入失敗：" + e.message;
    errBanner.classList.add("show");
    var fallback = cached || loadCache();
    if (fallback) {
      applyLoadedMoviePayload(fallback);
    }
  });
}

function refreshData() { loadData(true); }
switchTab(currentTab);
loadData(false);

(function refreshWeekLabelsAtBoundary() {
  var displayedWeekStart = taipeiWeekRange().start;
  setInterval(function() {
    var currentWeekStart = taipeiWeekRange().start;
    if (currentWeekStart === displayedWeekStart) return;
    displayedWeekStart = currentWeekStart;
    renderGrids({ preserveViewport: true });
    updateReleaseTicker();
  }, 60 * 1000);
})();

(function() {
  var TABS = ['now', 'soon'];
  var startX = 0, startY = 0;
  document.addEventListener('touchstart', function(e) {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
  }, { passive: true });
  document.addEventListener('touchend', function(e) {
    if (window.innerWidth > 768) return;
    var dx = e.changedTouches[0].clientX - startX;
    var dy = e.changedTouches[0].clientY - startY;
    if (Math.abs(dx) < 50 || Math.abs(dx) <= Math.abs(dy)) return;
    var idx = TABS.indexOf(currentTab);
    if (dx < 0 && idx < TABS.length - 1) switchTab(TABS[idx + 1]);
    else if (dx > 0 && idx > 0) switchTab(TABS[idx - 1]);
  }, { passive: true });
})();
