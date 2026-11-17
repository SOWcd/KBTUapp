"""An event's document (organizing.render_doc): its PDF's pages rendered to PNGs in a child process, so a crafted PDF
(a page of a million paths took 135 s in PDFium) or a PDFium crash costs only that child: the whole document has
`seconds` of wall time and CPU, `memory` bytes of address space, and no lock the receipts wait on. The child is this
file run by path with -I (stdlib, pypdfium2 and Pillow only; nothing of kbtu is imported there)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

TOO_MANY = 3  # the child's exit code for "more pages than allowed"


def run(data: bytes, out: Path, most: int, side: int, seconds: int, memory: int) -> list[Path]:
    """The pages as PNG files in `out` (the caller's temp directory), in order. ValueError("too_many_pages" |
    "not_a_pdf"): refused, broken, locked, too slow, too big, or the child died."""
    try:
        r = subprocess.run([sys.executable, "-I", __file__, str(out), str(most), str(side), str(seconds), str(memory)],
                           input=data, capture_output=True, timeout=seconds)
    except subprocess.TimeoutExpired:  # run() has killed it
        raise ValueError("not_a_pdf") from None
    if r.returncode == TOO_MANY:
        raise ValueError("too_many_pages")
    files = sorted(out.glob("*.png"), key=lambda p: int(p.stem) if p.stem.isdigit() else -1)
    if r.returncode or not 0 < len(files) <= most or [p.stem for p in files] != [str(i) for i in range(len(files))]:
        raise ValueError("not_a_pdf")
    return files


def _child() -> None:
    import resource
    out, most, side, seconds, memory = sys.argv[1], *map(int, sys.argv[2:6])
    resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))       # SIGXCPU kills it
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))          # a huge bitmap fails instead of swapping
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 20, 64 << 20))   # no PNG grows past 64 MB
    import pypdfium2 as pdfium
    try:
        pdf = pdfium.PdfDocument(sys.stdin.buffer.read())
    except pdfium.PdfiumError:
        sys.exit(2)
    n = len(pdf)
    if n > most:
        sys.exit(TOO_MANY)
    for i in range(n):
        page = pdf[i]
        w, h = (abs(x) for x in page.get_size())
        scale = min(4, side / max(w, h, 1))  # both sides at most `side`; a tiny page isn't blown up past 4x
        if w * scale * h * scale > side * side:
            sys.exit(2)
        page.render(scale=scale).to_pil().save(f"{out}/{i}.png", compress_level=1)
    sys.exit(0 if n else 2)


if __name__ == "__main__":
    _child()
