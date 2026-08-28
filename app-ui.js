function renderGrids(options) {
  ["now","soon"].forEach(function(t) {
    var html = "";
    var gridEl = document.getElementById("grid-" + t);
    if (currentView === 'list') {
      gridEl.className = 'movie-list';
      for (var i = 0; i < filtered[t].length; i++) html += listRowHTML(filtered[t][i], true);
    } else {
      gridEl.className = 'movie-grid';
      for (var i = 0; i < filtered[t].length; i++) html += cardHTML(filtered[t][i], true);
    }
    gridEl.innerHTML = html;
    var empty = document.getElementById("empty-" + t);
    if (filtered[t].length === 0) empty.classList.add("show"); else empty.classList.remove("show");
  });
  if (!options || !options.preserveViewport) scrollToResults();
}
function applyFilters(skipRender) {
  var minRating = parseFloat(document.getElementById("min-rating-select").value) || 0;
  var searchVal = (document.getElementById("tab-search").value || "").toLowerCase();
  var genreKeys = Object.keys(activeGenres);
  ["now","soon"].forEach(function(t) {
    filtered[t] = allMovies[t].filter(function(m) {
      if (searchVal && m.titleZh.toLowerCase().indexOf(searchVal) === -1 && m.titleEn.toLowerCase().indexOf(searchVal) === -1) return false;
      if (minRating > 0) {
        var tv = parseFloat(m.voteAverage) || 0; var iv = parseFloat(m.imdb) || 0;
        if (tv < minRating && iv < minRating) return false;
      }
      if (genreKeys.length > 0) {
        var ok = false;
        for (var i = 0; i < m.genre.length; i++) if (activeGenres[toTrad(m.genre[i])]) { ok = true; break; }
        if (!ok) return false;
      }
      return true;
    });
  });
  sortMovies(skipRender);
  updateActiveFiltersBadge();
}

function updateActiveFiltersBadge() {
  var parts = [];
  var genreKeys = Object.keys(activeGenres);
  for (var i = 0; i < genreKeys.length; i++) parts.push(genreKeys[i]);
  var rating = parseFloat(document.getElementById("min-rating-select").value) || 0;
  if (rating > 0) parts.push(rating + "分以上");
  var el = document.getElementById("active-filters-text");
  var clearBtn = document.getElementById("clear-all-filters-btn");
  if (el) el.textContent = parts.join(", ");
  if (clearBtn) {
    if (parts.length > 0) clearBtn.classList.add("visible");
    else clearBtn.classList.remove("visible");
  }
  updateMobileActiveBar();
}

function compareByPopularityDesc(a, b) {
  var diff = (parseFloat(b.popularity) || 0) - (parseFloat(a.popularity) || 0);
  if (diff !== 0) return diff;
  return (a.titleZh || a.titleEn || "").localeCompare(b.titleZh || b.titleEn || "", "zh-Hant-TW");
}

function withPopularityTiebreak(primary, a, b) {
  return primary || compareByPopularityDesc(a, b);
}

function sortMovies(skipRender, preserveViewport) {
  tabSortState[currentTab] = document.getElementById("sort-select").value;
  ["now","soon"].forEach(function(t) {
    var v = tabSortState[t];
    filtered[t] = filtered[t].slice().sort(function(a, b) {
      var primary = 0;
      if (v === "date_desc") primary = (b.releaseDate || "").localeCompare(a.releaseDate || "");
      else if (v === "date_asc") primary = (a.releaseDate || "").localeCompare(b.releaseDate || "");
      else if (v === "tmdb_desc") primary = (parseFloat(b.voteAverage)||0) - (parseFloat(a.voteAverage)||0);
      else if (v === "tmdb_asc") primary = (parseFloat(a.voteAverage)||0) - (parseFloat(b.voteAverage)||0);
      else if (v === "imdb_desc") primary = (parseFloat(b.imdb)||0) - (parseFloat(a.imdb)||0);
      else if (v === "imdb_asc") primary = (parseFloat(a.imdb)||0) - (parseFloat(b.imdb)||0);
      return withPopularityTiebreak(primary, a, b);
    });
  });
  if (!skipRender) renderGrids({ preserveViewport: !!preserveViewport });
}

function setClearBtn(id, val) {
  var b = document.getElementById(id);
  if (b) { if (val) b.classList.add("visible"); else b.classList.remove("visible"); }
}

function runTabSearch(val) {
  setClearBtn("tab-search-clear", val);
  clearTimeout(searchDebounce);
  applyFilters();
}

