/**
 * Service Worker for the Appian Expression Analyzer extension.
 * Handles communication between content script, side panel, and backend API.
 */

import {
  replaceAllText,
  replaceRangesText,
  applyMixedRangeEdits,
  typeText,
  click,
  pressEnter,
  typeThenSelectWithEnter,
  getEditorValue,
  highlightEditorLine,
  clearEditorHighlight,
} from "./background/cdp-typer.js";

// Default backend URL — configurable via extension storage
const DEFAULT_BACKEND_URL = "http://localhost:8000";

async function getBackendUrl() {
  const result = await chrome.storage.local.get("backendUrl");
  return result.backendUrl || DEFAULT_BACKEND_URL;
}

// Open side panel when extension icon is clicked
chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ tabId: tab.id });
});

// Listen for messages from content script and panel
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    case "EXPRESSION_EXTRACTED":
      // Forward extracted expression to the side panel
      chrome.runtime.sendMessage({
        type: "ANALYSIS_INPUT",
        payload: message.payload,
      });
      break;

    case "FETCH_APP_CONTEXT":
      fetchAppContext(message.appUuid)
        .then((data) => sendResponse({ success: true, data }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true; // Keep channel open for async response

    case "VALIDATE_EXPRESSION":
      validateWithBackend(message.expression, message.appUuid)
        .then((data) => sendResponse({ success: true, data }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "APPLY_EDIT_VIA_KEYSTROKES":
      if (!sender.tab?.id) {
        sendResponse({ success: false, error: "No tab associated with this request" });
        break;
      }
      replaceAllText(sender.tab.id, message.text)
        .then(() => sendResponse({ success: true }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "APPLY_RANGE_EDIT_VIA_KEYSTROKES":
      if (!sender.tab?.id) {
        sendResponse({ success: false, error: "No tab associated with this request" });
        break;
      }
      replaceRangesText(sender.tab.id, message.ranges, message.text)
        .then(() => sendResponse({ success: true }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "APPLY_MIXED_RANGE_EDITS_VIA_KEYSTROKES":
      if (!sender.tab?.id) {
        sendResponse({ success: false, error: "No tab associated with this request" });
        break;
      }
      applyMixedRangeEdits(sender.tab.id, message.edits)
        .then(() => sendResponse({ success: true }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "TYPE_TEXT_VIA_KEYSTROKES":
      if (!sender.tab?.id) {
        sendResponse({ success: false, error: "No tab associated with this request" });
        break;
      }
      typeText(sender.tab.id, message.text)
        .then(() => sendResponse({ success: true }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "PRESS_ENTER_VIA_DEBUGGER":
      if (!sender.tab?.id) {
        sendResponse({ success: false, error: "No tab associated with this request" });
        break;
      }
      pressEnter(sender.tab.id)
        .then(() => sendResponse({ success: true }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "TYPE_THEN_SELECT_WITH_ENTER":
      if (!sender.tab?.id) {
        sendResponse({ success: false, error: "No tab associated with this request" });
        break;
      }
      typeThenSelectWithEnter(sender.tab.id, message.text)
        .then(() => sendResponse({ success: true }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "CLICK_VIA_DEBUGGER":
      if (!sender.tab?.id) {
        sendResponse({ success: false, error: "No tab associated with this request" });
        break;
      }
      click(sender.tab.id, message.x, message.y)
        .then(() => sendResponse({ success: true }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "GET_EDITOR_VALUE_VIA_DEBUGGER":
      if (!sender.tab?.id) {
        sendResponse({ success: false, error: "No tab associated with this request" });
        break;
      }
      getEditorValue(sender.tab.id)
        .then((value) => sendResponse({ success: true, value }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "HIGHLIGHT_EDITOR_LINE":
      if (!sender.tab?.id) {
        sendResponse({ success: false, error: "No tab associated with this request" });
        break;
      }
      highlightEditorLine(sender.tab.id, message.line)
        .then(() => sendResponse({ success: true }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "CLEAR_EDITOR_HIGHLIGHT":
      if (!sender.tab?.id) {
        sendResponse({ success: false, error: "No tab associated with this request" });
        break;
      }
      clearEditorHighlight(sender.tab.id)
        .then(() => sendResponse({ success: true }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "REQUEST_SUGGESTION":
      requestSuggestion(message.payload)
        .then((data) => sendResponse({ success: true, data }))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;

    case "SET_BACKEND_URL":
      chrome.storage.local.set({ backendUrl: message.url });
      sendResponse({ success: true });
      return true;

    case "SET_APP_UUID":
      chrome.storage.local.set({ appUuid: message.appUuid });
      sendResponse({ success: true });
      return true;

    case "GET_SETTINGS":
      chrome.storage.local.get(["backendUrl", "appUuid"]).then((result) => {
        sendResponse({
          backendUrl: result.backendUrl || DEFAULT_BACKEND_URL,
          appUuid: result.appUuid || "",
        });
      });
      return true;

    default:
      break;
  }
});

async function fetchAppContext(appUuid) {
  const backendUrl = await getBackendUrl();
  const resp = await fetch(`${backendUrl}/api/v1/app/${appUuid}/context`);
  if (!resp.ok) throw new Error(`Backend returned ${resp.status}`);
  return resp.json();
}

/**
 * payload: { prompt, rule_inputs, expression }
 * returns: { response, rule_input, bulk_edit, line_by_line_edit }
 *
 * Adapter for the real backend contract, which turned out simpler than
 * what the rest of the extension is built around: POST
 * /api/v1/ai/process takes { code, prompt, ruleInputs, appUuid } and
 * returns { summary, code, ruleInputs } — a single full-replacement
 * `code` string (no separate bulk/line-by-line diff format) and a flat
 * ruleInputs list of just { name, type } (no description/array, no
 * old/new pairing — it's the AI's suggested full set, not a diff). This
 * function is the one place that gap is bridged, translating both
 * directions, so panel.js can keep working against the original
 * { response, rule_input, bulk_edit, line_by_line_edit } shape
 * unchanged. line_by_line_edit is always empty since the backend never
 * produces one — the Suggestion section's mode toggle already hides
 * itself when that's the case. rule_input only ever contains additions
 * (old: null) — an input name the backend already knows about is
 * treated as unchanged, since there's no old/new pairing to detect a
 * rename from. If the backend later grows to return more of the
 * original shape natively, only this function needs to change.
 */
async function requestSuggestion(payload) {
  const backendUrl = await getBackendUrl();
  const currentRuleInputs = payload.rule_inputs || [];

  const resp = await fetch(`${backendUrl}/api/v1/ai/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code: payload.expression || "",
      prompt: payload.prompt || "",
      ruleInputs: currentRuleInputs.map((ri) => ({ name: ri.name, type: ri.type || "Text" })),
      appUuid: payload.appUuid ?? null,
    }),
  });
  if (!resp.ok) throw new Error(`Backend returned ${resp.status}`);
  const result = await resp.json();

  const currentNames = new Set(currentRuleInputs.map((ri) => ri.name));
  const rule_input = (result.ruleInputs || [])
    .filter((ri) => !currentNames.has(ri.name))
    .map((ri) => ({
      old: null,
      new: { name: ri.name, description: "", type: ri.type || "", array: false },
    }));

  return {
    response: result.summary || "",
    bulk_edit: result.code || "",
    line_by_line_edit: [],
    rule_input,
  };
}

async function validateWithBackend(expression, appUuid = null) {
  const backendUrl = await getBackendUrl();
  const body = { expression };
  if (appUuid) body.app_uuid = appUuid;

  const resp = await fetch(`${backendUrl}/api/v1/validate-expression`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) throw new Error(`Backend returned ${resp.status}`);
  return resp.json();
}
