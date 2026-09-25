// Label UI, modelled on the ModuBOX label generator: pick drive + head (or nut/washer), type the size.
import { start } from "./engine.js";

const $ = (s) => document.querySelector(s);
say("Starting…");
let engine;
try { engine = await start((text) => say(text)); }
catch (e) { say(`Could not start: ${e.message}`, true); throw e; }
const B = engine.boot;
const press = (el, on) => { el.classList.toggle("on", on); el.setAttribute("aria-pressed", on); };
const state = { cat: "bolts", drive: null, head: null, nut: null, rivet: "rivets/dome", rmat: "alu", other: [], lenmode: "gf", queue: [], status: null,
  templates: B.templates, recent: B.recent, preview: null };

const NAMES = {
  "drive/hex-socket": "Allen / hex socket", "drive/torx": "Torx", "drive/torx-security": "Security Torx", "drive/phillips": "Phillips",
  "drive/pozidriv": "Pozidriv", "drive/robertson": "Robertson (square)", "drive/slotted": "Slotted", "drive/hex-external": "External hex",
  "drive/hex-flange": "Flange bolt (hex)", "drive/square-external": "External square",
  "head/countersunk": "Countersunk", "head/socket-cap": "Socket cap", "head/button": "Button", "head/pan": "Pan", "head/flange-pan": "Flange pan",
  "head/cheese": "Cheese / fillister", "head/hex": "Hex", "head/flange-hex": "Flange hex", "head/shoulder": "Shoulder", "head/truss": "Truss",
  "head/wafer": "Wafer", "head/set-screw": "Set screw (grub)", "head/wood-countersunk": "Wood, countersunk", "head/wood-pan": "Wood, pan", "head/wood-hex": "Wood, hex (lag)",
  "nuts/hex": "Hex nut", "nuts/square": "Square nut", "nuts/nyloc": "Nyloc nut", "nuts/flange": "Flange nut", "nuts/cap": "Cap (dome) nut", "nuts/wing": "Wing nut",
  "washers/flat": "Flat washer", "washers/fender": "Fender washer", "washers/split": "Spring washer",
  "washers/tooth-external": "External tooth lock washer", "washers/tooth-internal": "Internal tooth lock washer",
  "inserts/heat": "Heat-set insert", "inserts/wood": "Wood insert",
  "rivets/dome": "Blind rivet, dome head", "rivets/countersunk": "Blind rivet, countersunk", "rivets/large-flange": "Blind rivet, large flange",
  "rivets/nut": "Rivet nut (blind nut)",
};
const HEAD_ORDER = ["countersunk", "socket-cap", "button", "pan", "flange-pan", "cheese", "hex", "flange-hex", "shoulder", "truss", "wafer", "set-screw", "wood-countersunk", "wood-pan", "wood-hex"];
const RIVET_ORDER = ["dome", "countersunk", "large-flange", "nut"];
const RMAT = { alu: "Alu", steel: "Steel", a2: "A2", plast: "Alu/plast" };  // body material; standard rivets have a steel mandrel
const RIVET_STD = { dome: { alu: "ISO 15977", steel: "ISO 15979", a2: "ISO 15983" }, countersunk: { alu: "ISO 15978", steel: "ISO 15980", a2: "ISO 15984" } };
const NUT_DRILL = { M3: 5, M4: 6, M5: 7, M6: 9, M8: 11, M10: 13 };  // hole for round-body rivet nuts
const DRIVE_ORDER = ["hex-socket", "torx", "torx-security", "phillips", "pozidriv", "robertson", "slotted", "hex-external", "hex-flange", "square-external"];
const STANDARDS = {  // head|drive, or nut/washer id -> hint
  "socket-cap|hex-socket": "DIN 912 / ISO 4762 · socket head cap screw (SHCS)", "button|hex-socket": "ISO 7380 · button head socket screw",
  "countersunk|hex-socket": "DIN 7991 / ISO 10642 · countersunk socket screw", "hex|hex-external": "DIN 933 / ISO 4017 · hex bolt",
  "flange-hex|hex-flange": "DIN 6921 · hex flange bolt", "flange-hex|hex-external": "DIN 6921 · hex flange bolt",
  "pan|phillips": "DIN 7985 · pan head Phillips", "countersunk|phillips": "DIN 965 · countersunk Phillips",
  "pan|torx": "ISO 14583 · pan head Torx", "countersunk|torx": "ISO 14581 · countersunk Torx", "pan|pozidriv": "DIN 7985 · pan head Pozidriv",
  "countersunk|pozidriv": "DIN 965 · countersunk Pozidriv", "cheese|slotted": "DIN 84 · slotted cheese head", "pan|slotted": "DIN 85 · slotted pan head",
  "set-screw|hex-socket": "DIN 916 · set screw (grub screw)", "shoulder|hex-socket": "ISO 7379 · shoulder screw",
  "wood-countersunk|torx": "DIN 7997 · wood screw, countersunk", "wood-countersunk|pozidriv": "DIN 7997 · wood screw, countersunk",
  "wood-hex|hex-external": "DIN 571 · lag screw",
  "nuts/hex": "DIN 934 / ISO 4032 · hex nut", "nuts/nyloc": "DIN 985 · nyloc nut", "nuts/cap": "DIN 1587 · cap nut", "nuts/square": "DIN 557 · square nut",
  "nuts/flange": "DIN 6923 · flange nut", "nuts/wing": "DIN 315 · wing nut",
  "washers/flat": "DIN 125 · flat washer", "washers/fender": "DIN 9021 · fender washer", "washers/split": "DIN 127 · spring washer",
  "washers/tooth-external": "DIN 6798 A · external tooth lock washer", "washers/tooth-internal": "DIN 6798 J · internal tooth lock washer",
};

