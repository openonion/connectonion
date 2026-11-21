"""Run the current Reader citation/activity functions against synthetic DOM nodes."""
import json
import re
import shutil
import subprocess
import pytest
from connectonion.rem.reader import TEMPLATE

FAKE_DOM = '\nclass Text { constructor(text) { this.text = String(text); } get textContent() { return this.text; } }\nclass Node {\n  constructor(tag) { this.tag = tag; this.attrs = {}; this.children = []; this.own = ""; }\n  setAttribute(k, v) { this.attrs[k] = String(v); }\n  hasAttribute(k) { return k in this.attrs; }\n  focus(options) { document.activeElement = this; this.focusOptions = options; }\n  appendChild(c) { this.children.push(c); return c; }\n  append(...cs) { for (const c of cs) this.children.push(typeof c === "string" ? new Text(c) : c); }\n  set textContent(v) { this.children = []; this.own = String(v); }\n  get textContent() { return this.own + this.children.map(c => c.textContent).join(""); }\n  set innerHTML(v) { this.own = String(v); }\n  get tagName() { return this.tag.toUpperCase(); }\n  querySelectorAll(selector) {\n    const tags = selector.split(",").map(s => s.trim().toLowerCase());\n    return walk(this).slice(1).filter(n => tags.includes(n.tag));\n  }\n  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }\n}\nconst main = new Node("main");\nconst document = { activeElement: null, createElement: tag => new Node(tag), createTextNode: text => new Text(text), getElementById: () => main };\nfunction walk(node, out = []) { if (node instanceof Node) { out.push(node); node.children.forEach(c => walk(c, out)); } return out; }\nfunction view(c) { category(c); return describe(); }\nfunction describe() {\n  const nodes = walk(main);\n  return {\n    h1: nodes.filter(n => n.tag === "h1").map(n => n.textContent),\n    h2: nodes.filter(n => n.tag === "h2").map(n => n.textContent),\n    records: nodes.filter(n => n.tag === "a" && (n.attrs.href || "").startsWith("#r=")).map(n => decodeURIComponent(n.attrs.href.slice(3))),\n    empty: nodes.some(n => n.attrs.class === "empty"),\n    alert: nodes.filter(n => n.attrs.role === "alert").map(n => n.textContent),\n    links: nodes.filter(n => n.tag === "a").map(n => n.attrs.href),\n    tags: nodes.map(n => n.tag),\n  };\n}\n'

def _run(script, rem, extra=()):
    node=shutil.which("node")
    if not node:
        pytest.skip("Node is required for Reader JavaScript")
    page=TEMPLATE.read_text(encoding="utf-8")
    def function(name):
        one=re.search(r"^function "+name+r"\([^\n]*\}[ \t]*\r?$",page,re.M)
        return one[0] if one else re.search(r"^function "+name+r"\(.*?\n\}",page,re.M|re.S)[0]
    stubs="const ACTIVITY=new Set(['notes','logs']); const privateTopicHidden=()=>false; const t=x=>x; const byActivity=(a,b)=>a.title.localeCompare(b.title); const row=r=>el('li',{},[el('a',{href:href(r),text:r.title})]);"
    functions="\n".join(function(n) for n in dict.fromkeys(["el","href","listedRecords",*extra]))
    result=subprocess.run([node],input="\n".join([FAKE_DOM,stubs,functions,"const REM="+json.dumps(rem)+";",script]),capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)
