from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, PostLog
from app.services.instagram import InstagramAPIError, client_from_account


def check_account_health(db: Session, account: Account) -> dict:
    result = {
        "status": "healthy",
        "message": "Conta operacional",
        "token_valid": False,
        "api_limit": None,
        "recent_failures": 0,
    }

    if not (account.session_json or "").strip():
        account.health_status = "error"
        account.health_message = "Conta sem sessão — faça login (sessionid ou senha)"
        return {
            **result,
            "status": "error",
            "message": account.health_message,
        }

    try:
        client = client_from_account(account)
        profile = client.get_profile()
        result["token_valid"] = True
        account.username = profile.get("username", account.username)
        result["profile"] = profile
    except InstagramAPIError as exc:
        account.health_status = "error"
        account.health_message = str(exc)
        return {
            **result,
            "status": "error",
            "message": str(exc),
        }

    recent_errors = (
        db.query(PostLog)
        .filter(PostLog.account_id == account.id, PostLog.status == "error")
        .order_by(PostLog.posted_at.desc())
        .limit(10)
        .all()
    )
    failures = len(recent_errors)
    result["recent_failures"] = failures or 0

    if result["recent_failures"] >= 3:
        account.health_status = "warning"
        account.health_message = f"{result['recent_failures']} falhas recentes"
        result["status"] = "warning"
        result["message"] = account.health_message
    else:
        account.health_status = "healthy"
        account.health_message = "Conta operacional"
        result["status"] = "healthy"

    return result


def refresh_account_insights(db: Session, account: Account) -> dict:
    try:
        client = client_from_account(account)
        insights = client.get_account_insights()
        totals = {"profile_views": 0, "reach": 0, "impressions": 0}
        for item in insights.get("data", []):
            name = item.get("name", "")
            values = item.get("values", [])
            value = values[-1].get("value", 0) if values else 0
            if name == "profile_views":
                totals["profile_views"] = value
            elif name == "reach":
                totals["reach"] = value
            elif name == "impressions":
                totals["impressions"] = value

        account.profile_views = totals["profile_views"]
        account.total_reach = totals["reach"]
        account.total_impressions = totals["impressions"]
        db.commit()
        return totals
    except InstagramAPIError as exc:
        return {"error": str(exc)}