// ---- icon rows --------------------------------------------------------------------
function iconButton(id, rot) {
  const b = document.createElement("button"); b.type = "button"; b.dataset.icon = id; b.title = NAMES[id] || id;
  const i = document.createElement("span"); i.className = "ico" + (rot ? " rot" : ""); i.style.setProperty("--m", `url("${new URL(`icons/${id}.png`, location.href).href}")`);  // absolute: url() in a custom property resolves against the stylesheet
  b.setAttribute("aria-label", b.title); b.setAttribute("aria-pressed", false); b.appendChild(i); return b;
}
function fillRow(el, ids, onclick, rot) {
  el.innerHTML = "";
  for (const id of ids) { const b = iconButton(id, rot); b.onclick = () => onclick(id); el.appendChild(b); }
}
function ordered(folder, order) {
  const have = B.icons[folder] || [];
  return [...order.filter((n) => have.includes(n)), ...have.filter((n) => !order.includes(n))].map((n) => `${folder}/${n}`);
}
function buildRows() {
  fillRow($("#drives"), ordered("drive", DRIVE_ORDER), (id) => { state.drive = state.drive === id ? null : id; paint(); });
  fillRow($("#heads"), ordered("head", HEAD_ORDER), (id) => { state.head = state.head === id ? null : id; paint(); });
  const nuts = ["nuts", "washers", "inserts"].flatMap((f) => (B.icons[f] || []).map((n) => `${f}/${n}`));
  fillRow($("#nutsrow"), nuts, (id) => { state.nut = state.nut === id ? null : id; paint(); });
  fillRow($("#rivetsrow"), ordered("rivets", RIVET_ORDER), (id) => { state.rivet = state.rivet === id ? null : id; rivetForm(); });
  const other = Object.entries(B.icons).filter(([f]) => !["drive", "head", "nuts", "washers", "inserts", "rivets"].includes(f))
    .flatMap(([f, names]) => names.map((n) => (f === "." ? n : `${f}/${n}`)));
  fillRow($("#otherrow"), other, (id) => { const i = state.other.indexOf(id); i < 0 ? state.other.push(id) : state.other.splice(i, 1); paint(); });
  paint();
}
function paint() {
  const on = new Set([state.drive, state.head, state.nut, state.rivet, ...state.other]);
  document.querySelectorAll(".iconrow button").forEach((b) => press(b, on.has(b.dataset.icon)));
  const key = state.cat === "bolts" ? `${(state.head || "").replace("head/", "")}|${(state.drive || "").replace("drive/", "")}` : state.nut;
  const std = state.cat === "rivets" ? rivetHint() : STANDARDS[key];
  const h = $("#stdhint"); h.innerHTML = ""; h.hidden = !std;
  if (std) {
    h.textContent = std;
    if (state.cat === "rivets") return schedule();  // subtext is filled by the form already
    const b = document.createElement("button"); b.type = "button"; b.className = "small-btn"; b.textContent = "Use as subtext";
    b.onclick = () => { $("#sub").value = std.split(" · ")[0]; schedule(); }; h.appendChild(b);
  }
  schedule();
}
function icons() {
  if (!$("#showicons").checked) return [];
  if (state.cat === "bolts") return [state.drive, state.head].filter(Boolean);
  if (state.cat === "nuts") return state.nut ? [state.nut] : [];
  if (state.cat === "rivets") return state.rivet ? [state.rivet] : [];
  return state.other;
}
function setCategory(cat) {
  state.cat = cat;
  document.querySelectorAll("#cat button").forEach((b) => press(b, b.dataset.val === cat));
  for (const c of ["bolts", "nuts", "rivets", "other"]) $(`#grp-${c}`).hidden = c !== cat;
  paint();
}
$("#cat").onclick = (e) => { if (!e.target.dataset.val) return; setCategory(e.target.dataset.val); if (state.cat === "rivets") rivetForm(); };

