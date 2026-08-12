(function () {
  'use strict';

  var mobileTouch = window.matchMedia('(max-width: 1024px) and (pointer: coarse)');
  if (!mobileTouch.matches) return;

  var body = document.body;
  var startX = 0;
  var startY = 0;
  var startTime = 0;
  var dragX = 0;
  var tracking = false;
  var dragging = false;

  body.classList.add('movie-page-entering');
  body.addEventListener('animationend', function () {
    body.classList.remove('movie-page-entering');
  }, { once: true });

  // iPhone and iPad already provide an interactive edge-swipe history gesture.
  // Let the browser reveal the previous page instead of stacking a second drag
  // animation over it. This also covers iPadOS devices reporting as Macintosh.
  var appleTouchDevice = /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  if (appleTouchDevice) return;

  function resetSwipe() {
    tracking = false;
    dragging = false;
    dragX = 0;
    body.classList.remove('movie-page-swiping', 'movie-page-snap-back', 'movie-page-exiting');
    body.style.transform = '';
  }

  function returnToMovieList() {
    var sameSiteReferrer = false;
    try {
      sameSiteReferrer = !!document.referrer && new URL(document.referrer).origin === window.location.origin;
    } catch (error) {
      sameSiteReferrer = false;
    }

    if (sameSiteReferrer && window.history.length > 1) {
      window.history.back();
    } else {
      window.location.href = '../../';
    }
  }

  window.addEventListener('touchstart', function (event) {
    if (event.touches.length !== 1 || event.touches[0].clientX > 32) return;
    startX = event.touches[0].clientX;
    startY = event.touches[0].clientY;
    startTime = Date.now();
    dragX = 0;
    tracking = true;
    dragging = false;
  }, { passive: true });

  window.addEventListener('touchmove', function (event) {
    if (!tracking || event.touches.length !== 1) return;
    var deltaX = event.touches[0].clientX - startX;
    var deltaY = event.touches[0].clientY - startY;

    if (!dragging) {
      if (Math.abs(deltaY) > 12 && Math.abs(deltaY) > Math.abs(deltaX)) {
        resetSwipe();
        return;
      }
      if (deltaX < 10 || Math.abs(deltaX) <= Math.abs(deltaY)) return;
      dragging = true;
      body.classList.remove('movie-page-entering');
      body.classList.add('movie-page-swiping');
    }

    dragX = Math.max(0, deltaX);
    body.style.transform = 'translateX(' + dragX + 'px)';
    event.preventDefault();
  }, { passive: false });

  window.addEventListener('touchend', function () {
    if (!tracking) return;
    var elapsed = Math.max(Date.now() - startTime, 1);
    var velocity = dragX / elapsed;
    var shouldClose = dragging && (dragX >= Math.max(90, window.innerWidth * .25) || velocity > .55);

    tracking = false;
    if (!dragging) return;

    body.classList.remove('movie-page-swiping');
    if (shouldClose) {
      body.classList.add('movie-page-exiting');
      body.style.transform = 'translateX(100%)';
      window.setTimeout(returnToMovieList, 180);
    } else {
      body.classList.add('movie-page-snap-back');
      body.style.transform = 'translateX(0)';
      window.setTimeout(resetSwipe, 230);
    }
  }, { passive: true });

  window.addEventListener('touchcancel', function () {
    if (!tracking) return;
    body.classList.add('movie-page-snap-back');
    body.style.transform = 'translateX(0)';
    window.setTimeout(resetSwipe, 230);
  }, { passive: true });
}());
