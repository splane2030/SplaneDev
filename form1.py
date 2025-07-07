import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from PIL import Image, ImageTk, ImageDraw, ImageFont
from datetime import datetime
import random
import os
import sys
import sqlite3
import shutil
from fenetre_depot import FenetreDepot
from interface_retrait import interface_retrait
from inscription_menu import InscriptionInterface
import db
from typing import Dict, Optional, Tuple
import webbrowser
import stat
import tempfile
import logging

# ==================== CONFIGURATION DES PERMISSIONS ====================
def setup_permissions():
    """Configure les permissions système nécessaires"""
    try:
        # Créer le dossier d'application avec permissions étendues
        appdata_dir = os.getenv("APPDATA")
        app_folder = os.path.join(appdata_dir, "MonLogiciel")
        
        # Créer le dossier avec permissions 0o777 (rwx pour tous)
        os.makedirs(app_folder, exist_ok=True, mode=0o777)
        os.chmod(app_folder, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO)
        
        # Vérifier les permissions
        if not os.access(app_folder, os.R_OK | os.W_OK | os.X_OK):
            raise PermissionError(f"Permissions insuffisantes sur {app_folder}")
        
        # Configurer les permissions pour les fichiers de log
        log_path = os.path.join(app_folder, 'app.log')
        if os.path.exists(log_path):
            os.chmod(log_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH)
        
        return True
    except Exception as e:
        logging.critical(f"Erreur configuration permissions: {str(e)}")
        return False

# ==================== JOURNALISATION AU DÉMARRAGE ====================
# Configurer les permissions avant toute opération
if not setup_permissions():
    messagebox.showerror("Erreur Critique", 
                        "L'application n'a pas les permissions nécessaires pour fonctionner.\n"
                        "Veuillez exécuter en tant qu'administrateur ou vérifier les permissions des dossiers.")
    sys.exit(1)

# Maintenant, configurer le logging dans le dossier APPDATA
log_dir = os.path.join(os.environ['APPDATA'], 'MonLogiciel')
log_path = os.path.join(log_dir, 'app.log')

try:
    # S'assurer que le dossier existe
    os.makedirs(log_dir, exist_ok=True, mode=0o777)
    
    # Configurer les permissions du fichier log
    if os.path.exists(log_path) and not os.access(log_path, os.W_OK):
        os.chmod(log_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH)
    
    # Configurer le logging
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    logger.info("Application lancée")
except Exception as e:
    # Fallback: logging dans un fichier temporaire
    temp_log = os.path.join(tempfile.gettempdir(), 'money_app.log')
    logging.basicConfig(
        filename=temp_log,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)
    logger.error("Impossible d'écrire dans le fichier log principal: %s. Utilisation du fichier temporaire: %s", str(e), temp_log)

# ==================== CONSTANTES ====================
PRIMARY_COLOR = "#128C7E"
SECONDARY_COLOR = "#075E54"
ACCENT_COLOR = "#25D366"
BACKGROUND_COLOR = "#F0F2F5"
TEXT_COLOR = "#333333"
ERROR_COLOR = "#E74C3C"
SUCCESS_COLOR = "#2ECC71"
WARNING_COLOR = "#F39C12"

FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_SUBTITLE = ("Segoe UI", 12)
FONT_NORMAL = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 8)

# ==================== FONCTIONS UTILITAIRES ====================
def create_default_avatar(name: str = "", size: Tuple[int, int] = (60, 60)) -> ImageTk.PhotoImage:
    """Crée un avatar par défaut avec les initiales"""
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

