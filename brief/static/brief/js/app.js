/* AI Brief Generator — front-end logic.
   Plain jQuery: read the form, POST JSON, render the structured result. */
(function ($) {
  "use strict";

  var ENDPOINT = "/api/brief";
  var lastInputs = null; // remembered so "Regenerate" can re-run the same inputs

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

  function setLoading(isLoading) {
    var $btn = $("#submit-btn");
    $btn.prop("disabled", isLoading).toggleClass("is-loading", isLoading);
    $btn.find(".btn__label").text(isLoading ? "Generating…" : "Generate brief");
    $("#regenerate-btn").prop("disabled", isLoading);
  }

  function showError(message) {
    $("#error").text(message).prop("hidden", false);
  }
  function clearError() {
    $("#error").prop("hidden", true).text("");
  }

  function escapeHtml(text) {
    return $("<div>").text(text == null ? "" : text).html();
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
    renderTelemetry(data.telemetry);
    $("#brief-text").text(data.result.brief);
    renderAngles(data.result.angles);
    renderCriteria(data.result.criteria);
    $("#results").prop("hidden", false);
  }

  // ── Network ─────────────────────────────────────────────────────
  function generate(inputs) {
    lastInputs = inputs;
    clearError();
    setLoading(true);

    $.ajax({
      url: ENDPOINT,
      method: "POST",
      contentType: "application/json",
      headers: { "X-CSRFToken": csrfToken() },
      data: JSON.stringify(inputs),
    })
      .done(function (data) {
        renderResult(data);
      })
      .fail(function (xhr) {
        var detail = "Something went wrong. Please try again.";
        if (xhr.responseJSON && xhr.responseJSON.detail) {
          detail = xhr.responseJSON.detail;
        }
        showError(detail);
      })
      .always(function () {
        setLoading(false);
      });
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

  // Copy buttons (delegated): copy either a target element's text or inline text.
  $(document).on("click", ".copy", function () {
    var $btn = $(this);
    var target = $btn.data("copy-target");
    var text = target ? $.trim($(target).text()) : $btn.data("copy-text");

    var done = function () {
      var original = $btn.text();
      $btn.text("Copied").addClass("is-done");
      setTimeout(function () { $btn.text(original).removeClass("is-done"); }, 1200);
    };

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(done, done);
    } else {
      var $tmp = $("<textarea>").val(text).appendTo("body").select();
      document.execCommand("copy");
      $tmp.remove();
      done();
    }
  });
})(jQuery);
