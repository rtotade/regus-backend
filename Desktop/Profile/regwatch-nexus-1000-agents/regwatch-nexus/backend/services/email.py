"""Email delivery via SendGrid"""
import asyncio
from typing import Optional
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
from backend.config import settings


def send_email(to_email: str, subject: str, html_content: str, 
               from_email: Optional[str] = None) -> bool:
    if not settings.SENDGRID_API_KEY:
        print(f"[EMAIL] Would send to {to_email}: {subject}")
        return True
    try:
        sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        message = Mail(
            from_email=Email(from_email or settings.SENDGRID_FROM_EMAIL, 
                           settings.SENDGRID_FROM_NAME),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_content),
        )
        sg.send(message)
        return True
    except Exception as e:
        print(f"[EMAIL ERROR] {e}")
        return False


def send_welcome_email(email: str, name: str) -> bool:
    subject = f"Welcome to RegWatch Nexus"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
      <h2 style="color:#C9A84C">Welcome to RegWatch Nexus</h2>
      <p>Hi {name or "there"},</p>
      <p>Your account is active. You now have access to:</p>
      <ul>
        <li>Full live regulatory alert feed</li>
        <li>Save filters and watchlist (up to 5 regulators)</li>
        <li>Weekly intelligence digest</li>
      </ul>
      <p>Ready to upgrade to Pro for full analysis and action tracking?</p>
      <a href="https://app.regwatchnexus.com/pricing" 
         style="background:#C9A84C;color:#000;padding:12px 24px;text-decoration:none;display:inline-block;margin-top:16px">
        View Pro Plans
      </a>
    </div>"""
    return send_email(email, subject, html)


def send_alert_email(email: str, alert: dict) -> bool:
    severity_color = {"critical": "#C0392B", "high": "#7D3C00", 
                      "medium": "#C9A84C", "info": "#2C4A6B"}.get(alert.get("severity",""), "#666")
    subject = f"[{alert.get('severity','').upper()}] {alert.get('regulator','')} — {alert.get('title','')[:80]}"
    html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#0A0C0F;padding:16px;border-bottom:2px solid #C9A84C">
        <span style="color:#C9A84C;font-size:18px;font-weight:bold">RegWatch Nexus</span>
        <span style="float:right;background:{severity_color};color:white;padding:3px 10px;font-size:12px">
          {alert.get("severity","").upper()}
        </span>
      </div>
      <div style="padding:24px">
        <p style="font-size:11px;color:#666;font-family:monospace">{alert.get("regulator","")} · {alert.get("jurisdiction","")}</p>
        <h3 style="font-size:20px;margin-bottom:12px">{alert.get("title","")}</h3>
        <p style="color:#444;line-height:1.7">{alert.get("summary","")[:500]}...</p>
        <a href="https://app.regwatchnexus.com/alerts/{alert.get('id','')}"
           style="background:#0A0C0F;color:#C9A84C;padding:10px 20px;text-decoration:none;display:inline-block;margin-top:16px">
          View Full Alert →
        </a>
      </div>
    </div>"""
    return send_email(email, subject, html)
