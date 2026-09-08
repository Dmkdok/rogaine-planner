// Main controller: state, DOM wiring, all event handling. Talks to the backend only through
// api.js and draws only through view.js's MapView -- control markers live here as real DOM
// buttons (not canvas pixels) so they get native focus/ARIA/keyboard support (see view.js's
// module comment for why).

import * as api from "./api.js";
import { MapView } from "./view.js";

// -----------------------------------------------------------------------------------------
// DOM references
// -----------------------------------------------------------------------------------------

const els = {
  statusMessage: document.getElementById("status-message"),
  errorMessage: document.getElementById("error-message"),
  runIdDisplay: document.getElementById("run-id-display"),
  runIdValue: document.getElementById("run-id-value"),

  uploadForm: document.getElementById("upload-form"),
  mapFileInput: document.getElementById("map-file-input"),
  uploadBtn: document.getElementById("upload-btn"),

  scaleForm: document.getElementById("scale-form"),
  scaleFieldset: document.getElementById("scale-fieldset"),
  scaleModeRatio: document.getElementById("scale-mode-ratio"),
  scaleModeCalibrate: document.getElementById("scale-mode-calibrate"),
  scaleModeAuto: document.getElementById("scale-mode-auto"),
  scaleRatioPanel: document.getElementById("scale-ratio-panel"),
  scaleCalibratePanel: document.getElementById("scale-calibrate-panel"),
  scaleDenominator: document.getElementById("scale-denominator"),
  scaleDpi: document.getElementById("scale-dpi"),
  calibStartBtn: document.getElementById("calib-start-btn"),
  calibX1: document.getElementById("calib-x1"),
  calibY1: document.getElementById("calib-y1"),
  calibX2: document.getElementById("calib-x2"),
  calibY2: document.getElementById("calib-y2"),
  calibMeters: document.getElementById("calib-meters"),
  calibDpi: document.getElementById("calib-dpi"),
  scalePage: document.getElementById("scale-page"),
  applyScaleBtn: document.getElementById("apply-scale-btn"),

  mapToolbar: document.getElementById("map-toolbar"),
  zoomInBtn: document.getElementById("zoom-in-btn"),
  zoomOutBtn: document.getElementById("zoom-out-btn"),
  zoomResetBtn: document.getElementById("zoom-reset-btn"),
  toggleAddModeBtn: document.getElementById("toggle-add-mode-btn"),
  detectBtn: document.getElementById("detect-btn"),

  mapViewport: document.getElementById("map-viewport"),
  mapCanvas: document.getElementById("map-canvas"),
  calibrationOverlay: document.getElementById("calibration-overlay"),
  markersLayer: document.getElementById("markers-layer"),
  mapPreviewNote: document.getElementById("map-preview-note"),
  hubWarning: document.getElementById("hub-warning"),

  addControlBtn: document.getElementById("add-control-btn"),
  controlsTbody: document.getElementById("controls-tbody"),

  runForm: document.getElementById("run-form"),
  paramSpeedKmh: document.getElementById("param-speed-kmh"),
  paramTimeLimitMin: document.getElementById("param-time-limit-min"),
  paramPenalty: document.getElementById("param-penalty"),
  runBtn: document.getElementById("run-btn"),

  routeResults: document.getElementById("route-results"),
  routeTotalTime: document.getElementById("route-total-time"),
  routeTotalDistance: document.getElementById("route-total-distance"),
  routePoints: document.getElementById("route-points"),
  routePenalty: document.getElementById("route-penalty"),
  routeScore: document.getElementById("route-score"),
  routeSolver: document.getElementById("route-solver"),
  legsTbody: document.getElementById("legs-tbody"),

  exportJsonLink: document.getElementById("export-json-link"),
  exportPngLink: document.getElementById("export-png-link"),
  exportCsvLink: document.getElementById("export-csv-link"),
};

// -----------------------------------------------------------------------------------------
// State
// -----------------------------------------------------------------------------------------

const state = {
  runId: null,
  segment: null, // {width, height, meters_per_pixel, dpi} once segment succeeds
  controls: [], // Control[] -- the client's working copy, PUT to the server on every commit
  route: null, // Route once plan succeeds
  visitOrder: new Map(), // control id -> 1-based visiting order, derived from `route`
  mode: "idle", // "idle" | "add" | "calibrate" -- what a canvas click currently does
  selectedControlId: null, // id of the control whose marker/row are cross-highlighted, or null
  calibration: [], // up to two {x, y} map-pixel points for the calibration line
  mapImage: null, // HTMLImageElement | null -- the raw uploaded map, for canvas background
  detectAttempted: false, // gates the "no hub" warning until a detect result actually exists
  controlsArtifactReady: false, // controls.csv exists server-side (detect ran, or a PUT landed)
  routeArtifactReady: false, // route.json/route.png exist server-side (plan succeeded)
};

const view = new MapView(els.mapViewport, els.mapCanvas);

// -----------------------------------------------------------------------------------------
// Small helpers
// -----------------------------------------------------------------------------------------

function setStatus(text) {
  els.statusMessage.textContent = text;
}