// ---- rivets: structured form -> text + subtext ------------------------------------------
function segVal(id) { return $(`#${id} .on`)?.dataset.val; }
function segSet(id, v) { document.querySelectorAll(`#${id} button`).forEach((b) => press(b, b.dataset.val === v)); }
function rivetForm(fill = true) {
  const nut = state.rivet === "rivets/nut", seg = $("#rsize"), kind = nut ? "nut" : "dia";
  if (seg.dataset.kind !== kind) {
    seg.dataset.kind = kind; seg.innerHTML = "";
    for (const v of nut ? Object.keys(NUT_DRILL) : ["2.4", "3.2", "4.0", "4.8", "6.4"]) { const b = document.createElement("button"); b.type = "button"; b.dataset.val = v; b.textContent = v; seg.appendChild(b); }
    press(seg.children[3], true);  // M6 / 4.8, the common ones
  }
  $("#rsizelabel").textContent = nut ? "Thread" : "Diameter"; $("#rlenwrap").hidden = nut;
  const size = segVal("rsize"), mat = RMAT[state.rmat], L = +$("#rlen").value || 0;
  if (fill) {
    $("#text").value = nut ? size : `Ø${+size}×${L}`;
    $("#sub").value = nut ? `${mat} · drill ${NUT_DRILL[size]} mm` : `${mat} · grip ≈${grip(+size, L)}`;
  }
  paint();
}
// ponytail: grip range as length − diameter, within ~0.5 mm of maker tables for 3.2–6.4 mm; edit the subtext when the box says otherwise
function grip(d, L) { const max = Math.round((L - d + 0.5) * 2) / 2, min = Math.max(1, max - 2); return `${min}–${max}`; }
function rivetHint() {
  const t = (state.rivet || "").replace("rivets/", ""), size = segVal("rsize");
  if (!t) return "";
  if (t === "nut") return `Rivet nut (blindmutter), ${RMAT[state.rmat]} · drill a ${NUT_DRILL[size]} mm hole, set with a rivet-nut tool, then it takes an ${size} bolt`;
  const std = RIVET_STD[t]?.[state.rmat];
  return `${std ? std + " · " : ""}${NAMES["rivets/" + t]}, ${RMAT[state.rmat]} · drill Ø${(+size + 0.1).toFixed(1)} · grip = total thickness of the parts joined`;
}
$("#rmat").onclick = (e) => { if (!e.target.dataset.val) return; state.rmat = e.target.dataset.val; segSet("rmat", state.rmat); rivetForm(); };
$("#rsize").onclick = (e) => { if (!e.target.dataset.val) return; segSet("rsize", e.target.dataset.val); rivetForm(); };
$("#rlen").oninput = () => rivetForm();
$("#showicons").onchange = schedule;
$("#iconfile").onchange = async (e) => {
  const f = e.target.files[0]; if (!f) return;
  let d;
  try { d = await engine.uploadIcon(f); } catch (e) { return say(e.message, true); }
  B.icons = d.icons; buildRows(); state.other.push(d.icon); paint();
};

