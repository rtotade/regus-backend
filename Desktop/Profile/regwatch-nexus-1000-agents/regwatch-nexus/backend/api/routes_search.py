"""
RegWatch Nexus — Search Routes (No auth required)
Full-text and vector search across alerts and intelligence.
"""
from flask import Blueprint, jsonify, request
from supabase_client import supabase_anon
from pipeline.plan_filter import get_plan_from_request, apply_plan_filter_list

bp = Blueprint('search', __name__)


@bp.route('/', methods=['GET'])
def search():
    """Full-text search across alerts. No auth required."""
    plan = get_plan_from_request()
    q = (request.args.get('q') or '').strip()
    country = request.args.get('country')
    sector = request.args.get('sector')
    severity = request.args.get('severity')
    page = max(1, int(request.args.get('page', 1)))

    if not q:
        return jsonify({'results': [], 'query': q, 'count': 0})

    # Supabase full-text search using tsvector
    query = supabase_anon.table('alerts')\
        .select('id,regulator,jurisdiction,title,summary,severity,base_impact_score,'
                'topic_tags,affected_sectors,published_at,source_url')\
        .eq('validation_status', 'approved')\
        .text_search('fts', q, config={'type': 'websearch'})\
        .order('published_at', desc=True)

    if country:
        query = query.eq('jurisdiction', country)
    if severity:
        query = query.eq('severity', severity)

    result = query.range((page - 1) * 20, page * 20 - 1).execute()
    alerts = apply_plan_filter_list(result.data, plan)

    return jsonify({
        'results': alerts,
        'query': q,
        'count': len(alerts),
        'page': page,
        'user_plan': plan,
    })


@bp.route('/suggest', methods=['GET'])
def suggest():
    """Search suggestions/autocomplete. No auth required."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify({'suggestions': []})

    results = supabase_anon.table('alerts')\
        .select('title,regulator,jurisdiction')\
        .eq('validation_status', 'approved')\
        .ilike('title', f'%{q}%')\
        .limit(8).execute()

    suggestions = [{'title': r['title'], 'regulator': r['regulator']} for r in results.data]
    return jsonify({'suggestions': suggestions})
