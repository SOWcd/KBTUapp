"""Item 14: history out of comments, the why kept. Only comments and docstrings are touched (Python by tokens; web by
comment spans), and only these patterns:
  (owner, Oct 25)  (review, Oct 19)  (Oct 25)  (owner's video, Oct 25)        -> removed
  (owner, Oct 25: the reason)                                                  -> (the reason)
  (owner, Oct 25: "a quote")                                                   -> removed
  owner, Oct 25: the reason   (bare, in running text)                          -> the reason
argv: py|web, then files. Prints chars before/after."""
import io
import re
import sys
import tokenize

WHO = r"(?:the owner|owner|owner's (?:video|screenshot|phone|friend|test|list)|review|audit|a club leader|the creator)"
DATE = r"(?:Oct|Sep|Nov) \d{1,2}(?:\s*[-–]\s*\d{1,2}| and \d{1,2})?(?:,? ?~?\d{1,2}:\d{2})?"
# a who-and-when segment inside a parenthesis: "owner, Oct 25", "owner Oct 22", "Oct 7", "the owner's video, Oct 25"
SEG = re.compile(rf"(?:^|(?<=[,;(]))\s*(?:{WHO}(?:[, ]+{DATE})?|{DATE})\s*(?=$|[,;:)])")
GROUP = re.compile(r"([^\s#/*\-!<]?)(\s?)\(([^()]*)\)(:?)")  # the char before tells mid-sentence from a comment's start
QUOTED = re.compile(r"^\s*[\"“][^\"”]*[\"”]\s*$")
BARE = re.compile(rf"(?<![\w(])(?:{WHO}),\s*{DATE}:\s*(?=\S)")


def _group(m: re.Match) -> str:
    before, space, inner, colon = m.group(1), m.group(2), m.group(3), m.group(4)
    if not SEG.search(inner):
        return m.group(0)
    head, _, reason = inner.partition(":") if ":" in inner else (inner, "", "")
    kept = SEG.sub("", head)
    kept = re.sub(r"^[\s,;]+|[\s,;]+$", "", re.sub(r"\s*[,;]\s*(?=[,;])", "", kept))
    reason = reason.strip()
    if reason and QUOTED.match(reason):
        reason = ""
    body = "; ".join(x for x in (kept, reason) if x)
    if not body:  # gone; a colon after it stays mid-sentence ("an icon (owner): the bottom"), not at a comment's start
        return before + (colon if before else "")
    return f"{before}{space}({body}){colon}"


def trim(text: str) -> str:
    t = GROUP.sub(_group, text)
    t = BARE.sub("", t)
    return t


def py(path: str) -> tuple[int, int]:
    src = open(path).read()
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    import ast
    docs = set()
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and n.body and isinstance(n.body[0], ast.Expr) \
                and isinstance(n.body[0].value, ast.Constant) and isinstance(n.body[0].value.value, str):
            docs.add((n.body[0].lineno, n.body[0].col_offset))
    lines = src.splitlines(keepends=True)
    edits = []
    for t in toks:
        if t.type == tokenize.COMMENT or (t.type == tokenize.STRING and t.start in docs):
            new = trim(t.string)
            if new != t.string:
                edits.append((t.start, t.end, new))
    off = [0]
    for line in lines:
        off.append(off[-1] + len(line))
    out = src
    for (sl, sc), (el, ec), new in sorted(edits, reverse=True):
        a, b = off[sl - 1] + sc, off[el - 1] + ec
        out = out[:a] + new + out[b:]
    if out != src:
        open(path, "w").write(out)
    return len(src), len(out)


COMMENT = re.compile(r"(?<![:\w\"'`])//[^\n]*|/\*.*?\*/|<!--.*?-->", re.S)


def web(path: str) -> tuple[int, int]:
    src = open(path).read()
    out = COMMENT.sub(lambda m: trim(m.group(0)), src)
    if out != src:
        open(path, "w").write(out)
    return len(src), len(out)


if __name__ == "__main__":
    kind, files = sys.argv[1], sys.argv[2:]
    a = b = 0
    for f in files:
        x, y = (py if kind == "py" else web)(f)
        a, b = a + x, b + y
    print(f"{kind}: {len(files)} files, {a} -> {b} chars ({a - b} less)")
