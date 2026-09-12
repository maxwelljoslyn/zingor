// Building design editor (#197): a per-layer 2D plan editor drawn in SVG.
//
// One page, no library. It loads a design over JSON, keeps the working
// document and an undo stack in memory, autosaves a draft, asks the server
// for the bill of materials as the drawing changes, and commits versions.
// The document format and every rule the server enforces live in
// characters/design_document.py; wallPieces below mirrors
// characters/geometry.wall_pieces so walls drawn flush pass the overlap check.
//
// Hooks are data-* attributes on the [data-design-editor] root.
(function () {
  "use strict";

  var SVG_NS = "http://www.w3.org/2000/svg";
  var GRID = 5;
  var LAYER = 5;
  var MAGNET_PX = 10;
  // Undo and redo take Command on a Mac and Control elsewhere.
  var IS_MAC = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  var KINDS = ["walls", "floors", "solids", "roofs", "openings", "rooms"];
  var SINGULAR = { walls: "wall", floors: "floor", solids: "solid", roofs: "roof", openings: "opening", rooms: "room" };
  var TOOL_KIND = { wall: "walls", floor: "floors", solid: "solids", roof: "roofs", opening: "openings", room: "rooms" };

  // --- geometry (feet) ---

  function sub(a, b) { return [a[0] - b[0], a[1] - b[1]]; }
  function add(a, b) { return [a[0] + b[0], a[1] + b[1]]; }
  function scale(a, k) { return [a[0] * k, a[1] * k]; }
  function dot(a, b) { return a[0] * b[0] + a[1] * b[1]; }
  function cross2(a, b) { return a[0] * b[1] - a[1] * b[0]; }
  function len(a) { return Math.hypot(a[0], a[1]); }
  function dist(a, b) { return len(sub(b, a)); }
  function unit(a) { var l = len(a); return l < 1e-9 ? null : [a[0] / l, a[1] / l]; }

  function segments(points, closed) {
    var out = [];
    for (var i = 0; i + 1 < points.length; i++) out.push([points[i], points[i + 1]]);
    if (closed && points.length > 2) out.push([points[points.length - 1], points[0]]);
    return out;
  }

  function spans(points, closed) {
    var start = 0;
    return segments(points, closed).map(function (s) {
      var end = start + dist(s[0], s[1]);
      var span = { a: s[0], b: s[1], start: start, end: end };
      start = end;
      return span;
    });
  }

  function polygonArea(points) {
    var total = 0;
    for (var i = 0; i < points.length; i++) total += cross2(points[i], points[(i + 1) % points.length]);
    return Math.abs(total / 2);
  }

  function centroid(points) {
    var x = 0, y = 0;
    points.forEach(function (p) { x += p[0]; y += p[1]; });
    return [x / points.length, y / points.length];
  }

  // Mirrors geometry.wall_pieces: one mitred quadrilateral per segment, or
  // null when the wall cannot be built (the server says why).
  function wallPieces(points, thickness, closed) {
    var segs = segments(points, closed);
    var half = thickness / 2;
    var normals = [];
    for (var i = 0; i < segs.length; i++) {
      var d = unit(sub(segs[i][1], segs[i][0]));
      if (!d) return null;
      normals.push([-d[1], d[0]]);
    }
    function mitre(n0, n1) {
      var m = unit(add(n0, n1));
      if (!m) return null;
      var c = dot(m, n0);
      if (c < 0.2) return null;
      return scale(m, half / c);
    }
    var pieces = [];
    for (var k = 0; k < segs.length; k++) {
      var n = normals[k];
      var square = scale(n, half);
      var s = (k > 0 || closed) ? mitre(normals[(k - 1 + segs.length) % segs.length], n) : square;
      var e = (k < segs.length - 1 || closed) ? mitre(n, normals[(k + 1) % segs.length]) : square;
      if (!s || !e) return null;
      var a = segs[k][0], b = segs[k][1];
      pieces.push([sub(a, s), sub(b, e), add(b, e), add(a, s)]);
    }
    return pieces;
  }

  function insideConvex(p, poly) {
    for (var i = 0; i < poly.length; i++) {
      var a = poly[i], b = poly[(i + 1) % poly.length];
      if (cross2(sub(b, a), sub(p, a)) < -1e-9) return false;
    }
    return true;
  }

  function insidePolygon(p, poly) {
    var inside = false;
    for (var i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      var a = poly[i], b = poly[j];
      if ((a[1] > p[1]) !== (b[1] > p[1]) && p[0] < (b[0] - a[0]) * (p[1] - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
    }
    return inside;
  }

  // Where segment p→q first crosses the edge a→b, as a fraction along p→q.
  function crossing(p, q, a, b) {
    var r = sub(q, p), s = sub(b, a);
    var denom = cross2(r, s);
    if (Math.abs(denom) < 1e-12) return null;
    var t = cross2(sub(a, p), s) / denom;
    var u = cross2(sub(a, p), r) / denom;
    return (t >= -1e-9 && t <= 1 + 1e-9 && u >= -1e-9 && u <= 1 + 1e-9) ? { t: t, edge: s } : null;
  }

  function zOverlap(a, b) { return a[0] < b[1] - 1e-6 && b[0] < a[1] - 1e-6; }

  function onSegment(a, b, p) {
    return Math.min(a[0], b[0]) - 1e-9 <= p[0] && p[0] <= Math.max(a[0], b[0]) + 1e-9 &&
      Math.min(a[1], b[1]) - 1e-9 <= p[1] && p[1] <= Math.max(a[1], b[1]) + 1e-9;
  }

  // Mirrors geometry.segments_touch: any shared point, endpoints included.
  function segmentsTouch(p1, p2, q1, q2) {
    var d1 = cross2(sub(q2, q1), sub(p1, q1)), d2 = cross2(sub(q2, q1), sub(p2, q1));
    var d3 = cross2(sub(p2, p1), sub(q1, p1)), d4 = cross2(sub(p2, p1), sub(q2, p1));
    if (d1 * d2 < 0 && d3 * d4 < 0) return true;
    return (Math.abs(d1) <= 1e-9 && onSegment(q1, q2, p1)) || (Math.abs(d2) <= 1e-9 && onSegment(q1, q2, p2)) ||
      (Math.abs(d3) <= 1e-9 && onSegment(p1, p2, q1)) || (Math.abs(d4) <= 1e-9 && onSegment(p1, p2, q2));
  }

  // Mirrors geometry.is_simple: neighbouring segments may share only their
  // common point and may not fold back along each other; others may not meet.
  function isSimple(points, closed) {
    var segs = segments(points, closed);
    var n = segs.length;
    for (var i = 0; i < n; i++) {
      for (var j = i + 1; j < n; j++) {
        var next = j === i + 1, wrap = closed && i === 0 && j === n - 1;
        if (next || wrap) {
          var shared = next ? segs[i][1] : segs[i][0];
          var farI = next ? segs[i][0] : segs[i][1];
          var farJ = next ? segs[j][1] : segs[j][0];
          if (Math.abs(cross2(sub(farI, shared), sub(farJ, shared))) <= 1e-9 && dot(sub(farI, shared), sub(farJ, shared)) > 0) return false;
        } else if (segmentsTouch(segs[i][0], segs[i][1], segs[j][0], segs[j][1])) {
          return false;
        }
      }
    }
    return true;
  }

  // --- the editor ---

  function Editor(root) {
    this.root = root;
    this.svg = root.querySelector("[data-canvas]");
    this.doc = emptyDocument();
    this.headVersion = null;
    this.baseVersion = null;
    this.canEdit = false;
    this.materials = [];
    this.layer = 0;
    this.tool = "select";
    this.selection = null;
    this.drawing = null;
    this.cursor = null;
    this.view = { x: -10, y: -10, scale: 12 };
    this.undoStack = [];
    this.redoStack = [];
    this.defaults = {};
    this.draftTimer = null;
    this.bomTimer = null;
    this.bomRequest = 0;
    this.load();
  }

  function emptyDocument() {
    var doc = {};
    KINDS.forEach(function (k) { doc[k] = []; });
    return doc;
  }

  Editor.prototype.$ = function (selector) { return this.root.querySelector(selector); };

  Editor.prototype.request = function (url, body) {
    var options = { credentials: "same-origin", headers: {} };
    if (body !== undefined) {
      var token = document.querySelector("[name=csrfmiddlewaretoken]");
      options.method = "POST";
      options.headers["Content-Type"] = "application/json";
      options.headers["X-CSRFToken"] = token ? token.value : "";
      options.body = JSON.stringify(body);
    }
    return fetch(url, options).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (data) {
        return { ok: response.ok, status: response.status, data: data };
      });
    });
  };

  Editor.prototype.load = function () {
    var self = this;
    this.request(this.root.dataset.documentUrl).then(function (result) {
      var data = result.data;
      self.canEdit = data.can_edit;
      self.materials = data.materials;
      self.headVersion = data.head;
      self.setDefaults();
      if (data.draft) {
        self.doc = normalise(data.draft.document);
        self.baseVersion = data.draft.base_version;
        self.notice("Resumed your unsaved draft from " + new Date(data.draft.updated_at).toLocaleString() + ".", true);
      } else {
        self.doc = normalise(data.head ? data.head.document : emptyDocument());
        self.baseVersion = data.head ? data.head.id : null;
      }
      self.root.classList.toggle("design-editor--readonly", !self.canEdit);
      self.bind();
      self.fitView();
      self.renderVersion();
      self.changed(false);
    });
  };

  function normalise(doc) {
    var copy = JSON.parse(JSON.stringify(doc || {}));
    KINDS.forEach(function (k) { if (!Array.isArray(copy[k])) copy[k] = []; });
    return copy;
  }

  Editor.prototype.materialsFor = function (usages, unit) {
    return this.materials.filter(function (m) {
      return usages.indexOf(m.usage) >= 0 && (!unit || m.unit === unit);
    });
  };

  Editor.prototype.material = function (key) {
    for (var i = 0; i < this.materials.length; i++) if (this.materials[i].key === key) return this.materials[i];
    return null;
  };

  Editor.prototype.setDefaults = function () {
    function first(list) { return list.length ? list[0].key : ""; }
    var wall = first(this.materialsFor(["wall"]));
    // An ordinary door, where the catalogue has one, rather than whatever
    // opening sorts first (a 14 ft bastion gate fits few walls).
    var product = this.material("board-and-batten-door") ? "board-and-batten-door" : first(this.materialsFor(["opening"]));
    var wallMaterial = this.material(wall);
    var productMaterial = this.material(product);
    this.defaults = {
      walls: { material: wall, thickness: (wallMaterial && wallMaterial.thickness) || 1, height: 10, closed: false },
      floors: { material: first(this.materialsFor(["floor"])) },
      solids: { material: first(this.materialsFor(["solid", "wall"], "cuft")), height: 5 },
      roofs: { material: first(this.materialsFor(["roof"])), covering: null, pitch: 30 },
      openings: {
        product: product,
        width: (productMaterial && productMaterial.width) || 3,
        height: (productMaterial && productMaterial.height) || 7,
        sill: 0
      },
      rooms: { name: "Room", height: 10 }
    };
  };

  // --- document changes ---

  Editor.prototype.snapshot = function () {
    this.undoStack.push(JSON.stringify(this.doc));
    if (this.undoStack.length > 200) this.undoStack.shift();
    this.redoStack = [];
  };

  Editor.prototype.undo = function () {
    if (!this.undoStack.length) return;
    this.redoStack.push(JSON.stringify(this.doc));
    this.doc = JSON.parse(this.undoStack.pop());
    this.selection = null;
    this.changed(true);
  };

  Editor.prototype.redo = function () {
    if (!this.redoStack.length) return;
    this.undoStack.push(JSON.stringify(this.doc));
    this.doc = JSON.parse(this.redoStack.pop());
    this.selection = null;
    this.changed(true);
  };

  Editor.prototype.changed = function (dirty) {
    var self = this;
    this.render();
    this.renderProperties();
    clearTimeout(this.bomTimer);
    this.bomTimer = setTimeout(function () { self.refreshBom(); }, 350);
    if (dirty && this.canEdit) {
      this.status("Unsaved changes");
      clearTimeout(this.draftTimer);
      this.draftTimer = setTimeout(function () { self.saveDraft(); }, 2000);
    }
  };

  Editor.prototype.saveDraft = function () {
    var self = this;
    this.request(this.root.dataset.draftUrl, { document: this.doc, base_version: this.baseVersion }).then(function (result) {
      self.status(result.ok ? "Draft saved " + new Date().toLocaleTimeString() : "Draft not saved: " + (result.data.problems || []).join("; "));
    });
  };

  Editor.prototype.findShape = function (kind, id) {
    var list = this.doc[kind];
    for (var i = 0; i < list.length; i++) if (list[i].id === id) return list[i];
    return null;
  };

  Editor.prototype.newId = function (kind) {
    var prefix = SINGULAR[kind][0];
    var used = {};
    KINDS.forEach(function (k) { this.doc[k].forEach(function (s) { used[s.id] = true; }); }, this);
    var n = 1;
    while (used[prefix + n]) n++;
    return prefix + n;
  };

  Editor.prototype.newRoomId = function () {
    var lowest = 0;
    this.doc.rooms.forEach(function (r) { if (r.id < lowest) lowest = r.id; });
    return lowest - 1;
  };

  Editor.prototype.layerBottom = function () { return this.layer * LAYER; };

  Editor.prototype.onLayer = function (kind, shape) {
    var bottom = this.layerBottom(), top = bottom + LAYER;
    if (kind === "floors" || kind === "roofs") return shape.z >= bottom - 1e-6 && shape.z < top - 1e-6;
    if (kind === "openings") return false;
    return Array.isArray(shape.z) && shape.z[0] < top - 1e-6 && shape.z[1] > bottom + 1e-6;
  };

  // --- coordinates and snapping ---

  Editor.prototype.toWorld = function (event) {
    var point = this.svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    var p = point.matrixTransform(this.svg.getScreenCTM().inverse());
    return [p.x, p.y];
  };

  Editor.prototype.magnets = function () {
    var points = [];
    var self = this;
    KINDS.forEach(function (kind) {
      if (kind === "openings") return;
      self.doc[kind].forEach(function (shape) {
        if (!self.onLayer(kind, shape) || !shape.points) return;
        shape.points.forEach(function (p) { points.push(p); });
        if (kind === "walls") {
          (wallPieces(shape.points, shape.thickness, shape.closed) || []).forEach(function (piece) {
            piece.forEach(function (p) { points.push(p); });
          });
        }
      });
    });
    if (this.drawing) this.drawing.points.forEach(function (p) { points.push(p); });
    return points;
  };

  // Snap to a nearby vertex; else, from `anchor`, along the nearest 45° to
  // where that line crosses a grid line. Snapping to grid lines rather than
  // to 5 ft steps from the anchor means one point placed off the grid (at a
  // wall's face, say) does not carry every later point off it too. Holding
  // Shift places the point exactly where the pointer is.
  Editor.prototype.snap = function (p, anchor, event) {
    if (event && event.shiftKey) return p;
    var nearest = null, nearestDistance = MAGNET_PX / this.view.scale;
    this.magnets().forEach(function (m) {
      var d = dist(m, p);
      if (d < nearestDistance) { nearest = m; nearestDistance = d; }
    });
    if (nearest) return [nearest[0], nearest[1]];
    var grid = [Math.round(p[0] / GRID) * GRID, Math.round(p[1] / GRID) * GRID];
    var v = anchor ? sub(p, anchor) : null;
    if (!v || len(v) < 1e-9) return grid;
    var angle = Math.round(Math.atan2(v[1], v[0]) / (Math.PI / 4)) * (Math.PI / 4);
    var d = [Math.cos(angle), Math.sin(angle)].map(function (c) { return Math.abs(c) < 1e-9 ? 0 : c; });
    var along = dot(v, d);
    var best = null;
    [0, 1].forEach(function (axis) {
      if (d[axis] === 0) return;
      var line = Math.round((anchor[axis] + d[axis] * along) / GRID) * GRID;
      var t = (line - anchor[axis]) / d[axis];
      if (t > 1e-9 && (best === null || Math.abs(t - along) < Math.abs(best - along))) best = t;
    });
    if (best === null) return grid;
    var q = add(anchor, scale(d, best));
    // Keep an axis-aligned run exactly level with its anchor.
    if (d[0] === 0) q[0] = anchor[0];
    if (d[1] === 0) q[1] = anchor[1];
    return q;
  };

  // Butt joints: pull a new wall's end back to the face of any wall it has
  // run into, so the two bodies meet without sharing volume.
  Editor.prototype.trimEnd = function (inner, end, thickness, z, skipId) {
    var self = this;
    var direction = unit(sub(end, inner));
    if (!direction) return end;
    var total = dist(inner, end);
    var result = end;
    this.doc.walls.forEach(function (wall) {
      if (wall.id === skipId || !zOverlap(wall.z, z)) return;
      (wallPieces(wall.points, wall.thickness, wall.closed) || []).forEach(function (piece) {
        if (!insideConvex(end, piece)) return;
        var first = null;
        for (var i = 0; i < 4; i++) {
          var hit = crossing(inner, end, piece[i], piece[(i + 1) % 4]);
          if (hit && (!first || hit.t < first.t)) first = hit;
        }
        if (!first) return;
        var face = unit(first.edge);
        var sine = Math.abs(cross2(direction, face));
        if (sine < 1e-6) return;
        var pull = (thickness / 2) * Math.abs(dot(direction, face)) / sine;
        var length = first.t * total - pull;
        if (length > 0.1 && length < dist(inner, result)) result = add(inner, scale(direction, length));
      });
    });
    return result;
  };

  // --- hit testing ---

  Editor.prototype.openingQuad = function (opening) {
    var wall = this.findShape("walls", opening.wall);
    if (!wall) return null;
    var list = spans(wall.points, wall.closed);
    for (var i = 0; i < list.length; i++) {
      var span = list[i];
      if (opening.offset >= span.start - 1e-6 && opening.offset + opening.width <= span.end + 1e-6) {
        var d = unit(sub(span.b, span.a));
        var n = scale([-d[1], d[0]], wall.thickness / 2 + 0.15);
        var a = add(span.a, scale(d, opening.offset - span.start));
        var b = add(a, scale(d, opening.width));
        return [sub(a, n), sub(b, n), add(b, n), add(a, n)];
      }
    }
    return null;
  };

  Editor.prototype.hit = function (p) {
    return this.hits(p)[0] || null;
  };

  // Every shape under `p` on this layer, topmost first.
  Editor.prototype.hits = function (p) {
    var self = this;
    var found = [];
    var order = ["openings", "walls", "rooms", "solids", "roofs", "floors"];
    for (var o = 0; o < order.length; o++) {
      var kind = order[o];
      var list = this.doc[kind];
      for (var i = list.length - 1; i >= 0; i--) {
        var shape = list[i];
        if (kind === "openings") {
          var wall = self.findShape("walls", shape.wall);
          var quad = wall && self.onLayer("walls", wall) ? self.openingQuad(shape) : null;
          if (quad && insideConvex(p, quad)) found.push({ kind: kind, id: shape.id });
        } else if (self.onLayer(kind, shape)) {
          if (kind === "walls") {
            var pieces = wallPieces(shape.points, shape.thickness, shape.closed) || [];
            if (pieces.some(function (piece) { return insideConvex(p, piece); })) found.push({ kind: kind, id: shape.id });
          } else if (insidePolygon(p, shape.points)) {
            found.push({ kind: kind, id: shape.id });
          }
        }
      }
    }
    return found;
  };

  // --- pointer and keyboard ---

  Editor.prototype.bind = function () {
    var self = this;
    this.svg.addEventListener("pointerdown", function (e) { self.pointerDown(e); });
    this.svg.addEventListener("pointermove", function (e) { self.pointerMove(e); });
    this.svg.addEventListener("pointerup", function (e) { self.pointerUp(e); });
    this.svg.addEventListener("dblclick", function (e) { e.preventDefault(); self.finishDrawing(); });
    this.svg.addEventListener("wheel", function (e) { e.preventDefault(); self.zoom(e); }, { passive: false });
    this.svg.addEventListener("contextmenu", function (e) { e.preventDefault(); });
    // The canvas may not have its final size when the design loads, so fit
    // again on resize until the player has moved the view themselves.
    new ResizeObserver(function () {
      if (!self.viewMoved) self.fitView();
      self.render();
    }).observe(this.svg);
    document.addEventListener("keydown", function (e) { self.key(e); });
    this.root.querySelectorAll("[data-tool]").forEach(function (button) {
      button.addEventListener("click", function () { self.setTool(button.dataset.tool); });
    });
    this.root.querySelectorAll("[data-layer-step]").forEach(function (button) {
      button.addEventListener("click", function () { self.setLayer(self.layer + Number(button.dataset.layerStep)); });
    });
    this.$("[data-action=undo]").addEventListener("click", function () { self.undo(); });
    this.$("[data-action=redo]").addEventListener("click", function () { self.redo(); });
    this.$("[data-action=fit]").addEventListener("click", function () { self.fitView(); self.render(); });
    var commitButton = this.$("[data-action=commit]");
    if (commitButton) commitButton.addEventListener("click", function () { self.commit(); });
    var discardButton = this.$("[data-action=discard]");
    if (discardButton) discardButton.addEventListener("click", function () { self.discardDraft(); });
    window.addEventListener("beforeunload", function () {
      if (self.draftTimer && self.canEdit) self.saveDraft();
    });
    this.setTool("select");
    this.setLayer(0);
  };

  Editor.prototype.setTool = function (tool) {
    if (!this.canEdit && tool !== "select") return;
    this.tool = tool;
    this.drawing = null;
    if (tool !== "select") this.selection = null;
    this.root.querySelectorAll("[data-tool]").forEach(function (button) {
      button.setAttribute("aria-pressed", button.dataset.tool === tool ? "true" : "false");
    });
    this.render();
    this.renderProperties();
  };

  Editor.prototype.setLayer = function (layer) {
    this.layer = layer;
    this.drawing = null;
    var bottom = layer * LAYER;
    this.$("[data-layer-label]").textContent = "Layer " + layer + " (" + bottom + " to " + (bottom + LAYER) + " ft)";
    this.render();
    this.renderProperties();
  };

  Editor.prototype.pointerDown = function (e) {
    var p = this.toWorld(e);
    if (e.button === 1 || e.button === 2 || (this.tool === "select" && e.button === 0 && !this.canEdit)) {
      this.startPan(e);
      return;
    }
    if (e.button !== 0) return;
    if (this.tool === "select") {
      var handle = this.handleAt(p);
      if (handle) {
        this.snapshot();
        this.dragging = handle;
        this.svg.setPointerCapture(e.pointerId);
        return;
      }
      // Clicking again where shapes are stacked (a floor under a room, say)
      // selects the next one down, and from the bottom one back to the top.
      var under = this.hits(p);
      var current = this.selection;
      var at = current ? under.findIndex(function (h) { return h.kind === current.kind && h.id === current.id; }) : -1;
      this.selection = under.length ? under[(at + 1) % under.length] : null;
      if (!this.selection) this.startPan(e);
      this.render();
      this.renderProperties();
      return;
    }
    if (this.tool === "opening") {
      this.placeOpening(p);
      return;
    }
    var anchor = this.drawing ? this.drawing.points[this.drawing.points.length - 1] : null;
    var q = this.snap(p, anchor, e);
    if (!this.drawing) {
      this.drawing = { points: [q] };
    } else {
      var first = this.drawing.points[0];
      var minimum = 3;
      if (this.drawing.points.length >= minimum && dist(q, first) < 1e-6) {
        this.finishDrawing(true);
        return;
      }
      if (dist(q, anchor) > 1e-6) {
        if (!isSimple(this.drawing.points.concat([q]), false)) {
          this.status("That point would make the outline cross itself.");
          return;
        }
        this.drawing.points.push(q);
      }
    }
    this.render();
  };

  Editor.prototype.startPan = function (e) {
    this.pan = { client: [e.clientX, e.clientY], view: { x: this.view.x, y: this.view.y } };
    this.svg.setPointerCapture(e.pointerId);
  };

  Editor.prototype.pointerMove = function (e) {
    var p = this.toWorld(e);
    if (this.pan) {
      var s = this.view.scale;
      this.view.x = this.pan.view.x - (e.clientX - this.pan.client[0]) / s;
      this.view.y = this.pan.view.y - (e.clientY - this.pan.client[1]) / s;
      this.viewMoved = true;
      this.render();
      return;
    }
    if (this.dragging) {
      var shape = this.findShape(this.dragging.kind, this.dragging.id);
      var points = shape.points;
      var i = this.dragging.index;
      var anchor = points[i - 1] || (shape.closed || this.dragging.kind !== "walls" ? points[points.length - 1] : points[1]);
      points[i] = this.snap(p, anchor === points[i] ? null : anchor, e);
      this.render();
      return;
    }
    if (this.tool !== "select") {
      var last = this.drawing ? this.drawing.points[this.drawing.points.length - 1] : null;
      this.cursor = this.tool === "opening" ? p : this.snap(p, last, e);
      this.render();
    }
  };

  Editor.prototype.pointerUp = function (e) {
    if (this.pan) { this.pan = null; return; }
    if (this.dragging) {
      // A dragged end of an open wall stops at the face of a wall it ran
      // into, just as it would have if drawn there.
      var drag = this.dragging;
      var shape = this.findShape(drag.kind, drag.id);
      var last = shape.points.length - 1;
      if (drag.kind === "walls" && !shape.closed && (drag.index === 0 || drag.index === last)) {
        var inner = shape.points[drag.index === 0 ? 1 : last - 1];
        shape.points[drag.index] = this.trimEnd(inner, shape.points[drag.index], shape.thickness, shape.z, shape.id);
      }
      this.dragging = null;
      this.changed(true);
    }
  };

  Editor.prototype.zoom = function (e) {
    var before = this.toWorld(e);
    var factor = Math.exp(-e.deltaY * 0.0015);
    this.view.scale = Math.min(200, Math.max(1, this.view.scale * factor));
    this.viewMoved = true;
    this.render();
    var after = this.toWorld(e);
    this.view.x += before[0] - after[0];
    this.view.y += before[1] - after[1];
    this.render();
  };

  Editor.prototype.fitView = function () {
    var xs = [], ys = [];
    KINDS.forEach(function (kind) {
      this.doc[kind].forEach(function (shape) {
        (shape.points || []).forEach(function (p) { xs.push(p[0]); ys.push(p[1]); });
      });
    }, this);
    var rect = this.svg.getBoundingClientRect();
    var width = rect.width || 800, height = rect.height || 600;
    if (!xs.length) {
      this.view = { x: -10, y: -10, scale: Math.min(width, height) / 80 };
      return;
    }
    var minX = Math.min.apply(null, xs) - 10, maxX = Math.max.apply(null, xs) + 10;
    var minY = Math.min.apply(null, ys) - 10, maxY = Math.max.apply(null, ys) + 10;
    var s = Math.min(width / (maxX - minX), height / (maxY - minY));
    this.view = { x: minX, y: minY, scale: s };
  };

  Editor.prototype.key = function (e) {
    var target = e.target;
    if (target && (target.tagName === "INPUT" || target.tagName === "SELECT" || target.tagName === "TEXTAREA")) return;
    var letter = e.key.length === 1 ? e.key.toLowerCase() : "";
    if ((IS_MAC ? e.metaKey : e.ctrlKey) && (letter === "z" || letter === "y")) {
      e.preventDefault();
      if (!this.canEdit) return;
      if (letter === "y" || e.shiftKey) this.redo(); else this.undo();
      return;
    }
    // Tool shortcuts are declared on the buttons (data-shortcut), so they can
    // later come from a player's preferences without touching this handler.
    if (/^[a-z]$/.test(letter) && !e.metaKey && !e.ctrlKey && !e.altKey) {
      var button = this.root.querySelector('[data-tool][data-shortcut="' + letter + '"]');
      if (button) {
        e.preventDefault();
        this.setTool(button.dataset.tool);
        return;
      }
    }
    if (e.key === "Escape") { this.drawing = null; this.selection = null; this.render(); this.renderProperties(); return; }
    if (e.key === "Enter") { this.finishDrawing(); return; }
    if (e.key === "Backspace" && this.drawing) {
      e.preventDefault();
      this.drawing.points.pop();
      if (!this.drawing.points.length) this.drawing = null;
      this.render();
      return;
    }
    if ((e.key === "Delete" || e.key === "Backspace") && this.selection && this.canEdit) {
      e.preventDefault();
      this.deleteSelection();
      return;
    }
    if (e.key === "PageUp") { e.preventDefault(); this.setLayer(this.layer + 1); }
    if (e.key === "PageDown") { e.preventDefault(); this.setLayer(this.layer - 1); }
  };

  // --- creating and deleting shapes ---

  Editor.prototype.finishDrawing = function (closedByClick) {
    if (!this.drawing || this.tool === "select") return;
    var kind = TOOL_KIND[this.tool];
    var points = this.drawing.points;
    var defaults = this.defaults[kind];
    var bottom = this.layerBottom();
    var shape;
    if (kind === "walls") {
      if (points.length < 2) return;
      var closed = !!closedByClick || !!defaults.closed;
      if (closed && points.length < 3) closed = false;
      if (!isSimple(points, closed)) {
        this.status("That wall would cross itself.");
        return;
      }
      var z = [bottom, bottom + Number(defaults.height)];
      var id = this.newId("walls");
      points = points.slice();
      if (!closed) {
        points[points.length - 1] = this.trimEnd(points[points.length - 2], points[points.length - 1], Number(defaults.thickness), z, id);
        points[0] = this.trimEnd(points[1], points[0], Number(defaults.thickness), z, id);
      }
      shape = { id: id, points: points, closed: closed, thickness: Number(defaults.thickness), z: z, material: defaults.material };
    } else {
      if (points.length < 3 || polygonArea(points) < 0.01) return;
      if (!isSimple(points, true)) {
        this.status("Closing there would make the outline cross itself.");
        return;
      }
      if (kind === "floors") shape = { id: this.newId(kind), points: points, z: bottom, material: defaults.material };
      if (kind === "solids") shape = { id: this.newId(kind), points: points, z: [bottom, bottom + Number(defaults.height)], material: defaults.material };
      if (kind === "roofs") shape = { id: this.newId(kind), points: points, z: bottom, pitch: Number(defaults.pitch), material: defaults.material, covering: defaults.covering || null };
      if (kind === "rooms") shape = { id: this.newRoomId(), name: defaults.name || "Room", points: points, z: [bottom, bottom + Number(defaults.height)] };
    }
    this.snapshot();
    this.doc[kind].push(shape);
    this.drawing = null;
    this.selection = { kind: kind, id: shape.id };
    this.changed(true);
  };

  Editor.prototype.placeOpening = function (p) {
    var target = this.hits(p).filter(function (h) { return h.kind === "walls"; })[0];
    if (!target) {
      this.status("Click on a wall to place a door or window.");
      return;
    }
    var wall = this.findShape("walls", target.id);
    var defaults = this.defaults.openings;
    var width = Number(defaults.width);
    var best = null;
    spans(wall.points, wall.closed).forEach(function (span) {
      var d = unit(sub(span.b, span.a));
      var along = Math.max(0, Math.min(span.end - span.start, dot(sub(p, span.a), d)));
      var gap = dist(p, add(span.a, scale(d, along)));
      if (!best || gap < best.gap) best = { span: span, along: along, gap: gap };
    });
    var length = best.span.end - best.span.start;
    if (width > length) {
      this.status("That opening is wider than this run of wall.");
      return;
    }
    var wallHeight = wall.z[1] - wall.z[0];
    var height = Math.min(Number(defaults.height), wallHeight - Number(defaults.sill));
    if (height <= 0) {
      this.status("The sill is above the top of this wall.");
      return;
    }
    var local = Math.round(Math.max(0, Math.min(length - width, best.along - width / 2)) * 2) / 2;
    var opening = {
      id: this.newId("openings"),
      wall: wall.id,
      offset: Math.round((best.span.start + local) * 1000) / 1000,
      width: width,
      height: height,
      sill: Number(defaults.sill),
      product: defaults.product
    };
    this.snapshot();
    this.doc.openings.push(opening);
    this.selection = { kind: "openings", id: opening.id };
    this.changed(true);
  };

  Editor.prototype.deleteSelection = function () {
    var sel = this.selection;
    this.snapshot();
    this.doc[sel.kind] = this.doc[sel.kind].filter(function (s) { return s.id !== sel.id; });
    if (sel.kind === "walls") this.doc.openings = this.doc.openings.filter(function (o) { return o.wall !== sel.id; });
    this.selection = null;
    this.changed(true);
  };

  // --- saving ---

  Editor.prototype.commit = function () {
    var self = this;
    var messageInput = this.$("[data-commit-message]");
    clearTimeout(this.draftTimer);
    this.draftTimer = null;
    this.status("Saving…");
    this.request(this.root.dataset.commitUrl, {
      document: this.doc,
      parent: this.baseVersion,
      message: messageInput.value
    }).then(function (result) {
      if (!result.ok) {
        self.status("Not saved.");
        self.renderProblems(result.data.problems || ["The server refused the save."], true);
        return;
      }
      var mapping = result.data.rooms || {};
      function remap(json) {
        var doc = JSON.parse(json);
        (doc.rooms || []).forEach(function (r) { if (mapping[r.id] !== undefined) r.id = mapping[r.id]; });
        return JSON.stringify(doc);
      }
      self.undoStack = self.undoStack.map(remap);
      self.redoStack = self.redoStack.map(remap);
      self.doc = normalise(result.data.version.document);
      if (self.selection && self.selection.kind === "rooms" && mapping[self.selection.id] !== undefined) {
        self.selection.id = mapping[self.selection.id];
      }
      self.headVersion = result.data.version;
      self.baseVersion = result.data.version.id;
      messageInput.value = "";
      self.notice(result.data.sibling
        ? "Saved as version " + self.baseVersion + ". Someone else had already saved changes from the version you started with, so yours is a separate branch; the design now shows yours."
        : "Saved as version " + self.baseVersion + ".", false);
      self.status("Saved");
      self.renderVersion();
      self.changed(false);
    });
  };

  Editor.prototype.discardDraft = function () {
    var self = this;
    clearTimeout(this.draftTimer);
    this.draftTimer = null;
    this.request(this.root.dataset.discardUrl, {}).then(function () {
      self.snapshot();
      self.doc = normalise(self.headVersion ? self.headVersion.document : emptyDocument());
      self.baseVersion = self.headVersion ? self.headVersion.id : null;
      self.selection = null;
      self.notice("", false);
      self.status("Draft discarded");
      self.changed(false);
    });
  };

  Editor.prototype.status = function (text) {
    var el = this.$("[data-save-status]");
    if (el) el.textContent = text;
  };

  Editor.prototype.notice = function (text, offerDiscard) {
    var el = this.$("[data-notice]");
    el.hidden = !text;
    el.querySelector("[data-notice-text]").textContent = text;
    var discard = this.$("[data-action=discard]");
    if (discard) discard.hidden = !offerDiscard;
  };

  Editor.prototype.renderVersion = function () {
    var el = this.$("[data-version]");
    var head = this.headVersion;
    el.textContent = head
      ? "Version " + head.id + (head.author ? " by " + head.author : "") + ", " + new Date(head.created_at).toLocaleString() + (head.message ? ": " + head.message : "")
      : "Nothing saved yet.";
  };

  // --- bill of materials ---

  Editor.prototype.refreshBom = function () {
    var self = this;
    var request = ++this.bomRequest;
    this.request(this.root.dataset.bomUrl, { document: this.doc }).then(function (result) {
      if (request !== self.bomRequest) return;
      self.renderBom(result.data);
      self.renderProblems(result.data.problems || [], false);
    });
  };

  Editor.prototype.renderBom = function (data) {
    var body = this.$("[data-bom-lines]");
    body.textContent = "";
    function row(cells, title) {
      var tr = document.createElement("tr");
      cells.forEach(function (text, i) {
        var td = document.createElement("td");
        td.textContent = text;
        if (i > 0) td.className = "nowrap";
        tr.appendChild(td);
      });
      if (title) tr.title = title;
      body.appendChild(tr);
      return tr;
    }
    // Material, amount, sale unit, units, unit price, cost.
    (data.lines || []).forEach(function (line) {
      var tr = row([line.name, line.quantity, line.sale_unit, line.units, line.price || "unpriced", line.cost || "—"], line.good);
      if (line.basis) tr.children[2].title = line.basis;
    });
    // Shapes the server could not price: shown with a warning, their problems
    // on hover, so the rest of the bill still adds up.
    var broken = data.broken || [];
    broken.forEach(function (shape) {
      var tr = row([shape.name + " (" + shape.shape + ")", "—", "—", "—", "—", "⚠"], shape.problems.join("; "));
      tr.className = "design-bom-broken";
      tr.lastChild.setAttribute("aria-label", "Not priced until its problem is fixed");
    });
    this.$("[data-bom-legend]").hidden = !broken.length;
    this.$("[data-bom-total-label]").textContent = broken.length ? "Total, without ⚠ rows" : "Total";
    this.$("[data-bom-total]").textContent = data.total || "—";
    this.$("[data-bom-market]").textContent = data.market ? "Priced in " + data.market + "." : "No price list has been imported.";
    var unpriced = this.$("[data-bom-unpriced]");
    unpriced.hidden = !(data.unpriced && data.unpriced.length);
    unpriced.textContent = unpriced.hidden ? "" : "Not in the price list, so not in the total: " + data.unpriced.join(", ") + ".";
  };

  Editor.prototype.renderProblems = function (problems, fromSave) {
    var list = this.$("[data-problems]");
    list.textContent = "";
    problems.forEach(function (text) {
      var item = document.createElement("li");
      item.textContent = text;
      list.appendChild(item);
    });
    this.$("[data-problems-block]").hidden = !problems.length;
    this.$("[data-problems-heading]").textContent = fromSave ? "Why it was not saved" : "Must be fixed before saving";
  };

  // --- properties panel ---

  function fieldsFor(kind) {
    if (kind === "walls") return [["material", "Material", "material", ["wall"]], ["thickness", "Thickness (ft)", "number"], ["bottom", "Bottom (ft)", "number"], ["top", "Top (ft)", "number"], ["closed", "Closed loop", "checkbox"]];
    if (kind === "floors") return [["material", "Material", "material", ["floor"]], ["z", "Height (ft)", "number"]];
    if (kind === "solids") return [["material", "Material", "material", ["solid", "wall"], "cuft"], ["bottom", "Bottom (ft)", "number"], ["top", "Top (ft)", "number"]];
    if (kind === "roofs") return [["material", "Material", "material", ["roof"]], ["covering", "Covering", "material", ["roof"], null, true], ["pitch", "Pitch (°)", "number"], ["z", "Eaves height (ft)", "number"]];
    if (kind === "openings") return [["product", "Product", "material", ["opening"]], ["width", "Width (ft)", "number"], ["height", "Height (ft)", "number"], ["sill", "Sill (ft)", "number"], ["offset", "Offset along wall (ft)", "number"]];
    return [["name", "Name", "text"], ["bottom", "Bottom (ft)", "number"], ["top", "Top (ft)", "number"]];
  }

  // Tool defaults hold a height where a shape holds z; translate between them.
  function readField(target, key, isDefaults) {
    if (key === "bottom") return isDefaults ? null : target.z[0];
    if (key === "top") return isDefaults ? null : target.z[1];
    return target[key];
  }

  Editor.prototype.renderProperties = function () {
    var self = this;
    var panel = this.$("[data-properties]");
    var heading = this.$("[data-properties-heading]");
    panel.textContent = "";
    var target, kind, isDefaults;
    if (this.selection) {
      kind = this.selection.kind;
      target = this.findShape(kind, this.selection.id);
      if (!target) { this.selection = null; return this.renderProperties(); }
      isDefaults = false;
      heading.textContent = "Selected " + SINGULAR[kind] + (kind === "rooms" ? "" : " " + target.id);
    } else if (this.tool !== "select") {
      kind = TOOL_KIND[this.tool];
      target = this.defaults[kind];
      isDefaults = true;
      heading.textContent = "New " + SINGULAR[kind];
      var how = document.createElement("p");
      how.className = "muted text-sm";
      how.textContent = kind === "openings"
        ? "Click on a wall to place it."
        : kind === "walls"
          ? "Click each corner. Press Enter or double-click to finish, or click the first point to close the loop."
          : "Click each corner. Click the circled first point, press Enter or double-click to close the outline.";
      panel.appendChild(how);
    } else {
      heading.textContent = "Properties";
      var hint = document.createElement("p");
      hint.className = "muted text-sm";
      hint.textContent = this.canEdit
        ? "Choose a tool to draw, or click a shape to select it. Shift places points off the grid."
        : "Click a shape to see what it is made of.";
      panel.appendChild(hint);
      return;
    }
    var fields = fieldsFor(kind);
    if (isDefaults && kind !== "openings" && kind !== "floors" && kind !== "roofs") {
      fields = fields.filter(function (f) { return f[0] !== "bottom" && f[0] !== "top"; });
      fields.push(["height", "Height (ft)", "number"]);
    }
    if (isDefaults && kind === "openings") fields = fields.filter(function (f) { return f[0] !== "offset"; });
    if (isDefaults && (kind === "floors" || kind === "roofs")) fields = fields.filter(function (f) { return f[0] !== "z"; });
    fields.forEach(function (field) {
      var key = field[0], type = field[2];
      var label = document.createElement("label");
      label.className = "design-field";
      var caption = document.createElement("span");
      caption.textContent = field[1];
      label.appendChild(caption);
      var input;
      if (type === "material") {
        input = document.createElement("select");
        if (field[5]) input.appendChild(new Option("none", ""));
        self.materialsFor(field[3], field[4]).forEach(function (m) { input.appendChild(new Option(m.name, m.key)); });
        input.value = readField(target, key, isDefaults) || "";
      } else {
        input = document.createElement("input");
        input.type = type;
        if (type === "number") input.step = "any";
        if (type === "checkbox") input.checked = !!readField(target, key, isDefaults);
        else input.value = readField(target, key, isDefaults);
      }
      input.disabled = !self.canEdit;
      input.addEventListener("change", function () {
        var value = type === "checkbox" ? input.checked : type === "number" ? Number(input.value) : input.value;
        if (type === "material" && value === "") value = null;
        self.applyField(kind, target, key, value, isDefaults);
      });
      label.appendChild(input);
      panel.appendChild(label);
    });
    if (!isDefaults && this.canEdit) {
      var remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn btn-danger btn-small";
      remove.textContent = "Delete " + SINGULAR[kind];
      remove.addEventListener("click", function () { self.deleteSelection(); });
      panel.appendChild(remove);
    }
  };

  Editor.prototype.applyField = function (kind, target, key, value, isDefaults) {
    if (isDefaults) {
      target[key] = value;
      if (kind === "openings" && key === "product") {
        var m = this.material(value);
        if (m && m.width) target.width = m.width;
        if (m && m.height) target.height = m.height;
      }
      if (kind === "walls" && key === "material") {
        var wm = this.material(value);
        if (wm && wm.thickness) target.thickness = wm.thickness;
      }
      this.renderProperties();
      return;
    }
    this.snapshot();
    if (key === "bottom") target.z = [value, target.z[1]];
    else if (key === "top") target.z = [target.z[0], value];
    else target[key] = value;
    this.changed(true);
  };

  // --- drawing ---

  function el(name, attributes, parent) {
    var node = document.createElementNS(SVG_NS, name);
    Object.keys(attributes).forEach(function (k) { node.setAttribute(k, attributes[k]); });
    if (parent) parent.appendChild(node);
    return node;
  }

  function pointsAttr(points) {
    return points.map(function (p) { return p[0] + "," + p[1]; }).join(" ");
  }

  Editor.prototype.handleAt = function (p) {
    if (!this.selection || !this.canEdit || this.selection.kind === "openings") return null;
    var shape = this.findShape(this.selection.kind, this.selection.id);
    if (!shape) return null;
    var reach = MAGNET_PX / this.view.scale;
    for (var i = 0; i < shape.points.length; i++) {
      if (dist(shape.points[i], p) < reach) return { kind: this.selection.kind, id: shape.id, index: i };
    }
    return null;
  };

  Editor.prototype.render = function () {
    var svg = this.svg;
    var rect = svg.getBoundingClientRect();
    var width = (rect.width || 800) / this.view.scale;
    var height = (rect.height || 600) / this.view.scale;
    svg.setAttribute("viewBox", [this.view.x, this.view.y, width, height].join(" "));
    svg.textContent = "";
    var px = 1 / this.view.scale;
    this.renderGrid(width, height, px);
    var self = this;
    var below = { layer: this.layer - 1 };
    // The layer below, faintly, to line things up against.
    this.doc.walls.forEach(function (wall) {
      var bottom = below.layer * LAYER;
      if (!(wall.z[0] < bottom + LAYER && wall.z[1] > bottom) || self.onLayer("walls", wall)) return;
      (wallPieces(wall.points, wall.thickness, wall.closed) || []).forEach(function (piece) {
        el("polygon", { points: pointsAttr(piece), class: "dz-ghost", "stroke-width": px }, svg);
      });
    });
    ["floors", "roofs", "solids", "rooms", "walls"].forEach(function (kind) {
      self.doc[kind].forEach(function (shape) {
        if (!self.onLayer(kind, shape)) return;
        var selected = self.selection && self.selection.kind === kind && self.selection.id === shape.id;
        var extra = selected ? " dz-selected" : "";
        if (kind === "walls") {
          var pieces = wallPieces(shape.points, shape.thickness, shape.closed);
          if (!pieces) {
            el("polyline", { points: pointsAttr(shape.points), class: "dz-invalid", "stroke-width": 2 * px }, svg);
            return;
          }
          pieces.forEach(function (piece) {
            el("polygon", { points: pointsAttr(piece), class: "dz-wall" + extra, "stroke-width": px }, svg);
          });
        } else {
          el("polygon", { points: pointsAttr(shape.points), class: "dz-" + SINGULAR[kind] + extra, "stroke-width": 1.5 * px, "stroke-dasharray": kind === "roofs" ? 6 * px + " " + 4 * px : "" }, svg);
          var c = centroid(shape.points);
          var text = kind === "rooms" ? shape.name : kind === "roofs" ? "roof " + shape.pitch + "°" : "";
          if (text) {
            var label = el("text", { x: c[0], y: c[1], class: "dz-label", "font-size": 12 * px, "text-anchor": "middle" }, svg);
            label.textContent = text;
          }
        }
        if (selected && self.canEdit) {
          shape.points.forEach(function (p) {
            el("circle", { cx: p[0], cy: p[1], r: 4 * px, class: "dz-handle", "stroke-width": px }, svg);
          });
        }
      });
    });
    this.doc.openings.forEach(function (opening) {
      var wall = self.findShape("walls", opening.wall);
      if (!wall || !self.onLayer("walls", wall)) return;
      var quad = self.openingQuad(opening);
      if (!quad) return;
      var selected = self.selection && self.selection.kind === "openings" && self.selection.id === opening.id;
      el("polygon", { points: pointsAttr(quad), class: "dz-opening" + (selected ? " dz-selected" : ""), "stroke-width": px }, svg);
    });
    this.renderDrawing(px);
  };

  Editor.prototype.renderGrid = function (width, height, px) {
    var svg = this.svg;
    var step = GRID;
    while (step * this.view.scale < 8) step *= 2;
    var x0 = Math.floor(this.view.x / step) * step, y0 = Math.floor(this.view.y / step) * step;
    var path = "";
    for (var x = x0; x <= this.view.x + width; x += step) path += "M" + x + " " + this.view.y + "V" + (this.view.y + height);
    for (var y = y0; y <= this.view.y + height; y += step) path += "M" + this.view.x + " " + y + "H" + (this.view.x + width);
    el("path", { d: path, class: "dz-grid", "stroke-width": px }, svg);
    el("path", { d: "M-2 0H2M0 -2V2", class: "dz-origin", "stroke-width": 2 * px }, svg);
  };

  Editor.prototype.renderDrawing = function (px) {
    var svg = this.svg;
    if (this.tool === "select" || !this.cursor) return;
    var points = this.drawing ? this.drawing.points.concat([this.cursor]) : [this.cursor];
    if (this.drawing && this.drawing.points.length >= 2) {
      // Where the outline will close: the first point, and for a polygon the
      // edge back to it.
      var start = this.drawing.points[0];
      if (this.tool !== "wall") {
        el("line", { x1: this.cursor[0], y1: this.cursor[1], x2: start[0], y2: start[1], class: "dz-preview-close", "stroke-width": px, "stroke-dasharray": 4 * px + " " + 3 * px }, svg);
      }
      el("circle", { cx: start[0], cy: start[1], r: 7 * px, class: "dz-close-target", "stroke-width": 1.5 * px }, svg);
    }
    if (points.length > 1) {
      el("polyline", { points: pointsAttr(points), class: "dz-preview", "stroke-width": 1.5 * px }, svg);
      var a = points[points.length - 2], b = points[points.length - 1];
      var label = el("text", { x: b[0] + 8 * px, y: b[1] - 8 * px, class: "dz-label", "font-size": 12 * px }, svg);
      label.textContent = (Math.round(dist(a, b) * 10) / 10) + " ft";
    }
    el("circle", { cx: this.cursor[0], cy: this.cursor[1], r: 3 * px, class: "dz-cursor" }, svg);
  };

  document.querySelectorAll("[data-design-editor]").forEach(function (root) { new Editor(root); });
})();
