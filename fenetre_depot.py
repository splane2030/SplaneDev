# === interface_depot.py ===
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import random
import sqlite3
import os
import sys
import threading
import export_pdf
import export_carte
import interface_doublons
import shutil
from depot_export import exporter_depots_journaliers_pdf, exporter_rapport_global_pdf


# --- Couleurs modernes style WhatsApp/Facebook ---
PRIMARY_COLOR = "#128C7E"
SECONDARY_COLOR = "#075E54"
BACKGROUND_COLOR = "#F0F2F5"
CARD_COLOR = "#FFFFFF"
TEXT_COLOR = "#333333"
ACCENT_COLOR = "#25D366"
BUTTON_COLOR = "#128C7E"
BUTTON_HOVER = "#075E54"
ERROR_COLOR = "#FF5252"
LIGHT_GRAY = "#E5E5E5"
DARK_GRAY = "#4E4E4E"

def resource_path(relative_path):
    """Retourne le chemin absolu même après compilation avec PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_db_path():
    appdata_dir = os.getenv("APPDATA")
    app_folder = os.path.join(appdata_dir, "MyApp")
    os.makedirs(app_folder, exist_ok=True)
    local_db = os.path.join(app_folder, "data_epargne.db")

    if not os.path.exists(local_db):
        original_db = resource_path("data_epargne.db")
        if os.path.exists(original_db):
            shutil.copyfile(original_db, local_db)

    return local_db

def verifier_structure_bd():
    """Vérifie et met à jour la structure de la base de données"""
    with connexion_db() as conn:
        cur = conn.cursor()
        
        # Vérifier si la colonne 'numero_carte' existe dans 'compte_fixe'
        cur.execute("PRAGMA table_info(compte_fixe)")
        colonnes = [col[1] for col in cur.fetchall()]
        
        if 'numero_carte' not in colonnes:
            try:
                cur.execute("ALTER TABLE compte_fixe ADD COLUMN numero_carte TEXT")
                conn.commit()
            except sqlite3.Error as e:
                print(f"Erreur modification table: {str(e)}")
        
        # Vérifier si la colonne 'numero_carte' existe dans 'compte_fixe_pages'
        cur.execute("PRAGMA table_info(compte_fixe_pages)")
        colonnes = [col[1] for col in cur.fetchall()]
        if 'numero_carte' not in colonnes:
            try:
                cur.execute("ALTER TABLE compte_fixe_pages ADD COLUMN numero_carte TEXT")
                conn.commit()
            except sqlite3.Error as e:
                print(f"Erreur modification table: {str(e)}")

def connexion_db():
    chemin_db = get_db_path()
    conn = sqlite3.connect(chemin_db)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def ajouter_journal(action, acteur, cible=None, details=None):
    with connexion_db() as conn:
        cur = conn.cursor()
        try:
            cur.execute("""
            INSERT INTO journal (
                action, acteur, cible, details, 
                date_action, heure_action
            ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                action, acteur, cible, details,
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%H:%M:%S")
            ))
            conn.commit()
            return True
        except sqlite3.Error as e:
            print(f"Erreur journal: {str(e)}")
            return False

