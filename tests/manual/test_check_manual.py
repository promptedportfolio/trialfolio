"""The check of the user manual's built site fails on what UM-AC04, UM-AC06, and UM-AC07 forbid.

Traces to docs/user-manual.md: UM-AC07, a page or a stylesheet that loads a resource from another
host, and a page whose markup turns on a feature for which the theme's script loads code from
another host; UM-AC04, a footer without the non-affiliation notice or the link to LICENSE; tooling
and hosting, a footer without the link to the third-party notices, the only link to that page;
and UM-AC06, a link between pages whose page or anchor is missing. Each test writes a small site
by hand, as the theme lays one out, and runs `scripts/check_manual.py` on it. scripts/check runs
the same script on the manual's real build.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]

FOOTER = """
<footer class="md-footer"><div class="md-copyright">
  <p>Copyright &copy; 2026 Nathan Slaughter. Trial Folio is source available under the
  <a href="https://github.com/promptedportfolio/trialfolio/blob/main/LICENSE">Nathan Slaughter
  Personal Research License</a>. The site's
  <a href="/trialfolio/third-party-notices/">third-party notices</a>.</p>
  <p><strong>Not affiliated with Portfolio123.</strong> This is an independent project. It is not
  an official Portfolio123 project and has not been reviewed by Portfolio123. No endorsement by
  Portfolio123 is implied.</p>
