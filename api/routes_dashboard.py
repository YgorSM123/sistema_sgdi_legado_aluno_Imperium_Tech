from flask import Blueprint, jsonify, request
from flasgger import swag_from

from api.auth import token_required
from api.paths import swagger_path

dashboard_bp = Blueprint("api_dashboard", __name__, url_prefix="/api/dashboard")


@dashboard_bp.route("", methods=["GET"])
@token_required
@swag_from(swagger_path("dashboard_get.yml"))
def dashboard_json():
    from app import _build_dashboard_context

    context = _build_dashboard_context(request.args)
    return jsonify(
        {
            "company_name": context["company_name"],
            "generated_at": context["generated_at"],
            "filters": {
                "periodo": context["filters"]["periodo"],
                "periodo_label": context["filters"]["periodo_label"],
                "responsavel": context["filters"]["responsavel"],
                "prioridade": context["filters"]["prioridade"],
                "status": context["filters"]["status"],
            },
            "kpis": context["kpis"],
            "por_status": context["por_status"],
            "por_prioridade": context["por_prioridade"],
            "abertas_por_responsavel": context["abertas_por_responsavel"],
            "evolucao_temporal": context["evolucao_temporal"],
            "criticas_atrasadas": context["criticas_atrasadas"],
            "sla_days": context["sla_days"],
        }
    )
