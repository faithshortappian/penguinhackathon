/**
 * Side panel logic for the Appian AI Assistant.
 *
 * Flow: read the active tab's current expression + rule inputs ->
 * POST {prompt, rule_inputs, expression} to the backend -> render the
 * response {response, rule_input, bulk_edit, line_by_line_edit}.
 *
 * Contract with the backend (see background.js requestSuggestion):
 *   request:  { prompt, rule_inputs, expression }
 *   response: { response, rule_input, bulk_edit, line_by_line_edit }
 *     rule_input:         [{ old: ruleInputObj|null, new: ruleInputObj }]
 *     line_by_line_edit:  [{ old: string, new: string }]
 *   ruleInputObj: { name, description, type, array }
 *
 * Expression edits keep their own Bulk / Line-by-line toggle with
 * per-item Accept/Reject, unaffected by the rule-input changes below.
 *
 * Rule input changes work differently, by design (see
 * content/rule-inputs-bridge.js header for why): only the Name is ever
 * written automatically. The full { name, description, type, array }
 * grid is always shown as a reference; Type and Array are left for the
 * user to set by hand in Appian. Two modes:
 *   - "manual": grid only, no writes at all — read it, type it in
 *     yourself.
 *   - "auto": same grid, plus a per-row Accept/Reject in an Action
 *     column — clicking Accept fills just that row's Name. Deliberately
 *     one row at a time rather than looping through all of them
 *     automatically: confirmed live that firing several of these
 *     back-to-back without a real pause in between is unreliable.
 *
 * Static Tools tab (default on open) holds editor-local utilities that
 * never call the backend: Find & Replace, a parenthesis/bracket matcher
 * (reuses the existing tokenizer/analyzer), and Auto-Save (periodically
 * clicks Appian's own Save button).
 */

import { Tokenizer, TokenType } from "../parser/tokenizer.js";

// ─── Line-by-line diff synthesis ───────────────────────────────────
//
// The real backend (see background.js requestSuggestion) only ever
// returns a single full-replacement `code` string — it has no concept
// of a per-line diff, so line_by_line_edit always comes back empty and
// Line-by-line mode has nothing to show. computeLineDiff fills that gap
// on the frontend: a standard LCS-based line diff between the old
// expression and the new bulk_edit, producing hunks in the same shape
// the rest of this file already expects ({ old, new }), but ALSO
// carrying precise character offsets (atIndex/deleteCount/insertText/
// expectedText) so each hunk can be applied via the same precise
// range-edit mechanism built for the parenthesis fixer
// (APPLY_MULTI_CHAR_EDITS) rather than the older, less reliable
// substring search (APPLY_LINE_EDIT), which could misfire if the same
// line of text happens to appear more than once in the expression.
function computeLineDiff(oldText, newText) {
  if (oldText === newText) return [];

  const oldLines = oldText.split("\n");
  const newLines = newText.split("\n");
  const n = oldLines.length;
  const m = newLines.length;

  const dp = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = oldLines[i] === newLines[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }

  const ops = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (oldLines[i] === newLines[j]) {
      ops.push({ type: "equal" });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      ops.push({ type: "delete", line: oldLines[i] });
      i++;
    } else {
      ops.push({ type: "insert", line: newLines[j] });
      j++;
    }
  }
  while (i < n) {
    ops.push({ type: "delete", line: oldLines[i] });
    i++;
  }
  while (j < m) {
    ops.push({ type: "insert", line: newLines[j] });
    j++;
  }

  // Character offset where each old line begins, plus a sentinel entry
  // one past the last line (used for hunks that reach the end of doc).
  const oldLineStart = [];
  let acc = 0;
  for (const line of oldLines) {
    oldLineStart.push(acc);
    acc += line.length + 1;
  }
  oldLineStart.push(acc);

  const hunks = [];
  let k = 0;
  let oldLineIndex = 0;
  while (k < ops.length) {
    if (ops[k].type === "equal") {
      oldLineIndex++;
      k++;
      continue;
    }

    const startLine = oldLineIndex;
    const deleted = [];
    const inserted = [];
    while (k < ops.length && ops[k].type !== "equal") {
      if (ops[k].type === "delete") {
        deleted.push(ops[k].line);
        oldLineIndex++;
      } else {
        inserted.push(ops[k].line);
      }
      k++;
    }

    const atEnd = startLine >= n;
    const startIndex = atEnd ? oldText.length : oldLineStart[startLine];
    const endLine = startLine + deleted.length;
    const endIndex = deleted.length === 0 ? startIndex : endLine < n ? oldLineStart[endLine] : oldText.length;

    let insertText = inserted.join("\n");
    if (deleted.length === 0 && inserted.length > 0) {
      // Pure insertion — anchor as its own new line rather than merging
      // into whatever's already sitting at this position.
      insertText = atEnd ? "\n" + insertText : insertText + "\n";
    }

    hunks.push({
      old: deleted.join("\n"),
      new: inserted.join("\n"),
      line: startLine + 1,
      atIndex: startIndex,
      deleteCount: endIndex - startIndex,
      insertText,
      expectedText: oldText.slice(startIndex, endIndex),
    });
  }

  return hunks;
}

// ─── State ──────────────────────────────────────────────────────────

