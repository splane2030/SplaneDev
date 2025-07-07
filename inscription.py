import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from tkcalendar import DateEntry
import datetime
import time
import os
import sys
import random
import sqlite3
from PIL import Image, ImageTk, ImageOps
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
import tempfile
import webbrowser
import logging
import stat
import shutil
from typing import Optional, List, Dict, Tuple
import subprocess

# ==================== CONFIGURATION DE LA BASE DE DONNÉES CENTRALE ====================

def resource_path(relative_path: str) -> str:
    """Résout les chemins pour PyInstaller"""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_db_path() -> str:
    """Retourne le chemin de la base de données centrale"""
    # Chemin pour l'application principale
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Chemin par défaut dans APPDATA
    appdata_dir = os.getenv('APPDATA')
    app_folder = os.path.join(appdata_dir, "MyApp") if appdata_dir else os.path.join(app_dir, "data")
    
    # Créer le dossier si nécessaire
    os.makedirs(app_folder, exist_ok=True)
    
    db_path = os.path.join(app_folder, "data_epargne.db")
    
    # Copier la base originale si nécessaire
    if not os.path.exists(db_path):
        original_db = resource_path("data_epargne.db")
        if os.path.exists(original_db):
            try:
                shutil.copyfile(original_db, db_path)
                print(f"Base de données copiée de {original_db} vers {db_path}")
            except Exception as e:
                print(f"Erreur copie DB: {e}")
    
    return db_path

def get_photo_dir() -> str:
    """Retourne le répertoire pour stocker les photos"""
    appdata_dir = os.getenv('APPDATA')
    photos_dir = os.path.join(appdata_dir, "MyApp", "photos") if appdata_dir else "photos"
    os.makedirs(photos_dir, exist_ok=True)
    return photos_dir

def get_photo_path(filename: str) -> str:
    """Retourne un chemin complet pour une photo"""
    return os.path.join(get_photo_dir(), filename)

def connexion_db() -> sqlite3.Connection:
    """Établit une connexion à la base centrale"""
    db_path = get_db_path()
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn
    except sqlite3.Error as e:
        raise sqlite3.OperationalError(f"Impossible de se connecter à la base centrale: {str(e)}\nChemin: {db_path}")

def initialiser_base():
    """Vérifie et initialise la structure de la base si nécessaire"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='abonne'")
            if not cur.fetchone():
                # Créer la structure de base
                schema = """
                CREATE TABLE IF NOT EXISTS agent (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nom_agent TEXT NOT NULL,
                    identifiant TEXT UNIQUE NOT NULL,
                    mot_de_passe TEXT NOT NULL,
                    photo BLOB,
                    role TEXT DEFAULT 'agent',
                    date_creation TEXT,
                    actif INTEGER DEFAULT 1
                );
                
                CREATE TABLE IF NOT EXISTS abonne (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_client TEXT UNIQUE NOT NULL,
                    numero_carte TEXT UNIQUE NOT NULL,
                    nom TEXT NOT NULL,
                    postnom TEXT,
                    prenom TEXT,
                    sexe TEXT CHECK(sexe IN ('M', 'F')),
                    date_naissance TEXT,
                    lieu_naissance TEXT,
                    adresse TEXT,
                    telephone TEXT,
                    suppleant TEXT,
                    contact_suppleant TEXT,
                    type_compte TEXT NOT NULL CHECK(type_compte IN ('Fixe', 'Mixte', 'Bloque')),
                    montant REAL,
                    photo TEXT,
                    date_inscription TEXT,
                    solde REAL DEFAULT 0,
                    duree_blocage INTEGER DEFAULT 0,
                    montant_atteindre REAL DEFAULT 0,
                    pourcentage_retrait INTEGER DEFAULT 30,
                    frequence_retrait TEXT DEFAULT 'Mensuel',
                    date_derniere_operation TEXT,
                    statut TEXT DEFAULT 'Actif' CHECK(statut IN ('Actif', 'Inactif', 'Bloqué'))
                );
                
                CREATE TABLE IF NOT EXISTS depots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_client TEXT NOT NULL,
                    montant REAL NOT NULL,
                    ref_depot TEXT UNIQUE,
                    heure TEXT NOT NULL,
                    date_depot TEXT NOT NULL,
                    nom_agent TEXT NOT NULL,
                    methode_paiement TEXT
                );
                
                CREATE TABLE IF NOT EXISTS retraits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_client TEXT NOT NULL,
                    montant REAL NOT NULL,
                    ref_retrait TEXT UNIQUE,
                    heure TEXT NOT NULL,
                    date_retrait TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    statut TEXT DEFAULT 'En attente'
                );
                
                CREATE TABLE IF NOT EXISTS journal (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    acteur TEXT NOT NULL,
                    date_action TEXT NOT NULL,
                    heure_action TEXT NOT NULL,
                    cible TEXT,
                    details TEXT
                );
                
                CREATE TABLE IF NOT EXISTS compte_fixe (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_client TEXT NOT NULL,
                    numero_carte TEXT UNIQUE NOT NULL,
                    montant_initial REAL NOT NULL,
                    date_debut TEXT NOT NULL,
                    date_fin TEXT NOT NULL
                );
                
                CREATE TABLE IF NOT EXISTS compte_fixe_pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    numero_carte TEXT NOT NULL,
                    numero_client TEXT NOT NULL,
                    page INTEGER NOT NULL,
                    cases_remplies INTEGER DEFAULT 0
                );
                
                INSERT INTO agent (nom_agent, identifiant, mot_de_passe, role, date_creation) 
                VALUES ('Admin', 'admin', '8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918', 'admin', datetime('now'));
                """
                cur.executescript(schema)
                conn.commit()
                print("Structure de base de données initialisée")
    except Exception as e:
        print(f"Erreur d'initialisation de la base: {str(e)}")

def ajouter_journal(action: str, acteur: str, cible: Optional[str] = None, details: Optional[str] = None):
    """Ajoute une entrée dans le journal"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO journal (action, acteur, cible, details, date_action, heure_action)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                action, acteur, cible, details,
                datetime.datetime.now().strftime("%Y-%m-%d"),
                datetime.datetime.now().strftime("%H:%M:%S")
            ))
            conn.commit()
    except sqlite3.Error as e:
        print(f"Erreur journalisation: {str(e)}")

