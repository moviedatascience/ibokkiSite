// Auto-start SSO on Fluxer's login page when SSO is enforced.
//
// Fluxer (with enforced SSO) shows a single "Continue with SSO" button rather
// than auto-redirecting. This script, injected by the sso-injector nginx in
// front of Fluxer's Caddy, clicks that button automatically so users go
// straight to the ibokki login with zero clicks.
//
// It matches the button by visible text (Fluxer's prod build strips the
// data-flx attributes), and guards against redirect loops with a per-tab flag.
(function () {
  try { if (sessionStorage.getItem('sso_auto_started')) return; } catch (e) {}
  var attempts = 0;
  var timer = setInterval(function () {
    var btn = Array.prototype.find.call(
      document.querySelectorAll('button'),
      function (b) { return /sso|sign[\s-]?on/i.test(b.textContent || ''); }
    );
    if (btn) {
      clearInterval(timer);
      try { sessionStorage.setItem('sso_auto_started', '1'); } catch (e) {}
      btn.click();
    } else if (++attempts > 60) {
      clearInterval(timer); // give up after ~6s; fall back to the manual button
    }
  }, 100);
})();