const state = {
  objectName: "",
  expression: "",
  ruleInputs: [],
  suggestion: null, // { response, rule_input, bulk_edit, line_by_line_edit }
  mode: "bulk", // expression edit mode: "bulk" | "line"
  lineStatus: [], // per line_by_line_edit entry: "pending" | "accepted" | "rejected"
  lineNavIndex: 0, // which line_by_line_edit entry ▲/▼ navigation currently points at
  ruleInputMode: "auto", // rule input mode: "manual" | "auto"
  ruleInputAutomationSupported: true, // false in editors other than the Expression Rule Designer
  ruleInputStatus: [], // per rule_input entry, auto mode only: "pending" | "accepted" | "error" | "rejected"
  lastRequestPayload: null, // debug: exact payload sent to background.js
};

// ─── DOM ────────────────────────────────────────────────────────────

const statusDot = document.getElementById("statusDot");
const objectNameHint = document.getElementById("objectNameHint");
const promptInput = document.getElementById("promptInput");
const askBtn = document.getElementById("askBtn");
const askStatus = document.getElementById("askStatus");

const suggestionSection = document.getElementById("suggestionSection");
const suggestionResponse = document.getElementById("suggestionResponse");
const bulkModeBtn = document.getElementById("bulkModeBtn");
const lineModeBtn = document.getElementById("lineModeBtn");
const editsContainer = document.getElementById("editsContainer");

const ruleInputSection = document.getElementById("ruleInputSection");
const riManualModeBtn = document.getElementById("riManualModeBtn");
const riAutoModeBtn = document.getElementById("riAutoModeBtn");
const riGridContainer = document.getElementById("riGridContainer");
const riAutomationHint = document.getElementById("riAutomationHint");

const debugRequest = document.getElementById("debugRequest");
const debugResponse = document.getElementById("debugResponse");

const staticTabBtn = document.getElementById("staticTabBtn");
const dynamicTabBtn = document.getElementById("dynamicTabBtn");
const staticToolsPanel = document.getElementById("staticToolsPanel");
const dynamicToolsPanel = document.getElementById("dynamicToolsPanel");

const frFindInput = document.getElementById("frFindInput");
const frReplaceInput = document.getElementById("frReplaceInput");
const frFindBtn = document.getElementById("frFindBtn");
const frPrevBtn = document.getElementById("frPrevBtn");
const frNextBtn = document.getElementById("frNextBtn");
const frMatchStatus = document.getElementById("frMatchStatus");
const frReplaceBtn = document.getElementById("frReplaceBtn");
const frReplaceAllBtn = document.getElementById("frReplaceAllBtn");
const frStatus = document.getElementById("frStatus");

const parenCheckBtn = document.getElementById("parenCheckBtn");
const parenResults = document.getElementById("parenResults");
const parenHighlightCheckbox = document.getElementById("parenHighlightCheckbox");

const autoSaveEnabled = document.getElementById("autoSaveEnabled");
const autoSaveIntervalButtons = Array.from(document.querySelectorAll("#autoSaveIntervalToggle .mode-btn"));
const autoSaveStatus = document.getElementById("autoSaveStatus");

// ─── Helpers ────────────────────────────────────────────────────────

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

async function getActiveTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) throw new Error("No active tab");
  return tab;
}

async function sendToContentScript(type, extra = {}) {
  const tab = await getActiveTab();
  const response = await chrome.tabs.sendMessage(tab.id, { type, ...extra });
  return response ?? { success: false, error: "No response from content script" };
}

async function refreshEditorState() {
  const result = await sendToContentScript("GET_EDITOR_STATE");
  if (!result.success) throw new Error(result.error || "Failed to read editor state");
  state.objectName = result.objectName;
  state.expression = result.expression;
  state.ruleInputs = result.ruleInputs;
  state.ruleInputAutomationSupported = result.ruleInputAutomationSupported ?? true;
  if (!state.ruleInputAutomationSupported) state.ruleInputMode = "manual";
  objectNameHint.textContent = state.objectName
    ? `Editing: ${state.objectName}`
    : "Open an expression rule in Appian to begin.";
  return result;
}

// ─── Ask AI ─────────────────────────────────────────────────────────

askBtn.addEventListener("click", async () => {
  const prompt = promptInput.value.trim();
  if (!prompt) return;

  statusDot.classList.remove("active", "error");
  askStatus.textContent = "Reading current expression...";
  askBtn.disabled = true;

  try {
    await refreshEditorState();

    const payload = {
      prompt,
      rule_inputs: state.ruleInputs,
      expression: state.expression,
    };
    state.lastRequestPayload = payload;
    debugRequest.textContent = JSON.stringify(payload, null, 2);

    askStatus.textContent = "Asking AI...";
    const response = await chrome.runtime.sendMessage({ type: "REQUEST_SUGGESTION", payload });

    if (!response?.success) {
      throw new Error(response?.error || "Backend request failed");
    }

    state.suggestion = response.data;

    // The real backend never produces a line-by-line diff of its own
    // (see computeLineDiff's header) — synthesize one from bulk_edit
    // whenever the backend left it empty, so Line-by-line mode has
    // something to show instead of just disappearing.
    const hasBackendLineEdits =
      Array.isArray(state.suggestion.line_by_line_edit) && state.suggestion.line_by_line_edit.length > 0;
    if (!hasBackendLineEdits && state.suggestion.bulk_edit) {
      state.suggestion.line_by_line_edit = computeLineDiff(state.expression, state.suggestion.bulk_edit);
    }

    debugResponse.textContent = JSON.stringify(state.suggestion, null, 2);

    state.mode = "bulk";
    state.lineStatus = (state.suggestion.line_by_line_edit || []).map(() => "pending");
    state.lineNavIndex = 0;
    state.ruleInputStatus = (state.suggestion.rule_input || []).map(() => "pending");

    askStatus.textContent = "";
    statusDot.classList.add("active");
    renderSuggestion();
  } catch (err) {
    askStatus.textContent = "Error: " + err.message;
    statusDot.classList.add("error");
  } finally {
    askBtn.disabled = false;
  }
});

