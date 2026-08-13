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
    applyMixedRangeEditsViaKeystrokes,
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

  // Find & Replace's case-sensitivity toggle (off by default). Folding
  // both sides to lowercase for the search is fine for the ASCII
  // SAIL-expression content this deals with — it preserves string
  // length, so the resulting index lines up with the real (original-
  // case) text. The matched substring's actual case is never touched;
  // only what gets searched FOR changes.
  function findIndex(haystack, needle, fromIndex, caseSensitive) {
    if (caseSensitive) return haystack.indexOf(needle, fromIndex);
    return haystack.toLowerCase().indexOf(needle.toLowerCase(), fromIndex);
  }

  // 0-indexed {line, ch} CodeMirror position for a character offset.
  function positionAtIndex(text, index) {
    const before = text.slice(0, index);
    const lines = before.split("\n");
    return { line: lines.length - 1, ch: lines[lines.length - 1].length };
  }

  // Fallback for APPLY_TEXT_REPLACEMENT when an exact substring match
  // fails: searches line-by-line ignoring each line's leading
  // whitespace (same normalization computeLineDiff uses internally in
  // panel.js), then maps the match back to real character offsets in
  // the actual (unstripped) text. An exact match can fail even when the
  // content itself hasn't meaningfully changed — e.g. if Appian
  // reindents the expression on its own (such as when Auto-Save
  // triggers a real Save) between when the diff was computed and when
  // a section gets accepted.
  function findLinesIgnoringIndent(haystack, needle) {
    if (!needle) return { startIndex: 0, endIndex: 0 };
    const stripIndent = (line) => line.replace(/^[ \t]+/, "");
    const haystackLines = haystack.split("\n");
    const haystackNorm = haystackLines.map(stripIndent);
    const needleLines = needle.split("\n").map(stripIndent);

    for (let start = 0; start <= haystackNorm.length - needleLines.length; start++) {
      let matches = true;
      for (let k = 0; k < needleLines.length; k++) {
        if (haystackNorm[start + k] !== needleLines[k]) {
          matches = false;
          break;
        }
      }
      if (!matches) continue;

      let startIndex = 0;
      for (let k = 0; k < start; k++) startIndex += haystackLines[k].length + 1;
      let endIndex = startIndex;
      for (let k = start; k < start + needleLines.length; k++) endIndex += haystackLines[k].length + 1;
      endIndex -= 1; // exclude the trailing newline after the last matched line
      return { startIndex, endIndex };
    }
    return null;
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

    if (message.type === "HIGHLIGHT_TEXT_LOCATION") {
      const root = findMainEditor();
      if (!root) {
        sendResponse({ success: false, error: "No expression editor found on this page" });
        return true;
      }
      getAccurateExpressionText(root)
        .then(async (text) => {
          let idx = text.indexOf(message.text);
          if (idx === -1) {
            const healed = findLinesIgnoringIndent(text, message.text);
            idx = healed ? healed.startIndex : -1;
          }
          if (idx === -1) {
            sendResponse({ success: false, error: "Could not locate this text in the current expression." });
            return;
          }
          const line = lineNumberAtIndex(text, idx);
          const result = await highlightLine(line);
          sendResponse({ ...result, line });
        })
        .catch((err) => sendResponse({ success: false, error: err.message }));
      return true;
    }

    if (message.type === "APPLY_MULTI_CHAR_EDITS") {
      const root = findMainEditor();
      if (!root) {
        sendResponse({ success: false, error: "No expression editor found on this page" });
        return true;
      }
      getAccurateExpressionText(root)
        .then(async (currentText) => {
          // Resolve each item's absolute index against ONE shared
          // snapshot of the current text (atEnd items resolve to its
          // length), so a batch of edits can be validated and ordered
          // consistently before anything is actually typed.
          const items = message.edits.map((item) => ({
            ...item,
            atIndex: item.atEnd ? currentText.length : item.atIndex,
          }));

          for (const item of items) {
            const actual = currentText.slice(item.atIndex, item.atIndex + (item.deleteCount || 0));
            if (item.expectedText && actual !== item.expectedText) {
              // The precomputed offset doesn't match anymore — usually a
              // sign of small cumulative drift (an earlier edit in this
              // same session landing a character or two off from what
              // was predicted), not that the document actually changed
              // in a way that invalidates this specific edit. Self-heal
              // by searching for the expected text instead of failing
              // outright, but only when it's long enough to be a real
              // anchor — the parenthesis fixer's expectedText is often a
              // single bracket character, and indexOf(")") would match
              // almost anywhere in the document, healing to a
              // completely unrelated character instead of the one that
              // was actually flagged.
              const found = item.expectedText.length >= 4 ? currentText.indexOf(item.expectedText) : -1;
              if (found === -1) {
                sendResponse({
                  success: false,
                  error: "The expression changed since the check ran — click Check Current Expression again.",
                });
                return;
              }
              item.atIndex = found;
            }
          }

          // Apply from the end of the document backward so earlier
          // edits' positions never shift out from under the ones still
          // to come — same principle as Find & Replace All.
          const sorted = items.slice().sort((a, b) => b.atIndex - a.atIndex);
          const ranges = sorted.map((item) => ({
            from: positionAtIndex(currentText, item.atIndex),
            to: positionAtIndex(currentText, item.atIndex + (item.deleteCount || 0)),
            text: item.insertText || "",
          }));

          const result = await applyMixedRangeEditsViaKeystrokes(ranges);
          sendResponse(result);
        })
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
          const caseSensitive = !!message.caseSensitive;
          const matches = [];
          let idx = findIndex(text, message.find, 0, caseSensitive);
          while (idx !== -1) {
            matches.push({ index: idx, line: lineNumberAtIndex(text, idx) });
            idx = findIndex(text, message.find, idx + message.find.length, caseSensitive);
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
          const { atIndex, find, replace, caseSensitive } = message;
          const actualAtIndex = currentText.slice(atIndex, atIndex + find.length);
          const stillMatches = caseSensitive
            ? actualAtIndex === find
            : actualAtIndex.toLowerCase() === find.toLowerCase();
          if (!stillMatches) {
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

    if (message.type === "APPLY_TEXT_REPLACEMENT") {
      // Section-by-section editing's apply path: search the LIVE
      // document fresh for findText, right now, rather than trusting a
      // precomputed position — self-correcting regardless of what else
      // has changed elsewhere in the document (including from other
      // sections already accepted this session).
      const root = findMainEditor();
      if (!root) {
        sendResponse({ success: false, error: "No expression editor found on this page" });
        return true;
      }
      getAccurateExpressionText(root)
        .then(async (currentText) => {
          const { findText, replacement } = message;
          let startIndex;
          let endIndex;

          if (!findText) {
            startIndex = 0;
            endIndex = 0;
          } else {
            const exactIdx = currentText.indexOf(findText);
            if (exactIdx !== -1) {
              startIndex = exactIdx;
              endIndex = exactIdx + findText.length;
            } else {
              const healed = findLinesIgnoringIndent(currentText, findText);
              if (!healed) {
                sendResponse({
                  success: false,
                  error:
                    "Could not find this section's text in the current expression — it may already be up to date.",
                });
                return;
              }
              startIndex = healed.startIndex;
              endIndex = healed.endIndex;
            }
          }

          const from = positionAtIndex(currentText, startIndex);
          const to = positionAtIndex(currentText, endIndex);
          const result = await applyRangeEditViaKeystrokes([{ from, to }], replacement);
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
          const { find, replace, caseSensitive } = message;
          const indices = [];
          let idx = findIndex(currentText, find, 0, caseSensitive);
          while (idx !== -1) {
            indices.push(idx);
            idx = findIndex(currentText, find, idx + find.length, caseSensitive);
          }
          if (indices.length === 0) {
            sendResponse({ success: false, error: `Could not find text to replace: ${JSON.stringify(find)}` });
            return;
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
