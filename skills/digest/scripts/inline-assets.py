#!/usr/bin/env python3
"""inline-assets: make a digest page self-contained by pulling local files into it.

Usage:
  inline-assets.py <in.html> [out.html]      (out defaults to in.html, rewritten in place;
                                              keep a source copy if you will re-render the diagram)

Pulls in, from paths relative to the page:
  <img src="x.png"> and srcset         -> data:image/png;base64,...  (png, jpg, gif, webp, svg)
  <link rel="stylesheet" href="x.css"> -> <style media=...>...</style>, its url() resolved
                                          against the stylesheet's own folder
  <script src="x.js"></script>         -> <script>...</script>
  url(x.png) in <style> and style=""   -> url(data:...)
Web addresses (http, https, //) are left alone: page-check.mjs refuses them, on purpose.
HTML comments are left as they are.
Use it when a page shows the diagram PNG ("both shapes": the page with the diagram inside).
Exit codes: 0 done (prints how many files it inlined), 1 a referenced local file is missing
or unreadable (nothing is written), 2 bad usage.
"""
import base64
import os
import re
import sys

MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
        ".webp": "image/webp", ".svg": "image/svg+xml"}
REMOTE = re.compile(r"^\s*(?:[a-z][a-z0-9+.-]*:|//|#)", re.I)  # http:, data:, blob:, //host, #id
ATTR_VAL = r"(?:\"([^\"]*)\"|'([^']*)'|([^\s>\"']+))"


class Inliner:
    def __init__(self, page_dir):
        self.page_dir = page_dir
        self.problems = []
        self.count = 0

    def local(self, ref, base):
        path = os.path.normpath(os.path.join(base, ref.split("#")[0].split("?")[0]))
        if not os.path.isfile(path):
            self.problems.append("missing local file: %s" % ref)
            return None
        self.count += 1
        return path

    def text(self, path):
        try:
            with open(path, encoding="utf-8") as fh:
                return fh.read()
        except UnicodeDecodeError:
            self.problems.append("cannot read %s as UTF-8" % path)
            return None

    def data_uri(self, ref, base):
        if REMOTE.match(ref):
            return None
        path = self.local(ref, base)
        if not path:
            return None
        mime = MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
        with open(path, "rb") as fh:
            return "data:%s;base64,%s" % (mime, base64.b64encode(fh.read()).decode())

    def css(self, css, base):
        def u(m):
            uri = self.data_uri(m.group(2), base)
            return m.group(0) if uri is None else "url(%s)" % uri
        return re.sub(r"(?<![\w.-])url\(\s*([\"']?)([^\"')]+)\1\s*\)", u, css)

    def srcset(self, val):
        out = []
        for cand in re.split(r",\s+", val.strip()):
            parts = cand.strip().split(None, 1)
            if not parts:
                continue
            uri = self.data_uri(parts[0], self.page_dir)
            out.append(" ".join([uri or parts[0]] + parts[1:]))
        return ", ".join(out)

    def tag_attr(self, tag, name, fn):
        """Rewrite one attribute (quoted or not) inside a tag string; data-src does not match src."""
        def rep(m):
            val = m.group(2) if m.group(2) is not None else m.group(3) if m.group(3) is not None else m.group(4)
            new = fn(val)
            return m.group(0) if new is None else '%s"%s"' % (m.group(1), new.replace('"', "&quot;"))
        return re.sub(r"((?<![\w-])%s\s*=\s*)%s" % (name, ATTR_VAL), rep, tag, count=1, flags=re.I)

    def run(self, html):
        # Keep comments out of reach: a commented-out <img> is not part of the page.
        comments = []

        def hide(m):
            comments.append(m.group(0))
            return "\x00C%d\x00" % (len(comments) - 1)
        html = re.sub(r"<!--[\s\S]*?-->", hide, html)

        def img(m):
            tag = m.group(0)
            tag = self.tag_attr(tag, "src", lambda v: self.data_uri(v, self.page_dir))
            return self.tag_attr(tag, "srcset", lambda v: self.srcset(v))
        html = re.sub(r"<img\b[^>]*>", img, html, flags=re.I)

        def link(m):
            tag = m.group(0)
            if not re.search(r"\brel\s*=\s*[\"']?stylesheet", tag, re.I):
                return tag
            href = re.search(r"(?<![\w-])href\s*=\s*" + ATTR_VAL, tag, re.I)
            ref = href and next(g for g in href.groups() if g is not None)
            if not ref or REMOTE.match(ref):
                return tag
            path = self.local(ref, self.page_dir)
            css = self.text(path) if path else None
            if css is None:
                return tag
            media = re.search(r"(?<![\w-])media\s*=\s*" + ATTR_VAL, tag, re.I)
            media_val = media and next(g for g in media.groups() if g is not None)
            css = self.css(css, os.path.dirname(path)).replace("</style", "<\\/style")
            return "<style%s>\n%s\n</style>" % (' media="%s"' % media_val if media_val else "", css)
        html = re.sub(r"<link\b[^>]*>", link, html, flags=re.I)

        def script(m):
            attrs = m.group(1)
            src = re.search(r"(?<![\w-])src\s*=\s*" + ATTR_VAL, attrs, re.I)
            ref = src and next(g for g in src.groups() if g is not None)
            if not ref or REMOTE.match(ref):
                return m.group(0)
            path = self.local(ref, self.page_dir)
            js = self.text(path) if path else None
            if js is None:
                return m.group(0)
            rest = (attrs[:src.start()] + attrs[src.end():]).rstrip()
            return "<script%s>\n%s\n</script>" % (rest, js.replace("</script", "<\\/script"))
        html = re.sub(r"<script\b([^>]*)>\s*</script>", script, html, flags=re.I)

        html = re.sub(r"(<style\b[^>]*>)([\s\S]*?)(</style>)",
                      lambda m: m.group(1) + self.css(m.group(2), self.page_dir) + m.group(3), html, flags=re.I)

        def style_attr(m):
            val = m.group(2) if m.group(2) is not None else m.group(3)
            q = '"' if m.group(2) is not None else "'"
            return "%s%s%s%s" % (m.group(1), q, self.css(val, self.page_dir), q)
        html = re.sub(r"(\sstyle\s*=\s*)(?:\"([^\"]*)\"|'([^']*)')", style_attr, html, flags=re.I)

        return re.sub(r"\x00C(\d+)\x00", lambda m: comments[int(m.group(1))], html)


def main(argv):
    if len(argv) not in (1, 2):
        print("usage: inline-assets.py <in.html> [out.html]", file=sys.stderr)
        return 2
    src = argv[0]
    out = argv[1] if len(argv) == 2 else src
    try:
        with open(src, encoding="utf-8") as fh:
            html = fh.read()
    except (OSError, UnicodeDecodeError) as e:
        print("inline-assets: cannot read %s: %s" % (src, e), file=sys.stderr)
        return 2
    inl = Inliner(os.path.dirname(os.path.abspath(src)))
    html = inl.run(html)
    if inl.problems:
        for p in sorted(set(inl.problems)):
            print("inline-assets: %s" % p, file=sys.stderr)
        return 1
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("inline-assets: %s, %d files inlined, %d KB" % (out, inl.count, len(html.encode()) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