function bindSearchInput(el) {
  if (!el) return;
  var composing = false;
  el.addEventListener("compositionstart", function() { composing = true; });
  el.addEventListener("compositionend", function() {
    composing = false;
    runTabSearch(el.value);
  });
  el.addEventListener("input", function() {
    if (composing) return;
    clearTimeout(searchDebounce);
    setClearBtn("tab-search-clear", el.value);
    searchDebounce = setTimeout(function() { applyFilters(); }, 300);
  });
}

function clearSearch() {
  document.getElementById("tab-search").value = "";
  var ms = document.getElementById("mobile-tab-search");
  if (ms) ms.value = "";
  runTabSearch("");
}

function buildGenreFilters() {
  var gs = {};
  ["now","soon"].forEach(function(t) { allMovies[t].forEach(function(m) { normalizeGenreList(m.genre).forEach(function(g) { gs[g] = true; }); }); });
  var genres = Object.keys(gs).sort(); var html = "";
  for (var i = 0; i < genres.length; i++) html += '<button class="filter-tag" onclick="toggleGenre(\'' + escHtml(genres[i]) + '\',this)">' + escHtml(genres[i]) + '</button>';
  document.getElementById("genre-filters").innerHTML = html;
}
function toggleGenre(g, btn) {
  if (activeGenres[g]) { delete activeGenres[g]; btn.classList.remove("active"); } else { activeGenres[g] = true; btn.classList.add("active"); }
  applyFilters();
}
function clearFilters() {
  activeGenres = {};
  document.getElementById("min-rating-select").value = "0";
  document.getElementById("tab-search").value = "";
  var ms = document.getElementById("mobile-tab-search");
  if (ms) { ms.value = ""; setClearBtn("mobile-search-clear", ""); }
  document.querySelectorAll(".filter-tag").forEach(function(btn) { btn.classList.remove("active"); });
  applyFilters();
}
function toggleFilter(btn) {
  var panel = document.getElementById("filter-panel");
  var isOpen = panel.style.display === "block";
  panel.style.display = isOpen ? "none" : "block";
  if (window.innerWidth <= 768) {
    mobilePanelOpen = !isOpen;
    var toggle = document.getElementById("mobile-search-toggle");
    if (toggle) toggle.classList.toggle("active", mobilePanelOpen);
    updateMobileActiveBar();
  } else {
    if (btn) btn.blur();
  }
}
function clearMobileSearch() {
  document.getElementById("mobile-tab-search").value = "";
  document.getElementById("tab-search").value = "";
  setClearBtn("mobile-search-clear", "");
  applyFilters();
}
function getMobileActiveParts() {
  var parts = [];
  var sv = document.getElementById("tab-search").value;
  if (sv) parts.push(sv);
  var genreKeys = Object.keys(activeGenres);
  for (var i = 0; i < genreKeys.length; i++) parts.push(genreKeys[i]);
  var rating = parseFloat(document.getElementById("min-rating-select").value) || 0;
  if (rating > 0) parts.push(rating + "分以上");
  return parts;
}
function updateMobileActiveBar() {
  var bar = document.getElementById("mobile-active-bar");
  var barText = document.getElementById("mobile-active-bar-text");
  if (!bar) return;
  var parts = getMobileActiveParts();
  if (barText) barText.textContent = parts.join(", ");
  var clearBtn = bar.querySelector(".clear-active-btn");
  if (clearBtn) clearBtn.style.display = parts.length > 0 ? "flex" : "none";
  if (mobilePanelOpen) {
    bar.classList.add("panel-open");
    bar.classList.remove("visible");
  } else {
    bar.classList.remove("panel-open");
    if (parts.length > 0) bar.classList.add("visible");
    else bar.classList.remove("visible");
  }
}
function moveTabIndicator(tabId) {
  var indicator = document.getElementById('tab-indicator');
  var btn = document.getElementById('tab-' + tabId);
  if (!indicator || !btn) return;
  indicator.style.left = btn.offsetLeft + 'px';
  indicator.style.width = btn.offsetWidth + 'px';
}

var tabFadeTimer = null;
var tabFadeSeq = 0;

function activateTabContent(t) {
  document.querySelectorAll(".tab-content").forEach(function(el) { el.classList.remove("active"); });
  document.getElementById("content-" + t).classList.add("active");
  document.querySelectorAll(".tab-btn").forEach(function(el) {
    el.setAttribute("aria-selected", el.id === "tab-" + t ? "true" : "false");
  });
}