// ─── Rendering: expression edits ───────────────────────────────────

function renderSuggestion() {
  const s = state.suggestion;
  if (!s) {
    suggestionSection.hidden = true;
    ruleInputSection.hidden = true;
    return;
  }

  suggestionSection.hidden = false;
  suggestionResponse.textContent = s.response || "";

  const hasBulk = typeof s.bulk_edit === "string" && s.bulk_edit.length > 0;
  const hasLine = Array.isArray(s.line_by_line_edit) && s.line_by_line_edit.length > 0;

  document.getElementById("modeToggle").hidden = !(hasBulk && hasLine);
  bulkModeBtn.disabled = !hasBulk;
  lineModeBtn.disabled = !hasLine;
  bulkModeBtn.classList.toggle("active", state.mode === "bulk");
  lineModeBtn.classList.toggle("active", state.mode === "line");

  if (state.mode === "bulk" && hasBulk) {
    renderBulkEdit();
  } else if (state.mode === "line" && hasLine) {
    renderLineEdits();
  } else {
    editsContainer.innerHTML = '<p class="empty-state">No expression changes suggested.</p>';
  }

  const hasRuleInputChanges = Array.isArray(s.rule_input) && s.rule_input.length > 0;
  ruleInputSection.hidden = !hasRuleInputChanges;
  if (hasRuleInputChanges) renderRuleInputSection();
}

bulkModeBtn.addEventListener("click", () => {
  if (bulkModeBtn.disabled) return;
  state.mode = "bulk";
  renderSuggestion();
});

lineModeBtn.addEventListener("click", () => {
  if (lineModeBtn.disabled) return;
  state.mode = "line";
  renderSuggestion();
  highlightCurrentLineEdit();
});

function renderBulkEdit() {
  editsContainer.innerHTML = `
    <div class="diff-card">
      <div class="diff-old">${escapeHtml(state.expression)}</div>
      <div class="diff-new">${escapeHtml(state.suggestion.bulk_edit)}</div>
      <div class="diff-actions">
        <button class="btn btn-accept" id="bulkAcceptBtn">Accept</button>
        <button class="btn btn-reject" id="bulkRejectBtn">Reject</button>
      </div>
      <p class="hint" id="bulkResult"></p>
    </div>
  `;

  document.getElementById("bulkAcceptBtn").addEventListener("click", async () => {
    const resultEl = document.getElementById("bulkResult");
    resultEl.textContent = "Applying...";
    const result = await sendToContentScript("APPLY_BULK_EDIT", { text: state.suggestion.bulk_edit });
    resultEl.textContent = result.success ? "Applied." : "Error: " + result.error;
    if (result.success) await refreshEditorState();
  });

  document.getElementById("bulkRejectBtn").addEventListener("click", () => {
    editsContainer.innerHTML = '<p class="empty-state">Rejected.</p>';
  });
}

