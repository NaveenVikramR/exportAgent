"""Record the silent demo footage on the live site, using only the cached demo (case_002).

1920x1080 (viewport 1536x864 at 125% zoom), frames captured with Chromium's screencast, a drawn
cursor with a ripple on every click, smooth scrolling, and ~1.5 s pauses after actions.
Writes frames + timeline to OUT; build_video.py turns them into the MP4 and per-segment clips.

Run (Python with playwright installed):
    PLAYWRIGHT_BROWSERS_PATH=... python record_demo.py <out-dir> [base-url]
The demo should be freshly reset first; recording approves a draft, records a decision,
generates documents and switches a profile, so reset again afterwards.
"""
import asyncio
import base64
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import async_playwright

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "footage")
BASE = sys.argv[2] if len(sys.argv) > 2 else "https://3-104-80-176.sslip.io"
PAUSE = 1.5
NAV_OFFSET = 90  # sticky nav height (CSS px) to keep clear when scrolling to an element

OVERLAY = r"""
(() => {
  if (window.__overlay) return; window.__overlay = true;
  const add = () => {
    const c = document.createElement('div');
    c.id = '__cursor';
    c.style.cssText = 'position:fixed;left:-50px;top:-50px;width:22px;height:22px;z-index:2147483647;pointer-events:none;' +
      'transform:translate(-3px,-2px);';
    c.innerHTML = '<svg width="22" height="22" viewBox="0 0 22 22"><path d="M3 2 L3 18 L7.5 13.8 L10.6 20.5 L13.4 19.2 L10.4 12.7 L16.5 12.7 Z" ' +
      'fill="#111" stroke="#fff" stroke-width="1.6" stroke-linejoin="round"/></svg>';
    document.documentElement.appendChild(c);
    window.__moveCursor = (x, y) => { c.style.left = x + 'px'; c.style.top = y + 'px'; };
    if (window.__lastCursor) window.__moveCursor(...window.__lastCursor);
  };
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', add); else add();
  window.__ripple = (x, y) => {
    const r = document.createElement('div');
    r.style.cssText = `position:fixed;left:${x - 18}px;top:${y - 18}px;width:36px;height:36px;border-radius:50%;` +
      'border:3px solid rgba(16,185,129,.9);background:rgba(16,185,129,.18);z-index:2147483646;pointer-events:none;' +
      'transition:transform .6s ease-out, opacity .6s ease-out;transform:scale(.4);opacity:1';
    document.documentElement.appendChild(r);
    requestAnimationFrame(() => { r.style.transform = 'scale(1.6)'; r.style.opacity = '0'; });
    setTimeout(() => r.remove(), 700);
  };
  window.__highlight = (el, ms) => {
    const b = el.getBoundingClientRect();
    const h = document.createElement('div');
    h.style.cssText = `position:fixed;left:${b.left - 6}px;top:${b.top - 6}px;width:${b.width + 12}px;height:${b.height + 12}px;` +
      'border:3px solid rgba(245,158,11,.95);border-radius:10px;box-shadow:0 0 0 6px rgba(245,158,11,.18);' +
      'z-index:2147483645;pointer-events:none;transition:opacity .4s;opacity:0';
    document.documentElement.appendChild(h);
    requestAnimationFrame(() => { h.style.opacity = '1'; });
    setTimeout(() => { h.style.opacity = '0'; setTimeout(() => h.remove(), 450); }, ms);
  };
  window.__smoothScroll = (target, ms) => new Promise(resolve => {
    const start = window.scrollY, max = document.documentElement.scrollHeight - innerHeight;
    const end = Math.max(0, Math.min(target, max)), t0 = performance.now();
    const ease = t => t < .5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
    const step = now => {
      const t = Math.min(1, (now - t0) / ms);
      window.scrollTo(0, start + (end - start) * ease(t));
      t < 1 ? requestAnimationFrame(step) : resolve();
    };
    requestAnimationFrame(step);
  });
})();
"""


