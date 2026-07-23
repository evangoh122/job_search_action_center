"""Visible-browser autofill for reviewed public application packages.

The browser boundary deliberately never clicks an employer's final Submit control.
"""
from __future__ import annotations

import logging
from pathlib import Path

from apply.ats import ApplicationPlan
from apply.resume_artifact import stage_approved_resume_pdf
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


class PlaywrightApplicationFiller:
    """Autofill an application and pause for the applicant's final review and submit."""
    def __init__(
        self,
        *,
        user_data_dir: str = "data/browser_profile",
        headless: bool = False,
        wait_for_user: bool = True,
        screenshot_dir: str = "data/application_screenshots",
    ) -> None:
        """Initialize the instance."""
        self.user_data_dir = user_data_dir
        self.headless = headless
        self.wait_for_user = wait_for_user
        self.screenshot_dir = Path(screenshot_dir)

    @staticmethod
    def _fill_locator(locator, value: str) -> bool:
        """Fill locator."""
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
        """Fill fields."""
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
        """Return whether  captcha."""
        selectors = "iframe[src*='captcha' i], [class*='captcha' i], [id*='captcha' i]"
        try:
            return page.locator(selectors).count() > 0
        except Exception:
            return False

    @staticmethod
    def _missing_required(page) -> list[str]:
        """Missing required."""
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
        """Screenshot."""
        try:
            self.screenshot_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(self.screenshot_dir / f"{job.id}.png"), full_page=True)
        except Exception:
            logger.debug("Could not capture application screenshot", exc_info=True)

    def __call__(self, job: Job, applicant: Applicant, plan: ApplicationPlan) -> str:
        """Execute the configured operation."""
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
                with stage_approved_resume_pdf(plan.resume_path, plan.resume_sha256) as resume:
                    upload = page.locator("input[type='file']")
                    if upload.count():
                        upload.first.set_input_files(str(resume))
            page.wait_for_timeout(1_000)
            self._screenshot(page, job)
            if self._has_captcha(page):
                context.close()
                return "captcha_required"
            if self._missing_required(page):
                context.close()
                return "review_required"

            # Keep the visible browser open while the human reviews every field and owns
            # the employer's final Submit action. Pressing Enter only closes our browser.
            if self.wait_for_user:
                try:
                    input("Review the form, submit it yourself if correct, then press Enter here to close: ")
                except EOFError:
                    pass
            self._screenshot(page, job)
            context.close()
            return "ready_for_manual_submit"


# Backward-compatible import name. It now has fill-only behavior.
PlaywrightSubmitter = PlaywrightApplicationFiller
