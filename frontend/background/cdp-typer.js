/**
 * Drives real, browser-trusted mouse and keyboard input into a tab via
 * chrome.debugger (CDP Input domain).
 *
 * Why this exists: Appian's Save-button dirty-tracking (and, in the
 * live rule editor we tested against, CodeMirror 5's own document
 * model) only responds to real, browser-trusted input events.
 * CodeMirror's JS API (setValue/replaceRange), execCommand('insertText')
 * on the hidden textarea, and execCommand('paste') were all tried live
 * against a real Appian expression rule and none of them registered as
 * a real edit — confirmed by the Save button staying disabled and the
 * browser's own "unsaved changes" prompt never firing. Only literal
 * simulated keystrokes did. Mouse clicks need the same treatment for
 * Appian's Rule Inputs grid (adding a row, opening the type picker,
 * choosing a search result) — a plain `element.click()` call from a
 * content script is reachable, but we've been burned enough times in
 * this codebase by "reachable but not actually trusted" to just use
 * the same CDP mechanism uniformly rather than assume it's fine.
 */

const PROTOCOL_VERSION = "1.3";

const EXPRESSION_EDITOR_SELECTOR_JS =
  '(document.querySelector(".ExpressionEditorWidget---fit .CodeMirror") || document.querySelector(".CodeMirror"))';

const SPECIAL_KEYS = {
  "\n": { key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 },
  "\t": { key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 },
};

// CDP Input.dispatchKeyEvent modifiers bitmask: Alt=1, Ctrl=2, Meta=4, Shift=8.
const IS_MAC = /Mac/.test(navigator.platform || navigator.userAgent);
const SELECT_ALL_MODIFIER = IS_MAC ? 4 : 2;

function sendCommand(tabId, method, params = {}) {
  return chrome.debugger.sendCommand({ tabId }, method, params);
}

async function withDebugger(tabId, fn) {
  await chrome.debugger.attach({ tabId }, PROTOCOL_VERSION);
  try {
    return await fn();
  } finally {
    await chrome.debugger.detach({ tabId });
  }
}

/**
 * Toggles CodeMirror 5's autoCloseBrackets option via Runtime.evaluate.
 * Confirmed live: typing a full replacement string character-by-character
 * (as replaceAllText below does) triggers Appian's own auto-close-bracket
 * addon on every "(" we type, inserting a matching ")" — which then
 * collides with the ")" already present later in the text we're typing,
 * leaving an extra one behind. Disabling the option for the duration of
 * the simulated typing avoids it; it's restored afterward so the user's
 * own normal typing in Appian keeps auto-closing brackets as expected.
 */
async function setAutoCloseBrackets(tabId, enabled) {
  await sendCommand(tabId, "Runtime.evaluate", {
    expression: `(function() {
      var root = ${EXPRESSION_EDITOR_SELECTOR_JS};
      if (root && root.CodeMirror) root.CodeMirror.setOption("autoCloseBrackets", ${enabled});
      return true;
    })()`,
    returnByValue: true,
  });
}

/**
 * Dispatches a real select-all combo (Cmd+A on Mac, Ctrl+A elsewhere).
 * Used instead of an editor's own JS "select all" API because content
 * scripts can't reach page-created JS objects like a CodeMirror 5
 * instance — only real DOM/keyboard-level operations are reachable.
 * "rawKeyDown" (not "keyDown") is used because this is a shortcut
 * combo, not a character to insert.
 */
async function selectAll(tabId) {
  const params = { key: "a", code: "KeyA", windowsVirtualKeyCode: 65, modifiers: SELECT_ALL_MODIFIER };
  await sendCommand(tabId, "Input.dispatchKeyEvent", { type: "rawKeyDown", ...params });
  await sendCommand(tabId, "Input.dispatchKeyEvent", { type: "keyUp", ...params });
}

async function dispatchChar(tabId, char) {
  const special = SPECIAL_KEYS[char];
  if (special) {
    await sendCommand(tabId, "Input.dispatchKeyEvent", { type: "keyDown", ...special });
    await sendCommand(tabId, "Input.dispatchKeyEvent", { type: "keyUp", ...special });
    return;
  }

  await sendCommand(tabId, "Input.dispatchKeyEvent", {
    type: "keyDown",
    key: char,
    text: char,
    unmodifiedText: char,
  });
  await sendCommand(tabId, "Input.dispatchKeyEvent", { type: "keyUp", key: char });
}

async function dispatchClick(tabId, x, y) {
  await sendCommand(tabId, "Input.dispatchMouseEvent", { type: "mouseMoved", x, y });
  await sendCommand(tabId, "Input.dispatchMouseEvent", {
    type: "mousePressed",
    x,
    y,
    button: "left",
    clickCount: 1,
  });
  await sendCommand(tabId, "Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x,
    y,
    button: "left",
    clickCount: 1,
  });
}

