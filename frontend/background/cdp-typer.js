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
 *
 * Confirmed live that this extends even to a *real*, CDP-dispatched
 * Cmd/Ctrl+V (trusted, not execCommand('paste')): still didn't register
 * with Appian's dirty-tracking. So large writes have to go through
 * character-by-character typing (replaceAllText) — there's no faster
 * paste-based shortcut available here.
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
 * A CDP command resolving just means the browser process accepted and
 * dispatched the input event — not that the renderer has finished
 * processing it into CodeMirror's document model. Callers that read the
 * editor's value back (readExpressionValue) right after a typing
 * operation completes can otherwise catch it mid-flight and see stale,
 * pre-edit text. Used once at the end of each exported typing function
 * below, not per-character or per-edit, so it adds one short pause per
 * operation rather than compounding across a batch.
 */
function settle() {
  return new Promise((resolve) => setTimeout(resolve, 150));
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
 * Toggles CodeMirror 5's Enter handling via its extraKeys option.
 * Confirmed live: simulating a literal Enter keystroke doesn't just
 * insert "\n" — CodeMirror's default keymap binds Enter to its own
 * "newlineAndIndent" command, which inserts a newline PLUS whatever
 * indentation it guesses is correct for that point. Since the text
 * we're typing already contains its own correct leading whitespace for
 * every line, that auto-indent stacks on top of it, leaving extra tabs
 * before each line. Setting extraKeys: { Enter: false } tells
 * CodeMirror's keymap system to explicitly not handle Enter at all,
 * which lets it fall through to the underlying textarea's native
 * behavior — a plain, un-indented newline — for the duration of the
 * simulated typing. Restored afterward so the user's own typing in
 * Appian keeps its normal auto-indent.
 */
async function setEnterAutoIndent(tabId, enabled) {
  await sendCommand(tabId, "Runtime.evaluate", {
    expression: `(function() {
      var root = ${EXPRESSION_EDITOR_SELECTOR_JS};
      if (!root || !root.CodeMirror) return true;
      var cm = root.CodeMirror;
      if (${enabled}) {
        if (window.__appianAiOrigExtraKeys !== undefined) {
          cm.setOption("extraKeys", window.__appianAiOrigExtraKeys);
          window.__appianAiOrigExtraKeys = undefined;
        }
      } else {
        if (window.__appianAiOrigExtraKeys === undefined) {
          window.__appianAiOrigExtraKeys = cm.getOption("extraKeys") || {};
        }
        var keys = {};
        for (var k in window.__appianAiOrigExtraKeys) keys[k] = window.__appianAiOrigExtraKeys[k];
        keys.Enter = false;
        cm.setOption("extraKeys", keys);
      }
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

/**
 * Dispatches one character's keyDown+keyUp. The two are fired together
 * (not awaiting keyDown's ack before sending keyUp) rather than fully
 * sequential — a small, safe speedup, since both events belong to the
 * same character and their relative order to each other is preserved
 * by chrome.debugger's ordered connection regardless of whether we wait
 * in between. Callers still await this whole function, one character at
 * a time, before moving to the next.
 *
 * A prior version of this file tried removing ALL waiting — firing
 * every character's events for an entire string in one burst before
 * awaiting anything. That's the wrong tradeoff: confirmed live it
 * caused newlines to get dropped or coalesced in longer expressions
 * (everything landing on one line), almost certainly because the
 * renderer couldn't reliably keep up with Enter's actual line-break
 * DOM mutation while a flood of subsequent characters' events were
 * already in flight targeting positions that didn't exist yet. Waiting
 * for one full character (both its events) before starting the next
 * keeps every structural change — especially newlines — fully
 * committed before anything after it is dispatched.
 */
async function dispatchChar(tabId, char) {
  const special = SPECIAL_KEYS[char];
  const down = special ? { type: "keyDown", ...special } : { type: "keyDown", key: char, text: char, unmodifiedText: char };
  const up = special ? { type: "keyUp", ...special } : { type: "keyUp", key: char };
  await Promise.all([
    sendCommand(tabId, "Input.dispatchKeyEvent", down),
    sendCommand(tabId, "Input.dispatchKeyEvent", up),
  ]);
}

/**
 * Fires an entire line's worth of character events in one burst,
 * awaiting them all together — safe to pipeline because none of them
 * are structural: unlike Enter, plain characters don't create new DOM
 * nodes for CodeMirror to render, so there's nothing for a flood of
 * them to outrun.
 */
async function dispatchLineFast(tabId, lineText) {
  const pending = [];
  for (const char of lineText) {
    const special = SPECIAL_KEYS[char];
    const down = special ? { type: "keyDown", ...special } : { type: "keyDown", key: char, text: char, unmodifiedText: char };
    const up = special ? { type: "keyUp", ...special } : { type: "keyUp", key: char };
    pending.push(sendCommand(tabId, "Input.dispatchKeyEvent", down));
    pending.push(sendCommand(tabId, "Input.dispatchKeyEvent", up));
  }
  await Promise.all(pending);
}

/**
 * Types `text`, pipelining each line's plain characters together (fast)
 * but dispatching every newline on its own, fully awaited, before
 * moving on to the next line — the newline is the one character that
 * triggers a structural DOM change (a new rendered line), which is
 * exactly what broke when the whole string was pipelined without any
 * serialization at all (see dispatchChar's header). This keeps that one
 * risk contained to just the Enter keystrokes while still getting most
 * of the speed benefit back for everything else.
 *
 * Leading whitespace is stripped from every line before typing — by
 * design, not a bug: indentation isn't something this extension tries
 * to get right, since Appian has its own auto-format button for that.
 * A newline just starts a new line, with nothing in front of it;
 * combined with setEnterAutoIndent suppressing CodeMirror's own
 * indent-on-Enter, the typed result never has any indentation at all.
 */
async function dispatchText(tabId, text) {
  const lines = text.split("\n").map((line) => line.replace(/^[ \t]+/, ""));
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].length > 0) await dispatchLineFast(tabId, lines[i]);
    if (i < lines.length - 1) await dispatchChar(tabId, "\n");
  }
}

/**
 * Dispatches a real Backspace keystroke — used to delete an active
 * selection as its own committed edit, rather than relying on the first
 * character of a subsequent type-over to replace it (see replaceAllText's
 * header for why that distinction matters).
 */
async function deleteSelection(tabId) {
  const params = { key: "Backspace", code: "Backspace", windowsVirtualKeyCode: 8 };
  await sendCommand(tabId, "Input.dispatchKeyEvent", { type: "rawKeyDown", ...params });
  await sendCommand(tabId, "Input.dispatchKeyEvent", { type: "keyUp", ...params });
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
 * currently has focus (real Cmd/Ctrl+A), deletes it with a real
 * Backspace, then types `text` into the now-empty document
 * character-by-character, then detaches. Caller is responsible for
 * focusing the target element before calling this.
 *
 * The delete is its own explicit keystroke rather than letting the first
 * typed character replace the selection — confirmed live (see the same
 * finding documented on replaceRangesText below) that typing directly
 * over an active selection gives Appian's bracket-closing behavior a
 * chance to fire on that first character in a way that isn't fully
 * gated by the autoCloseBrackets option, producing a stray extra ")" on
 * effectively every whole-document replace. Deleting first, as its own
 * committed edit, means every subsequent character — including the
 * first "(" of the new text — is typed into a clean position rather
 * than over a selection.
 */
export async function replaceAllText(tabId, text) {
  return withDebugger(tabId, async () => {
    await setAutoCloseBrackets(tabId, false);
    await setEnterAutoIndent(tabId, false);
    try {
      await selectAll(tabId);
      await deleteSelection(tabId);
      await dispatchText(tabId, text);
      await settle();
    } finally {
      await setEnterAutoIndent(tabId, true);
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
async function applyOneRangeEdit(tabId, range, text) {
  const response = await sendCommand(tabId, "Runtime.evaluate", {
    expression: selectRangeScript(range.from.line, range.from.ch, range.to.line, range.to.ch),
    returnByValue: true,
  });
  if (!response.result?.value) {
    throw new Error("Could not select the target text in the editor");
  }
  if (text.length === 0) {
    // A selection alone doesn't delete anything — a real Backspace
    // does, consistent with this file only ever mutating the document
    // via genuine keystrokes rather than a JS API call.
    await deleteSelection(tabId);
  } else {
    await dispatchText(tabId, text);
  }
}

export async function replaceRangesText(tabId, ranges, text) {
  return withDebugger(tabId, async () => {
    await setAutoCloseBrackets(tabId, false);
    await setEnterAutoIndent(tabId, false);
    try {
      for (const range of ranges) {
        await applyOneRangeEdit(tabId, range, text);
      }
      await settle();
    } finally {
      await setEnterAutoIndent(tabId, true);
      await setAutoCloseBrackets(tabId, true);
    }
  });
}

/**
 * Like replaceRangesText, but each range carries its own replacement
 * text instead of all sharing one — used by the parenthesis auto-repair
 * (see panel.js computeBracketRepairPlan), which mixes deletions (extra
 * closers) and insertions (missing closers) of different characters in
 * a single pass. Ranges must still be given in descending document
 * order for the same reason as replaceRangesText.
 */
export async function applyMixedRangeEdits(tabId, edits) {
  return withDebugger(tabId, async () => {
    await setAutoCloseBrackets(tabId, false);
    await setEnterAutoIndent(tabId, false);
    try {
      for (const edit of edits) {
        await applyOneRangeEdit(tabId, edit, edit.text);
      }
      await settle();
    } finally {
      await setEnterAutoIndent(tabId, true);
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
