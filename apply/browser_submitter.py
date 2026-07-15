"""Optional Playwright autofill for public hosted application forms.

Playwright is imported lazily so the core tracker has no browser dependency. The submitter
only clicks Submit after AutoApplier has verified a per-job approval key.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from apply.ats import ApplicationPlan
from models import Applicant, Job

logger = logging.getLogger(__name__)


_FIELD_SELECTORS = {
    "first_name": ["input[name='first_name']", "input[id*='first_name' i]"],
    "last_name": ["input[name='last_name']", "input[id*='last_name' i]"],
    "name": ["input[name='name']", "input[autocomplete='name']"],
    "email": ["input[type='email']", "input[name='email']"],
    "phone": ["input[type='tel']", "input[name='phone']"],
    "linkedin": ["input[name*='linkedin' i]", "input[id*='linkedin' i]"],
    "github": ["input[name*='github' i]", "input[id*='github' i]"],
    "location": ["input[autocomplete*='address' i]", "input[name*='location' i]"],
    "current_company": ["input[name*='company' i]", "input[id*='company' i]"],
    "cover_letter": [
        "textarea[name*='cover' i]", "textarea[id*='cover' i]",
        "textarea[aria-label*='cover' i]",
    ],
}


class PlaywrightSubmitter:
    def __init__(
        self,
        *,
        user_data_dir: str = "data/browser_profile",
        headless: bool = False,
        submit: bool = True,
        screenshot_dir: str = "data/application_screenshots",
    ) -> None:
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.submit = submit
        self.screenshot_dir = Path(screenshot_dir)

    @staticmethod
    def _fill_locator(locator, value: str) -> bool:
        try:
            if locator.count() == 0:
                return False
            target = locator.first
            tag = target.evaluate("el => el.tagName.toLowerCase()")
            input_type = target.get_attribute("type") or ""
            if tag == "select":
                target.select_option(label=value)
            elif input_type in {"checkbox", "radio"}:
                if value.casefold() in {"yes", "true", "1", "checked"}:
                    target.check()
            else:
                target.fill(value)
            return True
        except Exception:
            return False

    def _fill_fields(self, page, plan: ApplicationPlan) -> set[str]:
        filled: set[str] = set()
        for key, value in plan.fields.items():
            for selector in _FIELD_SELECTORS.get(key, []):
                if self._fill_locator(page.locator(selector), value):
                    filled.add(key)
                    break
            if key in filled or key in _FIELD_SELECTORS:
                continue
            # User-provided answer keys are treated as visible label text.
            try:
                if self._fill_locator(page.get_by_label(key, exact=False), value):
                    filled.add(key)
            except Exception:
                pass
        return filled

    @staticmethod
    def _has_captcha(page) -> bool:
        selectors = "iframe[src*='captcha' i], [class*='captcha' i], [id*='captcha' i]"
        try:
            return page.locator(selectors).count() > 0
        except Exception:
            return False

    @staticmethod
    def _missing_required(page) -> list[str]:
        script = """els => els.filter(el => {
            if (el.disabled || el.offsetParent === null) return false;
            if ((el.type === 'checkbox' || el.type === 'radio')) return !el.checked;
            return !String(el.value || '').trim();
        }).map(el => el.getAttribute('aria-label') || el.name || el.id || el.type || 'field')"""
        try:
            return page.locator("input[required], textarea[required], select[required], [aria-required='true']").evaluate_all(script)
        except Exception:
            return ["unknown_required_fields"]

    def _screenshot(self, page, job: Job) -> None:
        try:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(self.screenshot_dir / f"{job.id}.png"), full_page=True)
        except Exception:
            logger.debug("Could not capture application screenshot", exc_info=True)

    def __call__(self, job: Job, applicant: Applicant, plan: ApplicationPlan) -> str:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "Browser automation requires: pip install -e '.[browser]' and playwright install chromium"
            ) from exc

        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                self.user_data_dir,
                headless=self.headless,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(plan.form_url, wait_until="domcontentloaded", timeout=60_000)
            self._fill_fields(page, plan)
            if plan.resume_path:
                resume = Path(plan.resume_path)
                if resume.exists():
                    upload = page.locator("input[type='file']")
                    if upload.count():
                        upload.first.set_input_files(str(resume.resolve()))
            page.wait_for_timeout(1_000)
            self._screenshot(page, job)
            if self._has_captcha(page):
                context.close()
                return "captcha_required"
            if self._missing_required(page) or not self.submit:
                context.close()
                return "review_required"

            submit = page.get_by_role("button", name="Submit", exact=False)
            if submit.count() == 0:
                submit = page.locator("button[type='submit'], input[type='submit']")
            if submit.count() == 0:
                context.close()
                return "review_required"
            submit.first.click()
            page.wait_for_timeout(2_000)
            confirmation = page.get_by_text(re.compile(
                r"application (?:has been )?(?:submitted|received)|thank you for applying",
                re.IGNORECASE,
            ))
            submitted = confirmation.count() > 0
            self._screenshot(page, job)
            context.close()
            return "submitted" if submitted else "review_required"