// ▲/▼ step between line_by_line_edit entries the same way Find &
// Replace's match navigation does, highlighting each edit's location in
// the editor (via a search for edit.old's text) before you accept it —
// so you can see exactly what's about to change, one at a time.
function renderLineEdits() {
  const edits = state.suggestion.line_by_line_edit;
  if (state.lineNavIndex >= edits.length) state.lineNavIndex = 0;

  const navHtml =
    edits.length > 1
      ? `<div class="fr-nav">
           <button class="btn fr-nav-btn" id="lineNavPrevBtn" title="Previous edit">&#9650;</button>
           <span class="hint">Edit ${state.lineNavIndex + 1} of ${edits.length}</span>
           <button class="btn fr-nav-btn" id="lineNavNextBtn" title="Next edit">&#9660;</button>
         </div>`
      : "";

  const cardsHtml = edits
    .map((edit, i) => {
      const status = state.lineStatus[i];
      const isCurrent = i === state.lineNavIndex ? " diff-current" : "";
      return `
        <div class="diff-card ${status !== "pending" ? "diff-resolved" : ""}${isCurrent}" data-index="${i}">
          <div class="diff-old">${escapeHtml(edit.old)}</div>
          <div class="diff-new">${escapeHtml(edit.new)}</div>
          ${
            status === "pending"
              ? `<div class="diff-actions">
                   <button class="btn btn-accept" data-action="accept" data-index="${i}">Accept</button>
                   <button class="btn btn-reject" data-action="reject" data-index="${i}">Reject</button>
                 </div>`
              : `<p class="hint">${status === "accepted" ? "Accepted." : "Rejected."}</p>`
          }
        </div>
      `;
    })
    .join("");

  editsContainer.innerHTML = navHtml + cardsHtml;

  if (edits.length > 1) {
    document.getElementById("lineNavPrevBtn").addEventListener("click", () => navigateLineEdit(-1));
    document.getElementById("lineNavNextBtn").addEventListener("click", () => navigateLineEdit(1));
  }

  editsContainer.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const i = Number(btn.dataset.index);
      const action = btn.dataset.action;
      const edit = edits[i];

      if (action === "reject") {
        state.lineStatus[i] = "rejected";
        renderLineEdits();
        return;
      }

      btn.disabled = true;

      if (edit.atIndex !== undefined) {
        // computeLineDiff hunks' offsets are all computed once against
        // the expression as it stood before ANY hunk was applied — the
        // moment one gets accepted, every hunk that comes after it in
        // the document has a stale atIndex, which is exactly what threw
        // "expression changed since the check ran" on the second Accept.
        // Same fix as the parenthesis checker: after applying, recompute
        // the whole diff fresh against the live document instead of
        // trying to patch up stale offsets — a hunk that's now fully
        // applied simply won't show up in the new diff at all.
        const result = await sendToContentScript("APPLY_MULTI_CHAR_EDITS", { edits: [edit] });
        if (!result.success) {
          alert("Error applying edit: " + result.error); // eslint-disable-line no-alert
          renderLineEdits();
          return;
        }
        await refreshEditorState();
        state.suggestion.line_by_line_edit = state.suggestion.bulk_edit
          ? computeLineDiff(state.expression, state.suggestion.bulk_edit)
          : [];
        state.lineStatus = state.suggestion.line_by_line_edit.map(() => "pending");
        state.lineNavIndex = 0;
        renderSuggestion();
        await highlightCurrentLineEdit();
        return;
      }

      // Legacy path — a real backend-provided { old, new } diff with no
      // precomputed offsets, applied via substring search.
      const result = await sendToContentScript("APPLY_LINE_EDIT", { old: edit.old, new: edit.new });
      if (result.success) {
        state.lineStatus[i] = "accepted";
        await refreshEditorState();
      } else {
        alert("Error applying edit: " + result.error); // eslint-disable-line no-alert
      }
      renderLineEdits();
    });
  });
}

async function navigateLineEdit(delta) {
  const edits = state.suggestion.line_by_line_edit;
  state.lineNavIndex = (state.lineNavIndex + delta + edits.length) % edits.length;
  renderLineEdits();
  editsContainer
    .querySelector(`[data-index="${state.lineNavIndex}"]`)
    ?.scrollIntoView({ behavior: "smooth", block: "center" });
  await highlightCurrentLineEdit();
}

async function highlightCurrentLineEdit() {
  if (state.mode !== "line") return;
  const edits = state.suggestion?.line_by_line_edit;

  if (!edits || !edits.length) {
    // Nothing left to point at — clear the highlight rather than
    // leaving a stale one sitting on whatever line was highlighted
    // before the last hunk got accepted (which is what made it look
    // like accepting hadn't done anything).
    await sendToContentScript("CLEAR_HIGHLIGHT");
    return;
  }

  const edit = edits[state.lineNavIndex];
  // computeLineDiff hunks carry an exact line number; fall back to a
  // text search only for edits that don't (e.g. a real line-by-line
  // diff a future backend might send with just { old, new }).
  if (edit.line != null) {
    await sendToContentScript("HIGHLIGHT_LINE", { line: edit.line });
  } else {
    await sendToContentScript("HIGHLIGHT_TEXT_LOCATION", { text: edit.old });
  }
}

// ─── Rendering: rule input changes (grid + per-row Accept in bulk mode) ─

riManualModeBtn.addEventListener("click", () => {
  state.ruleInputMode = "manual";
  renderRuleInputSection();
});

riAutoModeBtn.addEventListener("click", () => {
  if (riAutoModeBtn.disabled) return;
  state.ruleInputMode = "auto";
  renderRuleInputSection();
});

function renderRuleInputSection() {
  riAutoModeBtn.disabled = !state.ruleInputAutomationSupported;
  riAutomationHint.hidden = state.ruleInputAutomationSupported;
  riManualModeBtn.classList.toggle("active", state.ruleInputMode === "manual");
  riAutoModeBtn.classList.toggle("active", state.ruleInputMode === "auto");
  renderRuleInputGrid();
}

function ruleInputActionCell(status, i) {
  if (status === "pending") {
    return `<button class="btn btn-accept" data-ri-action="accept" data-ri-index="${i}">Accept</button>
            <button class="btn btn-reject" data-ri-action="reject" data-ri-index="${i}">Reject</button>`;
  }
  if (status === "accepted") return '<span class="ri-fill-note">Name filled ✓</span>';
  if (status === "error") return '<span class="ri-fill-note ri-fill-error">Failed — see error below</span>';
  return '<span class="ri-fill-note">Rejected</span>';
}

