/**
 * Reads and writes the SAIL expression editor's content.
 *
 * Appian's expression editor is CodeMirror. Two versions need different
 * handling, and — critically — everything here runs inside a content
 * script's "isolated world": it shares the live DOM with the page, but
 * NOT JavaScript object properties the page's own scripts attach to DOM
 * nodes. Confirmed by live testing: CM5 attaches its live editor
 * instance as `element.CodeMirror`, and that property is completely
 * invisible from here (`'CodeMirror' in element` is false), even though
 * the exact same check succeeds when run in the page's own main-world
 * console. So every read/write path below is pure-DOM or real-keystroke
 * based — nothing here may depend on reading a JS property the page set.
 *
 *  - CM5: read via `.CodeMirror-line` textContent (pure DOM). Write via
 *    real simulated keystrokes (see applyEditViaKeystrokes) — CM5's own
 *    JS API (setValue/replaceRange) is reachable from a plain page
 *    script (see applyEdit, used only by the standalone test harnesses,
 *    which run in the page's own world) but not from here, and separately
 *    doesn't register as a real edit to a host app's dirty-tracking
 *    (Appian's Save button) even when it is reachable.
 *  - CM6: read via `.cm-line` textContent (pure DOM). Write via simulated
 *    input (execCommand) so CM6's own input handlers pick it up like a
 *    real keystroke/paste.
 */

export function locateEditorRoot(root = document) {
  return root.querySelector(".CodeMirror") || root.querySelector(".cm-editor");
}

export function detectMode(editorRoot) {
  if (!editorRoot) return null;
  // DOM-only checks — see file header on why this can't check for the
  // `.CodeMirror` JS property.
  if (editorRoot.classList?.contains("CodeMirror")) return "cm5";
  if (editorRoot.classList?.contains("cm-editor") || editorRoot.querySelector(".cm-content")) {
    return "cm6";
  }
  return null;
}

// CodeMirror renders empty lines as a zero-width space placeholder
// (`<span cm-text="">​</span>`) — strip it so callers don't see
// phantom content.
function stripZeroWidthSpace(text) {
  return text.replace(/​/g, "");
}

export function readState(editorRoot) {
  const mode = detectMode(editorRoot);

  if (mode === "cm5") {
    const lines = Array.from(editorRoot.querySelectorAll(".CodeMirror-line"));
    const fullText = lines.length
      ? lines.map((l) => stripZeroWidthSpace(l.textContent)).join("\n")
      : "";
    return {
      mode,
      fullText,
      selectedText: "",
      // Not derivable from the DOM alone (CM5's real selection state
      // lives in the JS instance, which is invisible from here). Not
      // needed for MVP — callers should treat these as unavailable.
      selectionStart: null,
      selectionEnd: null,
    };
  }

  if (mode === "cm6") {
    const content = editorRoot.querySelector(".cm-content");
    const lines = Array.from(content.querySelectorAll(".cm-line"));
    const fullText = lines.length ? lines.map((l) => l.textContent).join("\n") : content.textContent;

    const selection = window.getSelection();
    const selectedText =
      selection && selection.rangeCount > 0 && content.contains(selection.anchorNode)
        ? selection.toString()
        : "";

    return {
      mode,
      fullText,
      selectedText,
      // CM6 offsets aren't derived from the browser Selection API reliably
      // (virtualized rendering, line wrapping). Not needed for MVP —
      // callers should treat these as unavailable in cm6 mode.
      selectionStart: null,
      selectionEnd: null,
    };
  }

  return null;
}

/**
 * Replaces the editor's content by simulating real keystrokes, via the
 * background service worker's chrome.debugger-based typer.
 *
 * Confirmed by live testing that this is necessary, not just belt-and-
 * suspenders: Appian's Save-button dirty-tracking never registered
 * edits made through applyEdit() below — only genuine simulated
 * keystrokes did. Only usable inside the real extension (requires
 * chrome.runtime and the "debugger" permission) — not in the standalone
 * test harnesses.
 *
 * Focuses the target element and lets the background worker send a real
 * select-all keystroke before typing, rather than calling the editor's
 * own JS API to select — see file header on why that's not reachable
 * from here for CM5.
 */
export async function applyEditViaKeystrokes(editorRoot, newText) {
  const mode = detectMode(editorRoot);

  if (mode === "cm5") {
    const textarea = editorRoot.querySelector("textarea");
    if (!textarea) return { success: false, error: "CM5 editor has no focusable textarea" };
    textarea.focus();
  } else if (mode === "cm6") {
    const content = editorRoot.querySelector(".cm-content");
    content.focus();
  } else {
    return { success: false, error: `Unrecognized editor mode for element: ${editorRoot?.className}` };
  }

  const response = await chrome.runtime.sendMessage({
    type: "APPLY_EDIT_VIA_KEYSTROKES",
    text: newText,
  });
  return response ?? { success: false, error: "No response from background script" };
}

