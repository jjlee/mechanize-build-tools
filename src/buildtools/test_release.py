import unittest

import lxml.html

import buildtools.release


def indent(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for elem in elem:
            indent(elem, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i


def pp(html):
    tree = lxml.html.fromstring(html)
    indent(tree)
    return lxml.html.tostring(tree, pretty_print=True)


class Test(unittest.TestCase):

    def make_site_map(self):
        Page = buildtools.release.Page
        class Pages(object):
            pass
        pages = Pages()
        def add(parent, page):
            parent.add(page)
            setattr(pages, page.name, page)
            return page
        root = Page("root", "/")
        pages.root = root
        add(root, Page("a", "/a/"))
        b = add(root, Page("b", "/b/"))
        ba = add(b, Page("ba", "/b/a/"))
        add(b, Page("bb", "/b/b/"))
        baa = add(ba, Page("baa", "/b/a/a/"))
        return root, pages

    def test_find_page(self):
        site_map, pages = self.make_site_map()
        self.assertEquals(buildtools.release.find_page(site_map, "root"),
                          [site_map])
        self.assertEquals(buildtools.release.find_page(site_map, "a"),
                          [site_map, pages.a])
        self.assertEquals(buildtools.release.find_page(site_map, "ba"),
                          [site_map, pages.b, pages.ba])
        self.assertEquals(buildtools.release.find_page(site_map, "bb"),
                          [site_map, pages.b, pages.bb])
        self.assertEquals(buildtools.release.find_page(site_map, "baa"),
                          [site_map, pages.b, pages.ba, pages.baa])

    def test_toc(self):
        site_map, pages = self.make_site_map()
        def toc_html(page, toc_root):
            return pp(buildtools.release.html(
                    buildtools.release.toc_tag(page, toc_root)))
        self.assertEquals(toc_html(pages.baa, pages.b),
            """\
<ul id="toc">
  <li>
    <a href="/b/a/">
ba
</a>
    <ul>
      <li>
        <span class="thispage">
baa
</span>
      </li>
    </ul>
  </li>
  <li>
    <a href="/b/b/">
bb
</a>
  </li>
</ul>

""")


if __name__ == "__main__":
    unittest.main()
