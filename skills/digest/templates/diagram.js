// digest diagram layout script: runs inside the rendered page.
// It draws the arrows from the real box positions (after fonts load), then checks the result:
// a label on a box, two labels on each other, an arrow through a box, or content wider than
// the canvas each become a warning in window.__digestWarnings, and diagram.mjs fails on them.
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const warnings = [];

  function run() {
    const canvas = document.getElementById("canvas");
    const svg = document.getElementById("wires");
    const labelLayer = document.getElementById("labels");
    const C = canvas.getBoundingClientRect();
    const W = canvas.clientWidth;
    const H = canvas.scrollHeight;
    svg.setAttribute("width", W);
    svg.setAttribute("height", H);
    svg.setAttribute("viewBox", "0 0 " + W + " " + H);
    const style = getComputedStyle(document.body);
    const color = (t) =>
      style.getPropertyValue("--" + (t || "line")).trim() || "#888";
    const defs = document.createElementNS(NS, "defs");
    svg.appendChild(defs);
    const markers = {};
    function marker(t) {
      const key = t || "line";
      if (markers[key]) return markers[key];
      const m = document.createElementNS(NS, "marker");
      m.setAttribute("id", "ah-" + key);
      m.setAttribute("viewBox", "0 0 12 12");
      m.setAttribute("refX", "10.5");
      m.setAttribute("refY", "6");
      m.setAttribute("markerWidth", "26");
      m.setAttribute("markerHeight", "26");
      m.setAttribute("markerUnits", "userSpaceOnUse");
      m.setAttribute("orient", "auto-start-reverse");
      const p = document.createElementNS(NS, "path");
      p.setAttribute("d", "M1,1.5 L11,6 L1,10.5 Z");
      p.setAttribute("fill", color(key));
      m.appendChild(p);
      defs.appendChild(m);
      markers[key] = "url(#ah-" + key + ")";
      return markers[key];
    }
    function box(el) {
      const r = el.getBoundingClientRect();
      const x = r.left - C.left,
        y = r.top - C.top;
      return {
        x: x,
        y: y,
        w: r.width,
        h: r.height,
        r: x + r.width,
        b: y + r.height,
        cx: x + r.width / 2,
        cy: y + r.height / 2,
      };
    }
    const byId = (id) =>
      document.querySelector('[data-id="' + CSS.escape(id) + '"]');
    const nodeEls = Array.from(
      document.querySelectorAll(".node, .lane, .chead, .cell, .verdict, .zlabel, .zsub"),
    );
    const nodeBoxes = nodeEls.map((el) => ({
      el: el,
      id:
        el.getAttribute("data-id") ||
        (el.matches(".zlabel, .zsub")
          ? 'zone title "' + el.textContent + '"'
          : el.className),
      b: box(el),
    }));

    function roundedPath(pts, rad) {
      let d = "M" + pts[0][0] + "," + pts[0][1];
      for (let i = 1; i < pts.length - 1; i++) {
        const p = pts[i - 1],
          c = pts[i],
          n = pts[i + 1];
        const l1 = Math.hypot(c[0] - p[0], c[1] - p[1]) || 1,
          l2 = Math.hypot(n[0] - c[0], n[1] - c[1]) || 1;
        const r = Math.min(rad, l1 / 2, l2 / 2);
        const ax = c[0] - ((c[0] - p[0]) / l1) * r,
          ay = c[1] - ((c[1] - p[1]) / l1) * r;
        const bx = c[0] + ((n[0] - c[0]) / l2) * r,
          by = c[1] + ((n[1] - c[1]) / l2) * r;
        d +=
          " L" + ax + "," + ay + " Q" + c[0] + "," + c[1] + " " + bx + "," + by;
      }
      const last = pts[pts.length - 1];
      return d + " L" + last[0] + "," + last[1];
    }
    function stroke(d, e) {
      const p = document.createElementNS(NS, "path");
      p.setAttribute("d", d);
      p.setAttribute("fill", "none");
      p.setAttribute("stroke", color(e.tone));
      p.setAttribute("stroke-width", String(e.weight || 4));
      p.setAttribute("stroke-linecap", "round");
      p.setAttribute("stroke-linejoin", "round");
      if (e.dashed) p.setAttribute("stroke-dasharray", "14 12");
      if (!e.noArrow) p.setAttribute("marker-end", marker(e.tone));
      svg.appendChild(p);
    }
    function setText(el, text) {
      String(text)
        .split("`")
        .forEach((part, i) => {
          if (!part) return;
          if (i % 2) {
            const c = document.createElement("code");
            c.textContent = part;
            el.appendChild(c);
          } else el.appendChild(document.createTextNode(part));
        });
    }
    // Labels are placed after every arrow is drawn, on the first side that is free of
    // boxes, other labels and other arrows.
    const labelReqs = [];
    const segs = [];
    function addLabel(text, x, y, align, e, seg) {
      if (text) labelReqs.push({ text: text, x: x, y: y, align: align, e: e, seg: seg });
    }
    function placeLabels() {
      const overlap = (p, q) =>
        p.x < q.r - 2 && p.r > q.x + 2 && p.y < q.b - 2 && p.b > q.y + 2;
      const onLine = (r, own) =>
        segs.some(
          (sg) =>
            sg !== own &&
            sg.pts.some((p, i) => {
              if (!i) return false;
              const q = sg.pts[i - 1];
              return (
                Math.max(p[0], q[0]) + 4 > r.x &&
                Math.min(p[0], q[0]) - 4 < r.r &&
                Math.max(p[1], q[1]) + 4 > r.y &&
                Math.min(p[1], q[1]) - 4 < r.b
              );
            }),
        );
      const placed = [];
      for (const q of labelReqs) {
        const el = document.createElement("div");
        el.className = "elabel" + (q.e && q.e.tone ? " tone-" + q.e.tone : "");
        setText(el, q.text);
        labelLayer.appendChild(el);
        const w = el.offsetWidth,
          h = el.offsetHeight;
        const order =
          q.align === "above"
            ? ["above", "below"]
            : q.align === "left-of"
              ? ["left-of", "right-of"]
              : ["right-of", "left-of"];
        let best = null;
        for (const al of order) {
          let left = q.x,
            top = q.y - h / 2;
          if (al === "right-of") left = q.x + 16;
          else if (al === "left-of") left = q.x - 16 - w;
          else if (al === "above") {
            left = q.x - w / 2;
            top = q.y - h - 10;
          } else {
            left = q.x - w / 2;
            top = q.y + 10;
          }
          left = Math.max(4, Math.min(left, W - w - 4));
          const r = { x: left, y: top, r: left + w, b: top + h };
          const line = onLine(r, q.seg);
          const bad = line || nodeBoxes.some((n) => overlap(r, n.b)) || placed.some((p) => overlap(r, p));
          if (!best || !bad) best = { r: r, bad: bad, line: line };
          if (!bad) break;
        }
        el.style.left = best.r.x + "px";
        el.style.top = best.r.y + "px";
        placed.push(best.r);
        if (best.line) warnings.push('label "' + q.text + '" sits on another arrow');
      }
    }
    // Segments that cross a box other than the edge's own ends become warnings.
    function checkCrossing(pts, e) {
      for (let i = 0; i < pts.length - 1; i++) {
        const x1 = Math.min(pts[i][0], pts[i + 1][0]),
          x2 = Math.max(pts[i][0], pts[i + 1][0]);
        const y1 = Math.min(pts[i][1], pts[i + 1][1]),
          y2 = Math.max(pts[i][1], pts[i + 1][1]);
        for (const n of nodeBoxes) {
          if (n.id === e.from || n.id === e.to) continue;
          if (
            n.el.closest('[data-id="' + CSS.escape(e.from) + '"]') ||
            n.el.closest('[data-id="' + CSS.escape(e.to) + '"]')
          )
            continue;
          const b = n.b;
          if (x2 > b.x + 2 && x1 < b.r - 2 && y2 > b.y + 2 && y1 < b.b - 2)
            warnings.push(
              "arrow " + e.from + " to " + e.to + " crosses " + n.id,
            );
        }
      }
    }

    // flow and map edges
    const edges = window.EDGES || [];
    const CLEAR = 16; // routing keeps arrows (and their heads) this far from other boxes
    // Each arrow leaves and enters a box at its own x, so two arrows never share a segment.
    const portsOut = {},
      portsIn = {};
    const portFree = (id, x, map) => !(map[id] || []).some((u) => Math.abs(u - x) < 36);
    const usePort = (id, x, map) => (map[id] = (map[id] || []).concat([x]));
    const allBoxes = nodeBoxes
      .filter((n) => n.el.matches(".node, .zlabel, .zsub"))
      .map((n) => n.b);
    const gutterR = Math.min(
      W - 10,
      Math.max.apply(null, allBoxes.map((b) => b.r).concat([0])) + 30,
    );
    const gutterL = Math.max(
      10,
      Math.min.apply(null, allBoxes.map((b) => b.x).concat([W])) - 30,
    );
    for (let e of edges) {
      const ae = byId(e.from),
        be = byId(e.to);
      if (!ae || !be) {
        warnings.push("edge " + e.from + " to " + e.to + ": node not found");
        continue;
      }
      const a = box(ae),
        b = box(be);
      let pts, lx, ly, align;
      if (b.y >= a.b - 2) {
        const lo = Math.max(a.x, b.x) + 40,
          hi = Math.min(a.r, b.r) - 40;
        const blocked = (x) =>
          allBoxes.some(
            (o) =>
              o !== a && x > o.x - CLEAR && x < o.r + CLEAR && o.y > a.b + 2 && o.b < b.y - 2,
          );
        if (lo <= hi) {
          // Prefer the narrower box's centre, then the nearest free x (zone titles, other boxes).
          const pref = Math.max(lo, Math.min(hi, a.w > b.w ? b.cx : a.cx));
          let x = pref;
          const ok = (v) => !blocked(v) && portFree(e.from, v, portsOut) && portFree(e.to, v, portsIn);
          for (let d = 0; d <= hi - lo; d += 12) {
            if (pref + d <= hi && ok(pref + d)) { x = pref + d; break; }
            if (pref - d >= lo && ok(pref - d)) { x = pref - d; break; }
          }
          if (ok(x)) {
            usePort(e.from, x, portsOut);
            usePort(e.to, x, portsIn);
            pts = [
              [x, a.b],
              [x, b.y - 4],
            ];
            lx = x;
            ly = (a.b + b.y) / 2;
            align = "right-of";
          }
        }
        if (!pts) {
          // Elbow: down from the source, across, down into the target, on free segments only.
          const same = (o, q) => Math.abs(o.x - q.x) < 1 && Math.abs(o.y - q.y) < 1;
          // A candidate segment must also stay clear of arrows already drawn (same axis, 14 px).
          const clearOfArrows = (x1, y1, x2, y2) =>
            !segs.some((sg) =>
              sg.pts.some((p, k) => {
                if (!k) return false;
                const q = sg.pts[k - 1];
                if (y1 === y2 && p[1] === q[1] && Math.abs(p[1] - y1) < 14)
                  return Math.min(Math.max(x1, x2), Math.max(p[0], q[0])) - Math.max(Math.min(x1, x2), Math.min(p[0], q[0])) > 0;
                if (x1 === x2 && p[0] === q[0] && Math.abs(p[0] - x1) < 14)
                  return Math.min(Math.max(y1, y2), Math.max(p[1], q[1])) - Math.max(Math.min(y1, y2), Math.min(p[1], q[1])) > 0;
                return false;
              }),
            );
          const segFree = (x1, y1, x2, y2) =>
            clearOfArrows(x1, y1, x2, y2) &&
            !allBoxes.some(
              (o) =>
                !same(o, a) &&
                !same(o, b) &&
                Math.max(x1, x2) > o.x - CLEAR &&
                Math.min(x1, x2) < o.r + CLEAR &&
                Math.max(y1, y2) > o.y + 2 &&
                Math.min(y1, y2) < o.b - 2,
            );
          const near = (c, lo2, hi2) => {
            const out = [];
            for (let d = 0; d <= hi2 - lo2; d += 12) {
              if (c + d <= hi2) out.push(c + d);
              if (d && c - d >= lo2) out.push(c - d);
            }
            return out;
          };
          const yms = [];
          for (let y = a.b + 36; y <= b.y - 36; y += 20) yms.push(y);
          yms.sort((p, q) => Math.abs(p - (a.b + b.y) / 2) - Math.abs(q - (a.b + b.y) / 2));
          search: for (const ym of yms) {
            for (const x2 of near(b.cx, b.x + 40, b.r - 40)) {
              if (!segFree(x2, ym, x2, b.y - 4) || !portFree(e.to, x2, portsIn)) continue;
              for (const x1 of near(a.cx, a.x + 40, a.r - 40)) {
                if (portFree(e.from, x1, portsOut) && segFree(x1, a.b, x1, ym) && segFree(x1, ym, x2, ym)) {
                  usePort(e.from, x1, portsOut);
                  usePort(e.to, x2, portsIn);
                  pts = [
                    [x1, a.b],
                    [x1, ym],
                    [x2, ym],
                    [x2, b.y - 4],
                  ];
                  lx = x2;
                  ly = (ym + b.y) / 2;
                  align = "right-of";
                  break search;
                }
              }
            }
          }
        }
        if (!pts) {
          {
            // Something sits in between: run down the gutter on the source's side.
            // A side route has no room for a label, so put those words in the target node.
            const yA = a.y + Math.min(60, a.h / 2),
              yB = b.y + Math.min(60, b.h / 2);
            const left = a.cx < W / 2;
            pts = left
              ? [
                  [a.x, yA],
                  [gutterL, yA],
                  [gutterL, yB],
                  [b.x - 4, yB],
                ]
              : [
                  [a.r, yA],
                  [gutterR, yA],
                  [gutterR, yB],
                  [b.r + 4, yB],
                ];
            if (e.label)
              warnings.push(
                "edge " +
                  e.from +
                  " to " +
                  e.to +
                  ' runs down the side, so its label "' +
                  e.label +
                  '" was dropped: put it in the target node',
              );
            e = Object.assign({}, e, { label: "" });
          }
        }
      } else if (b.b <= a.y + 2) {
        const yA = a.y + Math.min(60, a.h / 2),
          yB = b.y + Math.min(60, b.h / 2);
        pts = [
          [a.x, yA],
          [gutterL, yA],
          [gutterL, yB],
          [b.x - 4, yB],
        ];
        lx = gutterL;
        ly = (yA + yB) / 2;
        align = "right-of";
      } else {
        const y = Math.max(a.y, b.y) + 50;
        pts =
          a.cx < b.cx
            ? [
                [a.r, y],
                [b.x - 4, y],
              ]
            : [
                [a.x, y],
                [b.r + 4, y],
              ];
        lx = (pts[0][0] + pts[1][0]) / 2;
        ly = y;
        align = "above";
      }
      stroke(roundedPath(pts, 22), e);
      checkCrossing(pts, e);
      const seg = { e: e, pts: pts };
      segs.push(seg);
      addLabel(e.label, lx, ly, align, e, seg);
    }
    placeLabels();
    // Two arrows drawn on top of each other read as one: flag it.
    for (let i = 0; i < segs.length; i++)
      for (let j = i + 1; j < segs.length; j++)
        for (let p = 1; p < segs[i].pts.length; p++)
          for (let q = 1; q < segs[j].pts.length; q++) {
            const A0 = segs[i].pts[p - 1], A1 = segs[i].pts[p], B0 = segs[j].pts[q - 1], B1 = segs[j].pts[q];
            const vert = A0[0] === A1[0] && B0[0] === B1[0] && Math.abs(A0[0] - B0[0]) < 8;
            const horiz = A0[1] === A1[1] && B0[1] === B1[1] && Math.abs(A0[1] - B0[1]) < 8;
            const k = vert ? 1 : horiz ? 0 : -1;
            if (k < 0) continue;
            const lapLo = Math.max(Math.min(A0[k], A1[k]), Math.min(B0[k], B1[k]));
            const lapHi = Math.min(Math.max(A0[k], A1[k]), Math.max(B0[k], B1[k]));
            if (lapHi - lapLo > 10)
              warnings.push("arrows " + segs[i].e.from + " to " + segs[i].e.to + " and " + segs[j].e.from + " to " + segs[j].e.to + " run on top of each other");
          }

    // sequence lifelines and messages
    const lanes = Array.from(document.querySelectorAll(".lane")).map(box);
    const msgEls = Array.from(document.querySelectorAll(".msg"));
    if (lanes.length && msgEls.length) {
      const last = box(msgEls[msgEls.length - 1]);
      for (const l of lanes)
        stroke(
          roundedPath(
            [
              [l.cx, l.b],
              [l.cx, last.b + 24],
            ],
            0,
          ),
          { tone: "grey", dashed: true, noArrow: true, weight: 3 },
        );
      for (const el of msgEls) {
        if (el.classList.contains("self")) continue;
        const m = box(el);
        const from = lanes[Number(el.dataset.from)],
          to = lanes[Number(el.dataset.to)];
        const dir = to.cx > from.cx ? 1 : -1;
        const t = (el.className.match(/tone-(\w+)/) || [])[1];
        stroke(
          roundedPath(
            [
              [from.cx + dir * 6, m.b - 14],
              [to.cx - dir * 6, m.b - 14],
            ],
            0,
          ),
          {
            tone: t === "grey" ? "line" : t,
            dashed: el.classList.contains("dashed"),
          },
        );
      }
    }

    // overlap checks: labels against boxes and each other, and canvas overflow
    const labelEls = Array.from(document.querySelectorAll(".elabel, .mlabel"));
    const hit = (p, q) =>
      p.x < q.r - 2 && p.r > q.x + 2 && p.y < q.b - 2 && p.b > q.y + 2;
    labelEls.forEach((el, i) => {
      const lb = box(el);
      if (el.classList.contains("elabel")) {
        for (const n of nodeBoxes)
          if (hit(lb, n.b))
            warnings.push('label "' + el.textContent + '" overlaps ' + n.id);
      }
      for (let j = i + 1; j < labelEls.length; j++)
        if (hit(lb, box(labelEls[j])))
          warnings.push(
            'labels "' +
              el.textContent +
              '" and "' +
              labelEls[j].textContent +
              '" overlap',
          );
    });
    if (document.documentElement.scrollWidth > W + 1)
      warnings.push(
        "content is wider than the canvas (" +
          document.documentElement.scrollWidth +
          " > " +
          W +
          ")",
      );
    for (const n of nodeBoxes)
      if (n.el.scrollWidth > n.el.clientWidth + 1)
        warnings.push("text overflows " + n.id);
    // A word split across two lines is unreadable: flag it (breaks after - or / are fine).
    const textEls = Array.from(
      document.querySelectorAll(
        "h1, .subtitle, .label, .detail, .chip, .when, .bnote, .items li, .mlabel, .mdetail, .cell, .verdict, .zlabel, .zsub, .elabel",
      ),
    );
    for (const el of textEls) {
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      for (let t = walker.nextNode(); t; t = walker.nextNode()) {
        const re = /[^\s\/-]+[\/-]?/g;
        let m;
        while ((m = re.exec(t.data))) {
          const range = document.createRange();
          range.setStart(t, m.index);
          range.setEnd(t, m.index + m[0].length);
          const tops = new Set(
            Array.from(range.getClientRects()).map((r) => Math.round(r.top)),
          );
          if (tops.size > 1)
            warnings.push('the word "' + m[0] + '" breaks across lines: shorten it or give the box more room');
        }
      }
    }
    window.__digestWarnings = warnings;
    window.__digestReady = true;
  }

  (document.fonts ? document.fonts.ready : Promise.resolve())
    .then(run)
    .catch(function (err) {
      warnings.push("layout script failed: " + err);
      window.__digestWarnings = warnings;
      window.__digestReady = true;
    });
})();
