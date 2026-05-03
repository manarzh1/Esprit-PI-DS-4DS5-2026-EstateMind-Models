"""app/services/report/pdf_generator.py — Génération PDF ReportLab."""
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (HRFlowable, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
settings = get_settings()

ORANGE = colors.HexColor("#FF6B00")
BLACK  = colors.HexColor("#0A0A0A")
WHITE  = colors.white
GRAY   = colors.HexColor("#888888")
LIGHT  = colors.HexColor("#F5F5F5")


def _styles():
    return {
        "title": ParagraphStyle("title", fontSize=26, textColor=WHITE,
                                fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=8),
        "subtitle": ParagraphStyle("subtitle", fontSize=13, textColor=WHITE,
                                   fontName="Helvetica", alignment=TA_CENTER, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontSize=13, textColor=ORANGE,
                             fontName="Helvetica-Bold", spaceBefore=16, spaceAfter=8),
        "body": ParagraphStyle("body", fontSize=10, textColor=colors.black,
                               fontName="Helvetica", leading=16, spaceAfter=6),
        "caption": ParagraphStyle("caption", fontSize=8, textColor=GRAY,
                                  fontName="Helvetica-Oblique", spaceAfter=4),
        "cell_label": ParagraphStyle("cell_label", fontSize=9, textColor=ORANGE,
                                     fontName="Helvetica-Bold"),
        "cell_value": ParagraphStyle("cell_value", fontSize=10, textColor=colors.black,
                                     fontName="Helvetica"),
    }


def _on_page(canvas, doc):
    if doc.page == 1: return
    canvas.saveState()
    w = A4[0]
    canvas.setFillColor(BLACK)
    canvas.rect(1.5*cm, A4[1]-1.8*cm, w-3*cm, 0.55*cm, fill=1, stroke=0)
    canvas.setFillColor(ORANGE)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(2*cm, A4[1]-1.52*cm, "ESTATE MIND — Rapport Confidentiel")
    canvas.setFillColor(WHITE)
    canvas.drawRightString(w-2*cm, A4[1]-1.52*cm, datetime.now().strftime("%d %B %Y"))
    canvas.setFillColor(GRAY)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(1.5*cm, 0.9*cm, "© Estate Mind Platform · Usage autorisé uniquement")
    canvas.drawRightString(w-1.5*cm, 0.9*cm, f"Page {doc.page}")
    canvas.restoreState()


def _kv_table(rows, s):
    data = [[Paragraph(l, s["cell_label"]), Paragraph(str(v), s["cell_value"])]
            for l,v in rows]
    t = Table(data, colWidths=[6*cm, 10*cm])
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,-1),LIGHT),
        ("GRID",(0,0),(-1,-1),0.5,colors.HexColor("#DDDDDD")),
        ("TOPPADDING",(0,0),(-1,-1),6),
        ("BOTTOMPADDING",(0,0),(-1,-1),6),
        ("LEFTPADDING",(0,0),(-1,-1),8),
        ("ROWBACKGROUNDS",(0,0),(-1,-1),[LIGHT,WHITE]),
    ]))
    return t