# ==================== CLASSES PRINCIPALES ====================
class LoginWindow(tk.Toplevel):
    """Fenêtre de connexion moderne avec création de compte et réinitialisation de mot de passe"""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Connexion - SERVICE CENTRAL D'EPARGNE")
        self.geometry("450x650")
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        
        # Configuration du style
        self.setup_styles()
        
        # Centrer la fenêtre
        self.center_window()
        
        # Initialisation des composants
        self.setup_logo()
        self.setup_form()
        self.setup_footer()
        
        # Focus initial
        self.login_entry.focus()
        
        # Variables pour la photo
        self.photo_img = None
        self.photo_path = None

    def setup_styles(self):
        """Configure les styles visuels"""
        self.style = ttk.Style()
        self.style.configure('TLabel', background=BACKGROUND_COLOR, font=FONT_NORMAL)
        self.style.configure('TEntry', font=FONT_NORMAL, padding=5)
        self.style.configure('Login.TButton', font=FONT_NORMAL, padding=8, 
                           background=PRIMARY_COLOR, foreground='white')
        self.style.configure('Secondary.TButton', font=FONT_NORMAL, padding=8,
                           background=SECONDARY_COLOR, foreground='white')
        self.style.configure('Link.TLabel', foreground=PRIMARY_COLOR, font=FONT_SMALL, 
                           background=BACKGROUND_COLOR)

    def center_window(self):
        """Centre la fenêtre sur l'écran"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')

    def setup_logo(self):
        """Configure le logo et le titre"""
        logo_frame = ttk.Frame(self)
        logo_frame.pack(pady=20)
        
        # Logo (avec fallback si absent)
        try:
            logo_img = Image.open("logo.png").resize((120, 120))
            self.logo = ImageTk.PhotoImage(logo_img)
            ttk.Label(logo_frame, image=self.logo).pack()
        except:
            self.logo = create_default_avatar("", (120, 120))
            ttk.Label(logo_frame, image=self.logo).pack()
        
        # Titre
        ttk.Label(logo_frame, 
                 text="$-MONEY", 
                 font=FONT_TITLE, 
                 foreground=PRIMARY_COLOR).pack(pady=5)

    def setup_form(self):
        """Configure le formulaire de connexion"""
        form_frame = ttk.Frame(self, style='Card.TFrame')
        form_frame.pack(pady=10, padx=25, fill="x")
        
        # Titre
        ttk.Label(form_frame, 
                 text="Connexion", 
                 style='Title.TLabel').pack(pady=10)
        
        # Champ identifiant
        ttk.Label(form_frame, text="Identifiant:").pack(anchor="w", padx=10)
        self.login_entry = ttk.Entry(form_frame)
        self.login_entry.pack(fill="x", padx=10, pady=(0, 15))
        
        # Champ mot de passe
        ttk.Label(form_frame, text="Mot de passe:").pack(anchor="w", padx=10)
        self.password_entry = ttk.Entry(form_frame, show="•")
        self.password_entry.pack(fill="x", padx=10, pady=(0, 20))
        
        # Bouton de connexion
        ttk.Button(form_frame, 
                  text="Se connecter", 
                  style='Login.TButton',
                  command=self.authenticate).pack(fill="x", padx=10, pady=(0, 10))
        
        # Lien mot de passe oublié
        forgot_link = ttk.Label(form_frame, 
                              text="Mot de passe oublié ?", 
                              style='Link.TLabel',
                              cursor="hand2")
        forgot_link.pack(pady=(0, 15))
        forgot_link.bind("<Button-1>", lambda e: self.open_password_reset())
        
        # Séparateur
        ttk.Separator(form_frame, orient="horizontal").pack(fill="x", padx=10, pady=5)
        
        # Bouton création de compte
        ttk.Button(form_frame,
                  text="Créer un nouveau compte",
                  style='Secondary.TButton',
                  command=self.open_inscription).pack(fill="x", padx=10, pady=10)
        
        # Gestion de la touche Entrée
        self.password_entry.bind("<Return>", lambda e: self.authenticate())

    def setup_footer(self):
        """Configure le pied de page avec le lien d'aide"""
        footer_frame = ttk.Frame(self)
        footer_frame.pack(fill="x", pady=(10, 20))
        
        help_link = ttk.Label(footer_frame,
                            text="Besoin d'aide ? Contactez l'administrateur",
                            style='Link.TLabel',
                            cursor="hand2")
        help_link.pack()
        help_link.bind("<Button-1>", lambda e: self.contact_admin())

    def authenticate(self):
        """Authentifie l'utilisateur"""
        username = self.login_entry.get().strip()
        password = self.password_entry.get().strip()
        
        # Validation
        if not username:
            messagebox.showwarning("Champ requis", "Veuillez saisir votre identifiant", parent=self)
            self.login_entry.focus()
            return
            
        if not password:
            messagebox.showwarning("Champ requis", "Veuillez saisir votre mot de passe", parent=self)
            self.password_entry.focus()
            return
            
        # Vérification des identifiants
        success, agent = db.verifier_mot_de_passe(username, password)
        
        if success:
            self.parent.current_agent = agent
            self.parent.update_interface()
            self.destroy()
            db.ajouter_journal("Connexion", agent['nom_agent'])
        else:
            messagebox.showerror("Échec de connexion", 
                               "Identifiant ou mot de passe incorrect", 
                               parent=self)
            self.password_entry.delete(0, tk.END)
            self.password_entry.focus()

    def open_password_reset(self):
        """Ouvre la fenêtre de réinitialisation de mot de passe"""
        PasswordResetWindow(self)
        self.withdraw()

    def open_inscription(self):
        """Ouvre la fenêtre de création de compte"""
        InscriptionWindow(self)
        self.withdraw()

    def contact_admin(self):
        """Affiche les informations de contact de l'administrateur"""
        contact_window = tk.Toplevel(self)
        contact_window.title("Contact Administrateur")
        contact_window.geometry("400x250")
        
        # Centrage
        x = self.winfo_x() + (self.winfo_width() - 400) // 2
        y = self.winfo_y() + (self.winfo_height() - 250) // 2
        contact_window.geometry(f"+{x}+{y}")
        
        # Contenu
        ttk.Label(contact_window, 
                 text="Contact Administrateur", 
                 style='Title.TLabel').pack(pady=20)
        
        info_frame = ttk.Frame(contact_window)
        info_frame.pack(pady=10)
        
        ttk.Label(info_frame, text="Email:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        ttk.Label(info_frame, text="kiongasplane@gmail.com", foreground=PRIMARY_COLOR).grid(row=0, column=1, sticky="w", pady=5)
        
        ttk.Label(info_frame, text="Téléphone:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        ttk.Label(info_frame, text="+243 82 058 65 51", foreground=PRIMARY_COLOR).grid(row=1, column=1, sticky="w", pady=5)
        
        ttk.Button(contact_window, 
                  text="Fermer", 
                  command=contact_window.destroy).pack(pady=20)

    def quit_app(self):
        """Quitte proprement l'application"""
        self.parent.destroy()

class PasswordResetWindow(tk.Toplevel):
    """Fenêtre de réinitialisation de mot de passe"""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Réinitialisation du mot de passe")
        self.geometry("400x400")
        self.resizable(False, False)
        
        # Style
        self.style = ttk.Style()
        self.style.configure('TLabel', background=BACKGROUND_COLOR, font=FONT_NORMAL)
        self.style.configure('TEntry', font=FONT_NORMAL, padding=5)
        self.style.configure('Title.TLabel', font=FONT_TITLE, foreground=PRIMARY_COLOR)
        
        # Centrer la fenêtre
        self.center_window()
        
        # Interface
        self.setup_ui()
    
    def center_window(self):
        """Centre la fenêtre sur l'écran"""
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')
    
    def setup_ui(self):
        """Configure l'interface utilisateur"""
        main_frame = ttk.Frame(self, padding=20)
        main_frame.pack(fill="both", expand=True)
        
        ttk.Label(main_frame, 
                 text="Réinitialiser le mot de passe", 
                 style='Title.TLabel').pack(pady=10)
        
        # Instructions
        ttk.Label(main_frame, 
                 text="Veuillez saisir votre identifiant et votre nouveau mot de passe",
                 wraplength=350,
                 justify="center").pack(pady=10)
        
        # Champ identifiant
        ttk.Label(main_frame, text="Identifiant:").pack(anchor="w", pady=(10, 0))
        self.identifiant_entry = ttk.Entry(main_frame)
        self.identifiant_entry.pack(fill="x", pady=(0, 10))
        
        # Champ nouveau mot de passe
        ttk.Label(main_frame, text="Nouveau mot de passe:").pack(anchor="w", pady=(10, 0))
        self.new_password_entry = ttk.Entry(main_frame, show="•")
        self.new_password_entry.pack(fill="x", pady=(0, 10))
        
        # Champ confirmation
        ttk.Label(main_frame, text="Confirmer le mot de passe:").pack(anchor="w", pady=(10, 0))
        self.confirm_password_entry = ttk.Entry(main_frame, show="•")
        self.confirm_password_entry.pack(fill="x", pady=(0, 20))
        
        # Bouton de validation
        ttk.Button(main_frame, 
                  text="Réinitialiser", 
                  style='Login.TButton',
                  command=self.reset_password).pack(fill="x", pady=(0, 10))
        
        # Bouton retour
        ttk.Button(main_frame, 
                  text="Retour à la connexion", 
                  command=self.back_to_login).pack(fill="x")
    
    def reset_password(self):
        """Réinitialise le mot de passe"""
        identifiant = self.identifiant_entry.get().strip()
        new_password = self.new_password_entry.get().strip()
        confirm_password = self.confirm_password_entry.get().strip()
        
        # Validation
        if not identifiant:
            messagebox.showwarning("Champ requis", "Veuillez saisir votre identifiant", parent=self)
            return
            
        if not new_password or not confirm_password:
            messagebox.showwarning("Champs requis", "Veuillez saisir et confirmer le nouveau mot de passe", parent=self)
            return
            
        if new_password != confirm_password:
            messagebox.showwarning("Erreur", "Les mots de passe ne correspondent pas", parent=self)
            return
            
        if len(new_password) < 6:
            messagebox.showwarning("Mot de passe faible", "Le mot de passe doit contenir au moins 6 caractères", parent=self)
            return
            
        # Vérifier que l'identifiant existe
        try:
            with db.connexion_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT nom_agent FROM agent WHERE identifiant = ?", (identifiant,))
                result = cur.fetchone()
                if not result:
                    messagebox.showerror("Erreur", "Identifiant introuvable", parent=self)
                    return
                nom_agent = result[0]
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Impossible de vérifier l'identifiant: {e}", parent=self)
            return
            
        # Réinitialisation du mot de passe
        if db.reinitialiser_mot_de_passe(identifiant, new_password):
            messagebox.showinfo("Succès", "Mot de passe réinitialisé avec succès", parent=self)
            db.ajouter_journal("Réinitialisation MDP", "Système", cible=nom_agent)
            self.back_to_login()
        else:
            messagebox.showerror("Erreur", "Échec de la réinitialisation", parent=self)
    
    def back_to_login(self):
        """Retour à la fenêtre de connexion"""
        self.destroy()
        self.parent.deiconify()

class InscriptionWindow(tk.Toplevel):
    """Fenêtre d'inscription pour nouveaux agents"""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Création de compte")
        self.geometry("500x600")
        self.photo_path = None
        
        # Style
        self.style = ttk.Style()
        self.style.configure('TLabel', font=FONT_NORMAL)
        self.style.configure('TButton', font=FONT_NORMAL, padding=5)
        
        # Widgets
        ttk.Label(self, text="Création de compte agent", font=FONT_TITLE).pack(pady=10)
        
        # Photo preview
        self.photo_frame = ttk.Frame(self)
        self.photo_frame.pack(pady=10)
        self.photo_label = ttk.Label(self.photo_frame)
        self.photo_label.pack()
        self.default_avatar = create_default_avatar("", (150, 150))
        self.photo_label.config(image=self.default_avatar)
        
        ttk.Button(self.photo_frame, text="Choisir photo", command=self.choisir_photo).pack(pady=5)
        
        # Formulaire
        form_frame = ttk.Frame(self)
        form_frame.pack(pady=10, fill="x", padx=20)
        
        ttk.Label(form_frame, text="Nom complet:").grid(row=0, column=0, sticky="e", pady=5)
        self.nom_entry = ttk.Entry(form_frame)
        self.nom_entry.grid(row=0, column=1, pady=5, sticky="ew")
        
        ttk.Label(form_frame, text="Identifiant:").grid(row=1, column=0, sticky="e", pady=5)
        self.identifiant_entry = ttk.Entry(form_frame)
        self.identifiant_entry.grid(row=1, column=1, pady=5, sticky="ew")
        
        ttk.Label(form_frame, text="Mot de passe:").grid(row=2, column=0, sticky="e", pady=5)
        self.mdp_entry = ttk.Entry(form_frame, show="•")
        self.mdp_entry.grid(row=2, column=1, pady=5, sticky="ew")
        
        ttk.Label(form_frame, text="Confirmer mot de passe:").grid(row=3, column=0, sticky="e", pady=5)
        self.confirm_mdp_entry = ttk.Entry(form_frame, show="•")
        self.confirm_mdp_entry.grid(row=3, column=1, pady=5, sticky="ew")
        
        # Boutons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=20)
        
        ttk.Button(btn_frame, text="Créer compte", command=self.creer_compte).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="Annuler", command=self.destroy).pack(side="right", padx=10)
        
        form_frame.columnconfigure(1, weight=1)
    
    def choisir_photo(self):
        """Permet de sélectionner une photo de profil avec gestion des permissions"""
        filetypes = [("Images", "*.jpg *.jpeg *.png")]
        try:
            filename = filedialog.askopenfilename(title="Choisir une photo", filetypes=filetypes)
            
            if filename:
                # Vérifier les permissions de lecture
                if not os.access(filename, os.R_OK):
                    messagebox.showerror("Permission refusée", "L'application n'a pas les droits pour lire ce fichier")
                    return
                
                self.photo_path = filename
                try:
                    img = Image.open(filename).resize((150, 150))
                    self.photo = ImageTk.PhotoImage(img)
                    self.photo_label.config(image=self.photo)
                except Exception as e:
                    messagebox.showerror("Erreur", f"Impossible de charger l'image: {e}")
                    self.photo_path = None
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la sélection de la photo: {e}")
    
    def creer_compte(self):
        """Crée le nouveau compte avec gestion des permissions"""
        nom = self.nom_entry.get().strip()
        identifiant = self.identifiant_entry.get().strip()
        mdp = self.mdp_entry.get().strip()
        confirm_mdp = self.confirm_mdp_entry.get().strip()
        
        # Validation
        if not nom or not identifiant or not mdp:
            messagebox.showwarning("Champs manquants", "Tous les champs sont obligatoires")
            return
            
        if mdp != confirm_mdp:
            messagebox.showwarning("Erreur", "Les mots de passe ne correspondent pas")
            return
            
        if len(mdp) < 6:
            messagebox.showwarning("Mot de passe faible", "Le mot de passe doit contenir au moins 6 caractères")
            return
            
        # Création du compte
        try:
            if db.creer_compte_agent(nom, identifiant, mdp, photo_path=self.photo_path):
                messagebox.showinfo("Succès", "Compte créé avec succès!")
                self.destroy()
            else:
                messagebox.showerror("Erreur", "Impossible de créer le compte (identifiant peut-être déjà utilisé)")
        except PermissionError as pe:
            messagebox.showerror("Erreur de permission", f"L'application n'a pas les droits nécessaires: {str(pe)}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur inattendue: {str(e)}")

class Application(tk.Tk):
    """Application principale du système d'épargne"""
    def __init__(self):
        super().__init__()
        self.title("Système d'Épargne $-MONEY")
        
        # Configuration plein écran non redimensionnable
        self.state('zoomed')  # Plein écran
        self.resizable(False, False)  # Non redimensionnable
        
        self.configure(bg=BACKGROUND_COLOR)
        
        # Vérifier les permissions système
        try:
            if not setup_permissions():
                raise PermissionError("Permissions système insuffisantes")
        except PermissionError as pe:
            messagebox.showerror("Erreur Critique", 
                                f"L'application ne peut pas démarrer:\n{str(pe)}\n"
                                "Veuillez exécuter en tant qu'administrateur ou vérifier les permissions des dossiers.")
            self.destroy()
            return
        
        # Initialisation de la base de données
        if not db.initialiser_base():
            messagebox.showerror("Erreur", "Impossible d'initialiser la base de données")
            self.destroy()
            return
        
        # Créer un admin par défaut si aucun compte existe
        self.create_default_admin()
        
        # Style
        self.setup_styles()
        
        # Barre de menu (initialement désactivée)
        self.setup_menu()
        
        # Contenu principal
        self.setup_main_content()
        
        # Fenêtre de connexion
        self.show_login_window()
        
        # Rafraîchissement automatique
        self.bind("<FocusIn>", self.refresh_on_focus)
    
    def create_default_admin(self):
        """Crée un admin par défaut si aucun compte n'existe"""
        try:
            with db.connexion_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM agent")
                if cur.fetchone()[0] == 0:
                    db.ajouter_agent(
                        nom="Administrateur",
                        identifiant="admin",
                        mot_de_passe="admin123",
                        role="admin"
                    )
                    print("Compte admin par défaut créé (identifiant: admin, mot de passe: admin123)")
        except Exception as e:
            print(f"Erreur création admin par défaut: {e}")
    
    def setup_styles(self):
        """Configure les styles de l'application"""
        style = ttk.Style()
        
        # Style des boutons
        style.configure('TButton', 
                      font=FONT_NORMAL,
                      padding=6,
                      background=PRIMARY_COLOR,
                      foreground='white')
        style.map('TButton',
                background=[('active', SECONDARY_COLOR),
                          ('disabled', '#CCCCCC')])
        
        # Style des entrées
        style.configure('TEntry', 
                      font=FONT_NORMAL,
                      padding=5)
        
        # Style des labels
        style.configure('TLabel', 
                      font=FONT_NORMAL,
                      background=BACKGROUND_COLOR,
                      foreground=TEXT_COLOR)
        
        # Style des titres
        style.configure('Title.TLabel', 
                      font=FONT_TITLE,
                      foreground=PRIMARY_COLOR)
        
        # Style des frames
        style.configure('Card.TFrame',
                      background="white",
                      relief="groove",
                      borderwidth=2)
    
    def setup_menu(self):
        """Configure la barre de menu principale"""
        self.menubar = tk.Menu(self)
        
        # Menu Fichier
        self.file_menu = tk.Menu(self.menubar, tearoff=0)
        self.file_menu.add_command(label="Nouveau client", command=self.open_inscription, state=tk.DISABLED)
        self.file_menu.add_command(label="Nouveau dépôt", command=self.open_depot, state=tk.DISABLED)
        self.file_menu.add_command(label="Nouveau retrait", command=self.open_retrait, state=tk.DISABLED)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Quitter", command=self.quit)
        self.menubar.add_cascade(label="Fichier", menu=self.file_menu)
        
        # Menu Gestion
        self.manage_menu = tk.Menu(self.menubar, tearoff=0)
        self.manage_menu.add_command(label="Gérer les agents", command=self.manage_agents, state=tk.DISABLED)
        self.manage_menu.add_command(label="Paramètres", command=self.open_settings, state=tk.DISABLED)
        self.menubar.add_cascade(label="Gestion", menu=self.manage_menu)
        
        # Menu Aide
        self.help_menu = tk.Menu(self.menubar, tearoff=0)
        self.help_menu.add_command(label="Documentation", command=self.open_docs)
        self.help_menu.add_command(label="À propos", command=self.show_about)
        self.menubar.add_cascade(label="Aide", menu=self.help_menu)
        
        self.config(menu=self.menubar)
    
    def setup_main_content(self):
        """Configure le contenu principal de l'application"""
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Section de bienvenue
        welcome_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        welcome_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(welcome_frame, 
                 text="BIENVENUE AU SERVICE CENTRAL D'EPARGNE $-MONEY", 
                 style='Title.TLabel').pack(pady=10)
        
        self.user_label = ttk.Label(welcome_frame, 
                                  text="Connectez-vous pour commencer",
                                  font=FONT_SUBTITLE)
        self.user_label.pack(pady=(0, 10))
        
        # Statistiques rapides
        stats_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        stats_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(stats_frame, 
                 text="Statistiques", 
                 style='Title.TLabel').pack(pady=5)
        
        self.stats_subframe = ttk.Frame(stats_frame)
        self.stats_subframe.pack(fill="x", pady=5)
        
        # Dernières activités
        activity_frame = ttk.Frame(self.main_frame, style='Card.TFrame')
        activity_frame.pack(fill="both", expand=True)
        
        ttk.Label(activity_frame, 
                 text="Dernières activités", 
                 style='Title.TLabel').pack(pady=5)
        
        self.activity_tree = ttk.Treeview(activity_frame, 
                                        columns=('date', 'action', 'details'), 
                                        show='headings',
                                        height=10)
        self.activity_tree.heading('date', text='Date')
        self.activity_tree.heading('action', text='Action')
        self.activity_tree.heading('details', text='Détails')
        self.activity_tree.column('date', width=150)
        self.activity_tree.column('action', width=200)
        self.activity_tree.column('details', width=400)
        self.activity_tree.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Boutons d'action rapide
        action_frame = ttk.Frame(self.main_frame)
        action_frame.pack(fill="x", pady=(10, 0))
        
        self.quick_deposit_btn = ttk.Button(action_frame, 
                                          text="Dépôt rapide", 
                                          command=self.open_depot,
                                          state=tk.DISABLED)
        self.quick_deposit_btn.pack(side="left", padx=5)
        
        self.quick_withdraw_btn = ttk.Button(action_frame, 
                                           text="Retrait rapide", 
                                           command=self.open_retrait,
                                           state=tk.DISABLED)
        self.quick_withdraw_btn.pack(side="left", padx=5)
        
        self.quick_client_btn = ttk.Button(action_frame, 
                                         text="Nouveau client", 
                                         command=self.open_inscription,
                                         state=tk.DISABLED)
        self.quick_client_btn.pack(side="left", padx=5)
    
    def show_login_window(self):
        """Affiche la fenêtre de connexion"""
        self.withdraw()  # Cache la fenêtre principale
        self.login_window = LoginWindow(self)
        self.login_window.grab_set()
    
    def update_interface(self):
        """Met à jour l'interface après connexion"""
        if hasattr(self, 'current_agent'):
            self.user_label.config(
                text=f"Connecté en tant que: {self.current_agent['nom_agent']} ({self.current_agent['role']})"
            )
            self.update_menu_state(True)
            self.update_stats()
            self.load_recent_activities()
            self.deiconify()  # Montre la fenêtre principale
    
    def update_menu_state(self, logged_in: bool):
        """Active ou désactive les menus selon l'état de connexion"""
        state = tk.NORMAL if logged_in else tk.DISABLED
        
        # Menu Fichier
        self.file_menu.entryconfig(0, state=state)  # Nouveau client
        self.file_menu.entryconfig(1, state=state)  # Nouveau dépôt
        self.file_menu.entryconfig(2, state=state)  # Nouveau retrait
        
        # Menu Gestion (uniquement pour les admins)
        if logged_in and self.current_agent['role'].lower() == 'admin':
            self.manage_menu.entryconfig(0, state=state)  # Gérer les agents
            self.manage_menu.entryconfig(1, state=state)  # Paramètres
        else:
            self.manage_menu.entryconfig(0, state=tk.DISABLED)
            self.manage_menu.entryconfig(1, state=tk.DISABLED)
        
        # Boutons rapides
        self.quick_deposit_btn.config(state=state)
        self.quick_withdraw_btn.config(state=state)
        self.quick_client_btn.config(state=state)
    
    def update_stats(self):
        """Met à jour les statistiques affichées"""
        for widget in self.stats_subframe.winfo_children():
            widget.destroy()
            
        try:
            with db.connexion_db() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                
                # Nombre de clients
                cur.execute("SELECT COUNT(*) FROM abonne")
                clients = cur.fetchone()[0]
                
                # Total des dépôts
                cur.execute("SELECT SUM(montant) FROM depots")
                total_depots = cur.fetchone()[0] or 0
                
                # Total des retraits
                cur.execute("SELECT SUM(montant) FROM retraits")
                total_retraits = cur.fetchone()[0] or 0
                
                # Solde total
                cur.execute("SELECT SUM(solde) FROM abonne")
                solde_total = cur.fetchone()[0] or 0
                
                # Création des cartes de stats
                self.create_stat_card("Clients", clients, PRIMARY_COLOR, 0)
                self.create_stat_card("Dépôts", f"{total_depots:,.0f} FC", SUCCESS_COLOR, 1)
                self.create_stat_card("Retraits", f"{total_retraits:,.0f} FC", ERROR_COLOR, 2)
                self.create_stat_card("Solde total", f"{solde_total:,.0f} FC", SECONDARY_COLOR, 3)
                
        except sqlite3.Error as e:
            print(f"Erreur mise à jour stats: {e}")
    
    def create_stat_card(self, title: str, value, color: str, column: int):
        """Crée une carte de statistique"""
        card = ttk.Frame(self.stats_subframe, style='Card.TFrame')
        card.grid(row=0, column=column, padx=5, sticky="nsew")
        
        ttk.Label(card, 
                 text=title,
                 font=FONT_SMALL,
                 foreground="gray").pack(pady=(5, 0))
        
        ttk.Label(card, 
                 text=str(value),
                 font=("Segoe UI", 14, "bold"),
                 foreground=color).pack(pady=(0, 5))
        
        self.stats_subframe.columnconfigure(column, weight=1)
    
    def load_recent_activities(self):
        """Charge les activités récentes"""
        for item in self.activity_tree.get_children():
            self.activity_tree.delete(item)
            
        try:
            with db.connexion_db() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("""
                    SELECT date_action || ' ' || heure_action as datetime, 
                           action, 
                           acteur || ' - ' || COALESCE(cible, '') as details
                    FROM journal
                    ORDER BY date_action DESC, heure_action DESC
                    LIMIT 20
                """)
                
                for row in cur.fetchall():
                    self.activity_tree.insert("", "end", 
                                            values=(row['datetime'], 
                                                   row['action'], 
                                                   row['details']))
        except sqlite3.Error as e:
            print(f"Erreur chargement activités: {e}")
    
    def refresh_interface(self):
        """Rafraîchit l'interface après chaque opération"""
        if not hasattr(self, 'current_agent'):
            messagebox.showwarning("Non connecté", "Veuillez vous connecter d'abord")
            return
            
        interface_retrait(self.current_agent['nom_agent'])
        db.ajouter_journal("Ouverture interface", self.current_agent['nom_agent'], "Retrait")
    
    def refresh_on_focus(self, event):
        """Rafraîchit l'interface quand la fenêtre reprend le focus"""
        self.refresh_interface()
    
    def open_inscription(self):
        """Ouvre l'interface d'inscription"""
        if not hasattr(self, 'current_agent'):
            messagebox.showwarning("Non connecté", "Veuillez vous connecter d'abord")
            return
        # Créer une nouvelle fenêtre pour l'inscription
        inscription_window = tk.Toplevel(self)
        inscription_window.title("Interface d'Inscription")
        
        # Positionner la nouvelle fenêtre près de la fenêtre principale
        x = self.winfo_x() + 50
        y = self.winfo_y() + 50
        inscription_window.geometry(f"+{x}+{y}")
        # Initialiser l'interface d'inscription
        InscriptionInterface(inscription_window)
        
        # Ajouter une entrée dans le journal
        db.ajouter_journal("Ouverture interface", self.current_agent['nom_agent'], "Inscription")
        
        # Rafraîchir après fermeture
        inscription_window.protocol("WM_DELETE_WINDOW", lambda: [
            inscription_window.destroy(),
            self.refresh_interface()
        ])
    
    def open_depot(self):
        """Ouvre l'interface de dépôt"""
        if not hasattr(self, 'current_agent'):
            messagebox.showwarning("Non connecté", "Veuillez vous connecter d'abord")
            return
            
        # Ouvrir la fenêtre de dépôt avec callback de rafraîchissement
        depot_window = FenetreDepot(self, self.current_agent['nom_agent'])
        db.ajouter_journal("Ouverture interface", self.current_agent['nom_agent'], "Dépôt")
        
        # Rafraîchir après fermeture
        depot_window.protocol("WM_DELETE_WINDOW", lambda: [
            depot_window.destroy(),
            self.refresh_interface()
        ])
    
    # form1.py (ligne ~845)
    def open_retrait(self):
        if not hasattr(self, 'current_agent'):
            messagebox.showwarning("Non connecté", "Veuillez vous connecter d'abord")
            return
    
        # Créer une fenêtre pour le retrait
        retrait_window = tk.Toplevel(self)
        retrait_window.title("Interface de Retrait")
    
        # Ouvrir l'interface de retrait - PASSER LA FENÊTRE EN PARAMÈTRE
        interface_retrait(self.current_agent['nom_agent'], retrait_window)
    
        # Rafraîchir après fermeture
        retrait_window.protocol("WM_DELETE_WINDOW", lambda: [
        retrait_window.destroy(),
        self.refresh_interface()
    ])
    
    def refresh_interface(self):
        """Rafraîchit l'interface après chaque opération"""
        if hasattr(self, 'current_agent'):
            self.update_stats()
            self.load_recent_activities()
    
    def manage_agents(self):
        """Ouvre la gestion des agents"""
        if not hasattr(self, 'current_agent'):
            messagebox.showwarning("Non connecté", "Veuillez vous connecter d'abord")
            return
            
        if self.current_agent['role'].lower() != 'admin':
            messagebox.showwarning("Permission refusée", "Seuls les administrateurs peuvent gérer les agents")
            return
            
        agents_window = ManageAgentsWindow(self)
        db.ajouter_journal("Ouverture interface", self.current_agent['nom_agent'], "Gestion agents")
        
        # Rafraîchir après fermeture
        agents_window.protocol("WM_DELETE_WINDOW", lambda: [
            agents_window.destroy(),
            self.refresh_interface()
        ])
    
    def open_settings(self):
        """Ouvre les paramètres"""
        if not hasattr(self, 'current_agent'):
            messagebox.showwarning("Non connecté", "Veuillez vous connecter d'abord")
            return
            
        settings_window = SettingsWindow(self)
        db.ajouter_journal("Ouverture interface", self.current_agent['nom_agent'], "Paramètres")
        
        # Rafraîchir après fermeture
        settings_window.protocol("WM_DELETE_WINDOW", lambda: [
            settings_window.destroy(),
            self.refresh_interface()
        ])
    
    def open_docs(self):
        """Ouvre la documentation"""
        webbrowser.open("https://docs.example.com")
    
    def show_about(self):
        """Affiche la boîte 'À propos'"""
        about_window = tk.Toplevel(self)
        about_window.title("À propos de $-MONEY")
        about_window.geometry("400x300")
        
        # Centrer la fenêtre
        self.update_idletasks()
        x = (self.winfo_screenwidth() - 700) // 2
        y = (self.winfo_screenheight() - 600) // 2
        about_window.geometry(f"+{x}+{y}")
        
        # Contenu
        ttk.Label(about_window, 
                 text=" SERVICE CENTRAL D'EPARGNE", 
                 style='Title.TLabel').pack(pady=20)
        ttk.Label(about_window,
                  text="$ - MONEY/Easy save, Easy get",
                  style='Title.TLabel').pack(pady=5)
        
        ttk.Label(about_window, 
                 text="Système de gestion d'épargne\nVersion 1.1\n\n© 2025 Tous droits réservés",
                 justify="center").pack(pady=10)
        
        ttk.Label(about_window,
                  text="Développé par KIONGA TIMOTHEE SPLANE",justify="center").pack(pady=10)
        
        ttk.Button(about_window, 
                  text="Fermer", 
                  command=about_window.destroy).pack(pady=20)


# ==================== FENÊTRES SECONDAIRES ====================
class ManageAgentsWindow(tk.Toplevel):
    """Fenêtre de gestion des agents"""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Gestion des Agents")
        self.geometry("800x600")
        
        # Centrer la fenêtre
        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 1200) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 1000) // 2
        self.geometry(f"+{x}+{y}")
        
        # Variables
        self.agent_photo = None
        self.photo_path = None
        
        # Interface
        self.setup_ui()
        self.load_agents()
    
    def setup_ui(self):
        """Configure l'interface utilisateur"""
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Formulaire d'ajout
        form_frame = ttk.Frame(main_frame, style='Card.TFrame')
        form_frame.pack(fill="x", pady=(0, 10))
        
        ttk.Label(form_frame, 
                 text="Ajouter un nouvel agent", 
                 style='Title.TLabel').grid(row=0, column=0, columnspan=2, pady=10)
        
        # Champs du formulaire
        ttk.Label(form_frame, text="Nom complet:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.nom_entry = ttk.Entry(form_frame)
        self.nom_entry.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        
        ttk.Label(form_frame, text="Identifiant:").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.identifiant_entry = ttk.Entry(form_frame)
        self.identifiant_entry.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        
        ttk.Label(form_frame, text="Mot de passe:").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        self.mdp_entry = ttk.Entry(form_frame, show="*")
        self.mdp_entry.grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        
        ttk.Label(form_frame, text="Rôle:").grid(row=4, column=0, sticky="e", padx=5, pady=5)
        self.role_combo = ttk.Combobox(form_frame, values=["admin", "agent"], state="readonly")
        self.role_combo.grid(row=4, column=1, sticky="ew", padx=5, pady=5)
        self.role_combo.current(1)
        
        ttk.Label(form_frame, text="Photo:").grid(row=5, column=0, sticky="e", padx=5, pady=5)
        photo_frame = ttk.Frame(form_frame)
        photo_frame.grid(row=5, column=1, sticky="ew", padx=5, pady=5)
        
        self.photo_label = ttk.Label(photo_frame, text="Aucune photo sélectionnée")
        self.photo_label.pack(side="left", fill="x", expand=True)
        
        ttk.Button(photo_frame, 
                  text="Choisir...", 
                  command=self.select_photo).pack(side="right")
        
        # Boutons
        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=6, column=0, columnspan=2, pady=10)
        
        ttk.Button(button_frame, 
                  text="Ajouter", 
                  command=self.add_agent).pack(side="left", padx=5)
        ttk.Button(button_frame, 
                  text="Effacer", 
                  command=self.clear_form).pack(side="left", padx=5)
        
        # Liste des agents
        list_frame = ttk.Frame(main_frame, style='Card.TFrame')
        list_frame.pack(fill="both", expand=True)
        
        ttk.Label(list_frame, 
                 text="Liste des agents", 
                 style='Title.TLabel').pack(pady=10)
        
        columns = ("id", "nom", "identifiant", "role", "date_creation", "actif")
        self.agents_tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        
        # Configuration des colonnes
        self.agents_tree.heading("id", text="ID")
        self.agents_tree.heading("nom", text="Nom")
        self.agents_tree.heading("identifiant", text="Identifiant")
        self.agents_tree.heading("role", text="Rôle")
        self.agents_tree.heading("date_creation", text="Date création")
        self.agents_tree.heading("actif", text="Actif")
        
        self.agents_tree.column("id", width=50, anchor="center")
        self.agents_tree.column("nom", width=150)
        self.agents_tree.column("identifiant", width=100)
        self.agents_tree.column("role", width=80, anchor="center")
        self.agents_tree.column("date_creation", width=120)
        self.agents_tree.column("actif", width=50, anchor="center")
        
        # Barre de défilement
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.agents_tree.yview)
        self.agents_tree.configure(yscrollcommand=scrollbar.set)
        
        self.agents_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # Boutons d'action
        action_frame = ttk.Frame(list_frame)
        action_frame.pack(fill="x", pady=(10, 0))
        
        ttk.Button(action_frame, 
                  text="Désactiver", 
                  command=self.toggle_agent).pack(side="left", padx=5)
        ttk.Button(action_frame, 
                  text="Réinitialiser MDP", 
                  command=self.reset_password).pack(side="left", padx=5)
        ttk.Button(action_frame, 
                  text="Actualiser", 
                  command=self.load_agents).pack(side="right", padx=5)
        
        # Configurer le poids des colonnes
        form_frame.columnconfigure(1, weight=1)
    
    def select_photo(self):
        """Sélectionne une photo pour l'agent avec gestion des permissions"""
        filetypes = [("Images", "*.jpg *.jpeg *.png")]
        try:
            filename = filedialog.askopenfilename(title="Sélectionner une photo", filetypes=filetypes)
            
            if filename:
                # Vérifier les permissions de lecture
                if not os.access(filename, os.R_OK):
                    messagebox.showerror("Permission refusée", "L'application n'a pas les droits pour lire ce fichier")
                    return
                
                self.photo_path = filename
                self.photo_label.config(text=os.path.basename(filename))
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la sélection de la photo: {e}")
    
    def clear_form(self):
        """Efface le formulaire"""
        self.nom_entry.delete(0, tk.END)
        self.identifiant_entry.delete(0, tk.END)
        self.mdp_entry.delete(0, tk.END)
        self.role_combo.current(1)
        self.photo_path = None
        self.photo_label.config(text="Aucune photo sélectionnée")
    
    def add_agent(self):
        """Ajoute un nouvel agent avec gestion des permissions"""
        nom = self.nom_entry.get().strip()
        identifiant = self.identifiant_entry.get().strip()
        mdp = self.mdp_entry.get().strip()
        role = self.role_combo.get()
        
        if not nom or not identifiant or not mdp:
            messagebox.showwarning("Champs manquants", "Veuillez remplir tous les champs obligatoires")
            return
            
        if len(mdp) < 6:
            messagebox.showwarning("Mot de passe faible", "Le mot de passe doit contenir au moins 6 caractères")
            return
            
        # Convertir la photo en BLOB si elle existe
        photo_blob = None
        if self.photo_path:
            try:
                # Vérifier les permissions de lecture
                if not os.access(self.photo_path, os.R_OK):
                    raise PermissionError(f"Permission refusée pour lire {self.photo_path}")
                
                with open(self.photo_path, 'rb') as f:
                    photo_blob = f.read()
            except PermissionError as pe:
                messagebox.showerror("Erreur de permission", str(pe))
                return
            except Exception as e:
                messagebox.showerror("Erreur photo", f"Impossible de lire la photo: {e}")
                return
        
        try:
            success = db.ajouter_agent(nom, identifiant, mdp, role, photo_blob)
            if success:
                messagebox.showinfo("Succès", "Agent ajouté avec succès")
                self.clear_form()
                self.load_agents()
            else:
                messagebox.showerror("Erreur", "Impossible d'ajouter l'agent (identifiant peut-être déjà utilisé)")
        except PermissionError as pe:
            messagebox.showerror("Erreur de permission", f"L'application n'a pas les droits nécessaires: {str(pe)}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Une erreur s'est produite: {e}")
    
    def load_agents(self):
        """Charge la liste des agents"""
        for item in self.agents_tree.get_children():
            self.agents_tree.delete(item)
            
        try:
            agents = db.get_all_users()
            for agent in agents:
                self.agents_tree.insert("", "end", 
                                      values=(agent['id'],
                                             agent['nom_agent'],
                                             agent['identifiant'],
                                             agent['role'],
                                             agent['date_creation'],
                                             "Oui" if agent['actif'] else "Non"))
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger les agents: {e}")
    
    def toggle_agent(self):
        """Active/désactive un agent sélectionné"""
        selected = self.agents_tree.selection()
        if not selected:
            messagebox.showwarning("Sélection requise", "Veuillez sélectionner un agent")
            return
            
        item = self.agents_tree.item(selected[0])
        agent_id = item['values'][0]
        current_status = item['values'][5] == "Oui"
        
        try:
            with db.connexion_db() as conn:
                cur = conn.cursor()
                cur.execute("UPDATE agent SET actif = ? WHERE id = ?", 
                          (not current_status, agent_id))
                conn.commit()
                
                self.load_agents()
                messagebox.showinfo("Succès", "Statut de l'agent mis à jour")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de modifier l'agent: {e}")
    
    def reset_password(self):
        """Réinitialise le mot de passe d'un agent"""
        selected = self.agents_tree.selection()
        if not selected:
            messagebox.showwarning("Sélection requise", "Veuillez sélectionner un agent")
            return
            
        item = self.agents_tree.item(selected[0])
        agent_id = item['values'][0]
        agent_name = item['values'][1]
        
        # Demander confirmation
        if not messagebox.askyesno("Confirmation", 
                                 f"Réinitialiser le mot de passe de {agent_name}?\nLe nouveau mot de passe sera 'password123'."):
            return
            
        try:
            with db.connexion_db() as conn:
                cur = conn.cursor()
                new_password = db.hash_password("password123")
                cur.execute("UPDATE agent SET mot_de_passe = ? WHERE id = ?", 
                          (new_password, agent_id))
                conn.commit()
                
                messagebox.showinfo("Succès", "Mot de passe réinitialisé avec succès")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de réinitialiser le mot de passe: {e}")