function clearError() {
  els.errorMessage.hidden = true;
  els.errorMessage.textContent = "";
}

function setError(text) {
  els.errorMessage.textContent = text;
  els.errorMessage.hidden = false;
}

function describeError(err, fallback) {
  return (err && err.message) || fallback;
}

function clamp(value, lo, hi) {
  return Math.min(hi, Math.max(lo, value));
}

function round1(value) {
  return Math.round(value * 10) / 10;
}

function findControl(id) {
  return state.controls.find((c) => c.id === id);
}

function controlLabel(id) {
  const c = findControl(id);
  if (!c) return `#${id}`;
  if (c.is_hub) return "Хаб";
  return c.number != null ? String(c.number) : `#${id}`;
}

function formatDuration(totalSeconds) {
  const s = Math.round(totalSeconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${m}:${ss}`;
}

function formatMeters(meters) {
  return meters >= 1000 ? `${(meters / 1000).toFixed(2)} км` : `${Math.round(meters)} м`;
}

function jobStatusLabel(status) {
  return status === "running" ? "выполняется" : "в очереди";
}

/** Runs `fn` (a DOM rebuild), then restores focus to the element that had it by id -- a full
 * rebuild of the controls table/marker layer would otherwise silently drop keyboard focus to
 * <body> on every edit, which fails the "visible focus" requirement for anyone tabbing through.
 */
function withFocusPreserved(fn) {
  const activeId = document.activeElement && document.activeElement.id;
  fn();
  if (activeId) {
    const el = document.getElementById(activeId);
    if (el) el.focus({ preventScroll: true });
  }
}

// -----------------------------------------------------------------------------------------
// View (pan/zoom/redraw) -- markers are positioned here too since their screen position is a
// function of the same pan/zoom transform the canvas uses.
// -----------------------------------------------------------------------------------------

function getMarkerEl(id) {
  return document.getElementById(`marker-${id}`);
}

function positionMarkerElement(el, control) {
  const { x, y } = view.mapToScreen(control.x, control.y);
  el.style.left = `${x}px`;
  el.style.top = `${y}px`;
}

function repositionAllMarkers() {
  for (const control of state.controls) {
    const el = getMarkerEl(control.id);
    if (el) positionMarkerElement(el, control);
  }
}

function renderCalibrationOverlay() {
  const svg = els.calibrationOverlay;
  svg.innerHTML = "";
  const pts = state.calibration.map((p) => view.mapToScreen(p.x, p.y));
  if (pts.length === 2) {
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", String(pts[0].x));
    line.setAttribute("y1", String(pts[0].y));
    line.setAttribute("x2", String(pts[1].x));
    line.setAttribute("y2", String(pts[1].y));
    line.setAttribute("class", "calib-line");
    svg.appendChild(line);
  }
  for (const p of pts) {
    const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    c.setAttribute("cx", String(p.x));
    c.setAttribute("cy", String(p.y));
    c.setAttribute("r", "5");
    c.setAttribute("class", "calib-point");
    svg.appendChild(c);
  }
}

/** Cheap path for a pure view-transform change (pan/zoom/resize/fit): redraw the canvas and
 * reposition existing marker/calibration elements in place -- no DOM rebuild, so focus/drag
 * state is untouched. */
function redraw() {
  view.render();
  repositionAllMarkers();
  renderCalibrationOverlay();
}

function setMode(mode) {
  state.mode = mode;
  els.mapViewport.classList.toggle("mode-add", mode === "add");
  els.mapViewport.classList.toggle("mode-calibrate", mode === "calibrate");
  els.toggleAddModeBtn.setAttribute("aria-pressed", String(mode === "add"));
  els.calibStartBtn.setAttribute("aria-pressed", String(mode === "calibrate"));
}

// -----------------------------------------------------------------------------------------
// Controls: persistence
// -----------------------------------------------------------------------------------------

let saveDebounceTimer = null;
let saveInFlight = false;
let saveAgainNeeded = false;

function scheduleSaveControls(delay = 500) {
  clearTimeout(saveDebounceTimer);
  saveDebounceTimer = setTimeout(saveControlsNow, delay);
}

/** PUTs the full current `state.controls` (SPEC F9's CSV round trip, via the JSON endpoint).
 * On a 400 (e.g. no hub, duplicate ids) the user's edit is deliberately left in place -- only
 * the error is surfaced -- so nothing is ever silently discarded (per T061's brief).
 */
async function saveControlsNow() {
  clearTimeout(saveDebounceTimer);
  if (!state.runId) return;
  if (saveInFlight) {
    saveAgainNeeded = true;
    return;
  }
  saveInFlight = true;
  try {
    const validated = await api.putControls(state.runId, state.controls);
    // Merge onto the *same* objects (by id) instead of replacing state.controls outright: a
    // field edited on this control while the PUT above was in flight lives on these objects, and
    // any already-rendered table row's onCommit closure still points at them -- swapping in fresh
    // objects from the response would silently discard that edit on the next re-render (the bug:
    // typing a number then tabbing straight into points loses the points edit once the number
    // save's response lands).
    for (const v of validated) {
      const existing = state.controls.find((c) => c.id === v.id);
      if (existing) Object.assign(existing, v);
    }
    state.controls.sort((a, b) => Number(b.is_hub) - Number(a.is_hub) || a.id - b.id);
    state.controlsArtifactReady = true;
    clearError();
    repositionAllMarkers();
  } catch (err) {
    setError(describeError(err, "Не удалось сохранить контроли"));
  } finally {
    saveInFlight = false;
    if (saveAgainNeeded) {
      saveAgainNeeded = false;
      saveControlsNow();
    }
  }
}

function computeVisitOrder() {
  state.visitOrder = new Map();
  if (!state.route) return;
  state.route.order.slice(1, -1).forEach((id, i) => state.visitOrder.set(id, i + 1));
}

/** Full rebuild: marker layer + controls table, for any change that affects what they show
 * (add/delete, number/points/hub edits, a new detect/plan result). Position-only changes
 * (drag/keyboard-nudge) use the cheaper `redraw()`/`repositionAllMarkers()` path instead. */
function refreshControlsUI() {
  withFocusPreserved(() => {
    computeVisitOrder();
    renderMarkers();
    renderControlsTable();
  });
  updateHubWarning();
  updateAvailability();
}

function updateHubWarning() {
  const hasHub = state.controls.some((c) => c.is_hub);
  els.hubWarning.hidden = !(state.detectAttempted && !hasHub);
}

function updateAvailability() {
  const segmentReady = Boolean(state.segment);
  els.addControlBtn.disabled = !segmentReady;
  els.toggleAddModeBtn.disabled = !segmentReady;
  els.detectBtn.disabled = !segmentReady;
  const canRun = segmentReady && state.controls.some((c) => c.is_hub);
  els.runBtn.disabled = !canRun;
  updateExportLinks();
}

function setLinkEnabled(a, enabled, href, downloadName) {
  if (enabled && state.runId) {
    a.href = href;
    a.setAttribute("download", downloadName);
    a.removeAttribute("aria-disabled");
    a.removeAttribute("tabindex");
  } else {
    a.removeAttribute("href");
    a.setAttribute("aria-disabled", "true");
    a.setAttribute("tabindex", "-1");
  }
}

function updateExportLinks() {
  setLinkEnabled(
    els.exportCsvLink,
    state.controlsArtifactReady,
    api.exportUrl(state.runId, "controls.csv"),
    "controls.csv"
  );
  setLinkEnabled(
    els.exportJsonLink,
    state.routeArtifactReady,
    api.exportUrl(state.runId, "route.json"),
    "route.json"
  );
  setLinkEnabled(
    els.exportPngLink,
    state.routeArtifactReady,
    api.exportUrl(state.runId, "route.png"),
    "route.png"
  );
}

// -----------------------------------------------------------------------------------------
// Controls: markers (DOM overlay)
// -----------------------------------------------------------------------------------------

function describeControlForA11y(control) {
  const parts = [
    control.is_hub ? "Хаб, старт и финиш" : `Контроль ${control.number ?? "без номера"}`,
  ];
  if (!control.is_hub) parts.push(`${control.points ?? 0} очков`);
  const order = state.visitOrder.get(control.id);
  if (order != null) parts.push(`остановка №${order} по маршруту`);
  return parts.join(", ");
}

/** ADR-021: cross-highlight sync -- selecting a marker highlights its table row and vice versa.
 * Both directions call this same `selectControl`, which only ever toggles a class/ARIA attribute
 * on the (at most two) affected elements -- no table/marker rebuild, so it's safe to call from
 * hot paths like pointerdown/focus without disturbing drag state or input focus. */
function updateSelectionHighlight(prevId, nextId) {
  for (const id of [prevId, nextId]) {
    if (id == null) continue;
    const isSelected = id === nextId;
    const marker = getMarkerEl(id);
    if (marker) {
      marker.classList.toggle("marker--selected", isSelected);
      if (isSelected) marker.setAttribute("aria-current", "true");
      else marker.removeAttribute("aria-current");
    }
    const row = document.getElementById(`control-row-${id}`);
    if (row) {
      row.classList.toggle("row-selected", isSelected);
      if (isSelected) row.setAttribute("aria-selected", "true");
      else row.removeAttribute("aria-selected");
    }
  }
}

function selectControl(id) {
  if (state.selectedControlId === id) return;
  const prev = state.selectedControlId;
  state.selectedControlId = id;
  updateSelectionHighlight(prev, id);
}

function onMarkerPointerDown(e, controlId) {
  if (e.button !== 0) return;
  selectControl(controlId);
  e.preventDefault();
  const btn = e.currentTarget;
  btn.setPointerCapture(e.pointerId);
  const rect = els.mapViewport.getBoundingClientRect();

  function onMove(ev) {
    if (ev.pointerId !== e.pointerId) return;
    const control = findControl(controlId);
    if (!control) return;
    const { x, y } = view.screenToMap(ev.clientX - rect.left, ev.clientY - rect.top);
    control.x = clamp(x, 0, view.mapWidth || x);
    control.y = clamp(y, 0, view.mapHeight || y);
    positionMarkerElement(btn, control);
    updateTableRowXY(controlId, control.x, control.y);
  }
  function onUp(ev) {
    if (ev.pointerId !== e.pointerId) return;
    btn.removeEventListener("pointermove", onMove);
    btn.removeEventListener("pointerup", onUp);
    saveControlsNow();
  }
  btn.addEventListener("pointermove", onMove);
  btn.addEventListener("pointerup", onUp);
}

function onMarkerKeyDown(e, controlId) {
  const step = e.shiftKey ? 10 : 1;
  let dx = 0;
  let dy = 0;
  if (e.key === "ArrowUp") dy = -step;
  else if (e.key === "ArrowDown") dy = step;
  else if (e.key === "ArrowLeft") dx = -step;
  else if (e.key === "ArrowRight") dx = step;
  else if (e.key === "Delete") {
    e.preventDefault();
    deleteControl(controlId);
    return;
  } else if (e.key === "Enter") {
    e.preventDefault();
    const input = document.getElementById(`control-${controlId}-number`);
    if (input) {
      input.focus();
      input.select();
    }
    return;
  } else {
    return;
  }
  e.preventDefault();
  e.stopPropagation(); // don't let the viewport's own arrow-key panning also fire
  const control = findControl(controlId);
  if (!control) return;
  control.x = clamp(control.x + dx, 0, view.mapWidth || control.x + dx);
  control.y = clamp(control.y + dy, 0, view.mapHeight || control.y + dy);
  positionMarkerElement(e.currentTarget, control);
  updateTableRowXY(controlId, control.x, control.y);
  scheduleSaveControls();
}

function createMarkerElement(control) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "marker" + (control.is_hub ? " marker--hub" : "");
  btn.id = `marker-${control.id}`;
  btn.dataset.controlId = String(control.id);

  const label = document.createElement("span");
  label.className = "marker-label";
  label.textContent = control.is_hub ? "H" : control.number != null ? String(control.number) : "?";
  btn.appendChild(label);

  const order = state.visitOrder.get(control.id);
  if (order != null) {
    const badge = document.createElement("span");
    badge.className = "marker-order-badge";
    badge.textContent = String(order);
    btn.appendChild(badge);
  }

  const description = describeControlForA11y(control);
  btn.title = description;
  btn.setAttribute("aria-label", description);
  if (control.id === state.selectedControlId) {
    btn.classList.add("marker--selected");
    btn.setAttribute("aria-current", "true");
  }
  positionMarkerElement(btn, control);
  btn.addEventListener("pointerdown", (e) => onMarkerPointerDown(e, control.id));
  btn.addEventListener("keydown", (e) => onMarkerKeyDown(e, control.id));
  btn.addEventListener("focus", () => selectControl(control.id));
  return btn;
}

function renderMarkers() {
  els.markersLayer.innerHTML = "";
  for (const control of state.controls) {
    els.markersLayer.appendChild(createMarkerElement(control));
  }
}

// -----------------------------------------------------------------------------------------
// Controls: table (the fully keyboard-operable editing surface)
// -----------------------------------------------------------------------------------------

function updateTableRowXY(id, x, y) {
  const xInput = document.getElementById(`control-${id}-x`);
  const yInput = document.getElementById(`control-${id}-y`);
  if (xInput) xInput.value = String(round1(x));
  if (yInput) yInput.value = String(round1(y));
}

function numberInputCell(id, value, { step = 1, min, allowNull = false } = {}, onCommit) {
  const td = document.createElement("td");
  const input = document.createElement("input");
  input.type = "number";
  input.id = id;
  input.step = String(step);
  if (min != null) input.min = String(min);
  input.value = value == null ? "" : String(value);
  input.addEventListener("change", () => {
    const raw = input.value.trim();
    if (raw === "" && allowNull) {
      onCommit(null);
      return;
    }
    const num = Number(raw);
    if (Number.isNaN(num)) {
      input.value = value == null ? "" : String(value);
      return;
    }
    onCommit(num);
  });
  td.appendChild(input);
  return td;
}

function deleteControl(id) {
  if (state.selectedControlId === id) state.selectedControlId = null;
  state.controls = state.controls.filter((c) => c.id !== id);
  refreshControlsUI();
  saveControlsNow();
}

function createControlRow(control) {
  const tr = document.createElement("tr");
  tr.id = `control-row-${control.id}`;
  if (control.id === state.selectedControlId) {
    tr.classList.add("row-selected");
    tr.setAttribute("aria-selected", "true");
  }
  // Selecting a row highlights its marker (ADR-021, vice versa of onMarkerPointerDown). Ignore
  // clicks on the delete button -- the row is about to be removed, not selected.
  tr.addEventListener("click", (e) => {
    if (e.target.closest(`#control-${control.id}-delete`)) return;
    selectControl(control.id);
  });
  tr.addEventListener("focusin", () => selectControl(control.id));

  const idTd = document.createElement("td");
  idTd.textContent = String(control.id);
  tr.appendChild(idTd);

  tr.appendChild(
    numberInputCell(`control-${control.id}-x`, round1(control.x), { step: 0.1, min: 0 }, (v) => {
      control.x = v;
      refreshControlsUI();
      saveControlsNow();
    })
  );
  tr.appendChild(
    numberInputCell(`control-${control.id}-y`, round1(control.y), { step: 0.1, min: 0 }, (v) => {
      control.y = v;
      refreshControlsUI();
      saveControlsNow();
    })
  );
  tr.appendChild(
    numberInputCell(
      `control-${control.id}-number`,
      control.number,
      { step: 1, min: 0, allowNull: true },
      (v) => {
        control.number = v == null ? null : Math.trunc(v);
        refreshControlsUI();
        saveControlsNow();
      }
    )
  );
  tr.appendChild(
    numberInputCell(
      `control-${control.id}-points`,
      control.points,
      { step: 1, min: 0, allowNull: true },
      (v) => {
        control.points = v == null ? null : Math.trunc(v);
        refreshControlsUI();
        saveControlsNow();
      }
    )
  );

  const hubTd = document.createElement("td");
  const hubRadio = document.createElement("input");
  hubRadio.type = "radio";
  hubRadio.name = "control-hub-radio";
  hubRadio.id = `control-${control.id}-hub`;
  hubRadio.checked = control.is_hub;
  hubRadio.setAttribute("aria-label", `Отметить контроль ${control.id} как хаб (старт и финиш)`);
  hubRadio.addEventListener("change", () => {
    for (const c of state.controls) c.is_hub = c.id === control.id;
    refreshControlsUI();
    saveControlsNow();
  });
  hubTd.appendChild(hubRadio);
  tr.appendChild(hubTd);

  const delTd = document.createElement("td");
  const delBtn = document.createElement("button");
  delBtn.type = "button";
  delBtn.id = `control-${control.id}-delete`;
  delBtn.textContent = "Удалить";
  delBtn.setAttribute("aria-label", `Удалить контроль ${control.number ?? control.id}`);
  delBtn.addEventListener("click", () => deleteControl(control.id));
  delTd.appendChild(delBtn);
  tr.appendChild(delTd);

  return tr;
}