function renderRuleInputGrid() {
  const changes = state.suggestion.rule_input;
  const showActions = state.ruleInputMode === "auto";

  const rowsHtml = changes
    .map((change, i) => {
      const target = change.new; // the grid always shows the proposed/target state
      const arrayCell = target.array ? '<input type="checkbox" checked disabled>' : "";
      // Defensive fallback: if this row's status was never set (e.g. a
      // stale render before a fresh Ask AI response), treat as pending
      // rather than silently falling through to "Rejected" below.
      const status = state.ruleInputStatus[i] ?? "pending";
      const hasDescription = !!(target.description && target.description.trim());
      const descCell = hasDescription
        ? `<button class="btn ri-copy-btn" data-ri-copy-index="${i}">Copy</button>`
        : '<span class="ri-fill-note">(none)</span>';
      return `
        <tr>
          <td>${escapeHtml(target.name)}</td>
          <td class="ri-desc-cell">${descCell}</td>
          <td>${escapeHtml(target.type || "")}</td>
          <td class="ri-array-cell">${arrayCell}</td>
          ${showActions ? `<td class="ri-actions-cell">${ruleInputActionCell(status, i)}</td>` : ""}
        </tr>
      `;
    })
    .join("");

  riGridContainer.innerHTML = `
    <div class="ri-grid-wrap">
      <table class="ri-grid">
        <colgroup>
          <col />
          <col class="ri-col-desc" />
          <col />
          <col class="ri-col-array" />
          ${showActions ? '<col class="ri-col-actions" />' : ""}
        </colgroup>
        <thead>
          <tr>
            <th>Name</th><th>Desc</th><th>Type</th><th>Arr</th>
            ${showActions ? "<th>Action</th>" : ""}
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>
  `;

  // Copy-to-clipboard for Description — always available regardless of
  // Manual/Auto mode, since it only touches the panel's own clipboard,
  // not Appian's page, so none of the automation-reliability concerns
  // elsewhere in this file apply to it.
  riGridContainer.querySelectorAll("[data-ri-copy-index]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const i = Number(btn.dataset.riCopyIndex);
      const description = changes[i].new.description || "";
      const original = btn.textContent;
      try {
        await navigator.clipboard.writeText(description);
        btn.textContent = "Copied!";
      } catch (err) {
        btn.textContent = "Copy failed";
        console.error("[Appian AI Assistant] clipboard write failed:", err); // eslint-disable-line no-console
      }
      setTimeout(() => {
        btn.textContent = original;
      }, 1200);
    });
  });

  if (!showActions) return;

  riGridContainer.querySelectorAll("[data-ri-action]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const i = Number(btn.dataset.riIndex);
      const action = btn.dataset.riAction;
      const change = changes[i];

      if (action === "reject") {
        state.ruleInputStatus[i] = "rejected";
        renderRuleInputGrid();
        return;
      }

      // Disable both buttons in this row while the single request runs
      // — one row at a time, at the user's own pace, rather than
      // looping through all of them back-to-back (confirmed live that
      // firing several of these in quick succession without a real
      // pause between them is unreliable).
      riGridContainer
        .querySelectorAll(`[data-ri-index="${i}"]`)
        .forEach((b) => (b.disabled = true));

      let result;
      const isNew = !change.old || !change.old.name;
      if (isNew) {
        result = await sendToContentScript("ADD_RULE_INPUT", { name: change.new.name });
      } else {
        const index = state.ruleInputs.findIndex((ri) => ri.name === change.old.name);
        if (index === -1) {
          result = { success: false, error: `Could not find existing rule input "${change.old.name}"` };
        } else {
          result = await sendToContentScript("EDIT_RULE_INPUT", { index, name: change.new.name });
        }
      }

      state.ruleInputStatus[i] = result.success ? "accepted" : "error";
      if (result.success) {
        await refreshEditorState();
      }
      renderRuleInputGrid();
      if (!result.success) {
        alert(`Error filling "${change.new.name}": ${result.error}`); // eslint-disable-line no-alert
      }
    });
  });
}

// ─── Dev Test: exercises the real chrome.debugger write path directly ─

document.getElementById("testEditBtn").addEventListener("click", async () => {
  const resultEl = document.getElementById("testEditResult");
  const text = document.getElementById("testEditInput").value;
  resultEl.textContent = "Sending...";
  try {
    const result = await sendToContentScript("APPLY_BULK_EDIT", { text });
    resultEl.textContent = JSON.stringify(result, null, 2);
  } catch (err) {
    resultEl.textContent = "Error: " + err.message;
  }
});

// ─── Top-level tabs ─────────────────────────────────────────────────

function switchTab(tab) {
  staticTabBtn.classList.toggle("active", tab === "static");
  dynamicTabBtn.classList.toggle("active", tab === "dynamic");
  staticToolsPanel.hidden = tab !== "static";
  dynamicToolsPanel.hidden = tab !== "dynamic";
}

staticTabBtn.addEventListener("click", () => switchTab("static"));
dynamicTabBtn.addEventListener("click", () => switchTab("dynamic"));

