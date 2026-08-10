/**
 * Side panel logic for the Appian Expression Analyzer.
 * Receives expressions from the content script (via background) and displays analysis.
 */

import { Analyzer } from "../parser/analyzer.js";

const analyzer = new Analyzer();

// DOM elements
const statusDot = document.getElementById("statusDot");
const summaryText = document.getElementById("summaryText");
const issueCount = document.getElementById("issueCount");
const diagnosticsList = document.getElementById("diagnosticsList");
const functionsList = document.getElementById("functionsList");
const variablesList = document.getElementById("variablesList");
const manualInput = document.getElementById("manualInput");
const analyzeBtn = document.getElementById("analyzeBtn");

/**
 * Run analysis on an expression and update the UI.
 */
function runAnalysis(expression) {
  const result = analyzer.analyze(expression);
  updateUI(result);

  // Notify content script of result count (for the inline badge)
  chrome.runtime.sendMessage({
    type: "ANALYSIS_RESULT",
    payload: { errorCount: result.errorCount },
  });
}

/**
 * Update all panel sections with analysis results.
 */
function updateUI(result) {
  // Status dot
  statusDot.classList.remove("active", "error");
  if (result.errorCount > 0) {
    statusDot.classList.add("error");
  } else {
    statusDot.classList.add("active");
  }

  // Summary
  summaryText.textContent = result.summary;

  // Issue count badge
  const totalIssues = result.diagnostics.length;
  issueCount.textContent = totalIssues;
  issueCount.classList.remove("has-errors", "has-warnings");
  if (result.errors.length > 0) {
    issueCount.classList.add("has-errors");
  } else if (result.warnings.length > 0) {
    issueCount.classList.add("has-warnings");
  }

  // Diagnostics list
  if (result.diagnostics.length === 0) {
    diagnosticsList.innerHTML = '<p class="empty-state">No issues detected. Expression looks good!</p>';
  } else {
    diagnosticsList.innerHTML = result.diagnostics
      .map((d) => renderDiagnostic(d))
      .join("");
  }

  // Functions list
  if (result.functions.length === 0) {
    functionsList.innerHTML = "<li>None detected</li>";
  } else {
    functionsList.innerHTML = result.functions
      .map((f) => `<li class="function-tag">${escapeHtml(f)}</li>`)
      .join("");
  }

  // Variables list
  if (result.variables.length === 0) {
    variablesList.innerHTML = "<li>None detected</li>";
  } else {
    variablesList.innerHTML = result.variables
      .map((v) => `<li class="variable-tag">${escapeHtml(v)}</li>`)
      .join("");
  }
}

/**
 * Render a single diagnostic item.
 */
function renderDiagnostic(diagnostic) {
  const icons = {
    error: "❌",
    warning: "⚠️",
    info: "ℹ️",
  };

  return `
    <div class="diagnostic-item ${diagnostic.severity}">
      <span class="diagnostic-icon">${icons[diagnostic.severity]}</span>
      <div class="diagnostic-content">
        <div class="diagnostic-message">${escapeHtml(diagnostic.message)}</div>
        <div class="diagnostic-location">Line ${diagnostic.line}, Col ${diagnostic.column}</div>
      </div>
    </div>
  `;
}

/**
 * Escape HTML special characters to prevent XSS.
 */
function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// ─── Event Listeners ───────────────────────────────────────────

// Manual input analysis
analyzeBtn.addEventListener("click", () => {
  const expression = manualInput.value.trim();
  if (expression) {
    runAnalysis(expression);
  }
});

// Keyboard shortcut: Ctrl+Enter to analyze
manualInput.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
    e.preventDefault();
    analyzeBtn.click();
  }
});

// Listen for expressions forwarded from background/content script
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === "ANALYSIS_INPUT") {
    const expression = message.payload.expression;
    manualInput.value = expression;
    runAnalysis(expression);
  }
});