// ---- tape / width / length ---------------------------------------------------------
const tapeSeg = $("#tape");
function buildTapes(tapes) {
  const was = tapeSeg.querySelector(".on")?.dataset.val;
  tapeSeg.innerHTML = "";
  for (const mm of tapes) { const b = document.createElement("button"); b.type = "button"; b.dataset.val = mm; b.textContent = (mm === 4 ? "3.5" : mm) + " mm"; tapeSeg.appendChild(b); }
  if (was) setTape(tapes.includes(+was) ? was : tapes[0]);
}
buildTapes(B.tapes);
function tape() { return +tapeSeg.querySelector(".on").dataset.val; }
function setTape(mm) { tapeSeg.querySelectorAll("button").forEach((b) => press(b, +b.dataset.val === +mm)); mismatch(); schedule(); }
tapeSeg.onclick = (e) => { if (!e.target.dataset.val) return; setTape(e.target.dataset.val); renderQueue(); };
function units() { return +$("#units").value; }
function setUnits(u) { $("#units").value = Math.min(8, Math.max(0.5, u)); $("#wlabel").textContent = `${units()} wide`; schedule(); }
$("#units").oninput = () => setUnits(units());
$("#wminus").onclick = () => setUnits(units() - 0.5);
$("#wplus").onclick = () => setUnits(units() + 0.5);
$("#lenmode").onclick = (e) => { if (!e.target.dataset.val) return; state.lenmode = e.target.dataset.val;
  document.querySelectorAll("#lenmode button").forEach((b) => press(b, b.dataset.val === state.lenmode)); schedule(); };

