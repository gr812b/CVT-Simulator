"""Optional browser/visual QA: install playwright and its Chromium first.

python -m tools.sliding_block_demo.check_browser path/to/sliding_block_explorer.html \
    --screenshots /tmp/sliding-section-qa
"""
from __future__ import annotations
import argparse
from pathlib import Path


def check(html: Path, screenshots: Path):
    from playwright.sync_api import sync_playwright
    screenshots.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1120}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(html.resolve().as_uri())
        page.wait_for_selector("#geometry svg")

        def set_control(name, value):
            page.locator(f"#{name}").evaluate("(e,v)=>{e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}));}", str(value))

        names = page.locator("#scenario option").evaluate_all("es=>es.map(e=>e.value)")
        assert len(names) >= 5
        for name in names:
            page.select_option("#scenario", name)
            fixed_paths = None
            for index in (0, 38, 75):
                set_control("closure", index)
                current = page.evaluate("""()=>{
                    const name=document.getElementById('scenario').value;
                    const p=SCENES[name].points[Number(document.getElementById('closure').value)];
                    return {valid:p.section.pose_valid,issues:p.section.issues,com:p.section.com,
                            belt:p.section.belt,frame:p.section.x_mm};
                }""")
                assert not current["issues"], (name, index, current["issues"])
                assert page.locator('#geometry [data-part="Sliding weight"]').count() == int(current["valid"])
                assert "NaN" not in page.locator("#geometry").inner_html()
                assert "undefined" not in page.locator("#geometry").inner_html()
                fixed = [page.locator(f'#geometry [data-part="{part}"]').get_attribute("d")
                         for part in ("Shaft", "Reaction cup", "Fixed sheave")]
                if fixed_paths is None:
                    fixed_paths = fixed
                else:
                    assert fixed == fixed_paths, (name, "fixed bodies moved")
                assert page.locator("#status").inner_text().startswith("PASS") == current["valid"]
                page.locator(".section-panel").screenshot(path=str(screenshots/f"{name}-{index:02}.png"))

        page.select_option("#scenario", "both-curved")
        set_control("closure", 40)
        set_control("rpm", 250)
        set_control("accel", 200)
        assert "liftoff" in page.locator("#status").inner_text()
        assert page.locator('#geometry [data-part="Sliding weight"]').count() == 1
        page.locator(".section-layout").screenshot(path=str(screenshots/"liftoff.png"))
        set_control("accel", 0)
        assert page.locator("#status").inner_text().startswith("PASS")
        shape_before = page.locator('#geometry [data-part="Sliding weight"]').get_attribute("d")
        set_control("mass", .5)
        half = float(page.locator("#force").inner_text().split()[0])
        set_control("mass", 1)
        full = float(page.locator("#force").inner_text().split()[0])
        assert abs(full-2*half) <= .11
        assert page.locator('#geometry [data-part="Sliding weight"]').get_attribute("d") == shape_before
        page.locator("#contacts-toggle").uncheck()
        page.locator("#path-toggle").uncheck()
        assert page.locator('#geometry [data-part="Sliding weight"]').get_attribute("d") == shape_before
        page.locator("#contacts-toggle").check()
        page.locator("#path-toggle").check()
        set_control("mass", .75)
        set_control("rpm", 750)
        set_control("closure", 0)
        page.screenshot(path=str(screenshots/"desktop.png"), full_page=True)
        page.set_viewport_size({"width":390,"height":844})
        page.wait_for_function("document.documentElement.scrollWidth <= window.innerWidth", timeout=5000)
        page.screenshot(path=str(screenshots/"mobile.png"), full_page=True)
        assert not errors, errors
        browser.close()
        print(f"Browser PASS: {len(names)} samples × 3 positions; fixed bodies, invalid poses, liftoff, mass scaling, toggles, mobile overflow; no JavaScript errors.")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html",type=Path)
    parser.add_argument("--screenshots",type=Path,default=Path("sliding_block_outputs/browser_qa"))
    args=parser.parse_args()
    check(args.html,args.screenshots)


if __name__=="__main__":
    main()
