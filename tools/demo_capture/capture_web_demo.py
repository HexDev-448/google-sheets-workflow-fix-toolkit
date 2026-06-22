from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path


async def capture(url: str, output: Path) -> None:
    from playwright.async_api import async_playwright

    output.parent.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        browser = await launch_browser(playwright)
        page = await browser.new_page(viewport={"width": 1440, "height": 1100})
        await page.goto(url, wait_until="domcontentloaded")
        await page.get_by_text("Google Sheets Workflow Fix Toolkit").wait_for(
            timeout=30000
        )
        await page.wait_for_timeout(1500)
        await page.screenshot(path=str(output), full_page=True)
        await browser.close()


async def launch_browser(playwright):
    try:
        return await playwright.chromium.launch()
    except Exception:
        chromium_path = find_local_chromium()
        if chromium_path is None:
            raise
        return await playwright.chromium.launch(executable_path=str(chromium_path))


def find_local_chromium() -> Path | None:
    search_roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright",
        Path.home() / "AppData" / "Local" / "ms-playwright",
    ]
    for root in search_roots:
        if not root.exists():
            continue
        matches = sorted(root.glob("chromium-*/chrome-win64/chrome.exe"), reverse=True)
        if matches:
            return matches[0]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture the local Streamlit demo.")
    parser.add_argument("--url", default="http://localhost:8501")
    parser.add_argument(
        "--output",
        default="screenshots/workflow-preview.png",
        help="Screenshot output path.",
    )
    args = parser.parse_args()
    asyncio.run(capture(args.url, Path(args.output)))


if __name__ == "__main__":
    main()
