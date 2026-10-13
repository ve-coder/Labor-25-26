/* Blockprogrammierung für den Ablauf (Blockly).
 * Eigene Blöcke für Zylinder, Motoren, Kamera und Ablauf.
 * Das Programm wird als einfaches JSON (siehe app/machine.py) gespeichert
 * und ausgeführt – Blockly ist nur der Editor.
 */
(function () {
  "use strict";

  const C = {
    cyl: "#1D9E75",
    motor: "#7F77DD",
    cam: "#BA7517",
    flow: "#888780",
    start: "#D85A30",
  };

  const SPEEDS = [
    ["Lösen", "solve"],
    ["Scan", "scan"],
    ["Umsetzen", "regrip"],
    ["Hand", "manual"],
    ["eigene:", "custom"],
  ];
  const ANGLES = [["+90°", "90"], ["−90°", "-90"], ["180°", "180"], ["−180°", "-180"]];

  // Zahlenfeld für die Geschwindigkeit nur bei „eigene:“ anzeigen
  Blockly.Extensions.register("speed_toggle", function () {
    const block = this;
    const update = (v) => {
      const num = block.getField("SPEEDNUM");
      if (num) {
        num.setVisible(v === "custom");
        if (block.rendered) block.queueRender ? block.queueRender() : block.render();
      }
      return v;
    };
    this.getField("SPEED").setValidator(update);
    update(this.getFieldValue("SPEED"));
  });

  Blockly.common.defineBlocksWithJsonArray([
    {
      type: "cs_start",
      message0: "Programmstart",
      nextStatement: null,
      colour: C.start,
      tooltip: "Alles, was unter diesem Block hängt, wird beim Start ausgeführt.",
    },
    {
      type: "cs_cylinder",
      message0: "Zylinder %1 %2",
      args0: [
        { type: "field_dropdown", name: "TARGET", options: [["U", "U"], ["D", "D"], ["L + R", "LR"], ["F + B", "FB"]] },
        { type: "field_dropdown", name: "ACTION", options: [["ausfahren", "extend"], ["einfahren", "retract"]] },
      ],
      previousStatement: null,
      nextStatement: null,
      colour: C.cyl,
      tooltip: "Schaltet das Relais und wartet, bis die Reed-Kontakte die Endlage melden.",
    },
    {
      type: "cs_motor",
      message0: "Motor %1 drehen %2 Tempo %3 %4",
      args0: [
        { type: "field_dropdown", name: "SIDE", options: [["U", "U"], ["D", "D"], ["L", "L"], ["R", "R"], ["F", "F"], ["B", "B"]] },
        { type: "field_dropdown", name: "ANGLE", options: ANGLES },
        { type: "field_dropdown", name: "SPEED", options: SPEEDS },
        { type: "field_number", name: "SPEEDNUM", value: 400, min: 10, max: 5000, precision: 10 },
      ],
      previousStatement: null,
      nextStatement: null,
      colour: C.motor,
      tooltip: "Ein Motor dreht. Hält nur dieser Greifer den Würfel, dreht der ganze Würfel mit (z. B. D beim Umsetzen). Die Zahl gilt nur bei „eigene“ (Schritte/s).",
      extensions: ["speed_toggle"],
    },
    {
      type: "cs_pair",
      message0: "L + R gemeinsam drehen %1 Tempo %2 %3",
      args0: [
        { type: "field_dropdown", name: "ANGLE", options: ANGLES },
        { type: "field_dropdown", name: "SPEED", options: SPEEDS },
        { type: "field_number", name: "SPEEDNUM", value: 400, min: 10, max: 5000, precision: 10 },
      ],
      previousStatement: null,
      nextStatement: null,
      colour: C.motor,
      tooltip: "L und R drehen gegensinnig – der ganze Würfel dreht um die L-R-Achse. Nur erlaubt, wenn U, D, F und B eingefahren sind.",
      extensions: ["speed_toggle"],
    },
    {
      type: "cs_scan",
      message0: "Unterseite scannen (warten bis 9/9)",
      previousStatement: null,
      nextStatement: null,
      colour: C.cam,
      tooltip: "Die Kamera in D nimmt die Unterseite auf, sobald alle 9 Felder stabil erkannt sind. Welche Würfelseite gerade unten liegt, weiß das Programm selbst.",
    },
    {
      type: "cs_compute",
      message0: "Lösung berechnen",
      previousStatement: null,
      nextStatement: null,
      colour: C.cam,
      tooltip: "Prüft die 54 Farben und berechnet die Zugfolge (Kociemba).",
    },
    {
      type: "cs_execute",
      message0: "Lösung ausführen Tempo %1 %2",
      args0: [
        { type: "field_dropdown", name: "SPEED", options: SPEEDS },
        { type: "field_number", name: "SPEEDNUM", value: 1200, min: 10, max: 5000, precision: 10 },
      ],
      previousStatement: null,
      nextStatement: null,
      colour: C.cam,
      tooltip: "Führt die berechneten Züge aus. Alle Greifer müssen ausgefahren sein. „Lösen“ folgt dem Regler Lösegeschwindigkeit – auch während des Lösens.",
      extensions: ["speed_toggle"],
    },
    {
      type: "cs_repeat",
      message0: "Wiederhole %1 ×",
      args0: [{ type: "field_number", name: "TIMES", value: 4, min: 1, max: 100, precision: 1 }],
      message1: "%1",
      args1: [{ type: "input_statement", name: "DO" }],
      previousStatement: null,
      nextStatement: null,
      colour: C.flow,
    },
    {
      type: "cs_wait",
      message0: "Warte %1 s",
      args0: [{ type: "field_number", name: "SECONDS", value: 0.5, min: 0, max: 600, precision: 0.1 }],
      previousStatement: null,
      nextStatement: null,
      colour: C.flow,
    },
    {
      type: "cs_beep",
      message0: "Buzzer %1",
      args0: [{ type: "field_dropdown", name: "PATTERN", options: [["kurz", "kurz"], ["ok", "ok"], ["fertig", "fertig"], ["Fehler", "fehler"]] }],
      previousStatement: null,
      nextStatement: null,
      colour: C.flow,
    },
    {
      type: "cs_home",
      message0: "Grundstellung (U → F+B → L+R → D einfahren)",
      previousStatement: null,
      nextStatement: null,
      colour: C.cyl,
    },
  ]);

  const toolbox = {
    kind: "categoryToolbox",
    contents: [
      { kind: "category", name: "Zylinder", colour: C.cyl, contents: [
        { kind: "block", type: "cs_cylinder" },
        { kind: "block", type: "cs_cylinder", fields: { ACTION: "retract" } },
        { kind: "block", type: "cs_home" },
      ] },
      { kind: "category", name: "Motoren", colour: C.motor, contents: [
        { kind: "block", type: "cs_motor" },
        { kind: "block", type: "cs_motor", fields: { SIDE: "D", SPEED: "regrip" } },
        { kind: "block", type: "cs_pair", fields: { SPEED: "scan" } },
      ] },
      { kind: "category", name: "Kamera & Lösen", colour: C.cam, contents: [
        { kind: "block", type: "cs_scan" },
        { kind: "block", type: "cs_compute" },
        { kind: "block", type: "cs_execute" },
      ] },
      { kind: "category", name: "Ablauf", colour: C.flow, contents: [
        { kind: "block", type: "cs_start" },
        { kind: "block", type: "cs_repeat" },
        { kind: "block", type: "cs_wait" },
        { kind: "block", type: "cs_beep" },
      ] },
    ],
  };

  function makeTheme() {
    const light = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
    return Blockly.Theme.defineTheme("cubesolver-" + (light ? "light" : "dark"), {
      base: Blockly.Themes.Classic,
      componentStyles: light
        ? { workspaceBackgroundColour: "#faf9f6", toolboxBackgroundColour: "#f1efe8", toolboxForegroundColour: "#23221f",
            flyoutBackgroundColour: "#ebe9e2", flyoutForegroundColour: "#23221f", flyoutOpacity: 1,
            scrollbarColour: "#b4b2a9", insertionMarkerColour: "#000", insertionMarkerOpacity: 0.3 }
        : { workspaceBackgroundColour: "#181a1d", toolboxBackgroundColour: "#1e2125", toolboxForegroundColour: "#e9e7e1",
            flyoutBackgroundColour: "#262a2f", flyoutForegroundColour: "#e9e7e1", flyoutOpacity: 1,
            scrollbarColour: "#4a4f55", insertionMarkerColour: "#fff", insertionMarkerOpacity: 0.3 },
      fontStyle: { family: "system-ui, sans-serif", size: 11 },
    });
  }

  // ------------------------------------------------------------ Blockly -> JSON
  function speedOf(block) {
    const s = block.getFieldValue("SPEED");
    return s === "custom" ? Number(block.getFieldValue("SPEEDNUM")) : s;
  }

  function chainToAst(block) {
    const out = [];
    for (let b = block; b; b = b.getNextBlock()) {
      if (!b.isEnabled()) continue;
      out.push(blockToAst(b));
    }
    return out;
  }

  function blockToAst(b) {
    const id = b.id;
    switch (b.type) {
      case "cs_cylinder": return { id, type: "cylinder", target: b.getFieldValue("TARGET"), action: b.getFieldValue("ACTION") };
      case "cs_motor": return { id, type: "motor", side: b.getFieldValue("SIDE"), angle: Number(b.getFieldValue("ANGLE")), speed: speedOf(b) };
      case "cs_pair": return { id, type: "pair", angle: Number(b.getFieldValue("ANGLE")), speed: speedOf(b) };
      case "cs_scan": return { id, type: "scan" };
      case "cs_compute": return { id, type: "compute" };
      case "cs_execute": return { id, type: "execute", speed: speedOf(b) };
      case "cs_repeat": return { id, type: "repeat", times: Number(b.getFieldValue("TIMES")), body: chainToAst(b.getInputTargetBlock("DO")) };
      case "cs_wait": return { id, type: "wait", seconds: Number(b.getFieldValue("SECONDS")) };
      case "cs_beep": return { id, type: "beep", pattern: b.getFieldValue("PATTERN") };
      case "cs_home": return { id, type: "home" };
      default: throw new Error("Unbekannter Block " + b.type);
    }
  }

  // ------------------------------------------------------------ JSON -> Blockly
  let uid = 0;
  function speedFields(speed, fallback) {
    if (typeof speed === "number") return { SPEED: "custom", SPEEDNUM: speed };
    return { SPEED: speed || fallback };
  }

  function nodeToBlock(n) {
    const id = n.id || "b" + Date.now().toString(36) + (uid++);
    switch (n.type) {
      case "cylinder": return { type: "cs_cylinder", id, fields: { TARGET: n.target, ACTION: n.action || "extend" } };
      case "motor": return { type: "cs_motor", id, fields: { SIDE: n.side, ANGLE: String(n.angle || 90), ...speedFields(n.speed, "manual") } };
      case "pair": return { type: "cs_pair", id, fields: { ANGLE: String(n.angle || 90), ...speedFields(n.speed, "scan") } };
      case "scan": return { type: "cs_scan", id };
      case "compute": return { type: "cs_compute", id };
      case "execute": return { type: "cs_execute", id, fields: speedFields(n.speed, "solve") };
      case "repeat": {
        const blk = { type: "cs_repeat", id, fields: { TIMES: n.times || 1 } };
        const body = chainToBlocks(n.body || []);
        if (body) blk.inputs = { DO: { block: body } };
        return blk;
      }
      case "wait": return { type: "cs_wait", id, fields: { SECONDS: n.seconds ?? 1 } };
      case "beep": return { type: "cs_beep", id, fields: { PATTERN: n.pattern || "kurz" } };
      case "home": return { type: "cs_home", id };
      default: throw new Error("Unbekannter Block " + n.type);
    }
  }

  function chainToBlocks(nodes) {
    let first = null;
    let prev = null;
    for (const n of nodes) {
      const blk = nodeToBlock(n);
      if (!first) first = blk;
      if (prev) prev.next = { block: blk };
      prev = blk;
    }
    return first;
  }

  // ------------------------------------------------------------ öffentliche API
  let workspace = null;

  window.CubeBlocks = {
    init(el) {
      workspace = Blockly.inject(el, {
        toolbox,
        media: "/static/vendor/media/",
        theme: makeTheme(),
        renderer: "zelos",
        trashcan: true,
        zoom: { controls: true, wheel: true, startScale: 0.75, maxScale: 2, minScale: 0.3 },
        move: { scrollbars: true, drag: true, wheel: false },
        grid: { spacing: 24, length: 2, colour: "rgba(128,128,128,.18)", snap: true },
      });
      return workspace;
    },
    load(program) {
      const chain = chainToBlocks(program.blocks || []);
      const start = { type: "cs_start", id: "start", x: 30, y: 30 };
      if (chain) start.next = { block: chain };
      Blockly.Events.disable();
      try {
        workspace.clear();
        Blockly.serialization.workspaces.load({ blocks: { languageVersion: 0, blocks: [start] } }, workspace);
      } finally {
        Blockly.Events.enable();
      }
    },
    toProgram() {
      const starts = workspace.getTopBlocks(true).filter((b) => b.type === "cs_start");
      if (starts.length === 0) throw new Error("Es fehlt der Block „Programmstart“");
      if (starts.length > 1) throw new Error("Es darf nur einen Block „Programmstart“ geben");
      return { blocks: chainToAst(starts[0].getNextBlock()) };
    },
    highlight(id) {
      if (!workspace) return;
      workspace.highlightBlock(id || null);
    },
    resize() {
      if (workspace) Blockly.svgResize(workspace);
    },
    onChange(fn) {
      workspace.addChangeListener((e) => { if (!e.isUiEvent) fn(e); });
    },
  };
})();
