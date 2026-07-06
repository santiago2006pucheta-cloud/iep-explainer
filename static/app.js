(function () {
  "use strict";

  var form = document.getElementById("explain-form");
  var textInput = document.getElementById("text");
  var fileInput = document.getElementById("document");
  var resultsEl = document.getElementById("results");
  var submitBtn = document.getElementById("submit-btn");

  var EXPECTED_SECTION_COUNT = 3;

  var CARD_CLASS_BY_HEADING = {
    "possible gaps & missing pieces": "result-card--gaps",
    "questions to bring to the meeting": "result-card--questions",
  };

  // --- Escaping + tiny dependency-free markdown -> HTML renderer ---
  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function renderInline(text) {
    var escaped = escapeHtml(text);

    // Links: [text](url)
    escaped = escaped.replace(/\[([^\]]+)\]\(([^)]+)\)/g, function (match, label, url) {
      var safeUrl = url.trim();
      if (!/^https?:\/\//i.test(safeUrl) && !/^mailto:/i.test(safeUrl)) {
        return label;
      }
      return (
        '<a href="' +
        safeUrl +
        '" target="_blank" rel="noopener noreferrer">' +
        label +
        "</a>"
      );
    });

    // Bold: **text**
    escaped = escaped.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

    return escaped;
  }

  function markdownToHtml(markdown) {
    var lines = markdown.replace(/\r\n/g, "\n").split("\n");
    var html = [];
    var inList = false;
    var paragraphBuffer = [];

    function flushParagraph() {
      if (paragraphBuffer.length) {
        html.push("<p>" + renderInline(paragraphBuffer.join(" ")) + "</p>");
        paragraphBuffer = [];
      }
    }

    function closeListIfOpen() {
      if (inList) {
        html.push("</ul>");
        inList = false;
      }
    }

    lines.forEach(function (rawLine) {
      var line = rawLine.trim();

      if (line === "") {
        flushParagraph();
        closeListIfOpen();
        return;
      }

      var headingMatch = line.match(/^(#{1,3})\s+(.*)$/);
      if (headingMatch) {
        flushParagraph();
        closeListIfOpen();
        var level = headingMatch[1].length;
        html.push("<h" + level + ">" + renderInline(headingMatch[2]) + "</h" + level + ">");
        return;
      }

      var bulletMatch = line.match(/^[-*]\s+(.*)$/);
      if (bulletMatch) {
        flushParagraph();
        if (!inList) {
          html.push("<ul>");
          inList = true;
        }
        html.push("<li>" + renderInline(bulletMatch[1]) + "</li>");
        return;
      }

      closeListIfOpen();
      paragraphBuffer.push(line);
    });

    flushParagraph();
    closeListIfOpen();

    return html.join("\n");
  }

  // Split markdown into sections on lines beginning with "## "
  function splitIntoSections(markdown) {
    var lines = markdown.replace(/\r\n/g, "\n").split("\n");
    var sections = [];
    var currentHeading = null;
    var currentBody = [];

    function pushCurrent() {
      if (currentHeading !== null) {
        sections.push({ heading: currentHeading, body: currentBody.join("\n") });
      }
    }

    lines.forEach(function (line) {
      var match = line.match(/^##\s+(.*)$/);
      if (match) {
        pushCurrent();
        currentHeading = match[1].trim();
        currentBody = [line];
      } else if (currentHeading !== null) {
        currentBody.push(line);
      }
    });

    pushCurrent();
    return sections;
  }

  function cardClassFor(heading) {
    var key = heading.trim().toLowerCase();
    return CARD_CLASS_BY_HEADING[key] || "";
  }

  function renderResult(markdown) {
    var sections = splitIntoSections(markdown);

    if (sections.length < EXPECTED_SECTION_COUNT) {
      resultsEl.innerHTML =
        '<div class="result-card">' + markdownToHtml(markdown) + "</div>";
      return;
    }

    var cardsHtml = sections
      .map(function (section) {
        var extraClass = cardClassFor(section.heading);
        return (
          '<div class="result-card ' +
          extraClass +
          '">' +
          markdownToHtml(section.body) +
          "</div>"
        );
      })
      .join("");

    resultsEl.innerHTML = cardsHtml;
  }

  // --- Form submit handling ---
  form.addEventListener("submit", function (event) {
    event.preventDefault();

    var text = textInput.value.trim();
    var hasFile = fileInput.files && fileInput.files.length > 0;

    if (!hasFile && !text) {
      showError(
        "Please paste your IEP text or upload the document first."
      );
      return;
    }

    var formData = new FormData();
    formData.append("text", text);
    if (hasFile) {
      formData.append("document", fileInput.files[0]);
    }

    setLoading(true);

    fetch("/api/explain", {
      method: "POST",
      body: formData,
    })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (payload) {
        setLoading(false);
        if (!payload.ok) {
          showError(
            (payload.data && payload.data.error) ||
              "Something went wrong. Please try again."
          );
          return;
        }
        renderResult(payload.data.result || "");
      })
      .catch(function () {
        setLoading(false);
        showError(
          "Couldn't reach the server. Please check your connection and try again."
        );
      });
  });

  function setLoading(isLoading) {
    submitBtn.disabled = isLoading;
    if (isLoading) {
      resultsEl.innerHTML =
        '<div class="results-loading"><span class="spinner" aria-hidden="true"></span><span>Reading through the IEP…</span></div>';
    }
  }

  function showError(message) {
    resultsEl.innerHTML = '<div class="error-box">' + escapeHtml(message) + "</div>";
  }
})();