// ─── Static Tools: Find & Replace ──────────────────────────────────
//
// Find locates every occurrence of the search text and highlights the
// first one in the editor. ▲/▼ (or the arrow keys, while the Find input
// is focused) step between matches, re-highlighting as you go, so you
// can see exactly what you're about to change before Replace Selected
// commits it. The match list is a snapshot from the moment Find ran —
// Replace Selected re-validates the text at that exact position still
// matches before writing, and asks you to re-Find if the editor changed
// underneath it.

let frMatches = [];
let frCurrentIndex = -1;

function updateFrNav() {
  const hasMatches = frMatches.length > 0;
  frPrevBtn.disabled = !hasMatches;
  frNextBtn.disabled = !hasMatches;
  frReplaceBtn.disabled = !hasMatches;
}

async function highlightCurrentFrMatch() {
  const m = frMatches[frCurrentIndex];
  frMatchStatus.textContent = `Match ${frCurrentIndex + 1} of ${frMatches.length} (line ${m.line}).`;
  await sendToContentScript("HIGHLIGHT_LINE", { line: m.line });
}

frFindBtn.addEventListener("click", async () => {
  const find = frFindInput.value;
  if (!find) {
    frMatchStatus.textContent = "Enter text to find.";
    return;
  }

  frFindBtn.disabled = true;
  frMatchStatus.textContent = "Searching...";
  frStatus.textContent = "";
  try {
    const result = await sendToContentScript("FIND_MATCHES", { find });
    if (!result.success) {
      frMatches = [];
      frCurrentIndex = -1;
      frMatchStatus.textContent = "Error: " + result.error;
    } else {
      frMatches = result.matches;
      frCurrentIndex = frMatches.length ? 0 : -1;
      if (frCurrentIndex === -1) {
        frMatchStatus.textContent = "No matches found.";
        await sendToContentScript("CLEAR_HIGHLIGHT");
      } else {
        await highlightCurrentFrMatch();
      }
    }
  } catch (err) {
    frMatchStatus.textContent = "Error: " + err.message;
  } finally {
    frFindBtn.disabled = false;
    updateFrNav();
  }
});

frPrevBtn.addEventListener("click", async () => {
  if (!frMatches.length) return;
  frCurrentIndex = (frCurrentIndex - 1 + frMatches.length) % frMatches.length;
  await highlightCurrentFrMatch();
});

frNextBtn.addEventListener("click", async () => {
  if (!frMatches.length) return;
  frCurrentIndex = (frCurrentIndex + 1) % frMatches.length;
  await highlightCurrentFrMatch();
});

frFindInput.addEventListener("keydown", (e) => {
  if (e.key === "ArrowDown") {
    e.preventDefault();
    frNextBtn.click();
  } else if (e.key === "ArrowUp") {
    e.preventDefault();
    frPrevBtn.click();
  } else if (e.key === "Enter") {
    e.preventDefault();
    frFindBtn.click();
  }
});

frReplaceBtn.addEventListener("click", async () => {
  if (frCurrentIndex === -1) return;
  const find = frFindInput.value;
  const replace = frReplaceInput.value;
  const atIndex = frMatches[frCurrentIndex].index;

  frReplaceBtn.disabled = true;
  frStatus.textContent = "Replacing...";
  try {
    const result = await sendToContentScript("APPLY_REPLACE_AT_INDEX", { atIndex, find, replace });
    if (!result.success) {
      frStatus.textContent = "Error: " + result.error;
    } else {
      frStatus.textContent = `Replaced match on line ${result.line}.`;
      await refreshEditorState();
      // Indices shift after any edit — clear the stale match list rather
      // than risk replacing the wrong occurrence; user can click Find again.
      frMatches = [];
      frCurrentIndex = -1;
      frMatchStatus.textContent = "";
    }
  } catch (err) {
    frStatus.textContent = "Error: " + err.message;
  } finally {
    updateFrNav();
  }
});

frReplaceAllBtn.addEventListener("click", async () => {
  const find = frFindInput.value;
  const replace = frReplaceInput.value;
  if (!find) {
    frStatus.textContent = "Enter text to find.";
    return;
  }

  frReplaceAllBtn.disabled = true;
  frStatus.textContent = "Replacing all...";
  try {
    const result = await sendToContentScript("APPLY_FIND_REPLACE_ALL", { find, replace, highlight: true });
    frStatus.textContent = result.success ? `Replaced ${result.count} occurrence(s).` : "Error: " + result.error;
    if (result.success) await refreshEditorState();
  } catch (err) {
    frStatus.textContent = "Error: " + err.message;
  } finally {
    frMatches = [];
    frCurrentIndex = -1;
    frMatchStatus.textContent = "";
    updateFrNav();
    frReplaceAllBtn.disabled = false;
  }
});

// ─── Static Tools: Parenthesis Checker ─────────────────────────────

