"""
RegWatch Nexus — Public API Routes
NO authentication required. Open to all. Respects Supabase RLS.
"""
from flask import Blueprint, jsonify, request
from supabase_client import supabase_anon, supabase_service
from pipeline.plan_filter import get_plan_from_request, apply_plan_filter, apply_plan_filter_list
from agents.agent_21_22 import track_page_view

bp = Blueprint('public', __name__)


@bp.route('/alerts', methods=['GET'])
def get_alerts():
    """Public alert feed. No auth. Filterable by country, sector, severity."""
    plan = get_plan_from_request()
    country = request.args.get('country', 'IN')
    sector = request.args.get('sector')
    severity = request.args.get('severity')
    page = max(1, int(request.args.get('page', 1)))
    per_page = 20

    q = supabase_anon.table('alerts')\
        .select('id,regulator,jurisdiction,title,summary,severity,base_impact_score,'
                'topic_tags,affected_sectors,regulatory_deadline,source_url,'
                'seo_meta,view_count,published_at,full_analysis,recommended_actions,'
                'financial_exposure_usd,engineering_change_required')\
        .eq('validation_status', 'approved')\
        .order('published_at', desc=True)

    if country and country != 'GLOBAL':
        q = q.eq('jurisdiction', country)
    if severity:
        q = q.eq('severity', severity)

    result = q.range((page - 1) * per_page, page * per_page - 1).execute()

    alerts = apply_plan_filter_list(result.data, plan)

    return jsonify({
        'alerts': alerts,
        'page': page,
        'per_page': per_page,
        'count': len(alerts),
        'user_plan': plan,
    })


@bp.route('/alerts/<alert_id>', methods=['GET'])
def get_alert(alert_id):
    """Single alert detail. Public. Tracks view for trending."""
    plan = get_plan_from_request()
    session_id = request.headers.get('X-Session-Id', 'anon')

    result = supabase_anon.table('alerts')\
        .select('*')\
        .eq('id', alert_id)\
        .eq('validation_status', 'approved')\
        .single()\
        .execute()

    if not result.data:
        return jsonify({'error': 'Alert not found'}), 404

    alert = apply_plan_filter(result.data, plan)

    # Async view tracking (non-blocking)
    try:
        track_page_view(
            alert_id,
            result.data.get('jurisdiction', ''),
            str(result.data.get('affected_sectors', [''])[0] if result.data.get('affected_sectors') else ''),
            session_id
        )
    except Exception:
        pass

    # Related alerts
    related = supabase_anon.table('alerts')\
        .select('id,title,severity,regulator,published_at')\
        .eq('jurisdiction', result.data.get('jurisdiction', ''))\
        .eq('validation_status', 'approved')\
        .neq('id', alert_id)\
        .order('published_at', desc=True)\
        .limit(5)\
        .execute()

    # Cascade predictions
    cascade = supabase_anon.table('cascade_predictions')\
        .select('*')\
        .eq('source_alert_id', alert_id)\
        .limit(5)\
        .execute()

    return jsonify({
        'alert': alert,
        'related': related.data,
        'cascade_predictions': cascade.data,
        'user_plan': plan,
    })


@bp.route('/trending', methods=['GET'])
def get_trending():
    """Trending topics — fully public. Powered by Agent 22."""
    country = request.args.get('country', 'GLOBAL')
    result = supabase_anon.table('trending_topics')\
        .select('*')\
        .in_('jurisdiction', [country, 'GLOBAL'])\
        .order('trending_score', desc=True)\
        .limit(10)\
        .execute()
    return jsonify({'trending': result.data})


@bp.route('/intelligence', methods=['GET'])
def get_intelligence():
    """Consulting & bank market intelligence. Public summaries, Pro full content."""
    plan = get_plan_from_request()
    page = max(1, int(request.args.get('page', 1)))
    topic = request.args.get('topic')
    firm = request.args.get('firm')

    fields = 'id,firm_slug,firm_name,topic,summary_public,industry_tags,geography_tags,published_month'
    if plan in ('pro', 'enterprise'):
        fields += ',full_synthesis,regulatory_implications,key_themes'

    q = supabase_anon.table('consulting_synthesis')\
        .select(fields)\
        .order('published_month', desc=True)

    if topic:
        q = q.ilike('topic', f'%{topic}%')
    if firm:
        q = q.eq('firm_slug', firm)

    result = q.range((page - 1) * 20, page * 20 - 1).execute()
    return jsonify({'intelligence': result.data, 'user_plan': plan})


@bp.route('/regulators', methods=['GET'])
def get_regulators():
    """List all tracked regulators — public."""
    country = request.args.get('country')
    q = supabase_anon.table('regulator_profiles').select('*')
    if country:
        q = q.eq('jurisdiction', country)
    result = q.order('name').execute()
    return jsonify({'regulators': result.data})


@bp.route('/regulators/<regulator_code>', methods=['GET'])
def get_regulator(regulator_code):
    """Regulator profile + recent alerts — public."""
    profile = supabase_anon.table('regulator_profiles')\
        .select('*').eq('code', regulator_code.upper()).single().execute()
    alerts = supabase_anon.table('alerts')\
        .select('id,title,severity,base_impact_score,published_at,regulatory_deadline')\
        .eq('regulator', regulator_code.upper())\
        .eq('validation_status', 'approved')\
        .order('published_at', desc=True).limit(20).execute()
    return jsonify({
        'regulator': profile.data,
        'recent_alerts': alerts.data,
    })


@bp.route('/stats', methods=['GET'])
def get_stats():
    """Platform-wide stats — public homepage display."""
    total_alerts = supabase_anon.table('alerts')\
        .select('id', count='exact')\
        .eq('validation_status', 'approved').execute()
    today_alerts = supabase_anon.table('alerts')\
        .select('id,severity', count='exact')\
        .eq('validation_status', 'approved')\
        .gte('published_at', 'now()::date').execute()

    critical_count = sum(1 for a in (today_alerts.data or []) if a.get('severity') == 'critical')

    return jsonify({
        'total_alerts': total_alerts.count or 0,
        'today_alerts': len(today_alerts.data or []),
        'critical_today': critical_count,
        'sources_monitored': 210,
        'countries_covered': 80,
        'last_updated': 'Live',
    })


@bp.route('/track', methods=['POST'])
def track_view():
    """Anonymous page view tracking for Agent 22 trending."""
    data = request.get_json() or {}
    try:
        track_page_view(
            data.get('alert_id'),
            data.get('jurisdiction', ''),
            data.get('sector', ''),
            request.headers.get('X-Session-Id', 'anon'),
        )
    except Exception:
        pass
    return jsonify({'ok': True})
