from __future__ import annotations

from network.email_finder import HunterEmailFinder


def _canned_hunter_payload() -> dict:
    return {
        "data": {
            "domain": "acme.com",
            "emails": [
                {"value": "recruiter@acme.com", "first_name": "Jane", "last_name": "Doe",
                 "position": "Technical Recruiter", "department": "hr", "confidence": 90},
                {"value": "em@acme.com", "first_name": "Sam", "last_name": "Lee",
                 "position": "Engineering Manager", "department": "engineering", "confidence": 80},
                {"value": "swe@acme.com", "first_name": "Alex", "last_name": "Chen",
                 "position": "Software Engineer", "department": "engineering", "confidence": 70},
            ],
        }
    }


def _fake_http_get(url: str) -> dict:
    return _canned_hunter_payload()


def test_find_people_returns_recruiter_and_manager():
    contacts = HunterEmailFinder("k", http_get=_fake_http_get).find_people("Acme")
    assert len(contacts) == 2
    recruiter = next(c for c in contacts if c.role_type == "recruiter")
    manager = next(c for c in contacts if c.role_type == "hiring_manager")
    assert recruiter.email == "recruiter@acme.com"
    assert manager.email == "em@acme.com"


def test_swe_excluded():
    contacts = HunterEmailFinder("k", http_get=_fake_http_get).find_people("Acme")
    assert "swe@acme.com" not in [c.email for c in contacts]


def test_max_each_keeps_highest_confidence():
    payload = _canned_hunter_payload()
    payload["data"]["emails"].append(
        {"value": "recruiter2@acme.com", "first_name": "Bob", "last_name": "Smith",
         "position": "Senior Recruiter", "department": "hr", "confidence": 85}
    )
    finder = HunterEmailFinder("k", http_get=lambda url: payload)
    recruiters = [c for c in finder.find_people("Acme", max_each=1) if c.role_type == "recruiter"]
    assert len(recruiters) == 1
    assert recruiters[0].email == "recruiter@acme.com"  # confidence 90 > 85


def test_failed_request_returns_empty():
    def _fail(url: str) -> dict:
        raise RuntimeError("network down")

    assert HunterEmailFinder("k", http_get=_fail).find_people("Acme") == []
