# teip protocol and API notes

What the server and the page send to the printer, what was verified on real tape, and the HTTP API
of the server. Sources for the protocol: Brother's raster command references (linked in
`teip/printers.py`) and [ptouch-print](https://git.familie-radermacher.ch/linux/ptouch-print.git).

## PT-E560BT, verified on tape

The E560BT is not in Brother's E550W raster reference and behaves like ptouch-print's
"PT-D460BT family" (`Printer.d460bt` in `printers.py`):

- `ESC i z` byte n9 must be 2 on every page, otherwise the printer prints but stays in
  "printing", keeps the job across a power cycle, and blocks the USB OUT pipe.
- `^Z` (print with feed) ends every page; `FF` is not used. Chaining pages into one strip is
  `ESC i K` bit 3 = 0, half cut between pages is bit 2 = 1. Both verified.
- `ESC i M` bit 6 (auto cut) makes the printer cut the blank leader off the first label; with the
  half-cut bit set that leading cut is a half cut, a peel tab. The end cut stays a full cut. Verified.
- No `ESC i A`. Raster must be uncompressed (`M 00`): PackBits gives blank tape.
- It sends no status packets while printing. The backend waits a length-based estimate and
  then polls `ESC i S` until the printer answers idle.
- Half cuts only exist inside one job: when the next job arrives the printer releases the held tape
  with a full cut, so a batch goes as one job. A 6-label, 64 KB job once came out as one good label
  and blanks; `Printer.max_job_bytes` splits a batch into smaller jobs (full cut at each split) if
  the input buffer turns out to be the reason.
- Set Auto Power Off (AC adapter) to Off on the printer, or it drops off USB.

## API

```sh
# design spec -> print. Gridfinity 1-unit label: head profile + drive icons, size, standard
curl -X POST http://127.0.0.1:8014/api/print -H 'content-type: application/json' -d '{
  "labels": [{"icons": ["head/socket-cap", "drive/hex-socket"], "lines": ["M3×8", "DIN 912"], "units": 1}],
  "options": {"half_cut": true, "copies": 1}}'

# batch strip: several labels, half-cuts between, leader waste paid once
curl -X POST .../api/print -d '{"labels": [{"line1":"M3","units":1},{"line1":"M4","units":1}]}'

# raw 1-bit PNG, height must be the printable dots of the loaded tape (9 mm = 50 px at 180 dpi)
curl -X POST http://127.0.0.1:8014/api/print/png -F image=@label.png

curl http://127.0.0.1:8014/api/status
# {"backend":"usb","printer":"PT-E560BT","dpi":180,"connected":true,"tape_mm":9,"media":"laminated","errors":[],"half_cut":true}
```

Home Assistant:

```yaml
rest_command:
  teip_label:
    url: http://teip.local/api/print
    method: POST
    content_type: application/json
    payload: '{"labels":[{"lines":["{{ text }}"],"icon":"{{ icon }}","units":1}]}'
```

Label spec fields: `lines` (or `line1`/`line2`; line 2 renders as a smaller subtitle), `icons`
(list, left to right; `icon` for a single one), `tape_mm`, `length_mm`, `units`
(Gridfinity grid units, overrides length), `font_size`, `align`, `layout` (`side` | `stacked`),
`margin_mm`, `gap_mm`. Options: `margin_mm` (feed before/after each label, floor 2 mm),
`half_cut`, `hires`, `copies`, `chain` (no feed/cut after the last label: the next job's leading cut or the
printer's Feed/Cut key releases it, saving the ~24 mm head-to-cutter feed per job), `force`.

## Tape economics

The printer feeds at least 24.5 mm (head-to-cutter distance) per job, whatever the label
length. Queue labels in the batch panel and print them as one strip: half-cuts between labels,
one full cut and one leader per batch.
