var STATIC_DATA_PATH = "data/movie-data.json";
var CACHE_KEY = "movienotice_static_v1";
var CACHE_TTL = 60 * 60 * 1000;
var movieDataMeta = { generated_at: "" };

var allMovies = { now: [], soon: [] };
var filtered = { now: [], soon: [] };
var currentTab = (function() {
  var h = window.location.hash.replace('#','');
  if (h === 'soon') return h;
  try { var v = sessionStorage.getItem("wt_active_tab"); if (v === 'soon') return v; } catch(e) {}
  return "now";
})();
var activeGenres = {};
var searchDebounce = null;
var mobilePanelOpen = false;
var tabSortState = { now: "date_desc", soon: "date_asc" };
var currentView = 'card';

var genreMap = {
  "动作":"動作","冒险":"冒險","喜剧":"喜劇","犯罪":"犯罪","纪录片":"紀錄片",
  "剧情":"劇情","家庭":"家庭","奇幻":"奇幻","历史":"歷史","恐怖":"恐怖",
  "音乐":"音樂","悬疑":"懸疑","爱情":"愛情","科幻":"科幻","电视电影":"電視電影",
  "惊悚":"驚悚","战争":"戰爭","西部":"西部","动画":"動畫","传记":"傳記",
  "运动":"運動","歌舞":"歌舞","武侠":"武俠","古装":"古裝",
  "记录片":"紀錄片","纪录":"紀錄","记录":"紀錄",
  "Action":"動作","Adventure":"冒險","Comedy":"喜劇","Crime":"犯罪",
  "Documentary":"紀錄片","Drama":"劇情","Family":"家庭","Fantasy":"奇幻",
  "History":"歷史","Horror":"恐怖","Music":"音樂","Mystery":"懸疑",
  "Romance":"愛情","Science Fiction":"科幻","TV Movie":"電視電影",
  "Thriller":"驚悚","War":"戰爭","Western":"西部","Animation":"動畫",
  "Biography":"傳記","Sport":"運動","Musical":"歌舞","War & Politics":"戰爭",
  "Sci-Fi & Fantasy":"科幻","Action & Adventure":"動作","Kids":"家庭","News":"紀錄片"
};

