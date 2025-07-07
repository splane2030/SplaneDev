from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
import os
from datetime import datetime
import pathlib

# Liste des noms de jours en français
JOURS_SEMAINE = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# Styles pour le PDF
styles = getSampleStyleSheet()
style_title = ParagraphStyle(
    'Title',
    parent=styles['Heading1'],
    fontSize=16,
    alignment=1,
    spaceAfter=20
)
style_subtitle = ParagraphStyle(
    'Subtitle',
    parent=styles['Heading2'],
    fontSize=12,
    alignment=1,
    spaceAfter=10
)
style_header = ParagraphStyle(
    'Header',
    parent=styles['Normal'],
    fontSize=10,
    textColor=colors.white,
    alignment=1
)
style_cell = ParagraphStyle(
    'Cell',
    parent=styles['Normal'],
    fontSize=9,
    alignment=1
)
style_footer = ParagraphStyle(
    'Footer',
    parent=styles['Normal'],
    fontSize=10,
    textColor=colors.darkred,
    alignment=2
)

def formater_date_francais(date_str):
    """Formate une date au format 'YYYY-MM-DD' en français"""
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        jour_semaine = JOURS_SEMAINE[date_obj.weekday()]
        return f"{jour_semaine}, le {date_obj.strftime('%d/%m/%Y')}"
    except:
        return date_str

def exporter_depots_journaliers_pdf(depots, total, date_jour):
    """Exporte les dépôts journaliers en format PDF"""
    # Chemin vers le dossier Documents de l'utilisateur
    docs_path = pathlib.Path.home() / "Documents"
    
    # Créer le sous-dossier "Rapports journaliers" s'il n'existe pas
    depot_dir = docs_path / "Rapports journaliers"
    depot_dir.mkdir(parents=True, exist_ok=True)
    
    # Créer le nom du fichier dans le sous-dossier
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"depots_journaliers_{date_str}.pdf"
    filepath = depot_dir / filename
    
    # Créer le document PDF
    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=letter,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    # Préparer les données
    elements = []
    
    # Titre principal
    title = Paragraph("RAPPORT DES DÉPÔTS JOURNALIERS", style_title)
    elements.append(title)
    
    # Date du rapport formatée en français
    date_formatee = formater_date_francais(date_jour)
    date_rapport = Paragraph(f"Date: {date_formatee}", style_subtitle)
    elements.append(date_rapport)
    
    # En-tête du tableau
    header = [
        Paragraph("Heure", style_header),
        Paragraph("Client", style_header),
        Paragraph("Montant (FC)", style_header),
        Paragraph("Référence", style_header),
        Paragraph("Agent", style_header)
    ]
    
    # Données des dépôts
    data = [header]
    for depot in depots:
        # Correction: extraire les valeurs dans le bon ordre
        # Structure: (date_depot, heure, nom_client, montant, ref_depot, nom_agent)
        # Nous n'utilisons pas date_depot (déjà dans le titre)
        _, heure, client, montant, ref, agent = depot
        
        # Formater le montant si c'est un nombre
        if isinstance(montant, (int, float)):
            montant_str = f"{montant:,.2f}"
        else:
            montant_str = str(montant)
            
        row = [
            Paragraph(str(heure), style_cell),
            Paragraph(str(client), style_cell),
            Paragraph(montant_str, style_cell),
            Paragraph(str(ref), style_cell),
            Paragraph(str(agent), style_cell)
        ]
        data.append(row)
    
    # Ajouter une ligne pour le total
    total_row = [
        Paragraph("", style_cell),
        Paragraph("<b>TOTAL</b>", style_cell),
        Paragraph(f"<b>{total:,.2f} FC</b>", style_cell),
        Paragraph("", style_cell),
        Paragraph("", style_cell)
    ]
    data.append(total_row)
    
    # Créer le tableau
    table = Table(data, colWidths=[1*inch, 2.5*inch, 1.2*inch, 2*inch, 1.5*inch])
    
    # Style du tableau
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkblue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ('BACKGROUND', (0, -1), (1, -1), colors.lightgrey),
        ('BACKGROUND', (2, -1), (2, -1), colors.lightblue),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])
    
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Pied de page modifié
    aujourdhui = datetime.now()
    jour_semaine = JOURS_SEMAINE[aujourdhui.weekday()]
    date_footer = f"{jour_semaine}, le {aujourdhui.strftime('%d/%m/%Y')}"
    footer = Paragraph(f"Fait à Kinshasa, le {date_footer}", style_footer)
    elements.append(footer)
    
    # Générer le PDF
    doc.build(elements)
    
    return str(filepath)

