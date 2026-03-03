"""Plan-level access control — strips Pro+ fields for lower-tier users"""
from backend.config import settings

PRO_PLANS = {settings.PLAN_PRO, settings.PLAN_ENTERPRISE}
REGISTERED_PLANS = {settings.PLAN_FREE, settings.PLAN_PRO, settings.PLAN_ENTERPRISE}

ALERT_RESTRICTED_FIELDS = ["full_analysis", "recommended_actions", "financial_exposure",
                             "engineering_weeks", "cascade_risk_score"]

def filter_alert(alert: dict, plan: str) -> dict:
    if plan in PRO_PLANS:
        return alert
    filtered = {k: v for k, v in alert.items() if k not in ALERT_RESTRICTED_FIELDS}
    filtered["_pro_upgrade"] = True
    return filtered

def filter_synthesis(synthesis: dict, plan: str) -> dict:
    if plan in PRO_PLANS:
        return synthesis
    return {k: v for k, v in synthesis.items() if k != "full_synthesis"}

def can_access_dashboard(plan: str) -> bool:
    return plan in PRO_PLANS

def can_access_counsel(plan: str) -> bool:
    return plan in PRO_PLANS

def can_access_gap_analysis(plan: str) -> bool:
    return plan in PRO_PLANS