function renderControlsTable() {
  els.controlsTbody.innerHTML = "";
  for (const control of state.controls) {
    els.controlsTbody.appendChild(createControlRow(control));
  }
}

function addControlAt(x, y) {
  const id = state.controls.length ? Math.max(...state.controls.map((c) => c.id)) + 1 : 0;
  const control = {
    id,
    x,
    y,
    number: null,
    points: null,
    confidence: 1.0,
    source: "manual",
    is_hub: state.controls.length === 0,
  };
  state.controls = [...state.controls, control];
  refreshControlsUI();
  saveControlsNow();
  const numberInput = document.getElementById(`control-${id}-number`);
  if (numberInput) numberInput.focus();
}

// -----------------------------------------------------------------------------------------
// Map preview (raw uploaded bytes) + calibration
// -----------------------------------------------------------------------------------------

async function loadMapPreview() {
  try {
    const img = await new Promise((resolve, reject) => {
      const image = new Image();
      image.onload = () => resolve(image);
      image.onerror = () => reject(new Error("preview unavailable"));
      image.src = api.mapUrl(state.runId);
    });
    state.mapImage = img;
    view.setImage(img);
    if (!state.segment) {
      view.setMapSize(img.naturalWidth, img.naturalHeight);
      view.fit();
    }
    els.mapPreviewNote.hidden = true;
    redraw();
  } catch {
    // Expected for formats an <img> can't decode (e.g. PDF) -- SPEC/T061 brief accepts this as
    // a known gap; the user can still calibrate/edit by typing pixel coordinates directly.
    state.mapImage = null;
    view.setImage(null);
    els.mapPreviewNote.hidden = false;
  }
}

