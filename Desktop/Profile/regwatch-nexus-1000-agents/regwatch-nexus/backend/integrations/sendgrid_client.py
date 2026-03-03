"""
RegWatch Nexus — SendGrid Email Integration
Sends alert notifications and weekly digests to Registered+ users.
"""
import logging
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content
from config import config

logger = logging.getLogger(__name__)
sg = SendGridAPIClient(config.SENDGRID_API_KEY)


def send_alert_email(to_email: str, alert: dict, plan: str = 'free'):
    """Send a single alert notification email."""
    severity_emoji = {
        'critical': '🔴',
        'high': '🟠',
        'medium': '🟡',
        'info': '🔵',
    }.get(alert.get('severity', 'medium'), '🔵')

    subject = f"{severity_emoji} {alert.get('severity', '').upper()}: {alert.get('title', '')[:80]}"

    html_body = f"""
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><style>
body {{font-family: 'Georgia', serif; max-width: 620px; margin: 0 auto; color: #0A0C0F; background: #F4F1EC;}}
.header {{background: #0A0C0F; padding: 24px 32px; border-bottom: 2px solid #C9A84C;}}
.brand {{color: #C9A84C; font-size: 18px; font-weight: bold; letter-spacing: 0.05em;}}
.badge {{display: inline-block; padding: 4px 12px; font-size: 11px; font-family: monospace; letter-spacing: 0.1em; margin: 16px 32px;}}
.critical {{background: rgba(192,57,43,0.1); color: #C0392B; border: 1px solid #C0392B;}}
.high {{background: rgba(125,60,0,0.1); color: #7D3C00; border: 1px solid #7D3C00;}}
.medium {{background: rgba(139,105,20,0.1); color: #8B6914; border: 1px solid #8B6914;}}
.info {{background: rgba(44,74,107,0.1); color: #2C4A6B; border: 1px solid #2C4A6B;}}
h1 {{font-size: 22px; line-height: 1.3; margin: 0 32px 8px; color: #0A0C0F;}}
.meta {{font-family: monospace; font-size: 11px; color: #9A948E; margin: 4px 32px 20px;}}
.summary {{font-size: 13px; line-height: 1.8; margin: 0 32px 24px; color: #6B6560;}}
.cta {{display: block; background: #C9A84C; color: #0A0C0F; text-decoration: none; padding: 14px 28px; margin: 0 32px 32px; text-align: center; font-family: monospace; font-size: 11px; letter-spacing: 0.15em;}}
.footer {{padding: 20px 32px; border-top: 1px solid rgba(10,12,15,0.1); font-size: 10px; color: #9A948E; font-family: monospace;}}
</style></head>
<body>
<div class="header"><div class="brand">RegWatch Nexus</div></div>
<div class="badge {alert.get('severity', 'info')}">{alert.get('severity', '').upper()} · IMPACT {alert.get('base_impact_score', 5.0)}/10</div>
<h1>{alert.get('title', '')}</h1>
<div class="meta">{alert.get('regulator', '')} · {alert.get('jurisdiction', '')} · {str(alert.get('published_at', ''))[:10]}</div>
<div class="summary">{str(alert.get('summary', ''))[:600]}...</div>
<a class="cta" href="https://regwatchnexus.com/alerts/{alert.get('id', '')}">VIEW FULL ANALYSIS →</a>
<div class="footer">
RegWatch Nexus · Compliance Intelligence · <a href="https://regwatchnexus.com/unsubscribe">Unsubscribe</a>
</div>
</body>
</html>"""

    message = Mail(
        from_email=Email(config.SENDGRID_FROM_EMAIL, config.SENDGRID_FROM_NAME),
        to_emails=To(to_email),
        subject=subject,
        html_content=Content('text/html', html_body)
    )

    try:
        sg.send(message)
        logger.info(f"[SendGrid] Alert email sent to {to_email}")
    except Exception as e:
        logger.error(f"[SendGrid] Failed to send to {to_email}: {e}")


def send_weekly_digest(to_email: str, alerts: list):
    """Send weekly digest email to Free Registered users."""
    rows = ''
    for a in alerts[:10]:
        sev = a.get('severity', 'info')
        color = {'critical': '#C0392B', 'high': '#7D3C00', 'medium': '#8B6914', 'info': '#2C4A6B'}.get(sev, '#2C4A6B')
        rows += f"""
<tr>
  <td style="padding:12px;border-bottom:1px solid #E4DFD6;font-size:12px;">
    <span style="color:{color};font-family:monospace;font-size:10px">{sev.upper()}</span><br>
    <strong>{a.get('title','')[:90]}</strong><br>
    <span style="color:#9A948E;font-family:monospace;font-size:10px">{a.get('regulator','')} · {a.get('jurisdiction','')}</span>
  </td>
</tr>"""

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
<body style="font-family:Georgia,serif;max-width:620px;margin:0 auto;background:#F4F1EC;color:#0A0C0F">
<div style="background:#0A0C0F;padding:20px 32px;border-bottom:2px solid #C9A84C">
  <span style="color:#C9A84C;font-size:18px;font-weight:bold">RegWatch Nexus</span>
  <span style="color:rgba(244,241,236,0.5);font-family:monospace;font-size:10px;margin-left:16px">WEEKLY DIGEST</span>
</div>
<div style="padding:24px 32px">
<h2 style="font-size:20px">This week's regulatory intelligence</h2>
<table style="width:100%;border-collapse:collapse;border:1px solid #E4DFD6">{rows}</table>
<a href="https://regwatchnexus.com" style="display:block;background:#C9A84C;color:#0A0C0F;padding:14px;text-align:center;text-decoration:none;font-family:monospace;font-size:11px;letter-spacing:0.15em;margin-top:24px">VIEW ALL ALERTS →</a>
</div>
<div style="padding:16px 32px;border-top:1px solid rgba(10,12,15,0.1);font-size:10px;color:#9A948E;font-family:monospace">
RegWatch Nexus · <a href="https://regwatchnexus.com/unsubscribe">Unsubscribe</a>
</div>
</body></html>"""

    message = Mail(
        from_email=Email(config.SENDGRID_FROM_EMAIL, config.SENDGRID_FROM_NAME),
        to_emails=To(to_email),
        subject=f"RegWatch Nexus — Weekly Digest: {len(alerts)} new regulatory alerts",
        html_content=Content('text/html', html)
    )
    try:
        sg.send(message)
    except Exception as e:
        logger.error(f"[SendGrid] Digest failed for {to_email}: {e}")