function toTrad(s) { return genreMap[s] || s; }
function normalizeGenreList(genres) {
  if (!Array.isArray(genres)) return [];
  var seen = {};
  var result = [];
  genres.forEach(function(g) {
    var trad = toTrad(g);
    if (!trad || seen[trad]) return;
    seen[trad] = true;
    result.push(trad);
  });
  return result;
}
function normalizeMovieGenres(movie) {
  if (!movie) return movie;
  movie.genre = normalizeGenreList(movie.genre);
  if (movie.detail) movie.detail.genres = normalizeGenreList(movie.detail.genres || movie.genre);
  return movie;
}
function normalizeMoviePayload(payload) {
  if (!payload || !payload.movies) return payload;
  ["now","soon"].forEach(function(t) {
    if (!Array.isArray(payload.movies[t])) payload.movies[t] = [];
    payload.movies[t].forEach(normalizeMovieGenres);
  });
  return payload;
}
function tmdbScore(v) {
  if (!v) return "";
  var n = parseFloat(v);
  return isNaN(n) ? "" : Math.round(n * 10) + "%";
}
var RT_ICON_PATH = "M9.39062 1.98047C10.9661 2.92468 11.9998 4.50879 12 6.30371C12 9.19723 9.31327 11.5448 6 11.5449C2.68684 11.5449 0 9.19729 0 6.30371C2.58634e-05 4.52964 1.01216 2.96319 2.55762 2.01562L3.54492 2.55176L2.37988 4.44629C2.31509 4.55166 2.27242 4.6472 2.24805 4.7373C2.19735 4.92517 2.23996 5.06172 2.28516 5.14258C2.36849 5.29151 2.52759 5.37988 2.70996 5.37988C2.83408 5.37984 2.97181 5.34088 3.13086 5.25977L5.82129 3.8877L8.71582 5.27832C8.87274 5.35373 9.00746 5.3906 9.12695 5.39062C9.3129 5.39062 9.47228 5.29883 9.55273 5.14551C9.59684 5.06137 9.63579 4.92115 9.57227 4.73145C9.543 4.64405 9.4942 4.55214 9.42383 4.4502L8.12305 2.56543L9.39062 1.98047ZM6.03516 0.0449219L6.83398 1.18066L6.94922 1.34473L7.14746 1.36914L8.40527 1.52051L7.36719 2.00098L6.88086 2.22461L7.18359 2.66602L8.1709 4.09668L6.01074 3.05859L5.80957 2.96289L5.6123 3.06445L3.55859 4.11035L4.46094 2.64551L4.70801 2.24121L4.29199 2.01367L3.41211 1.53613L4.79785 1.3623L4.98828 1.33887L5.10254 1.18359L5.94922 0.0439453C5.96811 0.0186072 5.98301 0.00535117 5.99121 0C5.99878 0.00489482 6.0155 0.0170432 6.03516 0.0449219Z";
function rtIconSvg(fill, style) {
  return '<svg width="10" height="10" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" style="' + (style || 'flex-shrink:0') + '"><path d="' + RT_ICON_PATH + '" fill="' + fill + '"/></svg>';
}
function formatLocalDate(d) {
  var y = d.getFullYear();
  var m = String(d.getMonth() + 1).padStart(2, "0");
  var day = String(d.getDate()).padStart(2, "0");
  return y + "-" + m + "-" + day;
}
function shiftedLocalDate(n) {
  var d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + n);
  return formatLocalDate(d);
}
function today() { return shiftedLocalDate(0); }
function daysLater(n) { return shiftedLocalDate(n); }
function taipeiToday() {
  var parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(new Date());
  var values = {};
  parts.forEach(function(part) { values[part.type] = part.value; });
  return values.year + "-" + values.month + "-" + values.day;
}
function taipeiWeekRange() {
  var currentDate = taipeiToday();
  var current = new Date(currentDate + "T00:00:00Z");
  var sunday = new Date(current);
  sunday.setUTCDate(current.getUTCDate() - current.getUTCDay());
  var saturday = new Date(sunday);
  saturday.setUTCDate(sunday.getUTCDate() + 6);
  return {
    start: sunday.toISOString().slice(0, 10),
    end: saturday.toISOString().slice(0, 10)
  };
}
function isThisWeekRelease(movie) {
  var releaseDate = movie && movie.releaseDate;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(releaseDate || "")) return false;
  var week = taipeiWeekRange();
  return releaseDate >= week.start && releaseDate <= week.end;
}
function buildReleaseTickerGroup(titles, isDuplicate) {
  var group = document.createElement("div");
  group.className = "release-ticker-group";
  if (isDuplicate) group.setAttribute("aria-hidden", "true");

  var label = document.createElement("span");
  label.className = "release-ticker-label";
  label.textContent = "本週上映";
  group.appendChild(label);

  titles.forEach(function(title) {
    var dot = document.createElement("span");
    dot.className = "release-ticker-dot";
    dot.setAttribute("aria-hidden", "true");
    dot.textContent = "·";
    group.appendChild(dot);

    var titleNode = document.createElement("span");
    titleNode.className = "release-ticker-title";
    titleNode.textContent = title;
    group.appendChild(titleNode);
  });

  var trailingDot = document.createElement("span");
  trailingDot.className = "release-ticker-dot";
  trailingDot.setAttribute("aria-hidden", "true");
  trailingDot.textContent = "·";
  group.appendChild(trailingDot);
  return group;
}
function updateReleaseTicker() {
  var ticker = document.getElementById("release-ticker");
  var track = document.getElementById("release-ticker-track");
  if (!ticker || !track) return;

  var seen = {};
  var movies = (allMovies.now || []).concat(allMovies.soon || []).filter(isThisWeekRelease);
  movies.sort(function(a, b) {
    return (a.releaseDate || "").localeCompare(b.releaseDate || "") ||
      compareByPopularityDesc(a, b);
  });
  var titles = movies.map(function(movie) { return movie.titleZh || movie.titleEn || ""; }).filter(function(title) {
    var key = normalizeTitleKey(title);
    if (!key || seen[key]) return false;
    seen[key] = true;
    return true;
  });

  track.replaceChildren();
  if (!titles.length) {
    ticker.classList.add("is-empty");
    ticker.setAttribute("aria-label", "本週上映電影：敬請期待");
    track.appendChild(buildReleaseTickerGroup(["敬請期待"], false));
    return;
  }

  ticker.classList.remove("is-empty");
  ticker.setAttribute("aria-label", "本週上映電影：" + titles.join("、"));
  track.appendChild(buildReleaseTickerGroup(titles, false));
  track.appendChild(buildReleaseTickerGroup(titles, true));
  var characterCount = titles.join("").length + titles.length * 3;
  track.style.setProperty("--ticker-duration", Math.max(36, characterCount * 0.5) + "s");
}
function normalizeTitleKey(text) {
  return String(text || "").toLowerCase().trim().replace(/[\s\-–—:：'"!?,.&／/·・()\[\]{}]+/g, "");
}
function formatDate(d) {
  if (!d) return "";
  var p = d.split("-");
  return p[0] + "/" + p[1] + "/" + p[2];
}
var releaseLanguageMap = { "ja":"日文", "zh":"中文", "en":"英文" };
function formatReleaseDates(movie, separator) {
  var releases = Array.isArray(movie.twTheatricalReleases) ? movie.twTheatricalReleases : [];
  if (releases.length < 2) return formatDate(movie.releaseDate);
  return releases.map(function(item) {
    var language = releaseLanguageMap[item.language] || "";
    return formatDate(item.date) + (language ? "（" + language + "）" : "");
  }).join(separator === undefined ? "<br>" : separator);
}
function formatUpdateTime(isoString) {
  if (!isoString) return "";
  var d = new Date(isoString);
  if (isNaN(d.getTime())) return "";
  var y = d.getFullYear();
  var mo = String(d.getMonth() + 1).padStart(2, "0");
  var day = String(d.getDate()).padStart(2, "0");
  var hh = String(d.getHours()).padStart(2, "0");
  var mm = String(d.getMinutes()).padStart(2, "0");
  return y + "/" + mo + "/" + day + " " + hh + ":" + mm;
}
function updateDataStatus(generatedAt) {
  movieDataMeta.generated_at = generatedAt || "";
  var formatted = formatUpdateTime(generatedAt);
  var updateTime = document.getElementById("info-update-time");
  if (updateTime) updateTime.textContent = formatted ? "更新於 " + formatted : "靜態資料模式";
  var nowCount = document.getElementById("info-count-now");
  var soonCount = document.getElementById("info-count-soon");
  if (nowCount) nowCount.textContent = (allMovies.now ? allMovies.now.length : 0) + " 部";
  if (soonCount) soonCount.textContent = (allMovies.soon ? allMovies.soon.length : 0) + " 部";
}
function closeSiteInfo() {
  var panel = document.getElementById("site-info-panel");
  var button = document.getElementById("site-info-btn");
  if (!panel || !button || panel.hidden) return;
  panel.hidden = true;
  button.setAttribute("aria-expanded", "false");
}

function toggleSiteInfo(event) {
  if (event) event.stopPropagation();
  var panel = document.getElementById("site-info-panel");
  var button = document.getElementById("site-info-btn");
  if (!panel || !button) return;
  var willOpen = panel.hidden;
  panel.hidden = !willOpen;
  button.setAttribute("aria-expanded", willOpen ? "true" : "false");
}
function saveCache(data) {
  try { localStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), data: data })); } catch(e) {}
}
function loadCache() {
  try {
    var raw = localStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    var obj = JSON.parse(raw);
    return Date.now() - obj.ts > CACHE_TTL ? null : obj.data;
  } catch(e) { return null; }
}
function escHtml(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function rebucketMoviesByReleaseDate() {
  var rebucketed = { now: [], soon: [] };
  var seen = {};
  var todayStr = today();
  var soonCutoff = daysLater(180);
  ["now","soon"].forEach(function(t) {
    (allMovies[t] || []).forEach(function(m) {
      if (!m || seen[m.id]) return;
      seen[m.id] = true;
      var releaseDate = m.releaseDate || "";
      if (releaseDate && releaseDate <= todayStr) rebucketed.now.push(m);
      else if (releaseDate && releaseDate <= soonCutoff) rebucketed.soon.push(m);
    });
  });
  allMovies = rebucketed;
}

function cardHTML(m, showRatings) {
  var cardImage = m.poster || m.backdrop || "";
  var useBackdropImage = !!(!m.poster && m.backdrop) || !!m.posterIsBackdrop;
  var imgHTML = cardImage
    ? '<img src="' + cardImage + '" alt="" loading="lazy"' + (useBackdropImage ? ' class="card-img-backdrop"' : '') + '/>'
    : '<div class="card-no-img"><span class="material-symbols-outlined" style="font-size:48px">movie</span></div>';
  var titleEn = (m.titleEn && m.titleEn !== m.titleZh)
    ? '<p class="card-title-en">' + escHtml(m.titleEn) + '</p>'
    : '<p class="card-title-en"></p>';
  var metaHTML = '<div class="card-meta"><span class="card-date">' + formatReleaseDates(m) + '</span>';
  if (showRatings) {
    var imdbStyle = m.imdb ? '' : ' style="display:none"';
    var rtStyle = m.rt ? '' : ' style="display:none"';
    var mcStyle = m.mc ? '' : ' style="display:none"';
    metaHTML += '<div class="card-badges">';
    metaHTML += '<span class="badge-imdb" id="imdb-' + m.id + '"' + imdbStyle + '><span class="badge-source">IMDb</span><span>' + escHtml(m.imdb || '') + '</span></span>';
    metaHTML += '<span class="badge-rt" id="rt-' + m.id + '"' + rtStyle + '>' + rtIconSvg('#a36b66', 'flex-shrink:0;vertical-align:middle;margin-right:2px') + '<span>' + escHtml(m.rt || '') + '</span></span>';
    metaHTML += '<span class="badge-mc" id="mc-' + m.id + '"' + mcStyle + '><span class="badge-source">MT</span><span>' + escHtml(m.mc || '') + '</span></span>';
    if (m.voteAverage) metaHTML += '<span class="badge-tmdb"><span class="badge-source">TMDB</span><span>' + tmdbScore(m.voteAverage) + '</span></span>';
    metaHTML += '</div>';
  }
  metaHTML += '</div>';
  var href = escHtml(movieDetailHref(m));
  var thisWeekLabel = isThisWeekRelease(m) ? '<span class="this-week-ribbon">本週上映</span>' : '';
  return '<a class="movie-card movie-link fade-in" id="card-' + m.id + '" href="' + href + '">' +
    '<div class="card-img-wrap"><div class="card-poster-clip">' + imgHTML + thisWeekLabel +
    '<div class="card-hover-overlay"><span class="card-hover-genre">' + escHtml(normalizeGenreList(m.genre).slice(0,2).join(' / ')) + '</span></div></div>' +
    '<span class="card-corner card-corner-tl" aria-hidden="true"></span><span class="card-corner card-corner-tr" aria-hidden="true"></span>' +
    '<span class="card-corner card-corner-bl" aria-hidden="true"></span><span class="card-corner card-corner-br" aria-hidden="true"></span></div>' +
    '<div class="card-info"><p class="card-title">' + escHtml(m.titleZh) + '</p>' + titleEn +
    '<div class="card-spacer"></div>' + metaHTML + '</div></a>';
}

function skeletonHTML() {
  var html = "";
  for (var i = 0; i < 10; i++) {
    html += '<div><div class="skeleton" style="padding-top:150%;border-radius:16px;margin-bottom:12px"></div>' +
      '<div class="skeleton" style="height:12px;border-radius:6px;margin-bottom:6px;width:75%"></div>' +
      '<div class="skeleton" style="height:10px;border-radius:6px;width:50%"></div></div>';
  }
  return html;
}

function showSkeletons() {
  ["now","soon"].forEach(function(t) { document.getElementById("grid-" + t).innerHTML = skeletonHTML(); });
}

function setView(v) {
  currentView = v;
  document.getElementById('btn-view-card').classList.toggle('active', v === 'card');
  document.getElementById('btn-view-list').classList.toggle('active', v === 'list');
  renderGrids();
}

function listRowHTML(m, showRatings) {
  var listImage = m.poster || m.backdrop || "";
  var useBackdropImage = !!(!m.poster && m.backdrop) || !!m.posterIsBackdrop;
  var imgHTML = listImage
    ? '<img class="list-poster' + (useBackdropImage ? ' list-poster-backdrop' : '') + '" src="' + listImage + '" alt="" loading="lazy"/>'
    : '<div class="list-no-poster"><span class="material-symbols-outlined" style="font-size:16px">movie</span></div>';
  var subtitleParts = [];
  if (m.titleEn && m.titleEn !== m.titleZh) subtitleParts.push(m.titleEn);
  var displayGenres = normalizeGenreList(m.genre);
  if (displayGenres.length > 0) subtitleParts.push(displayGenres.slice(0, 2).join(' / '));
  var subtitleHTML = subtitleParts.length ? '<p class="list-subtitle">' +
    (m.titleEn && m.titleEn !== m.titleZh ? '<span class="original-title">' + escHtml(m.titleEn) + '</span>' : '') +
    (m.titleEn && m.titleEn !== m.titleZh && displayGenres.length > 0 ? ' · ' : '') +
    (displayGenres.length > 0 ? escHtml(displayGenres.slice(0, 2).join(' / ')) : '') + '</p>' : '';
  var badgesHTML = '';
  if (showRatings) {
    var imdbStyle = m.imdb ? '' : ' style="display:none"';
    var rtStyle = m.rt ? '' : ' style="display:none"';
    var mcStyle = m.mc ? '' : ' style="display:none"';
    badgesHTML += '<span class="badge-imdb" id="imdb-' + m.id + '"' + imdbStyle + '><span class="badge-source">IMDb</span><span>' + escHtml(m.imdb || '') + '</span></span>';
    badgesHTML += '<span class="badge-rt" id="rt-' + m.id + '"' + rtStyle + '>' + rtIconSvg('#a36b66', 'flex-shrink:0;vertical-align:middle;margin-right:2px') + '<span>' + escHtml(m.rt || '') + '</span></span>';
    badgesHTML += '<span class="badge-mc" id="mc-' + m.id + '"' + mcStyle + '><span class="badge-source">MT</span><span>' + escHtml(m.mc || '') + '</span></span>';
    if (m.voteAverage) badgesHTML += '<span class="badge-tmdb"><span class="badge-source">TMDB</span><span>' + tmdbScore(m.voteAverage) + '</span></span>';
  }
  var href = escHtml(movieDetailHref(m));
  var thisWeekLabel = isThisWeekRelease(m) ? '<span class="this-week-list-label">本週上映</span>' : '';
  return '<a class="list-item movie-link fade-in" id="card-' + m.id + '" href="' + href + '">' +
    imgHTML +
    '<div class="list-info"><p class="list-title">' + escHtml(m.titleZh) + '</p>' + thisWeekLabel + subtitleHTML + (m.releaseDate ? '<p class="list-date">' + formatReleaseDates(m) + '</p>' : '') + '</div>' +
    '<div class="list-badges">' + badgesHTML + '</div>' +
    '</a>';
}
