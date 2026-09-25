// Two engines behind one interface. The page asks for api/boot: a teip server answers and the
// server renders and prints (server mode). No server (GitHub Pages): the label code runs here
// under Pyodide and the page drives the printer itself over WebUSB or Web Serial.

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";

async function http(path, body, method) {
  const r = await fetch(path, body === undefined ? { method: method || "GET" } :
    { method: method || "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
  if (!r.ok) { let d = ""; try { d = (await r.json()).detail; } catch {} throw new Error(d || r.statusText); }
  return r;
}

export async function start(onprogress) {
  try {
    const r = await fetch("api/boot");
    if (r.ok) return serverEngine(await r.json());
  } catch {}
  return localEngine(onprogress);
}

// ---- server mode: everything goes to the teip server ------------------------------------------
function serverEngine(boot) {
  return {
    mode: "server", boot,
    async preview(req) {
      const r = await http("api/preview", req);
      return { blob: await r.blob(), dots: r.headers.get("X-Dots"), dpi: r.headers.get("X-Dpi") };
    },
    async print(req) { return (await (await http("api/print", req)).json()).result; },
    async status() { return (await http("api/status")).json(); },
    async parse(text) { return (await (await http("api/batch/parse", { text })).json()).labels; },
    async templates() { return (await http("api/templates")).json(); },
    async saveTemplate(t) { return (await http("api/templates", t)).json(); },
    async deleteTemplate(name) { return (await http(`api/templates/${encodeURIComponent(name)}`, undefined, "DELETE")).json(); },
    async recent() { return (await http("api/recent")).json(); },
    async uploadIcon(file) {
      const fd = new FormData(); fd.append("file", file);
      const r = await fetch("api/icons", { method: "POST", body: fd });
      if (!r.ok) throw new Error((await r.json()).detail);
      return r.json();
    },
  };
}

// ---- local mode: Pyodide renders, WebUSB / Web Serial print ------------------------------------
const store = {  // per-browser templates and history. Storage can be missing or throw (private windows)
  get(k, d) { try { return JSON.parse(localStorage.getItem(`teip.${k}`)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(`teip.${k}`, JSON.stringify(v)); } catch {} },
};

async function loadPython(onprogress) {
  onprogress("Loading the label renderer. The first visit downloads about 15 MB; later visits use the cache.");
  const { loadPyodide } = await import(PYODIDE + "pyodide.mjs");
  const py = await loadPyodide({ indexURL: PYODIDE });
  await py.loadPackage(["pillow", "pydantic", "pyyaml"]);
  const files = await (await fetch("py/manifest.json")).json();
  await Promise.all(files.map(async (f) => {
    const data = new Uint8Array(await (await fetch(`py/${f}`)).arrayBuffer());
    py.FS.mkdirTree(`/lib/${f.slice(0, f.lastIndexOf("/"))}`);
    py.FS.writeFile(`/lib/${f}`, data);
  }));
  py.runPython("import sys; sys.path.insert(0, '/lib')");
  return { py, mod: py.pyimport("teip.browser") };
}

async function localEngine(onprogress) {
  const [{ py, mod }, index] = await Promise.all([loadPython(onprogress), fetch("icons/index.json").then((r) => r.json())]);
  const models = JSON.parse(mod.models());
  const defaults = JSON.parse(mod.defaults());
  let model = store.get("model", "PT-E560BT");
  if (!models.some((m) => m.model === model)) model = models[0].model;
  const info = () => models.find((m) => m.model === model);
  let printer = null;  // a Printer while one is connected

  async function icons(req) {  // the renderer reads icon files from /icons: fetch the ones this request uses
    for (const id of new Set(req.labels.flatMap((l) => [...(l.icons || []), l.icon].filter(Boolean)).map((i) => i.split("@")[0]))) {
      const file = index.files[id];
      if (!file) throw new Error(`icon not found: ${id}`);
      if (py.FS.analyzePath(`/icons/${file}`).exists) continue;
      py.FS.mkdirTree(`/icons/${file.slice(0, file.lastIndexOf("/"))}`);
      py.FS.writeFile(`/icons/${file}`, new Uint8Array(await (await fetch(`icons/${file}`)).arrayBuffer()));
    }
  }
  const call = (fn) => { try { return fn(); } catch (e) { throw new Error(pyError(e)); } };

  const engine = {
    mode: "local", models,
    get model() { return model; },
    setModel(m) { model = m; store.set("model", m); if (printer) printer.model = m; },
    get boot() {
      const m = info();
      return { icons: index.icons, tapes: m.tapes, printer: model, dpi: m.dpi, defaults, templates: store.get("templates", []), recent: store.get("recent", []) };
    },
    get connection() { return printer && printer.link.kind; },
    async preview(req) {
      await icons(req);
      const tape = printer?.last?.tape_mm || req.labels[0]?.tape_mm || defaults.tape_mm;
      const out = call(() => mod.preview(model, JSON.stringify(req), tape));
      const [png, dots, dpi] = out.toJs(); out.destroy();
      return { blob: new Blob([png], { type: "image/png" }), dots, dpi };
    },
    async print(req) {
      if (!printer) throw new Error("No printer connected. Connect one over USB or Bluetooth first.");
      await icons(req);
      const result = await printer.print(req);
      const recent = store.get("recent", []);
      recent.unshift({ ts: Math.floor(Date.now() / 1000), result, request: req });
      store.set("recent", recent.slice(0, 30));
      return result;
    },
    async status() {
      const base = { backend: printer ? printer.link.kind : "none", printer: model, connected: false, tape_mm: null, media: null, errors: [], busy: false };
      if (!printer) return base;
      try {
        const s = await printer.status();
        return { ...base, connected: true, tape_mm: s.tape_mm, media: s.media, errors: s.errors, busy: printer.busy };
      } catch (e) {
        return { ...base, connected: true, errors: [e.message] };
      }
    },
    async parse(text) { return JSON.parse(call(() => mod.parse(text))); },
    async templates() { return store.get("templates", []); },
    async saveTemplate(t) {
      const items = store.get("templates", []).filter((x) => x.name !== t.name).concat([t]).sort((a, b) => a.name.localeCompare(b.name));
      store.set("templates", items); return items;
    },
    async deleteTemplate(name) { const items = store.get("templates", []).filter((x) => x.name !== name); store.set("templates", items); return items; },
    async recent() { return store.get("recent", []); },
    uploadIcon: null,  // no server to keep uploads on
    usb: "usb" in navigator, serial: "serial" in navigator,
    async connectUsb() {
      const dev = await navigator.usb.requestDevice({ filters: [{ vendorId: 0x04f9 }] });
      return attach(await UsbLink.open(dev), models.find((m) => m.usb_pid === dev.productId)?.model);
    },
    async connectSerial() { return attach(await SerialLink.open(await navigator.serial.requestPort())); },
    async reconnect() {  // devices this site was given access to before
      if (engine.usb) for (const dev of await navigator.usb.getDevices()) {
        const m = models.find((x) => x.usb_pid === dev.productId); if (m) return attach(await UsbLink.open(dev), m.model);
      }
      if (engine.serial && store.get("serial", false)) for (const port of await navigator.serial.getPorts()) return attach(await SerialLink.open(port));
    },
    async disconnect() { if (printer) { await printer.link.close(); printer = null; store.set("serial", false); } },
  };

  async function attach(link, usbModel) {
    if (printer) await printer.link.close();
    if (usbModel) engine.setModel(usbModel);
    if (link.kind === "Bluetooth") store.set("serial", true);
    printer = new Printer(link, mod, py, model, () => info());
    link.onclose = () => { if (printer?.link === link) printer = null; };
    return printer;
  }
  try { await engine.reconnect(); } catch {}
  return engine;
}

function pyError(e) {  // "Traceback ... ValueError: design is for [12] mm tape" -> the last line's message
  const last = String(e.message || e).trim().split("\n").pop();
  return last.replace(/^\w+(Error|Exception|NotFound): /, "");
}

// ---- links: a byte pipe to the printer, with a buffer of what it sent back --------------------
class Link {
  constructor(kind) { this.kind = kind; this.rx = new Uint8Array(0); this.wake = null; this.closed = false; this.onclose = null; }
  push(data) {
    const b = new Uint8Array(this.rx.length + data.length); b.set(this.rx); b.set(data, this.rx.length); this.rx = b;
    this.wake?.();
  }
  gone() { this.closed = true; this.wake?.(); this.onclose?.(); }
  // Next 32-byte status packet within `ms`, or null. Packets can arrive split or two at a time.
  async readStatus(ms) {
    const deadline = Date.now() + ms;
    for (;;) {
      while (this.rx.length >= 32) {
        const pkt = this.rx.slice(0, 32); this.rx = this.rx.slice(32);
        if (pkt[0] === 0x80 && pkt[1] === 0x20) return pkt;
        console.warn("teip: dropping non-status bytes", pkt);
      }
      const left = deadline - Date.now();
      if (left <= 0 || this.closed) return null;
      await new Promise((ok) => { this.wake = ok; setTimeout(ok, left); });
      this.wake = null;
    }
  }
}

class UsbLink extends Link {
  static async open(dev) {
    const l = new UsbLink("USB"); l.dev = dev;
    await dev.open();
    if (!dev.configuration) await dev.selectConfiguration(1);
    await dev.claimInterface(0);
    const eps = dev.configuration.interfaces[0].alternate.endpoints;
    l.out = eps.find((e) => e.direction === "out").endpointNumber;
    l.in = eps.find((e) => e.direction === "in").endpointNumber;
    navigator.usb.addEventListener("disconnect", (e) => { if (e.device === dev) l.gone(); });
    l.pump();
    return l;
  }
  async pump() {
    while (!this.closed) {
      try {
        const r = await this.dev.transferIn(this.in, 64);
        if (r.data?.byteLength) this.push(new Uint8Array(r.data.buffer));
      } catch { if (!this.dev.opened) return this.gone(); await new Promise((ok) => setTimeout(ok, 200)); }
    }
  }
  // Resolves when the printer has taken every byte. While it prints it holds the OUT pipe, so this can take a while.
  async write(bytes) { await this.dev.transferOut(this.out, bytes); }
  async close() { this.closed = true; try { await this.dev.close(); } catch {} this.gone(); }
}

class SerialLink extends Link {
  static async open(port) {
    const l = new SerialLink("Bluetooth"); l.port = port;
    await port.open({ baudRate: 115200 });  // ponytail: ignored over Bluetooth RFCOMM; set it for real serial adapters if one ever needs it
    l.writer = port.writable.getWriter();
    l.pump();
    return l;
  }
  async pump() {
    while (!this.closed && this.port.readable) {
      this.reader = this.port.readable.getReader();
      try { for (;;) { const { value, done } = await this.reader.read(); if (done) break; this.push(value); } }
      catch {} finally { this.reader.releaseLock(); }
    }
    this.gone();
  }
  async write(bytes) { await this.writer.write(bytes); }
  async close() {
    this.closed = true;
    try { await this.reader?.cancel(); this.writer.releaseLock(); await this.port.close(); } catch {}
    this.gone();
  }
}

// ---- the print conversation, as in teip/backend.py UsbBackend ---------------------------------
const STATUS_COMPLETED = 0x01, STATUS_ERROR = 0x02, RASTER_MODE = [0x1b, 0x69, 0x61, 0x01];

class Printer {
  constructor(link, mod, py, model, info) { Object.assign(this, { link, mod, py, model, info }); this.busy = false; this.last = null; this.queue = Promise.resolve(); }
  exclusive(fn) { const run = this.queue.then(fn, fn); this.queue = run.catch(() => {}); return run; }  // one conversation at a time
  parse(pkt) { return JSON.parse(this.mod.status(pkt)); }
  async drain() { while (await this.link.readStatus(300)) {} }
  async hello() {
    await this.drain();
    const hs = this.mod.handshake(); const bytes = hs.toJs(); hs.destroy();
    await this.link.write(bytes);
    const pkt = await this.link.readStatus(3000);
    if (!pkt) throw new Error(`${this.model}: no status reply`);
    return (this.last = this.parse(pkt));
  }
  status() { return this.busy ? Promise.resolve(this.last) : this.exclusive(() => this.hello()); }
  print(req) {
    return this.exclusive(async () => {
      this.busy = true;
      try {
        const st = await this.hello();
        if (st.errors.length) throw new Error("printer error: " + st.errors.join(", "));
        if (!st.tape_mm) throw new Error("no tape loaded");
        let out;
        try { out = this.mod.jobs(this.model, JSON.stringify(req), st.tape_mm); } catch (e) { throw new Error(pyError(e)); }
        const [jobs, mm] = out.toJs(); out.destroy();
        const n = mm.length;
        let k = 0;
        for (const job of jobs) {
          const pages = count(job, RASTER_MODE);
          const len = mm.slice(k, k + pages).reduce((a, b) => a + b, 0) + this.info().min_feed_mm; k += pages;
          await this.link.write(job);
          await this.waitDone(3 + 0.1 * len);
        }
        return `printed ${n} label(s) on ${st.tape_mm} mm tape`;
      } finally { this.busy = false; }
    });
  }
  // Until the page is out. E550W-family printers say "printing completed"; the E560BT says nothing and
  // holds the OUT pipe while printing, so keep offering ESC i S. The first one it takes is answered idle.
  async waitDone(estimate) {
    const t0 = Date.now(), deadline = t0 + (60 + estimate) * 1000, settle = 1500;
    const req = this.mod.status_request(); const ask = req.toJs(); req.destroy();
    let pending = null;
    while (Date.now() < deadline) {
      const pkt = await this.link.readStatus(300);
      if (pkt) {
        const s = this.parse(pkt);
        if (s.status_type === STATUS_ERROR || s.errors.length) throw new Error("printer error: " + (s.errors.join(", ") || "unknown"));
        if (s.status_type === STATUS_COMPLETED || (s.status_type === 0 && s.phase_type === 0 && Date.now() - t0 >= settle)) { this.last = s; return; }
        continue;
      }
      if (this.link.closed) throw new Error("printer disconnected");
      if (!pending) pending = this.link.write(ask).catch(() => {}).finally(() => { pending = null; });
    }
    throw new Error("printer did not report idle in time");
  }
}

function count(hay, needle) {
  let n = 0;
  outer: for (let i = 0; i <= hay.length - needle.length; i++) {
    for (let j = 0; j < needle.length; j++) if (hay[i + j] !== needle[j]) continue outer;
    n++;
  }
  return n;
}
