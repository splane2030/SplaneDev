def exporter_cartes_compte_fixe(data):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    import tempfile
    import webbrowser
    import sqlite3
    import os
    import sys
    import shutil
    from datetime import datetime
    from reportlab.platypus import Table, TableStyle, Paragraph
    from reportlab.lib.styles import ParagraphStyle

    # Fonction pour obtenir le chemin de la base de données
    def get_db_path():
        appdata_dir = os.getenv("APPDATA")
        app_folder = os.path.join(appdata_dir, "MyApp")
        os.makedirs(app_folder, exist_ok=True)
        local_db = os.path.join(app_folder, "data_epargne.db")

        if not os.path.exists(local_db):
            def resource_path(relative_path):
                try:
                    base_path = sys._MEIPASS
                except Exception:
                    base_path = os.path.abspath(".")
                return os.path.join(base_path, relative_path)
            
            original_db = resource_path("data_epargne.db")
            if os.path.exists(original_db):
                shutil.copyfile(original_db, local_db)

        return local_db

    # Données
    numero_client = data["numero_client"]
    nom_client = data["nom_client"]
    montant_initial = data["montant_initial"]
    ref_depot = data.get("ref", datetime.now().strftime("%Y%m%d%H%M"))

    # Connexion à la base de données
    conn = sqlite3.connect(get_db_path())
    cur = conn.cursor()
    
    # Récupérer les cases
    cur.execute("""
        SELECT ref_depot, date_remplissage 
        FROM compte_fixe_cases 
        WHERE numero_client = ?
        ORDER BY date_remplissage, id
    """, (numero_client,))
    cases = cur.fetchall()
    conn.close()
    
    total_cases = len(cases)
    montant_total = total_cases * montant_initial

    # Création du PDF
    temp_file = tempfile.NamedTemporaryFile(suffix='.pdf', delete=False)
    filename = temp_file.name
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    # Paramètres de mise en page
    marge = 1.5 * cm
    espace_ligne = 0.6 * cm
    colonnes = 2
    largeur_colonne = (width - 2 * marge - 0.5*cm) / colonnes
    hauteur_carte = 19 * cm
    y_start = height - marge - 3.0 * cm  # Position de départ après l'en-tête

    # Couleurs
    couleur_texte = colors.black
    couleur_titre = colors.HexColor("#128C7E")
    couleur_entete = colors.HexColor("#075E54")
    couleur_ligne = colors.HexColor("#E5E5E5")
    couleur_footer_border = colors.darkred
    couleur_fond_entete = colors.HexColor("#075E54")
    couleur_texte_entete = colors.white

    # En-tête principal (sur chaque page)
    def draw_header(page_num):
        # SERVICE CENTRAL D'EPARGNE...
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(couleur_entete)
        c.drawCentredString(width / 2, height - 0.7*cm, "SERVICE CENTRAL D'EPARGNE POUR LA PROMOTION DE L'ENTREPRENEURIAT")
        
        # PAGE N°X
        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(couleur_titre)
        c.drawCentredString(width / 2, height - 1.7*cm, f"PAGE N°{page_num}")
        
        # Informations client
        c.setFont("Helvetica", 10)
        c.setFillColor(couleur_texte)
        c.drawString(marge, height - 2.7*cm, f"Client: {nom_client}")
        c.drawString(width / 2, height - 2.7*cm, f"N° Client: {numero_client}")
        
        c.drawString(marge, height - 3.2*cm, f"Montant unitaire: {montant_initial:,.0f} FC")
        c.drawString(width / 2, height - 3.2*cm, f"Total épargné: {montant_total:,.0f} FC")
        
        # Ligne séparatrice
        c.setStrokeColor(couleur_entete)
        c.setLineWidth(1)
        c.line(marge, height - 3.7*cm, width - marge, height - 3.7*cm)

    # Pied de page avec bordure
    def draw_footer():
        footer_y = 0.7 * cm
        footer_text = "$-MONEY/Easy save, Easy get"
        
        # Bordure en haut du pied de page
        c.setStrokeColor(couleur_footer_border)
        c.setLineWidth(1)
        c.line(marge, footer_y + 0.3*cm, width - marge, footer_y + 0.3*cm)
        
        # Texte du pied de page
        c.setFont("Helvetica-Bold", 10)
        c.setFillColor(couleur_footer_border)
        c.drawCentredString(width / 2, footer_y, footer_text)

    # Dessiner une carte avec tableau
    def draw_card(x, y, card_title, cases_subset):
        # Préparer les données du tableau
        table_data = []
        
        # Entête du tableau
        table_data.append([
            Paragraph("N°", style_header),
            Paragraph("MISE", style_header),
            Paragraph("REFERENCE", style_header),
            Paragraph("DATE", style_header)
        ])
        
        # Cases
        for idx, case in enumerate(cases_subset):
            numero_case = idx + 1
            ref_depot_case, date_case = case
            
            # Formater la date
            try:
                date_parts = date_case.split('-')
                date_formatted = f"{date_parts[2]}/{date_parts[1]}/{date_parts[0][2:]}"
            except:
                date_formatted = date_case
            
            table_data.append([
                Paragraph(str(numero_case)), 
                Paragraph(f"{montant_initial:,.0f}"), 
                Paragraph(ref_depot_case), 
                Paragraph(date_formatted)
            ])
        
        # Solde
        table_data.append([
            "", 
            "", 
            Paragraph("<b>SOLDE:</b>"), 
            Paragraph(f"<b>{montant_initial * len(cases_subset):,.0f} FC</b>")
        ])
        
        # Créer le tableau
        col_widths = [1.0*cm, 1.4*cm, 4.0*cm, 2.2*cm]
        table = Table(table_data, colWidths=col_widths)
        
        # Style du tableau
        table_style = TableStyle([
            # Style de l'entête
            ('BACKGROUND', (0, 0), (-1, 0), couleur_fond_entete),
            ('TEXTCOLOR', (0, 0), (-1, 0), couleur_texte_entete),
            ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            
            # Bordures
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('BOX', (0, 0), (-1, -1), 1, colors.gray),
            
            # Alignement
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            
            # Style du solde
            ('FONT', (2, -1), (3, -1), 'Helvetica-Bold'),
            ('ALIGN', (2, -1), (3, -1), 'RIGHT'),
            
            # Alternance des couleurs de fond
            ('BACKGROUND', (0, 1), (-1, -2), colors.white),
            ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.whitesmoke, colors.white]),
        ])
        
        table.setStyle(table_style)
        
        # Dessiner le tableau
        table.wrapOn(c, largeur_colonne, hauteur_carte)
        table.drawOn(c, x, y - table._height - 0.5*cm)
        
        # Titre de la carte
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(couleur_entete)
        c.drawString(x, y, card_title)
        
        return table._height

    # Définir les styles pour les paragraphes
    style_header = ParagraphStyle(
        'Header',
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=couleur_texte_entete,
        alignment=1  # Centré
    )

    # Calcul du nombre de pages
    cases_per_card = 31
    total_cards = (total_cases + cases_per_card - 1) // cases_per_card
    total_pages = (total_cards + 1) // 2  # 2 cartes par page

    # Génération des pages
    case_index = 0
    page_num = 1

    while case_index < total_cases:
        # Entête de page avec "PAGE N°X"
        draw_header(page_num)
        
        # Position initiale pour les cartes
        y = y_start
        
        # Deux cartes par page
        for col in range(colonnes):
            if case_index >= total_cases:
                break
                
            x = marge + col * (largeur_colonne + 0.5*cm)
            card_title = f"PAGE {((page_num - 1) * colonnes) + col + 1}"
            
            # Sélection des cases pour cette carte
            end_index = min(case_index + cases_per_card, total_cases)
            card_cases = cases[case_index:end_index]
            case_index = end_index
            
            # Dessiner la carte avec tableau
            card_height = draw_card(x, y, card_title, card_cases)
            
            # Ajuster la position Y pour la prochaine carte
            # (non utilisé ici car nous avons deux cartes côte à côte)
        
        # Pied de page avec bordure
        draw_footer()
        
        # Nouvelle page si nécessaire
        if case_index < total_cases:
            c.showPage()
            page_num += 1

    # Enregistrement et ouverture du PDF
    c.save()
    webbrowser.open(filename)
    return filename