/* CEI LABS — shared behavior (nav toggle, copy buttons, event freshness fetch) */
(function () {
  "use strict";

  // Mobile nav toggle
  var toggle = document.querySelector(".nav-toggle");
  var links = document.querySelector(".nav-links");
  if (toggle && links) {
    toggle.addEventListener("click", function () {
      var open = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  // Terminal copy buttons
  document.querySelectorAll(".term-copy").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var pre = btn.closest(".term").querySelector("pre");
      // Copy only the COMMAND text: clone the block and drop the prompt
      // markers (.pr, the ">" / "$" decoration spans) and the blinking cursor,
      // so a paste never starts with a stray ">" (which PowerShell rejects
      // with "The term '>' is not recognized").
      var clone = pre.cloneNode(true);
      clone.querySelectorAll(".pr, .cursor").forEach(function (el) { el.remove(); });
      var text = clone.textContent.replace(/\u2588/g, "").trim();
      navigator.clipboard.writeText(text).then(function () {
        var old = btn.textContent;
        btn.textContent = "COPIED";
        setTimeout(function () { btn.textContent = old; }, 1600);
      });
    });
  });

  // Event page: live "tracker last updated" stamp (fails silently to static stamp)
  var live = document.querySelector("[data-tracker-updated]");
  if (live) {
    fetch("https://api.github.com/repos/stoptalkingishh/cei-labs-event/commits?per_page=1")
      .then(function (r) { return r.ok ? r.json() : Promise.reject(); })
      .then(function (data) {
        var d = data && data[0] && data[0].commit && data[0].commit.committer.date;
        if (d) live.textContent = " · TRACKER LAST UPDATED: " + d.slice(0, 10);
      })
      .catch(function () { /* keep static stamp */ });
  }
})();
