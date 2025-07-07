import tkinter as tk
from tkinter import ttk, messagebox
import datetime
import random
import os
import webbrowser
import threading
import time
import sqlite3
from PIL import Image, ImageDraw, ImageTk, ImageFont
import sys
import hashlib
import logging
import shutil
from typing import Optional, Tuple
import export_retrait
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import math

# Configuration des couleurs
BG_COLOR = "#f0f8ff"
HEADER_COLOR = "#2c3e50"
ACCENT_COLOR = "#3498db"
BUTTON_COLOR = "#3498db"
BUTTON_HOVER_COLOR = "#2980b9"
TEXT_COLOR = "#2c3e50"
ENTRY_BG = "#ffffff"
SUCCESS_COLOR = "#2ecc71"
ERROR_COLOR = "#e74c3c"
WARNING_COLOR = "#f39c12"

# Configuration du logging
logging.basicConfig(
    filename='app.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filemode='a'
)

logger = logging.getLogger(__name__)

# ==================== FONCTIONS UTILITAIRES ====================

def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_db_path() -> str:
    appdata_dir = os.getenv("APPDATA")
    app_folder = os.path.join(appdata_dir, "MyApp")
    os.makedirs(app_folder, exist_ok=True)
    local_db = os.path.join(app_folder, "data_epargne.db")

    if not os.path.exists(local_db):
        original_db = resource_path("data_epargne.db")
        if os.path.exists(original_db):
            shutil.copyfile(original_db, local_db)
    
    return local_db

def get_rapports_dir() -> str:
    """Retourne le chemin du dossier de rapports dans Documents de l'utilisateur"""
    try:
        # Chemin du dossier Documents de l'utilisateur
        documents_dir = os.path.join(os.path.expanduser("~"), "Documents")
        
        # Chemin complet du dossier de rapports
        rapports_dir = os.path.join(documents_dir, "Rapport de retrait")
        
        # Création du dossier avec permissions d'écriture
        os.makedirs(rapports_dir, exist_ok=True)
        
        # Vérification des permissions
        test_file = os.path.join(rapports_dir, "permission_test.txt")
        try:
            with open(test_file, 'w') as f:
                f.write("Test de permission")
            os.remove(test_file)
        except Exception as e:
            logger.error(f"Erreur de permission pour {rapports_dir}: {str(e)}")
            # Fallback vers AppData si échec
            appdata_dir = os.getenv("APPDATA")
            rapports_dir = os.path.join(appdata_dir, "MyApp", "Rapports")
            os.makedirs(rapports_dir, exist_ok=True)
        
        return rapports_dir
    except Exception as e:
        logger.error(f"Erreur création dossier rapports: {str(e)}")
        # Fallback vers le répertoire courant
        return os.getcwd()

def connexion_db() -> sqlite3.Connection:
    chemin_db = get_db_path()
    max_attempts = 5
    
    for attempt in range(max_attempts):
        try:
            conn = sqlite3.connect(
                chemin_db,
                timeout=30,
                check_same_thread=False
            )
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("SELECT 1").fetchone()
            return conn
            
        except sqlite3.OperationalError as e:
            if attempt == max_attempts - 1:
                raise sqlite3.OperationalError(
                    f"Échec connexion après {max_attempts} tentatives"
                ) from e
            time.sleep(min(2 ** attempt, 10))
    
    raise sqlite3.Error("Échec inattendu de connexion")

def hash_password(password: str, salt: str = "fixed_salt_value") -> str:
    return hashlib.sha256((password + salt).encode()).hexdigest()

def ajouter_journal(action: str, acteur: str, cible: Optional[str] = None, 
                   details: Optional[str] = None) -> bool:
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with connexion_db() as conn:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO journal 
                    (action, acteur, cible, details, date_action, heure_action)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    action, acteur, cible, details,
                    datetime.datetime.now().strftime("%Y-%m-%d"),
                    datetime.datetime.now().strftime("%H:%M:%S")
                ))
                conn.commit()
                return True
        except sqlite3.Error as e:
            logger.error(f"Erreur journalisation: {e}")
            time.sleep(0.5 * (attempt + 1))
    return False

# ==================== FONCTIONS POUR L'INTERFACE DE RETRAIT ====================