def generer_numero_client_unique() -> str:
    """Génère un numéro client unique de 4 chiffres"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            while True:
                numero = str(random.randint(1000, 9999))
                cur.execute("SELECT COUNT(*) FROM abonne WHERE numero_client = ?", (numero,))
                if cur.fetchone()[0] == 0:
                    return numero
    except sqlite3.Error:
        return str(random.randint(1000, 9999))

def generer_numero_carte_unique() -> str:
    """Génère un numéro de carte unique de 10 chiffres"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            while True:
                numero = str(random.randint(1000000000, 9999999999))
                cur.execute("SELECT COUNT(*) FROM abonne WHERE numero_carte = ?", (numero,))
                if cur.fetchone()[0] == 0:
                    return numero
    except sqlite3.Error:
        return str(random.randint(1000000000, 9999999999))

def hash_password(password: str, salt: str = "fixed_salt_value") -> str:
    """Hash un mot de passe avec SHA-256 et un sel"""
    return hashlib.sha256((password + salt).encode()).hexdigest()

# ==================== INTERFACE D'INSCRIPTION ====================

class WebcamCapture:
    def __init__(self):
        self.cap = None
        self.current_camera_index = 0
        self.camera_list = []
        
    def detect_cameras(self):
        if not CV2_AVAILABLE:
            return []
            
        arr = []
        for i in range(0, 4):
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap is not None and cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        arr.append(i)
                    cap.release()
            except Exception:
                continue
        self.camera_list = arr
        return arr
    
    def start_capture(self, index=0):
        if not CV2_AVAILABLE:
            return False
            
        if self.cap is not None:
            self.stop_capture()
            
        if index >= len(self.camera_list):
            return False
            
        self.current_camera_index = index
        try:
            self.cap = cv2.VideoCapture(self.camera_list[index], cv2.CAP_DSHOW)
            return self.cap.isOpened()
        except Exception:
            return False
    
    def get_frame(self):
        if not CV2_AVAILABLE:
            return None
            
        if self.cap is None or not self.cap.isOpened():
            return None
            
        try:
            ret, frame = self.cap.read()
            if ret:
                return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        except Exception:
            return None
    
    def stop_capture(self):
        if not CV2_AVAILABLE:
            return
            
        if self.cap is not None:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None
    
    def switch_camera(self):
        if not CV2_AVAILABLE:
            return False
            
        if not self.camera_list:
            return False
            
        new_index = (self.current_camera_index + 1) % len(self.camera_list)
        return self.start_capture(new_index)
    
    def __del__(self):
        self.stop_capture()

