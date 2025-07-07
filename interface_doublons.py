import tkinter as tk
from tkinter import ttk, messagebox
from db import connexion_db
from datetime import datetime
import webbrowser
import tempfile
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm

class DoublonsInterface:
    def __init__(self, master=None):
        # CORRECTION PRINCIPALE : Utilisation directe de la fenêtre parente
        if master is None:
            self.root = tk.Tk()
            self.is_standalone = True
        else:
            self.root = master
            self.is_standalone = False
            
        self.root.title("📑 Doublons Dépôts")
        self.root.geometry("950x500")
        
        # Configuration du Treeview
        self.frame = tk.Frame(self.root)
        self.frame.pack(padx=10, pady=10, fill="both", expand=True)
        
        self.tree = ttk.Treeview(
            self.frame, 
            columns=("Client", "Montant", "Heure", "Date", "Occurrences"), 
            show="headings",
            selectmode="browse"
        )
        
        # Configuration des colonnes
        columns = {
            "Client": "Code Client",
            "Montant": "Montant",
            "Heure": "Heure",
            "Date": "Date Dépôt",
            "Occurrences": "Occur."
        }
        
        for col, text in columns.items():
            self.tree.heading(col, text=text)
            self.tree.column(col, anchor="center", width=100)
        
        # Ajustement automatique de la colonne Client
        self.tree.column("Client", width=150, stretch=True)
        
        self.tree.pack(side="left", fill="both", expand=True)
        
        # Barre de défilement
        scrollbar = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree.yview)
        scrollbar.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Chargement initial des données
        self.charger_doublons()
        
        # Boutons d'action
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)
        
        buttons = [
            ("Supprimer (garder 1)", "red", self.supprimer_doublons_conserver_1),
            ("Supprimer Tout", "darkred", self.supprimer_tout_doublon),
            ("Exporter PDF", "blue", self.exporter_pdf),
            ("Actualiser", "grey", self.charger_doublons),
            ("Fermer", "grey", self.root.destroy)
        ]
        
        for text, color, command in buttons:
            tk.Button(
                btn_frame, 
                text=text, 
                bg=color,
                fg="white",
                command=command
            ).pack(side="left", padx=5)

        # Fermeture propre en mode standalone
        if self.is_standalone:
            self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
            self.root.mainloop()

    def charger_doublons(self):
        """Charge les doublons depuis la base de données"""
        # Efface les anciennes données
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        conn = connexion_db()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                SELECT numero_client, montant, heure, date_depot, COUNT(*)
                FROM depots
                GROUP BY numero_client, montant, heure, date_depot
                HAVING COUNT(*) > 1
                ORDER BY date_depot DESC, heure DESC
            """)
            
            # Insertion des résultats
            for row in cursor.fetchall():
                self.tree.insert("", "end", values=row)
                
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur de base de données:\n{str(e)}", parent=self.root)
        finally:
            conn.close()

    def supprimer_doublons_conserver_1(self):
        """Supprime les doublons en conservant une occurrence"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Aucune sélection", "Veuillez sélectionner un doublon à traiter.", parent=self.root)
            return
            
        item = self.tree.item(selected[0])["values"]
        numero_client, montant, heure, date_depot, _ = item
        
        conn = connexion_db()
        cursor = conn.cursor()
        
        try:
            # Récupération des IDs à supprimer
            cursor.execute("""
                SELECT id FROM depots
                WHERE numero_client = ? AND montant = ? AND heure = ? AND date_depot = ?
                ORDER BY id ASC
            """, (numero_client, montant, heure, date_depot))
            
            ids = [row[0] for row in cursor.fetchall()]
            
            if len(ids) <= 1:
                messagebox.showinfo("Information", "Aucune duplication à supprimer", parent=self.root)
                return
                
            # Conserve le premier ID (le plus ancien)
            ids_a_supprimer = ids[1:]
            
            # Suppression des doublons
            cursor.executemany("DELETE FROM depots WHERE id = ?", [(id_,) for id_ in ids_a_supprimer])
            
            # Mise à jour du solde
            montant_total = montant * len(ids_a_supprimer)
            cursor.execute(
                "UPDATE abonne SET solde = solde - ? WHERE numero_client = ?",
                (montant_total, numero_client)
            )
            
            conn.commit()
            messagebox.showinfo(
                "Succès",
                f"{len(ids_a_supprimer)} doublon(s) supprimé(s)\n"
                f"Montant déduit: {montant_total}",
                parent=self.root
            )
            
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Erreur", f"Erreur de suppression:\n{str(e)}", parent=self.root)
        finally:
            conn.close()
            self.charger_doublons()

    def supprimer_tout_doublon(self):
        """Supprime toutes les occurrences du doublon"""
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Aucune sélection", "Veuillez sélectionner un doublon à traiter.", parent=self.root)
            return
            
        item = self.tree.item(selected[0])["values"]
        numero_client, montant, heure, date_depot, _ = item
        
        conn = connexion_db()
        cursor = conn.cursor()
        
        try:
            # Récupération des IDs
            cursor.execute("""
                SELECT id FROM depots
                WHERE numero_client = ? AND montant = ? AND heure = ? AND date_depot = ?
            """, (numero_client, montant, heure, date_depot))
            
            ids = [row[0] for row in cursor.fetchall()]
            
            if not ids:
                messagebox.showinfo("Information", "Aucune donnée à supprimer", parent=self.root)
                return
                
            # Suppression totale
            cursor.executemany("DELETE FROM depots WHERE id = ?", [(id_,) for id_ in ids])
            
            # Mise à jour du solde
            montant_total = montant * len(ids)
            cursor.execute(
                "UPDATE abonne SET solde = solde - ? WHERE numero_client = ?",
                (montant_total, numero_client)
            )
            
            conn.commit()
            messagebox.showinfo(
                "Succès",
                f"Toutes les occurrences ({len(ids)}) ont été supprimées\n"
                f"Montant déduit: {montant_total}",
                parent=self.root
            )
            
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Erreur", f"Erreur de suppression:\n{str(e)}", parent=self.root)
        finally:
            conn.close()
            self.charger_doublons()

    def exporter_pdf(self):
        """Exporte les doublons en format PDF avec numérotation des pages"""
        # Création d'un fichier temporaire
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmpfile:
            filename = tmpfile.name
        
        # Création du document PDF
        doc = SimpleDocTemplate(filename, pagesize=A4)
        styles = getSampleStyleSheet()
        elements = []
        
        # Titre
        title = Paragraph("Liste des dépôts en doublon", styles["Title"])
        elements.append(title)
        
        # Date d'export
        date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_text = Paragraph(f"Exporté le: {date_str}", styles["Normal"])
        elements.append(date_text)
        
        elements.append(Paragraph("<br/><br/>", styles["Normal"]))
        
        # Préparation des données du tableau
        data = [["Code Client", "Montant", "Heure", "Date", "Occurrences"]]
        
        for item in self.tree.get_children():
            row = self.tree.item(item)["values"]
            data.append([str(x) for x in row])
        
        # Création du tableau
        table = Table(data)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3A5683")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 12),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
            ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F0F0F0")),
            ("GRID", (0, 0), (-1, -1), 1, colors.black),
            ("FONTSIZE", (0, 1), (-1, -1), 10),
        ]))
        
        elements.append(table)
        
        # Pied de page avec numéro de page
        def footer(canvas, doc):
            canvas.saveState()
            canvas.setFont("Helvetica", 8)
            page_num = f"Page {doc.page}"
            canvas.drawString(10*mm, 10*mm, page_num)
            canvas.restoreState()
        
        doc.build(elements, onFirstPage=footer, onLaterPages=footer)
        
        # Ouverture du PDF
        webbrowser.open(filename)

# Fonction à ajouter dans votre classe principale
def gerer_doublons(self):
    """Ouvre l'interface de gestion des doublons"""
    fen_doublons = tk.Toplevel(self)
    fen_doublons.title("Gestion des Doublons")
    fen_doublons.geometry("1000x600")
    
    # Intégration de l'interface corrigée
    DoublonsInterface(fen_doublons)

if __name__ == "__main__":
    app = DoublonsInterface()