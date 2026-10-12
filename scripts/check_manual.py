"""Checks the user manual's built site (docs/user-manual.md, UM-AC04, UM-AC06, and UM-AC07).

scripts/check builds the site with `uv run zensical build --clean`, then runs this on site/:

    uv run python scripts/check_manual.py site

It fails when:

- a page loads a resource from another host, such as a script, stylesheet, font, or image, or a
  stylesheet the site serves does (UM-AC07);
- a page's footer lacks the non-affiliation notice or the link to LICENSE (UM-AC04);
- a link between pages doesn't resolve: the page it names, or its anchor, is missing (UM-AC06).

Zensical's strict build already fails on a broken link in a page's Markdown. This reads the built
HTML, so it also covers what the theme writes, such as the footer, and it catches a theme update
that starts loading something from elsewhere. It reads the theme's scripts only as files the pages
load: what a script fetches when it runs isn't checked.
"""

import posixpath
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

# The site's own address. A link that starts with it is a link between pages. So is a link from
# the root that starts with its path, as the 404 page's are, which work from any address.
SITE_URL = "https://promptedportfolio.github.io/trialfolio/"
SITE_PATH = urlsplit(SITE_URL).path
LICENSE_URL = "https://github.com/promptedportfolio/trialfolio/blob/main/LICENSE"
# The README's non-affiliation notice (docs/disclaimers.md, DSC-06), with its whitespace collapsed.
NON_AFFILIATION_NOTICE = (
    "Not affiliated with Portfolio123. This is an independent project. It is not an official "
    "Portfolio123 project and has not been reviewed by Portfolio123. No endorsement by "
    "Portfolio123 is implied."
)

# The attributes that make a browser load what they name, by element.
RESOURCE_ATTRIBUTES = {
    "script": ("src",),
    "img": ("src", "srcset"),
    "source": ("src", "srcset"),
    "video": ("src", "poster"),
    "audio": ("src",),
    "track": ("src",),
    "iframe": ("src",),
    "embed": ("src",),
    "object": ("data",),
    "input": ("src",),
    "image": ("href", "xlink:href"),
    "use": ("href", "xlink:href"),
}
# The kinds of <link> that load what they name, or connect to its host ahead of time.
LOADING_LINK_TYPES = {
    "stylesheet",
    "icon",
    "apple-touch-icon",
    "apple-touch-icon-precomposed",
    "mask-icon",
    "manifest",
    "preload",
    "prefetch",
    "modulepreload",
    "preconnect",
    "dns-prefetch",
    "prerender",
}
# The kinds of <link> that name another page of the site.
PAGE_LINK_TYPES = {"prev", "next"}

CSS_URL = re.compile(r"""(?:url\(|@import)\s*(['"]?)\s*([^'")\s;]*)""", re.IGNORECASE)


class _Page(HTMLParser):
    """What a page links to, loads, and carries in its footer."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.resources: list[str] = []
        self.footer_text: list[str] = []
        self.footer_links: list[str] = []
        self._footer_depth = 0
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name: value or "" for name, value in attrs}
        for name in ("id", "name") if tag == "a" else ("id",):
            if values.get(name):
                self.ids.add(values[name])
        if tag == "footer":
            self._footer_depth += 1
        if tag == "style":
            self._in_style = True
        if "style" in values:
            self.resources.extend(_css_urls(values["style"]))
        for name in RESOURCE_ATTRIBUTES.get(tag, ()):
            if values.get(name):
                self.resources.extend(
                    _srcset_urls(values[name]) if name == "srcset" else [values[name]]
                )
        if tag == "link" and values.get("href"):
            types = set(values.get("rel", "").lower().split())
            if types & LOADING_LINK_TYPES:
                self.resources.append(values["href"])
            if types & PAGE_LINK_TYPES:
                self.links.append(values["href"])
        if tag in ("a", "area") and "href" in values:
            self.links.append(values["href"])
            if self._footer_depth:
                self.footer_links.append(values["href"])

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "footer" and self._footer_depth:
            self._footer_depth -= 1
        if tag == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._footer_depth:
            self.footer_text.append(data)
        if self._in_style:
            self.resources.extend(_css_urls(data))


def _css_urls(css: str) -> list[str]:
    return [match.group(2) for match in CSS_URL.finditer(css)]


def _srcset_urls(srcset: str) -> list[str]:
    return [candidate.split()[0] for candidate in srcset.split(",") if candidate.strip()]


def _from_another_host(url: str) -> bool:
    if url.lower().startswith("data:"):
        return False
    return bool(urlsplit(url).netloc) and not url.startswith(SITE_URL)


def _page_url(site: Path, page: Path) -> str:
    """The page's path within the site, as a browser resolves relative links from it."""
    return page.relative_to(site).as_posix()