function syncCalibrationFields() {
  const [p1, p2] = state.calibration;
  els.calibX1.value = p1 ? String(round1(p1.x)) : "";
  els.calibY1.value = p1 ? String(round1(p1.y)) : "";
  els.calibX2.value = p2 ? String(round1(p2.x)) : "";
  els.calibY2.value = p2 ? String(round1(p2.y)) : "";
}

function readCalibrationFieldsIntoState() {
  const p1x = els.calibX1.value.trim();
  const p1y = els.calibY1.value.trim();
  const p2x = els.calibX2.value.trim();
  const p2y = els.calibY2.value.trim();
  const pts = [];
  if (p1x !== "" && p1y !== "") pts.push({ x: Number(p1x), y: Number(p1y) });
  if (p2x !== "" && p2y !== "") pts.push({ x: Number(p2x), y: Number(p2y) });
  state.calibration = pts;
  renderCalibrationOverlay();
}

function setCalibrationPoint(x, y) {
  state.calibration = state.calibration.length >= 2 ? [{ x, y }] : [...state.calibration, { x, y }];
  syncCalibrationFields();
  renderCalibrationOverlay();
}

function getCalibrationPoints() {
  const [p1, p2] = state.calibration;
  if (!p1 || !p2) return null;
  return { x1: p1.x, y1: p1.y, x2: p2.x, y2: p2.y };
}