def exporter_rapport_global_pdf(clients, total_general):
    """Exporte le rapport global des dépôts en format PDF"""
    # Chemin vers le dossier Documents de l'utilisateur
    docs_path = pathlib.Path.home() / "Documents"
    
    # Créer le sous-dossier "Rapports globaux" s'il n'existe pas
    global_dir = docs_path / "Rapports globaux"
    global_dir.mkdir(parents=True, exist_ok=True)
    
    # Créer le nom du fichier dans le sous-dossier
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"rapport_global_depots_{date_str}.pdf"
    filepath = global_dir / filename
    
    # Créer le document PDF
    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=letter,
        leftMargin=0.5*inch,
        rightMargin=0.5*inch,
        topMargin=0.5*inch,
        bottomMargin=0.5*inch
    )
    
    # Préparer les données
    elements = []
    
    # Titre principal
    title = Paragraph("RAPPORT GLOBAL DES DÉPÔTS", style_title)
    elements.append(title)
    
    # Date du rapport formatée en français
    aujourdhui = datetime.now()
    jour_semaine = JOURS_SEMAINE[aujourdhui.weekday()]
    date_formatee = f"{jour_semaine}, le {aujourdhui.strftime('%d/%m/%Y')}"
    date_rapport = Paragraph(f"Date: {date_formatee}", style_subtitle)
    elements.append(date_rapport)
    
    # En-tête du tableau
    header = [
        Paragraph("Code Client", style_header),
        Paragraph("Nom Client", style_header),
        Paragraph("Total Dépôts (FC)", style_header),
        Paragraph("Nombre Dépôts", style_header)
    ]
    
    # Données des clients
    data = [header]
    for client in clients:
        # Correction: extraire les valeurs dans le bon ordre
        # Structure: (code_client, nom_client, total_depots, nb_depots)
        code, nom, total, nb_depots = client
        
        # Formater les valeurs numériques
        total_fmt = f"{total:,.2f}" if isinstance(total, (int, float)) else str(total)
        nb_depots_str = str(nb_depots) if isinstance(nb_depots, (int, float)) else str(nb_depots)
        
        row = [
            Paragraph(str(code), style_cell),
            Paragraph(str(nom), style_cell),
            Paragraph(total_fmt, style_cell),
            Paragraph(nb_depots_str, style_cell)
        ]
        data.append(row)
    
    # Ajouter une ligne pour le total général
    total_row = [
        Paragraph("", style_cell),
        Paragraph("<b>TOTAL GÉNÉRAL</b>", style_cell),
        Paragraph(f"<b>{total_general:,.2f} FC</b>", style_cell),
        Paragraph("", style_cell)
    ]
    data.append(total_row)
    
    # Créer le tableau
    table = Table(data, colWidths=[1.2*inch, 3.5*inch, 1.5*inch, 1.2*inch])
    
    # Style du tableau
    table_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.darkgreen),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 10),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -2), colors.white),
        ('GRID', (0, 0), (-1, -1), 1, colors.lightgrey),
        ('BACKGROUND', (0, -1), (1, -1), colors.lightgrey),
        ('BACKGROUND', (2, -1), (2, -1), colors.lightblue),
        ('FONT', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ])
    
    table.setStyle(table_style)
    elements.append(table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Statistiques supplémentaires
    # Précaution contre les listes vides
    montants = [c[2] for c in clients if isinstance(c[2], (int, float)) and len(c) > 2]
    
    stats = []
    if clients:
        stats = [
            f"Nombre total de clients: {len(clients)}",
            f"Montant moyen par client: {total_general / len(clients):,.2f} FC",
            f"Plus haut dépôt: {max(montants) if montants else 0:,.2f} FC",
            f"Plus bas dépôt: {min(montants) if montants else 0:,.2f} FC"
        ]
    else:
        stats = ["Aucun dépôt enregistré"]
    
    for stat in stats:
        elements.append(Paragraph(stat, style_cell))
    
    elements.append(Spacer(1, 0.2*inch))
    
    # Pied de page modifié
    footer = Paragraph(f"Fait à Kinshasa, le {date_formatee}", style_footer)
    elements.append(footer)
    
    # Générer le PDF
    doc.build(elements)
    
    return str(filepath)