class InscriptionInterface:
    def __init__(self, parent=None, nom_agent="Administrateur"):
        # Initialisation de la base de données
        initialiser_base()
        
        # Configuration de la fenêtre principale
        if parent is None:
            self.parent = tk.Tk()
            self.parent.title("SERVICE CENTRAL D'EPARGNE - Inscription")
            self.parent.geometry("1200x800")
            self.parent.state('zoomed')
        else:
            self.parent = parent
            self.parent.title("SERVICE CENTRAL D'EPARGNE - Inscription")
            if parent.winfo_x() > 0:
                self.parent.geometry(f"+{parent.winfo_x()+50}+{parent.winfo_y()+50}")
        
        self.nom_agent = nom_agent
        self.photo_references = []
        self.current_abonne_id = None
        self.setup_ui()
        
    def setup_ui(self):
        """Configure l'interface utilisateur"""
        # Configuration des styles
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.configure('TButton', background="#128C7E", foreground='white', font=('Helvetica', 10))
        self.style.map('TButton', background=[('active', '#075E54')])
        self.style.configure('Card.TFrame', background="#FFFFFF", relief='solid', borderwidth=1)
        self.style.configure('TLabel', background="#F0F2F5", foreground="#333333")
        self.style.configure('TEntry', fieldbackground='white')
        
        # Cadre principal
        self.container = tk.Frame(self.parent, bg="#F0F2F5")
        self.container.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Variables pour les données
        self.data = {
            "numero_client": tk.StringVar(value=generer_numero_client_unique()),
            "numero_carte": tk.StringVar(value=generer_numero_carte_unique()),
            "nom": tk.StringVar(),
            "postnom": tk.StringVar(),
            "prenom": tk.StringVar(),
            "sexe": tk.StringVar(value="M"),
            "date_naissance": tk.StringVar(),
            "lieu_naissance": tk.StringVar(),
            "adresse": tk.StringVar(),
            "telephone": tk.StringVar(),
            "suppleant": tk.StringVar(),
            "contact_suppleant": tk.StringVar(),
            "type_compte": tk.StringVar(value="Fixe"),
            "montant": tk.StringVar(),
            "duree_blocage": tk.StringVar(value="3"),
            "montant_atteindre": tk.StringVar(),
            "pourcentage_retrait": tk.StringVar(value="30"),
            "frequence_retrait": tk.StringVar(value="Mensuel"),
            "photo": tk.StringVar(value="")
        }
        
        self.photo_ref = None
        self.webcam = WebcamCapture()
        
        # Création des composants
        self.create_header()
        self.create_main_frame()
        self.create_form()
        self.create_abonne_list()
        self.afficher_donnees()
        
    def create_header(self):
        """Crée l'en-tête de l'application"""
        header = tk.Frame(self.container, bg="#128C7E", height=70)
        header.pack(fill='x', pady=(0, 10))
        
        title = tk.Label(header, text="ENREGISTREMENT DES ABONNÉS", 
                        bg="#128C7E", fg='white', font=('Helvetica', 18, 'bold'))
        title.pack(side='left', padx=20, pady=15)
        
        btn_frame = tk.Frame(header, bg="#128C7E")
        btn_frame.pack(side='right', padx=20)
        
        actions = [
            ("📊 Rapport", self.rapport_global),
            ("📁 Exporter", self.exporter_donnees),
            ("❌ Fermer", self.parent.destroy)
        ]
        
        for text, cmd in actions:
            btn = ttk.Button(btn_frame, text=text, command=cmd, width=12)
            btn.pack(side='left', padx=5)

    def create_main_frame(self):
        """Crée le cadre principal"""
        self.main_frame = tk.Frame(self.container, bg="#F0F2F5")
        self.main_frame.pack(fill='both', expand=True)
        
        # Formulaire (60%)
        self.form_container = ttk.Frame(self.main_frame, style='Card.TFrame')
        self.form_container.pack(side='left', fill='both', expand=True, padx=(0, 10))
        
        # Liste des abonnés (40%)
        self.list_container = ttk.Frame(self.main_frame, style='Card.TFrame')
        self.list_container.pack(side='right', fill='both', expand=True)

    def create_form(self):
        """Crée le formulaire d'inscription"""
        # Titre du formulaire
        form_header = tk.Frame(self.form_container, bg="#FFFFFF")
        form_header.pack(fill='x', padx=10, pady=10)
        
        tk.Label(form_header, text="NOUVEL ABONNÉ", 
                font=('Helvetica', 14, 'bold'), bg="#FFFFFF", fg="#128C7E").pack(side='left')
        
        # Cadre avec barre de défilement
        form_scroll = tk.Frame(self.form_container, bg="#FFFFFF")
        form_scroll.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        canvas = tk.Canvas(form_scroll, bg="#FFFFFF", highlightthickness=0)
        scrollbar = ttk.Scrollbar(form_scroll, orient='vertical', command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#FFFFFF")
        
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Section photo
        photo_frame = tk.Frame(scrollable_frame, bg="#FFFFFF")
        photo_frame.pack(fill='x', pady=10)
        
        self.photo_label = tk.Label(photo_frame, bg='white', width=180, height=180,
                                  relief='sunken', cursor='hand2')
        self.photo_label.pack(pady=10)
        self.photo_label.bind("<Button-1>", lambda e: self.select_photo())
        self.display_photo("")
        
        # Boutons photo
        btn_frame = tk.Frame(photo_frame, bg="#FFFFFF")
        btn_frame.pack(pady=10)
        
        ttk.Button(btn_frame, text="Sélectionner photo", command=self.select_photo, width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Prendre photo", command=self.lancer_interface_capture, width=15).pack(side='left', padx=5)
        
        # Champs de formulaire
        fields = [
            ("Numéro client*", "numero_client", False, None),
            ("Numéro carte*", "numero_carte", False, None),
            ("Nom*", "nom", False, None),
            ("Postnom", "postnom", False, None),
            ("Prénom*", "prenom", False, None),
            ("Sexe*", "sexe", True, ["M", "F"]),
            ("Date naissance*", "date_naissance", False, 'date'),
            ("Lieu naissance*", "lieu_naissance", False, None),
            ("Adresse*", "adresse", False, None),
            ("Téléphone*", "telephone", False, None),
            ("Suppléant", "suppleant", False, None),
            ("Contact suppléant", "contact_suppleant", False, None),
            ("Type de compte*", "type_compte", True, ["Fixe", "Mixte", "Bloqué"]),
            ("Montant*", "montant", False, None),
            ("Durée blocage (mois)", "duree_blocage", True, ["3", "6", "9", "12", "24"]),
            ("Montant à atteindre", "montant_atteindre", False, None),
            ("Pourcentage retrait", "pourcentage_retrait", True, ["10", "20", "30", "40", "50"]),
            ("Fréquence retrait", "frequence_retrait", True, ["Mensuel", "Trimestriel", "Semestriel", "Annuel"])
        ]
        
        self.conditional_fields = {}
        
        for i, (label, key, is_combo, values) in enumerate(fields):
            frame = tk.Frame(scrollable_frame, bg="#FFFFFF")
            frame.pack(fill='x', padx=10, pady=5)
            
            self.conditional_fields[key] = frame
            
            lbl = tk.Label(frame, text=label, bg="#FFFFFF", fg="#333333", width=20, anchor='w')
            lbl.pack(side='left', padx=(0, 10))
            
            if is_combo:
                combo = ttk.Combobox(frame, textvariable=self.data[key], values=values, width=25, state='readonly')
                combo.pack(side='left', fill='x', expand=True)
            elif values == 'date':
                date_entry = DateEntry(frame, textvariable=self.data[key], locale='fr_FR', 
                                      date_pattern='yyyy-mm-dd', width=12)
                date_entry.pack(side='left', fill='x', expand=True)
            else:
                entry = ttk.Entry(frame, textvariable=self.data[key], width=28)
                entry.pack(side='left', fill='x', expand=True)
        
        # Gestion de la visibilité des champs
        self.data["type_compte"].trace_add('write', self.on_type_compte_change)
        self.on_type_compte_change()
        
        # Boutons d'action
        btn_frame = tk.Frame(scrollable_frame, bg="#FFFFFF")
        btn_frame.pack(fill='x', pady=20, padx=10)
        
        ttk.Button(btn_frame, text="Enregistrer", command=self.enregistrer, width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Réinitialiser", command=self.reinitialiser_formulaire, width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Modifier", command=self.modifier_abonne, width=15).pack(side='left', padx=5)
        ttk.Button(btn_frame, text="Supprimer", command=self.supprimer_abonne, width=15).pack(side='left', padx=5)

    def create_abonne_list(self):
        """Crée la liste des abonnés"""
        # En-tête de liste
        list_header = tk.Frame(self.list_container, bg="#FFFFFF")
        list_header.pack(fill='x', padx=10, pady=10)
        
        tk.Label(list_header, text="LISTE DES ABONNÉS", 
                font=('Helvetica', 14, 'bold'), bg="#FFFFFF", fg="#128C7E").pack(side='left')
        
        # Barre de recherche
        search_frame = tk.Frame(list_header, bg="#FFFFFF")
        search_frame.pack(side='right')
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=20)
        search_entry.pack(side='left', padx=5)
        search_entry.bind('<KeyRelease>', lambda e: self.rechercher_abonne())
        
        ttk.Button(search_frame, text="Rechercher", command=self.rechercher_abonne).pack(side='left')
        
        # Liste avec défilement
        list_frame = tk.Frame(self.list_container, bg="#FFFFFF")
        list_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        # Création du Treeview
        columns = ("ID", "Nom", "Téléphone", "Type Compte", "Solde", "Statut")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode='browse')
        
        # Configuration des colonnes
        self.tree.heading("ID", text="ID")
        self.tree.heading("Nom", text="Nom")
        self.tree.heading("Téléphone", text="Téléphone")
        self.tree.heading("Type Compte", text="Type Compte")
        self.tree.heading("Solde", text="Solde (FC)")
        self.tree.heading("Statut", text="Statut")
        
        self.tree.column("ID", width=50, anchor='center')
        self.tree.column("Nom", width=150)
        self.tree.column("Téléphone", width=100, anchor='center')
        self.tree.column("Type Compte", width=80, anchor='center')
        self.tree.column("Solde", width=100, anchor='center')
        self.tree.column("Statut", width=80, anchor='center')
        
        # Barre de défilement
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # Placement des composants
        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Lier l'événement de sélection
        self.tree.bind('<<TreeviewSelect>>', self.on_abonne_select)

    def on_type_compte_change(self, *args):
        """Gère la visibilité des champs selon le type de compte"""
        type_compte = self.data["type_compte"].get()
        
        if type_compte == "Bloqué":
            for field in ["duree_blocage", "montant_atteindre", "pourcentage_retrait", "frequence_retrait"]:
                self.conditional_fields[field].pack(fill='x', padx=10, pady=5)
        else:
            for field in ["duree_blocage", "montant_atteindre", "pourcentage_retrait", "frequence_retrait"]:
                self.conditional_fields[field].pack_forget()

    def display_photo(self, path):
        """Affiche une photo dans le formulaire"""
        try:
            if path and os.path.exists(path):
                img = Image.open(path)
                img = ImageOps.fit(img, (180, 180), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                self.photo_ref = photo
                self.photo_label.config(image=photo)
            else:
                img = Image.new('RGB', (180, 180), color='#E0E0E0')
                draw = ImageDraw.Draw(img)
                draw.text((60, 80), "Aucune photo", fill='#777777')
                photo = ImageTk.PhotoImage(img)
                self.photo_ref = photo
                self.photo_label.config(image=photo)
        except Exception as e:
            print(f"Erreur affichage photo: {str(e)}")
    
    def select_photo(self):
        """Sélectionne une photo depuis le système de fichiers"""
        file_path = filedialog.askopenfilename(
            title="Sélectionner une photo",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp")]
        )
        if file_path:
            self.data["photo"].set(file_path)
            self.display_photo(file_path)
    
    def lancer_interface_capture(self):
        """Lance l'interface de capture de photo"""
        if not CV2_AVAILABLE:
            messagebox.showwarning("Fonction désactivée", 
                                  "OpenCV n'est pas installé. La capture caméra est désactivée.")
            return
            
        cameras = self.webcam.detect_cameras()
        if not cameras:
            messagebox.showerror("Erreur", "Aucune webcam détectée")
            return
            
        if not self.webcam.start_capture():
            messagebox.showerror("Erreur", "Impossible de démarrer la webcam")
            return
            
        capture_win = tk.Toplevel(self.parent)
        capture_win.title("Capture de Photo")
        capture_win.geometry("640x520")
        capture_win.transient(self.parent)
        capture_win.grab_set()
        
        x = self.parent.winfo_x() + 100
        y = self.parent.winfo_y() + 100
        capture_win.geometry(f"+{x}+{y}")
        
        capture_frame = tk.Frame(capture_win)
        capture_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        video_label = tk.Label(capture_frame)
        video_label.pack(fill='both', expand=True)
        
        btn_frame = tk.Frame(capture_frame)
        btn_frame.pack(fill='x', pady=10)
        
        btn_capture = ttk.Button(btn_frame, text="Capturer", command=lambda: self.capture_image(capture_win))
        btn_capture.pack(side='left', padx=5)
        
        btn_switch = ttk.Button(btn_frame, text="Changer caméra", command=self.webcam.switch_camera)
        btn_switch.pack(side='left', padx=5)
        
        btn_cancel = ttk.Button(btn_frame, text="Annuler", command=capture_win.destroy)
        btn_cancel.pack(side='right', padx=5)
        
        def update_video():
            frame = self.webcam.get_frame()
            if frame is not None:
                img = Image.fromarray(frame)
                img = img.resize((640, 480), Image.LANCZOS)
                photo = ImageTk.PhotoImage(img)
                video_label.config(image=photo)
                video_label.image = photo
            capture_win.after(10, update_video)
        
        update_video()
        
        def on_close():
            self.webcam.stop_capture()
            capture_win.destroy()
        
        capture_win.protocol("WM_DELETE_WINDOW", on_close)
    
    def capture_image(self, window):
        """Capture une image depuis la webcam"""
        frame = self.webcam.get_frame()
        if frame is None:
            messagebox.showerror("Erreur", "Impossible de capturer l'image")
            return
            
        try:
            img = Image.fromarray(frame)
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = get_photo_path(f"photo_{timestamp}.jpg")
            img.save(file_path)
            self.data["photo"].set(file_path)
            self.display_photo(file_path)
            self.webcam.stop_capture()
            window.destroy()
            messagebox.showinfo("Succès", f"Photo enregistrée: {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur sauvegarde photo: {str(e)}")

    def validate_fields(self) -> bool:
        """Valide les champs obligatoires"""
        required_fields = [
            "nom", "prenom", "date_naissance", 
            "lieu_naissance", "adresse", "telephone", 
            "type_compte"
        ]
        
        # Vérification spécifique pour les comptes Fixe et Bloqué
        type_compte = self.data["type_compte"].get()
        if type_compte in ("Fixe", "Bloqué"):
            required_fields.append("montant")
            if not self.data["montant"].get().replace('.', '', 1).isdigit():
                messagebox.showerror("Erreur", "Le montant doit être un nombre valide")
                return False
        
        # Vérifier les champs vides
        for field in required_fields:
            value = self.data[field].get().strip()
            if not value:
                messagebox.showerror("Erreur", f"Le champ {field.replace('_', ' ')} est obligatoire!")
                return False
        
        # Validation du téléphone
        phone = self.data["telephone"].get().strip()
        if len(phone) != 10 or not phone.isdigit():
            messagebox.showerror("Erreur", "Le numéro de téléphone doit contenir 10 chiffres")
            return False
        
        # Validation de la date de naissance
        try:
            datetime.datetime.strptime(self.data["date_naissance"].get(), "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Erreur", "Format de date invalide. Utilisez AAAA-MM-JJ")
            return False
        
        return True
    
    def enregistrer(self):
        """Enregistre un nouvel abonné dans la base centrale"""
        if not self.validate_fields():
            return

        try:
            with connexion_db() as conn:
                cur = conn.cursor()
                
                # Préparer les données
                values = (
                    self.data["numero_client"].get(),
                    self.data["numero_carte"].get(),
                    self.data["nom"].get(),
                    self.data["postnom"].get() or "",
                    self.data["prenom"].get(),
                    self.data["sexe"].get(),
                    self.data["date_naissance"].get(),
                    self.data["lieu_naissance"].get(),
                    self.data["adresse"].get(),
                    self.data["telephone"].get(),
                    self.data["suppleant"].get() or "",
                    self.data["contact_suppleant"].get() or "",
                    self.data["type_compte"].get(),
                    float(self.data["montant"].get() or 0),
                    self.data["photo"].get() or "",
                    datetime.date.today().isoformat(),
                    0,  # solde initial
                    0,  # duree_blocage
                    0,  # montant_atteindre
                    0,  # pourcentage_retrait
                    "",  # frequence_retrait
                    datetime.date.today().isoformat(),  # date_derniere_operation
                    "Actif"  # statut
                )
                
                # Insertion dans la table abonne
                if self.current_abonne_id:
                    # Mise à jour de l'abonné existant
                    cur.execute("""
                        UPDATE abonne SET
                            numero_client = ?,
                            numero_carte = ?,
                            nom = ?,
                            postnom = ?,
                            prenom = ?,
                            sexe = ?,
                            date_naissance = ?,
                            lieu_naissance = ?,
                            adresse = ?,
                            telephone = ?,
                            suppleant = ?,
                            contact_suppleant = ?,
                            type_compte = ?,
                            montant = ?,
                            photo = ?,
                            date_inscription = ?,
                            solde = ?,
                            duree_blocage = ?,
                            montant_atteindre = ?,
                            pourcentage_retrait = ?,
                            frequence_retrait = ?,
                            date_derniere_operation = ?,
                            statut = ?
                        WHERE id = ?
                    """, values + (self.current_abonne_id,))
                    action = "Modification"
                else:
                    # Création d'un nouvel abonné
                    cur.execute("""
                        INSERT INTO abonne (
                            numero_client, numero_carte, nom, postnom, prenom, sexe, 
                            date_naissance, lieu_naissance, adresse, telephone, 
                            suppleant, contact_suppleant, type_compte, montant, 
                            photo, date_inscription, solde, duree_blocage,
                            montant_atteindre, pourcentage_retrait, frequence_retrait, 
                            date_derniere_operation, statut
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, values)
                    action = "Inscription"
                
                conn.commit()
                
                # Journalisation
                ajouter_journal(action, self.nom_agent, 
                              f"Abonné: {self.data['nom'].get()} {self.data['prenom'].get()}")
                
                messagebox.showinfo("Succès", "Opération enregistrée avec succès!")
                self.afficher_donnees()
                self.reinitialiser_formulaire()

        except sqlite3.IntegrityError as e:
            messagebox.showerror("Erreur", f"Violation de contrainte: {str(e)}")
        except sqlite3.OperationalError as e:
            messagebox.showerror("Erreur Base de Données", 
                                f"Impossible d'accéder à la base centrale:\n{str(e)}\n"
                                f"Chemin DB: {get_db_path()}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur système: {str(e)}")

    def afficher_donnees(self):
        """Affiche la liste des abonnés"""
        # Effacer les données précédentes
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        try:
            with connexion_db() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, nom, postnom, prenom, telephone, type_compte, solde, statut
                    FROM abonne
                    ORDER BY date_inscription DESC
                """)
                
                for row in cur.fetchall():
                    nom_complet = f"{row['prenom']} {row['postnom']} {row['nom']}" if row['postnom'] else f"{row['prenom']} {row['nom']}"
                    solde = f"{int(row['solde']):,} FC" if row['solde'] else "0 FC"
                    
                    self.tree.insert("", "end", values=(
                        row['id'],
                        nom_complet,
                        row['telephone'],
                        row['type_compte'],
                        solde,
                        row['statut']
                    ))
        
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Erreur de base de données: {str(e)}")

    def on_abonne_select(self, event):
        """Remplit le formulaire avec les données de l'abonné sélectionné"""
        selected = self.tree.focus()
        if not selected:
            return
            
        abonne_id = self.tree.item(selected, "values")[0]
        self.current_abonne_id = int(abonne_id)
        
        try:
            with connexion_db() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT * FROM abonne WHERE id = ?", (abonne_id,))
                abonne = cur.fetchone()
                
                if abonne:
                    for key in self.data:
                        if key in abonne.keys():
                            self.data[key].set(abonne[key])
                    self.display_photo(abonne['photo'] or "")
        
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Erreur de base de données: {str(e)}")

    def rechercher_abonne(self):
        """Recherche des abonnés par nom ou téléphone"""
        search_term = self.search_var.get().strip().lower()
        if not search_term:
            self.afficher_donnees()
            return
        
        # Effacer les données précédentes
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        try:
            with connexion_db() as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("""
                    SELECT id, nom, postnom, prenom, telephone, type_compte, solde, statut
                    FROM abonne
                    WHERE LOWER(nom) LIKE ? OR LOWER(prenom) LIKE ? OR telephone LIKE ?
                    ORDER BY date_inscription DESC
                """, (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%"))
                
                found = False
                for row in cur.fetchall():
                    found = True
                    nom_complet = f"{row['prenom']} {row['postnom']} {row['nom']}" if row['postnom'] else f"{row['prenom']} {row['nom']}"
                    solde = f"{int(row['solde']):,} FC" if row['solde'] else "0 FC"
                    
                    self.tree.insert("", "end", values=(
                        row['id'],
                        nom_complet,
                        row['telephone'],
                        row['type_compte'],
                        solde,
                        row['statut']
                    ))
                
                if not found:
                    self.tree.insert("", "end", values=("", "Aucun résultat trouvé", "", "", "", ""))
        
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Erreur de base de données: {str(e)}")

    def modifier_abonne(self):
        """Active le mode modification pour l'abonné sélectionné"""
        if not self.current_abonne_id:
            messagebox.showwarning("Avertissement", "Veuillez sélectionner un abonné à modifier")
            return
        self.enregistrer()

    def supprimer_abonne(self):
        """Supprime l'abonné sélectionné"""
        if not self.current_abonne_id:
            messagebox.showwarning("Avertissement", "Veuillez sélectionner un abonné à supprimer")
            return
            
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cet abonné?"):
            return
        
        try:
            with connexion_db() as conn:
                cur = conn.cursor()
                
                # Récupérer le nom avant suppression
                cur.execute("SELECT nom, prenom FROM abonne WHERE id = ?", (self.current_abonne_id,))
                abonne = cur.fetchone()
                
                # Supprimer l'abonné
                cur.execute("DELETE FROM abonne WHERE id = ?", (self.current_abonne_id,))
                conn.commit()
                
                if abonne:
                    ajouter_journal("Suppression", self.nom_agent, 
                                   f"Abonné supprimé: {abonne[0]} {abonne[1]}")
                
                self.afficher_donnees()
                self.reinitialiser_formulaire()
                messagebox.showinfo("Succès", "Abonné supprimé avec succès")
        
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Erreur de base de données: {str(e)}")

    def reinitialiser_formulaire(self):
        """Réinitialise le formulaire"""
        self.current_abonne_id = None
        self.data["numero_client"].set(generer_numero_client_unique())
        self.data["numero_carte"].set(generer_numero_carte_unique())
        for key in self.data:
            if key not in ("numero_client", "numero_carte", "type_compte"):
                self.data[key].set("")
        self.data["type_compte"].set("Fixe")
        self.display_photo("")
        self.tree.selection_remove(self.tree.selection())

    def rapport_global(self):
        """Affiche un rapport statistique"""
        try:
            with connexion_db() as conn:
                cur = conn.cursor()
                
                # Nombre total d'abonnés
                cur.execute("SELECT COUNT(*) FROM abonne")
                total = cur.fetchone()[0]
                
                # Nombre d'abonnés par type de compte
                cur.execute("SELECT type_compte, COUNT(*) FROM abonne GROUP BY type_compte")
                par_type = cur.fetchall()
                
                # Total des soldes
                cur.execute("SELECT SUM(solde) FROM abonne")
                total_soldes = cur.fetchone()[0] or 0
                
                # Rapport
                report = f"RAPPORT GLOBAL - {datetime.date.today()}\n\n"
                report += f"Total abonnés: {total}\n"
                report += f"Total soldes: {int(total_soldes):,} FC\n\n"
                report += "Répartition par type de compte:\n"
                for type_compte, count in par_type:
                    report += f"- {type_compte}: {count} abonnés ({count/total*100:.1f}%)\n"
                
                # Afficher dans une nouvelle fenêtre
                report_win = tk.Toplevel(self.parent)
                report_win.title("Rapport Statistique")
                report_win.geometry("500x400")
                
                text_area = scrolledtext.ScrolledText(report_win, wrap=tk.WORD)
                text_area.pack(fill='both', expand=True, padx=10, pady=10)
                text_area.insert(tk.INSERT, report)
                text_area.configure(state='disabled')
                
                btn_frame = tk.Frame(report_win)
                btn_frame.pack(fill='x', padx=10, pady=10)
                
                ttk.Button(btn_frame, text="Exporter", 
                          command=lambda: self.exporter_texte(report, "rapport_abonnes.txt")).pack(side='left')
                ttk.Button(btn_frame, text="Fermer", command=report_win.destroy).pack(side='right')
        
        except sqlite3.Error as e:
            messagebox.showerror("Erreur", f"Erreur de base de données: {str(e)}")

    def exporter_donnees(self):
        """Exporte les données des abonnés au format CSV"""
        try:
            with connexion_db() as conn:
                cur = conn.cursor()
                cur.execute("""
                    SELECT numero_client, numero_carte, nom, postnom, prenom, sexe, date_naissance,
                           lieu_naissance, adresse, telephone, suppleant, contact_suppleant,
                           type_compte, montant, solde, statut, date_inscription
                    FROM abonne
                    ORDER BY date_inscription DESC
                """)
                
                # Créer le contenu CSV
                csv_content = "Numéro Client;Numéro Carte;Nom;Postnom;Prénom;Sexe;Date Naissance;" \
                              "Lieu Naissance;Adresse;Téléphone;Suppléant;Contact Suppl;Type Compte;" \
                              "Montant;Solde;Statut;Date Inscription\n"
                
                for row in cur.fetchall():
                    csv_content += ";".join(str(value) if value is not None else "" for value in row) + "\n"
                
                # Demander où sauvegarder
                file_path = filedialog.asksaveasfilename(
                    defaultextension=".csv",
                    filetypes=[("Fichiers CSV", "*.csv")],
                    title="Enregistrer les données"
                )
                
                if file_path:
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(csv_content)
                    messagebox.showinfo("Succès", f"Données exportées avec succès:\n{file_path}")
                
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'exportation: {str(e)}")

    def exporter_texte(self, contenu, nom_fichier):
        """Exporte du texte dans un fichier"""
        try:
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                initialfile=nom_fichier,
                filetypes=[("Fichiers texte", "*.txt")]
            )
            
            if file_path:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(contenu)
                messagebox.showinfo("Succès", f"Fichier enregistré:\n{file_path}")
                
                # Ouvrir le fichier
                if sys.platform == "win32":
                    os.startfile(file_path)
                elif sys.platform == "darwin":
                    subprocess.call(["open", file_path])
                else:
                    subprocess.call(["xdg-open", file_path])
                    
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'exportation: {str(e)}")

    def __del__(self):
        if hasattr(self, 'webcam'):
            self.webcam.stop_capture()

# ==================== LANCEMENT DE L'APPLICATION ====================

if __name__ == "__main__":
    # Vérification de la base de données au démarrage
    db_path = get_db_path()
    print(f"Chemin de la base de données: {db_path}")
    
    if not os.path.exists(db_path):
        print("Création d'une nouvelle base de données...")
        with sqlite3.connect(db_path) as conn:
            pass
    
    app = InscriptionInterface()
    app.parent.mainloop()