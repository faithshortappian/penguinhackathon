/**
 * Reads and writes Appian's Rule Inputs grid (the panel on the right of
 * the expression rule designer).
 *
 * Same isolated-world constraint as editor-bridge.js: no reading
 * page-created JS properties, real DOM/keyboard/mouse events only for
 * writes. Rule input rows are plain <input>/<button> elements (no
 * CodeMirror-style custom editor), so click+type via the
 * chrome.debugger-backed primitives is sufficient — no read/write
 * asymmetry like CM5's textarea hack here.
 *
 * Rule input objects on the wire (both what we send and what we
 * receive) are { name, description, type, array }.
 *
 * Product decision after repeated live failures: automating the Type
 * combobox (async search + select) and the Array checkbox both proved
 * unreliable enough in practice (despite each being individually
 * confirmed to work in isolated tests) that neither is worth continuing
 * to automate. Only the Name field is written automatically now —
 * Type and Array are left for the user to set by hand in Appian, using
 * the always-visible grid in the panel as their reference. See
 * setRuleInputArray/editRuleInputType below — kept as working, callable
 * primitives (still real, still functional) in case they're useful
 * again later, but the main add/edit flow no longer calls them.
 *
 * Verified live: adding a new rule input's Name registers as a real
 * edit (Save enables, Appian's own Test Inputs panel picks it up).
 *
 * NOT yet verified: editing an existing (already-saved) row's name —
 * built the same way as the add flow, but not yet tested against a
 * rule that already has inputs.
 */

function addLink(doc = document) {
  return doc.querySelector('[aria-label*="New Rule Input"]');
}

function rows(doc = document) {
  return Array.from(doc.querySelectorAll(".EditableGridLayout---table tbody tr"));
}

function readDescription(descCell) {
  if (!descCell) return "";
  const addLinkEl = descCell.querySelector("a");
  if (addLinkEl && addLinkEl.textContent.trim() === "Add") return ""; // empty-state placeholder link
  return descCell.textContent?.trim() ?? "";
}

export function readRuleInputs(doc = document) {
  return rows(doc).map((row) => {
    const cells = row.querySelectorAll("td");
    const nameInput = cells[0]?.querySelector("input");
    const typeChip = cells[2]?.querySelector(".PickerTokenWidget---label");
    const arrayCheckbox = cells[3]?.querySelector('input[type="checkbox"]');
    return {
      name: nameInput?.value?.trim() ?? "",
      description: readDescription(cells[1]),
      type: typeChip?.textContent?.trim() ?? "",
      array: !!arrayCheckbox?.checked,
    };
  });
}

async function clickElement(el) {
  const rect = el.getBoundingClientRect();
  const x = Math.round(rect.left + rect.width / 2);
  const y = Math.round(rect.top + rect.height / 2);
  const response = await chrome.runtime.sendMessage({ type: "CLICK_VIA_DEBUGGER", x, y });
  return response ?? { success: false, error: "No response from background script" };
}

async function typeIntoFocusedField(text) {
  const response = await chrome.runtime.sendMessage({ type: "TYPE_TEXT_VIA_KEYSTROKES", text });
  return response ?? { success: false, error: "No response from background script" };
}

async function replaceFocusedFieldText(text) {
  const response = await chrome.runtime.sendMessage({ type: "APPLY_EDIT_VIA_KEYSTROKES", text });
  return response ?? { success: false, error: "No response from background script" };
}

function waitFor(predicate, { timeoutMs = 5000, intervalMs = 150 } = {}) {
  return new Promise((resolve, reject) => {
    const start = Date.now();
    const tick = () => {
      const result = predicate();
      if (result) return resolve(result);
      if (Date.now() - start > timeoutMs) return reject(new Error("timed out"));
      setTimeout(tick, intervalMs);
    };
    tick();
  });
}

/**
 * Adds a new rule input row and types its name. Does not touch Type or
 * Array — see file header.
 */
export async function addRuleInput(name) {
  const add = addLink();
  if (!add) return { success: false, error: 'Could not find the "New Rule Input" control' };

  const rowCountBefore = rows().length;
  const clicked = await clickElement(add);
  if (!clicked.success) return clicked;

  let newRows;
  try {
    newRows = await waitFor(() => {
      const current = rows();
      return current.length > rowCountBefore ? current : null;
    });
  } catch {
    return { success: false, error: "New rule input row did not appear" };
  }

  const row = newRows[newRows.length - 1];
  if (!row) return { success: false, error: "New rule input row did not appear" };

  const nameInput = row.querySelector("td:first-child input");
  if (!nameInput) return { success: false, error: "New row has no name field" };
  nameInput.focus();
  return typeIntoFocusedField(name);
}

/**
 * Edits an existing rule input row's name. UNVERIFIED — see file header.
 */
export async function editRuleInputName(rowIndex, newName) {
  const row = rows()[rowIndex];
  if (!row) return { success: false, error: `No rule input row at index ${rowIndex}` };
  const nameInput = row.querySelector("td:first-child input");
  if (!nameInput) return { success: false, error: "Row has no name field" };
  nameInput.focus();
  return replaceFocusedFieldText(newName);
}

/**
 * Clicks a rule input row's Array checkbox to match `arrayValue`, if it
 * isn't already in that state. Kept as a working primitive — not
 * currently called by the main add/edit flow. See file header.
 */
export async function setRuleInputArray(rowIndex, arrayValue) {
  const row = rows()[rowIndex];
  if (!row) return { success: false, error: `No rule input row at index ${rowIndex}` };
  const checkbox = row.querySelectorAll("td")[3]?.querySelector('input[type="checkbox"]');
  if (!checkbox) return { success: false, error: "Row has no array checkbox" };
  if (checkbox.checked === !!arrayValue) return { success: true };
  return clickElement(checkbox);
}

/**
 * Types a type-name query into an existing row's Type field and stops
 * — does not attempt to select a result. Kept as a working primitive —
 * not currently called by the main add/edit flow. See file header.
 */
export async function editRuleInputType(rowIndex, newTypeName) {
  const row = rows()[rowIndex];
  if (!row) return { success: false, error: `No rule input row at index ${rowIndex}` };
  const typeCell = row.querySelectorAll("td")[2];

  const removeChip = typeCell?.querySelector(".PickerTokenWidget---chip button, .PickerTokenWidget---chip .close");
  if (removeChip) {
    const result = await clickElement(removeChip);
    if (!result.success) return result;
    try {
      await waitFor(() => typeCell.querySelector("input"));
    } catch {
      return { success: false, error: "Type search field did not appear after removing the existing type" };
    }
  }

  const typeField = typeCell?.querySelector("input");
  if (!typeField) return { success: false, error: "Row has no type search field" };
  typeField.focus();
  return typeIntoFocusedField(newTypeName);
}