// -----------------------------------------------------------------------------------------
// Jobs: segment / detect / plan
// -----------------------------------------------------------------------------------------

async function runSegment(body) {
  setStatus("Сегментация карты…");
  clearError();
  els.applyScaleBtn.disabled = true;
  try {
    const { job_id } = await api.startSegment(state.runId, body);
    const job = await api.waitForJob(job_id, {
      onTick: (j) => setStatus(`Сегментация карты: ${jobStatusLabel(j.status)}…`),
    });
    if (job.status === "error") {
      setError(job.error || "Сегментация завершилась ошибкой");
      return;
    }
    onSegmentDone(job.result);
  } catch (err) {
    setError(describeError(err, "Не удалось запустить сегментацию"));
  } finally {
    els.applyScaleBtn.disabled = false;
  }
}

function onSegmentDone(result) {
  state.segment = result;
  view.setMapSize(result.width, result.height);
  view.fit();
  // A re-segment (new scale) invalidates any previously planned route -- its polyline pixel
  // coordinates were computed against the old grid.
  state.route = null;
  view.setRoute(null);
  state.routeArtifactReady = false;
  els.routeResults.hidden = true;
  redraw();
  setStatus(`Сегментация завершена: ${result.width}x${result.height} px, ${result.dpi} DPI.`);
  updateAvailability();
  if (!state.detectAttempted) runDetect();
}

