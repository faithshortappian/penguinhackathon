/**
 * Content script that runs on Appian Designer pages.
 * Detects the expression editor (CodeMirror instance) and extracts SAIL text.
 */

(function () {
  "use strict";

  const POLL_INTERVAL_MS = 2000;
  const DEBOUNCE_MS = 500;

  let lastExpression = "";
  let debounceTimer = null;
  let observer = null;

  /**
   * Attempts to find the CodeMirror expression editor in the Appian DOM.
   * Appian uses CodeMirror for its expression mode editor.
   */
  function findExpressionEditor() {
    // Appian's expression editor uses CodeMirror — look for the CM container
    const cmElements = document.querySelectorAll(".CodeMirror");
    if (cmElements.length > 0) {
      return cmElements[0];
    }

    // Fallback: look for Appian-specific expression editor containers
    const appianEditor = document.querySelector(
      '[class*="ExpressionEditor"], [class*="expression-editor"], [data-testid*="expression"]'
    );
    if (appianEditor) {
      return appianEditor;
    }

    return null;
  }

  /**
   * Extracts expression text from the CodeMirror instance or DOM.
   */
  function extractExpression(editorElement) {
    // Try to get the CodeMirror instance directly
    if (editorElement.CodeMirror) {
      return editorElement.CodeMirror.getValue();
    }

    // Try accessing via the CM6 view (newer Appian versions)
    const cmContent = editorElement.querySelector(".cm-content");
    if (cmContent) {
      return cmContent.textContent || "";
    }

    // Fallback to line-based extraction (CodeMirror 5)
    const lines = editorElement.querySelectorAll(".CodeMirror-line");
    if (lines.length > 0) {
      return Array.from(lines)
        .map((line) => line.textContent)
        .join("\n");
    }

    // Last resort: textarea fallback
    const textarea = editorElement.querySelector("textarea");
    if (textarea) {
      return textarea.value;
    }

    return "";
  }

  /**
   * Sends the extracted expression to the background script for analysis.
   */
  function sendExpression(expression) {
    if (expression === lastExpression) return;
    lastExpression = expression;

    chrome.runtime.sendMessage({
      type: "EXPRESSION_EXTRACTED",
      payload: {
        expression,
        url: window.location.href,
        timestamp: Date.now(),
      },
    });
  }

  /**
   * Debounced handler for editor content changes.
   */
  function onEditorChange(editorElement) {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      const expression = extractExpression(editorElement);
      if (expression.trim()) {
        sendExpression(expression);
      }
    }, DEBOUNCE_MS);
  }

  /**
   * Sets up a MutationObserver on the editor to watch for content changes.
   */
  function watchEditor(editorElement) {
    if (observer) observer.disconnect();

    observer = new MutationObserver(() => {
      onEditorChange(editorElement);
    });

    observer.observe(editorElement, {
      childList: true,
      subtree: true,
      characterData: true,
    });

    // Initial extraction
    onEditorChange(editorElement);
    console.log("[Appian Analyzer] Watching expression editor for changes.");
  }

  /**
   * Adds an inline indicator badge to the editor area showing error count.
   */
  function showInlineIndicator(editorElement, errorCount) {
    let badge = document.getElementById("appian-analyzer-badge");
    if (!badge) {
      badge = document.createElement("div");
      badge.id = "appian-analyzer-badge";
      badge.className = "appian-analyzer-badge";
      editorElement.parentElement.style.position = "relative";
      editorElement.parentElement.appendChild(badge);
    }

    if (errorCount === 0) {
      badge.textContent = "✓";
      badge.classList.remove("has-errors");
      badge.classList.add("no-errors");
    } else {
      badge.textContent = `${errorCount} issue${errorCount > 1 ? "s" : ""}`;
      badge.classList.remove("no-errors");
      badge.classList.add("has-errors");
    }
  }

  // Listen for analysis results from the panel/background
  chrome.runtime.onMessage.addListener((message) => {
    if (message.type === "ANALYSIS_RESULT") {
      const editor = findExpressionEditor();
      if (editor) {
        showInlineIndicator(editor, message.payload.errorCount);
      }
    }
  });

  /**
   * Poll for the editor appearing in the DOM (Appian loads dynamically).
   */
  function pollForEditor() {
    const interval = setInterval(() => {
      const editor = findExpressionEditor();
      if (editor) {
        clearInterval(interval);
        watchEditor(editor);
      }
    }, POLL_INTERVAL_MS);
  }

  // Start polling when the page loads
  pollForEditor();
})();