def _target(site: Path, page_url: str, href: str) -> tuple[str, str] | None:
    """The file within the site that a link between pages names, and its anchor.

    None for a link that isn't between pages, such as one to another host or a mailto: link.
    """
    if href.startswith(SITE_URL):
        href = SITE_PATH + href[len(SITE_URL) :]
    parts = urlsplit(href)
    if parts.scheme or parts.netloc:
        return None
    if not parts.path:
        return page_url, unquote(parts.fragment)
    if parts.path.startswith("/"):
        if not parts.path.startswith(SITE_PATH):
            return "..", ""
        path = parts.path[len(SITE_PATH) :]
    else:
        path = posixpath.join(posixpath.dirname(page_url), parts.path)
    path = posixpath.normpath(unquote(path))
    if path == ".":
        path = ""
    if path.startswith(".."):
        return "..", ""
    if path == "" or parts.path.endswith("/") or (site / path).is_dir():
        path = posixpath.join(path, "index.html")
    return path, unquote(parts.fragment)


def check_site(site: Path) -> list[str]:
    """Every problem found in the built site at `site`, or none."""
    problems: list[str] = []
    pages = {_page_url(site, path): path for path in sorted(site.rglob("*.html"))}
    if not pages:
        return [f"{site}: no pages; build the site first"]
    parsed: dict[str, _Page] = {}
    for url, path in pages.items():
        page = _Page()
        page.feed(path.read_text(encoding="utf-8"))
        page.close()
        parsed[url] = page

    for url, page in parsed.items():
        for resource in page.resources:
            if _from_another_host(resource):
                problems.append(f"{url}: loads {resource} from another host (UM-AC07)")
        footer = " ".join(" ".join(page.footer_text).split())
        if NON_AFFILIATION_NOTICE not in footer:
            problems.append(f"{url}: the footer lacks the non-affiliation notice (UM-AC04)")
        if LICENSE_URL not in page.footer_links:
            problems.append(f"{url}: the footer lacks the link to LICENSE (UM-AC04)")
        for href in page.links:
            target = _target(site, url, href)
            if target is None:
                continue
            path, anchor = target
            if path not in parsed:
                if path == ".." or not (site / path).is_file():
                    problems.append(f"{url}: the link {href} names no page of the site (UM-AC06)")
                continue
            if anchor and anchor not in parsed[path].ids:
                problems.append(f"{url}: the link {href} names a missing anchor (UM-AC06)")

    for stylesheet in sorted(site.rglob("*.css")):
        for resource in _css_urls(stylesheet.read_text(encoding="utf-8")):
            if _from_another_host(resource):
                name = stylesheet.relative_to(site).as_posix()
                problems.append(f"{name}: loads {resource} from another host (UM-AC07)")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_manual.py <the built site's folder>", file=sys.stderr)
        return 2
    site = Path(argv[0])
    problems = check_site(site)
    for problem in problems:
        print(f"check_manual: {problem}", file=sys.stderr)
    if problems:
        return 1
    count = len(list(site.rglob("*.html")))
    print(
        f"Checked {count} pages: none loads anything from another host, every footer carries "
        "the notices, and every link between pages resolves."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