// Click-through navigator over a computed *repair plan* rather than raw
// bracket-matching diagnostics. The old approach (Analyzer's
// checkBracketMatching) reported every downstream mismatch as its own
// diagnostic, so a single missing "(" near the top of an expression
// cascaded into a wrong diagnosis for every closer after it — e.g.
// deleting 2 real extra characters could still leave 8 diagnostics
// because the rest were never separate problems, just fallout from the
// same one. computeBracketRepairPlan below instead greedily determines
// the minimal set of concrete edits (delete this extra closer / insert
// this closer here / insert this closer at the end) that makes the
// whole expression balanced, so the issue count directly reflects the
// number of real fixes needed and shrinks exactly in step with them.
const OPENER_TYPES = new Set([TokenType.OPEN_PAREN, TokenType.OPEN_BRACKET, TokenType.OPEN_BRACE]);
const CLOSER_TYPES = new Set([TokenType.CLOSE_PAREN, TokenType.CLOSE_BRACKET, TokenType.CLOSE_BRACE]);
const CLOSE_TYPE_FOR_OPEN = {
  [TokenType.OPEN_PAREN]: TokenType.CLOSE_PAREN,
  [TokenType.OPEN_BRACKET]: TokenType.CLOSE_BRACKET,
  [TokenType.OPEN_BRACE]: TokenType.CLOSE_BRACE,
};
const CHAR_FOR_CLOSE_TYPE = {
  [TokenType.CLOSE_PAREN]: ")",
  [TokenType.CLOSE_BRACKET]: "]",
  [TokenType.CLOSE_BRACE]: "}",
};

function computeBracketRepairPlan(tokens) {
  const stack = [];
  const raw = [];

  for (const token of tokens) {
    if (OPENER_TYPES.has(token.type)) {
      stack.push(token);
    } else if (CLOSER_TYPES.has(token.type)) {
      // Anything mismatched on top of the stack is greedily treated as
      // unclosed and given its missing closer right before this token,
      // then we re-check this token against what's left underneath.
      while (stack.length && CLOSE_TYPE_FOR_OPEN[stack[stack.length - 1].type] !== token.type) {
        const opener = stack.pop();
        raw.push({
          atIndex: token.startIndex,
          deleteCount: 0,
          insertText: CHAR_FOR_CLOSE_TYPE[CLOSE_TYPE_FOR_OPEN[opener.type]],
          line: token.line,
        });
      }
      if (stack.length) {
        stack.pop();
      } else {
        raw.push({
          atIndex: token.startIndex,
          deleteCount: token.value.length,
          insertText: "",
          expectedText: token.value,
          line: token.line,
        });
      }
    }
  }

  // Anything still open at the end needs closing, innermost (most
  // recently opened) first.
  while (stack.length) {
    const opener = stack.pop();
    raw.push({
      atEnd: true,
      deleteCount: 0,
      insertText: CHAR_FOR_CLOSE_TYPE[CLOSE_TYPE_FOR_OPEN[opener.type]],
      line: null,
    });
  }

  // Merge pure insertions that land at the exact same position (e.g.
  // several unclosed openers all needing to close at the end) into one
  // edit, concatenating in the order generated above — which is already
  // correct nesting order — so they can't get typed out of order by
  // being applied as separate, position-shifting edits.
  const merged = [];
  const insertIndexByKey = new Map();
  for (const edit of raw) {
    const isPureInsert = edit.deleteCount === 0 && edit.expectedText === undefined;
    if (isPureInsert) {
      const key = edit.atEnd ? "end" : `i:${edit.atIndex}`;
      if (insertIndexByKey.has(key)) {
        merged[insertIndexByKey.get(key)].insertText += edit.insertText;
        continue;
      }
      insertIndexByKey.set(key, merged.length);
    }
    merged.push({ ...edit });
  }

  return merged;
}

function describeParenEdit(edit) {
  if (edit.deleteCount > 0) {
    return { text: `Extra "${edit.expectedText}" — no matching opener.`, action: "Delete this character" };
  }
  if (edit.atEnd) {
    return {
      text: `Missing "${edit.insertText}" — expression ends before it's closed.`,
      action: `Add "${edit.insertText}" at the end of the expression`,
    };
  }
  return {
    text: `Missing "${edit.insertText}" before this point.`,
    action: `Insert "${edit.insertText}" here`,
  };
}

let parenPlan = [];
let parenIndex = -1;
let parenTotalLines = 1;

async function runParenCheck() {
  const { expression } = await refreshEditorState();
  if (!expression || !expression.trim()) {
    parenResults.innerHTML = '<p class="empty-state">Expression is empty.</p>';
    parenPlan = [];
    parenIndex = -1;
    if (parenHighlightCheckbox.checked) await sendToContentScript("CLEAR_HIGHLIGHT");
    return;
  }

  parenTotalLines = expression.split("\n").length;
  const tokens = new Tokenizer(expression).tokenize();
  parenPlan = computeBracketRepairPlan(tokens);

  if (parenPlan.length === 0) {
    parenResults.innerHTML = '<p class="empty-state">All parentheses/brackets/braces are matched.</p>';
    parenIndex = -1;
    if (parenHighlightCheckbox.checked) await sendToContentScript("CLEAR_HIGHLIGHT");
    return;
  }

  if (parenIndex < 0 || parenIndex >= parenPlan.length) parenIndex = 0;
  renderParenNav();
  if (parenHighlightCheckbox.checked) await highlightCurrentParenIssue();
}

parenCheckBtn.addEventListener("click", async () => {
  parenResults.innerHTML = '<p class="hint">Checking...</p>';
  try {
    await runParenCheck();
  } catch (err) {
    parenResults.innerHTML = `<p class="hint">Error: ${escapeHtml(err.message)}</p>`;
  }
});

