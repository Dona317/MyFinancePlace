"""Submit an HTML form from a rendered page the way a browser would (for end-to-end tests)."""
import re
from html.parser import HTMLParser


class _FormParser(HTMLParser):
    def __init__(self, form_id):
        super().__init__()
        self.form_id, self.inside, self.fields = form_id, False, []
        self._select, self._select_disabled, self._first_option = None, False, None
        self._in_template = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "template":
            self._in_template = True  # rows added by JavaScript are not part of the page yet
        if self._in_template:
            return
        if tag == "form" and a.get("id") == self.form_id:
            self.inside = True
            return
        if tag == "option":
            self._option(a)
            return
        belongs = self.inside or a.get("form") == self.form_id
        if not belongs or "name" not in a:
            return
        if tag == "select":
            self._select, self._select_disabled, self._first_option = a["name"], "disabled" in a, None
        elif tag == "input" and "disabled" not in a:
            kind = a.get("type", "text")
            if kind in ("checkbox", "radio"):
                if "checked" in a:
                    self.fields.append((a["name"], a.get("value", "on")))
            elif kind not in ("submit", "button"):
                self.fields.append((a["name"], a.get("value", "")))

    def _option(self, a):
        if self._select is None:
            return
        if self._first_option is None:
            self._first_option = a.get("value", "")
        if "selected" in a:
            if not self._select_disabled:
                self.fields.append((self._select, a.get("value", "")))
            self._select = None

    def handle_endtag(self, tag):
        if tag == "template":
            self._in_template = False
        elif tag == "form" and self.inside:
            self.inside = False
        elif tag == "select" and self._select is not None:
            if not self._select_disabled and self._first_option is not None:
                self.fields.append((self._select, self._first_option))  # no option selected: browser sends the first
            self._select = None


def form_data(html: str, form_id: str, **overrides) -> dict:
    """Fields a browser would submit for form `form_id`; `overrides` replace or add values."""
    parser = _FormParser(form_id)
    parser.feed(html)
    data: dict[str, list[str]] = {}
    for name, value in parser.fields:
        data.setdefault(name, []).append(value)
    for name, value in overrides.items():
        data[name] = value if isinstance(value, list) else [value]
    return data


def assert_divs_balanced(html: str) -> None:
    """A stray </div> closes the page container early and breaks the layout (browsers hide it)."""
    assert len(re.findall(r"<div\b", html)) == len(re.findall(r"</div>", html))