async function runDetect() {
  if (!state.runId || !state.segment) return;
  setStatus("Распознавание контролей…");
  clearError();
  els.detectBtn.disabled = true;
  try {
    const { job_id } = await api.startDetect(state.runId);
    const job = await api.waitForJob(job_id, {
      onTick: (j) => setStatus(`Распознавание контролей: ${jobStatusLabel(j.status)}…`),
    });
    onDetectDone(job);
  } catch (err) {
    state.detectAttempted = true;
    setError(describeError(err, "Не удалось запустить распознавание контролей"));
    updateHubWarning();
    updateAvailability();
  } finally {
    els.detectBtn.disabled = !state.segment;
  }
}

function onDetectDone(job) {
  state.detectAttempted = true;
  if (job.status === "error") {
    setError(job.error || "Распознавание контролей завершилось ошибкой");
    updateHubWarning();
    updateAvailability();
    return;
  }
  const result = job.result;
  state.controls = result.controls;
  state.controlsArtifactReady = true;
  if (!result.hub_found) {
    setError("Хаб не найден автоматически. Добавьте контроль и отметьте его как хаб в таблице.");
  } else {
    clearError();
    setStatus(`Распознано контролей: ${result.controls.length}.`);
  }
  refreshControlsUI();
}

function onPlanDone(route) {
  state.route = route;
  state.routeArtifactReady = true;
  view.setRoute(route);
  redraw();
  renderRouteResults(route);
  refreshControlsUI(); // picks up the new visit-order badges
  setStatus("Маршрут построен.");
}

function renderRouteResults(route) {
  els.routeResults.hidden = false;
  els.routeTotalTime.textContent = formatDuration(route.total_seconds);
  els.routeTotalDistance.textContent = formatMeters(route.total_meters);
  els.routePoints.textContent = String(route.points);
  els.routePenalty.textContent = route.penalty.toFixed(1);
  els.routeScore.textContent = route.score.toFixed(1);
  els.routeSolver.textContent =
    route.solver === "exact" ? (route.optimal ? "точный (оптимально)" : "точный") : "эвристика";

  els.legsTbody.innerHTML = "";
  let cumulative = 0;
  route.legs.forEach((leg, i) => {
    cumulative += leg.seconds;
    const toControl = findControl(leg.to_id);
    const points =
      toControl && !toControl.is_hub && toControl.points != null ? String(toControl.points) : "—";
    const tr = document.createElement("tr");
    tr.id = `leg-row-${i}`;
    for (const text of [
      String(i + 1),
      controlLabel(leg.from_id),
      controlLabel(leg.to_id),
      (leg.seconds / 60).toFixed(1),
      String(Math.round(leg.meters)),
      formatDuration(cumulative),
      points,
    ]) {
      const td = document.createElement("td");
      td.textContent = text;
      tr.appendChild(td);
    }
    els.legsTbody.appendChild(tr);
  });
}

// -----------------------------------------------------------------------------------------
// Run lifecycle
// -----------------------------------------------------------------------------------------

function resetForNewRun(runId) {
  state.runId = runId;
  state.segment = null;
  state.controls = [];
  state.route = null;
  state.visitOrder = new Map();
  state.detectAttempted = false;
  state.controlsArtifactReady = false;
  state.routeArtifactReady = false;
  state.mapImage = null;
  state.calibration = [];
  syncCalibrationFields();
  setMode("idle");
  view.setImage(null);
  view.setRoute(null);
  view.setMapSize(0, 0);
  els.runIdValue.textContent = runId;
  els.runIdDisplay.hidden = false;
  els.routeResults.hidden = true;
  refreshControlsUI();
  redraw();
}