def create_default_avatar(name: str, size: Tuple[int, int] = (60, 60)) -> ImageTk.PhotoImage:
    # Correction: Vérifier le type de name
    if not isinstance(name, str):
        name = ""
    
    colors = ["#FF5733", "#33FF57", "#3357FF", "#F333FF"]
    bg_color = random.choice(colors)
    img = Image.new('RGB', size, bg_color)
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 20)
    except:
        font = ImageFont.load_default()
    
    initials = name[0].upper() if name else "A"
    bbox = draw.textbbox((0, 0), initials, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    position = ((size[0] - text_width) // 2, (size[1] - text_height) // 2)
    draw.text(position, initials, font=font, fill="white")
    
    return ImageTk.PhotoImage(img)

def get_parametre(cle: str, default: float) -> float:
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT valeur FROM parametres WHERE cle = ?", (cle,))
            result = cur.fetchone()
            return float(result[0]) if result else default
    except sqlite3.Error as e:
        logger.error(f"Erreur récupération paramètre {cle}: {e}")
        return default

def interface_retrait(nom_agent, parent_window=None):
    # CORRECTION PRINCIPALE : Utiliser la fenêtre parente si fournie
    root = parent_window if parent_window else tk.Toplevel()
    
    # Récupération des paramètres système
    taux_interet = get_parametre('taux_interet', 5.0)
    montant_min_retrait = get_parametre('retrait_min', 1000.0)
    
    root.title("SERVICE CENTRAL D'EPARGNE POUR LA PROMOTION DE L'ENTREPRENEURIAT - S-MONEY")
    root.geometry("1000x700")
    root.resizable(True, True)
    root.configure(bg=BG_COLOR)
    
    # Configuration du style
    style = ttk.Style()
    style.theme_use('clam')
    
    # Configuration des styles spécifiques à cette fenêtre
    for widget_type, config in {
        'TFrame': {'background': BG_COLOR},
        'Header.TFrame': {'background': HEADER_COLOR},
        'Title.TLabel': {
            'background': HEADER_COLOR, 
            'foreground': 'white', 
            'font': ('Arial', 16, 'bold'),
            'padding': 10
        },
        'Subtitle.TLabel': {
            'background': BG_COLOR, 
            'foreground': TEXT_COLOR, 
            'font': ('Arial', 12),
            'padding': 5
        },
        'Info.TLabel': {
            'background': BG_COLOR, 
            'foreground': TEXT_COLOR, 
            'font': ('Arial', 10),
            'padding': 5
        },
        'Highlight.TLabel': {
            'background': BG_COLOR, 
            'foreground': ACCENT_COLOR, 
            'font': ('Arial', 12, 'bold'),
            'padding': 5
        },
        'TButton': {
            'background': BUTTON_COLOR, 
            'foreground': 'white',
            'font': ('Arial', 10, 'bold'),
            'borderwidth': 1,
            'padding': 5
        },
        'TEntry': {
            'fieldbackground': ENTRY_BG,
            'foreground': TEXT_COLOR,
            'font': ('Arial', 10),
            'padding': 5
        },
        'TRadiobutton': {
            'background': BG_COLOR,
            'foreground': TEXT_COLOR,
            'font': ('Arial', 10),
            'padding': 5
        },
        'TCombobox': {
            'fieldbackground': ENTRY_BG,
            'foreground': TEXT_COLOR,
            'font': ('Arial', 10)
        },
        'TLabelframe': {
            'background': BG_COLOR,
            'foreground': HEADER_COLOR,
            'font': ('Arial', 10, 'bold'),
            'padding': 10
        },
        'TLabelframe.Label': {
            'background': BG_COLOR,
            'foreground': HEADER_COLOR,
            'font': ('Arial', 10, 'bold')
        },
        'Warning.TLabel': {
            'background': BG_COLOR, 
            'foreground': WARNING_COLOR, 
            'font': ('Arial', 10, 'italic'),
            'padding': 5
        }
    }.items():
        style.configure(widget_type, **config)
    
    style.map('TButton', 
             background=[('active', BUTTON_HOVER_COLOR), ('pressed', BUTTON_HOVER_COLOR)])
    
    # Variables globales
    current_abonne = None
    current_id_client = None
    current_numero_carte = None
    current_solde = 0.0
    dernier_retrait_data = None
    montant_initial = 0.0
    type_compte = ""
    
    type_global_var = tk.StringVar(value="fixe")
    interet_var = tk.StringVar(value=f"{taux_interet}%")
    
    # Fonctions principales
    def rechercher():
        nonlocal current_abonne, current_id_client, current_solde, current_numero_carte, montant_initial, type_compte
        identifiant = entree_id.get().strip()
        
        if not identifiant:
            messagebox.showwarning("Attention", "Veuillez saisir un numéro client ou numéro de carte.")
            return
        
        loading_label.config(text="Recherche en cours...")
        root.update()
        
        try:
            with connexion_db() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("""
                    SELECT 
                        a.nom, a.postnom, a.prenom, 
                        a.numero_client, a.numero_carte, a.solde,
                        a.type_compte, cf.montant_initial
                    FROM abonne a
                    LEFT JOIN compte_fixe cf ON a.numero_carte = cf.numero_carte
                    WHERE a.numero_client=? OR a.numero_carte=?
                """, (identifiant, identifiant))
                res = cur.fetchone()
                
                if not res:
                    messagebox.showerror("Erreur", "Abonné introuvable.")
                    current_abonne = None
                    current_id_client = None
                    current_numero_carte = None
                    current_solde = 0.0
                    montant_initial = 0.0
                    label_nom_val.config(text="")
                    label_solde_val.config(text="")
                    label_type_compte.config(text="")
                    return

                nom_complet = f"{res['nom']} {res['postnom']} {res['prenom']}"
                num_client = res['numero_client']
                current_numero_carte = res['numero_carte']
                solde = res['solde'] or 0.0
                type_compte = res['type_compte'] or "Inconnu"
                montant_initial = res['montant_initial'] or 0.0

                current_abonne = nom_complet
                current_id_client = num_client
                current_solde = solde

                label_nom_val.config(text=nom_complet)
                label_solde_val.config(text=f"{solde:,.0f} FC".replace(",", " "))
                label_type_compte.config(text=type_compte)
                
                # Mise à jour de la couleur selon le type de compte
                if type_compte == "Fixe":
                    label_type_compte.config(foreground=ACCENT_COLOR)
                elif type_compte == "Mixte":
                    label_type_compte.config(foreground=SUCCESS_COLOR)
                else:
                    label_type_compte.config(foreground=TEXT_COLOR)
                
                label_solde_val.config(foreground=SUCCESS_COLOR)
                root.after(1000, lambda: label_solde_val.config(foreground=TEXT_COLOR))
                
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Erreur base de données: {str(e)}")
        finally:
            loading_label.config(text="")

    def basculer_interet(*args):
        type_global_label.grid_remove()
        type_global_menu.grid_remove()
        interet_label.grid_remove()
        interet_menu.grid_remove()
        
        if type_retrait_var.get() == "global":
            type_global_label.grid(row=5, column=0, sticky=tk.W, padx=5, pady=5)
            type_global_menu.grid(row=5, column=1, sticky=tk.W, padx=5, pady=5)
            
            if type_global_var.get() == "mixte":
                interet_label.grid(row=6, column=0, sticky=tk.W, padx=5, pady=5)
                interet_menu.grid(row=6, column=1, sticky=tk.W, padx=5, pady=5)

    def generer_ref():
        return f"R{random.randint(100000, 999999)}"

    def effectuer_retrait():
        nonlocal current_solde, current_id_client, dernier_retrait_data, montant_initial, type_compte
        if current_id_client is None:
            messagebox.showerror("Erreur", "Aucun abonné sélectionné.")
            return
        
        try:
            montant = float(entree_montant.get())
        except ValueError:
            messagebox.showerror("Erreur", "Montant invalide.")
            return
        
        if montant <= 0:
            messagebox.showerror("Erreur", "Le montant doit être supérieur à 0.")
            return
        
        type_retrait = type_retrait_var.get()
        type_global = type_global_var.get() if type_retrait == "global" else ""
        
        # Vérification des règles de type de compte
        if type_retrait == "global":
            if type_compte == "Fixe" and type_global != "fixe":
                messagebox.showerror("Erreur", 
                    "Ce compte fixe ne peut que faire un retrait global de type fixe.")
                return
                
            if type_compte == "Mixte" and type_global == "fixe":
                messagebox.showerror("Erreur", 
                    "Ce compte mixte ne peut pas faire un retrait global de type fixe.")
                return
                
            if type_global == "bloqué":
                messagebox.showerror("Erreur", 
                    "Ce type de retrait n'est pas encore défini. Veuillez contactez l'administrateur.")
                return
        
        if type_retrait == "partiel" or (type_retrait == "global" and type_global == "mixte"):
            if montant < montant_min_retrait:
                messagebox.showerror("Erreur", 
                    f"Le montant minimum de retrait est {montant_min_retrait:,.0f} FC")
                return
        
        type_retrait = type_retrait_var.get()
        montant_retrait = 0.0
        commission = 0.0
        montant_net = 0.0
        
        retrait_button.config(state=tk.DISABLED, text="Traitement en cours...")
        root.update()
        time.sleep(0.5)
        
        if type_retrait == "partiel":
            solde_apres = current_solde - montant
            if type_compte == "Fixe" and montant_initial > 0 and solde_apres < montant_initial:
                max_retrait = current_solde - montant_initial
                messagebox.showerror("Erreur", 
                    f"Le solde après retrait doit être au moins égal au montant initial ({montant_initial:,.0f} FC).\n"
                    f"Vous pouvez retirer au maximum {max_retrait:,.0f} FC.")
                retrait_button.config(state=tk.NORMAL, text="Effectuer retrait")
                return
            montant_retrait = montant
            montant_net = montant
        
        elif type_retrait == "global":
            type_global = type_global_var.get()
            
            if type_global == "fixe":
                commission = montant_initial
                montant_retrait = current_solde
                montant_net = montant_retrait - commission
                
                if montant_net < 0:
                    messagebox.showerror("Erreur", "Fonds insuffisants pour couvrir la commission.")
                    retrait_button.config(state=tk.NORMAL, text="Effectuer retrait")
                    return
                    
            elif type_global == "mixte":
                try:
                    taux_str = interet_var.get().replace("%", "")
                    taux = float(taux_str) / 100
                    interet = montant * taux
                    montant_retrait = montant + interet
                    montant_net = montant
                    commission = interet
                except Exception as e:
                    messagebox.showerror("Erreur", f"Erreur de taux ou montant : {e}")
                    retrait_button.config(state=tk.NORMAL, text="Effectuer retrait")
                    return
            else:
                montant_retrait = montant
                montant_net = montant

        if montant_retrait > current_solde:
            # Gestion spéciale pour compte mixte avec solde insuffisant
            if type_retrait == "global" and type_global == "mixte":
                taux_str = interet_var.get().replace("%", "")
                taux = float(taux_str) / 100
                montant_max = current_solde / (1 + taux)
                montant_max = math.floor(montant_max)
                montant_commission = montant_max * taux
                montant_total = montant_max + montant_commission
                
                messagebox.showerror("Erreur", 
                    f"L'abonné {current_abonne} a un solde insuffisant et ne peut retirer que {montant_max:,.0f} FC\n"
                    f"(soit un total de {montant_total:,.0f} FC avec commission).")
                retrait_button.config(state=tk.NORMAL, text="Effectuer retrait")
                return
            else:
                messagebox.showerror("Erreur", 
                    f"Fonds insuffisants.\nSolde actuel : {current_solde:,.0f} FC")
                retrait_button.config(state=tk.NORMAL, text="Effectuer retrait")
                return
            
        ref = generer_ref()
        maintenant = datetime.datetime.now()
        
        try:
            with connexion_db() as conn:
                cur = conn.cursor()
                
                cur.execute("""
                    INSERT INTO retraits (
                        numero_client, montant, ref_retrait, 
                        heure, date_retrait, agent
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    current_id_client,
                    montant_retrait,
                    ref,
                    maintenant.strftime("%H:%M:%S"),
                    maintenant.strftime("%Y-%m-%d"),
                    nom_agent
                ))
                
                cur.execute("""
                    UPDATE abonne 
                    SET solde = solde - ?
                    WHERE numero_client = ?
                """, (montant_retrait, current_id_client))
                
                conn.commit()
                
                ajouter_journal(
                    "Retrait", 
                    nom_agent, 
                    cible=current_id_client,
                    details=f"Montant: {montant_retrait:,.0f} FC, Ref: {ref}"
                )
                
                dernier_retrait_data = {
                    "numero_client": current_id_client,
                    "numero_carte": current_numero_carte,
                    "nom_complet": current_abonne,
                    "montant_retire": montant_retrait,
                    "commission": commission,
                    "montant_net": montant_net,
                    "ancien_solde": current_solde,
                    "nouveau_solde": current_solde - montant_retrait,
                    "date_heure": maintenant.strftime("%d/%m/%Y %H:%M"),
                    "ref": ref,
                    "agent": nom_agent,
                    "montant_initial": montant_initial
                }
                
                cur.execute("SELECT solde FROM abonne WHERE numero_client=?", (current_id_client,))
                current_solde = cur.fetchone()[0] or 0.0
                label_solde_val.config(text=f"{current_solde:,.0f} FC".replace(",", " "))
                entree_montant.delete(0, tk.END)
                
                messagebox.showinfo("✅ Succès", 
                    f"Retrait effectué avec succès pour {current_abonne}\n"
                    f"• Montant net : {montant_net:,.0f} FC\n"
                    f"• Commission : {commission:,.0f} FC\n"
                    f"• Nouveau solde : {current_solde:,.0f} FC")
                
                label_solde_val.config(foreground=SUCCESS_COLOR)
                root.after(2000, lambda: label_solde_val.config(foreground=TEXT_COLOR))
                
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Erreur base de données: {str(e)}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur inattendue: {str(e)}")
        finally:
            retrait_button.config(state=tk.NORMAL, text="Effectuer retrait")

    def afficher_historique():
        if not current_id_client:
            messagebox.showwarning("Attention", "Aucun abonné sélectionné.")
            return
        
        fen = tk.Toplevel(root)
        fen.title(f"Historique des retraits - {current_abonne}")
        fen.geometry("800x500")
        fen.configure(bg=BG_COLOR)
        fen.transient(root)
        fen.grab_set()
        
        main_frame = ttk.Frame(fen, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(
            header_frame, 
            text=f"HISTORIQUE DES RETRAITS: {current_abonne}", 
            font=("Arial", 12, "bold"),
            foreground=HEADER_COLOR
        ).pack(side=tk.LEFT)
        
        tree_frame = ttk.Frame(main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(tree_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        tree = ttk.Treeview(
            tree_frame, 
            columns=("Date", "Heure", "Montant", "Référence", "Agent"), 
            show="headings",
            yscrollcommand=scrollbar.set
        )
        scrollbar.config(command=tree.yview)
        
        tree.heading("Date", text="Date")
        tree.heading("Heure", text="Heure")
        tree.heading("Montant", text="Montant (FC)")
        tree.heading("Référence", text="Référence")
        tree.heading("Agent", text="Agent")
        
        tree.column("Date", width=100, anchor=tk.CENTER)
        tree.column("Heure", width=80, anchor=tk.CENTER)
        tree.column("Montant", width=120, anchor=tk.E)
        tree.column("Référence", width=150, anchor=tk.CENTER)
        tree.column("Agent", width=120, anchor=tk.CENTER)
        
        tree.pack(fill=tk.BOTH, expand=True)
        
        try:
            with connexion_db() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("""
                    SELECT date_retrait, heure, montant, ref_retrait, agent
                    FROM retraits
                    WHERE numero_client=?
                    ORDER BY date_retrait DESC, heure DESC
                """, (current_id_client,))
                resultats = cur.fetchall()
                
                total = 0
                for ligne in resultats:
                    montant = ligne['montant']
                    tree.insert("", tk.END, values=(
                        ligne['date_retrait'],
                        ligne['heure'],
                        f"{montant:,.0f}".replace(",", " "),
                        ligne['ref_retrait'],
                        ligne['agent']
                    ))
                    total += montant
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Erreur base de données: {str(e)}")
            return
        
        total_frame = ttk.Frame(main_frame)
        total_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Label(
            total_frame, 
            text=f"Total des retraits: {total:,.0f} FC".replace(",", " "), 
            font=("Arial", 11, "bold"),
            foreground=ACCENT_COLOR
        ).pack(side=tk.RIGHT)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(10, 0))
        
        ttk.Button(
            button_frame, 
            text="Fermer", 
            command=fen.destroy
        ).pack(side=tk.RIGHT, padx=5)

    def imprimer_bordereau_wrapper():
        if dernier_retrait_data:
            try:
                data = {
                    "nom_complet": dernier_retrait_data["nom_complet"],
                    "montant_retire": dernier_retrait_data["montant_retire"],
                    "agent": dernier_retrait_data["agent"],
                    "ancien_solde": dernier_retrait_data["ancien_solde"],
                    "nouveau_solde": dernier_retrait_data["nouveau_solde"],
                    "ref": dernier_retrait_data["ref"],
                    "numero_client": dernier_retrait_data["numero_client"],
                    "numero_carte": dernier_retrait_data["numero_carte"]
                }
                
                threading.Thread(
                    target=export_retrait.imprimer_bordereau,
                    args=(data, dernier_retrait_data["commission"])
                ).start()
                
                messagebox.showinfo("Impression", "Bordereau envoyé à l'imprimante")
            except Exception as e:
                messagebox.showerror("Erreur", f"Échec de l'impression : {str(e)}")
        else:
            messagebox.showwarning("Avertissement", "Aucun retrait effectué")

    def exporter_pdf_wrapper():
        if dernier_retrait_data:
            try:
                data = {
                    "nom_complet": dernier_retrait_data["nom_complet"],
                    "montant_retire": dernier_retrait_data["montant_retire"],
                    "agent": dernier_retrait_data["agent"],
                    "ancien_solde": dernier_retrait_data["ancien_solde"],
                    "nouveau_solde": dernier_retrait_data["nouveau_solde"],
                    "ref": dernier_retrait_data["ref"],
                    "numero_client": dernier_retrait_data["numero_client"],
                    "numero_carte": dernier_retrait_data["numero_carte"]
                }
                
                data["commission"] = dernier_retrait_data["commission"]
                
                pdf_path = export_retrait.exporter_pdf(data)
                messagebox.showinfo("PDF", f"Bordereau sauvegardé dans :\n{pdf_path}")
                webbrowser.open_new(pdf_path)
            except Exception as e:
                messagebox.showerror("Erreur", f"Échec de l'export PDF : {str(e)}")
        else:
            messagebox.showwarning("Avertissement", "Aucun retrait effectué")

    def exporter_word_wrapper():
        if dernier_retrait_data:
            try:
                data = {
                    "nom_complet": dernier_retrait_data["nom_complet"],
                    "montant_retire": dernier_retrait_data["montant_retire"],
                    "agent": dernier_retrait_data["agent"],
                    "ancien_solde": dernier_retrait_data["ancien_solde"],
                    "nouveau_solde": dernier_retrait_data["nouveau_solde"],
                    "ref": dernier_retrait_data["ref"],
                    "numero_client": dernier_retrait_data["numero_client"],
                    "numero_carte": dernier_retrait_data["numero_carte"]
                }
                
                data["commission"] = dernier_retrait_data["commission"]
                
                word_path = export_retrait.exporter_word(data)
                messagebox.showinfo("Word", f"Bordereau sauvegardé dans :\n{word_path}")
                webbrowser.open_new(word_path)
            except Exception as e:
                messagebox.showerror("Erreur", f"Échec de l'export Word : {str(e)}")
        else:
            messagebox.showwarning("Avertissement", "Aucun retrait effectué")
            
    def generer_rapport():
        fen_rapport = tk.Toplevel(root)
        fen_rapport.title("Rapports de Retraits")
        fen_rapport.geometry("600x400")
        fen_rapport.resizable(False, False)
        fen_rapport.configure(bg=BG_COLOR)
        fen_rapport.transient(root)
        fen_rapport.grab_set()
        
        # Création du notebook avec des onglets
        notebook = ttk.Notebook(fen_rapport)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Création des onglets
        onglet_journalier = ttk.Frame(notebook)
        onglet_hebdomadaire = ttk.Frame(notebook)
        onglet_mensuel = ttk.Frame(notebook)
        onglet_annuel = ttk.Frame(notebook)
        
        notebook.add(onglet_journalier, text="Journalier")
        notebook.add(onglet_hebdomadaire, text="Hebdomadaire")
        notebook.add(onglet_mensuel, text="Mensuel")
        notebook.add(onglet_annuel, text="Annuel")
        
        # Configuration des onglets
        configurer_onglet_journalier(onglet_journalier)
        configurer_onglet_hebdomadaire(onglet_hebdomadaire)
        configurer_onglet_mensuel(onglet_mensuel)
        configurer_onglet_annuel(onglet_annuel)
        
        # Bouton Fermer
        btn_frame = ttk.Frame(fen_rapport)
        btn_frame.pack(fill=tk.X, pady=10)
        ttk.Button(btn_frame, text="Fermer", command=fen_rapport.destroy).pack(side=tk.RIGHT, padx=10)

    def configurer_onglet_journalier(onglet):
        ttk.Label(onglet, text="Date (AAAA-MM-JJ):", font=('Arial', 10)).pack(pady=5)
        date_journalier = tk.StringVar(value=datetime.datetime.now().strftime("%Y-%m-%d"))
        ttk.Entry(onglet, textvariable=date_journalier, width=15).pack(pady=5)
        
        btn_frame = ttk.Frame(onglet)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="📊 Générer Rapport PDF", 
                  command=lambda: generer_rapport_pdf("journalier", date_journalier.get())).pack(pady=5, fill=tk.X)
        ttk.Button(btn_frame, text="📈 Exporter Données Brutes", 
                  command=lambda: exporter_donnees_brutes("journalier", date_journalier.get())).pack(pady=5, fill=tk.X)
        ttk.Button(btn_frame, text="📉 Exporter Graphique", 
                  command=lambda: exporter_graphique("journalier", date_journalier.get())).pack(pady=5, fill=tk.X)

    def configurer_onglet_hebdomadaire(onglet):
        ttk.Label(onglet, text="Date de début de semaine (AAAA-MM-JJ):", font=('Arial', 10)).pack(pady=5)
        today = datetime.datetime.now()
        monday = today - datetime.timedelta(days=today.weekday())
        date_hebdomadaire = tk.StringVar(value=monday.strftime("%Y-%m-%d"))
        ttk.Entry(onglet, textvariable=date_hebdomadaire, width=15).pack(pady=5)
        
        btn_frame = ttk.Frame(onglet)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="📊 Générer Rapport PDF", 
                  command=lambda: generer_rapport_pdf("hebdomadaire", date_hebdomadaire.get())).pack(pady=5, fill=tk.X)
        ttk.Button(btn_frame, text="📈 Exporter Données Brutes", 
                  command=lambda: exporter_donnees_brutes("hebdomadaire", date_hebdomadaire.get())).pack(pady=5, fill=tk.X)
        ttk.Button(btn_frame, text="📉 Exporter Graphique", 
                  command=lambda: exporter_graphique("hebdomadaire", date_hebdomadaire.get())).pack(pady=5, fill=tk.X)

    def configurer_onglet_mensuel(onglet):
        ttk.Label(onglet, text="Mois (AAAA-MM):", font=('Arial', 10)).pack(pady=5)
        date_mensuel = tk.StringVar(value=datetime.datetime.now().strftime("%Y-%m"))
        ttk.Entry(onglet, textvariable=date_mensuel, width=15).pack(pady=5)
        
        btn_frame = ttk.Frame(onglet)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="📊 Générer Rapport PDF", 
                  command=lambda: generer_rapport_pdf("mensuel", date_mensuel.get() + "-01")).pack(pady=5, fill=tk.X)
        ttk.Button(btn_frame, text="📈 Exporter Données Brutes", 
                  command=lambda: exporter_donnees_brutes("mensuel", date_mensuel.get() + "-01")).pack(pady=5, fill=tk.X)
        ttk.Button(btn_frame, text="📉 Exporter Graphique", 
                  command=lambda: exporter_graphique("mensuel", date_mensuel.get() + "-01")).pack(pady=5, fill=tk.X)

    def configurer_onglet_annuel(onglet):
        ttk.Label(onglet, text="Année (AAAA):", font=('Arial', 10)).pack(pady=5)
        date_annuel = tk.StringVar(value=datetime.datetime.now().strftime("%Y"))
        ttk.Entry(onglet, textvariable=date_annuel, width=15).pack(pady=5)
        
        btn_frame = ttk.Frame(onglet)
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="📊 Générer Rapport PDF", 
                  command=lambda: generer_rapport_pdf("annuel", date_annuel.get() + "-01-01")).pack(pady=5, fill=tk.X)
        ttk.Button(btn_frame, text="📈 Exporter Données Brutes", 
                  command=lambda: exporter_donnees_brutes("annuel", date_annuel.get() + "-01-01")).pack(pady=5, fill=tk.X)
        ttk.Button(btn_frame, text="📉 Exporter Graphique", 
                  command=lambda: exporter_graphique("annuel", date_annuel.get() + "-01-01")).pack(pady=5, fill=tk.X)

    def generer_rapport_pdf(report_type, ref_date):
        try:
            ref_date = datetime.datetime.strptime(ref_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Erreur", "Format de date invalide. Utilisez AAAA-MM-JJ.")
            return
        
        # Determine date range based on report type
        if report_type == "journalier":
            start_date = ref_date
            end_date = ref_date
            title = f"Rapport Journalier - {ref_date.strftime('%d/%m/%Y')}"
        elif report_type == "hebdomadaire":
            start_date = ref_date - datetime.timedelta(days=ref_date.weekday())
            end_date = start_date + datetime.timedelta(days=6)
            title = f"Rapport Hebdomadaire - Semaine {ref_date.isocalendar()[1]} ({start_date.strftime('%d/%m')} au {end_date.strftime('%d/%m/%Y')})"
        elif report_type == "mensuel":
            start_date = datetime.datetime(ref_date.year, ref_date.month, 1)
            next_month = start_date.replace(day=28) + datetime.timedelta(days=4)
            end_date = next_month - datetime.timedelta(days=next_month.day)
            title = f"Rapport Mensuel - {ref_date.strftime('%B %Y')}"
        elif report_type == "annuel":
            start_date = datetime.datetime(ref_date.year, 1, 1)
            end_date = datetime.datetime(ref_date.year, 12, 31)
            title = f"Rapport Annuel - {ref_date.year}"
        
        # Fetch data from database
        try:
            with connexion_db() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("""
                    SELECT r.date_retrait, r.heure, a.nom, a.postnom, a.prenom, 
                           r.montant, r.ref_retrait, r.agent
                    FROM retraits r
                    JOIN abonne a ON r.numero_client = a.numero_client
                    WHERE r.date_retrait BETWEEN ? AND ?
                    ORDER BY r.date_retrait, r.heure
                """, (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
                retraits = cur.fetchall()
                
                if not retraits:
                    messagebox.showinfo("Information", "Aucun retrait trouvé pour cette période.")
                    return
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Erreur base de données: {str(e)}")
            return
        
        # Create PDF report
        try:
            # Generate filename with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            rapports_dir = get_rapports_dir()
            filename = os.path.join(rapports_dir, f"rapport_retraits_{report_type}_{timestamp}.pdf")
            
            with PdfPages(filename) as pdf:
                # Create a figure
                plt.figure(figsize=(11, 8.5))  # Letter size
                
                # Add title
                plt.figtext(0.5, 0.95, title, 
                           ha='center', va='top', 
                           fontsize=16, fontweight='bold')
                
                # Add subtitle
                plt.figtext(0.5, 0.90, "Service Central d'Épargne pour la Promotion de l'Entreprenariat - S-MONEY", 
                           ha='center', va='top', 
                           fontsize=12)
                
                # Add generation info
                plt.figtext(0.1, 0.85, f"Généré le: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}", 
                           fontsize=10)
                plt.figtext(0.1, 0.82, f"Agent: {nom_agent}", 
                           fontsize=10)
                
                # Create table data
                table_data = [
                    ["Date", "Heure", "Client", "Montant (FC)", "Référence", "Agent"]
                ]
                
                total = 0
                for retrait in retraits:
                    nom_complet = f"{retrait['nom']} {retrait['postnom']} {retrait['prenom']}"
                    montant = retrait['montant']
                    total += montant
                    
                    table_data.append([
                        retrait['date_retrait'],
                        retrait['heure'],
                        nom_complet,
                        f"{montant:,.0f}",
                        retrait['ref_retrait'],
                        retrait['agent']
                    ])
                
                # Add summary
                plt.figtext(0.1, 0.78, f"Période: {start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}", 
                           fontsize=10)
                plt.figtext(0.1, 0.75, f"Nombre de retraits: {len(retraits)}", 
                           fontsize=10)
                plt.figtext(0.1, 0.72, f"Total des retraits: {total:,.0f} FC", 
                           fontsize=10, fontweight='bold')
                
                # Create table
                table = plt.table(
                    cellText=table_data,
                    cellLoc='center',
                    loc='center',
                    bbox=[0.1, 0.05, 0.8, 0.65]
                )
                
                # Style table
                table.auto_set_font_size(False)
                table.set_fontsize(8)
                table.scale(1, 1.5)
                
                # Style header row
                for i in range(len(table_data[0])):
                    table[0, i].set_facecolor('#3498db')
                    table[0, i].set_text_props(color='white', weight='bold')
                
                # Alternate row colors
                for i in range(1, len(table_data)):
                    color = '#f2f2f2' if i % 2 == 1 else '#ffffff'
                    for j in range(len(table_data[0])):
                        table[i, j].set_facecolor(color)
                
                plt.axis('off')
                pdf.savefig()
                plt.close()
                
            messagebox.showinfo("Succès", 
                              f"Rapport généré avec succès!\n\nFichier: {filename}\n\nTotal des retraits: {total:,.0f} FC")
            
            # Open the PDF file
            webbrowser.open_new(filename)
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la génération du PDF: {str(e)}")
    
    def exporter_donnees_brutes(report_type, ref_date):
        """Exporte les données brutes au format CSV"""
        try:
            ref_date = datetime.datetime.strptime(ref_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Erreur", "Format de date invalide. Utilisez AAAA-MM-JJ.")
            return
        
        # Determine date range based on report type
        if report_type == "journalier":
            start_date = ref_date
            end_date = ref_date
            title = f"Rapport Journalier - {ref_date.strftime('%d/%m/%Y')}"
        elif report_type == "hebdomadaire":
            start_date = ref_date - datetime.timedelta(days=ref_date.weekday())
            end_date = start_date + datetime.timedelta(days=6)
            title = f"Rapport Hebdomadaire - Semaine {ref_date.isocalendar()[1]}"
        elif report_type == "mensuel":
            start_date = datetime.datetime(ref_date.year, ref_date.month, 1)
            next_month = start_date.replace(day=28) + datetime.timedelta(days=4)
            end_date = next_month - datetime.timedelta(days=next_month.day)
            title = f"Rapport Mensuel - {ref_date.strftime('%B %Y')}"
        elif report_type == "annuel":
            start_date = datetime.datetime(ref_date.year, 1, 1)
            end_date = datetime.datetime(ref_date.year, 12, 31)
            title = f"Rapport Annuel - {ref_date.year}"
        
        # Fetch data from database
        try:
            with connexion_db() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("""
                    SELECT r.date_retrait, r.heure, a.nom, a.postnom, a.prenom, 
                           r.montant, r.ref_retrait, r.agent
                    FROM retraits r
                    JOIN abonne a ON r.numero_client = a.numero_client
                    WHERE r.date_retrait BETWEEN ? AND ?
                    ORDER BY r.date_retrait, r.heure
                """, (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
                retraits = cur.fetchall()
                
                if not retraits:
                    messagebox.showinfo("Information", "Aucun retrait trouvé pour cette période.")
                    return
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Erreur base de données: {str(e)}")
            return
        
        # Generate CSV file
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            rapports_dir = get_rapports_dir()
            filename = os.path.join(rapports_dir, f"donnees_brutes_{report_type}_{timestamp}.csv")
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("Date;Heure;Nom;Postnom;Prenom;Montant;Reference;Agent\n")
                for retrait in retraits:
                    line = (
                        f"{retrait['date_retrait']};{retrait['heure']};"
                        f"{retrait['nom']};{retrait['postnom']};{retrait['prenom']};"
                        f"{retrait['montant']};{retrait['ref_retrait']};{retrait['agent']}\n"
                    )
                    f.write(line)
            
            messagebox.showinfo("Succès", 
                              f"Données brutes exportées avec succès!\n\nFichier: {filename}")
            
            # Open the CSV file
            webbrowser.open_new(filename)
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'export des données: {str(e)}")
    
    def exporter_graphique(report_type, ref_date):
        """Exporte un graphique des retraits au format PNG"""
        try:
            ref_date = datetime.datetime.strptime(ref_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Erreur", "Format de date invalide. Utilisez AAAA-MM-JJ.")
            return
        
        # Determine date range based on report type
        if report_type == "journalier":
            start_date = ref_date
            end_date = ref_date
            title = f"Rapport Journalier - {ref_date.strftime('%d/%m/%Y')}"
            group_by = "heure"
        elif report_type == "hebdomadaire":
            start_date = ref_date - datetime.timedelta(days=ref_date.weekday())
            end_date = start_date + datetime.timedelta(days=6)
            title = f"Rapport Hebdomadaire - Semaine {ref_date.isocalendar()[1]}"
            group_by = "date_retrait"
        elif report_type == "mensuel":
            start_date = datetime.datetime(ref_date.year, ref_date.month, 1)
            next_month = start_date.replace(day=28) + datetime.timedelta(days=4)
            end_date = next_month - datetime.timedelta(days=next_month.day)
            title = f"Rapport Mensuel - {ref_date.strftime('%B %Y')}"
            group_by = "date_retrait"
        elif report_type == "annuel":
            start_date = datetime.datetime(ref_date.year, 1, 1)
            end_date = datetime.datetime(ref_date.year, 12, 31)
            title = f"Rapport Annuel - {ref_date.year}"
            group_by = "strftime('%m', date_retrait)"
        
        # Fetch aggregated data from database
        try:
            with connexion_db() as conn:
                cur = conn.cursor()
                cur.execute(f"""
                    SELECT {group_by} AS periode, SUM(montant) AS total
                    FROM retraits
                    WHERE date_retrait BETWEEN ? AND ?
                    GROUP BY periode
                    ORDER BY periode
                """, (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))
                data = cur.fetchall()
                
                if not data:
                    messagebox.showinfo("Information", "Aucun retrait trouvé pour cette période.")
                    return
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Erreur base de données: {str(e)}")
            return
        
        # Generate chart
        try:
            periods = [row[0] for row in data]
            totals = [row[1] for row in data]
            
            plt.figure(figsize=(10, 6))
            plt.bar(periods, totals, color=ACCENT_COLOR)
            plt.title(f"Retraits par période\n{title}", fontsize=14)
            plt.xlabel("Période", fontsize=12)
            plt.ylabel("Montant total (FC)", fontsize=12)
            plt.xticks(rotation=45, ha='right')
            plt.tight_layout()
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            rapports_dir = get_rapports_dir()
            filename = os.path.join(rapports_dir, f"graphique_retraits_{report_type}_{timestamp}.png")
            plt.savefig(filename, dpi=300)
            plt.close()
            
            messagebox.showinfo("Succès", 
                              f"Graphique généré avec succès!\n\nFichier: {filename}")
            
            # Open the image file
            webbrowser.open_new(filename)
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la génération du graphique: {str(e)}")

    def quitter():
        root.destroy()

    # Interface principale
    main_frame = ttk.Frame(root)
    main_frame.pack(fill=tk.BOTH, expand=True)
    
    header_frame = ttk.Frame(main_frame, style='Header.TFrame')
    header_frame.pack(fill=tk.X)
    
    # Ajout d'un avatar pour l'agent
    avatar_img = create_default_avatar(nom_agent)
    avatar_label = ttk.Label(header_frame, image=avatar_img)
    avatar_label.image = avatar_img
    avatar_label.pack(side=tk.LEFT, padx=10)
    
    ttk.Label(
        header_frame, 
        text="S-MONEY", 
        style='Title.TLabel',
        font=('Arial', 20, 'bold')
    ).pack(side=tk.LEFT, padx=20)
    
    agent_frame = ttk.Frame(header_frame)
    agent_frame.pack(side=tk.RIGHT, padx=20)
    
    ttk.Label(
        agent_frame, 
        text=f"Agent: {nom_agent}", 
        style='Title.TLabel',
        font=('Arial', 12)
    ).pack(anchor=tk.E)
    
    ttk.Label(
        agent_frame, 
        text=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        font=('Arial', 10),
        foreground='white'
    ).pack(anchor=tk.E)
    
    content_frame = ttk.Frame(main_frame, padding=20)
    content_frame.pack(fill=tk.BOTH, expand=True)
    
    left_frame = ttk.LabelFrame(content_frame, text="Recherche Abonné", padding=10)
    left_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
    
    ttk.Label(left_frame, text="Numéro Client/Carte:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
    entree_id = ttk.Entry(left_frame, width=25)
    entree_id.grid(row=0, column=1, padx=5, pady=5, sticky=tk.W)
    entree_id.bind("<Return>", lambda e: rechercher())
    ttk.Button(left_frame, text="Rechercher", command=rechercher).grid(row=0, column=2, padx=5, pady=5)
    
    loading_label = ttk.Label(left_frame, text="", foreground=ACCENT_COLOR)
    loading_label.grid(row=1, column=0, columnspan=3, pady=5)
    
    info_frame = ttk.LabelFrame(left_frame, text="Informations Abonné", padding=10)
    info_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=10)
    
    ttk.Label(info_frame, text="Nom complet:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
    label_nom_val = ttk.Label(info_frame, text="", font=('Arial', 10, 'bold'))
    label_nom_val.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
    
    ttk.Label(info_frame, text="Solde actuel:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
    label_solde_val = ttk.Label(info_frame, text="", font=('Arial', 10, 'bold'))
    label_solde_val.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
    
    ttk.Label(info_frame, text="Type de compte:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
    label_type_compte = ttk.Label(info_frame, text="", font=('Arial', 10, 'bold'))
    label_type_compte.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
    
    right_frame = ttk.LabelFrame(content_frame, text="Opération de Retrait", padding=10)
    right_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
    
    ttk.Label(right_frame, text="Type de retrait:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
    type_retrait_var = tk.StringVar(value="partiel")
    ttk.Radiobutton(right_frame, text="Partiel", variable=type_retrait_var, value="partiel", command=basculer_interet).grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
    ttk.Radiobutton(right_frame, text="Global", variable=type_retrait_var, value="global", command=basculer_interet).grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
    
    ttk.Label(right_frame, text="Montant à retirer (FC):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
    entree_montant = ttk.Entry(right_frame, width=15)
    entree_montant.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
    entree_montant.bind("<Return>", lambda e: effectuer_retrait())
    
    type_global_label = ttk.Label(right_frame, text="Type de compte:")
    type_global_menu = ttk.Combobox(right_frame, textvariable=type_global_var, values=["fixe", "mixte", "bloqué"], width=10, state="readonly")
    
    interet_label = ttk.Label(right_frame, text="Taux d'intérêt (%):")
    interet_menu = ttk.Combobox(right_frame, textvariable=interet_var, values=[f"{taux_interet}%", f"{taux_interet+1}%", f"{taux_interet+2}%", f"{taux_interet-1}%"], width=8, state="readonly")
    
    retrait_button = ttk.Button(right_frame, text="Effectuer retrait", command=effectuer_retrait)
    retrait_button.grid(row=7, column=0, columnspan=3, pady=15)
    
    rules_frame = ttk.LabelFrame(right_frame, text="Règles d'opération", padding=10)
    rules_frame.grid(row=8, column=0, columnspan=3, sticky="ew", pady=10)
    
    rules_text = (
        f"• Compte fixe: Retrait partiel possible uniquement au-dessus du montant initial\n"
        f"• Retrait global: Commission = montant initial\n"
        f"• Compte mixte: Prélevement d'intérêts sur le montant retiré\n"
        f"• Montant minimum de retrait: {montant_min_retrait:,.0f} FC"
    )
    ttk.Label(rules_frame, text=rules_text, wraplength=350, justify=tk.LEFT).pack()
    
    actions_frame = ttk.Frame(content_frame)
    actions_frame.grid(row=1, column=0, columnspan=2, pady=20, sticky="ew")
    
    # Création d'un bouton avec une icône pour chaque action
    ttk.Button(actions_frame, text="🖨 Imprimer Bordereau", command=imprimer_bordereau_wrapper).pack(side=tk.LEFT, padx=5)
    ttk.Button(actions_frame, text="📜 Historique", command=afficher_historique).pack(side=tk.LEFT, padx=5)
    ttk.Button(actions_frame, text="📊 Rapport", command=generer_rapport).pack(side=tk.LEFT, padx=5)
    ttk.Button(actions_frame, text="💾 Exporter PDF", command=exporter_pdf_wrapper).pack(side=tk.LEFT, padx=5)
    ttk.Button(actions_frame, text="📄 Exporter Word", command=exporter_word_wrapper).pack(side=tk.LEFT, padx=5)
    ttk.Button(actions_frame, text="🚪 Fermer", command=quitter).pack(side=tk.RIGHT, padx=5)
    
    footer_frame = ttk.Frame(main_frame, style='Header.TFrame')
    footer_frame.pack(fill=tk.X, side=tk.BOTTOM)
    
    ttk.Label(
        footer_frame, 
        text="Service Central d'Épargne pour la Promotion de l'Entreprenariat - © 2025",
        foreground="white",
        background=HEADER_COLOR,
        padding=5
    ).pack()
    
    content_frame.columnconfigure(0, weight=1)
    content_frame.columnconfigure(1, weight=1)
    content_frame.rowconfigure(0, weight=1)
    
    basculer_interet()
    entree_id.focus_set()
    
    if parent_window is None:
        root.mainloop()
    else:
        root.grab_set()

if __name__ == "__main__":
    interface_retrait("John Doe")