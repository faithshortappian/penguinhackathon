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