// -----------------------------------------------------------------------------------------
// Event wiring
// -----------------------------------------------------------------------------------------

function initUploadForm() {
  els.uploadForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = els.mapFileInput.files[0];
    if (!file) {
      setError("Выберите файл карты.");
      return;
    }
    setStatus("Загрузка карты…");
    clearError();
    els.uploadBtn.disabled = true;
    try {
      const { run_id } = await api.uploadMap(file);
      resetForNewRun(run_id);
      els.scaleFieldset.disabled = false;
      setStatus("Карта загружена. Задайте масштаб.");
      await loadMapPreview();
    } catch (err) {
      setError(describeError(err, "Не удалось загрузить карту"));
    } finally {
      els.uploadBtn.disabled = false;
    }
  });
}

function initScaleForm() {
  function updateScalePanels() {
    const calibrate = els.scaleModeCalibrate.checked;
    const auto = els.scaleModeAuto.checked;
    els.scaleRatioPanel.hidden = calibrate || auto;
    els.scaleCalibratePanel.hidden = !calibrate;
    setMode(calibrate && state.mode === "calibrate" ? "calibrate" : "idle");
  }
  els.scaleModeRatio.addEventListener("change", updateScalePanels);
  els.scaleModeCalibrate.addEventListener("change", updateScalePanels);
  els.scaleModeAuto.addEventListener("change", updateScalePanels);
  updateScalePanels();

  els.calibStartBtn.addEventListener("click", () => {
    if (state.mode === "calibrate") {
      setMode("idle");
      return;
    }
    state.calibration = [];
    syncCalibrationFields();
    renderCalibrationOverlay();
    setMode("calibrate");
    els.mapViewport.focus();
  });

  for (const field of [els.calibX1, els.calibY1, els.calibX2, els.calibY2]) {
    field.addEventListener("change", readCalibrationFieldsIntoState);
  }

  els.scaleForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.runId) return;
    const page = Number(els.scalePage.value) || 0;
    const body = { page };
    if (els.scaleModeRatio.checked) {
      const scale = Number(els.scaleDenominator.value);
      const dpi = Number(els.scaleDpi.value);
      if (!(scale > 0) || !(dpi > 0)) {
        setError("Укажите положительные значения масштаба (1:N) и DPI.");
        return;
      }
      body.scale = scale;
      body.dpi = dpi;
    } else if (els.scaleModeAuto.checked) {
      setStatus("Автоматическое определение масштаба…");
      clearError();
      els.applyScaleBtn.disabled = true;
      let job;
      try {
        const { job_id } = await api.startAutoScale(state.runId);
        job = await api.waitForJob(job_id, {
          onTick: (j) =>
            setStatus(`Автоматическое определение масштаба: ${jobStatusLabel(j.status)}…`),
        });
      } catch (err) {
        setError(describeError(err, "Не удалось запустить автоматическое определение масштаба"));
        els.applyScaleBtn.disabled = false;
        return;
      }
      els.applyScaleBtn.disabled = false;
      if (job.status === "error") {
        setError(job.error || "Автоматическое определение масштаба завершилось ошибкой");
        return;
      }
      const { source, scale_denominator: scale, dpi } = job.result;
      els.scaleDenominator.value = scale;
      els.scaleDpi.value = dpi;
      els.scaleModeRatio.checked = true;
      updateScalePanels();
      setStatus(`Масштаб определён автоматически (${source}): 1:${scale}, ${dpi} DPI.`);
      // Give the browser a chance to actually paint the line above -- runSegment() below
      // overwrites #status-message with its own text as its very first (synchronous) statement,
      // so without this pause the tier message never has a rendered frame to appear in (found
      // during T088's own review; see docs/TASKS.md's T088 entry).
      await new Promise((resolve) => setTimeout(resolve, 1200));
      body.scale = scale;
      body.dpi = dpi;
    } else {
      const points = getCalibrationPoints();
      const meters = Number(els.calibMeters.value);
      if (!points || !(meters > 0)) {
        setError("Укажите обе точки калибровочной линии и положительную длину в метрах.");
        return;
      }
      body.calibrate = { ...points, meters };
      const dpiOverride = els.calibDpi.value.trim();
      if (dpiOverride !== "") body.dpi = Number(dpiOverride);
    }
    await runSegment(body);
  });
}

function initMapToolbar() {
  els.zoomInBtn.addEventListener("click", () => {
    view.zoomAt(view.cssWidth / 2, view.cssHeight / 2, 1.25);
    redraw();
  });
  els.zoomOutBtn.addEventListener("click", () => {
    view.zoomAt(view.cssWidth / 2, view.cssHeight / 2, 1 / 1.25);
    redraw();
  });
  els.zoomResetBtn.addEventListener("click", () => {
    view.fit();
    redraw();
  });
  els.toggleAddModeBtn.addEventListener("click", () => {
    setMode(state.mode === "add" ? "idle" : "add");
    els.mapViewport.focus();
  });
  els.detectBtn.addEventListener("click", () => runDetect());
  els.addControlBtn.addEventListener("click", () => {
    const c = view.viewCenterMap();
    addControlAt(clamp(c.x, 0, view.mapWidth || c.x), clamp(c.y, 0, view.mapHeight || c.y));
  });
}