/**
 * Attaches the debugger and presses Enter, then detaches. Used to
 * select the currently-highlighted result in an ARIA combobox (e.g.
 * Appian's rule input type picker) — confirmed live that Enter selects
 * the top search result the same way it would for a sighted user
 * tabbing through the list, without needing to know the dropdown's
 * exact DOM structure to click a specific item.
 *
 * Deliberately NOT implemented via dispatchChar("\n") — that path uses
 * "keyDown" because it's meant to insert a literal newline character
 * into text (needed when typing multi-line expressions). Here Enter is
 * a control/action key (select the highlighted option), not a
 * character to insert, so — matching the same reasoning as selectAll's
 * Cmd/Ctrl+A below — this uses "rawKeyDown".
 */
export async function pressEnter(tabId) {
  return withDebugger(tabId, async () => {
    const params = { key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 };
    await sendCommand(tabId, "Input.dispatchKeyEvent", { type: "rawKeyDown", ...params });
    await sendCommand(tabId, "Input.dispatchKeyEvent", { type: "keyUp", ...params });
  });
}

/**
 * Attaches the debugger once, types `text` with a small realistic
 * pause between characters into whatever element currently has focus,
 * waits, then presses Enter to select the top-highlighted result — all
 * within one continuous debugger session.
 *
 * Built specifically for Appian's rule-input Type search combobox.
 * Confirmed live: doing type-then-Enter as two *separate* debugger
 * sessions (type, detach, wait in the content script, reattach, Enter)
 * doesn't reliably select the result even with a generous wait, while
 * this — one unbroken session, back-to-back character delay instead of
 * zero-delay dispatch, matching how a real user actually interacts —
 * is the closest reproduction of the one interaction pattern confirmed
 * to work.
 */
export async function typeThenSelectWithEnter(tabId, text, { charDelayMs = 60, waitBeforeEnterMs = 2000 } = {}) {
  return withDebugger(tabId, async () => {
    for (const char of text) {
      await dispatchChar(tabId, char);
      await new Promise((r) => setTimeout(r, charDelayMs));
    }
    await new Promise((r) => setTimeout(r, waitBeforeEnterMs));
    const params = { key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 };
    await sendCommand(tabId, "Input.dispatchKeyEvent", { type: "rawKeyDown", ...params });
    await sendCommand(tabId, "Input.dispatchKeyEvent", { type: "keyUp", ...params });
  });
}

/**
 * Attaches the debugger, types `text` character-by-character into
 * whatever element currently has focus, then detaches. Caller is
 * responsible for focusing the target element before calling this.
 */
export async function typeText(tabId, text) {
  return withDebugger(tabId, async () => {
    for (const char of text) {
      await dispatchChar(tabId, char);
    }
  });
}

/**
 * Attaches the debugger, selects all content in whatever element
 * currently has focus (real Cmd/Ctrl+A), types `text` over that
 * selection character-by-character, then detaches. Caller is
 * responsible for focusing the target element before calling this.
 */
export async function replaceAllText(tabId, text) {
  return withDebugger(tabId, async () => {
    await setAutoCloseBrackets(tabId, false);
    try {
      await selectAll(tabId);
      for (const char of text) {
        await dispatchChar(tabId, char);
      }
    } finally {
      await setAutoCloseBrackets(tabId, true);
    }
  });
}

function selectRangeScript(fromLine, fromCh, toLine, toCh) {
  return `(function() {
    var root = ${EXPRESSION_EDITOR_SELECTOR_JS};
    if (!root || !root.CodeMirror) return false;
    var cm = root.CodeMirror;
    cm.focus();
    cm.setSelection({ line: ${fromLine}, ch: ${fromCh} }, { line: ${toLine}, ch: ${toCh} });
    cm.scrollIntoView({ line: ${fromLine}, ch: ${fromCh} }, 100);
    return true;
  })()`;
}

/**
 * Replaces one or more explicit {from, to} ranges (CodeMirror line/ch
 * positions, 0-indexed) with `text`, by selecting exactly that range in
 * the real editor and typing over it — rather than select-all + retype
 * the entire document, which is what replaceAllText above does.
 *
 * That whole-document retype turned out to be the actual cause of an
 * extra ")" showing up after a Find & Replace: disabling
 * autoCloseBrackets (see setAutoCloseBrackets) alone didn't fully fix
 * it — retyping every already-correct "(" in the surrounding,
 * *unchanged* text still gave Appian's bracket-closing behavior many
 * chances to fire, apparently not entirely gated by that one CodeMirror
 * option. Only ever typing the actual replacement text over a precise
 * selection — never touching the rest of the document — removes that
 * surface entirely rather than trying to suppress it.
 *
 * Ranges must be given in original-document coordinates and in
 * *descending* document order (bottom/right to top/left): replacing
 * later occurrences first means earlier ones' positions never shift
 * out from under us, so no re-reading/re-indexing is needed between
 * edits in the same call.
 */
