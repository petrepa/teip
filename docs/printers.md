# Printers

Brother **TZe** tape printers with USB. Thermal paper printers (QL series) are not supported.

| Printer | USB | Bluetooth | Status |
|---|---|---|---|
| PT-E560BT | ✓ | ✓ | **Works** over USB. Through the teip server: single labels, half-cut strips, chain printing. Straight from the browser (WebUSB, Chrome on Windows): single labels; strips not tried yet. Bluetooth untested. |
| PT-P700 | ✓ | | Untested. Its "Editor Lite" switch must be **off**, or it shows up as a USB drive instead of a printer. |
| PT-P710BT | ✓ | ✓ | Untested. No half cutter. |
| PT-E550W, PT-P750W | ✓ | | Untested. The models Brother's raster reference is written for. |
| PT-P910BT | ✓ | ✓ | Untested. 360 dpi, tape up to 36 mm. |
| PT-P950NW | ✓ | | Untested. 360 dpi, tape up to 36 mm. Network printing is not supported. |

Tape widths 3.5, 6, 9, 12, 18 and 24 mm (36 mm on the P9xx). teip reads the loaded tape from the
printer; a design made for another width is refused, with a one-click switch to the loaded one.

**Tried one?** Please [file a printer report](https://github.com/petrepa/teip/issues/new?template=printer-report.yml),
working or not. That is how a row above turns from "untested" to "works".

## Things to know

- **Auto Power Off:** turn it off on the printer, or it drops off USB after a while.
- **Leader waste:** every print job feeds about 24 mm of tape before the first label, because the
  cutter sits that far from the print head. Print labels as one strip from the batch, or use chain
  printing, and you pay that once instead of once per label.
- **Browser vs. server rendering:** both run the same Python code, but their FreeType builds differ,
  so text can come out a pixel bolder in the browser, and a "fit text" label a millimetre or so
  longer. Layout, icons and printer commands are the same.

What each printer was verified to do, byte by byte, is in [PROTOCOL.md](PROTOCOL.md).
