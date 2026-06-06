/* AI Brief Generator — front-end logic.
   Plain jQuery: read the form, POST JSON, render the structured result.
   Also: a localStorage-backed "recent runs" list, shareable run links
   (?run=<id> → GET /api/brief/<id>), and a staged loading state. */
(function ($) {
  "use strict";

  var ENDPOINT = "/api/brief";
  var RUNS_KEY = "collabstr.runs";
  var MAX_RUNS = 20;

  var lastInputs = null; // remembered so "Regenerate" can re-run the same inputs
  var currentRunId = null; // id of the run currently shown (for the Share button)
  var timerInterval = null;
  var stageInterval = null;

  // Django CSRF token lives in a cookie; echo it back in a header on POST.
  function csrfToken() {
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function readForm() {
    return {
      brand: $.trim($("#brand").val()),
      platform: $("#platform").val(),
      goal: $("#goal").val(),
      tone: $("#tone").val(),
    };
  }

  function escapeHtml(text) {
    return $("<div>").text(text == null ? "" : text).html();
  }

  function copyToClipboard(text, done) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, done);
    } else {
      var $tmp = $("<textarea>").val(text).appendTo("body").select();
      document.execCommand("copy");
      $tmp.remove();
      done();
    }
  }

  function showError(message) {
    $("#error").text(message).prop("hidden", false);
  }
  function clearError() {
    $("#error").prop("hidden", true).text("");
  }

  // ── Loading state ───────────────────────────────────────────────
  // Staged status messages give a sense of progress over the ~5s call.
  var STAGES = [
    "Sending your brief to the model…",
    "Drafting the campaign brief…",
    "Exploring creative angles…",
    "Defining success criteria…",
    "Polishing the final brief…",
  ];

  function setButtonLoading(isLoading) {
    var $btn = $("#submit-btn");
    $btn.prop("disabled", isLoading).toggleClass("is-loading", isLoading);
    $btn.find(".btn__label").text(isLoading ? "Generating…" : "Generate new brief");
    $("#regenerate-btn, #share-btn").prop("disabled", isLoading);
  }

  function startLoading() {
    clearError();
    setButtonLoading(true);
    $("#results").prop("hidden", true);
    $("#loading").prop("hidden", false);

    var start = Date.now();
    var stage = 0;
    $("#loading-text").text(STAGES[0]);
    $("#loading-timer").text("0.0s");

    timerInterval = setInterval(function () {
      $("#loading-timer").text(((Date.now() - start) / 1000).toFixed(1) + "s");
    }, 100);
    stageInterval = setInterval(function () {
      stage = Math.min(stage + 1, STAGES.length - 1);
      $("#loading-text").text(STAGES[stage]);
    }, 1400);
  }

  function stopLoading() {
    setButtonLoading(false);
    clearInterval(timerInterval);
    clearInterval(stageInterval);
    $("#loading").prop("hidden", true);
  }

  // ── Recent runs (localStorage) ──────────────────────────────────
  function loadRuns() {
    try {
      return JSON.parse(localStorage.getItem(RUNS_KEY)) || [];
    } catch (e) {
      return [];
    }
  }
  function saveRuns(runs) {
    try {
      localStorage.setItem(RUNS_KEY, JSON.stringify(runs.slice(0, MAX_RUNS)));
    } catch (e) {
      /* storage full / disabled — history is best-effort */
    }
  }
  // A freshly generated run: goes to the top, stamped now ("just now").
  function recordNewRun(entry) {
    var runs = loadRuns().filter(function (r) {
      return r.id !== entry.id;
    });
    runs.unshift(entry);
    saveRuns(runs);
    renderRuns(entry.id);
  }

  // Opening an existing run is a read, not a re-run: leave its timestamp and
  // position untouched. Only add it (using the server's real created_at, not
  // "now") if this browser hasn't seen it — e.g. a shared link on a fresh device.
  function ensureRun(entry) {
    var runs = loadRuns();
    if (!runs.some(function (r) { return r.id === entry.id; })) {
      runs.unshift(entry);
      saveRuns(runs);
    }
    renderRuns(entry.id);
  }

  function relTime(ts) {
    if (!ts) return "";
    var s = Math.max(0, (Date.now() - ts) / 1000);
    if (s < 60) return "just now";
    var m = Math.floor(s / 60);
    if (m < 60) return m + "m ago";
    var h = Math.floor(m / 60);
    if (h < 24) return h + "h ago";
    return Math.floor(h / 24) + "d ago";
  }

  function renderRuns(activeId) {
    var runs = loadRuns();
    var $list = $("#runs-list");
    var hasRuns = runs.length > 0;
    $("#runs-empty").prop("hidden", hasRuns);
    $("#clear-runs").prop("hidden", !hasRuns);

    $list.html(
      runs
        .map(function (r) {
          var active = r.id === activeId ? " is-active" : "";
          return (
            '<li><button type="button" class="run' + active + '" data-run-id="' + escapeHtml(r.id) + '">' +
            '<span class="run__brand">' + escapeHtml(r.brand) + "</span>" +
            '<span class="run__meta">' +
            escapeHtml(r.platform) + '<span class="dot">·</span>' + escapeHtml(r.tone) +
            '<span class="dot">·</span>' + relTime(r.ts) +
            "</span></button></li>"
          );
        })
        .join("")
    );
  }

  // ── URL (shareable ?run=<id>) ───────────────────────────────────
  function getUrlRun() {
    return new URLSearchParams(window.location.search).get("run");
  }
  function setUrlRun(id) {
    if (window.history.replaceState) {
      window.history.replaceState(null, "", window.location.pathname + "?run=" + encodeURIComponent(id));
    }
  }
  function clearUrlRun() {
    if (window.history.replaceState) {
      window.history.replaceState(null, "", window.location.pathname);
    }
  }

  // ── Rendering ───────────────────────────────────────────────────
  function renderTelemetry(t) {
    var cost = "$" + Number(t.cost_usd).toFixed(5);
    var chips = [
      '<span class="chip chip--accent">' + escapeHtml(t.provider) + " · " + escapeHtml(t.model) + "</span>",
      '<span class="chip">⚡ <b>' + t.latency_ms + "</b> ms</span>",
      '<span class="chip">🪙 <b>' + t.total_tokens + "</b> tokens <span>(" + t.input_tokens + " in / " + t.output_tokens + " out)</span></span>",
      '<span class="chip">💵 <b>' + cost + "</b></span>",
    ];
    $("#telemetry").html(chips.join(""));
  }

  function renderAngles(angles) {
    var html = angles.map(function (a) {
      return (
        '<div class="angle">' +
        '<button type="button" class="copy" data-copy-text="' + escapeHtml(a.title + " — " + a.description) + '">Copy</button>' +
        '<p class="angle__title editable" contenteditable="true">' + escapeHtml(a.title) + "</p>" +
        '<p class="angle__desc editable" contenteditable="true">' + escapeHtml(a.description) + "</p>" +
        "</div>"
      );
    });
    $("#angles").html(html.join(""));
  }

  function renderCriteria(criteria) {
    var html = criteria.map(function (c) {
      return "<li><span>" + escapeHtml(c) + "</span></li>";
    });
    $("#criteria").html(html.join(""));
  }

  function renderResult(data) {
    currentRunId = data.id || null;
    renderTelemetry(data.telemetry);
    $("#brief-text").text(data.result.brief);
    renderAngles(data.result.angles);
    renderCriteria(data.result.criteria);
    $("#share-btn").prop("hidden", !currentRunId);
    $("#results").prop("hidden", false);
  }

  function historyEntry(id, inputs, ts) {
    return {
      id: id,
      brand: inputs.brand,
      platform: inputs.platform,
      goal: inputs.goal,
      tone: inputs.tone,
      ts: ts,
    };
  }

  // ── Network ─────────────────────────────────────────────────────
  function generate(inputs) {
    lastInputs = inputs;
    startLoading();

    $.ajax({
      url: ENDPOINT,
      method: "POST",
      contentType: "application/json",
      headers: { "X-CSRFToken": csrfToken() },
      data: JSON.stringify(inputs),
    })
      .done(function (data) {
        renderResult(data);
        if (data.id) {
          recordNewRun(historyEntry(data.id, inputs, Date.now()));
          setUrlRun(data.id);
        }
      })
      .fail(function (xhr) {
        var detail = "Something went wrong. Please try again.";
        if (xhr.responseJSON && xhr.responseJSON.detail) {
          detail = xhr.responseJSON.detail;
        }
        showError(detail);
      })
      .always(stopLoading);
  }

  // Load a previously stored run (shared link, or a click in the sidebar).
  function openRun(id) {
    startLoading();

    $.ajax({ url: ENDPOINT + "/" + encodeURIComponent(id), method: "GET" })
      .done(function (data) {
        if (data.inputs) {
          $("#brand").val(data.inputs.brand);
          $("#platform").val(data.inputs.platform);
          $("#goal").val(data.inputs.goal);
          $("#tone").val(data.inputs.tone);
          lastInputs = data.inputs;
        }
        renderResult(data);
        // Opening, not generating: keep the original age (server created_at),
        // and don't bump position. Only adds it if unseen (e.g. a shared link).
        var createdTs = data.created_at ? new Date(data.created_at).getTime() : Date.now();
        ensureRun(historyEntry(data.id, data.inputs, createdTs));
        setUrlRun(data.id);
      })
      .fail(function (xhr) {
        var detail = (xhr.responseJSON && xhr.responseJSON.detail) || "Couldn't load that brief.";
        showError(detail);
        clearUrlRun();
      })
      .always(stopLoading);
  }

  // ── Events ──────────────────────────────────────────────────────
  $("#brief-form").on("submit", function (e) {
    e.preventDefault();
    var inputs = readForm();
    if (inputs.brand.length < 2) {
      showError("Please enter a brand name (at least 2 characters).");
      return;
    }
    generate(inputs);
  });

  $("#regenerate-btn").on("click", function () {
    if (lastInputs) generate(lastInputs);
  });

  $("#share-btn").on("click", function () {
    if (!currentRunId) return;
    var $btn = $(this);
    var url = window.location.origin + window.location.pathname + "?run=" + encodeURIComponent(currentRunId);
    copyToClipboard(url, function () {
      $btn.text("Link copied").addClass("is-done");
      setTimeout(function () {
        $btn.text("Share").removeClass("is-done");
      }, 1400);
    });
  });

  $("#runs-list").on("click", ".run", function () {
    var id = $(this).data("run-id");
    if (id) openRun(String(id));
  });

  $("#clear-runs").on("click", function () {
    saveRuns([]);
    renderRuns(null);
  });

  // Copy buttons (delegated): copy either a target element's text or inline text.
  $(document).on("click", ".copy", function () {
    var $btn = $(this);
    var target = $btn.data("copy-target");
    var text = target ? $.trim($(target).text()) : $btn.data("copy-text");
    var original = $btn.text();
    copyToClipboard(text, function () {
      $btn.text("Copied").addClass("is-done");
      setTimeout(function () {
        $btn.text(original).removeClass("is-done");
      }, 1200);
    });
  });

  // ── Init ────────────────────────────────────────────────────────
  $(function () {
    var initial = getUrlRun();
    renderRuns(initial);
    if (initial) openRun(initial);
  });
})(jQuery);
