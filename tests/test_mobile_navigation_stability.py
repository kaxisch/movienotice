from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


def homepage_script():
    return "\n".join(
        (ROOT / filename).read_text()
        for filename in ("app-data.js", "app-ui.js", "app.js")
    )


class MobileNavigationStabilityTests(unittest.TestCase):
    def test_homepage_scripts_load_in_dependency_order_and_are_cached(self):
        index = (ROOT / "index.html").read_text()
        service_worker = (ROOT / "sw.js").read_text()

        self.assertLess(index.index('src="app-data.js'), index.index('src="app-ui.js'))
        self.assertLess(index.index('src="app-ui.js'), index.index('src="app.js'))
        self.assertIn("'./app-data.js'", service_worker)
        self.assertIn("'./app-ui.js'", service_worker)

    def test_data_load_error_has_in_app_retry_control(self):
        script = (ROOT / "app.js").read_text()
        styles = (ROOT / "styles.css").read_text()

        self.assertIn('retryButton.textContent = "重新載入資料"', script)
        self.assertIn("loadData(true)", script)
        self.assertIn("min-height: 44px", styles)

    def test_movie_page_has_no_mobile_entry_transform(self):
        generator = (ROOT / "scripts" / "generate_movie_pages.py").read_text()
        script = (ROOT / "movie-page.js").read_text()

        self.assertNotIn("movie-page-entering", generator)
        self.assertNotIn("movie-page-entering", script)
        self.assertIn("<body>", generator)

    def test_movie_page_uses_share_control_with_clipboard_fallback(self):
        generator = (ROOT / "scripts" / "generate_movie_pages.py").read_text()
        script = (ROOT / "movie-page.js").read_text()

        self.assertIn('class="share-button"', generator)
        self.assertNotIn('class="back-link"', generator)
        self.assertIn("(max-width: 1024px) and (pointer: coarse)", script)
        self.assertIn("if (mobileShare && navigator.share)", script)
        self.assertIn("navigator.share(shareData)", script)
        self.assertIn("navigator.clipboard.writeText(window.location.href)", script)
        self.assertIn("showShareSnackbar('已複製')", script)
        self.assertIn("}, 2000)", script)

    def test_mobile_cards_do_not_replay_entrance_animation(self):
        styles = (ROOT / "styles.css").read_text()

        self.assertIn(".movie-card.fade-in", styles)
        self.assertIn(".list-item.fade-in", styles)
        self.assertIn("animation: none", styles)

    def test_data_refresh_preserves_restored_viewport(self):
        script = homepage_script()

        self.assertIn("sortMovies(false, true)", script)
        self.assertIn("if (!options || !options.preserveViewport) scrollToResults()", script)

    def test_mobile_card_text_does_not_follow_detail_link(self):
        script = homepage_script()
        styles = (ROOT / "styles.css").read_text()

        self.assertIn('e.target.closest(".movie-card .card-info")', script)
        self.assertIn('e.preventDefault()', script)
        self.assertIn("-webkit-tap-highlight-color: transparent", styles)

    def test_pinned_tab_bar_is_held_during_mobile_history_return(self):
        script = homepage_script()
        styles = (ROOT / "styles.css").read_text()

        self.assertIn("holdPinnedTabBarForMobileReturn()", script)
        self.assertIn('document.addEventListener("touchstart"', script)
        self.assertIn('window.addEventListener("pageshow"', script)
        self.assertIn("}, 400)", script)
        self.assertIn('window.addEventListener("scroll", releaseMobileReturnPinAtPageTop', script)
        self.assertIn("body.mobile-return-pinned #tab-bar", styles)
        self.assertIn("--return-tab-bar-height", styles)


if __name__ == "__main__":
    unittest.main()