function startPan(e) {
  const canvas = els.mapCanvas;
  canvas.setPointerCapture(e.pointerId);
  let lastX = e.clientX;
  let lastY = e.clientY;
  function onMove(ev) {
    view.panBy(ev.clientX - lastX, ev.clientY - lastY);
    lastX = ev.clientX;
    lastY = ev.clientY;
    redraw();
  }
  function onUp() {
    canvas.removeEventListener("pointermove", onMove);
    canvas.removeEventListener("pointerup", onUp);
  }
  canvas.addEventListener("pointermove", onMove);
  canvas.addEventListener("pointerup", onUp);
}

function initMapViewport() {
  els.mapCanvas.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    const rect = els.mapViewport.getBoundingClientRect();
    const { x, y } = view.screenToMap(e.clientX - rect.left, e.clientY - rect.top);
    if (state.mode === "add") {
      addControlAt(clamp(x, 0, view.mapWidth || x), clamp(y, 0, view.mapHeight || y));
      return;
    }
    if (state.mode === "calibrate") {
      setCalibrationPoint(clamp(x, 0, view.mapWidth || x), clamp(y, 0, view.mapHeight || y));
      return;
    }
    startPan(e);
  });

  els.mapCanvas.addEventListener(
    "wheel",
    (e) => {
      e.preventDefault();
      const rect = els.mapViewport.getBoundingClientRect();
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
      view.zoomAt(e.clientX - rect.left, e.clientY - rect.top, factor);
      redraw();
    },
    { passive: false }
  );

  els.mapViewport.addEventListener("keydown", (e) => {
    if (e.target.closest(".marker")) return; // the marker's own handler owns this keystroke
    const panStep = 40;
    const centerZoom = () => view.zoomAt(view.cssWidth / 2, view.cssHeight / 2, 1.25);
    switch (e.key) {
      case "ArrowUp":
        view.panBy(0, panStep);
        redraw();
        e.preventDefault();
        break;
      case "ArrowDown":
        view.panBy(0, -panStep);
        redraw();
        e.preventDefault();
        break;
      case "ArrowLeft":
        view.panBy(panStep, 0);
        redraw();
        e.preventDefault();
        break;
      case "ArrowRight":
        view.panBy(-panStep, 0);
        redraw();
        e.preventDefault();
        break;
      case "+":
      case "=":
        centerZoom();
        redraw();
        e.preventDefault();
        break;
      case "-":
        view.zoomAt(view.cssWidth / 2, view.cssHeight / 2, 1 / 1.25);
        redraw();
        e.preventDefault();
        break;
      case "0":
        view.fit();
        redraw();
        e.preventDefault();
        break;
      case "Enter": {
        const c = view.viewCenterMap();
        const cx = clamp(c.x, 0, view.mapWidth || c.x);
        const cy = clamp(c.y, 0, view.mapHeight || c.y);
        if (state.mode === "add") {
          addControlAt(cx, cy);
          e.preventDefault();
        } else if (state.mode === "calibrate") {
          setCalibrationPoint(cx, cy);
          e.preventDefault();
        }
        break;
      }
      default:
        break;
    }
  });

  const resizeObserver = new ResizeObserver(() => {
    view.resize();
    redraw();
  });
  resizeObserver.observe(els.mapViewport);
}

function initRunForm() {
  els.runForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.runId || !state.segment) return;
    const speedKmh = Number(els.paramSpeedKmh.value);
    const timeLimitMin = Number(els.paramTimeLimitMin.value);
    const penalty = Number(els.paramPenalty.value);
    if (!(speedKmh > 0) || !(timeLimitMin > 0)) {
      setError("Скорость и лимит времени должны быть положительными числами.");
      return;
    }
    const runConfig = {
      base_speed_mps: speedKmh / 3.6,
      time_limit_s: timeLimitMin * 60,
      penalty_per_min: Number.isFinite(penalty) ? penalty : 1.0,
    };
    setStatus("Построение маршрута…");
    clearError();
    els.runBtn.disabled = true;
    try {
      const { job_id } = await api.startPlan(state.runId, runConfig);
      const job = await api.waitForJob(job_id, {
        onTick: (j) => setStatus(`Построение маршрута: ${jobStatusLabel(j.status)}…`),
      });
      if (job.status === "error") {
        setError(job.error || "Не удалось построить маршрут");
        return;
      }
      onPlanDone(job.result.route);
    } catch (err) {
      setError(describeError(err, "Не удалось построить маршрут"));
    } finally {
      updateAvailability();
    }
  });
}

function init() {
  initUploadForm();
  initScaleForm();
  initMapToolbar();
  initMapViewport();
  initRunForm();
  updateAvailability();
}

init();