// ---- spec <-> form ----------------------------------------------------------------
function spec() {
  return { lines: [$("#text").value, $("#sub").value].filter((t) => t.trim()), icons: icons(), tape_mm: tape(),
    units: state.lenmode === "gf" ? units() : null, font_size: +$("#fontsize").value || null, align: "left", layout: "side", margin_mm: 0.6, gap_mm: 0.8 };
}
function options() { return { margin_mm: B.defaults.margin_mm, half_cut: true, chain: $("#chain").checked, copies: 1 }; }
function load(s) {
  $("#text").value = s.lines?.[0] ?? s.line1 ?? ""; $("#sub").value = s.lines?.[1] ?? s.line2 ?? "";
  $("#fontsize").value = s.font_size ?? "";
  if (s.tape_mm) setTape(s.tape_mm);
  state.lenmode = s.units ? "gf" : "auto"; if (s.units) setUnits(s.units);
  document.querySelectorAll("#lenmode button").forEach((b) => press(b, b.dataset.val === state.lenmode));
  const ids = s.icons ?? (s.icon ? [s.icon] : []);
  state.drive = ids.find((i) => i.startsWith("drive/")) || null;
  state.head = (ids.find((i) => i.startsWith("head/")) || null)?.replace("@90", "") ?? null;
  state.nut = ids.find((i) => /^(nuts|washers|inserts)\//.test(i)) || null;
  state.rivet = ids.find((i) => i.startsWith("rivets/")) || state.rivet;
  state.other = ids.filter((i) => !/^(drive|head|nuts|washers|inserts|rivets)\//.test(i));
  $("#showicons").checked = ids.length > 0 || !s.lines?.length;
  setCategory(state.nut ? "nuts" : ids.some((i) => i.startsWith("rivets/")) ? "rivets" : state.other.length ? "other" : "bolts");
  if (state.cat === "rivets") rivetForm(false);
}

// ---- preview / status ---------------------------------------------------------------
let timer;
function schedule() { clearTimeout(timer); timer = setTimeout(preview, 150); }
async function preview() {
  try {
    const r = await engine.preview({ labels: [spec()], options: options() });
    const [w, h] = r.dots.split("x").map(Number);
    const [dx, dy] = r.dpi.split("x").map(Number);
    const img = $("#preview"); img.src = URL.createObjectURL(r.blob);
    const wmm = (w * 25.4) / dx, hmm = (h * 25.4) / dy;
    img.style.setProperty("--wmm", wmm);
    $("#dims").textContent = `${wmm.toFixed(1)} × ${hmm.toFixed(1)} mm · ${w} × ${h} dots · ${tape()} mm tape · shown enlarged`;
    say("");
  } catch (e) { say(e.message, true); }
}
function say(text, bad) {
  const m = $("#msg"); m.hidden = !text; m.textContent = text; m.classList.toggle("bad", !!bad);
  if (bad) m.scrollIntoView({ behavior: "smooth", block: "center" });  // the hero is off-screen when pressing a button at the bottom
}
async function poll() {
  try {
    const s = await engine.status(); state.status = s;
    const el = $("#status");
    if (!s.connected) { el.textContent = "not connected"; el.dataset.state = "error"; }
    else if (s.errors.length) { el.textContent = s.errors.join(", "); el.dataset.state = "error"; }
    else { el.textContent = `${s.tape_mm ? s.tape_mm + " mm " + s.media : "no tape"}${s.busy ? " · printing" : ""}${s.backend === "mock" ? " (mock)" : ""}`; el.dataset.state = "ok"; }
    $("#a-status").textContent = el.textContent; $("#a-status").dataset.state = el.dataset.state;
    if (engine.mode === "local" && !s.connected) { el.textContent = "no printer"; el.dataset.state = ""; }
    mismatch();
  } catch (e) { $("#status").textContent = "offline"; $("#status").dataset.state = "error"; $("#a-status").textContent = e.message; }
}
function mismatch() {
  const s = state.status, want = tape(), b = $("#mismatch");
  const bad = s && s.connected && s.tape_mm && s.tape_mm !== want;
  b.hidden = !bad;
  if (bad) {
    b.textContent = `Design is for ${want} mm tape, the printer has ${s.tape_mm} mm loaded.`;
    const fix = document.createElement("button"); fix.className = "small-btn"; fix.textContent = `Use ${s.tape_mm} mm`; fix.onclick = () => setTape(s.tape_mm); b.appendChild(fix);
  }
  $("#print").disabled = !!bad; $("#printbatch").disabled = !!bad || !state.queue.length;
}

// ---- print / batch / templates ------------------------------------------------------
async function doPrint(labels, opts) {
  say("printing…");
  try { say(await engine.print({ labels, options: opts || options() })); refreshLists(); poll(); }
  catch (e) { say(e.message, true); }
}
$("#print").onclick = () => doPrint([spec()]);
const plate = () => state.queue.map((s) => ({ ...s, tape_mm: tape() }));  // one strip = one tape: the selected one, whatever each label was added with
$("#printbatch").onclick = () => state.queue.length && doPrint(plate());
$("#queue").onclick = () => { state.queue.push(spec()); renderQueue(); };
$("#clearbatch").onclick = () => { state.queue = []; renderQueue(); };
$("#sortbatch").onclick = () => { state.queue.sort((a, b) => (a.units || 0) - (b.units || 0) || (a.lines[0] || "").localeCompare(b.lines[0] || "", undefined, { numeric: true })); renderQueue(); };
$("#parse").onclick = async () => {
  try { state.queue.push(...await engine.parse($("#batchtext").value)); renderQueue(); }
  catch (e) { say(e.message, true); }
};
function describe(s) {
  const len = s.units ? `${s.units} wide` : s.length_mm ? `${s.length_mm} mm` : "fit";
  const ic = (s.icons?.length ? s.icons : s.icon ? [s.icon] : []).map((i) => NAMES[i.replace("@90", "")] || i).join(" + ") || "no icon";
  return `${(s.lines || [s.line1, s.line2]).filter(Boolean).join(" / ") || "(blank)"} · ${ic} · ${len}`;
}
async function renderQueue() {
  const ol = $("#queuelist"); ol.innerHTML = "";
  state.queue.forEach((s, i) => {
    const li = document.createElement("li");
    const t = rowText(describe(s), () => load(s));
    const x = dropBtn("Remove from batch"); x.onclick = () => { state.queue.splice(i, 1); renderQueue(); };
    li.append(t, x); ol.appendChild(li);
  });
  $("#qhint").hidden = state.queue.length > 0; $("#qcount").textContent = state.queue.length ? `${state.queue.length} labels` : "";
  $("#printbatch").disabled = !state.queue.length || !$("#mismatch").hidden;
  const img = $("#strip"); img.hidden = state.queue.length < 1;
  if (state.queue.length) {
    try { img.src = URL.createObjectURL((await engine.preview({ labels: plate(), options: options() })).blob); }
    catch (e) { say(e.message, true); }
  }
}
$("#save").onclick = async () => {
  const name = prompt("Template name", $("#text").value); if (!name) return;
  state.templates = await engine.saveTemplate({ name, label: spec() }); renderLists();
};
async function refreshLists() {
  state.templates = await engine.templates();
  state.recent = await engine.recent(); renderLists();
}
function rowText(text, onpick) {  // the row's text loads it into the form, by click or Enter
  const t = document.createElement("span"); t.className = "t"; t.tabIndex = 0; t.setAttribute("role", "button"); t.textContent = text;
  t.onclick = onpick; t.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onpick(); } };
  return t;
}
function smallBtn(text, onclick) { const b = document.createElement("button"); b.type = "button"; b.className = "small-btn"; b.textContent = text; b.onclick = onclick; return b; }
function dropBtn(label) { const b = document.createElement("button"); b.type = "button"; b.className = "drop"; b.textContent = "✕"; b.setAttribute("aria-label", label); return b; }
function renderLists() {
  const tl = $("#templates"); tl.innerHTML = "";
  for (const t of state.templates) {
    const li = document.createElement("li");
    const s = rowText(`${t.name} — ${describe(t.label)}`, () => load(t.label));
    const p = smallBtn("Print", () => doPrint([t.label]));
    const x = dropBtn(`Delete template ${t.name}`);
    x.onclick = async () => { state.templates = await engine.deleteTemplate(t.name); renderLists(); };
    li.append(s, p, x); tl.appendChild(li);
  }
  const rl = $("#recent"); rl.innerHTML = "";
  for (const r of state.recent) {
    const li = document.createElement("li"), req = r.request, n = req.labels.length;
    const s = rowText(`${new Date(r.ts * 1000).toLocaleString()} — ${describe(req.labels[0])}${n > 1 ? ` (+${n - 1})` : ""}`, () => load(req.labels[0]));
    const p = smallBtn("Reprint", () => doPrint(req.labels, req.options));
    li.append(s, p); rl.appendChild(li);
  }
  $("#tempty").hidden = state.templates.length > 0; $("#rempty").hidden = state.recent.length > 0;
}

