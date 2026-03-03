"""
RegWatch Nexus — Dashboard Routes (Pro+ only)
Personalised compliance dashboard, actions, health score, gap analysis.
"""
import json
import logging
from flask import Blueprint, jsonify, request, g
from supabase_client import supabase_service
from pipeline.plan_filter import require_plan, get_user_from_request

bp = Blueprint('dashboard', __name__)
logger = logging.getLogger(__name__)


@bp.route('/', methods=['GET'])
@require_plan('pro', 'enterprise')
def get_dashboard():
    """Pro/Enterprise personalised dashboard data."""
    user = g.user
    client_id = user.get('client_id') or user.get('sub')

    # Health score
    health = supabase_service.table('health_scores')\
        .select('*').eq('client_id', client_id)\
        .order('calculated_at', desc=True).limit(1).execute()

    # Open critical actions
    open_actions = supabase_service.table('compliance_actions')\
        .select('*')\
        .eq('client_id', client_id)\
        .eq('status', 'todo')\
        .order('due_date').limit(10).execute()

    # Recent personalised alerts
    impact_reports = supabase_service.table('impact_reports')\
        .select('*, alerts(id,title,severity,regulator,jurisdiction,published_at)')\
        .eq('client_id', client_id)\
        .order('created_at', desc=True)\
        .limit(20).execute()

    # Upcoming deadlines (next 60 days)
    upcoming = supabase_service.table('compliance_actions')\
        .select('*, alerts(title,regulator,regulatory_deadline)')\
        .eq('client_id', client_id)\
        .neq('status', 'done')\
        .order('due_date').limit(20).execute()

    return jsonify({
        'health_score': health.data[0] if health.data else {'score': 75, 'trend': 'stable'},
        'open_actions': open_actions.data,
        'impact_reports': impact_reports.data,
        'upcoming_deadlines': upcoming.data,
    })


@bp.route('/actions', methods=['GET'])
@require_plan('pro', 'enterprise')
def get_actions():
    user = g.user
    client_id = user.get('client_id') or user.get('sub')
    status = request.args.get('status')

    q = supabase_service.table('compliance_actions')\
        .select('*').eq('client_id', client_id)
    if status:
        q = q.eq('status', status)
    result = q.order('due_date').execute()
    return jsonify({'actions': result.data})


@bp.route('/actions', methods=['POST'])
@require_plan('pro', 'enterprise')
def create_action():
    user = g.user
    client_id = user.get('client_id') or user.get('sub')
    data = request.get_json() or {}

    action = {
        'client_id': client_id,
        'alert_id': data.get('alert_id'),
        'title': data.get('title', ''),
        'description': data.get('description', ''),
        'owner_team': data.get('owner_team', ''),
        'assignee': data.get('assignee', ''),
        'status': 'todo',
        'due_date': data.get('due_date'),
        'notes': data.get('notes', ''),
    }
    result = supabase_service.table('compliance_actions').insert(action).execute()
    return jsonify({'action': result.data[0]}), 201


@bp.route('/actions/<action_id>', methods=['PUT'])
@require_plan('pro', 'enterprise')
def update_action(action_id):
    user = g.user
    client_id = user.get('client_id') or user.get('sub')
    data = request.get_json() or {}

    allowed = ['status', 'notes', 'assignee', 'due_date', 'owner_team', 'title']
    updates = {k: v for k, v in data.items() if k in allowed}

    supabase_service.table('compliance_actions')\
        .update(updates)\
        .eq('id', action_id)\
        .eq('client_id', client_id)\
        .execute()
    return jsonify({'ok': True})


@bp.route('/policies', methods=['GET'])
@require_plan('pro', 'enterprise')
def get_policies():
    user = g.user
    client_id = user.get('client_id') or user.get('sub')
    result = supabase_service.table('policy_documents')\
        .select('*').eq('client_id', client_id).execute()
    return jsonify({'policies': result.data})


@bp.route('/ask', methods=['POST'])
@require_plan('pro', 'enterprise')
def ask_intelligence():
    """Natural language compliance question. Pro/Enterprise only."""
    import anthropic
    from config import config

    user = g.user
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    if not question:
        return jsonify({'error': 'Question required'}), 400

    # Get relevant alerts for context
    recent_alerts = supabase_service.table('alerts')\
        .select('title,summary,regulator,jurisdiction,severity,regulatory_deadline')\
        .eq('validation_status', 'approved')\
        .order('published_at', desc=True)\
        .limit(20).execute()

    context = '\n\n'.join([
        f"ALERT: {a['title']}\nREGULATOR: {a['regulator']} ({a['jurisdiction']})\n"
        f"SEVERITY: {a['severity']}\nSUMMARY: {str(a.get('summary',''))[:400]}"
        for a in (recent_alerts.data or [])
    ])

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    model = config.ANTHROPIC_MODEL_PREMIUM if user.get('plan') == 'enterprise' else config.ANTHROPIC_MODEL_STANDARD

    response = client.messages.create(
        model=model,
        max_tokens=1500,
        system="""You are a senior compliance intelligence expert. Answer the user's question 
        using the regulatory context provided. Be specific, cite the relevant regulations, 
        and provide actionable guidance. Never use the words 'AI', 'model', or 'generated'.""",
        messages=[{
            'role': 'user',
            'content': f"Recent regulatory context:\n{context}\n\nQuestion: {question}"
        }]
    )

    # Log query for audit trail
    supabase_service.table('ask_intelligence_log').insert({
        'user_id': user.get('sub'),
        'question': question,
        'plan': user.get('plan'),
    }).execute()

    return jsonify({
        'answer': response.content[0].text,
        'sources': [a['regulator'] for a in (recent_alerts.data or [])[:5]],
    })


@bp.route('/health-history', methods=['GET'])
@require_plan('pro', 'enterprise')
def get_health_history():
    user = g.user
    client_id = user.get('client_id') or user.get('sub')
    result = supabase_service.table('health_scores')\
        .select('score,trend,calculated_at')\
        .eq('client_id', client_id)\
        .order('calculated_at', desc=True)\
        .limit(90).execute()
    return jsonify({'history': result.data})
