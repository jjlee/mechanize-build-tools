import unittest

import lxml.html

import buildtools.tidy


class TestRemoveElementKeepingChildren(unittest.TestCase):

    def test_no_inner_element(self):
        tree = lxml.html.fromstring("""\
<html><head></head><body>
  <p>ptext<span class="q">spantext</span>spantail</p>ptail
</body></html>""")
        buildtools.tidy.collapse_p_span(tree)
        self.assertEquals(lxml.html.tostring(tree),
                          """\
<html><head></head><body>
  <p class="q">ptextspantextspantail</p>ptail
</body></html>""")

    def test_inner_element(self):
        tree = lxml.html.fromstring("""\
<html><head></head><body>
  <p>ptext<span class="q">spantext<b>btext</b>btail</span>spantail</p>ptail
</body></html>""")
        buildtools.tidy.collapse_p_span(tree)
        self.assertEquals(lxml.html.tostring(tree),
                          """\
<html><head></head><body>
  <p class="q">ptextspantext<b>btext</b>btailspantail</p>ptail
</body></html>""")

    def test_multiple_inner_elements(self):
        tree = lxml.html.fromstring("""\
<html><head></head><body>
  <pre>pretext<code>codetext<span>spantext</span>spantail</code>codetail</pre>pretail
</body></html>""")
        buildtools.tidy.collapse_pre_code(tree)
        self.assertEquals(lxml.html.tostring(tree),
                          """\
<html><head></head><body>
  <pre>pretextcodetext<span>spantext</span>spantailcodetail</pre>pretail
</body></html>""")

    def test_collapse_normal(self):
        tree = lxml.html.fromstring("""\
<html><head></head><body>
  <pre class="sourceCode python"><span class="Char Preprocessor">import</span><span class="Normal NormalText"> </span><span class="Normal">mechanize</span><br></pre>
</body></html>""")
        buildtools.tidy.collapse_normal(tree)
        self.assertEquals(lxml.html.tostring(tree),
                          """\
<html><head></head><body>
  <pre class="sourceCode python"><span class="Char Preprocessor">import</span> mechanize<br></pre>
</body></html>""")


if __name__ == "__main__":
    unittest.main()
