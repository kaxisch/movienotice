var STATIC_DATA_PATH = "data/movie-data.json";
var CACHE_KEY = "movienotice_static_v1";
var CACHE_TTL = 60 * 60 * 1000;
var movieDataMeta = { generated_at: "" };
function normalizeImdbRatings(ratings) {
  return {
    imdb: ratings && ratings.imdb && ratings.imdb !== "N/A" ? ratings.imdb : "",
    rt: ratings && ratings.rt ? ratings.rt : "",
    mc: ratings && ratings.mc ? ratings.mc : ""
  };
}
function getMoviesForRatingRefresh() {
  return [];
}

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
var currentModalMovieId = null;

var countryMap = {
  "US":"美國","GB":"英國","FR":"法國","DE":"德國","IT":"義大利","JP":"日本","KR":"韓國",
  "CN":"中國","HK":"香港","TW":"台灣","AU":"澳洲","CA":"加拿大","ES":"西班牙","IN":"印度",
  "NZ":"紐西蘭","IE":"愛爾蘭","NL":"荷蘭","BE":"比利時","SE":"瑞典","DK":"丹麥","NO":"挪威",
  "FI":"芬蘭","RU":"俄羅斯","MX":"墨西哥","BR":"巴西","AR":"阿根廷","TH":"泰國","SG":"新加坡",
  "ZA":"南非","AT":"奧地利","CH":"瑞士","PL":"波蘭","CZ":"捷克","HU":"匈牙利","PT":"葡萄牙",
  "GR":"希臘","IL":"以色列","TR":"土耳其","MY":"馬來西亞","ID":"印尼","PH":"菲律賓","VN":"越南",
  "United States of America":"美國","Japan":"日本","United Kingdom":"英國","Taiwan":"台灣",
  "France":"法國","Canada":"加拿大","Netherlands":"荷蘭","South Korea":"韓國","Germany":"德國",
  "Thailand":"泰國","Hong Kong":"香港","Mexico":"墨西哥","Saudi Arabia":"沙烏地阿拉伯",
  "Spain":"西班牙","Belgium":"比利時","Ireland":"愛爾蘭","United Arab Emirates":"阿拉伯聯合大公國",
  "Brazil":"巴西","Chile":"智利","China":"中國","Tunisia":"突尼西亞","Cyprus":"賽普勒斯",
  "Italy":"義大利","Palestinian Territory":"巴勒斯坦","Indonesia":"印尼","Hungary":"匈牙利",
  "Turkey":"土耳其","Greece":"希臘","Sweden":"瑞典","Philippines":"菲律賓","India":"印度"
};
function formatCountryList(countries) {
  if (!countries || !countries.length) return "—";
  return countries.map(function(country) { return countryMap[country] || country; }).join(" · ");
}

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
function daysAgo(n) { return shiftedLocalDate(-n); }
function daysLater(n) { return shiftedLocalDate(n); }
function dateYear(s) { return s ? parseInt(s.slice(0, 4), 10) : 0; }
function dateDiffDays(a, b) {
  if (!a || !b) return 0;
  var ad = new Date(a + "T00:00:00Z");
  var bd = new Date(b + "T00:00:00Z");
  return Math.round(Math.abs(ad - bd) / 86400000);
}
function normalizeTitleKey(text) {
  return String(text || "").toLowerCase().trim().replace(/[\s\-–—:：'"!?,.&／/·・()\[\]{}]+/g, "");
}
function isLikelyTmdbMismatch(whitelistDate, primaryReleaseDate, twTheatricalDate) {
  if (!whitelistDate) return false;
  if (primaryReleaseDate) {
    var yearGap = Math.abs(dateYear(primaryReleaseDate) - dateYear(whitelistDate));
    if (yearGap > 2) return true;
  }
  if (twTheatricalDate && dateDiffDays(twTheatricalDate, whitelistDate) > 120) return true;
  return false;
}
function formatDate(d) {
  if (!d) return "";
  var p = d.split("-");
  return p[0] + "/" + p[1] + "/" + p[2];
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
  var statusEl = document.getElementById("data-status");
  if (!statusEl) return;
  var label = statusEl.querySelector(".refresh-label");
  if (!label) return;
  var formatted = formatUpdateTime(generatedAt);
  label.textContent = formatted ? "更新於 " + formatted : "靜態資料模式";
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
function emptyDynamicWhitelist() {
  return {
    tmdb_ids: [],
    tw_release_dates: {},
    titles_zh: {},
    resolved_by_atmovies: {},
    checked_candidates: {}
  };
}
function normalizeDynamicWhitelist(data) {
  var base = emptyDynamicWhitelist();
  if (!data || typeof data !== "object") return base;
  if (Array.isArray(data.tmdb_ids)) base.tmdb_ids = data.tmdb_ids.slice();
  if (data.tw_release_dates && typeof data.tw_release_dates === "object") base.tw_release_dates = data.tw_release_dates;
  if (data.titles_zh && typeof data.titles_zh === "object") base.titles_zh = data.titles_zh;
  if (data.resolved_by_atmovies && typeof data.resolved_by_atmovies === "object") base.resolved_by_atmovies = data.resolved_by_atmovies;
  if (data.checked_candidates && typeof data.checked_candidates === "object") base.checked_candidates = data.checked_candidates;
  return base;
}
function loadDynamicWhitelist() {
  try {
    var raw = localStorage.getItem(DYNAMIC_WHITELIST_KEY);
    if (!raw) return emptyDynamicWhitelist();
    return normalizeDynamicWhitelist(JSON.parse(raw));
  } catch(e) {
    return emptyDynamicWhitelist();
  }
}
function saveDynamicWhitelist(data) {
  try { localStorage.setItem(DYNAMIC_WHITELIST_KEY, JSON.stringify(normalizeDynamicWhitelist(data))); } catch(e) {}
}
function mergeWhitelistData(staticData) {
  var merged = {
    tmdb_ids: (staticData && staticData.tmdb_ids ? staticData.tmdb_ids.slice() : []),
    tw_release_dates: Object.assign({}, staticData && staticData.tw_release_dates ? staticData.tw_release_dates : {}),
    titles_zh: Object.assign({}, staticData && staticData.titles_zh ? staticData.titles_zh : {})
  };
  var dynamic = loadDynamicWhitelist();
  dynamic.tmdb_ids.forEach(function(id) {
    if (merged.tmdb_ids.indexOf(id) === -1) merged.tmdb_ids.push(id);
  });
  Object.keys(dynamic.tw_release_dates).forEach(function(id) {
    merged.tw_release_dates[id] = dynamic.tw_release_dates[id];
  });
  Object.keys(dynamic.titles_zh).forEach(function(id) {
    merged.titles_zh[id] = dynamic.titles_zh[id];
  });
  return merged;
}
function escHtml(s) {
  return String(s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}

function tmdbFetch(path, params, noRegion) {
  return Promise.reject(new Error("Static data mode"));
}

// 用 TMDB ID 抓電影,並判斷該分到 now 還是 soon (依台灣上映日期)
function fetchByIdsWithTwBucket(ids) {
  return Promise.resolve({ nowItems: [], soonItems: [] });
}

function fetchPages(path, params, maxPages, noRegion) {
  if (!maxPages) maxPages = 3;
  return tmdbFetch(path, Object.assign({}, params, { page: 1 }), noRegion).then(function(first) {
    var total = Math.min(first.total_pages, maxPages);
    var promises = [];
    for (var i = 2; i <= total; i++) promises.push(tmdbFetch(path, Object.assign({}, params, { page: i }), noRegion));
    return Promise.all(promises).then(function(rest) {
      var all = [first].concat(rest);
      var results = [];
      for (var j = 0; j < all.length; j++) results = results.concat(all[j].results);
      return results;
    });
  });
}

function getDetail(id) {
  var movie = findMovieInLists(id);
  if (!movie) return Promise.resolve({});
  if (movie.detail) return Promise.resolve(movie.detail);
  return Promise.resolve({
    duration: movie.duration || "",
    genres: movie.genre || [],
    synopsis: movie.synopsis || "",
    poster: movie.poster || null,
    backdrop: movie.backdrop || null,
    voteAverage: movie.voteAverage || "",
    trailerKey: movie.trailerKey || null,
    imdbId: movie.imdbId || "",
    countries: movie.countries || [],
    cast: movie.cast || [],
    crew: movie.crew || [],
    budget: movie.budget || 0,
    revenue: movie.revenue || 0,
    status: movie.status || "",
    origLang: movie.origLang || "",
    origTitle: movie.origTitle || "",
    platforms: movie.platforms || []
  });
}

function extractTwTheatricalDate(d) {
  if (!d.release_dates || !d.release_dates.results) return "";
  for (var i = 0; i < d.release_dates.results.length; i++) {
    var entry = d.release_dates.results[i];
    if (entry.iso_3166_1 !== "TW" || !entry.release_dates) continue;
    var theatrical = entry.release_dates.filter(function(r) { return r.type === 3; });
    if (!theatrical.length) return "";
    theatrical.sort(function(a, b) { return b.release_date > a.release_date ? 1 : -1; });
    return theatrical[0].release_date.split("T")[0];
  }
  return "";
}

function getBasicDetail(id) {
  return getDetail(id).then(function(detail) {
    return {
      duration: detail.duration || "",
      genres: detail.genres || [],
      synopsis: detail.synopsis || "",
      poster: detail.poster || null,
      backdrop: detail.backdrop || null,
      voteAverage: detail.voteAverage || "",
      imdbId: detail.imdbId || "",
      primaryReleaseDate: "",
      trailerKey: detail.trailerKey || null,
      cast: detail.cast || [],
      crew: detail.crew || [],
      budget: detail.budget || 0,
      revenue: detail.revenue || 0,
      status: detail.status || "",
      origLang: detail.origLang || "",
      origTitle: detail.origTitle || "",
      platforms: detail.platforms || [],
      twReleaseDate: ""
    };
  });
}

function fetchMovieWithTwInfo(id) {
  return tmdbFetch("/movie/" + id, { append_to_response: "release_dates" }).then(function(d) {
    return { movie: d, twReleaseDate: extractTwTheatricalDate(d) };
  }).catch(function() { return null; });
}

function scoreAtmoviesCandidateResult(candidate, result) {
  var zhNorm = normalizeTitleKey(candidate.title_zh);
  var enNorm = normalizeTitleKey(candidate.title_en);
  var titleNorm = normalizeTitleKey(result.title);
  var originalNorm = normalizeTitleKey(result.original_title);
  var score = 0;

  if (zhNorm && (titleNorm === zhNorm || originalNorm === zhNorm)) score += 60;
  else if (zhNorm && (
    titleNorm.indexOf(zhNorm) === 0 || originalNorm.indexOf(zhNorm) === 0 ||
    zhNorm.indexOf(titleNorm) === 0 || zhNorm.indexOf(originalNorm) === 0
  )) score += 25;

  if (enNorm && (titleNorm === enNorm || originalNorm === enNorm)) score += 90;
  else if (enNorm && (
    titleNorm.indexOf(enNorm) >= 0 || originalNorm.indexOf(enNorm) >= 0 ||
    enNorm.indexOf(titleNorm) >= 0 || enNorm.indexOf(originalNorm) >= 0
  )) score += 35;

  var candidateYear = dateYear(candidate.release_date_tw || "");
  var resultYear = dateYear(result.release_date || "");
  if (candidateYear && resultYear) {
    var gap = Math.abs(candidateYear - resultYear);
    if (gap === 0) score += 20;
    else if (gap === 1) score += 10;
    else if (gap > 2) score -= 20;
  }

  return score;
}

function candidateDateMatches(tmdbDate, atmoviesDate) {
  if (!tmdbDate || !atmoviesDate) return false;
  return dateDiffDays(tmdbDate, atmoviesDate) <= 14;
}

function resolveAtmoviesSearchCandidate(candidate, results, index) {
  if (!results || index >= results.length) return Promise.resolve(null);
  return fetchMovieWithTwInfo(results[index].id).then(function(info) {
    if (info && candidateDateMatches(info.twReleaseDate, candidate.release_date_tw)) return info;
    return resolveAtmoviesSearchCandidate(candidate, results, index + 1);
  });
}

function searchAtmoviesCandidateOnTmdb(candidate) {
  var queries = [];
  if (candidate.title_zh) queries.push(candidate.title_zh);
  if (candidate.title_en) queries.push(candidate.title_en);
  if (!queries.length) return Promise.resolve(null);

  var year = dateYear(candidate.release_date_tw || "");
  return Promise.all(queries.map(function(query) {
    var params = { query: query };
    if (year) params.year = year;
    return tmdbFetch("/search/movie", params, true).catch(function() { return { results: [] }; });
  })).then(function(responses) {
    var seen = {};
    var combined = [];
    responses.forEach(function(response) {
      var items = response && response.results ? response.results : [];
      items.forEach(function(item) {
        if (!item || seen[item.id]) return;
        seen[item.id] = true;
        combined.push(item);
      });
    });
    combined.sort(function(a, b) {
      return scoreAtmoviesCandidateResult(candidate, b) - scoreAtmoviesCandidateResult(candidate, a);
    });
    combined = combined.filter(function(item) { return scoreAtmoviesCandidateResult(candidate, item) >= 35; }).slice(0, 3);
    return resolveAtmoviesSearchCandidate(candidate, combined, 0);
  });
}

function candidatePriorityValue(candidate) {
  if (!candidate || !candidate.release_date_tw) return Number.MAX_SAFE_INTEGER;
  var target = new Date(candidate.release_date_tw + "T00:00:00Z").getTime();
  var todayMs = new Date(today() + "T00:00:00Z").getTime();
  var diff = Math.abs(target - todayMs);
  return diff + (candidate.source_bucket === "missing_tw_date" ? 0 : 1000000);
}

function candidateRefreshLog(message, details) {
  if (details !== undefined) console.log("[Candidate refresh]", message, details);
  else console.log("[Candidate refresh]", message);
}

function clearCandidateRefreshTimer() {
  if (!candidateRefreshTimer) return;
  clearTimeout(candidateRefreshTimer);
  candidateRefreshTimer = null;
}

function loadAtmoviesCandidatesPayload() {
  if (!candidateRefreshPayloadPromise) {
    candidateRefreshPayloadPromise = fetch("data/atmovies-candidates.json").then(function(r) {
      return r.ok ? r.json() : { candidates: [] };
    }).catch(function() {
      return { candidates: [] };
    }).then(function(payload) {
      var candidates = payload && payload.candidates ? payload.candidates : [];
      candidateRefreshLog("Loaded candidate pool: " + candidates.length + " movies");
      return candidates;
    });
  }
  return candidateRefreshPayloadPromise;
}

function getAtmoviesCandidateStats(candidates, dynamicStore) {
  var recentPast = daysAgo(60);
  var nearFuture = daysLater(120);
  var stats = {
    total: 0,
    invalid: 0,
    out_of_window: 0,
    resolved: 0,
    ttl_blocked: 0,
    eligible: []
  };
  candidates.forEach(function(candidate) {
    if (!candidate || !candidate.atmovies_id || !candidate.release_date_tw) {
      stats.invalid++;
      return;
    }
    stats.total++;
    if (candidate.release_date_tw < recentPast || candidate.release_date_tw > nearFuture) {
      stats.out_of_window++;
      return;
    }
    if (dynamicStore.resolved_by_atmovies[candidate.atmovies_id]) {
      stats.resolved++;
      return;
    }
    var checked = dynamicStore.checked_candidates[candidate.atmovies_id];
    if (checked && Date.now() - checked.checked_at <= CANDIDATE_CHECK_TTL) {
      stats.ttl_blocked++;
      return;
    }
    stats.eligible.push(candidate);
  });
  stats.eligible.sort(function(a, b) {
    return candidatePriorityValue(a) - candidatePriorityValue(b);
  });
  return stats;
}

function describeCandidateStopReason(stats) {
  if (!stats || stats.total === 0) return "Stopped: candidate pool is empty.";
  if (stats.eligible.length > 0) return "";
  if (stats.ttl_blocked > 0 && stats.resolved === 0) {
    return "Stopped: waiting for TTL expiry; " + stats.ttl_blocked + " candidate(s) were checked recently.";
  }
  if (stats.ttl_blocked > 0) {
    return "Stopped: no eligible candidates left; " + stats.resolved + " resolved, " + stats.ttl_blocked + " waiting for TTL expiry.";
  }
  if (stats.resolved > 0 && stats.out_of_window > 0) {
    return "Stopped: all current candidates are either resolved (" + stats.resolved + ") or outside the date window (" + stats.out_of_window + ").";
  }
  if (stats.resolved > 0) {
    return "Stopped: all in-range candidates are already resolved (" + stats.resolved + ").";
  }
  if (stats.out_of_window > 0) {
    return "Stopped: all remaining candidates are outside the date window (" + stats.out_of_window + ").";
  }
  return "Stopped: no eligible candidates left for this session.";
}

function rememberCandidateCheck(dynamicStore, candidate, status, tmdbId) {
  dynamicStore.checked_candidates[candidate.atmovies_id] = {
    checked_at: Date.now(),
    status: status,
    tmdb_id: tmdbId || null
  };
}

function addResolvedCandidateToDynamicWhitelist(dynamicStore, candidate, movie, twReleaseDate) {
  var tmdbId = movie.id;
  var tmdbIdStr = String(tmdbId);
  var effectiveDate = candidate.release_date_tw || twReleaseDate || "";
  var effectiveTitleZh = candidate.title_zh || movie.title || movie.original_title || "";

  if (dynamicStore.tmdb_ids.indexOf(tmdbId) === -1) dynamicStore.tmdb_ids.push(tmdbId);
  if (effectiveDate) dynamicStore.tw_release_dates[tmdbIdStr] = effectiveDate;
  if (effectiveTitleZh) dynamicStore.titles_zh[tmdbIdStr] = effectiveTitleZh;
  dynamicStore.resolved_by_atmovies[candidate.atmovies_id] = {
    tmdb_id: tmdbId,
    title_zh: effectiveTitleZh,
    release_date_tw: effectiveDate,
    resolved_at: Date.now()
  };
  rememberCandidateCheck(dynamicStore, candidate, "resolved", tmdbId);
}

function mergeResolvedMovieIntoLists(movieData, candidate, twReleaseDate) {
  if (!movieData || !movieData.id) return null;
  var tmdbIdStr = String(movieData.id);
  var effectiveDate = candidate.release_date_tw || twReleaseDate || "";
  var effectiveTitleZh = candidate.title_zh || movieData.title || movieData.original_title || "";

  if (effectiveDate) WHITELIST_TW_DATES[tmdbIdStr] = effectiveDate;
  if (effectiveTitleZh) WHITELIST_TITLES_ZH[tmdbIdStr] = effectiveTitleZh;

  var existing = findMovieInLists(movieData.id);
  if (!existing) {
    existing = buildBasicMovie(movieData);
    existing.releaseDate = effectiveDate || existing.releaseDate;
    existing.twReleaseDateVerified = !!existing.releaseDate;
    existing.titleZh = effectiveTitleZh || existing.titleZh;
    existing.titleEn = movieData.original_title || existing.titleEn;
    var bucket = classifyReleaseBucket(existing.releaseDate);
    if (bucket === "now") allMovies.now.push(existing);
    else if (bucket === "soon") allMovies.soon.push(existing);
    else return null;
  } else {
    existing.releaseDate = effectiveDate || existing.releaseDate;
    existing.twReleaseDateVerified = !!existing.releaseDate;
    existing.titleZh = effectiveTitleZh || existing.titleZh;
  }
  return existing;
}

function checkAtmoviesCandidate(dynamicStore, candidate) {
  var resolver = candidate.tmdb_id
    ? fetchMovieWithTwInfo(candidate.tmdb_id)
    : searchAtmoviesCandidateOnTmdb(candidate);

  return resolver.then(function(info) {
    if (!info || !info.movie || !candidateDateMatches(info.twReleaseDate, candidate.release_date_tw)) {
      rememberCandidateCheck(dynamicStore, candidate, "no_match", candidate.tmdb_id || null);
      candidateRefreshLog("No match:", candidate.title_zh || candidate.title_en || candidate.atmovies_id);
      return false;
    }

    addResolvedCandidateToDynamicWhitelist(dynamicStore, candidate, info.movie, info.twReleaseDate);
    var movie = mergeResolvedMovieIntoLists(info.movie, candidate, info.twReleaseDate);
    candidateRefreshLog("Resolved:", {
      title: candidate.title_zh || candidate.title_en || candidate.atmovies_id,
      tmdbId: info.movie.id,
      tmdbTitle: info.movie.title || info.movie.original_title || ""
    });
    if (!movie) return false;

    return getBasicDetail(movie.id).then(function(detail) {
      applyMovieDetail(movie, detail);
      return true;
    }).catch(function() {
      return true;
    });
  }).catch(function() {
    rememberCandidateCheck(dynamicStore, candidate, "error", candidate.tmdb_id || null);
    candidateRefreshLog("Error while checking:", candidate.title_zh || candidate.title_en || candidate.atmovies_id);
    return false;
  });
}

function runAtmoviesCandidateBatch(limit, reason) {
  if (candidateRefreshInFlight) {
    candidateRefreshLog("Skip batch: another batch is still running.");
    return Promise.resolve({ processed: 0, changed: false, stop: false, reason: "busy" });
  }
  candidateRefreshInFlight = true;
  return loadAtmoviesCandidatesPayload().then(function(candidates) {
    var dynamicStore = loadDynamicWhitelist();
    var remainingQuota = CANDIDATE_SESSION_MAX_CHECKS - candidateRefreshChecksThisSession;
    var batchLimit = Math.min(limit, remainingQuota);
    if (batchLimit <= 0) return { processed: 0, changed: false, stop: true, reason: "limit" };
    var stats = getAtmoviesCandidateStats(candidates, dynamicStore);
    var batch = stats.eligible.slice(0, batchLimit);
    if (!batch.length) {
      candidateRefreshLog(describeCandidateStopReason(stats), {
        total: stats.total,
        resolved: stats.resolved,
        ttlBlocked: stats.ttl_blocked,
        outOfWindow: stats.out_of_window,
        invalid: stats.invalid
      });
      return { processed: 0, changed: false, stop: true, reason: "empty" };
    }

    candidateRefreshLog("Checking " + batch.length + " candidate(s) [" + reason + "]", batch.map(function(candidate) {
      return (candidate.title_zh || candidate.title_en || candidate.atmovies_id) + " (" + candidate.release_date_tw + ")";
    }));

    var changed = false;
    return batch.reduce(function(chain, candidate) {
      return chain.then(function() {
        return checkAtmoviesCandidate(dynamicStore, candidate).then(function(didChange) {
          if (didChange) changed = true;
        });
      });
    }, Promise.resolve()).then(function() {
      candidateRefreshChecksThisSession += batch.length;
      saveDynamicWhitelist(dynamicStore);
      if (changed) normalizeMovieBuckets(false, false, false);
      candidateRefreshLog("Batch complete: " + candidateRefreshChecksThisSession + "/" + CANDIDATE_SESSION_MAX_CHECKS + " checked this page load.");
      return {
        processed: batch.length,
        changed: changed,
        stop: candidateRefreshChecksThisSession >= CANDIDATE_SESSION_MAX_CHECKS,
        reason: candidateRefreshChecksThisSession >= CANDIDATE_SESSION_MAX_CHECKS ? "limit" : ""
      };
    });
  }).catch(function(err) {
    console.warn("Candidate refresh failed", err);
    return { processed: 0, changed: false, stop: true, reason: "error" };
  }).then(function(result) {
    candidateRefreshInFlight = false;
    return result;
  });
}

function scheduleNextCandidateRefreshTick() {
  clearCandidateRefreshTimer();
  if (candidateRefreshChecksThisSession >= CANDIDATE_SESSION_MAX_CHECKS) {
    candidateRefreshLog("Stopped background checks: reached session cap of " + CANDIDATE_SESSION_MAX_CHECKS + ".");
    return;
  }
  candidateRefreshTimer = setTimeout(function() {
    runAtmoviesCandidateBatch(CANDIDATE_DRIP_BATCH_LIMIT, "drip").then(function(result) {
      if (!result || result.stop || result.processed === 0) {
        if (result && result.reason === "limit") {
          candidateRefreshLog("Stopped background checks: reached session cap of " + CANDIDATE_SESSION_MAX_CHECKS + ".");
        }
        return;
      }
      scheduleNextCandidateRefreshTick();
    });
  }, CANDIDATE_DRIP_INTERVAL_MS);
  candidateRefreshLog("Next background check scheduled in " + Math.round(CANDIDATE_DRIP_INTERVAL_MS / 1000) + "s.");
}

function backgroundRefreshAtmoviesCandidates() {
  return;
}

function parseOmdbRatings(d) {
  var imdb = (d.imdbRating && d.imdbRating !== "N/A") ? d.imdbRating : "";
  var rt = "";
  if (d.Ratings) {
    for (var i = 0; i < d.Ratings.length; i++) {
      if (d.Ratings[i].Source === "Rotten Tomatoes" && d.Ratings[i].Value !== "N/A") { rt = d.Ratings[i].Value; break; }
    }
  }
  var mc = (d.Metascore && d.Metascore !== "N/A") ? d.Metascore : "";
  return { imdb: imdb, rt: rt, mc: mc };
}

function getImdb(imdbId, options) {
  return Promise.resolve({ imdb: "", rt: "", mc: "" });
}

function getExternalIds(id) {
  var movie = findMovieInLists(id);
  return Promise.resolve({ imdb_id: movie && movie.imdbId ? movie.imdbId : "" });
}

function dedup(arr) {
  var map = {}; var result = [];
  for (var i = 0; i < arr.length; i++) if (!map[arr[i].id]) { map[arr[i].id] = true; result.push(arr[i]); }
  return result;
}

function filteredSignature() {
  return filtered.now.map(function(m) { return m.id; }).join(",") + "|" + filtered.soon.map(function(m) { return m.id; }).join(",");
}

function buildBasicMovie(m) {
  var whitelistTitleZh = WHITELIST_TITLES_ZH[String(m.id)] || "";
  var posterUrl = m.poster_path ? IMG_W + m.poster_path : null;
  var backdropUrl = m.backdrop_path ? IMG_BG + m.backdrop_path : null;
  return {
    id: m.id, titleZh: whitelistTitleZh || m.title || "", titleEn: m.original_title || "",
    releaseDate: m.release_date || "",
    twReleaseDateVerified: !!m.release_date,
    poster: posterUrl || backdropUrl,
    posterIsBackdrop: !posterUrl && !!backdropUrl,
    backdrop: backdropUrl,
    voteAverage: m.vote_average ? m.vote_average.toFixed(1) : "",
    genre: [], duration: 0, synopsis: "", imdb: "", rt: "", mc: "", trailerKey: null,
    cast: [], crew: [], budget: 0, revenue: 0, status: "",
    origLang: m.original_language || "", origTitle: m.original_title || "",
    platforms: [], popularity: m.popularity || 0, imdbId: ""
  };
}

function classifyReleaseBucket(releaseDate) {
  if (!releaseDate) return "";
  if (releaseDate >= daysAgo(45) && releaseDate <= today()) return "now";
  if (releaseDate >= daysLater(1) && releaseDate <= daysLater(180)) return "soon";
  return "";
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

function findMovieInLists(id) {
  var found = null;
  ["now","soon"].forEach(function(t) {
    if (found) return;
    for (var i = 0; i < allMovies[t].length; i++) {
      if (allMovies[t][i].id === id) { found = allMovies[t][i]; break; }
    }
  });
  return found;
}

function updateCardGenre(id, genre) {
  var el = document.querySelector('#card-' + id + ' .card-hover-genre');
  if (el) el.textContent = normalizeGenreList(genre).slice(0, 2).join(' / ');
}

function updateCardDate(id, date) {
  var el = document.querySelector('#card-' + id + ' .card-date');
  if (el && date) el.textContent = formatDate(date);
}

function applyMovieDetail(movie, detail) {
  if (!movie || !detail) return;
  movie.genre = normalizeGenreList(detail.genres || []);
  detail.genres = movie.genre.slice();
  movie.duration = detail.duration || 0;
  movie.synopsis = detail.synopsis || "";
  movie.platforms = detail.platforms || [];
  movie.imdbId = detail.imdbId || "";
  if (detail.voteAverage) movie.voteAverage = detail.voteAverage;
  if (detail.poster) {
    movie.poster = detail.poster;
    movie.posterIsBackdrop = false;
  } else if (!movie.poster && detail.backdrop) {
    movie.poster = detail.backdrop;
    movie.posterIsBackdrop = true;
  }
  if (detail.backdrop && !movie.backdrop) movie.backdrop = detail.backdrop;
  var whitelistDate = WHITELIST_TW_DATES[String(movie.id)] || "";
  var whitelistTitleZh = WHITELIST_TITLES_ZH[String(movie.id)] || "";
  if (whitelistTitleZh) movie.titleZh = whitelistTitleZh;
  movie.autoExcluded = isLikelyTmdbMismatch(whitelistDate, detail.primaryReleaseDate || "", detail.twReleaseDate || "");
  if (whitelistDate) {
    movie.releaseDate = whitelistDate;
    movie.twReleaseDateVerified = true;
    updateCardDate(movie.id, movie.releaseDate);
  } else if (detail.twReleaseDate) {
    movie.releaseDate = detail.twReleaseDate;
    movie.twReleaseDateVerified = true;
    updateCardDate(movie.id, movie.releaseDate);
  } else {
    movie.twReleaseDateVerified = false;
  }
  updateCardGenre(movie.id, movie.genre);
}

function normalizeMovieBuckets(skipNowFilter, deferInitialRender, forceRefreshRatings) {
  var todayStr = today();
  var nowToSoon = [];
  var soonToNow = [];

  if (!skipNowFilter) {
    allMovies.now = allMovies.now.filter(function(m) {
      if (m.autoExcluded) return false;
      if (m.releaseDate && m.releaseDate > todayStr) { nowToSoon.push(m); return false; }
      return (!m.platforms || m.platforms.length === 0) && (m.duration === 0 || m.duration > 60);
    });
  }

  var soonIdSet = {};
  allMovies.soon.forEach(function(m) { soonIdSet[m.id] = true; });
  nowToSoon.forEach(function(m) { if (!soonIdSet[m.id]) { allMovies.soon.push(m); } });

  allMovies.soon = allMovies.soon.filter(function(m) {
    if (m.autoExcluded) return false;
    if (m.releaseDate && m.releaseDate <= todayStr) { soonToNow.push(m); return false; }
    var hasFutureTheatrical = m.twReleaseDateVerified && m.releaseDate && m.releaseDate >= todayStr;
    if (!hasFutureTheatrical) return false;
    return (hasFutureTheatrical || !m.platforms || m.platforms.length === 0) && (m.duration === 0 || m.duration > 60);
  });

  var nowIdSet = {};
  allMovies.now.forEach(function(m) { nowIdSet[m.id] = true; });
  soonToNow.forEach(function(m) { if (!nowIdSet[m.id]) { allMovies.now.push(m); } });

  var beforeSig = deferInitialRender ? "" : filteredSignature();
  applyFilters(true);
  if (deferInitialRender || beforeSig !== filteredSignature()) renderGrids();
  buildGenreFilters();
  saveCache(allMovies);
  fetchImdbInBackground(getMoviesForRatingRefresh(!!forceRefreshRatings), { forceRefresh: !!forceRefreshRatings });
}


function fetchBasicLists() {
  return Promise.all([
    fetchPages("/discover/movie", { "release_date.gte": daysAgo(45), "release_date.lte": today(), sort_by: "release_date.desc", with_release_type: "3|2", region: "TW", watch_region: "TW" }, 8),
    fetchPages("/discover/movie", { "primary_release_date.gte": daysAgo(45), "primary_release_date.lte": today(), sort_by: "popularity.desc", with_release_type: "2|3", with_original_language: "en" }, 2, true),
    fetchPages("/discover/movie", { "release_date.gte": daysLater(1), "release_date.lte": daysLater(180), sort_by: "release_date.asc", with_release_type: "3|2", watch_region: "TW" }, 8),
    fetchPages("/discover/movie", { "primary_release_date.gte": daysLater(1), "primary_release_date.lte": daysLater(180), sort_by: "popularity.desc", with_release_type: "2|3", with_original_language: "en" }, 2, true),
    // 反向白名單: 開眼有的 TMDB ID 清單
    fetch("data/tw-whitelist.json").then(function(r) { return r.ok ? r.json() : { tmdb_ids: [], tw_release_dates: {}, titles_zh: {} }; }).catch(function() { return { tmdb_ids: [], tw_release_dates: {}, titles_zh: {} }; })
  ]).then(function(results) {
    var cutoff45 = daysAgo(45);
    var todayStr = today();
    var tomorrowStr = daysLater(1);
    var soonWhitelistCutoff = daysLater(60);
    var soonCutoff180 = daysLater(180);
    var npA = dedup(results[0]).filter(function(m) { return m.release_date >= cutoff45; });
    var npAIds = {};
    npA.forEach(function(m) { npAIds[m.id] = true; });
    var npB = results[1].filter(function(m) { return !npAIds[m.id] && m.release_date >= cutoff45 && m.popularity > 45; }).slice(0, 20);
    var np = dedup(npA.concat(npB));
    var npIds2 = {};
    np.forEach(function(m) { npIds2[m.id] = true; });
    var csA = dedup(results[2]).filter(function(m) { return !npIds2[m.id]; });
    var csAIds = {};
    csA.forEach(function(m) { csAIds[m.id] = true; });
    var csB = results[3].filter(function(m) { return !csAIds[m.id] && !npIds2[m.id] && m.release_date >= daysLater(1); }).slice(0, 15);
    var cs = dedup(csA.concat(csB));

    var mergedWhitelist = mergeWhitelistData(results[4] || {});
    var whitelistRaw = mergedWhitelist.tmdb_ids ? mergedWhitelist.tmdb_ids : [];
    var whitelist = whitelistRaw.slice();
    WHITELIST_TW_DATES = {};
    WHITELIST_TITLES_ZH = {};
    var whitelistDatesRaw = mergedWhitelist.tw_release_dates ? mergedWhitelist.tw_release_dates : {};
    Object.keys(whitelistDatesRaw).forEach(function(id) {
      WHITELIST_TW_DATES[id] = whitelistDatesRaw[id];
    });
    var whitelistTitlesRaw = mergedWhitelist.titles_zh ? mergedWhitelist.titles_zh : {};
    Object.keys(whitelistTitlesRaw).forEach(function(id) {
      WHITELIST_TITLES_ZH[id] = whitelistTitlesRaw[id];
    });
    var whitelistSet = {};
    whitelist.forEach(function(id) { whitelistSet[id] = true; });

    // 開眼清單作為台灣院線白名單；TMDB 多抓幾頁只用來降低候選片漏抓。
    np = np.filter(function(m) { return !!whitelistSet[m.id]; });
    cs = cs.filter(function(m) {
      if (whitelistSet[m.id]) return true;
      return m.release_date && m.release_date > soonWhitelistCutoff;
    });

    var existingIds = {};
    np.forEach(function(m) { existingIds[m.id] = true; });
    cs.forEach(function(m) { existingIds[m.id] = true; });
    var nowBeforeBackfill = np.length;
    var soonBeforeBackfill = cs.length;

    // 白名單補片: 把 discover 因頁數或排序漏掉的開眼片補回來。
    var whitelistBackfillIds = whitelist.filter(function(id) { return !existingIds[id]; });

    return Promise.all([
      fetchByIdsWithTwBucket(FORCE_INCLUDE_TMDB_IDS),
      fetchByIdsWithTwBucket(whitelistBackfillIds)
    ]).then(function(extraResults) {
      var forced = extraResults[0];
      var whitelistBackfill = extraResults[1];

      // 合併到 np (現正熱映)
      var npExistingIds = {};
      np.forEach(function(m) { npExistingIds[m.id] = true; });
      forced.nowItems.forEach(function(m) {
        if (!npExistingIds[m.id]) {
          np.push(m);
          npExistingIds[m.id] = true;
          console.log("Force included into NOW:", m.title || m.original_title);
        } else {
          console.log("Already in NOW, skip:", m.title || m.original_title);
        }
      });

      // 合併到 cs (即將上映)
      var csExistingIds = {};
      cs.forEach(function(m) { csExistingIds[m.id] = true; });
      forced.soonItems.forEach(function(m) {
        if (!csExistingIds[m.id]) {
          cs.push(m);
          csExistingIds[m.id] = true;
          console.log("Force included into SOON:", m.title || m.original_title);
        } else {
          console.log("Already in SOON, skip:", m.title || m.original_title);
        }
      });

      // 白名單補片: 以開眼上映日為優先，只負責補回 discover 漏掉的片。
      var whitelistMovies = whitelistBackfill.nowItems.concat(whitelistBackfill.soonItems);
      var whitelistSeenIds = {};
      whitelistMovies.forEach(function(m) {
        if (!m || whitelistSeenIds[m.id]) return;
        whitelistSeenIds[m.id] = true;

        var whitelistDate = WHITELIST_TW_DATES[String(m.id)] || "";
        if (whitelistDate) m.release_date = whitelistDate;
        if (!m.release_date) return;

        if (m.release_date >= cutoff45 && m.release_date <= todayStr) {
          if (!npExistingIds[m.id]) {
            np.push(m);
            npExistingIds[m.id] = true;
            console.log("Whitelist backfill into NOW:", m.title || m.original_title);
          }
          return;
        }

        if (m.release_date >= tomorrowStr && m.release_date <= soonCutoff180) {
          if (!csExistingIds[m.id]) {
            cs.push(m);
            csExistingIds[m.id] = true;
            console.log("Whitelist backfill into SOON:", m.title || m.original_title);
          }
        }
      });

      np.sort(function(a, b) {
        return (b.release_date || "").localeCompare(a.release_date || "");
      });
      cs.sort(function(a, b) {
        return (a.release_date || "").localeCompare(b.release_date || "");
      });
      console.log("Now list summary: discover " + nowBeforeBackfill + ", whitelist backfill " + (np.length - nowBeforeBackfill) + ", final " + np.length);
      console.log("Soon list summary: discover " + soonBeforeBackfill + ", whitelist backfill " + (cs.length - soonBeforeBackfill) + ", final " + cs.length);

      return {
        now: np.map(buildBasicMovie),
        soon: cs.map(buildBasicMovie),
        _np: np, _cs: cs
      };
    });
  });
}

function enrichBackground(rawData, skipNowFilter, deferInitialRender, forceRefreshRatings) {
  var nowIds = {}; allMovies.now.forEach(function(m) { nowIds[m.id] = true; });
  var soonIds = {}; allMovies.soon.forEach(function(m) { soonIds[m.id] = true; });
  var npToEnrich = rawData._np.filter(function(r) { return nowIds[r.id]; });
  var csToEnrich = rawData._cs.filter(function(r) { return soonIds[r.id]; });
  var total = npToEnrich.length + csToEnrich.length;
  if (total === 0) {
    normalizeMovieBuckets(skipNowFilter, deferInitialRender, forceRefreshRatings);
    backgroundRefreshAtmoviesCandidates();
    return Promise.resolve();
  }

  return Promise.all(npToEnrich.concat(csToEnrich).map(function(raw) {
    return getBasicDetail(raw.id).then(function(detail) {
      var movie = findMovieInLists(raw.id);
      if (movie) applyMovieDetail(movie, detail);
    }).catch(function() {});
  })).then(function() {
    normalizeMovieBuckets(skipNowFilter, deferInitialRender, forceRefreshRatings);
    backgroundRefreshAtmoviesCandidates();
  });
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
  var metaHTML = '<div class="card-meta"><span class="card-date">' + formatDate(m.releaseDate) + '</span>';
  if (showRatings) {
    var imdbStyle = m.imdb ? '' : ' style="display:none"';
    var rtStyle = m.rt ? '' : ' style="display:none"';
    var mcStyle = m.mc ? '' : ' style="display:none"';
    metaHTML += '<div class="card-badges">';
    metaHTML += '<span class="badge-imdb" id="imdb-' + m.id + '"' + imdbStyle + '>IMDb<span>' + escHtml(m.imdb || '') + '</span></span>';
    metaHTML += '<span class="badge-rt" id="rt-' + m.id + '"' + rtStyle + '>' + rtIconSvg('#e08a82', 'flex-shrink:0;vertical-align:middle;margin-right:2px') + '<span>' + escHtml(m.rt || '') + '</span></span>';
    metaHTML += '<span class="badge-mc" id="mc-' + m.id + '"' + mcStyle + '>MT<span>' + escHtml(m.mc || '') + '</span></span>';
    if (m.voteAverage) metaHTML += '<span class="badge-tmdb">TMDB ' + tmdbScore(m.voteAverage) + '</span>';
    metaHTML += '</div>';
  }
  metaHTML += '</div>';
  return '<div class="movie-card fade-in" id="card-' + m.id + '">' +
    '<div class="card-img-wrap" onclick="openModal(' + m.id + ')">' + imgHTML +
    '<div class="card-hover-overlay"><span class="card-hover-genre">' + escHtml(normalizeGenreList(m.genre).slice(0,2).join(' / ')) + '</span></div></div>' +
    '<div class="card-info"><p class="card-title">' + escHtml(m.titleZh) + '</p>' + titleEn +
    '<div class="card-spacer"></div>' + metaHTML + '</div></div>';
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
  var subtitleHTML = subtitleParts.length ? '<p class="list-subtitle">' + escHtml(subtitleParts.join(' · ')) + '</p>' : '';
  var badgesHTML = '';
  if (showRatings) {
    var imdbStyle = m.imdb ? '' : ' style="display:none"';
    var rtStyle = m.rt ? '' : ' style="display:none"';
    var mcStyle = m.mc ? '' : ' style="display:none"';
    badgesHTML += '<span class="badge-imdb" id="imdb-' + m.id + '"' + imdbStyle + '>IMDb<span>' + escHtml(m.imdb || '') + '</span></span>';
    badgesHTML += '<span class="badge-rt" id="rt-' + m.id + '"' + rtStyle + '>' + rtIconSvg('#e08a82', 'flex-shrink:0;vertical-align:middle;margin-right:2px') + '<span>' + escHtml(m.rt || '') + '</span></span>';
    badgesHTML += '<span class="badge-mc" id="mc-' + m.id + '"' + mcStyle + '>MT<span>' + escHtml(m.mc || '') + '</span></span>';
    if (m.voteAverage) badgesHTML += '<span class="badge-tmdb">TMDB ' + tmdbScore(m.voteAverage) + '</span>';
  }
  return '<div class="list-item fade-in" id="card-' + m.id + '" onclick="openModal(' + m.id + ')">' +
    imgHTML +
    '<div class="list-info"><p class="list-title">' + escHtml(m.titleZh) + '</p>' + subtitleHTML + (m.releaseDate ? '<p class="list-date">' + formatDate(m.releaseDate) + '</p>' : '') + '</div>' +
    '<div class="list-badges">' + badgesHTML + '</div>' +
    '</div>';
}

function renderGrids() {
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
  scrollToResults();
  var countEl = document.getElementById("movie-count");
  if (countEl && filtered) countEl.textContent = (filtered[currentTab] ? filtered[currentTab].length : 0) + " 部";
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

function sortMovies(skipRender) {
  tabSortState[currentTab] = document.getElementById("sort-select").value;
  ["now","soon"].forEach(function(t) {
    var v = tabSortState[t];
    filtered[t] = filtered[t].slice().sort(function(a, b) {
      if (v === "date_desc") return b.releaseDate > a.releaseDate ? 1 : -1;
      if (v === "date_asc") return a.releaseDate > b.releaseDate ? 1 : -1;
      if (v === "tmdb_desc") return (parseFloat(b.voteAverage)||0) - (parseFloat(a.voteAverage)||0);
      if (v === "tmdb_asc") return (parseFloat(a.voteAverage)||0) - (parseFloat(b.voteAverage)||0);
      if (v === "imdb_desc") return (parseFloat(b.imdb)||0) - (parseFloat(a.imdb)||0);
      if (v === "imdb_asc") return (parseFloat(a.imdb)||0) - (parseFloat(b.imdb)||0);
      return 0;
    });
  });
  if (!skipRender) renderGrids();
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

function switchTab(t) {
  currentTab = t;
  try { sessionStorage.setItem("wt_active_tab", t); } catch(e) {}
  try { history.replaceState(null, '', t === 'now' ? '#' : '#' + t); } catch(e) {}
  document.getElementById("sort-select").value = tabSortState[t];
  document.querySelectorAll(".tab-content").forEach(function(el) { el.classList.remove("active"); });
  document.querySelectorAll(".tab-btn").forEach(function(el) { el.classList.remove("active"); });
  document.getElementById("content-" + t).classList.add("active");
  document.getElementById("tab-" + t).classList.add("active");
  moveTabIndicator(t);
  var countEl = document.getElementById("movie-count");
  if (countEl && filtered) countEl.textContent = (filtered[t] ? filtered[t].length : 0) + " 部";
}

var modalSwipeState = {
  tracking: false,
  active: false,
  pointerId: null,
  startX: 0,
  startY: 0,
  deltaX: 0,
  deltaY: 0,
  lastX: 0,
  lastTime: 0,
  velocityX: 0,
  closing: false
};
var lockedBodyScrollY = 0;
var modalVerticalTouchState = {
  active: false,
  pointerId: null,
  startY: 0,
  lastY: 0
};

function isTouchModalViewport() {
  return window.matchMedia("(max-width: 1024px)").matches;
}

function resetModalSwipe() {
  modalSwipeState.tracking = false;
  modalSwipeState.active = false;
  modalSwipeState.pointerId = null;
  modalSwipeState.startX = 0;
  modalSwipeState.startY = 0;
  modalSwipeState.deltaX = 0;
  modalSwipeState.deltaY = 0;
  modalSwipeState.lastX = 0;
  modalSwipeState.lastTime = 0;
  modalSwipeState.velocityX = 0;
  modalSwipeState.closing = false;
  var modal = document.getElementById("detail-modal");
  if (!modal) return;
  modal.classList.remove("swiping");
  modal.classList.remove("swipe-closing");
  modal.style.removeProperty("--modal-swipe-offset");
  modal.style.removeProperty("--modal-swipe-progress");
}

function lockBodyScroll() {
  lockedBodyScrollY = window.scrollY || window.pageYOffset || 0;
  document.documentElement.style.overflow = "hidden";
  document.documentElement.style.overscrollBehavior = "none";
  document.body.style.position = "fixed";
  document.body.style.top = -lockedBodyScrollY + "px";
  document.body.style.left = "0";
  document.body.style.right = "0";
  document.body.style.width = "100%";
  document.body.style.overflow = "hidden";
}

function unlockBodyScroll() {
  document.documentElement.style.overflow = "";
  document.documentElement.style.overscrollBehavior = "";
  document.body.style.position = "";
  document.body.style.top = "";
  document.body.style.left = "";
  document.body.style.right = "";
  document.body.style.width = "";
  document.body.style.overflow = "";
  window.scrollTo(0, lockedBodyScrollY || 0);
}

function finishSwipeClose() {
  currentModalMovieId = null;
  var modal = document.getElementById("detail-modal");
  if (modal) modal.classList.remove("open");
  resetModalSwipe();
  unlockBodyScroll();
}

function animateModalSwipeClose() {
  var modal = document.getElementById("detail-modal");
  if (!modal || modalSwipeState.closing) return;
  modalSwipeState.closing = true;
  modal.classList.remove("swiping");
  modal.classList.add("swipe-closing");
  modal.style.setProperty("--modal-swipe-progress", "0");
  window.requestAnimationFrame(function() {
    modal.style.setProperty("--modal-swipe-offset", window.innerWidth + "px");
  });
  window.setTimeout(finishSwipeClose, 240);
}

function buildModalHeroSlot(imageUrl) {
  if (!imageUrl) return "";
  return '<img src="' + escHtml(imageUrl) + '" style="position:absolute;inset:-40px;width:calc(100% + 80px);height:calc(100% + 80px);object-fit:cover;object-position:top center;opacity:1;filter:blur(30px);will-change:transform"/>' +
    '<div style="position:absolute;inset:0;background:linear-gradient(to bottom,rgba(0,0,0,0) 0%,rgba(0,0,0,0.08) 44%,rgba(0,0,0,0.30) 58%,rgba(0,0,0,0.70) 79%,rgba(0,0,0,0.94) 100%)"></div>';
}

function buildModalLoadingState(movie) {
  var heroImage = movie && (movie.backdrop || movie.poster) ? (movie.backdrop || movie.poster) : "";
  var title = movie && (movie.titleZh || movie.titleEn) ? (movie.titleZh || movie.titleEn) : "載入中";
  var subtitle = [];
  if (movie && movie.releaseDate) subtitle.push(formatDate(movie.releaseDate));
  if (movie && movie.duration) subtitle.push(movie.duration + "分鐘");
  return {
    heroSlot: buildModalHeroSlot(heroImage),
    content: '<div class="fade-in"><div class="modal-hero"><div class="modal-hero-media">' +
      (heroImage
        ? '<img class="modal-hero-img" src="' + escHtml(heroImage) + '" fetchpriority="high" decoding="async"/>'
        : '<div style="width:100%;height:100%" class="skeleton"></div>') +
      '</div><div class="modal-hero-fade"></div><div class="modal-hero-info"><div class="modal-info-group">' +
      '<h2 class="modal-title">' + escHtml(title) + '</h2>' +
      '<p class="modal-subtitle">' + escHtml(subtitle.join(' · ') || "載入詳細資訊中") + '</p>' +
      '</div></div></div><div class="modal-body"><div style="display:flex;align-items:center;justify-content:center;min-height:180px"><div class="skeleton" style="width:64px;height:64px;border-radius:50%"></div></div></div></div>'
  };
}

function shouldPreventModalOverscroll(modalScroll, deltaY) {
  var maxScrollTop = modalScroll.scrollHeight - modalScroll.clientHeight;
  var atTop = modalScroll.scrollTop <= 0;
  var atBottom = modalScroll.scrollTop >= maxScrollTop - 1;
  return (atTop && deltaY > 0) || (atBottom && deltaY < 0);
}

function initModalSwipe() {
  var modal = document.getElementById("detail-modal");
  var modalScroll = modal ? modal.querySelector(".modal-scroll") : null;
  if (!modal || !modalScroll) return;

  modalScroll.addEventListener("touchstart", function(e) {
    if (!isTouchModalViewport() || !modal.classList.contains("open")) return;
    if (e.touches.length !== 1) return;
    var verticalTouch = e.touches[0];
    modalVerticalTouchState.active = true;
    modalVerticalTouchState.pointerId = verticalTouch.identifier;
    modalVerticalTouchState.startY = verticalTouch.clientY;
    modalVerticalTouchState.lastY = verticalTouch.clientY;
    if (e.target.closest(".cast-row")) return;
    var touch = e.touches[0];
    if (modalSwipeState.closing) return;
    modalSwipeState.tracking = true;
    modalSwipeState.active = false;
    modalSwipeState.pointerId = touch.identifier;
    modalSwipeState.startX = touch.clientX;
    modalSwipeState.startY = touch.clientY;
    modalSwipeState.deltaX = 0;
    modalSwipeState.deltaY = 0;
    modalSwipeState.lastX = touch.clientX;
    modalSwipeState.lastTime = Date.now();
    modalSwipeState.velocityX = 0;
  }, { passive: true });

  modal.addEventListener("touchmove", function(e) {
    if (!isTouchModalViewport() || !modal.classList.contains("open")) return;
    if (!modalVerticalTouchState.active) return;
    var verticalTouch = null;
    for (var i = 0; i < e.touches.length; i++) {
      if (e.touches[i].identifier === modalVerticalTouchState.pointerId) {
        verticalTouch = e.touches[i];
        break;
      }
    }
    if (!verticalTouch) return;
    var deltaYFromLast = verticalTouch.clientY - modalVerticalTouchState.lastY;
    modalVerticalTouchState.lastY = verticalTouch.clientY;
    if (shouldPreventModalOverscroll(modalScroll, deltaYFromLast)) {
      e.preventDefault();
    }
  }, { passive: false });

  modalScroll.addEventListener("touchmove", function(e) {
    if (!isTouchModalViewport() || !modal.classList.contains("open")) return;
    var verticalTouch = null;
    for (var vt = 0; vt < e.touches.length; vt++) {
      if (e.touches[vt].identifier === modalVerticalTouchState.pointerId) {
        verticalTouch = e.touches[vt];
        break;
      }
    }
    if (verticalTouch) {
      var deltaYFromLast = verticalTouch.clientY - modalVerticalTouchState.lastY;
      if (shouldPreventModalOverscroll(modalScroll, deltaYFromLast)) {
        e.preventDefault();
      }
    }
    if (!modalSwipeState.tracking || !isTouchModalViewport() || !modal.classList.contains("open")) return;
    var touch = null;
    for (var i = 0; i < e.touches.length; i++) {
      if (e.touches[i].identifier === modalSwipeState.pointerId) {
        touch = e.touches[i];
        break;
      }
    }
    if (!touch) return;
    var now = Date.now();
    var dt = Math.max(now - modalSwipeState.lastTime, 16);
    modalSwipeState.velocityX = (touch.clientX - modalSwipeState.lastX) / dt;
    modalSwipeState.lastX = touch.clientX;
    modalSwipeState.lastTime = now;
    modalSwipeState.deltaX = touch.clientX - modalSwipeState.startX;
    modalSwipeState.deltaY = touch.clientY - modalSwipeState.startY;
    if (!modalSwipeState.active) {
      if (modalSwipeState.deltaX <= 0) return;
      if (Math.abs(modalSwipeState.deltaY) > Math.abs(modalSwipeState.deltaX)) return;
      if (modalSwipeState.deltaX < 12) return;
      modalSwipeState.active = true;
      modal.classList.add("swiping");
    }
    if (modalSwipeState.deltaX <= 0) {
      modal.style.setProperty("--modal-swipe-offset", "0px");
      modal.style.setProperty("--modal-swipe-progress", "0");
      return;
    }
    if (Math.abs(modalSwipeState.deltaY) > Math.abs(modalSwipeState.deltaX)) {
      modal.style.setProperty("--modal-swipe-offset", "0px");
      modal.style.setProperty("--modal-swipe-progress", "0");
      return;
    }
    e.preventDefault();
    var easedOffset = modalSwipeState.deltaX * 0.16;
    var clampedOffset = Math.min(easedOffset, 48);
    modal.style.setProperty("--modal-swipe-offset", clampedOffset + "px");
    modal.style.setProperty("--modal-swipe-progress", "0");
  }, { passive: false });

  function finishSwipe() {
    if (!modalSwipeState.tracking) return;
    modalSwipeState.tracking = false;
    if (!modalSwipeState.active) {
      modalSwipeState.pointerId = null;
      return;
    }
    var shouldClose =
      Math.abs(modalSwipeState.deltaX) > Math.abs(modalSwipeState.deltaY) * 1.15 &&
      (modalSwipeState.deltaX > 26 || (modalSwipeState.deltaX > 14 && modalSwipeState.velocityX > 0.35));
    modalSwipeState.active = false;
    modalSwipeState.pointerId = null;
    if (shouldClose) {
      animateModalSwipeClose();
      return;
    }
    modal.classList.remove("swiping");
    modal.style.setProperty("--modal-swipe-offset", "0px");
    modal.style.setProperty("--modal-swipe-progress", "0");
  }

  modalScroll.addEventListener("touchend", finishSwipe);
  modalScroll.addEventListener("touchend", function() {
    modalVerticalTouchState.active = false;
    modalVerticalTouchState.pointerId = null;
  });
  modalScroll.addEventListener("touchcancel", function() {
    modalVerticalTouchState.active = false;
    modalVerticalTouchState.pointerId = null;
    resetModalSwipe();
  });
}

function openModal(id) {
  if (!id) return;
  var modal = document.getElementById("detail-modal");
  var modalScroll = modal.querySelector(".modal-scroll");
  var movie = null;
  ["now","soon"].forEach(function(t) { allMovies[t].forEach(function(m) { if (m.id === id) movie = m; }); });
  if (!movie) movie = {};
  currentModalMovieId = id;
  modal.classList.add("open");
  lockBodyScroll();
  if (modalScroll) modalScroll.scrollTop = 0;
  var loadingState = buildModalLoadingState(movie);
  document.getElementById("modal-hero-slot").innerHTML = loadingState.heroSlot;
  document.getElementById("modal-content").innerHTML = loadingState.content;
  getDetail(id).then(function(detail) {
    if (currentModalMovieId !== id || !modal.classList.contains("open")) return;
    var imdbRating = movie.imdb || "";
    renderModal(movie, detail, imdbRating);
    if (modalScroll) modalScroll.scrollTop = 0;
  });
}

function renderModal(movie, detail, imdbRating) {
  var trailerKey = detail.trailerKey || movie.trailerKey;
  var langMap = {en:"英語",zh:"中文",ja:"日語",ko:"韓語",fr:"法語",es:"西班牙語",de:"德語",it:"義大利語",th:"泰語",hi:"印地語",tl:"菲律賓語",ar:"阿拉伯語",id:"印尼語",pt:"葡萄牙語",tr:"土耳其語"};
  var statusMap = {Released:"已上映","In Production":"製作中",Planned:"計畫中"};
  var genres = normalizeGenreList(detail.genres || movie.genre || []);
  var genreTags = "";
  for (var i = 0; i < Math.min(genres.length,3); i++) genreTags += '<span class="modal-genre-tag">' + escHtml(genres[i]) + '</span>';
  var cast = detail.cast || []; var castHTML = "";
  for (var c = 0; c < cast.length; c++) {
    castHTML += '<div class="cast-card">';
    if (cast[c].photo) castHTML += '<img class="cast-photo" src="' + escHtml(cast[c].photo) + '" loading="lazy"/>';
    else castHTML += '<div class="cast-no-photo"><span class="material-symbols-outlined">person</span></div>';
    castHTML += '<p class="cast-name">' + escHtml(cast[c].name) + '</p><p class="cast-char">' + escHtml(cast[c].char) + '</p></div>';
  }
  var crew = detail.crew || []; var crewHTML = "";
  for (var cr = 0; cr < crew.length; cr++) {
    var rl = crew[cr].job === "Director" ? "導演" : crew[cr].job === "Screenplay" ? "編劇" : "製作人";
    crewHTML += '<div><p class="crew-name">' + escHtml(crew[cr].name) + '</p><p class="crew-role">' + rl + '</p></div>';
  }
  var platforms = detail.platforms || []; var platformHTML = "";
  for (var p = 0; p < platforms.length; p++) {
    platformHTML += '<div class="platform-tag">';
    if (platforms[p].logo) platformHTML += '<img class="platform-logo" src="https://image.tmdb.org/t/p/w92' + platforms[p].logo + '"/>';
    platformHTML += '<span class="platform-name">' + escHtml(platforms[p].name) + '</span></div>';
  }
  var subtitleParts = [];
  if (detail.origTitle) subtitleParts.push(detail.origTitle);
  if (movie.releaseDate) subtitleParts.push(formatDate(movie.releaseDate));
  if (detail.duration) subtitleParts.push(detail.duration + "分鐘");
  var metaRows = [
    ["原始標題", detail.origTitle || movie.titleEn || "—"],
    ["狀態", statusMap[detail.status] || detail.status || "—"],
    ["原始語言", langMap[detail.origLang] || detail.origLang || "—"],
    ["製片國家", formatCountryList(detail.countries)],
    ["電影成本", detail.budget ? "$" + detail.budget.toLocaleString() : "—"],
    ["票房收入", detail.revenue ? "$" + detail.revenue.toLocaleString() : "—"]
  ];
  var metaHTML = "";
  for (var mr = 0; mr < metaRows.length; mr++) metaHTML += '<div class="meta-row"><span class="meta-key">' + metaRows[mr][0] + '</span><span class="meta-val">' + escHtml(metaRows[mr][1]) + '</span></div>';
  var heroImage = detail.backdrop || movie.backdrop || movie.poster || "";
  var bdHTML = heroImage ? '<img class="modal-hero-img" src="' + escHtml(heroImage) + '" fetchpriority="high" decoding="async"/>' : '<div style="width:100%;height:100%;background:rgba(255,255,255,0.05)"></div>';
  var rtRating = movie.rt || "";
  var mcRating = movie.mc || "";
  var ratingItems = [];
  if (imdbRating) ratingItems.push('<span class="modal-rating-item"><span class="material-symbols-outlined star">star</span>IMDb <span class="val">' + escHtml(imdbRating) + '</span></span>');
  if (rtRating) ratingItems.push('<span class="modal-rating-item">' + rtIconSvg('rgba(255,255,255,0.6)') + ' RT <span class="val">' + escHtml(rtRating) + '</span></span>');
  if (mcRating) ratingItems.push('<span class="modal-rating-item"><svg width="11" height="11" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg" style="flex-shrink:0"><circle cx="6" cy="6" r="5.3" stroke="rgba(255,255,255,0.6)" stroke-width="0.9"/><text x="6" y="8.2" text-anchor="middle" font-size="7.5" font-family="sans-serif" fill="rgba(255,255,255,0.6)">m</text></svg> MT <span class="val">' + escHtml(mcRating) + '</span></span>');
  if (detail.voteAverage) ratingItems.push('<span class="modal-rating-item"><span class="material-symbols-outlined star">star</span>TMDB <span class="val">' + tmdbScore(detail.voteAverage) + '</span></span>');
  var ratingsHTML = ratingItems.join('<span class="modal-rating-divider"></span>');
  var bgHTML = buildModalHeroSlot(heroImage);
  var html = '<div class="fade-in"><div class="modal-hero"><div class="modal-hero-media">' + bdHTML +
    '</div><div class="modal-hero-fade"></div>' +
    '<div class="modal-hero-info">' +
    '<div class="modal-info-group"><div class="modal-genre-tags">' + genreTags + '</div>' +
    '<h2 class="modal-title">' + escHtml(movie.titleZh || detail.origTitle || "—") + '</h2>' +
    '<p class="modal-subtitle">' + escHtml(subtitleParts.join(' · ')) + '</p>' +
    '</div>' +
    (ratingsHTML ? '<div class="modal-ratings">' + ratingsHTML + '</div>' : '') +
    (trailerKey ? '<button class="btn-trailer" onclick="playTrailer(\'' + trailerKey + '\')"><span class="material-symbols-outlined" style="font-size:22px">play_arrow</span>播放預告</button>' : '') +
    '</div></div><div class="modal-body">' +
    (detail.synopsis ? '<p class="modal-synopsis">' + escHtml(detail.synopsis) + '</p>' : '') +
    (crewHTML ? '<div class="crew-grid">' + crewHTML + '</div>' : '') +
    (castHTML ? '<div><p class="section-label">主要演員</p><div class="cast-row">' + castHTML + '</div></div>' : '') +
    (platformHTML ? '<div><p class="section-label">收看平台</p><div class="platform-row">' + platformHTML + '</div></div>' : '') +
    '<div><p class="section-label">其他資訊</p><div class="meta-panel">' + metaHTML + '</div></div></div></div>';
  document.getElementById("modal-hero-slot").innerHTML = bgHTML;
  document.getElementById("modal-content").innerHTML = html;
}

function closeModal() {
  finishSwipeClose();
}
function playTrailer(key) {
  var isLocal = location.protocol === "file:";
  if (isLocal) {
    window.open("https://www.youtube.com/watch?v=" + key, "_blank");
  } else {
    document.getElementById("trailer-iframe").src = "https://www.youtube-nocookie.com/embed/" + key + "?autoplay=1&rel=0";
    document.getElementById("trailer-modal").classList.add("open");
  }
}
function closeTrailer() { document.getElementById("trailer-iframe").src = ""; document.getElementById("trailer-modal").classList.remove("open"); }
document.addEventListener("keydown", function(e) { if (e.key === "Escape") { closeModal(); closeTrailer(); } });

document.addEventListener("click", function(e) {
  var panel = document.getElementById("filter-panel");
  if (panel.style.display !== "block") return;
  if (panel.contains(e.target)) return;
  if (e.target.closest("#mobile-search-toggle, .filter-btn")) return;
  toggleFilter();
});

document.addEventListener("DOMContentLoaded", function() {
  initModalSwipe();
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

function fetchImdbInBackground(movies, options) {
  return;
}

function applyLoadedMoviePayload(payload) {
  movieDataMeta.generated_at = payload.generated_at || "";
  payload = normalizeMoviePayload(payload);
  allMovies = payload.movies || { now: [], soon: [] };
  rebucketMoviesByReleaseDate();
  filtered = { now: allMovies.now.slice(), soon: allMovies.soon.slice() };
  sortMovies();
  buildGenreFilters();
  updateDataStatus(payload.generated_at || "");
  return payload;
}

function loadData(forceRefresh) {
  var errBanner = document.getElementById("error-banner");
  errBanner.classList.remove("show");
  if (!forceRefresh) {
    var cached = loadCache();
    if (cached) {
      applyLoadedMoviePayload(cached);
      return;
    }
  }
  showSkeletons();
  fetch(STATIC_DATA_PATH, { cache: forceRefresh ? "reload" : "default" }).then(function(r) {
    if (!r.ok) throw new Error("STATIC " + r.status);
    return r.json();
  }).then(function(payload) {
    payload = applyLoadedMoviePayload(payload);
    saveCache(payload);
  }).catch(function(e) {
    errBanner.textContent = "⚠️ 資料載入失敗：" + e.message;
    errBanner.classList.add("show");
    var cached = loadCache();
    if (cached) {
      applyLoadedMoviePayload(cached);
    }
  });
}

function refreshData() { loadData(true); }
switchTab(currentTab);
loadData(false);

(function() {
  var TABS = ['now', 'soon'];
  var startX = 0, startY = 0;
  document.addEventListener('touchstart', function(e) {
    startX = e.touches[0].clientX;
    startY = e.touches[0].clientY;
  }, { passive: true });
  document.addEventListener('touchend', function(e) {
    if (window.innerWidth > 768) return;
    if (document.getElementById('detail-modal').classList.contains('open')) return;
    var dx = e.changedTouches[0].clientX - startX;
    var dy = e.changedTouches[0].clientY - startY;
    if (Math.abs(dx) < 50 || Math.abs(dx) <= Math.abs(dy)) return;
    var idx = TABS.indexOf(currentTab);
    if (dx < 0 && idx < TABS.length - 1) switchTab(TABS[idx + 1]);
    else if (dx > 0 && idx > 0) switchTab(TABS[idx - 1]);
  }, { passive: true });
})();