function renderParenNav() {
  const edit = parenPlan[parenIndex];
  const { text, action } = describeParenEdit(edit);
  const lineLabel = edit.atEnd ? `end (line ${parenTotalLines})` : `line ${edit.line}`;

  parenResults.innerHTML = `
    <p class="hint">${parenPlan.length} fix(es) needed.</p>
    <div class="fr-nav">
      <button class="btn fr-nav-btn" id="parenPrevBtn" title="Previous issue">&#9650;</button>
      <span class="hint">Issue ${parenIndex + 1} of ${parenPlan.length} (${lineLabel})</span>
      <button class="btn fr-nav-btn" id="parenNextBtn" title="Next issue">&#9660;</button>
    </div>
    <p class="hint">${escapeHtml(text)}</p>
    <button class="btn" id="parenFixBtn">${escapeHtml(action)}</button>
    <button class="btn" id="parenResolveAllBtn">Resolve All (${parenPlan.length})</button>
    <p class="hint" id="parenFixStatus"></p>
  `;

  document.getElementById("parenPrevBtn").addEventListener("click", () => navigateParenIssue(-1));
  document.getElementById("parenNextBtn").addEventListener("click", () => navigateParenIssue(1));
  document.getElementById("parenFixBtn").addEventListener("click", () => applyParenFix(edit));
  document.getElementById("parenResolveAllBtn").addEventListener("click", applyParenResolveAll);
}

async function navigateParenIssue(delta) {
  parenIndex = (parenIndex + delta + parenPlan.length) % parenPlan.length;
  renderParenNav();
  if (parenHighlightCheckbox.checked) await highlightCurrentParenIssue();
}

async function highlightCurrentParenIssue() {
  const edit = parenPlan[parenIndex];
  const line = edit.atEnd ? parenTotalLines : edit.line;
  const hl = await sendToContentScript("HIGHLIGHT_LINE", { line });
  if (!hl.success) {
    parenResults.innerHTML += `<p class="hint">Couldn't highlight in editor: ${escapeHtml(hl.error)}</p>`;
  }
}

async function applyParenFix(edit) {
  const statusEl = document.getElementById("parenFixStatus");
  statusEl.textContent = "Applying...";
  try {
    const result = await sendToContentScript("APPLY_MULTI_CHAR_EDITS", { edits: [edit] });
    if (!result.success) {
      statusEl.textContent = "Error: " + result.error;
      return;
    }
    statusEl.textContent = "Fixed. Re-checking...";
    await runParenCheck();
  } catch (err) {
    statusEl.textContent = "Error: " + err.message;
  }
}

async function applyParenResolveAll() {
  const statusEl = document.getElementById("parenFixStatus");
  statusEl.textContent = `Applying ${parenPlan.length} fix(es)...`;
  try {
    const result = await sendToContentScript("APPLY_MULTI_CHAR_EDITS", { edits: parenPlan });
    if (!result.success) {
      statusEl.textContent = "Error: " + result.error;
      return;
    }
    statusEl.textContent = "Resolved. Re-checking...";
    await runParenCheck();
  } catch (err) {
    statusEl.textContent = "Error: " + err.message;
  }
}

// ─── Static Tools: Auto-Save ────────────────────────────────────────

let autoSaveTimer = null;

function stopAutoSave() {
  if (autoSaveTimer) {
    clearInterval(autoSaveTimer);
    autoSaveTimer = null;
  }
}

async function runAutoSave() {
  const time = new Date().toLocaleTimeString();
  try {
    const tab = await getActiveTab();
    if (!/appiancloud\.com|appian\.community/.test(tab.url || "")) {
      autoSaveStatus.textContent = `Auto-save on — skipped at ${time}: active tab isn't an Appian page.`;
      return;
    }
    const result = await chrome.tabs
      .sendMessage(tab.id, { type: "TRIGGER_SAVE" })
      .catch((err) => ({ success: false, error: err.message }));

    autoSaveStatus.textContent = result?.success
      ? `Auto-save on — last saved at ${time}.`
      : `Auto-save on — last attempt at ${time} failed: ${result?.error || "no response from the Appian tab"}`;
  } catch (err) {
    autoSaveStatus.textContent = `Auto-save on — last attempt at ${time} failed: ${err.message}`;
  }
}

let autoSaveMinutes = 5;

autoSaveIntervalButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    autoSaveIntervalButtons.forEach((b) => b.classList.toggle("active", b === btn));
    autoSaveMinutes = Number(btn.dataset.minutes);
    if (autoSaveEnabled.checked) {
      // Re-arm with the new interval.
      autoSaveEnabled.dispatchEvent(new Event("change"));
    }
  });
});

autoSaveEnabled.addEventListener("change", () => {
  stopAutoSave();
  if (!autoSaveEnabled.checked) {
    autoSaveStatus.textContent = "Auto-save is off.";
    return;
  }
  autoSaveStatus.textContent = `Auto-save on — will save every ${autoSaveMinutes} minute(s).`;
  autoSaveTimer = setInterval(runAutoSave, autoSaveMinutes * 60 * 1000);
});

// ─── Init ───────────────────────────────────────────────────────────

refreshEditorState().catch(() => {
  // No Appian tab active yet — leave the default hint in place.
});
