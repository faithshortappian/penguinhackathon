/**
 * Service Worker for the Appian Expression Analyzer extension.
 * Handles communication between content script, side panel, and backend API.
 */

import { replaceAllText, typeText, click, pressEnter, typeThenSelectWithEnter } from "./background/cdp-typer.js";

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
 * See frontend/README.md "AI suggestion contract" for the full shape —
 * this is the one place the exact backend URL/fields need to match
 * whatever the backend actually implements.
 */
async function requestSuggestion(payload) {
  const backendUrl = await getBackendUrl();
  const resp = await fetch(`${backendUrl}/api/v1/suggest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!resp.ok) throw new Error(`Backend returned ${resp.status}`);
  return resp.json();
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