// ---- connection (no server: this browser drives the printer) -------------------------------
function about() {
  $("#a-mode").textContent = engine.mode === "server" ? "teip server" : "in this browser";
  $("#a-printer").textContent = engine.mode === "server" ? B.printer : `${engine.model}${engine.connection ? ` over ${engine.connection}` : ""}`;
}
function connectionUi() {
  const sec = $("#connection"); sec.hidden = engine.mode === "server";
  about();
  if (sec.hidden) return;
  const on = !!engine.connection;
  sec.classList.toggle("callout", !on);
  $("#connusb").hidden = on || !engine.usb; $("#connbt").hidden = on || !engine.serial; $("#disconnect").hidden = !on;
  $("#connhelp").textContent = on ? `${engine.model} connected over ${engine.connection}.`
    : engine.usb ? "Plug the printer in and press Connect. On Windows the printer needs the WinUSB driver (see the README); Linux needs a udev rule."
    : "This browser can't reach printers directly. Use Chrome or Edge on a computer, or open a teip server on your network. You can still design labels here.";
}
async function connect(how) {
  try { await engine[how](); say(""); } catch (e) { if (e.name !== "NotFoundError") say(e.message, true); }  // NotFoundError: the picker was closed
  connectionUi(); poll();
}
if (engine.mode === "local") {
  const sel = $("#model");
  for (const m of engine.models) { const o = document.createElement("option"); o.value = o.textContent = m.model; sel.appendChild(o); }
  sel.value = engine.model;
  sel.onchange = () => { engine.setModel(sel.value); buildTapes(engine.boot.tapes); connectionUi(); schedule(); };
  $("#connusb").onclick = () => connect("connectUsb");
  $("#connbt").onclick = () => connect("connectSerial");
  $("#disconnect").onclick = async () => { await engine.disconnect(); connectionUi(); poll(); };
  $("#uploadwrap").hidden = true;  // uploads need a server to keep them
}
$("#gfhelp").textContent = `Gridfinity = ${B.defaults.gridfinity_base_mm} mm for 1 wide, + ${B.defaults.gridfinity_unit_mm} mm per extra unit.`;
connectionUi();

// ---- init -------------------------------------------------------------------------
setTape(B.defaults.tape_mm);
buildRows(); renderLists();
document.querySelectorAll("#text, #sub, #fontsize").forEach((el) => el.addEventListener("input", schedule));
state.drive = "drive/hex-socket"; state.head = "head/countersunk"; rivetForm(false);
const hash = location.hash.slice(1);  // #rivets opens on that category
if (hash && $(`#grp-${hash}`)) { setCategory(hash); if (hash === "rivets") rivetForm(); }
$("#aboutbtn").onclick = () => $("#about").showModal();
$("#aboutclose").onclick = () => $("#about").close();
poll(); setInterval(poll, 5000);