class Director:
    def __init__(self, page, cdp):
        self.page, self.cdp = page, cdp
        self.x, self.y = 760.0, 430.0
        self.frames: list[tuple[float, str]] = []
        self.segments: list[dict] = []
        (OUT / "frames").mkdir(parents=True, exist_ok=True)

    async def on_frame(self, params):
        ts = params["metadata"]["timestamp"]  # seconds since the epoch, same clock as time.time()
        name = f"frames/{len(self.frames):06d}.jpg"
        (OUT / name).write_bytes(base64.b64decode(params["data"]))
        self.frames.append((ts, name))
        try:
            await self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        except Exception:
            pass

    def now(self) -> float:
        return time.time() - self.wall0

    def segment(self, key: str, title: str):
        self.segments.append({"key": key, "title": title, "start": round(self.now(), 3)})
        print(f"[{self.now():6.1f}s] {key}: {title}", flush=True)

    async def wait(self, s: float = PAUSE):
        await self.page.wait_for_timeout(int(s * 1000))

    async def _sync_cursor(self):
        await self.page.evaluate(f"window.__lastCursor=[{self.x},{self.y}]; window.__moveCursor && window.__moveCursor({self.x},{self.y})")

    async def move(self, x: float, y: float, ms: int = 700):
        # Each step's round trips take ~20 ms, so no extra wait is needed for a smooth glide.
        steps = max(8, ms // 22)
        x0, y0 = self.x, self.y
        for i in range(1, steps + 1):
            t = i / steps
            e = t * t * (3 - 2 * t)
            self.x, self.y = x0 + (x - x0) * e, y0 + (y - y0) * e
            await self.page.mouse.move(self.x, self.y)
            await self._sync_cursor()

    async def point(self, locator, ms: int = 700, dx: float = 0.5, dy: float = 0.5):
        await locator.scroll_into_view_if_needed()
        box = await locator.bounding_box()
        await self.move(box["x"] + box["width"] * dx, box["y"] + box["height"] * dy, ms)
        return box

    async def click(self, locator, pause: float = PAUSE, dx: float = 0.5, dy: float = 0.5):
        await self.point(locator, dx=dx, dy=dy)
        await self.page.evaluate(f"window.__ripple({self.x},{self.y})")
        await self.page.mouse.click(self.x, self.y)
        await self.wait(pause)

    async def highlight(self, locator, ms: int = 1800, pause: float = PAUSE):
        await locator.evaluate(f"(el) => window.__highlight(el, {ms})")
        await self.wait(pause)

    async def highlight_card(self, locator, ms: int = 1800, pause: float = PAUSE):
        """Highlight the bordered card that contains `locator`."""
        await locator.evaluate("(el, ms) => window.__highlight(el.closest('div[class*=\"border\"]') || el, ms)", ms)
        await self.wait(pause)

    async def scroll_to(self, locator=None, y: float | None = None, ms: int = 1800, offset: int = NAV_OFFSET):
        if locator is not None:
            y = await locator.evaluate("(el, off) => el.getBoundingClientRect().top + window.scrollY - off", offset)
        await self.page.evaluate(f"window.__smoothScroll({y}, {ms})")  # resolves when the scroll ends
        await self._sync_cursor()

    async def scroll_by(self, dy: float, ms: int = 1800):
        y = await self.page.evaluate("window.scrollY")
        await self.scroll_to(y=y + dy, ms=ms)

    async def goto(self, path: str):
        await self.page.goto(BASE + path, wait_until="networkidle")
        await self.page.wait_for_timeout(600)
        await self._sync_cursor()

    async def type(self, locator, text: str):
        await self.click(locator, pause=0.3)
        await locator.press_sequentially(text, delay=70)
        await self.wait(0.6)


def heading(page, text):
    return page.locator("h1,h2,h3", has_text=re.compile(text, re.I)).first


async def shoot(d: Director):
    page = d.page

    # 0:00-0:20 Inbox, open the case_002 email, scroll slowly through the buyer's message
    d.segment("01_inbox_email", "Inbox, open the revised PO, read the buyer's email")
    await d.goto("/inbox")
    await d.wait(1.5)
    row = page.get_by_text("REVISED PO NW-45120 Rev.1", exact=False).first
    await d.point(row)
    await d.highlight(row, 1300, pause=1.0)
    await d.click(row)
    await page.wait_for_load_state("networkidle")
    await d.scroll_to(heading(page, "^email$"), ms=3600)
    await d.wait(1.6)
    await d.scroll_by(420, ms=3200)
    await d.wait(1.4)

    # 0:20-0:55 Extracted fields with confidence and quotes, then the change list on the order
    d.segment("02_fields_changes", "Extracted fields, then the changes between PO versions")
    await d.scroll_to(heading(page, "Extracted order data"), ms=3000)
    await d.wait(1.2)
    for label in ("Total quantity", "Delivery date"):
        field = page.locator("tr", has_text=label).first
        await d.point(field, ms=600)
        await d.highlight(field, 1800, pause=1.9)
    await d.scroll_by(380, ms=3000)
    await d.wait(1.8)
    await d.scroll_to(y=0, ms=2000)
    await d.click(page.get_by_role("link", name=re.compile("View order")))
    await page.wait_for_load_state("networkidle")
    await d.scroll_to(heading(page, "Version history"), ms=3000)
    await d.wait(1.0)
    for label in ("Total quantity", "Delivery date", "Navy"):
        change = page.locator("div", has_text=re.compile(label)).filter(has=page.locator("text=→")).last
        await d.point(change, ms=600)
        await d.highlight(change, 1900, pause=2.0)
    await d.wait(1.0)

    # 0:55-1:10 Risk card and trace
    d.segment("03_risk_trace", "Risk card: 4,186 pcs short, judged by Nemotron Ultra; the trace")
    await d.goto("/emails/2")
    await d.scroll_to(heading(page, "Risk assessment"), ms=1200)
    badge = page.get_by_text("Judged by Nemotron Ultra").first
    await d.point(badge, ms=500)
    await d.highlight(badge.locator(".."), 1500, pause=1.4)
    short = page.locator("li", has_text="4,186").first
    await d.point(short, dx=0.35, ms=500)
    await d.highlight(short, 1500, pause=1.4)
    await d.scroll_to(heading(page, "Agent trace"), ms=1400)
    step = page.locator("button", has_text="Check delivery feasibility").first
    await d.click(step, pause=2.2)
    await d.click(step, pause=0.3)

    # 1:10-1:20 Compliance check with its Tavily sources
    d.segment("04_compliance_tavily", "Compliance check: Tavily web search with its sources")
    tavily = page.locator("button", has_text="Check compliance (Tavily)").first
    await d.scroll_to(tavily, ms=1000, offset=160)
    await d.click(tavily, pause=0.6)
    await d.scroll_by(330, ms=1200)
    url = page.get_by_text("collectivestudioltd.com", exact=False).first
    await d.point(url, dx=0.4, ms=500)
    await d.highlight(url, 1500, pause=1.6)
    await d.click(tavily, pause=0.3)
    comp = page.locator("li, div", has_text="Germany requires EU textile labelling").last
    await d.scroll_to(comp, ms=1400, offset=300)
    await d.point(comp, dx=0.3, ms=500)
    await d.highlight(comp, 1400, pause=1.3)

    # 1:20-1:35 Draft reply with the Python-computed options and the fact check
    d.segment("05_draft_reply", "Draft reply: two delivery options computed in Python, fact check passed")
    await d.scroll_to(page.get_by_text("Reply to buyer").first, ms=2800, offset=110)
    check = page.get_by_text("Fact check passed").first
    await d.point(check, dx=0.3, ms=600)
    await d.highlight(check, 2000, pause=2.1)
    options = page.get_by_text("Ship the full quantity by the earliest feasible date").first
    await d.point(options, dx=0.3, ms=700)
    await d.highlight(options.locator(".."), 3400, pause=3.5)
    await d.scroll_by(-120, ms=1500)
    await d.wait(1.0)

    # Approve the reply (part of 1:35-1:50 in the shot list)
    d.segment("06_approve", "Approve the reply (nothing is emailed)")
    name = page.get_by_placeholder("your name").first
    await d.type(name, "Demo reviewer")
    await d.click(page.get_by_role("button", name="Approve and mark sent").first)

    # 1:50-2:10 in the shot list, filmed before the decision: after a split decision the
    # profile cards show the split plan, so the Tiruppur-vs-Dhaka contrast is filmed first.
    d.segment("07_profiles", "Factory profiles: Tiruppur infeasible, Dhaka feasible")
    await d.goto("/orders/1")
    await d.scroll_to(heading(page, "Factory profile"), ms=2800)
    bad = page.get_by_text(re.compile(r"^infeasible$", re.I)).first
    good = page.get_by_text(re.compile(r"^feasible$", re.I)).first
    await d.point(bad, ms=700)
    await d.highlight_card(bad, 2400, pause=2.4)
    await d.point(good, ms=800)
    await d.highlight_card(good, 2400, pause=2.4)
    await d.click(page.get_by_role("button", name="Use this profile"), pause=2.2)
    await d.click(page.get_by_role("button", name="Use this profile"), pause=1.2)

    # 1:35-1:50 Record the split decision, generate documents, open the invoice
    d.segment("08_decision_documents", "Record the split shipment, generate the invoice and packing list")
    await d.scroll_to(y=0, ms=1200)
    await d.click(page.get_by_text("Split shipment", exact=False).first, pause=0.8)
    reviewer = page.get_by_placeholder("your name").first
    if not (await reviewer.input_value()):
        await d.type(reviewer, "Demo reviewer")
    await d.click(page.get_by_role("button", name="Record buyer decision"))
    await page.wait_for_load_state("networkidle")
    gen = page.get_by_role("button", name="Generate documents")
    await d.click(gen, pause=0.3)
    link = page.locator('a[href*="/api/documents/"]').first
    await link.wait_for(timeout=30000)
    await d.wait(1.2)
    await d.point(link, ms=500)
    await d.highlight(link.locator(".."), 1200, pause=0.5)
    await d.page.evaluate(f"window.__ripple({d.x},{d.y})")
    await d.wait(0.5)
    pdf = await page.request.get(urljoin(BASE, await link.get_attribute("href")))
    await show_pdf(d, await pdf.body(), "Commercial Invoice (PDF)")

    # 2:10-2:40 How it works
    d.segment("09_how_it_works", "How it works: routing and measured numbers")
    await d.goto("/about")
    await d.wait(2.0)
    height = await page.evaluate("document.documentElement.scrollHeight - innerHeight")
    await d.scroll_to(y=height * 0.45, ms=8500)
    await d.wait(2.8)
    await d.scroll_to(y=height, ms=8500)
    await d.wait(3.2)

    # 2:40-2:50 Dashboard
    d.segment("10_dashboard", "Dashboard: the closing shot")
    await d.goto("/")
    await d.move(760, 300, 700)
    await d.wait(3.8)
    d.segment("end", "end")


async def show_pdf(d: Director, data: bytes, title: str):
    """Headless Chromium has no PDF viewer: show the PDF's first page, rendered at full size."""
    import pypdfium2

    pdf = pypdfium2.PdfDocument(data)
    image = pdf[0].render(scale=2.2).to_pil()
    from io import BytesIO
    buf = BytesIO()
    image.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    await d.page.set_content(f"""<!doctype html><html><head><title>{title}</title></head>
      <body style="margin:0;background:#525659;font-family:system-ui">
      <div style="position:sticky;top:0;background:#323639;color:#eee;padding:12px 24px;font-size:15px">{title}</div>
      <img src="data:image/png;base64,{b64}"
        style="display:block;margin:24px auto;width:900px;box-shadow:0 4px 18px rgba(0,0,0,.5)"></body></html>""")
    await d.page.evaluate(OVERLAY)
    await d._sync_cursor()
    await d.wait(1.8)
    await d.scroll_to(y=420, ms=2400, offset=0)
    await d.wait(1.6)


async def main():
    OUT.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": 1536, "height": 864}, device_scale_factor=1.25)
        await context.add_init_script(OVERLAY)
        page = await context.new_page()
        cdp = await context.new_cdp_session(page)
        d = Director(page, cdp)
        cdp.on("Page.screencastFrame", lambda params: asyncio.ensure_future(d.on_frame(params)))
        await page.goto(BASE + "/inbox", wait_until="networkidle")
        await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080, "everyNthFrame": 1})
        d.wall0 = time.time()
        await page.wait_for_timeout(300)
        try:
            await shoot(d)
        finally:
            await page.wait_for_timeout(500)
            await cdp.send("Page.stopScreencast")
            await page.wait_for_timeout(300)
            timeline = {"frames": [{"t": round(ts - d.wall0, 3), "file": f} for ts, f in d.frames],
                        "segments": d.segments, "wall_seconds": round(d.now(), 2)}
            (OUT / "timeline.json").write_text(json.dumps(timeline, indent=1))
            print(f"{len(d.frames)} frames, {timeline['wall_seconds']} s", flush=True)
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