</div></footer>
"""


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "check_manual", ROOT / "scripts" / "check_manual.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_manual"] = module
    spec.loader.exec_module(module)
    return module


check_manual = _load_checker()


def _page(head: str = "", body: str = "", footer: str = FOOTER) -> str:
    return f"<!doctype html><html><head>{head}</head><body>{body}{footer}</body></html>"


def _write(site: Path, path: str, text: str) -> None:
    (site / path).parent.mkdir(parents=True, exist_ok=True)
    (site / path).write_text(text, encoding="utf-8")


def _site(tmp_path: Path, **pages: str) -> Path:
    """A site with a home page and a how-to page that link to each other, plus `pages`."""
    site = tmp_path / "site"
    _write(
        site,
        "index.html",
        _page(
            head='<link rel="stylesheet" href="./assets/main.css">'
            '<script src="./assets/bundle.js"></script>',
            body='<h1 id="home">Home</h1><a href="how-to/a/#steps">Steps</a>'
            '<a href="https://www.portfolio123.com/">Portfolio123</a>',
        ),
    )
    _write(
        site,
        "how-to/a/index.html",
        _page(body='<h2 id="steps">Steps</h2><a href="../../">Home</a><a href="#steps">Here</a>'),
    )
    _write(site, "third-party-notices/index.html", _page(body="<h1>Third-party notices</h1>"))
    _write(site, "assets/main.css", "body{background:url(../images/x.png)}")
    _write(site, "assets/bundle.js", "")
    for name, text in pages.items():
        _write(site, name.replace("__", "/") + ".html", text)
    return site


def test_a_site_that_meets_the_criteria_passes(tmp_path: Path) -> None:
    site = _site(tmp_path)

    assert check_manual.check_site(site) == []
    assert check_manual.main([str(site)]) == 0


def test_an_unbuilt_site_fails(tmp_path: Path) -> None:
    assert check_manual.check_site(tmp_path) != []


def test_a_script_from_another_host_fails(tmp_path: Path) -> None:
    site = _site(tmp_path, b=_page(head='<script src="https://unpkg.com/mermaid"></script>'))

    assert check_manual.check_site(site) == [
        "b.html: loads https://unpkg.com/mermaid from another host (UM-AC07)"
    ]
    assert check_manual.main([str(site)]) == 1


def test_web_fonts_from_another_host_fail(tmp_path: Path) -> None:
    # What the theme writes with its font setting on.
    head = (
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        '<link rel="stylesheet" href="//fonts.googleapis.com/css?family=Inter">'
    )
    site = _site(tmp_path, b=_page(head=head))

    assert check_manual.check_site(site) == [
        "b.html: loads https://fonts.gstatic.com from another host (UM-AC07)",
        "b.html: loads //fonts.googleapis.com/css?family=Inter from another host (UM-AC07)",
    ]


def test_images_and_inline_styles_from_another_host_fail(tmp_path: Path) -> None:
    body = (
        '<img src="https://example.com/a.png">'
        '<img srcset="x.png 1x, https://example.com/b.png 2x">'
        "<div style=\"background:url('https://example.com/c.png')\"></div>"
        "<style>@import 'https://example.com/d.css';</style>"
    )
    site = _site(tmp_path, b=_page(body=body))

    assert check_manual.check_site(site) == [
        "b.html: loads https://example.com/a.png from another host (UM-AC07)",
        "b.html: loads https://example.com/b.png from another host (UM-AC07)",
        "b.html: loads https://example.com/c.png from another host (UM-AC07)",
        "b.html: loads https://example.com/d.css from another host (UM-AC07)",
    ]


def test_a_stylesheet_that_loads_from_another_host_fails(tmp_path: Path) -> None:
    site = _site(tmp_path)
    # An icon inlined as data, as the theme's stylesheets carry them, loads nothing.
    _write(
        site,
        "assets/extra.css",
        """a{mask:url('data:image/svg+xml;charset=utf-8,<svg xmlns="http://www.w3.org/2000/svg"/>')}"""
        "@font-face{src:url(https://fonts.gstatic.com/x.woff2)}",
    )

    assert check_manual.check_site(site) == [
        "assets/extra.css: loads https://fonts.gstatic.com/x.woff2 from another host (UM-AC07)"
    ]


def test_an_import_by_url_from_another_host_fails(tmp_path: Path) -> None:
    # @import takes a url() as well as a string, quoted or not, in a stylesheet or a page.
    site = _site(
        tmp_path,
        b=_page(body="<style>@import url(https://example.com/b.css);</style>"),
    )
    _write(
        site,
        "assets/extra.css",
        '@import url("https://example.com/a.css");@IMPORT URL( https://example.com/c.css );',
    )

    assert check_manual.check_site(site) == [
        "b.html: loads https://example.com/b.css from another host (UM-AC07)",
        "assets/extra.css: loads https://example.com/a.css from another host (UM-AC07)",
        "assets/extra.css: loads https://example.com/c.css from another host (UM-AC07)",
    ]


def test_a_diagram_fails(tmp_path: Path) -> None:
    # What a mermaid fence becomes, with the fences Zensical turns on by default.
    body = '<pre class="mermaid"><code>graph LR\n  A --&gt; B</code></pre>'
    site = _site(tmp_path, b=_page(body=body))

    assert check_manual.check_site(site) == [
        (
            "b.html: has diagrams (pre.mermaid), for which the theme's script loads code from "
            "another host (UM-AC07)"
        )
    ]
    assert check_manual.main([str(site)]) == 1


def test_an_image_lightbox_fails(tmp_path: Path) -> None:
    # Zensical's lightbox extension wraps an image in a link. An image can carry the class itself,
    # through attr_list. Either turns the feature on, and the page fails once.
    body = (
        '<a class="glightbox" data-type="image" href="assets/x.png"><img src="assets/x.png"></a>'
        '<img alt="An image" class="figure glightbox" src="assets/x.png" />'
    )
    site = _site(tmp_path, b=_page(body=body))
    _write(site, "assets/x.png", "")

    assert check_manual.check_site(site) == [
        (
            "b.html: has image lightboxes (.glightbox), for which the theme's script loads code "
            "from another host (UM-AC07)"
        )
    ]


def test_a_runnable_python_block_fails(tmp_path: Path) -> None:
    # The block holds the parts the theme's script looks for: an editor, run and clear buttons,
    # and an output.
    body = (
        '<div class="pyodide" data-session="default">'
        '<button id="py--run">Run</button><button id="py--clear">Clear</button>'
        '<div class="pyodide-editor" id="py--editor">print(1)</div>'
        '<pre class="pyodide-output"><code id="py--output"></code></pre>'
        "</div>"
    )
    site = _site(tmp_path, b=_page(body=body))

    assert check_manual.check_site(site) == [
        (
            "b.html: has runnable Python code blocks (.pyodide), for which the theme's script "
            "loads code from another host (UM-AC07)"
        )
    ]


def test_a_class_that_only_contains_a_features_name_passes(tmp_path: Path) -> None:
    # The theme's script selects a whole class name, and a diagram only on a <pre>. A code block
    # in the mermaid language is only code.
    body = (
        '<pre class="mermaid-source"><code class="language-mermaid">graph LR</code></pre>'
        '<div class="mermaid">graph LR</div>'
        '<img class="no-glightbox" src="assets/x.png">'
        '<p class="pyodide-note">Runs in the browser.</p>'
    )
    site = _site(tmp_path, b=_page(body=body))
    _write(site, "assets/x.png", "")

    assert check_manual.check_site(site) == []


def test_links_out_and_resources_from_the_sites_own_address_pass(tmp_path: Path) -> None:
    body = (
        '<a href="https://github.com/promptedportfolio/trialfolio/blob/main/docs/spec.md">Spec</a>'
        '<img src="https://promptedportfolio.github.io/trialfolio/assets/x.png">'
        '<a href="mailto:someone@example.com">Mail</a>'
    )
    site = _site(tmp_path, b=_page(body=body))
    _write(site, "assets/x.png", "")

    assert check_manual.check_site(site) == []


def test_a_footer_without_the_non_affiliation_notice_fails(tmp_path: Path) -> None:
    footer = FOOTER.replace("No endorsement by\n  Portfolio123 is implied.", "")
    # The notice elsewhere on the page doesn't count: a reader may not scroll to it.
    body = f"<p>{check_manual.NON_AFFILIATION_NOTICE}</p>"
    site = _site(tmp_path, b=_page(body=body, footer=footer))

    assert check_manual.check_site(site) == [
        "b.html: the footer lacks the non-affiliation notice (UM-AC04)"
    ]


def test_a_footer_without_the_link_to_license_fails(tmp_path: Path) -> None:
    footer = FOOTER.replace("blob/main/LICENSE", "blob/main/README.md")
    body = f'<a href="{check_manual.LICENSE_URL}">LICENSE</a>'
    site = _site(tmp_path, b=_page(body=body, footer=footer))

    assert check_manual.check_site(site) == [
        "b.html: the footer lacks the link to LICENSE (UM-AC04)"
    ]


def test_a_footer_without_the_link_to_the_notices_fails(tmp_path: Path) -> None:
    # The footer's link is the only one to the notices page, which isn't in the navigation. A link
    # elsewhere on the page doesn't count, and neither does a footer link to another page.
    footer = FOOTER.replace("/trialfolio/third-party-notices/", "/trialfolio/how-to/a/")
    body = '<a href="third-party-notices/">Notices</a>'
    site = _site(tmp_path, b=_page(body=body, footer=footer))

    assert check_manual.check_site(site) == [
        (
            "b.html: the footer lacks the link to the third-party notices "
            "(docs/user-manual.md, tooling and hosting)"
        )
    ]


def test_a_footer_link_to_the_notices_resolves_from_any_page(tmp_path: Path) -> None:
    # The theme writes the link relative to each page, and from the root on the 404 page, as
    # FOOTER does.
    def footer(href: str) -> str:
        return FOOTER.replace("/trialfolio/third-party-notices/", href)

    site = _site(
        tmp_path,
        **{
            "c": _page(footer=footer("third-party-notices/")),
            "how-to__d__index": _page(footer=footer("../../third-party-notices/#mit")),
            "third-party-notices__index": _page(body='<h2 id="mit">MIT</h2>', footer=footer("./")),
        },
    )

    assert check_manual.check_site(site) == []


def test_a_page_without_a_footer_fails(tmp_path: Path) -> None:
    site = _site(tmp_path, b=_page(footer=""))

    assert check_manual.check_site(site) == [
        "b.html: the footer lacks the non-affiliation notice (UM-AC04)",
        "b.html: the footer lacks the link to LICENSE (UM-AC04)",
        (
            "b.html: the footer lacks the link to the third-party notices "
            "(docs/user-manual.md, tooling and hosting)"
        ),
    ]


def test_a_link_to_a_missing_page_fails(tmp_path: Path) -> None:
    body = '<a href="how-to/missing/">Gone</a><a href="../outside/">Out</a>'
    site = _site(tmp_path, b=_page(body=body))
    # A page beside the site, which the link reaches, isn't one of its pages.
    _write(tmp_path, "outside/index.html", _page())

    assert check_manual.check_site(site) == [
        "b.html: the link how-to/missing/ names no page of the site (UM-AC06)",
        "b.html: the link ../outside/ names no page of the site (UM-AC06)",
    ]


def test_a_link_to_a_missing_anchor_fails(tmp_path: Path) -> None:
    body = '<a href="how-to/a/#missing">Gone</a><a href="#nowhere">Here</a>'
    site = _site(tmp_path, b=_page(body=body))

    assert check_manual.check_site(site) == [
        "b.html: the link how-to/a/#missing names a missing anchor (UM-AC06)",
        "b.html: the link #nowhere names a missing anchor (UM-AC06)",
    ]


def test_links_from_the_sites_root_and_address_resolve_within_it(tmp_path: Path) -> None:
    # The 404 page's links start from the root, so they work at any address.
    body = (
        '<a href="/trialfolio/how-to/a/">Steps</a>'
        '<a href="https://promptedportfolio.github.io/trialfolio/how-to/a/#steps">Steps</a>'
        '<a href="/trialfolio/how-to/missing/">Gone</a>'
        '<a href="/elsewhere/">Elsewhere</a>'
        '<a href="https://promptedportfolio.github.io/trialfolio/missing/">Gone</a>'
    )
    site = _site(tmp_path, **{"404": _page(body=body)})

    assert check_manual.check_site(site) == [
        "404.html: the link /trialfolio/how-to/missing/ names no page of the site (UM-AC06)",
        "404.html: the link /elsewhere/ names no page of the site (UM-AC06)",
        (
            "404.html: the link https://promptedportfolio.github.io/trialfolio/missing/ names no "
            "page of the site (UM-AC06)"
        ),
    ]
