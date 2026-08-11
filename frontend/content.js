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
  const {
    locateEditorRoot,
    readState,
    applyEditViaKeystrokes,
    applyRangeEditViaKeystrokes,
    triggerSave,
    readExpressionValue,
    highlightLine,
    clearHighlight,
  } = await import(chrome.runtime.getURL("content/editor-bridge.js"));
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

  // Appian's Interface Designer also has a "Rule Inputs" panel and its
  // "+" control also matches [aria-label*="New Rule Input"] — but it
  // opens a modal dialog (Name/Description/Type/Array all in one form)
  // instead of an inline editable grid row. Confirmed live: our
  // automation would click it, then time out waiting for a row that
  // never appears, leaving the modal open and unfilled. Rather than
  // build a second automation path for that modal, only allow
  // automated rule-input writes in the one editor confirmed compatible
  // with the grid-based flow this file implements.
  function ruleInputAutomationSupported() {
    return document.title.includes("Expression Rule Designer");
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

  // 1-indexed line number containing a given character offset.
  function lineNumberAtIndex(text, index) {
    return text.slice(0, index).split("\n").length;
  }

  // 0-indexed {line, ch} CodeMirror position for a character offset.
  function positionAtIndex(text, index) {
    const before = text.slice(0, index);
    const lines = before.split("\n");
    return { line: lines.length - 1, ch: lines[lines.length - 1].length };
  }

  // Prefer the debugger-based accurate read (see readExpressionValue's
  // header) over the DOM join, which drops lines scrolled out of view —
  // the same bug that mislocated the parenthesis checker's line numbers
  // would also mislocate find/replace matches in a long expression.
  async function getAccurateExpressionText(root) {
    const valueResult = await readExpressionValue();
    if (valueResult.success && typeof valueResult.value === "string") return valueResult.value;
    return root ? readState(root)?.fullText ?? "" : "";
  }

  chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === "GET_EDITOR_STATE") {
      const root = findMainEditor();
      const domText = root ? readState(root)?.fullText ?? "" : "";
      // Prefer the debugger-based read (accurate even when lines are
      // scrolled out of the DOM); fall back to the DOM join if it fails
      // for any reason (e.g. debugger unavailable).
      readExpressionValue()
        .then((valueResult) => {
          const expression =
            valueResult.success && typeof valueResult.value === "string" ? valueResult.value : domText;
          sendResponse({
            success: true,
            objectName: objectNameFromTitle(),
            expression,
            ruleInputs: readRuleInputs(),
            ruleInputAutomationSupported: ruleInputAutomationSupported(),
          });
        })
        .catch(() => {
          sendResponse({
            success: true,
            objectName: objectNameFromTitle(),
            expression: domText,
            ruleInputs: readRuleInputs(),
            ruleInputAutomationSupported: ruleInputAutomationSupported(),
          });
        });
      return true;
    }

    if (message.type === "HIGHLIGHT_LINE") {
      highlightLine(message.line)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }

    if (message.type === "CLEAR_HIGHLIGHT") {
      clearHighlight()
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ success: false, error: err.message }));
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

    if (message.type === "FIND_MATCHES") {
      const root = findMainEditor();
      if (!root) {
        sendResponse({ success: false, error: "No expression editor found on this page" });
        return true;
      }
      if (!message.find) {
        sendResponse({ success: false, error: "Enter text to find." });
        return true;
      }
      getAccurateExpressionText(root)
        .then((text) => {
          const matches = [];
          let idx = text.indexOf(message.find);
          while (idx !== -1) {
            matches.push({ index: idx, line: lineNumberAtIndex(text, idx) });
            idx = text.indexOf(message.find, idx + message.find.length);
          }
          sendResponse({ success: true, matches, text });
        })
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }

    if (message.type === "APPLY_REPLACE_AT_INDEX") {
      const root = findMainEditor();
      if (!root) {
        sendResponse({ success: false, error: "No expression editor found on this page" });
        return true;
      }
      getAccurateExpressionText(root)
        .then(async (currentText) => {
          const { atIndex, find, replace } = message;
          if (currentText.slice(atIndex, atIndex + find.length) !== find) {
            sendResponse({ success: false, error: "The expression changed since Find — click Find again." });
            return;
          }
          const from = positionAtIndex(currentText, atIndex);
          const to = positionAtIndex(currentText, atIndex + find.length);
          const result = await applyRangeEditViaKeystrokes([{ from, to }], replace);
          sendResponse({ ...result, line: from.line + 1 });
        })
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }

    if (message.type === "APPLY_FIND_REPLACE_ALL") {
      const root = findMainEditor();
      if (!root) {
        sendResponse({ success: false, error: "No expression editor found on this page" });
        return true;
      }
      getAccurateExpressionText(root)
        .then(async (currentText) => {
          const { find, replace } = message;
          if (!currentText.includes(find)) {
            sendResponse({ success: false, error: `Could not find text to replace: ${JSON.stringify(find)}` });
            return;
          }

          const indices = [];
          let idx = currentText.indexOf(find);
          while (idx !== -1) {
            indices.push(idx);
            idx = currentText.indexOf(find, idx + find.length);
          }

          if (message.highlight) {
            await highlightLine(lineNumberAtIndex(currentText, indices[0])).catch(() => {});
          }

          // Replace from the end backward so earlier matches' positions
          // never shift out from under the ones still to come.
          const ranges = indices
            .slice()
            .reverse()
            .map((i) => ({
              from: positionAtIndex(currentText, i),
              to: positionAtIndex(currentText, i + find.length),
            }));

          const result = await applyRangeEditViaKeystrokes(ranges, replace);
          sendResponse({ ...result, count: indices.length });
        })
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }

    if (message.type === "TRIGGER_SAVE") {
      triggerSave()
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }

    if (message.type === "ADD_RULE_INPUT") {
      if (!ruleInputAutomationSupported()) {
        sendResponse({ success: false, error: "Rule input automation isn't supported in this editor" });
        return true;
      }
      // Name only, by design — see content/rule-inputs-bridge.js header.
      addRuleInput(message.name)
        .then((result) => sendResponse(result))
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }

    if (message.type === "EDIT_RULE_INPUT") {
      if (!ruleInputAutomationSupported()) {
        sendResponse({ success: false, error: "Rule input automation isn't supported in this editor" });
        return true;
      }
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