class FenetreDepot(tk.Toplevel):
    def __init__(self, parent, nom_agent):
        super().__init__(parent)
        self.title("💰 Interface de Dépôt")
        self.state('zoomed')
        self.configure(bg=BACKGROUND_COLOR)
        self.nom_agent = nom_agent
        self.dernier_bordereau = {}
        self.dernier_ref = tk.StringVar()
        
        # Vérifier la structure de la BD
        verifier_structure_bd()
        
        # Style moderne
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TFrame', background=BACKGROUND_COLOR)
        self.style.configure('TLabel', background=BACKGROUND_COLOR, foreground=TEXT_COLOR, font=('Helvetica', 11))
        self.style.configure('TButton', background=BUTTON_COLOR, foreground='white', font=('Helvetica', 11, 'bold'))
        self.style.map('TButton', 
                      background=[('active', BUTTON_HOVER), ('pressed', SECONDARY_COLOR)],
                      foreground=[('active', 'white'), ('pressed', 'white')])
        self.style.configure('TEntry', fieldbackground='white', foreground=TEXT_COLOR)
        self.style.configure('Card.TFrame', background=CARD_COLOR, relief='solid', borderwidth=1)
        
        self.creer_interface()
        
    def creer_interface(self):
        # Header
        header = tk.Frame(self, bg=PRIMARY_COLOR, height=80)
        header.pack(fill='x', padx=0, pady=0)
        
        tk.Label(header, 
                text="INTERFACE DE DÉPÔT", 
                bg=PRIMARY_COLOR, 
                fg='white', 
                font=('Helvetica', 20, 'bold')).pack(side='left', padx=30, pady=20)
        
        # Conteneur principal
        main_frame = tk.Frame(self, bg=BACKGROUND_COLOR)
        main_frame.pack(fill='both', expand=True, padx=20, pady=20)
        
        # Formulaire de dépôt
        form_frame = ttk.Frame(main_frame, style='Card.TFrame', padding=20)
        form_frame.pack(fill='both', expand=True, side='left', padx=(0, 10))
        
        # Titre formulaire
        tk.Label(form_frame, 
                text="FORMULAIRE DE DÉPÔT", 
                font=('Helvetica', 16, 'bold'),
                bg=CARD_COLOR,
                fg=PRIMARY_COLOR).grid(row=0, column=0, columnspan=2, pady=(0, 20), sticky='w')
        
        # Champs
        self.entries = {}
        champs = [
            ("Numéro Client:", "entry_numero_client"),
            ("Numéro Carte:", "entry_numero_carte"),
            ("Montant du Dépôt (FC):", "entry_montant")
        ]
        
        for i, (label, var_name) in enumerate(champs):
            ttk.Label(form_frame, text=label).grid(row=i+1, column=0, sticky='e', padx=10, pady=10)
            entry = ttk.Entry(form_frame, width=30, font=('Helvetica', 11))
            entry.grid(row=i+1, column=1, sticky='w', padx=10, pady=10)
            self.entries[var_name] = entry
        
        # Validation du montant
        vcmd = (self.register(self.validate_amount), '%P')
        self.entries["entry_montant"].configure(validate="key", validatecommand=vcmd)
        
        # Informations abonné
        self.label_nom_client = tk.Label(form_frame, 
                                       text="Nom du Client : -", 
                                       font=('Helvetica', 10, 'italic'),
                                       bg=CARD_COLOR, 
                                       fg="blue")
        self.label_nom_client.grid(row=4, column=0, columnspan=2, pady=5, sticky='w')
        
        self.label_solde = tk.Label(form_frame, 
                                  text="Solde Actuel : 0 FC", 
                                  font=('Helvetica', 10, 'italic'),
                                  bg=CARD_COLOR, 
                                  fg="green")
        self.label_solde.grid(row=5, column=0, columnspan=2, pady=5, sticky='w')
        
        # Type de compte
        ttk.Label(form_frame, text="Type de Compte:").grid(row=6, column=0, sticky='e', padx=10, pady=5)
        self.type_compte_var = tk.StringVar(value="normal")
        
        compte_frame = tk.Frame(form_frame, bg=CARD_COLOR)
        compte_frame.grid(row=6, column=1, sticky='w')
        ttk.Radiobutton(compte_frame, text="Mixte", variable=self.type_compte_var, value="normal").pack(side='left', padx=5)
        ttk.Radiobutton(compte_frame, text="Fixe", variable=self.type_compte_var, value="fixe").pack(side='left', padx=5)
        
        # Boutons d'action
        btn_frame = tk.Frame(form_frame, bg=CARD_COLOR)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=20)
        
        actions = [
            ("🔍 Afficher Info", self.afficher_nom_et_solde),
            ("💰 Effectuer Dépôt", self.effectuer_depot),
            ("📊 Vérifier Compte Fixe", self.verifier_compte_fixe),
            ("📜 Historique Client", self.afficher_historique_client),
            ("📋 Comptes Fixes", self.afficher_comptes_fixes)
        ]
        
        for text, cmd in actions:
            btn = ttk.Button(btn_frame, text=text, command=cmd, width=20)
            btn.pack(side='left', padx=5, fill='x', expand=True)
        
        # Historique des dépôts (30 derniers)
        hist_frame = ttk.Frame(main_frame, style='Card.TFrame', padding=20)
        hist_frame.pack(fill='both', expand=True, side='right', padx=(10, 0))
        
        tk.Label(hist_frame, 
                text="HISTORIQUE RÉCENT (30 derniers dépôts)", 
                font=('Helvetica', 16, 'bold'),
                bg=CARD_COLOR,
                fg=PRIMARY_COLOR).pack(anchor='w', pady=(0, 10))
        
        # Treeview pour l'historique
        columns = ("Date", "Heure", "Client", "Montant", "Réf.", "Agent")
        self.hist_tree = ttk.Treeview(hist_frame, columns=columns, show="headings", height=15)
        
        for col in columns:
            self.hist_tree.heading(col, text=col)
            self.hist_tree.column(col, width=120, anchor='center')
        
        scrollbar = ttk.Scrollbar(hist_frame, orient="vertical", command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=scrollbar.set)
        
        self.hist_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Charger l'historique
        self.charger_historique()
        
        # Boutons bas
        bottom_frame = tk.Frame(self, bg=BACKGROUND_COLOR)
        bottom_frame.pack(fill='x', padx=20, pady=(0, 20))
        
        bottom_actions = [
            ("🖨 Imprimer PDF", self.imprimer_pdf),
            ("📄 Exporter Word", self.exporter_word),
            ("📛 Gérer Doublons", self.gerer_doublons),
            ("📊 Dépôts Journaliers", self.afficher_depots_journaliers),
            ("📈 Rapport Global", self.afficher_rapport_global),
            ("❌ Fermer", self.destroy)
        ]
        
        for text, cmd in bottom_actions:
            btn = ttk.Button(bottom_frame, text=text, command=cmd, width=15)
            btn.pack(side='left', padx=5)
        
        self.label_ref = ttk.Label(bottom_frame, 
                                 textvariable=self.dernier_ref, 
                                 font=('Helvetica', 10, 'italic'),
                                 foreground=DARK_GRAY)
        self.label_ref.pack(side='right', padx=10)
    
    def get_parametre(self, cle):
        """Récupère un paramètre depuis la base de données"""
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,))
            result = cur.fetchone()
            if result:
                try:
                    return float(result[0])
                except:
                    return result[0]
            return None
    
    def validate_amount(self, value):
        """Validation du champ montant"""
        if value == "":
            return True
        try:
            float(value)
            return True
        except ValueError:
            return False
    
    def charger_historique(self):
        """Charge les 30 derniers dépôts dans l'historique"""
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT date_depot, heure, 
                       (SELECT nom || ' ' || postnom || ' ' || prenom 
                        FROM abonne 
                        WHERE numero_client = d.numero_client) as nom_client,
                       montant, ref_depot, nom_agent
                FROM depots d
                ORDER BY date_depot DESC, heure DESC
                LIMIT 30
            """)
            for row in cur.fetchall():
                self.hist_tree.insert("", "end", values=row)
    
    def afficher_nom_et_solde(self):
        """Affiche les informations de l'abonné"""
        abonne = self.chercher_abonne()
        if not abonne:
            self.label_nom_client.config(text="Nom du Client : Client introuvable")
            self.label_solde.config(text="Solde Actuel : -")
            return False
        
        nom_complet = f"{abonne[1]} {abonne[2]} {abonne[3]}"
        self.label_nom_client.config(text=f"Nom du Client : {nom_complet}")
        self.label_solde.config(text=f"Solde Actuel : {abonne[5]:,.2f} FC")
        return True
    
    def chercher_abonne(self):
        """Recherche un abonné dans la base de données"""
        numero_client = self.entries["entry_numero_client"].get().strip()
        numero_carte = self.entries["entry_numero_carte"].get().strip()
        
        if not numero_client and not numero_carte:
            messagebox.showerror("Erreur", "Veuillez entrer un numéro client ou un numéro de carte.", parent=self)
            return None

        with connexion_db() as conn:
            cur = conn.cursor()
            abonne = None
            
            try:
                if numero_client:
                    cur.execute("""
                        SELECT a.numero_client, a.nom, a.postnom, a.prenom, a.numero_carte, a.solde, a.type_compte 
                        FROM abonne a 
                        WHERE a.numero_client = ?
                    """, (numero_client,))
                else:
                    cur.execute("""
                        SELECT a.numero_client, a.nom, a.postnom, a.prenom, a.numero_carte, a.solde, a.type_compte 
                        FROM abonne a 
                        WHERE a.numero_carte = ?
                    """, (numero_carte,))
                
                abonne = cur.fetchone()
                
            except sqlite3.Error as e:
                messagebox.showerror("Erreur BD", f"Erreur base de données: {str(e)}", parent=self)
                return None

        if not abonne:
            messagebox.showerror("Erreur", "Aucun abonné trouvé avec ces identifiants", parent=self)
            return None
        
        return abonne
    
    def effectuer_depot(self):
        """Effectue un dépôt sur le compte de l'abonné"""
        abonne = self.chercher_abonne()
        if not abonne:
            return

        # Afficher les infos de l'abonné
        nom_complet = f"{abonne[1]} {abonne[2]} {abonne[3]}"
        self.label_nom_client.config(text=f"Nom du Client : {nom_complet}")
        self.label_solde.config(text=f"Solde Actuel : {abonne[5]:,.2f} FC")

        # Vérification du type de compte
        if abonne[6] == "Fixe" and self.type_compte_var.get() == "normal":
            messagebox.showerror("Erreur", 
                                f"{nom_complet} a un compte fixe et ne peut pas effectuer de dépôt mixte.",
                                parent=self)
            return

        try:
            montant = float(self.entries["entry_montant"].get().strip())
            if montant <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Erreur", "Montant invalide (nombre positif requis)", parent=self)
            return

        # Déterminer le type de dépôt
        is_depot_fixe = (
            self.type_compte_var.get() == "fixe" and 
            abonne[6] == "Fixe"
        )

        # Règles pour les comptes fixes (UNIQUEMENT si l'option "Fixe" est sélectionnée)
        if is_depot_fixe:
            with connexion_db() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT montant_initial, numero_carte
                    FROM compte_fixe 
                    WHERE numero_client = ?
                """, (abonne[0],))
                result = cur.fetchone()
                
                if not result or result[0] <= 0:
                    messagebox.showerror("Erreur", "Configuration du compte fixe invalide", parent=self)
                    return
                    
                montant_initial = result[0]
                numero_carte = result[1]  # Récupérer le numéro de carte du compte fixe
                
                if montant < montant_initial:
                    messagebox.showerror(
                        "Erreur", 
                        f"Minimum pour compte fixe: {montant_initial:,.2f} FC",
                        parent=self
                    )
                    return
                    
                # Vérifier si le montant est un multiple du montant initial
                if montant % montant_initial != 0:
                    messagebox.showerror("Erreur", 
                                        f"Pour un compte fixe, le montant doit être un multiple de {montant_initial:,.2f} FC",
                                        parent=self)
                    return
                
                # Calculer le nombre de cases à ajouter
                nb_cases = int(montant / montant_initial)
                
                # Vérifier si le compte a déjà 8 pages complètes (248 cases)
                cur.execute("""
                    SELECT SUM(cases_remplies) 
                    FROM compte_fixe_pages 
                    WHERE numero_client = ?
                """, (abonne[0],))
                total_cases = cur.fetchone()[0] or 0
                
                if total_cases + nb_cases > 248:
                    messagebox.showerror("Compte fixe bloqué", 
                                        "Ce compte fixe a atteint le maximum de 8 pages (248 cases). Aucun dépôt supplémentaire n'est possible.",
                                        parent=self)
                    return
        else:  # Règles pour les dépôts mixtes/normaux
            depot_min_normal = self.get_parametre('depot_min') or 500  # Valeur par défaut 500 si non trouvé
            if montant < depot_min_normal:
                messagebox.showerror(
                    "Erreur", 
                    f"Dépôt minimum: {depot_min_normal} FC",
                    parent=self
                )
                return

        heure = datetime.now().strftime("%H:%M:%S")
        date_depot = datetime.now().strftime("%Y-%m-%d")
        ref_depot = f"DEP{datetime.now().strftime('%Y%m%d')}-{random.randint(10000,99999)}"
        numero_client = abonne[0]
        ancien_solde = abonne[5]
        nouveau_solde = ancien_solde + montant

        with connexion_db() as conn:
            try:
                cur = conn.cursor()
                
                # Mettre à jour le solde dans la table abonne
                cur.execute("UPDATE abonne SET solde = ? WHERE numero_client = ?", (nouveau_solde, numero_client))
                
                # Insérer le dépôt
                cur.execute("""
                    INSERT INTO depots (numero_client, heure, montant, date_depot, ref_depot, nom_agent)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (numero_client, heure, montant, date_depot, ref_depot, self.nom_agent))
                
                # Gestion spécifique du compte fixe (UNIQUEMENT pour dépôts fixes)
                if is_depot_fixe:
                    # Insérer les cases dans compte_fixe_cases
                    for i in range(nb_cases):
                        cur.execute("""
                            INSERT INTO compte_fixe_cases (
                                numero_client, numero_carte, ref_depot, 
                                date_remplissage, montant
                            ) VALUES (?, ?, ?, ?, ?)
                        """, (
                            numero_client, 
                            numero_carte,
                            ref_depot,
                            datetime.now().strftime("%Y-%m-%d"),
                            montant_initial
                        ))
                    
                    # Gestion des pages
                    cases_restantes = nb_cases
                    
                    # Trouver les pages existantes non pleines
                    cur.execute("""
                        SELECT page, cases_remplies 
                        FROM compte_fixe_pages 
                        WHERE numero_client = ? AND cases_remplies < 31
                        ORDER BY page
                    """, (abonne[0],))
                    pages_non_pleines = cur.fetchall()
                    
                    # Remplir les pages existantes d'abord
                    for page in pages_non_pleines:
                        if cases_restantes <= 0:
                            break
                            
                        page_num, cases_remplies = page
                        cases_possibles = 31 - cases_remplies
                        cases_a_ajouter = min(cases_restantes, cases_possibles)
                        
                        cur.execute("""
                            UPDATE compte_fixe_pages 
                            SET cases_remplies = cases_remplies + ?
                            WHERE numero_client = ? AND page = ?
                        """, (cases_a_ajouter, numero_client, page_num))
                        
                        cases_restantes -= cases_a_ajouter
                    
                    # Créer de nouvelles pages si nécessaire
                    while cases_restantes > 0:
                        # Trouver le numéro de la dernière page
                        cur.execute("""
                            SELECT MAX(page) 
                            FROM compte_fixe_pages 
                            WHERE numero_client = ?
                        """, (numero_client,))
                        last_page = cur.fetchone()[0] or 0
                        
                        if last_page >= 8:
                            messagebox.showwarning("Attention", "Le plafond de 8 pages a été atteint! Les cases restantes ne seront pas ajoutées.", parent=self)
                            break
                            
                        new_page = last_page + 1
                        cases_a_ajouter = min(cases_restantes, 31)
                        
                        cur.execute("""
                            INSERT INTO compte_fixe_pages (numero_client, numero_carte, page, cases_remplies)
                            VALUES (?, ?, ?, ?)
                        """, (numero_client, numero_carte, new_page, cases_a_ajouter))
                        
                        cases_restantes -= cases_a_ajouter
                
                conn.commit()

                self.dernier_bordereau.clear()
                self.dernier_bordereau.update({
                    "nom_complet": nom_complet,
                    "numero_client": numero_client,
                    "numero_carte": abonne[4],
                    "montant": montant,
                    "ancien_solde": ancien_solde,
                    "nouveau_solde": nouveau_solde,
                    "ref": ref_depot,
                    "date_heure": datetime.now().strftime("%d/%m/%Y %H:%M"),
                    "nom_agent": self.nom_agent
                })

                self.dernier_ref.set(f"Réf: {ref_depot}")
                messagebox.showinfo("Succès", f"Dépôt de {montant:,.2f} FC effectué avec succès.", parent=self)
                ajouter_journal("Dépôt", self.nom_agent, nom_complet)
                
                # Actualiser l'affichage
                self.afficher_nom_et_solde()
                self.hist_tree.delete(*self.hist_tree.get_children())
                self.charger_historique()
                
                # Vérifier la progression après dépôt (uniquement pour dépôts fixes)
                if is_depot_fixe:
                    self.verifier_compte_fixe(ref_depot)
                
                # Générer et afficher les chemins des bordereaux
                def generer_et_afficher():
                    try:
                        pdf_path, word_path = export_pdf.generer_bordereaux(self.dernier_bordereau, "depot")
                        messagebox.showinfo(
                            "Bordereaux générés",
                            f"Bordereaux enregistrés avec succès!\n\n"
                            f"PDF: {pdf_path}\n"
                            f"Word: {word_path}",
                            parent=self
                        )
                    except Exception as e:
                        messagebox.showerror("Erreur", f"Erreur lors de la génération: {str(e)}", parent=self)
                
                threading.Thread(target=generer_et_afficher).start()

            except Exception as e:
                conn.rollback()
                messagebox.showerror("Erreur", f"Erreur base de données : {e}", parent=self)
    
    def verifier_compte_fixe(self, ref_depot=None):
        """Vérifie la progression du compte fixe"""
        abonne = self.chercher_abonne()
        if not abonne:
            return
            
        if abonne[6] != "Fixe":
            messagebox.showerror("Erreur", "Ce client n'a pas de compte fixe", parent=self)
            return
            
        numero_client = abonne[0]
        with connexion_db() as conn:
            cur = conn.cursor()
        
            try:
                # Requête optimisée pour récupérer les données de progression
                cur.execute("""
                    SELECT 
                        cf.montant_initial,
                        (SELECT COUNT(*) FROM compte_fixe_pages 
                         WHERE numero_client = ? AND cases_remplies = 31) AS pages_completes,
                        (SELECT SUM(cases_remplies) FROM compte_fixe_pages 
                         WHERE numero_client = ?) AS total_cases,
                        (SELECT SUM(montant) FROM retraits 
                         WHERE numero_client = ?) AS total_retires
                    FROM compte_fixe cf
                    WHERE cf.numero_client = ?
                """, (numero_client, numero_client, numero_client, numero_client))
            
                result = cur.fetchone()
            
                if not result:
                    messagebox.showerror("Erreur", "Compte fixe non trouvé", parent=self)
                    return
            
                montant_initial = result[0]
                pages_remplies = result[1] or 0
                total_cases = result[2] or 0
                total_retires = result[3] or 0
                
                total_epargne = total_cases * montant_initial
                montant_restant = total_epargne - total_retires
            
                # Récupérer les données détaillées des pages
                cur.execute("""
                    SELECT page, cases_remplies
                    FROM compte_fixe_pages
                    WHERE numero_client = ?
                    ORDER BY page
                """, (numero_client,))
                pages_data = cur.fetchall()
            
                # Calculer le pourcentage de progression
                total_possible = 8 * 31  # 8 pages x 31 cases
                pourcentage = (total_cases / total_possible) * 100 if total_possible > 0 else 0
            
                # Créer une fenêtre pour afficher les résultats
                fen_progression = tk.Toplevel(self)
                fen_progression.title("Progression du Compte Fixe")
                fen_progression.geometry("500x800")
                fen_progression.configure(bg=BACKGROUND_COLOR)
            
                # Style
                style = ttk.Style()
                style.configure('TFrame', background=BACKGROUND_COLOR)
                style.configure('TLabel', background=BACKGROUND_COLOR, foreground=TEXT_COLOR, font=('Helvetica', 12))
                style.configure('Title.TLabel', font=('Helvetica', 14, 'bold'), foreground=PRIMARY_COLOR)
            
                main_frame = ttk.Frame(fen_progression)
                main_frame.pack(fill='both', expand=True, padx=20, pady=20)
            
                # Titre
                ttk.Label(main_frame, 
                     text="PROGRESSION DU COMPTE FIXE", 
                     style='Title.TLabel').pack(pady=10)
            
                # Informations
                ttk.Label(main_frame, 
                     text=f"Client: {abonne[1]} {abonne[2]} {abonne[3]}").pack(anchor='w', pady=5)
            
                ttk.Label(main_frame, 
                     text=f"Numéro client: {abonne[0]}").pack(anchor='w', pady=5)
            
                ttk.Label(main_frame, 
                     text=f"Montant initial: {montant_initial:,.2f} FC").pack(anchor='w', pady=5)
            
                # Affichage des pages complètes et cases remplies
                ttk.Label(main_frame, 
                     text=f"Pages complètes: {pages_remplies}/8").pack(anchor='w', pady=5)
            
                ttk.Label(main_frame, 
                     text=f"Cases remplies: {total_cases}/248").pack(anchor='w', pady=5)
            
                ttk.Label(main_frame, 
                     text=f"Montant épargné: {total_epargne:,.2f} FC").pack(anchor='w', pady=5)
                     
                ttk.Label(main_frame, 
                     text=f"Montant retiré: {total_retires:,.2f} FC").pack(anchor='w', pady=5)
                     
                ttk.Label(main_frame, 
                     text=f"Montant restant: {montant_restant:,.2f} FC", 
                     font=('Helvetica', 11, 'bold')).pack(anchor='w', pady=5)
            
                # Barre de progression
                progress_frame = ttk.Frame(main_frame)
                progress_frame.pack(fill='x', pady=15)
            
                ttk.Label(progress_frame, 
                     text="Progression globale:").pack(anchor='w')
            
                progress = ttk.Progressbar(progress_frame, 
                                      orient='horizontal', 
                                      length=400, 
                                      mode='determinate',
                                      maximum=100)
                progress.pack(fill='x', pady=5)
                progress['value'] = pourcentage
            
                ttk.Label(progress_frame, 
                     text=f"{pourcentage:.1f}%").pack(anchor='e')
            
                # Message d'encouragement
                if pourcentage >= 90:
                    message = "Félicitations! Votre compte fixe est presque terminé!"
                    color = "green"
                elif pourcentage >= 50:
                    message = "Continuez ainsi! Vous avez déjà fait plus de la moitié!"
                    color = "blue"
                else:
                    message = "Bonne progression! Continuez à épargner régulièrement."
                    color = "orange"
            
                ttk.Label(main_frame, 
                     text=message,
                     foreground=color,
                     font=('Helvetica', 11, 'italic')).pack(pady=10)
            
                def exporter_cartes():
                    try:
                        data = {
                            "numero_client": numero_client,
                            "nom_client": f"{abonne[1]} {abonne[2]} {abonne[3]}",
                            "montant_initial": montant_initial,
                            "pages": pages_data,
                            "ref": ref_depot  # Passer la référence du dépôt
                        }
                        export_carte.exporter_cartes_compte_fixe(data)
                    except Exception as e:
                        messagebox.showerror("Erreur", f"Erreur lors de l'export: {str(e)}", parent=fen_progression)

                ttk.Button(main_frame, 
                            text="Exporter les Cartes PDF", 
                            command=exporter_cartes).pack(pady=10)
                
                def reinitialiser_compte():
                    """Réinitialise le compte fixe à zéro"""
                    if messagebox.askyesno("Confirmation", 
                                          "Voulez-vous réinitialiser ce compte fixe?\n\nTous les dépôts et retraits seront supprimés et le solde remis à zéro. Cette action est irréversible!",
                                          parent=fen_progression):
                        try:
                            with connexion_db() as conn:
                                cur = conn.cursor()
                                
                                # Supprimer les pages du compte fixe
                                cur.execute("DELETE FROM compte_fixe_pages WHERE numero_client = ?", (numero_client,))
                                
                                # Supprimer les dépôts et retraits
                                cur.execute("DELETE FROM depots WHERE numero_client = ?", (numero_client,))
                                cur.execute("DELETE FROM retraits WHERE numero_client = ?", (numero_client,))
                                
                                # Réinitialiser le solde
                                cur.execute("UPDATE abonne SET solde = 0 WHERE numero_client = ?", (numero_client,))
                                
                                conn.commit()
                                
                                messagebox.showinfo("Succès", "Compte fixe réinitialisé avec succès!", parent=fen_progression)
                                fen_progression.destroy()
                                self.afficher_nom_et_solde()
                        except Exception as e:
                            messagebox.showerror("Erreur", f"Erreur lors de la réinitialisation: {str(e)}", parent=fen_progression)

                ttk.Button(main_frame, 
                          text="Réinitialiser Compte", 
                          command=reinitialiser_compte,
                          style="TButton").pack(pady=10)
            
                # Bouton fermer
                ttk.Button(main_frame, 
                          text="Fermer", 
                          command=fen_progression.destroy).pack(pady=10)
            
            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur lors de la vérification: {str(e)}", parent=self)
        
    def afficher_historique_client(self):
        """Affiche l'historique complet des dépôts d'un client"""
        abonne = self.chercher_abonne()
        if not abonne:
            messagebox.showerror("Erreur", "Veuillez d'abord rechercher un client", parent=self)
            return

        numero_client = abonne[0]
        nom_complet = f"{abonne[1]} {abonne[2]} {abonne[3]}"
        
        with connexion_db() as conn:
            cur = conn.cursor()
            
            # Récupérer la date d'inscription
            cur.execute("SELECT date_inscription FROM abonne WHERE numero_client = ?", (numero_client,))
            date_inscription = cur.fetchone()[0]
            
            # Calculer la durée du compte
            try:
                date_insc = datetime.strptime(date_inscription, "%Y-%m-%d")
                duree = (datetime.now() - date_insc).days
                annees = duree // 365
                mois = (duree % 365) // 30
                duree_txt = f"{annees} an(s) et {mois} mois"
            except:
                duree_txt = "Inconnue"
            
            # Récupérer les dépôts
            cur.execute("""
                SELECT date_depot, heure, montant, ref_depot, nom_agent
                FROM depots
                WHERE numero_client = ?
                ORDER BY date_depot DESC, heure DESC
            """, (numero_client,))
            depots = cur.fetchall()
            
            # Créer la fenêtre d'historique
            fen_hist = tk.Toplevel(self)
            fen_hist.title(f"Historique des dépôts - {nom_complet}")
            fen_hist.geometry("1000x600")
            fen_hist.configure(bg=BACKGROUND_COLOR)
            
            # Titre
            tk.Label(fen_hist, 
                    text=f"HISTORIQUE DES DÉPÔTS - {nom_complet.upper()}", 
                    font=("Helvetica", 16, "bold"),
                    bg=PRIMARY_COLOR,
                    fg="white").pack(fill="x", padx=10, pady=10)
            
            # Informations client
            info_frame = tk.Frame(fen_hist, bg=BACKGROUND_COLOR)
            info_frame.pack(fill="x", padx=10, pady=5)
            
            tk.Label(info_frame, 
                    text=f"N° Client: {numero_client} | Date inscription: {date_inscription} | Durée: {duree_txt}",
                    font=("Helvetica", 10),
                    bg=BACKGROUND_COLOR).pack(side="left")
            
            # Treeview pour afficher les dépôts
            columns = ("Date", "Heure", "Montant (FC)", "Référence", "Agent")
            tree = ttk.Treeview(fen_hist, columns=columns, show="headings", height=20)
            
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, width=150, anchor="center")
            
            scrollbar = ttk.Scrollbar(fen_hist, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=scrollbar.set)
            
            tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
            scrollbar.pack(side="right", fill="y")
            
            # Ajouter les données
            total = 0
            for depot in depots:
                tree.insert("", "end", values=(depot[0], depot[1], f"{depot[2]:,.2f}", depot[3], depot[4]))
                total += depot[2]
            
            # Afficher le total
            tk.Label(fen_hist, 
                    text=f"TOTAL DES DÉPÔTS: {total:,.2f} FC", 
                    font=("Helvetica", 12, "bold"),
                    bg=SECONDARY_COLOR,
                    fg="white").pack(fill="x", padx=10, pady=5)
            
            # Bouton pour exporter en PDF
            def exporter_releve_pdf():
                try:
                    # Préparer les données pour le PDF
                    data = {
                        "nom_complet": nom_complet,
                        "numero_client": numero_client,
                        "date_inscription": date_inscription,
                        "duree_compte": duree_txt,
                        "depots": depots,
                        "total_depots": total
                    }
                    # Note: Cette fonction doit être définie dans export_pdf
                    export_pdf.exporter_releve_client_pdf(data)
                except Exception as e:
                    messagebox.showerror("Erreur PDF", f"Erreur lors de la génération du PDF: {str(e)}", parent=fen_hist)
            
            btn_frame = tk.Frame(fen_hist, bg=BACKGROUND_COLOR)
            btn_frame.pack(fill="x", padx=10, pady=10)
            
            ttk.Button(btn_frame, 
                     text="Exporter PDF", 
                     command=exporter_releve_pdf,
                     style="TButton").pack(side="left", padx=5)
            
            ttk.Button(btn_frame, 
                     text="Fermer", 
                     command=fen_hist.destroy,
                     style="TButton").pack(side="right", padx=5)
    
    def afficher_comptes_fixes(self):
        """Affiche tous les comptes fixes avec numéro carte et numéro client"""
        with connexion_db() as conn:
            cur = conn.cursor()
            try:
                cur.execute("""
                    SELECT a.numero_client, a.nom || ' ' || a.postnom || ' ' || a.prenom, 
                           cf.numero_carte, cf.montant_initial
                    FROM compte_fixe cf
                    JOIN abonne a ON cf.numero_client = a.numero_client
                """)
                comptes = cur.fetchall()
                
                # Créer une nouvelle fenêtre pour afficher les résultats
                fen_comptes = tk.Toplevel(self)
                fen_comptes.title("Liste des Comptes Fixes")
                fen_comptes.geometry("900x600")
                fen_comptes.configure(bg=BACKGROUND_COLOR)
                
                # Titre
                tk.Label(fen_comptes, 
                        text="LISTE DES COMPTES FIXES", 
                        font=("Helvetica", 16, "bold"),
                        bg=PRIMARY_COLOR,
                        fg="white").pack(fill="x", padx=10, pady=10)
                
                # Treeview pour afficher les comptes
                columns = ("N° Client", "Nom Client", "N° Carte", "Montant Initial")
                tree = ttk.Treeview(fen_comptes, columns=columns, show="headings", height=25)
                
                for col in columns:
                    tree.heading(col, text=col)
                    tree.column(col, width=180, anchor="center")
                
                scrollbar = ttk.Scrollbar(fen_comptes, orient="vertical", command=tree.yview)
                tree.configure(yscrollcommand=scrollbar.set)
                
                tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
                scrollbar.pack(side="right", fill="y")
                
                # Ajouter les données
                for compte in comptes:
                    tree.insert("", "end", values=(
                        compte[0],
                        compte[1],
                        compte[2],
                        f"{compte[3]:,.2f} FC"
                    ))
                
                # Bouton fermer
                ttk.Button(fen_comptes, 
                         text="Fermer", 
                         command=fen_comptes.destroy).pack(pady=10)
                
            except sqlite3.Error as e:
                messagebox.showerror("Erreur BD", f"Erreur base de données: {str(e)}", parent=self)
    
    def afficher_depots_journaliers(self):
        """Affiche les dépôts effectués aujourd'hui"""
        today = datetime.now().strftime("%Y-%m-%d")
        
        with connexion_db() as conn:
            cur = conn.cursor()
            
            try:
                # Récupérer les dépôts du jour
                cur.execute("""
                    SELECT d.date_depot, d.heure, a.nom || ' ' || a.postnom || ' ' || a.prenom, 
                           d.montant, d.ref_depot, d.nom_agent
                    FROM depots d
                    JOIN abonne a ON d.numero_client = a.numero_client
                    WHERE d.date_depot = ?
                    ORDER BY d.heure DESC
                """, (today,))
                
                depots = cur.fetchall()
                
                # Créer une nouvelle fenêtre pour afficher les résultats
                fen_depots = tk.Toplevel(self)
                fen_depots.title(f"Dépôts Journaliers - {today}")
                fen_depots.geometry("1000x600")
                fen_depots.configure(bg=BACKGROUND_COLOR)
                
                # Titre
                tk.Label(fen_depots, 
                        text=f"DÉPÔTS EFFECTUÉS AUJOURD'HUI ({today})", 
                        font=("Helvetica", 16, "bold"),
                        bg=PRIMARY_COLOR,
                        fg="white").pack(fill="x", padx=10, pady=10)
                
                # Treeview pour afficher les dépôts
                columns = ("Heure", "Client", "Montant", "Référence", "Agent")
                tree = ttk.Treeview(fen_depots, columns=columns, show="headings", height=20)
                
                for col in columns:
                    tree.heading(col, text=col)
                    tree.column(col, width=150, anchor="center")
                
                scrollbar = ttk.Scrollbar(fen_depots, orient="vertical", command=tree.yview)
                tree.configure(yscrollcommand=scrollbar.set)
                
                tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
                scrollbar.pack(side="right", fill="y")
                
                # Ajouter les données
                total = 0
                for depot in depots:
                    tree.insert("", "end", values=(depot[1], depot[2], f"{depot[3]:,.2f} FC", depot[4], depot[5]))
                    total += depot[3]
                
                # Afficher le total
                tk.Label(fen_depots, 
                        text=f"TOTAL DES DÉPÔTS: {total:,.2f} FC", 
                        font=("Helvetica", 12, "bold"),
                        bg=SECONDARY_COLOR,
                        fg="white").pack(fill="x", padx=10, pady=5)
                
                # Bouton pour exporter en PDF
                btn_frame = tk.Frame(fen_depots, bg=BACKGROUND_COLOR)
                btn_frame.pack(fill="x", padx=10, pady=10)
                
                # Fonction pour exporter en PDF dans un thread
                def exporter_en_pdf():
                    try:
                        chemin = exporter_depots_journaliers_pdf(depots, total, today)
                        messagebox.showinfo("Succès", f"Rapport journalier exporté avec succès dans :\n{chemin}", parent=fen_depots)
                    except Exception as e:
                        messagebox.showerror("Erreur", f"Erreur lors de l'export : {str(e)}", parent=fen_depots)
                
                ttk.Button(btn_frame, 
                         text="Exporter en PDF", 
                         command=lambda: threading.Thread(target=exporter_en_pdf).start(),
                         style="TButton").pack(side="left", padx=5)
                
                ttk.Button(btn_frame, 
                         text="Fermer", 
                         command=fen_depots.destroy,
                         style="TButton").pack(side="right", padx=5)
                
            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur lors de la récupération des dépôts: {str(e)}", parent=self)
    
    def afficher_rapport_global(self):
        """Affiche un rapport global de tous les dépôts"""
        with connexion_db() as conn:
            cur = conn.cursor()
            
            try:
                # Récupérer tous les dépôts groupés par client
                cur.execute("""
                    SELECT a.numero_client, a.nom || ' ' || a.postnom || ' ' || a.prenom, 
                           SUM(d.montant), COUNT(d.id)
                    FROM abonne a
                    LEFT JOIN depots d ON a.numero_client = d.numero_client
                    GROUP BY a.numero_client
                    ORDER BY SUM(d.montant) DESC
                """)
                
                clients = cur.fetchall()
                
                # Créer une nouvelle fenêtre pour afficher les résultats
                fen_rapport = tk.Toplevel(self)
                fen_rapport.title("Rapport Global des Dépôts")
                fen_rapport.geometry("1000x600")
                fen_rapport.configure(bg=BACKGROUND_COLOR)
                
                # Titre
                tk.Label(fen_rapport, 
                        text="RAPPORT GLOBAL DES DÉPÔTS PAR CLIENT", 
                        font=("Helvetica", 16, "bold"),
                        bg=PRIMARY_COLOR,
                        fg="white").pack(fill="x", padx=10, pady=10)
                
                # Treeview pour afficher les clients
                columns = ("Code Client", "Nom Client", "Total Dépôts (FC)", "Nombre Dépôts")
                tree = ttk.Treeview(fen_rapport, columns=columns, show="headings", height=20)
                
                for col in columns:
                    tree.heading(col, text=col)
                    tree.column(col, width=150, anchor="center")
                
                scrollbar = ttk.Scrollbar(fen_rapport, orient="vertical", command=tree.yview)
                tree.configure(yscrollcommand=scrollbar.set)
                
                tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)
                scrollbar.pack(side="right", fill="y")
                
                # Ajouter les données
                total_general = 0
                for client in clients:
                    total_client = client[2] if client[2] else 0
                    tree.insert("", "end", values=(
                        client[0],
                        client[1],
                        f"{total_client:,.2f}",
                        client[3] if client[3] else 0
                    ))
                    total_general += total_client
                
                # Afficher le total général
                tk.Label(fen_rapport, 
                        text=f"TOTAL GÉNÉRAL: {total_general:,.2f} FC", 
                        font=("Helvetica", 12, "bold"),
                        bg=SECONDARY_COLOR,
                        fg="white").pack(fill="x", padx=10, pady=5)
                
                # Bouton pour exporter en PDF
                btn_frame = tk.Frame(fen_rapport, bg=BACKGROUND_COLOR)
                btn_frame.pack(fill="x", padx=10, pady=10)
                
                # Fonction pour exporter en PDF dans un thread
                def exporter_en_pdf():
                    try:
                        chemin = exporter_rapport_global_pdf(clients, total_general)
                        messagebox.showinfo("Succès", f"Rapport global exporté avec succès dans :\n{chemin}", parent=fen_rapport)
                    except Exception as e:
                        messagebox.showerror("Erreur", f"Erreur lors de l'export : {str(e)}", parent=fen_rapport)
                
                ttk.Button(btn_frame, 
                         text="Exporter en PDF", 
                         command=lambda: threading.Thread(target=exporter_en_pdf).start(),
                         style="TButton").pack(side="left", padx=5)
                
                ttk.Button(btn_frame, 
                         text="Fermer", 
                         command=fen_rapport.destroy,
                         style="TButton").pack(side="right", padx=5)
                
            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur lors de la génération du rapport: {str(e)}", parent=self)
    
    def imprimer_pdf(self):
        """Génère le bordereau de dépôt en PDF et affiche le chemin"""
        if not self.dernier_bordereau:
            messagebox.showerror("Erreur", "Aucun bordereau disponible à générer", parent=self)
            return
        
        try:
            pdf_path, _ = export_pdf.generer_bordereaux(self.dernier_bordereau, "depot")
            messagebox.showinfo(
                "PDF généré",
                f"Bordereau PDF enregistré avec succès!\n\nChemin: {pdf_path}",
                parent=self
            )
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la génération: {str(e)}", parent=self)
    
    def exporter_word(self):
        """Génère le bordereau de dépôt en Word et affiche le chemin"""
        if not self.dernier_bordereau:
            messagebox.showerror("Erreur", "Aucun bordereau disponible à exporter", parent=self)
            return
        
        try:
            _, word_path = export_pdf.generer_bordereaux(self.dernier_bordereau, "depot")
            messagebox.showinfo(
                "Word généré",
                f"Bordereau Word enregistré avec succès!\n\nChemin: {word_path}",
                parent=self
            )
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'export: {str(e)}", parent=self)
    
    def gerer_doublons(self):
        """Ouvre l'interface de gestion des doublons"""
        # Créer une nouvelle fenêtre pour la gestion des doublons
        fen_doublons = tk.Toplevel(self)
        fen_doublons.title("Gestion des Doublons")
        fen_doublons.geometry("1000x600")
        
        # Intégrer l'interface de gestion des doublons
        interface_doublons.DoublonsInterface(fen_doublons)

# --- Pour tester l'interface seule ---
if __name__ == "__main__":
    root = tk.Tk()
    app = FenetreDepot(root, "Agent_test")
    root.mainloop()