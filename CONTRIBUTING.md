# Contributing to teip

**Contributions are very welcome.** teip is young, and most of it has only been tried on one
printer, so almost any help moves it forward:

- **Printer reports.** Own a Brother TZe printer? Try teip on it and
  [file a printer report](https://github.com/petrepa/teip/issues/new?template=printer-report.yml),
  whether it worked or not. Photos of the label help.
- **Icons.** New part types: fasteners, electronics, plumbing, anything that lives in a drawer.
  Black on white, readable at 9 mm tall. Draw them in `icons/generate.py` or add PNGs with a
  license that allows redistribution, and credit them in `icons/ATTRIBUTION.md`.
- **Standards and presets.** More DIN/ISO hints, rivet tables, sizes.
- **Bugs and ideas.** Open an issue. A screenshot or a photo of the printed label says a lot.
- **Code.** Pull requests are welcome. For something big, open an issue first so we can agree on
  the shape.

## Development

```sh
uv sync
cp config.example.toml config.toml     # backend = "mock": no printer needed
uv run python serve.py                 # http://127.0.0.1:8014/
uv run pytest
uv run python tools/build_site.py && python -m http.server -d site 8000   # the server-less build
```

With `backend = "mock"` the server writes each print job and a PNG of the strip to `data/mock/`
instead of printing, so almost everything can be worked on without a printer.

## Where things are

- `teip/labels.py` request → images → printer jobs, shared by the server and the browser
- `teip/render.py` draws a label at exactly the printable height of the tape
- `teip/raster.py` Brother's raster commands and status packets
- `teip/printers.py` every supported model: pins per tape width, dpi, cutter
- `teip/backend.py` the server's USB conversation (pyusb); `teip/static/engine.js` the browser's (WebUSB / Web Serial)
- `teip/browser.py` what the page calls under Pyodide
- `teip/app.py` the server (FastAPI)
- `teip/static/` the page: plain HTML, CSS and ES modules, no build step
- `icons/` the icon set; `deploy/` the Linux and Windows installers
- [docs/PROTOCOL.md](docs/PROTOCOL.md) printer protocol notes and the HTTP API

Keep the page free of frameworks and build steps, and keep printer-specific facts in
`printers.py` rather than scattered through the code.
