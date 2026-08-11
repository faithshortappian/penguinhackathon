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
 */

// ─── State ──────────────────────────────────────────────────────────

const state = {
  objectName: "",
  expression: "",
  ruleInputs: [],
  suggestion: null, // { response, rule_input, bulk_edit, line_by_line_edit }
  mode: "bulk", // expression edit mode: "bulk" | "line"
  lineStatus: [], // per line_by_line_edit entry: "pending" | "accepted" | "rejected"
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
    debugResponse.textContent = JSON.stringify(state.suggestion, null, 2);

    state.mode = "bulk";
    state.lineStatus = (state.suggestion.line_by_line_edit || []).map(() => "pending");
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

function renderLineEdits() {
  const edits = state.suggestion.line_by_line_edit;
  editsContainer.innerHTML = edits
    .map((edit, i) => {
      const status = state.lineStatus[i];
      return `
        <div class="diff-card ${status !== "pending" ? "diff-resolved" : ""}" data-index="${i}">
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

// ─── Init ───────────────────────────────────────────────────────────

refreshEditorState().catch(() => {
  // No Appian tab active yet — leave the default hint in place.
});