def generate_pdf_report(report_type: str, query: str, agent_data: dict[str,Any],
                         response_text: str, session_id: str | None = None,
                         explanation_summary: str | None = None) -> str:
    out_dir = Path(settings.pdf_output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    sid = str(session_id)[:8] if session_id else "nosession"
    fname = f"estate_mind_{report_type}_{sid}_{str(uuid.uuid4())[:6]}.pdf"
    fpath = out_dir / fname
    s = _styles()
    generated = datetime.now().strftime("%d %B %Y à %H:%M")
    story = []

    # Cover
    story += [
        Spacer(1, 4*cm),
        Paragraph("ESTATE MIND", s["title"]),
        Paragraph(f"RAPPORT {report_type.upper()}", s["subtitle"]),
        Spacer(1, 0.8*cm),
        HRFlowable(width="100%", thickness=1, color=ORANGE),
        Paragraph(f"<b>Requête :</b> {query[:120]}", s["subtitle"]),
        Spacer(1, 0.4*cm),
        Paragraph(f"Généré le : {generated}", s["subtitle"]),
        PageBreak(),
    ]

    # Summary
    story += [Paragraph("Résumé Exécutif", s["h2"]),
              HRFlowable(width="100%", thickness=0.5, color=ORANGE, spaceAfter=8)]
    clean = response_text.replace("**","").replace("##","").replace("#","").replace("|","")
    for line in clean.split("\n")[:20]:
        if line.strip(): story.append(Paragraph(line.strip(), s["body"]))
    story.append(Spacer(1, 0.5*cm))

    # Métriques selon type
    story += [Paragraph("Données Clés", s["h2"]),
              HRFlowable(width="100%", thickness=0.5, color=ORANGE, spaceAfter=8)]

    def fmt(v, d=0):
        try: return f"{int(v or d):,}"
        except: return str(v or d)

    if report_type == "price":
        rows = [
            ("Prix estimé", f"{fmt(agent_data.get('estimated_price'))} TND"),
            ("Prix médian", f"{fmt(agent_data.get('median_price'))} TND"),
            ("Fourchette", f"{fmt(agent_data.get('min_price'))} – {fmt(agent_data.get('max_price'))} TND"),
            ("Prix/m²", f"{fmt(agent_data.get('price_per_sqm'))} TND"),
            ("Fiabilité", f"{int((agent_data.get('confidence') or 0)*100)}%"),
            ("Annonces analysées", fmt(agent_data.get("total_listings_used"))),
        ]
    elif report_type == "investment":
        best = agent_data.get("best_opportunity") or {}
        rows = [
            ("Score investissement", f"{agent_data.get('investment_score',0)}/10"),
            ("Recommandation", agent_data.get("recommendation","N/A")),
            ("ROI annuel attendu", f"{agent_data.get('expected_annual_roi',0):.1f}%"),
            ("Rendement locatif", f"{agent_data.get('rental_yield',0):.1f}%"),
            ("Niveau de risque", agent_data.get("risk_level","N/A")),
            ("Meilleure zone", f"{best.get('city','')}/{best.get('district','')}"),
        ]
    elif report_type == "location":
        ms = agent_data.get("market_stats") or {}
        rows = [
            ("Ville analysée", agent_data.get("city","N/A")),
            ("Score localisation", f"{agent_data.get('location_score',0)}/10"),
            ("Annonces totales", fmt(ms.get("total_listings"))),
            ("Prix vente moyen", f"{fmt(ms.get('avg_price'))} TND"),
            ("Loyer moyen", f"{fmt(ms.get('avg_rent'))} TND/mois"),
            ("Prix/m²", f"{fmt(ms.get('avg_price_per_m2'))} TND"),
        ]
    elif report_type == "legal":
        rows = [
            ("Statut légal", agent_data.get("legal_status","N/A")),
            ("Titre vérifié", "Oui" if agent_data.get("title_verified") else "Non"),
            ("Zonage", agent_data.get("zoning","N/A")),
            ("Statut fiscal", agent_data.get("tax_status","N/A")),
            ("Score conformité", f"{int((agent_data.get('compliance_score') or 0)*100)}%"),
        ]
    else:
        total = agent_data.get("total_listings") or agent_data.get("total_zone_listings") or 0
        rows = [("Annonces analysées", fmt(total)),
                ("Sources", "tayara.tn, mubawab.tn, tecnocasa.tn"),
                ("Type de rapport", "Complet")]

    story.append(_kv_table(rows, s))
    story.append(Spacer(1, 0.5*cm))

    # Sources
    story += [Paragraph("Sources & Méthodologie", s["h2"]),
              HRFlowable(width="100%", thickness=0.5, color=ORANGE, spaceAfter=8)]
    story.append(Paragraph("• tayara.tn | mubawab.tn | tecnocasa.tn", s["body"]))
    story.append(Paragraph(f"• Base PostgreSQL estate_mind_db — {generated}", s["caption"]))

    # Disclaimer
    HRFlowable(width="100%", thickness=0.5, color=GRAY)
    story.append(Paragraph(
        "AVERTISSEMENT : Ce rapport est généré automatiquement par Estate Mind. "
        "Il est fourni à titre informatif uniquement et ne constitue pas un conseil légal, "
        "financier ou d'investissement. Consultez un professionnel avant toute décision.",
        ParagraphStyle("disc", fontSize=8, textColor=GRAY, fontName="Helvetica"),
    ))

    doc = SimpleDocTemplate(str(fpath), pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm,
                            title=f"Estate Mind — Rapport {report_type}")
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    log.info("pdf_generated", path=str(fpath))
    return str(fpath)
