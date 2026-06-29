PACKAGE_TEMPLATES = {
    "demo": {"label": "Demo", "allowed_pages": ["dashboard", "market", "reports"], "max_paper_models": 5, "real_approval": False, "rule_editor": False},
    "paper_lab": {"label": "Paper Lab", "allowed_pages": ["dashboard", "market", "coinFilter", "strategies", "reports"], "max_paper_models": 25, "real_approval": False, "rule_editor": False},
    "pro": {"label": "Pro", "allowed_pages": ["dashboard", "market", "coinFilter", "strategies", "reports", "settings"], "max_paper_models": 60, "real_approval": True, "rule_editor": False},
    "owner": {"label": "Owner", "allowed_pages": ["*"], "max_paper_models": 250, "real_approval": True, "rule_editor": True},
}


def normalize_package(package_id: str, role: str = "user") -> dict:
    if role == "owner":
        package_id = "owner"
    package_id = package_id if package_id in PACKAGE_TEMPLATES else "demo"
    payload = dict(PACKAGE_TEMPLATES[package_id])
    payload["id"] = package_id
    return payload


def can_access_page(package_id: str, role: str, page: str) -> bool:
    package = normalize_package(package_id, role)
    pages = package.get("allowed_pages") or []
    return "*" in pages or page in pages


def package_limits(package_id: str, role: str = "user") -> dict:
    package = normalize_package(package_id, role)
    return {
        "package_id": package.get("id"),
        "label": package.get("label"),
        "allowed_pages": package.get("allowed_pages", []),
        "max_paper_models": int(package.get("max_paper_models") or 0),
        "real_approval": bool(package.get("real_approval")),
        "rule_editor": bool(package.get("rule_editor")),
    }