function isTabBarPinned() {
  var tabBar = document.getElementById("tab-bar");
  if (!tabBar) return false;
  return tabBar.getBoundingClientRect().top <= 0;
}

function holdPinnedTabBarForMobileReturn() {
  if (!window.matchMedia("(max-width: 1024px) and (pointer: coarse)").matches) return;
  if (!isTabBarPinned()) return;
  var tabBar = document.getElementById("tab-bar");
  if (!tabBar) return;
  document.body.style.setProperty("--return-tab-bar-height", tabBar.offsetHeight + "px");
  document.body.classList.add("mobile-return-pinned");
}

document.addEventListener("touchstart", function(event) {
  if (event.target.closest(".movie-card .card-info")) return;
  if (event.target.closest(".movie-link")) holdPinnedTabBarForMobileReturn();
}, { passive: true, capture: true });

var mobileReturnSettling = false;

function releaseMobileReturnPinAtPageTop() {
  if (mobileReturnSettling || !document.body.classList.contains("mobile-return-pinned")) return;
  var navbar = document.getElementById("navbar");
  var releaseAt = navbar ? navbar.offsetHeight : 0;
  if ((window.scrollY || window.pageYOffset || 0) > releaseAt) return;
  document.body.classList.remove("mobile-return-pinned");
  document.body.style.removeProperty("--return-tab-bar-height");
}

window.addEventListener("pageshow", function() {
  if (!document.body.classList.contains("mobile-return-pinned")) return;
  mobileReturnSettling = true;
  // WebKit can finish restoring scroll after pageshow. Once it settles, keep
  // the fixed bar for a restored scrolled page and release it only near top.
  window.setTimeout(function() {
    mobileReturnSettling = false;
    releaseMobileReturnPinAtPageTop();
  }, 400);
});

window.addEventListener("scroll", releaseMobileReturnPinAtPageTop, { passive: true });

function jumpToContentTop(keepTabBarPinned) {
  if (!keepTabBarPinned) return;
  var contentArea = document.querySelector(".content-area");
  var tabBar = document.getElementById("tab-bar");
  if (!contentArea || !tabBar) return;
  var targetY = contentArea.offsetTop - tabBar.offsetHeight;
  window.scrollTo(0, Math.max(0, targetY));
}

function switchTab(t) {
  var shouldFadeContent = currentTab !== t;
  var contentArea = document.querySelector(".content-area");
  var keepTabBarPinned = isTabBarPinned();
  currentTab = t;
  try { sessionStorage.setItem("wt_active_tab", t); } catch(e) {}
  try { history.replaceState(null, '', t === 'now' ? '#' : '#' + t); } catch(e) {}
  document.getElementById("sort-select").value = tabSortState[t];
  document.querySelectorAll(".tab-btn").forEach(function(el) { el.classList.remove("active"); });
  document.getElementById("tab-" + t).classList.add("active");
  moveTabIndicator(t);

  if (!shouldFadeContent || !contentArea) {
    activateTabContent(t);
    return;
  }

  tabFadeSeq += 1;
  var seq = tabFadeSeq;
  if (tabFadeTimer) clearTimeout(tabFadeTimer);
  contentArea.classList.add("tab-fading");

  tabFadeTimer = setTimeout(function() {
    if (seq !== tabFadeSeq) return;
    jumpToContentTop(keepTabBarPinned);
    activateTabContent(t);
    requestAnimationFrame(function() {
      if (seq !== tabFadeSeq) return;
      contentArea.classList.remove("tab-fading");
      tabFadeTimer = null;
    });
  }, 160);
}

function movieDetailSlug(movie, detail) {
  var titles = [
    movie && movie.titleEn,
    movie && movie.origTitle,
    movie && movie.titleZh,
    detail && detail.origTitle
  ];
  var slug = "";
  for (var i = 0; i < titles.length; i++) {
    if (!titles[i]) continue;
    var title = String(titles[i]);
    var hasCjk = /[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(title);
    var asciiLetters = (title.toLowerCase().match(/[a-z]/g) || []).length;
    if (hasCjk && asciiLetters < 3) continue;
    if (asciiLetters === 0 && /[^\x00-\x7f]/.test(title.replace(/[^\p{L}]/gu, ""))) continue;
    slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    if (slug) break;
  }
  if (!slug) slug = "movie";
  return String(movie.id) + "-" + slug;
}

function movieDetailHref(movie, detail) {
  return "movies/" + encodeURIComponent(movieDetailSlug(movie, detail)) + "/";
}