/**
 * Clicks Appian's own Save control via a real trusted click (same
 * chrome.debugger path as applyEditViaKeystrokes) so it registers with
 * Appian's own save flow rather than being a no-op synthetic click.
 * Selector is best-effort — Appian doesn't expose a stable test id here,
 * so this matches on the keyboard-shortcut tooltip title, which has been
 * stable across the Expression Rule Designer and Interface Designer.
 */
export async function triggerSave(doc = document) {
  // Appian's Save button has no title/aria-label — confirmed live via
  // its actual outer HTML. The only stable, distinctive marker is the
  // visually-hidden keyboard-shortcut hint span it renders for screen
  // readers: <span class="Button---accessibilityhidden">Ctrl/Cmd + S</span>.
  const saveBtn = Array.from(doc.querySelectorAll("button.Button---btn")).find((btn) => {
    const hint = btn.querySelector(".Button---accessibilityhidden");
    return hint && /ctrl\/cmd\s*\+\s*s/i.test(hint.textContent || "");
  });

  if (!saveBtn) {
    return { success: false, error: "Could not find Appian's Save button on this page" };
  }
  if (saveBtn.disabled) {
    return { success: false, error: "Save button is disabled (no unsaved changes?)" };
  }

  const rect = saveBtn.getBoundingClientRect();
  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;

  const response = await chrome.runtime.sendMessage({ type: "CLICK_VIA_DEBUGGER", x, y });
  return response ?? { success: false, error: "No response from background script" };
}

/**
 * Reads the expression editor's full logical text via the background
 * worker's chrome.debugger Runtime.evaluate path (see cdp-typer.js
 * getEditorValue) rather than the pure-DOM join above, since the DOM
 * join drops lines CodeMirror hasn't mounted into the viewport. Callers
 * should fall back to readState()'s DOM join if this reports failure.
 */
export async function readExpressionValue() {
  const response = await chrome.runtime.sendMessage({ type: "GET_EDITOR_VALUE_VIA_DEBUGGER" });
  return response ?? { success: false, error: "No response from background script" };
}

export async function highlightLine(lineNumber) {
  const response = await chrome.runtime.sendMessage({ type: "HIGHLIGHT_EDITOR_LINE", line: lineNumber });
  return response ?? { success: false, error: "No response from background script" };
}

export async function clearHighlight() {
  const response = await chrome.runtime.sendMessage({ type: "CLEAR_EDITOR_HIGHLIGHT" });
  return response ?? { success: false, error: "No response from background script" };
}

/**
 * Replaces one or more explicit ranges (0-indexed {line, ch} pairs, in
 * descending document order — see cdp-typer.js replaceRangesText) with
 * `text`, by selecting exactly that range and typing over it, instead
 * of retyping the whole document like applyEditViaKeystrokes does. Used
 * by the Find & Replace tool so unrelated, already-correct parentheses
 * elsewhere in the expression are never retyped and can't spuriously
 * trigger Appian's auto-close-bracket behavior.
 */
export async function applyRangeEditViaKeystrokes(ranges, text) {
  const response = await chrome.runtime.sendMessage({
    type: "APPLY_RANGE_EDIT_VIA_KEYSTROKES",
    ranges,
    text,
  });
  return response ?? { success: false, error: "No response from background script" };
}

/**
 * Direct-API write, used only by the standalone test harnesses
 * (frontend/test/*.html), which run in the page's own main world where
 * `element.CodeMirror` is genuinely reachable. Not usable from the real
 * content script — see file header.
 */
export async function applyEdit(editorRoot, newText) {
  const mode = detectMode(editorRoot);

  if (mode === "cm5") {
    editorRoot.CodeMirror.setValue(newText);
    return true;
  }

  if (mode === "cm6") {
    const content = editorRoot.querySelector(".cm-content");
    content.focus();
    document.execCommand("selectAll", false, null);
    const ok = document.execCommand("insertText", false, newText);
    // execCommand mutates the contenteditable DOM synchronously, but CM6
    // reconciles its own state from that mutation via its internal
    // MutationObserver, which flushes on the next animation frame — not
    // synchronously. Reading view.state right after this call returns
    // without waiting would see the pre-edit value.
    await new Promise((resolve) => requestAnimationFrame(resolve));
    return ok;
  }

  return false;
}
