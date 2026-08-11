/**
 * Content script entry point for the Appian Expression Analyzer.
 * Locates the SAIL expression editor and rule inputs grid, and exposes
 * them to the rest of the extension via runtime messages.
 *
 * Manifest V3 content scripts declared in content_scripts[] are always
 * loaded as classic (non-module) scripts — there's no manifest option
 * to change that, unlike the background service worker. Static `import`
 * throws a SyntaxError in that context. Dynamic `import()` still works
 * from a classic script, so that's how the bridge modules are loaded
 * here.
 */

(async () => {
  const { locateEditorRoot, readState, applyEditViaKeystrokes } = await import(
    chrome.runtime.getURL("content/editor-bridge.js")
  );
  const { readRuleInputs, addRuleInput, editRuleInputName } = await import(
    chrome.runtime.getURL("content/rule-inputs-bridge.js")
  );

  function findMainEditor() {
    return (
      document.querySelector(".ExpressionEditorWidget---fit .CodeMirror") ||
      document.querySelector(".CodeMirror") ||
      document.querySelector(".cm-editor")
    );
  }

  // e.g. "ZS_TestRule • Appian Expression Rule Designer" -> "ZS_TestRule"
  function objectNameFromTitle() {
    return document.title.split("•")[0].trim();
  }

  function applyLineEdit(currentText, find, replace) {
    const index = currentText.indexOf(find);
    if (index === -1) {
      return { success: false, error: `Could not find text to replace: ${JSON.stringify(find)}` };
    }
    // First occurrence only — there's no position info in a
    // find/replace hunk to disambiguate repeated substrings.
    const newText = currentText.slice(0, index) + replace + currentText.slice(index + find.length);
    return { success: true, newText };
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "GET_EDITOR_STATE") {
      const root = findMainEditor();
      sendResponse({
        success: true,
        objectName: objectNameFromTitle(),
        expression: root ? readState(root)?.fullText ?? "" : "",
        ruleInputs: readRuleInputs(),
      });
      return true;
    }

    if (message.type === "APPLY_BULK_EDIT") {
      const root = findMainEditor();
      if (!root) {
        sendResponse({ success: false, error: "No expression editor found on this page" });
        return true;
      }
      applyEditViaKeystrokes(root, message.text)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }

    if (message.type === "APPLY_LINE_EDIT") {
      const root = findMainEditor();
      if (!root) {
        sendResponse({ success: false, error: "No expression editor found on this page" });
        return true;
      }
      const currentText = readState(root)?.fullText ?? "";
      const edit = applyLineEdit(currentText, message.old, message.new);
      if (!edit.success) {
        sendResponse(edit);
        return true;
      }
      applyEditViaKeystrokes(root, edit.newText)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }

    if (message.type === "ADD_RULE_INPUT") {
      // Name only, by design — see content/rule-inputs-bridge.js header.
      addRuleInput(message.name)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }

    if (message.type === "EDIT_RULE_INPUT") {
      // Name only, by design — see content/rule-inputs-bridge.js header.
      editRuleInputName(message.index, message.name)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }

    return false;
  });

  console.log("[Appian AI Assistant] content script loaded. Editor found:", !!findMainEditor());
  console.log("[Appian AI Assistant] locateEditorRoot check:", locateEditorRoot(document));
})();
