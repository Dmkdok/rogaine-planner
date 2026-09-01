// Canvas rendering + pan/zoom transform (ADR-005: Canvas 2D, no framework). Owns the canvas
// pixel grid and the map-pixel <-> screen-pixel transform; control markers are separate DOM
// elements (app.js) so they get real keyboard focus and ARIA semantics -- something a canvas
// cannot offer an assistive-tech user on its own. `render()` here draws only what genuinely
// benefits from raster drawing: the map image (or a placeholder ground) and the route overlay.

const MIN_ZOOM = 0.02;
const MAX_ZOOM = 16;

// Mirrors `render/overlay.py`'s `_HALO_COLOR`/`_CORE_COLOR` so the on-canvas route preview reads
// the same way as the exported route.png: a dark halo pass then a bright core pass, legible over
// any map colouring regardless of the UI's own light/dark theme.
const HALO_COLOR = "rgb(15, 15, 15)";
const CORE_COLOR = "rgb(255, 36, 36)";

export class MapView {
  /** @param {HTMLElement} container @param {HTMLCanvasElement} canvas */
  constructor(container, canvas) {
    this.container = container;
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.mapWidth = 0;
    this.mapHeight = 0;
    this.image = null; // HTMLImageElement | null -- null draws a placeholder ground instead
    this.route = null; // Route | null
    this.zoom = 1;
    this.panX = 0;
    this.panY = 0;
    this._resizeCanvasToContainer();
  }

  /** Call once the map's true pixel grid is known (segment result, or the raw image's own size). */
  setMapSize(width, height) {
    this.mapWidth = width;
    this.mapHeight = height;
  }

  setImage(image) {
    this.image = image;
  }

  setRoute(route) {
    this.route = route;
  }

  /** Resync the canvas's backing-store resolution to its CSS size (call on container resize). */
  _resizeCanvasToContainer() {
    const dpr = window.devicePixelRatio || 1;
    const rect = this.container.getBoundingClientRect();
    const w = Math.max(1, Math.round(rect.width));
    const h = Math.max(1, Math.round(rect.height));
    this.canvas.width = w * dpr;
    this.canvas.height = h * dpr;
    this.canvas.style.width = `${w}px`;
    this.canvas.style.height = `${h}px`;
    this.cssWidth = w;
    this.cssHeight = h;
    this._dpr = dpr;
  }

  resize() {
    this._resizeCanvasToContainer();
  }

  /** Centre + scale the whole map-pixel grid to fill the viewport. */
  fit() {
    if (this.mapWidth <= 0 || this.mapHeight <= 0) return;
    const margin = 0.92; // small breathing room so edge markers aren't clipped by the viewport
    const zoom = Math.min(
      (this.cssWidth / this.mapWidth) * margin,
      (this.cssHeight / this.mapHeight) * margin
    );
    this.zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
    this.panX = (this.cssWidth - this.mapWidth * this.zoom) / 2;
    this.panY = (this.cssHeight - this.mapHeight * this.zoom) / 2;
  }

  /** Zoom by `factor`, keeping the map point under CSS-pixel (`cx`, `cy`) fixed on screen. */
  zoomAt(cx, cy, factor) {
    const newZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, this.zoom * factor));
    const mapX = (cx - this.panX) / this.zoom;
    const mapY = (cy - this.panY) / this.zoom;
    this.zoom = newZoom;
    this.panX = cx - mapX * newZoom;
    this.panY = cy - mapY * newZoom;
  }

  panBy(dx, dy) {
    this.panX += dx;
    this.panY += dy;
  }

  /** CSS-pixel viewport coordinates -> map-pixel coordinates. */
  screenToMap(sx, sy) {
    return { x: (sx - this.panX) / this.zoom, y: (sy - this.panY) / this.zoom };
  }

  /** Map-pixel coordinates -> CSS-pixel viewport coordinates (for positioning marker elements). */
  mapToScreen(mx, my) {
    return { x: mx * this.zoom + this.panX, y: my * this.zoom + this.panY };
  }

  /** The map-pixel point currently at the centre of the viewport (for keyboard-only placement). */
  viewCenterMap() {
    return this.screenToMap(this.cssWidth / 2, this.cssHeight / 2);
  }

  render() {
    const ctx = this.ctx;
    ctx.setTransform(this._dpr, 0, 0, this._dpr, 0, 0);
    ctx.clearRect(0, 0, this.cssWidth, this.cssHeight);

    ctx.save();
    ctx.translate(this.panX, this.panY);
    ctx.scale(this.zoom, this.zoom);

    if (this.mapWidth > 0 && this.mapHeight > 0) {
      if (this.image) {
        ctx.drawImage(this.image, 0, 0, this.mapWidth, this.mapHeight);
      } else {
        ctx.fillStyle = "#9a9a90";
        ctx.fillRect(0, 0, this.mapWidth, this.mapHeight);
      }
      if (this.route) this._drawRoute(ctx);
    }

    ctx.restore();
  }

  _drawRoute(ctx) {
    const halo = Math.max(1, 4 / this.zoom);
    const core = Math.max(0.5, 1.6 / this.zoom);
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    for (const leg of this.route.legs) {
      if (!leg.polyline || leg.polyline.length < 2) continue;
      for (const [width, color] of [
        [halo, HALO_COLOR],
        [core, CORE_COLOR],
      ]) {
        ctx.beginPath();
        ctx.moveTo(leg.polyline[0][0], leg.polyline[0][1]);
        for (const [x, y] of leg.polyline.slice(1)) ctx.lineTo(x, y);
        ctx.strokeStyle = color;
        ctx.lineWidth = width;
        ctx.stroke();
      }
    }
  }
}