export async function replaceRangesText(tabId, ranges, text) {
  return withDebugger(tabId, async () => {
    await setAutoCloseBrackets(tabId, false);
    try {
      for (const range of ranges) {
        const response = await sendCommand(tabId, "Runtime.evaluate", {
          expression: selectRangeScript(range.from.line, range.from.ch, range.to.line, range.to.ch),
          returnByValue: true,
        });
        if (!response.result?.value) {
          throw new Error("Could not select the target text in the editor");
        }
        for (const char of text) {
          await dispatchChar(tabId, char);
        }
      }
    } finally {
      await setAutoCloseBrackets(tabId, true);
    }
  });
}

/**
 * Attaches the debugger, real-clicks at viewport coordinates (x, y),
 * then detaches. Caller resolves the coordinates (e.g. from a DOM
 * element's getBoundingClientRect(), which is a plain DOM read and
 * reachable from a content script) — this module only knows about
 * pixels, not elements.
 */
export async function click(tabId, x, y) {
  return withDebugger(tabId, () => dispatchClick(tabId, x, y));
}

/**
 * Runs a fixed, hardcoded snippet in the tab's own main-world JS
 * context via CDP Runtime.evaluate. Unlike everything else in this
 * file, this isn't simulated input — it's direct script execution — but
 * it runs through the same chrome.debugger attachment, which (unlike a
 * content script) is NOT confined to the isolated world. This is
 * exactly where page-created objects like a CodeMirror 5 instance
 * actually live (see content/editor-bridge.js file header). Only ever
 * called with the hardcoded scripts below, never with caller-supplied
 * strings.
 */
async function evaluate(tabId, expression) {
  return withDebugger(tabId, async () => {
    const response = await sendCommand(tabId, "Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (response.exceptionDetails) {
      const desc = response.exceptionDetails.exception?.description || response.exceptionDetails.text;
      throw new Error(desc || "Evaluation failed in page context");
    }
    return response.result?.value;
  });
}

/**
 * Reads the expression editor's full logical text straight from its own
 * CodeMirror instance in the main world, instead of joining whatever
 * `.CodeMirror-line` elements are currently in the DOM. That DOM-only
 * approach (still used as a fallback in editor-bridge.js) silently
 * drops lines that are scrolled out of view — CodeMirror only mounts
 * lines near its viewport — confirmed live: an unmatched paren actually
 * on line 6 of a longer expression was reported as "line 1" because
 * only one line had made it into the DOM at read time.
 */
export async function getEditorValue(tabId) {
  return evaluate(
    tabId,
    `(function() {
      var root = ${EXPRESSION_EDITOR_SELECTOR_JS};
      if (root && root.CodeMirror) return root.CodeMirror.getValue();
      return null;
    })()`
  );
}

/**
 * Highlights a single 1-indexed line in the expression editor and
 * scrolls it into view, clearing any previously-highlighted line first.
 * Lets a diagnostic (e.g. "unmatched paren") be pointed at directly
 * instead of making the user count lines from a printed number.
 */
export async function highlightEditorLine(tabId, lineNumber) {
  return evaluate(
    tabId,
    `(function() {
      var root = ${EXPRESSION_EDITOR_SELECTOR_JS};
      if (!root || !root.CodeMirror) return false;
      var cm = root.CodeMirror;
      if (window.__appianAiHighlightedLine !== undefined) {
        cm.removeLineClass(window.__appianAiHighlightedLine, "background", "appian-ai-highlight-line");
      }
      if (!document.getElementById("appian-ai-highlight-style")) {
        var style = document.createElement("style");
        style.id = "appian-ai-highlight-style";
        style.textContent = ".appian-ai-highlight-line { background: rgba(255,196,0,0.35) !important; }";
        document.head.appendChild(style);
      }
      var lineIndex = ${lineNumber} - 1;
      cm.addLineClass(lineIndex, "background", "appian-ai-highlight-line");
      window.__appianAiHighlightedLine = lineIndex;
      cm.scrollIntoView({ line: lineIndex, ch: 0 }, 100);
      return true;
    })()`
  );
}

/** Clears any highlight added by highlightEditorLine, if one is active. */
export async function clearEditorHighlight(tabId) {
  return evaluate(
    tabId,
    `(function() {
      var root = ${EXPRESSION_EDITOR_SELECTOR_JS};
      if (root && root.CodeMirror && window.__appianAiHighlightedLine !== undefined) {
        root.CodeMirror.removeLineClass(window.__appianAiHighlightedLine, "background", "appian-ai-highlight-line");
        window.__appianAiHighlightedLine = undefined;
      }
      return true;
    })()`
  );
}