class SettingsWindow(tk.Toplevel):
    """Fenêtre des paramètres"""
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Paramètres")
        self.geometry("600x400")
        
        # Centrer la fenêtre
        parent.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - 600) // 2
        y = parent.winfo_y() + (parent.winfo_height() - 400) // 2
        self.geometry(f"+{x}+{y}")
        
        # Variables
        self.settings = {}
        
        # Interface
        self.setup_ui()
        self.load_settings()
    
    def setup_ui(self):
        """Configure l'interface utilisateur"""
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Onglets
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill="both", expand=True)
        
        # Onglet Général
        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text="Général")
        
        ttk.Label(general_frame, 
                 text="Paramètres généraux", 
                 style='Title.TLabel').pack(pady=10)
        
        # Paramètres
        settings_frame = ttk.Frame(general_frame)
        settings_frame.pack(fill="x", padx=10, pady=10)
        
        ttk.Label(settings_frame, text="Taux d'intérêt (%):").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.interest_rate = ttk.Entry(settings_frame)
        self.interest_rate.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        
        ttk.Label(settings_frame, text="Dépôt minimum ($):").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.min_deposit = ttk.Entry(settings_frame)
        self.min_deposit.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        
        ttk.Label(settings_frame, text="Retrait minimum ($):").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.min_withdrawal = ttk.Entry(settings_frame)
        self.min_withdrawal.grid(row=2, column=1, sticky="ew", padx=5, pady=5)
        
        # Boutons
        button_frame = ttk.Frame(general_frame)
        button_frame.pack(fill="x", pady=10)
        
        ttk.Button(button_frame, 
                  text="Enregistrer", 
                  command=self.save_settings).pack(side="right", padx=5)
        
        # Configurer le poids des colonnes
        settings_frame.columnconfigure(1, weight=1)
    
    def load_settings(self):
        """Charge les paramètres actuels"""
        try:
            with db.connexion_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT cle, valeur FROM parametres")
                
                for row in cur.fetchall():
                    self.settings[row[0]] = row[1]
                
                # Mettre à jour les champs
                self.interest_rate.insert(0, self.settings.get('taux_interet', '5.0'))
                self.min_deposit.insert(0, self.settings.get('depot_min', '500'))
                self.min_withdrawal.insert(0, self.settings.get('retrait_min', '1000'))
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger les paramètres: {e}")
    
    def save_settings(self):
        """Enregistre les paramètres modifiés"""
        try:
            new_settings = {
                'taux_interet': self.interest_rate.get(),
                'depot_min': self.min_deposit.get(),
                'retrait_min': self.min_withdrawal.get()
            }
            
            with db.connexion_db() as conn:
                cur = conn.cursor()
                
                for key, value in new_settings.items():
                    cur.execute("UPDATE parametres SET valeur = ? WHERE cle = ?", (value, key))
                
                conn.commit()
                messagebox.showinfo("Succès", "Paramètres enregistrés avec succès")
        except PermissionError as pe:
            messagebox.showerror("Erreur de permission", f"L'application n'a pas les droits nécessaires: {str(pe)}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'enregistrer les paramètres: {e}")

# ==================== POINT D'ENTRÉE ====================
if __name__ == "__main__":
    # Vérification initiale des permissions
    try:
        if not setup_permissions():
            raise PermissionError("Permissions système insuffisantes")
        
        app = Application()
        app.mainloop()
    except PermissionError as pe:
        messagebox.showerror("Erreur Critique", 
                            f"L'application ne peut pas démarrer:\n{str(pe)}\n"
                            "Veuillez exécuter en tant qu'administrateur.")
        sys.exit(1)
    except Exception as e:
        messagebox.showerror("Erreur Inattendue", f"Une erreur critique s'est produite:\n{str(e)}")
        sys.exit(1)