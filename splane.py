import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkcalendar import DateEntry
import datetime
import time
import os
import sys
import hashlib
import shutil
import random
import sqlite3
from PIL import Image, ImageTk
import tempfile
from fpdf import FPDF
import subprocess
import webbrowser
import traceback
from interface_retrait import interface_retrait
from fenetre_depot import FenetreDepot
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from typing import Optional

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError as e:
    print(f"Warning: OpenCV not available - {e}")
    CV2_AVAILABLE = False
    cv2 = None
    np = None
import tempfile
from fpdf import FPDF
import subprocess
import webbrowser
import traceback
import logging
from typing import Optional

# Configuration du logging
logging.basicConfig(
    filename='app.log',
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filemode='a'
)

logger = logging.getLogger(__name__)

# Import des modules de la base de données
from db import (
    connexion_db, initialiser_base, ajouter_journal, generer_numero_client_unique,
    generer_numero_carte_unique, hash_password, get_db_path
)

# --- Styles et couleurs ---
PRIMARY_COLOR = "#128C7E"  # Vert WhatsApp
SECONDARY_COLOR = "#075E54"  # Vert WhatsApp foncé
BACKGROUND_COLOR = "#F0F2F5"  # Fond gris clair
CARD_COLOR = "#FFFFFF"  # Blanc
TEXT_COLOR = "#333333"
ACCENT_COLOR = "#25D366"  # Vert vif WhatsApp
BUTTON_COLOR = "#128C7E"
BUTTON_HOVER = "#075E54"
ERROR_COLOR = "#FF5252"

class WebcamCapture:
    def __init__(self):
        self.cap = None
        self.current_camera_index = 0
        self.camera_list = []
        
    def detect_cameras(self):
        """Détecte les caméras disponibles"""
        if not CV2_AVAILABLE:
            return []  # Retourne une liste vide si OpenCV n'est pas installé
            
        index = 0
        arr = []
        for i in range(0, 4):  # Vérifie les 4 premiers indices
            try:
                cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
                if cap is not None and cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        arr.append(i)
                    cap.release()
            except Exception as e:
                print(f"Erreur caméra {i}: {str(e)}")
                continue
        self.camera_list = arr
        return arr
    
    def start_capture(self, index=0):
        """Démarre la capture vidéo"""
        if not CV2_AVAILABLE:
            return False
            
        if self.cap is not None:
            self.stop_capture()
            
        if index >= len(self.camera_list):
            return False
            
        self.current_camera_index = index
        try:
            self.cap = cv2.VideoCapture(self.camera_list[index], cv2.CAP_DSHOW)
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                return True
        except Exception as e:
            print(f"Erreur démarrage capture: {str(e)}")
        return False
    
    def get_frame(self):
        """Capture une frame de la webcam"""
        if not CV2_AVAILABLE:
            return None
            
        if self.cap is None or not self.cap.isOpened():
            return None
            
        try:
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                return frame
        except Exception as e:
            print(f"Erreur capture frame: {str(e)}")
        return None
    
    def stop_capture(self):
        """Arrête la capture vidéo"""
        if not CV2_AVAILABLE:
            return
            
        if self.cap is not None:
            try:
                if self.cap.isOpened():
                    self.cap.release()
            except:
                pass
            self.cap = None
    
    def switch_camera(self):
        """Change de caméra"""
        if not CV2_AVAILABLE:
            return False
            
        if not self.camera_list:
            return False
            
        new_index = (self.current_camera_index + 1) % len(self.camera_list)
        return self.start_capture(new_index)
    
    def __del__(self):
        """Nettoyage à la destruction de l'objet"""
        self.stop_capture()

class FenetreDepot:
    """Fenêtre simplifiée pour les dépôts (implémentation minimale)"""
    def __init__(self, parent, nom_agent):
        self.parent = parent
        self.nom_agent = nom_agent
        self.window = tk.Toplevel(parent)
        self.window.title("Interface de Dépôt")
        self.window.geometry("400x300")
        tk.Label(self.window, text=f"Interface de dépôt pour {nom_agent}").pack(pady=20)

def interface_retrait(nom_agent):
    """Interface simplifiée pour les retraits (implémentation minimale)"""
    win = tk.Toplevel()
    win.title("Interface de Retrait")
    win.geometry("400x300")
    tk.Label(win, text=f"Interface de retrait pour {nom_agent}").pack(pady=20)

def initialiser_pages_compte_fixe(numero_carte):
    """Initialise les pages pour un compte fixe"""
    logger.debug(f"Tentative d'initialisation des pages pour {numero_carte}")
    conn = None
    try:
        conn = connexion_db()
        cur = conn.cursor()
        
        # Vérifier que le compte fixe existe
        cur.execute("SELECT COUNT(*) FROM compte_fixe WHERE numero_carte = ?", (numero_carte,))
        if cur.fetchone()[0] == 0:
            logger.error(f"Aucun compte fixe trouvé pour la carte {numero_carte}")
            return False
            
        # Vérifier si les pages existent déjà
        cur.execute("SELECT COUNT(*) FROM compte_fixe_pages WHERE numero_carte = ?", (numero_carte,))
        if cur.fetchone()[0] > 0:
            logger.warning(f"Pages déjà existantes pour {numero_carte}")
            return False
            
        # Initialiser les 8 pages
        for page in range(1, 9):
            cur.execute("""
                INSERT INTO compte_fixe_pages (numero_carte, page, cases_remplies)
                VALUES (?, ?, 0)
            """, (numero_carte, page))
            
        conn.commit()
        logger.info(f"Pages initialisées avec succès pour {numero_carte}")
        return True
        
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation des pages pour {numero_carte}: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        return False
    finally:
        if conn:
            conn.close()

class InscriptionInterface:
    def __init__(self, parent=None, nom_agent="Administrateur"):
        self.logger = logging.getLogger('interface')
        if parent is None:
            self.parent = tk.Tk()
            self.parent.title("SERVICE CENTRAL D'EPARGNE - Mode Autonome")
            self.parent.state('zoomed')
            self.parent.geometry("1200x800+100+100")
        else:
            self.parent = parent
            self.parent.title("SERVICE CENTRAL D'EPARGNE - Mode Intégré")
            if parent.winfo_x() > 0:
                self.parent.geometry(f"+{parent.winfo_x()+50}+{parent.winfo_y()+50}")
        
        self.nom_agent = nom_agent
        self.container = tk.Frame(self.parent, bg=BACKGROUND_COLOR)
        self.container.pack(fill='both', expand=True)
        
        initialiser_base()
        self.global_photo_ref = None
        self.photo_references = []
        self.webcam = WebcamCapture()
        
        self.setup_styles()
        self.create_header()
        self.create_main_frame()
        self.create_form()
        self.create_abonne_list()
        self.afficher_donnees()
        
    def setup_styles(self):
        """Configure les styles pour l'application"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Style des boutons
        style.configure('TButton', 
                       background=BUTTON_COLOR, 
                       foreground='white',
                       font=('Helvetica', 10, 'bold'),
                       borderwidth=1,
                       focusthickness=3,
                       focuscolor='none')
        style.map('TButton', 
                 background=[('active', BUTTON_HOVER), ('pressed', SECONDARY_COLOR)])
        
        # Style des labels
        style.configure('TLabel', background=BACKGROUND_COLOR, foreground=TEXT_COLOR)
        
        # Style des entrées
        style.configure('TEntry', fieldbackground='white', foreground=TEXT_COLOR)
        
        # Style des cadres
        style.configure('Card.TFrame', background=CARD_COLOR, relief='solid', borderwidth=1)
        
    def ouvrir_interface_depot(self):
        """Ouvre l'interface de dépôt"""
        if not hasattr(self, 'nom_agent') or not self.nom_agent:
            self.nom_agent = "Agent_" + datetime.datetime.now().strftime("%Y%m%d_%H%M")
            print(f"Avertissement: Utilisation du nom d'agent par défaut: {self.nom_agent}")
        
        FenetreDepot(self.parent, self.nom_agent)
        
    def create_header(self):
        """Crée l'en-tête de l'application"""
        header = tk.Frame(self.container, bg=PRIMARY_COLOR, height=60)
        header.pack(fill='x', padx=0, pady=0)
        
        title = tk.Label(header, 
                        text="ENREGISTREMENT DES ABONNÉS", 
                        bg=PRIMARY_COLOR, 
                        fg='white', 
                        font=('Helvetica', 18, 'bold'))
        title.pack(side='left', padx=20, pady=15)
        
        # Boutons d'action rapide
        btn_frame = tk.Frame(header, bg=PRIMARY_COLOR)
        btn_frame.pack(side='right', padx=25)
        
        actions = [
            ("💸 Retrait", self.ouvrir_interface_retrait),
            ("📊 Status", self.rapport_global),
            ("📁 Répertoire", self.afficher_repertoire),
            ("❌ Fermer", self.parent.destroy)
        ]
        
        for text, cmd in actions:
            btn = ttk.Button(btn_frame, text=text, command=cmd, width=15)
            btn.pack(side='left', padx=5)
    
    def ouvrir_interface_retrait(self):
        """Ouvre l'interface de retrait"""
        interface_retrait(self.nom_agent)
    
    def create_main_frame(self):
        """Crée le cadre principal avec une répartition 60/40"""
        self.main_frame = tk.Frame(self.container, bg=BACKGROUND_COLOR)
        self.main_frame.pack(fill='both', expand=True, padx=20, pady=20)
    
        # Diviser en formulaire (60%) et liste (40%)
        self.form_container = tk.Frame(self.main_frame, bg=BACKGROUND_COLOR)
        self.form_container.pack(side='left', fill='both', expand=True, padx=(0, 10))
    
        self.list_container = tk.Frame(self.main_frame, bg=BACKGROUND_COLOR)
        self.list_container.pack(side='right', fill='y')  # plus de expand=True

    def create_form(self):
        """Crée le formulaire d'inscription élargi (60%)"""
        form_scroll_frame = tk.Frame(self.form_container, bg=BACKGROUND_COLOR)
        form_scroll_frame.pack(fill='both', expand=True)
        form_scroll_frame.update_idletasks()
        form_scroll_frame.config(height=600)
    
        canvas = tk.Canvas(form_scroll_frame, bg=BACKGROUND_COLOR, highlightthickness=0)
        scrollbar = ttk.Scrollbar(form_scroll_frame, orient='vertical', command=canvas.yview)
        self.scrollable_form = tk.Frame(canvas, bg=BACKGROUND_COLOR)
    
        self.scrollable_form.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.scrollable_form, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
    
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
    
        form_card = ttk.Frame(self.scrollable_form, style='Card.TFrame', padding=20)
        form_card.pack(fill='x', pady=(0, 20))
    
        form_title = tk.Label(form_card, 
                        text="INTERFACE D'OUVERTURE COMPTE EPARGNE",
                        justify="center", 
                        font=('Helvetica', 13, 'bold'),
                        bg=CARD_COLOR,
                        fg=PRIMARY_COLOR)
        form_title.pack(anchor='w', pady=(0, 20))
    
        # Variables pour les champs
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
    
        # Photo de profil agrandie
        photo_frame = tk.Frame(form_card, bg=CARD_COLOR)
        photo_frame.pack(fill='x', pady=15)
    
        self.photo_label = tk.Label(photo_frame, bg='white', width=190, height=200,
                              relief='sunken', cursor='hand2')
        self.photo_label.pack()
        self.photo_label.bind("<Button-1>", lambda e: self.select_photo())
        self.display_photo("")
    
        # Boutons photo
        photo_btns = tk.Frame(photo_frame, bg=CARD_COLOR)
        photo_btns.pack(pady=15)
    
        ttk.Button(photo_btns, text="Sélectionner", command=self.select_photo, width=15).pack(side='left', padx=10)
        ttk.Button(photo_btns, text="Prendre photo", command=self.lancer_interface_capture, width=15).pack(side='left', padx=10)
    
        # Champs du formulaire avec taille augmentée
        fields = [
            ("Numéro client*", "numero_client", False),
            ("Numéro carte*", "numero_carte", False),
            ("Nom*", "nom", False),
            ("Postnom*", "postnom", False),
            ("Prénom*", "prenom", False),
            ("Sexe*", "sexe", True, ["M", "F"]),
            ("Date naissance*", "date_naissance", False, 'date'),
            ("Lieu naissance*", "lieu_naissance", False),
            ("Adresse*", "adresse", False),
            ("Téléphone*", "telephone", False),
            ("Suppléant", "suppleant", False),
            ("Contact suppléant", "contact_suppleant", False),
            ("Type de compte*", "type_compte", True, ["Fixe", "Mixte", "Bloqué"]),
            ("Montant*", "montant", False),
            ("Durée blocage", "duree_blocage", True, ["3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "24"]),
            ("Montant à atteindre", "montant_atteindre", False),
            ("Pourcentage retrait", "pourcentage_retrait", True, ["10", "20", "30", "40", "50"]),
            ("Fréquence retrait", "frequence_retrait", True, ["Mensuel", "Trimestriel", "Semestriel", "Annuel"])
        ]
    
        self.conditional_fields = {}
    
        for field in fields:
            frame = tk.Frame(form_card, bg=CARD_COLOR, height=40)
            frame.pack(fill='x', pady=5)
            frame.pack_propagate(False)  # Important pour forcer la hauteur

            self.conditional_fields[field[1]] = frame
            
            label = tk.Label(frame, 
                           text=field[0], 
                           bg=CARD_COLOR,
                           fg=TEXT_COLOR,
                           width=20,
                           anchor='w',
                           font=('Helvetica', 11))  # Police agrandie
            label.pack(side='left', padx=(0, 15))
            
            key = field[1]
            if field[2]:  # Combobox
                values = field[3] if len(field) > 3 else []
                combobox = ttk.Combobox(frame, 
                                      textvariable=self.data[key], 
                                      values=values,
                                      width=28,  # Largeur augmentée
                                      font=('Helvetica', 11),  # Police agrandie
                                      state='readonly')
                combobox.pack(side='left', fill='x', expand=True)
            elif len(field) > 3 and field[3] == 'date':  # DateEntry
                date_entry = DateEntry(frame, 
                                     textvariable=self.data[key], 
                                     locale='fr_FR', 
                                     date_pattern='yyyy-mm-dd',
                                     width=10,  # Largeur augmentée
                                     font=('Helvetica', 11))  # Police agrandie
                date_entry.pack(side='left', fill='x', expand=True)
            else:  # Champ texte
                entry = ttk.Entry(frame, 
                                textvariable=self.data[key], 
                                width=33,  # Largeur augmentée
                                font=('Helvetica', 11))  # Police agrandie
                entry.pack(side='left', fill='x', expand=True)
    
        self.data["type_compte"].trace_add('write', self.on_type_compte_change)
        self.on_type_compte_change()  # Appliquer l'état initial
    
        # Boutons d'action
        btn_frame = tk.Frame(form_card, bg=CARD_COLOR)
        btn_frame.pack(fill='x', pady=20)
    
        actions = [
            ("Enregistrer", self.enregistrer),
            ("Réinitialiser", self.reinitialiser_formulaire),
            ("Dépôt", self.ouvrir_interface_depot),
        ]
    
        for text, cmd in actions:
            btn = ttk.Button(btn_frame, 
                        text=text, 
                        command=cmd, 
                        width=18)
            btn.pack(side='left', padx=10, fill='x', expand=True)

    def on_type_compte_change(self, *args):
        """Gère l'affichage des champs selon le type de compte"""
        type_compte = self.data["type_compte"].get()
        
        if type_compte == "Bloqué":
            self.conditional_fields["duree_blocage"].pack(fill='x', pady=8)
            self.conditional_fields["montant_atteindre"].pack(fill='x', pady=8)
            self.conditional_fields["pourcentage_retrait"].pack(fill='x', pady=8)
            self.conditional_fields["frequence_retrait"].pack(fill='x', pady=8)
        else:
            self.conditional_fields["duree_blocage"].pack_forget()
            self.conditional_fields["montant_atteindre"].pack_forget()
            self.conditional_fields["pourcentage_retrait"].pack_forget()
            self.conditional_fields["frequence_retrait"].pack_forget()

    def create_abonne_list(self):
        """Crée la liste des abonnés avec une scrollbar ajustée"""
        list_card = ttk.Frame(self.list_container, style='Card.TFrame')
        list_card.pack(fill='both', expand=True, padx=(0, 2))
        
        header_frame = tk.Frame(list_card, bg=CARD_COLOR)
        header_frame.pack(fill='x', padx=5, pady=5)
        
        tk.Label(header_frame, 
               text="LISTE DES ABONNÉS", 
               font=('Helvetica', 14, 'bold'),
               bg=CARD_COLOR,
               fg=PRIMARY_COLOR).pack(side='left')
        
        # Boutons de filtrage par statut
        filter_frame = tk.Frame(header_frame, bg=CARD_COLOR)
        filter_frame.pack(side='left', padx=20)
        
        self.filtre_statut = tk.StringVar(value="Tous")
        
        ttk.Button(filter_frame, 
                  text="Tous", 
                  command=lambda: self.filtrer_abonnes(None),
                  width=10).pack(side='left', padx=5)
        
        ttk.Button(filter_frame, 
                  text="Actifs", 
                  command=lambda: self.filtrer_abonnes("Actif"),
                  width=10).pack(side='left', padx=5)
        
        ttk.Button(filter_frame, 
                  text="Inactifs", 
                  command=lambda: self.filtrer_abonnes("Inactif"),
                  width=10).pack(side='left', padx=5)
        
        search_frame = tk.Frame(header_frame, bg=CARD_COLOR)
        search_frame.pack(side='right')
        
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, 
                               textvariable=self.search_var, 
                               width=20)
        search_entry.pack(side='left', padx=5)
        search_entry.bind('<KeyRelease>', lambda e: self.rechercher_abonne())
        
        ttk.Button(search_frame, 
                  text="Rechercher", 
                  command=self.rechercher_abonne,
                  width=10).pack(side='left')
        
        list_frame = tk.Frame(list_card, bg=BACKGROUND_COLOR)
        list_frame.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        canvas = tk.Canvas(list_frame, bg=BACKGROUND_COLOR, highlightthickness=0)
        scrollbar = tk.Scrollbar(list_frame, orient='vertical', command=canvas.yview, width=10)
        self.scrollable_frame = tk.Frame(canvas, bg=BACKGROUND_COLOR)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        canvas.create_window((0, 0), window=self.scrollable_frame, anchor='nw')
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Initialisation du filtre
        self.current_filter = None

    def filtrer_abonnes(self, statut):
        """Filtre les abonnés par statut (Actif/Inactif)"""
        self.current_filter = statut
        self.afficher_donnees()

    def display_photo(self, path):
        """Affiche une photo dans le formulaire"""
        try:
            if path and os.path.exists(path):
                img = Image.open(path)
                img = img.resize((200, 240), Image.LANCZOS)  # Taille agrandie
                photo = ImageTk.PhotoImage(img)
                
                self.global_photo_ref = photo
                
                self.photo_label.config(image=photo)
            else:
                # Créer une image vide plus grande
                img = Image.new('RGB', (200, 240), color='#E0E0E0')
                photo = ImageTk.PhotoImage(img)
                
                self.global_photo_ref = photo
                
                self.photo_label.config(image=photo)
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible de charger l'image: {str(e)}")
    
    def select_photo(self):
        """Sélectionne une photo depuis le système de fichiers"""
        file_path = filedialog.askopenfilename(
            filetypes=[("Images", "*.jpg *.jpeg *.png")]
        )
        if file_path:
            self.data["photo"].set(file_path)
            self.display_photo(file_path)
    
    def lancer_interface_capture(self):
        """Lance l'interface de capture indépendante"""
        # Vérifier si OpenCV est disponible
        if not CV2_AVAILABLE:
            messagebox.showwarning("Fonction désactivée", 
                                  "OpenCV n'est pas installé. La capture caméra est désactivée.")
            return
            
        # Détecter les caméras disponibles
        cameras = self.webcam.detect_cameras()
        if not cameras:
            messagebox.showerror("Erreur", "Aucune webcam détectée")
            return
            
        # Démarrer la capture
        if not self.webcam.start_capture():
            messagebox.showerror("Erreur", "Impossible de démarrer la webcam")
            return
            
        # Créer la fenêtre de capture
        capture_win = tk.Toplevel()
        capture_win.title("Capture de Photo")
        capture_win.geometry("640x520")
        capture_win.resizable(False, False)
        
        # Positionner la fenêtre
        x = self.parent.winfo_x() + 100
        y = self.parent.winfo_y() + 100
        capture_win.geometry(f"+{x}+{y}")
        
        capture_frame = tk.Frame(capture_win)
        capture_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        video_label = tk.Label(capture_frame)
        video_label.pack(fill='both', expand=True)
        
        btn_frame = tk.Frame(capture_frame)
        btn_frame.pack(fill='x', pady=10)
        
        btn_capture = ttk.Button(btn_frame, text="Capturer (Espace/Entrée)", 
                               command=lambda: self.capture_image(capture_win),
                               width=20)
        btn_capture.pack(side='left', padx=5)
        
        btn_switch = ttk.Button(btn_frame, text="Changer caméra", 
                              command=self.webcam.switch_camera,
                              width=15)
        btn_switch.pack(side='left', padx=5)
        
        # Liaisons clavier
        capture_win.bind('<Return>', lambda e: self.capture_image(capture_win))
        capture_win.bind('<space>', lambda e: self.capture_image(capture_win))
        capture_win.focus_force()
        
        def update_video():
            """Mise à jour de l'image vidéo"""
            frame = self.webcam.get_frame()
            if frame is not None:
                try:
                    img = Image.fromarray(frame)
                    img = img.resize((640, 480), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    video_label.config(image=photo)
                    video_label.image = photo
                    capture_win.after(10, update_video)
                except Exception as e:
                    print(f"Erreur mise à jour vidéo: {str(e)}")
                    capture_win.after(100, update_video)
            else:
                capture_win.after(100, update_video)
        
        update_video()
        
        def on_close():
            """Gestion de la fermeture de la fenêtre"""
            self.webcam.stop_capture()
            capture_win.destroy()
        
        capture_win.protocol("WM_DELETE_WINDOW", on_close)
        
    def switch_camera(self):
        """Change de caméra"""
        if self.webcam.switch_camera():
            messagebox.showinfo("Succès", "Caméra changée avec succès")
        else:
            messagebox.showerror("Erreur", "Impossible de changer de caméra")
    
    def capture_image(self, window):
        """Capture une image depuis la webcam"""
        frame = self.webcam.get_frame()
        if frame is None:
            messagebox.showerror("Erreur", "Impossible de capturer l'image")
            return
            
        try:
            img = Image.fromarray(frame)
            
            chemin_db = get_db_path()
            photos_dir = os.path.join(os.path.dirname(chemin_db), "photos")
            os.makedirs(photos_dir, exist_ok=True)
            
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = os.path.join(photos_dir, f"photo_{timestamp}.jpg")
            
            img.save(file_path)
            self.data["photo"].set(file_path)
            self.display_photo(file_path)
            self.webcam.stop_capture()
            
            window.destroy()
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur sauvegarde photo: {str(e)}")

    def validate_fields(self):
        """Valide les champs obligatoires"""
        required_fields = [
            "nom", "postnom", "prenom", "date_naissance", 
            "lieu_naissance", "adresse", "telephone", 
            "type_compte"
        ]
        
        type_compte = self.data["type_compte"].get()
        if type_compte in ("Fixe", "Bloqué"):
            required_fields.append("montant")
        
        for field in required_fields:
            if not self.data[field].get().strip():
                messagebox.showerror("Erreur", f"Le champ {field.replace('_', ' ')} est obligatoire!")
                return False
        
        phone = self.data["telephone"].get()
        if len(phone) != 10 or not phone.isdigit():
            messagebox.showerror("Erreur", "Le numéro de téléphone doit contenir 10 chiffres")
            return False
        
        return True
    
    def afficher_donnees(self):
        """Affiche la liste des abonnés avec filtrage"""
        if not hasattr(self, 'scrollable_frame'):
            self.create_abonne_list()
        
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        conn = None
        try:
            conn = connexion_db()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Requête avec filtrage par statut si nécessaire
            query = """
                SELECT id, numero_client, nom, postnom, prenom, telephone, 
                       date_inscription, type_compte, photo, solde, statut,
                       date_derniere_operation
                FROM abonne
            """
            
            params = ()
            
            if self.current_filter:
                query += " WHERE statut = ?"
                params = (self.current_filter,)
            
            query += " ORDER BY date_inscription DESC"
            
            cur.execute(query, params)
            
            for row in cur.fetchall():
                abonne_id = row['id']
                numero_client = row['numero_client']
                nom = row['nom']
                postnom = row['postnom']
                prenom = row['prenom']
                telephone = row['telephone']
                date_inscription = row['date_inscription']
                type_compte = row['type_compte']
                photo_path = row['photo']
                solde = row['solde']
                statut = row['statut']
                date_derniere_operation = row['date_derniere_operation']
                
                card = tk.Frame(self.scrollable_frame, 
                              bg=CARD_COLOR, 
                              bd=1, 
                              relief='solid', 
                              padx=10, 
                              pady=10)
                card.pack(fill='x', padx=5, pady=5, ipadx=5, ipady=5)
                
                photo_frame = tk.Frame(card, bg=CARD_COLOR)
                photo_frame.pack(side='left', padx=(0, 10))
                
                if photo_path and os.path.exists(photo_path):
                    try:
                        img = Image.open(photo_path)
                        img = img.resize((60, 60), Image.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        self.photo_references.append(photo)
                        photo_label = tk.Label(photo_frame, image=photo, bg=CARD_COLOR)
                        photo_label.image = photo
                        photo_label.pack()
                    except Exception as e:
                        print(f"Erreur chargement photo: {e}")
                        tk.Label(photo_frame, text="👤", font=("Arial", 24), bg=CARD_COLOR).pack()
                else:
                    tk.Label(photo_frame, text="👤", font=("Arial", 24), bg=CARD_COLOR).pack()
                
                info_frame = tk.Frame(card, bg=CARD_COLOR)
                info_frame.pack(side='left', fill='x', expand=True)
                
                nom_complet = f"{nom} {postnom} {prenom}" if postnom else f"{nom} {prenom}"
                tk.Label(info_frame, 
                        text=nom_complet, 
                        font=("Helvetica", 12, "bold"), 
                        bg=CARD_COLOR, 
                        anchor="w").pack(anchor="w")
                
                tk.Label(info_frame, 
                        text=f"📱 {telephone}", 
                        bg=CARD_COLOR, 
                        anchor="w").pack(anchor="w")
                
                type_color = {
                    "Fixe": "green",
                    "Mixte": "blue",
                    "Bloqué": "red"
                }.get(type_compte, "black")
                
                solde_int = int(solde) if solde else 0
                solde_text = f"💰 {solde_int} FC ({type_compte})" if solde else f"Type: {type_compte}"
                tk.Label(info_frame, 
                        text=solde_text, 
                        fg=type_color, 
                        bg=CARD_COLOR, 
                        anchor="w").pack(anchor="w")
                
                # Affichage du statut
                statut_color = "green" if statut == "Actif" else "red"
                statut_text = f"Statut: {statut}"
                
                if statut == "Actif" and date_derniere_operation:
                    try:
                        date_derniere = datetime.datetime.strptime(date_derniere_operation, "%Y-%m-%d").strftime("%d/%m/%Y")
                        statut_text = f"Actif depuis {date_derniere}"
                    except:
                        statut_text = f"Statut: {statut}"
                
                elif statut == "Inactif" and date_derniere_operation:
                    try:
                        date_derniere = datetime.datetime.strptime(date_derniere_operation, "%Y-%m-%d")
                        jours_inactif = (datetime.datetime.now() - date_derniere).days
                        statut_text = f"Inactif depuis {jours_inactif} jours"
                    except:
                        statut_text = f"Statut: {statut}"
                
                tk.Label(info_frame, 
                        text=statut_text, 
                        fg=statut_color, 
                        bg=CARD_COLOR, 
                        anchor="w").pack(anchor="w")
                
                try:
                    date_str = str(date_inscription)
                    date_formatted = datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                except:
                    date_formatted = "Date inconnue"
                    
                tk.Label(info_frame, 
                        text=f"📅 Inscrit le: {date_formatted}", 
                        bg=CARD_COLOR, 
                        anchor="w").pack(anchor="w")
                
                btn_frame = tk.Frame(card, bg=CARD_COLOR)
                btn_frame.pack(side='right', padx=(10, 0))
                
                edit_btn = tk.Button(btn_frame, 
                                    text="✏️ Modifier", 
                                    font=("Arial", 10),
                                    command=lambda id=abonne_id: self.modifier_abonne_par_id(id),
                                    bd=0,
                                    bg="#e0e0e0",
                                    padx=5,
                                    cursor="hand2")
                edit_btn.pack(side='left', padx=2)
                
                profile_btn = tk.Button(btn_frame, 
                                    text="👤 Profil", 
                                    font=("Arial", 10),
                                    command=lambda id=abonne_id: self.afficher_profil(id),
                                    bd=0,
                                    bg="#e0e0e0",
                                    padx=5,
                                    cursor="hand2")
                profile_btn.pack(side='left', padx=2)
                
                delete_btn = tk.Button(btn_frame, 
                                      text="🗑️ Supprimer", 
                                      font=("Arial", 10),
                                      command=lambda id=abonne_id: self.supprimer_abonne_par_id(id),
                                      bd=0,
                                      bg="#e0e0e0",
                                      padx=5,
                                      cursor="hand2")
                delete_btn.pack(side='left', padx=2)
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du chargement des données: {str(e)}")
        finally:
            if conn:
                conn.close()

    def afficher_profil(self, abonne_id):
        """Affiche les détails d'un abonné dans une nouvelle fenêtre"""
        conn = None
        try:
            conn = connexion_db()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM abonne WHERE id=?", (abonne_id,))
            abonne = cur.fetchone()
            
            if not abonne:
                messagebox.showerror("Erreur", "Abonné introuvable")
                return
            
            # Récupérer les infos spécifiques au compte fixe si nécessaire
            type_compte = abonne['type_compte']
            infos_compte_fixe = None
            if type_compte == "Fixe":
                cur.execute("""
                    SELECT cf.montant_initial, cf.date_debut, cf.date_fin,
                           (SELECT COUNT(*) FROM compte_fixe_pages WHERE numero_carte = ? AND cases_remplies = 31) as pages_completes,
                           (SELECT SUM(cases_remplies) FROM compte_fixe_pages WHERE numero_carte = ?) as total_cases
                    FROM compte_fixe cf
                    WHERE cf.numero_carte = ?
                """, (abonne['numero_carte'], abonne['numero_carte'], abonne['numero_carte']))
                infos_compte_fixe = cur.fetchone()
            
            profile_win = tk.Toplevel()
            profile_win.title(f"Profil de l'abonné {abonne['nom']} {abonne['prenom']}")
            profile_win.geometry("600x700")
            profile_win.configure(bg=BACKGROUND_COLOR)
            
            profile_win.geometry(f"+{self.parent.winfo_x()+50}+{self.parent.winfo_y()+50}")
            
            main_frame = tk.Frame(profile_win, bg=BACKGROUND_COLOR, padx=20, pady=20)
            main_frame.pack(fill='both', expand=True)
            
            # Affichage de la photo de profil
            photo_frame = tk.Frame(main_frame, bg=BACKGROUND_COLOR)
            photo_frame.pack(pady=10)
            
            photo_path = abonne['photo'] if 'photo' in abonne and abonne['photo'] else ""
            if photo_path and os.path.exists(photo_path):
                try:
                    img = Image.open(photo_path)
                    img = img.resize((150, 180), Image.LANCZOS)
                    photo = ImageTk.PhotoImage(img)
                    self.photo_references.append(photo)  # Conservation de la référence
                    lbl_photo = tk.Label(photo_frame, image=photo, bg=BACKGROUND_COLOR)
                    lbl_photo.image = photo
                    lbl_photo.pack()
                except Exception as e:
                    print(f"Erreur chargement photo: {e}")
                    lbl_photo = tk.Label(photo_frame, text="👤", font=("Arial", 48), bg=BACKGROUND_COLOR)
                    lbl_photo.pack()
            else:
                lbl_photo = tk.Label(photo_frame, text="👤", font=("Arial", 48), bg=BACKGROUND_COLOR)
                lbl_photo.pack()
            
            info_frame = tk.Frame(main_frame, bg=CARD_COLOR, padx=15, pady=15)
            info_frame.pack(fill='x', pady=10)
            
            date_inscription_str = abonne['date_inscription']
            try:
                date_inscription = datetime.datetime.strptime(date_inscription_str, "%Y-%m-%d").date()
                date_formatted = date_inscription.strftime("%d/%m/%Y")
                
                # Calcul de la durée d'inscription
                aujourdhui = datetime.date.today()
                duree = aujourdhui - date_inscription
                duree_annees = duree.days // 365
                duree_mois = (duree.days % 365) // 30
                duree_jours = duree.days
                
                duree_texte = f"{duree_jours} jours"
                if duree_annees > 0:
                    duree_texte = f"{duree_annees} an(s) et {duree_mois} mois"
                elif duree_mois > 0:
                    duree_texte = f"{duree_mois} mois et {duree_jours % 30} jours"
            except:
                date_formatted = "Date inconnue"
                duree_texte = "Inconnue"
            
            solde = abonne['solde'] if 'solde' in abonne else 0
            
            duree_blocage = abonne['duree_blocage'] if 'duree_blocage' in abonne else 0
            duree_blocage_text = f"{duree_blocage} mois" if duree_blocage is not None and duree_blocage > 0 else "-"
            
            montant_atteindre = abonne['montant_atteindre'] if 'montant_atteindre' in abonne else 0
            pourcentage_retrait = abonne['pourcentage_retrait'] if 'pourcentage_retrait' in abonne else 0
            frequence_retrait = abonne['frequence_retrait'] if 'frequence_retrait' in abonne else ""
            
            # Informations de statut
            statut = abonne['statut'] if 'statut' in abonne else "Actif"
            date_derniere_operation = abonne['date_derniere_operation'] if 'date_derniere_operation' in abonne else ""
            
            statut_text = f"Statut: {statut}"
            if statut == "Actif" and date_derniere_operation:
                try:
                    date_derniere = datetime.datetime.strptime(date_derniere_operation, "%Y-%m-%d").strftime("%d/%m/%Y")
                    statut_text = f"Actif depuis {date_derniere}"
                except:
                    pass
            elif statut == "Inactif" and date_derniere_operation:
                try:
                    date_derniere = datetime.datetime.strptime(date_derniere_operation, "%Y-%m-%d")
                    jours_inactif = (datetime.datetime.now() - date_derniere).days
                    statut_text = f"Inactif depuis {jours_inactif} jours (dernière opération: {date_derniere.strftime('%d/%m/%Y')})"
                except:
                    pass
            
            labels = [
                ("Numéro client:", abonne['numero_client']),
                ("Numéro carte:", abonne['numero_carte']),
                ("Nom:", abonne['nom']),
                ("Postnom:", abonne['postnom']),
                ("Prénom:", abonne['prenom']),
                ("Sexe:", abonne['sexe']),
                ("Date de naissance:", abonne['date_naissance']),
                ("Lieu de naissance:", abonne['lieu_naissance']),
                ("Adresse:", abonne['adresse']),
                ("Téléphone:", abonne['telephone']),
                ("Supplétant:", abonne['suppleant'] or "-"),
                ("Contact suppléant:", abonne['contact_suppleant'] or "-"),
                ("Type de compte:", abonne['type_compte']),
                ("Montant initial:", f"{int(abonne['montant'])} FC" if 'montant' in abonne and abonne['montant'] else "-"),
                ("Durée blocage:", duree_blocage_text if abonne['type_compte'] == "Bloqué" else "-"),
                ("Date d'inscription:", date_formatted),
                ("Solde actuel:", f"{int(solde)} FC" if solde else "-"),
                ("Durée d'inscription:", duree_texte),
                ("Statut:", statut_text)
            ]
            
            if abonne['type_compte'] == "Bloqué":
                labels.extend([
                    ("Montant à atteindre:", f"{int(montant_atteindre)} FC" if montant_atteindre else "-"),
                    ("Pourcentage retrait:", f"{pourcentage_retrait}%" if pourcentage_retrait else "-"),
                    ("Fréquence retrait:", frequence_retrait or "-")
                ])
            elif abonne['type_compte'] == "Fixe" and infos_compte_fixe:
                montant_initial = infos_compte_fixe['montant_initial']
                date_fin = infos_compte_fixe['date_fin']
                pages_completes = infos_compte_fixe['pages_completes'] or 0
                total_cases = infos_compte_fixe['total_cases'] or 0
                labels.extend([
                    ("Montant initial fixe:", f"{int(montant_initial)} FC"),
                    ("Date début:", infos_compte_fixe['date_debut']),
                    ("Date fin:", date_fin),
                    ("Pages complètes:", f"{pages_completes}/8"),
                    ("Cases remplies:", f"{total_cases}/248"),
                    ("Montant épargné:", f"{int(montant_initial * total_cases)} FC")
                ])
            
            for i, (text, value) in enumerate(labels):
                frame = tk.Frame(info_frame, bg=CARD_COLOR)
                frame.grid(row=i, column=0, sticky='w', pady=2)
                
                lbl_text = tk.Label(frame, text=text, font=("Arial", 10, 'bold'), bg=CARD_COLOR, width=20, anchor='w')
                lbl_text.pack(side='left')
                
                lbl_value = tk.Label(frame, text=value, font=("Arial", 10), bg=CARD_COLOR, anchor='w')
                lbl_value.pack(side='left')
            
            btn_frame = tk.Frame(main_frame, bg=BACKGROUND_COLOR)
            btn_frame.pack(pady=20)
            
            ttk.Button(btn_frame, 
                      text="Exporter en PDF", 
                      command=lambda: self.exporter_pdf(abonne)).pack(side='left', padx=10)
            
            if abonne['type_compte'] == "Bloqué":
                ttk.Button(btn_frame, 
                          text="Configurer retrait", 
                          command=lambda: self.configurer_retrait_blocage(abonne_id)).pack(side='left', padx=10)
            elif abonne['type_compte'] == "Fixe":
                ttk.Button(btn_frame,
                         text="Voir carnet fixe",
                         command=lambda: self.afficher_carnet_fixe(abonne['numero_carte'])).pack(side='left', padx=10)
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'affichage du profil: {str(e)}")
        finally:
            if conn:
                conn.close()

    def enregistrer(self):
        """Enregistre un nouvel abonné"""
        if not self.validate_fields():
            return

        try:
            with connexion_db() as conn:
                curseur = conn.cursor()
            
                telephone = self.data["telephone"].get()
                type_compte = self.data["type_compte"].get()
                nom = self.data["nom"].get()
                postnom = self.data["postnom"].get()
                
                # Vérifier si l'abonné existe déjà
                curseur.execute("""
                SELECT COUNT(*) FROM abonne 
                WHERE nom = ? AND postnom = ? AND telephone = ? AND type_compte = ?
                """, (nom, postnom, telephone, type_compte))

                if curseur.fetchone()[0] > 0:
                    messagebox.showerror("Erreur", f"{nom} {postnom} avec ce numéro et type de compte existe déjà!")
                    return

                # Préparation des données
                data_values = {
                    "numero_client": self.data["numero_client"].get(),
                    "numero_carte": self.data["numero_carte"].get(),
                    "nom": self.data["nom"].get(),
                    "postnom": self.data["postnom"].get(),
                    "prenom": self.data["prenom"].get(),
                    "sexe": self.data["sexe"].get(),
                    "date_naissance": self.data["date_naissance"].get(),
                    "lieu_naissance": self.data["lieu_naissance"].get(),
                    "adresse": self.data["adresse"].get(),
                    "telephone": telephone,
                    "suppleant": self.data["suppleant"].get() or "",
                    "contact_suppleant": self.data["contact_suppleant"].get() or "",
                    "type_compte": type_compte,
                    "montant": float(self.data["montant"].get() or 0),
                    "photo": self.data["photo"].get() or "",
                    "date_inscription": datetime.date.today().isoformat(),
                    "solde": 0,
                    "duree_blocage": 0,
                    "montant_atteindre": 0,
                    "pourcentage_retrait": 0,
                    "frequence_retrait": "",
                    "statut": "Actif",
                    "date_derniere_operation": datetime.date.today().isoformat()  # Nouvelle colonne
                }

                # Gestion spécifique pour compte bloqué
                if type_compte == "Bloqué":
                    data_values.update({
                        "duree_blocage": int(self.data["duree_blocage"].get()),
                        "montant_atteindre": float(self.data["montant_atteindre"].get() or 0),
                        "pourcentage_retrait": int(self.data["pourcentage_retrait"].get()),
                        "frequence_retrait": self.data["frequence_retrait"].get()
                    })

                # Insertion dans la table abonne
                curseur.execute("""
                    INSERT INTO abonne (
                        numero_client, numero_carte, nom, postnom, prenom, sexe, 
                        date_naissance, lieu_naissance, adresse, telephone, 
                        suppleant, contact_suppleant, type_compte, montant, 
                        photo, date_inscription, solde, duree_blocage,
                        montant_atteindre, pourcentage_retrait, frequence_retrait, 
                        statut, date_derniere_operation
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, tuple(data_values.values()))
                
                # Gestion spécifique pour compte fixe
                if type_compte == "Fixe":
                    date_debut = datetime.date.today().isoformat()
                    date_fin = (datetime.date.today() + datetime.timedelta(days=365)).isoformat()
                    numero_carte = data_values["numero_carte"]
                    numero_client = data_values["numero_client"]  # Récupérer le numéro client
                    
                    # Vérifier que le montant est valide
                    montant = data_values["montant"]
                    if not montant or montant <=0:
                        raise ValueError("Le montant doit être positif pour un compte fixe")
                    
                    
                    curseur.execute("""
                        INSERT INTO compte_fixe (
                            numero_client, numero_carte, 
                            montant_initial, date_debut, date_fin
                        ) VALUES (?, ?, ?, ?, ?)
                        """, (
                        numero_client,
                        numero_carte,
                        data_values["montant"],
                        date_debut,
                        date_fin
                    ))
                    
                    # Initialiser les pages du carnet
                    try: 
                        for page in range(1,9):
                            curseur.execute("""
                                    INSERT INTO compte_fixe_pages(numero_carte,numero_client, page, cases_remplies)
                                    VALUES(?, ?,?,0)
                                """, (numero_carte, numero_client, page))
                    except sqlite3.IntegrityError:
                        #Les pages existent peut-être déjà (peu probable)
                        conn.rollback()
                        raise ValueError(f"Les pages existent déjà pour la carte {numero_carte}")
                
                conn.commit()
                ajouter_journal("Inscription", self.nom_agent, f"Nouvel abonné: {data_values['nom']} {data_values['prenom']}")
                
                message = f"Abonné enregistré avec succès!"
                if type_compte == "Fixe":
                    message += f"\nCompte fixe configuré avec un montant initial de {data_values['montant']} FC"
                
                messagebox.showinfo("Succès", message)
                self.afficher_donnees()
                self.reinitialiser_formulaire()

        except sqlite3.IntegrityError as e:
            self.logger.error(f"Erreur intégrité base de données: {str(e)}", exc_info=True)
            messagebox.showerror("Erreur", f"Violation contraintes base de données: {str(e)}")
        except ValueError as e:
            self.logger.error(f"Erreur de valeur: {str(e)}", exc_info=True)
            messagebox.showerror("Erreur", f"Données invalides: {str(e)}")
        except Exception as e:
            self.logger.critical(f"Erreur inattendue: {str(e)}", exc_info=True)
            messagebox.showerror("Erreur", f"Erreur système: {str(e)}")

    def afficher_carnet_fixe(self, numero_carte):
        """Affiche l'interface du carnet de compte fixe"""
        conn = None
        try:
            conn = connexion_db()
            cur = conn.cursor()
            
            # Récupérer les infos du compte fixe
            cur.execute("""
                SELECT cf.montant_initial, cf.date_debut, cf.date_fin,
                       (SELECT COUNT(*) FROM compte_fixe_pages WHERE numero_carte = ? AND cases_remplies = 31) as pages_completes,
                       (SELECT SUM(cases_remplies) FROM compte_fixe_pages WHERE numero_carte = ?) as total_cases
                FROM compte_fixe cf
                WHERE cf.numero_carte = ?
            """, (numero_carte, numero_carte, numero_carte))
            
            compte_fixe = cur.fetchone()
            
            if not compte_fixe:
                messagebox.showerror("Erreur", "Ce client n'a pas de compte fixe configuré")
                return
            
            montant_initial = compte_fixe[0]
            pages_completes = compte_fixe[3] or 0
            total_cases = compte_fixe[4] or 0
            
            # Récupérer les pages existantes
            cur.execute("""
                SELECT page, cases_remplies 
                FROM compte_fixe_pages 
                WHERE numero_carte = ? 
                ORDER BY page
            """, (numero_carte,))
            pages_existantes = {row[0]: row[1] for row in cur.fetchall()}
            
            # Créer la fenêtre
            fen_carnet = tk.Toplevel(self.parent)
            fen_carnet.title(f"Carnet Compte Fixe - Client {numero_carte}")
            fen_carnet.geometry("900x700")
            fen_carnet.configure(bg=BACKGROUND_COLOR)
            
            # Cadre d'information
            info_frame = tk.Frame(fen_carnet, padx=20, pady=15, bg=PRIMARY_COLOR)
            info_frame.pack(fill="x")
            
            tk.Label(info_frame, 
                   text=f"Montant initial: {montant_initial:,.2f} FC", 
                   font=("Helvetica", 12, "bold"), 
                   bg=PRIMARY_COLOR,
                   fg="white").pack(side="left", padx=10)
            
            tk.Label(info_frame, 
                   text=f"Pages complètes: {pages_completes}/8 | Cases: {total_cases}/248", 
                   font=("Helvetica", 12, "bold"), 
                   bg=PRIMARY_COLOR,
                   fg="white").pack(side="right", padx=10)
            
            # Notebook pour les pages (8 maximum)
            notebook = ttk.Notebook(fen_carnet)
            notebook.pack(fill="both", expand=True, padx=20, pady=10)
            
            # Créer les pages du carnet
            for page_num in range(1, 9):
                page_frame = tk.Frame(notebook, bg=CARD_COLOR)
                notebook.add(page_frame, text=f"Page {page_num}")
                
                # Titre de la page
                tk.Label(page_frame, 
                        text=f"Page {page_num}", 
                        font=("Helvetica", 14, "bold"), 
                        bg=CARD_COLOR,
                        fg=PRIMARY_COLOR).pack(pady=10)
                
                # Cadre pour les cases
                cases_frame = tk.Frame(page_frame, bg=CARD_COLOR)
                cases_frame.pack(pady=10)
                
                # Créer la grille 31 cases (7 colonnes x 5 lignes)
                cases_remplies = pages_existantes.get(page_num, 0)
                for i in range(31):
                    row = i // 7
                    col = i % 7
                    
                    case_value = f"{i+1}\n{montant_initial:,.2f} FC" if i < cases_remplies else str(i+1)
                    case_color = ACCENT_COLOR if i < cases_remplies else CARD_COLOR
                    case_fg = "white" if i < cases_remplies else TEXT_COLOR
                    
                    case = tk.Label(cases_frame, 
                                  text=case_value, 
                                  width=12, 
                                  height=3, 
                                  relief="solid", 
                                  borderwidth=1, 
                                  bg=case_color,
                                  fg=case_fg,
                                  font=("Helvetica", 8, "bold"))
                    case.grid(row=row, column=col, padx=2, pady=2)
            
            # Boutons de gestion
            btn_frame = tk.Frame(fen_carnet, bg=BACKGROUND_COLOR)
            btn_frame.pack(pady=15)
            
            ttk.Button(btn_frame, 
                     text="Exporter en PDF", 
                     command=lambda: self.exporter_carnet_pdf(numero_carte, montant_initial, pages_existantes),
                     style='TButton').pack(side="left", padx=10)
            
            ttk.Button(btn_frame, 
                     text="Fermer", 
                     command=fen_carnet.destroy,
                     style='TButton').pack(side="right", padx=10)
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'affichage du carnet: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def exporter_carnet_pdf(self, numero_carte, montant_initial, pages_existantes):
        """Exporte le carnet de compte fixe en PDF"""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                fichier = tmp.name
            
            doc = SimpleDocTemplate(fichier, pagesize=A4)
            styles = getSampleStyleSheet()
            elements = []
            
            # Style personnalisé
            title_style = ParagraphStyle(
                'Title',
                parent=styles['Title'],
                fontSize=16,
                textColor=colors.HexColor(PRIMARY_COLOR),
                alignment=TA_CENTER,
                spaceAfter=20
            )
            
            # Titre
            elements.append(Paragraph("CARNET DE COMPTE FIXE", title_style))
            
            # Informations client
            info_style = ParagraphStyle(
                'Info',
                parent=styles['Normal'],
                fontSize=11,
                textColor=colors.black,
                spaceAfter=12
            )
            
            elements.append(Paragraph(f"<b>Numéro carte:</b> {numero_carte}", info_style))
            elements.append(Paragraph(f"<b>Montant initial:</b> {montant_initial:,.2f} FC", info_style))
            elements.append(Paragraph(f"<b>Date d'édition:</b> {datetime.datetime.now().strftime('%d/%m/%Y')}", info_style))
            elements.append(Spacer(1, 20))
            
            # Pages du carnet
            page_style = ParagraphStyle(
                'PageTitle',
                parent=styles['Heading2'],
                fontSize=14,
                textColor=colors.HexColor(SECONDARY_COLOR),
                spaceAfter=10
            )
            
            for page_num in range(1, 9):
                elements.append(Paragraph(f"Page {page_num}", page_style))
                elements.append(Spacer(1, 10))
                
                cases_remplies = pages_existantes.get(page_num, 0)
                data = []
                
                # Créer les lignes pour le tableau (5 lignes de 7 cases)
                for i in range(0, 31, 7):
                    row = []
                    for j in range(7):
                        case_num = i + j + 1
                        if case_num <= 31:
                            if case_num <= cases_remplies:
                                row.append(f"{case_num}\n{montant_initial:,.2f} FC")
                            else:
                                row.append(str(case_num))
                        else:
                            row.append("")
                    data.append(row)
                
                table = Table(data, colWidths=[70]*7, rowHeights=[40]*5)
                table.setStyle(TableStyle([
                    ('GRID', (0,0), (-1,-1), 1, colors.black),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('BACKGROUND', (0,0), (-1,-1), colors.white),
                    *[('BACKGROUND', (col,row), (col,row), colors.HexColor(ACCENT_COLOR)) 
                      for row in range(5) for col in range(7) 
                      if row*7 + col + 1 <= cases_remplies],
                    *[('TEXTCOLOR', (col,row), (col,row), colors.white)
                      for row in range(5) for col in range(7)
                      if row*7 + col + 1 <= cases_remplies]
                ]))
                
                elements.append(table)
                elements.append(Spacer(1, 20))
            
            doc.build(elements)
            webbrowser.open(fichier)
            
        except Exception as e:
            messagebox.showerror("Erreur PDF", f"Erreur lors de la génération du PDF: {str(e)}")

    def configurer_retrait_blocage(self, abonne_id):
        """Ouvre une interface pour configurer les critères de retrait pour un compte bloqué"""
        conn = None
        try:
            conn = connexion_db()
            cur = conn.cursor()
            cur.execute("""
                SELECT montant_atteindre, pourcentage_retrait, frequence_retrait 
                FROM abonne WHERE id=?
            """, (abonne_id,))
            config = cur.fetchone()
            
            montant_atteindre = config[0] if config and config[0] else 0
            pourcentage_retrait = config[1] if config and config[1] else 30
            frequence_retrait = config[2] if config and config[2] else "Mensuel"
            
            config_win = tk.Toplevel()
            config_win.title("Configuration des retraits - Compte Bloqué")
            config_win.geometry("500x400")
            config_win.configure(bg=BACKGROUND_COLOR)
            
            config_win.geometry(f"+{self.parent.winfo_x()+100}+{self.parent.winfo_y()+100}")
            
            main_frame = tk.Frame(config_win, bg=BACKGROUND_COLOR, padx=20, pady=20)
            main_frame.pack(fill='both', expand=True)
            
            tk.Label(main_frame, 
                    text="CRITÈRES DE RETRAIT", 
                    font=("Helvetica", 16, "bold"),
                    bg=BACKGROUND_COLOR).pack(pady=10)
            
            config_frame = tk.Frame(main_frame, bg=CARD_COLOR, padx=15, pady=15)
            config_frame.pack(fill='x', pady=10)
            
            self.montant_atteindre_var = tk.StringVar(value=str(int(montant_atteindre)) if montant_atteindre else "")
            self.pourcentage_retrait_var = tk.StringVar(value=str(pourcentage_retrait))
            self.frequence_retrait_var = tk.StringVar(value=frequence_retrait)
            
            tk.Label(config_frame, 
                    text="Montant à atteindre:", 
                    bg=CARD_COLOR).grid(row=0, column=0, sticky='w', pady=5)
            ttk.Entry(config_frame, 
                     textvariable=self.montant_atteindre_var, 
                     width=15).grid(row=0, column=1, sticky='w', pady=5)
            
            tk.Label(config_frame, 
                    text="Pourcentage de retrait:", 
                    bg=CARD_COLOR).grid(row=1, column=0, sticky='w', pady=5)
            ttk.Combobox(config_frame, 
                        textvariable=self.pourcentage_retrait_var, 
                        values=["10", "20", "30", "40", "50"],
                        width=5,
                        state='readonly').grid(row=1, column=1, sticky='w', pady=5)
            
            tk.Label(config_frame, 
                    text="Fréquence de retrait:", 
                    bg=CARD_COLOR).grid(row=2, column=0, sticky='w', pady=5)
            ttk.Combobox(config_frame, 
                        textvariable=self.frequence_retrait_var, 
                        values=["Mensuel", "Trimestriel", "Semestriel", "Annuel"],
                        width=10,
                        state='readonly').grid(row=2, column=1, sticky='w', pady=5)
            
            btn_frame = tk.Frame(main_frame, bg=BACKGROUND_COLOR)
            btn_frame.pack(pady=20)
            
            ttk.Button(btn_frame, 
                      text="Enregistrer", 
                      command=lambda: self.enregistrer_config_retrait(abonne_id)).pack(side='left', padx=10)
        
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la configuration: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def enregistrer_config_retrait(self, abonne_id):
        """Enregistre la configuration des retraits pour un compte bloqué"""
        conn = None
        try:
            montant = float(self.montant_atteindre_var.get())
            pourcentage = int(self.pourcentage_retrait_var.get())
            frequence = self.frequence_retrait_var.get()
            
            if montant <= 0 or pourcentage <= 0 or pourcentage > 100:
                raise ValueError("Valeurs invalides")
            
            conn = connexion_db()
            cur = conn.cursor()
            cur.execute("""
                UPDATE abonne 
                SET montant_atteindre = ?, pourcentage_retrait = ?, frequence_retrait = ?
                WHERE id = ?
            """, (montant, pourcentage, frequence, abonne_id))
            conn.commit()
            
            messagebox.showinfo("Succès", "Configuration enregistrée avec succès!")
        except ValueError:
            messagebox.showerror("Erreur", "Veuillez entrer des valeurs valides")
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'enregistrement: {str(e)}")
        finally:
            if conn:
                conn.close()

    def exporter_pdf(self, abonne):
        """Exporte le profil de l'abonné en PDF"""
        try:
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            
            pdf.cell(0, 10, f"Profil de l'abonné: {abonne['nom']} {abonne['prenom']}", 0, 1, 'C')
            pdf.ln(10)
            
            photo_path = abonne['photo'] if 'photo' in abonne and abonne['photo'] else ""
            if photo_path and os.path.exists(photo_path):
                img = Image.open(photo_path)
                img.thumbnail((100, 100))
                temp_photo = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
                img.save(temp_photo.name)
                pdf.image(temp_photo.name, x=pdf.w/2-25, w=50)
                os.unlink(temp_photo.name)
                pdf.ln(40)
            
            pdf.set_font("Arial", size=12)
            
            date_inscription_str = abonne['date_inscription']
            try:
                date_inscription = datetime.datetime.strptime(date_inscription_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                date_inscription = datetime.date.today()
            
            aujourdhui = datetime.date.today()
            duree = aujourdhui - date_inscription
            duree_annees = duree.days // 365
            duree_mois = (duree.days % 365) // 30
            duree_jours = duree.days
            
            duree_texte = f"{duree_jours} jours"
            if duree_annees > 0:
                duree_texte = f"{duree_annees} an(s) et {duree_mois} mois"
            elif duree_mois > 0:
                duree_texte = f"{duree_mois} mois et {duree_jours % 30} jours"
            
            solde = abonne['solde'] if 'solde' in abonne else 0
            
            duree_blocage = abonne['duree_blocage'] if 'duree_blocage' in abonne else 0
            montant_atteindre = abonne['montant_atteindre'] if 'montant_atteindre' in abonne else 0
            pourcentage_retrait = abonne['pourcentage_retrait'] if 'pourcentage_retrait' in abonne else 0
            frequence_retrait = abonne['frequence_retrait'] if 'frequence_retrait' in abonne else ""
            
            # Informations de statut
            statut = abonne['statut'] if 'statut' in abonne else "Actif"
            date_derniere_operation = abonne['date_derniere_operation'] if 'date_derniere_operation' in abonne else ""
            
            statut_text = f"Statut: {statut}"
            if statut == "Actif" and date_derniere_operation:
                try:
                    date_derniere = datetime.datetime.strptime(date_derniere_operation, "%Y-%m-%d").strftime("%d/%m/%Y")
                    statut_text = f"Actif depuis {date_derniere}"
                except:
                    pass
            elif statut == "Inactif" and date_derniere_operation:
                try:
                    date_derniere = datetime.datetime.strptime(date_derniere_operation, "%Y-%m-%d")
                    jours_inactif = (datetime.datetime.now() - date_derniere).days
                    statut_text = f"Inactif depuis {jours_inactif} jours (dernière opération: {date_derniere.strftime('%d/%m/%Y')})"
                except:
                    pass
            
            # Récupérer les infos spécifiques au compte fixe si nécessaire
            infos_compte_fixe = None
            if abonne['type_compte'] == "Fixe":
                conn = None
                try:
                    conn = connexion_db()
                    cur = conn.cursor()
                    cur.execute("""
                        SELECT cf.montant_initial, cf.date_debut, cf.date_fin,
                               (SELECT COUNT(*) FROM compte_fixe_pages WHERE numero_carte = ? AND cases_remplies = 31) as pages_completes,
                               (SELECT SUM(cases_remplies) FROM compte_fixe_pages WHERE numero_carte = ?) as total_cases
                        FROM compte_fixe cf
                        WHERE cf.numero_carte = ?
                    """, (abonne['numero_carte'], abonne['numero_carte'], abonne['numero_carte']))
                    infos_compte_fixe = cur.fetchone()
                except Exception as e:
                    print(f"Erreur récupération compte fixe: {str(e)}")
                finally:
                    if conn:
                        conn.close()
            
            infos = [
                f"Numéro client: {abonne['numero_client']}",
                f"Numéro carte: {abonne['numero_carte']}",
                f"Nom: {abonne['nom']}",
                f"Postnom: {abonne['postnom']}",
                f"Prénom: {abonne['prenom']}",
                f"Sexe: {abonne['sexe']}",
                f"Date de naissance: {abonne['date_naissance']}",
                f"Lieu de naissance: {abonne['lieu_naissance']}",
                f"Adresse: {abonne['adresse']}",
                f"Téléphone: {abonne['telephone']}",
                f"Suppléant: {abonne['suppleant'] or '-'}",
                f"Contact suppléant: {abonne['contact_suppleant'] or '-'}",
                f"Type de compte: {abonne['type_compte']}",
                f"Montant initial: {int(abonne['montant'])} FC" if 'montant' in abonne and abonne['montant'] else "Montant initial: -",
                f"Durée blocage: {duree_blocage} mois" if abonne['type_compte'] == "Bloqué" else "",
                f"Date d'inscription: {date_inscription.strftime('%d/%m/%Y')}",
                f"Solde actuel: {int(solde)} FC" if solde else "Solde actuel: -",
                f"Durée d'inscription: {duree_texte}",
                statut_text
            ]
            
            if abonne['type_compte'] == "Bloqué":
                infos.extend([
                    f"Montant à atteindre: {int(montant_atteindre)} FC" if montant_atteindre else "Montant à atteindre: -",
                    f"Pourcentage de retrait: {pourcentage_retrait}%" if pourcentage_retrait else "Pourcentage de retrait: -",
                    f"Fréquence de retrait: {frequence_retrait}" if frequence_retrait else "Fréquence de retrait: -"
                ])
            elif abonne['type_compte'] == "Fixe" and infos_compte_fixe:
                infos.extend([
                    f"Montant initial fixe: {infos_compte_fixe[0]:,.2f} FC",
                    f"Date début: {infos_compte_fixe[1]}",
                    f"Date fin: {infos_compte_fixe[2]}",
                    f"Pages complètes: {infos_compte_fixe[3]}/8",
                    f"Cases remplies: {infos_compte_fixe[4]}/248",
                    f"Montant épargné: {infos_compte_fixe[0] * infos_compte_fixe[4]:,.2f} FC"
                ])
        
            for info in infos:
                if info.strip():
                    pdf.cell(0, 10, info, 0, 1)
            
            chemin_db = get_db_path()
            exports_dir = os.path.join(os.path.dirname(chemin_db), "exports")
            os.makedirs(exports_dir, exist_ok=True)
            
            nom_abonne = f"{abonne['nom']}_{abonne['prenom']}".replace(" ", "_")
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            file_name = f"Profil_{nom_abonne}_{timestamp}.pdf"
            file_path = os.path.join(exports_dir, file_name)
            
            pdf.output(file_path)
            
            if sys.platform == "win32":
                os.startfile(file_path)
            elif sys.platform == "darwin":
                subprocess.call(('open', file_path))
            else:
                subprocess.call(('xdg-open', file_path))
                
            messagebox.showinfo("Succès", f"Profil exporté en PDF et ouvert automatiquement")
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'export PDF: {str(e)}")

    def modifier_abonne_par_id(self, abonne_id):
        """Remplit le formulaire avec les données d'un abonné existant"""
        conn = None
        try:
            conn = connexion_db()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM abonne WHERE id=?", (abonne_id,))
            abonne = cur.fetchone()
            
            if not abonne:
                messagebox.showerror("Erreur", "Abonné introuvable")
                return
            
            self.data["numero_client"].set(abonne['numero_client'])
            self.data["numero_carte"].set(abonne['numero_carte'])
            self.data["nom"].set(abonne['nom'])
            self.data["postnom"].set(abonne['postnom'])
            self.data["prenom"].set(abonne['prenom'])
            self.data["sexe"].set(abonne['sexe'])
            self.data["date_naissance"].set(abonne['date_naissance'])
            self.data["lieu_naissance"].set(abonne['lieu_naissance'])
            self.data["adresse"].set(abonne['adresse'])
            self.data["telephone"].set(abonne['telephone'])
            self.data["suppleant"].set(abonne['suppleant'] or "")
            self.data["contact_suppleant"].set(abonne['contact_suppleant'] or "")
            self.data["type_compte"].set(abonne['type_compte'])
            self.data["montant"].set(abonne['montant'])
            self.data["photo"].set(abonne['photo'] if 'photo' in abonne and abonne['photo'] else "")
            
            if abonne['type_compte'] == "Bloqué" and 'duree_blocage' in abonne:
                self.data["duree_blocage"].set(str(abonne['duree_blocage']))
            
            if 'photo' in abonne and abonne['photo'] and os.path.exists(abonne['photo']):
                self.display_photo(abonne['photo'])
            else:
                self.display_photo("")
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du chargement des données: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def supprimer_abonne_par_id(self, abonne_id):
        """Supprime un abonné par son ID"""
        if not messagebox.askyesno("Confirmation", "Voulez-vous vraiment supprimer cet abonné?"):
            return
        
        conn = None
        try:
            conn = connexion_db()
            cur = conn.cursor()
            
            cur.execute("SELECT nom, prenom FROM abonne WHERE id = ?", (abonne_id,))
            abonne = cur.fetchone()
            nom_complet = f"{abonne[0]} {abonne[1]}" if abonne else "Inconnu"
            
            # Supprimer d'abord les dépendances (compte_fixe et compte_fixe_pages)
            cur.execute("SELECT numero_carte FROM abonne WHERE id = ?", (abonne_id,))
            numero_carte = cur.fetchone()[0]
            
            cur.execute("DELETE FROM compte_fixe_pages WHERE numero_carte = ?", (numero_carte,))
            cur.execute("DELETE FROM compte_fixe WHERE numero_carte = ?", (numero_carte,))
            
            # Puis supprimer l'abonné
            cur.execute("DELETE FROM abonne WHERE id=?", (abonne_id,))
            conn.commit()
            
            ajouter_journal("Suppression", "Admin", f"Abonné supprimé: {nom_complet}")
            
            self.afficher_donnees()
            messagebox.showinfo("Succès", "Abonné supprimé avec succès")
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur de suppression: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def rechercher_abonne(self):
        """Recherche des abonnés par nom, prénom ou numéro"""
        if not hasattr(self, 'scrollable_frame'):
            self.create_abonne_list()
        
        recherche = self.search_var.get().lower()
        if not recherche:
            self.afficher_donnees()
            return
        
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        conn = None
        try:
            conn = connexion_db()
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT id, numero_client, nom, postnom, prenom, telephone, 
                       date_inscription, type_compte, photo, solde, statut,
                       date_derniere_operation
                FROM abonne
                WHERE numero_client LIKE ? OR nom LIKE ? OR postnom LIKE ? OR prenom LIKE ?
            """, (f"%{recherche}%", f"%{recherche}%", f"%{recherche}%", f"%{recherche}%"))
            
            found = False
            for row in cur.fetchall():
                found = True
                abonne_id = row['id']
                numero_client = row['numero_client']
                nom = row['nom']
                postnom = row['postnom']
                prenom = row['prenom']
                telephone = row['telephone']
                date_inscription = row['date_inscription']
                type_compte = row['type_compte']
                photo_path = row['photo']
                solde = row['solde']
                statut = row['statut']
                date_derniere_operation = row['date_derniere_operation']
                
                card = tk.Frame(self.scrollable_frame, 
                              bg=CARD_COLOR, 
                              bd=1, 
                              relief='solid', 
                              padx=10, 
                              pady=10)
                card.pack(fill='x', padx=5, pady=5, ipadx=5, ipady=5)
                
                photo_frame = tk.Frame(card, bg=CARD_COLOR)
                photo_frame.pack(side='left', padx=(0, 10))
                
                if photo_path and os.path.exists(photo_path):
                    try:
                        img = Image.open(photo_path)
                        img = img.resize((60, 60), Image.LANCZOS)
                        photo = ImageTk.PhotoImage(img)
                        self.photo_references.append(photo)
                        photo_label = tk.Label(photo_frame, image=photo, bg=CARD_COLOR)
                        photo_label.image = photo
                        photo_label.pack()
                    except Exception as e:
                        print(f"Erreur chargement photo: {e}")
                        tk.Label(photo_frame, text="👤", font=("Arial", 24), bg=CARD_COLOR).pack()
                else:
                    tk.Label(photo_frame, text="👤", font=("Arial", 24), bg=CARD_COLOR).pack()
                
                info_frame = tk.Frame(card, bg=CARD_COLOR)
                info_frame.pack(side='left', fill='x', expand=True)
                
                nom_complet = f"{nom} {postnom} {prenom}" if postnom else f"{nom} {prenom}"
                tk.Label(info_frame, 
                        text=nom_complet, 
                        font=("Helvetica", 12, "bold"), 
                        bg=CARD_COLOR, 
                        anchor="w").pack(anchor="w")
                
                tk.Label(info_frame, 
                        text=f"📱 {telephone}", 
                        bg=CARD_COLOR, 
                        anchor="w").pack(anchor="w")
                
                type_color = {
                    "Fixe": "green",
                    "Mixte": "blue",
                    "Bloqué": "red"
                }.get(type_compte, "black")
                
                solde_int = int(solde) if solde else 0
                solde_text = f"💰 {solde_int} FC ({type_compte})" if solde else f"Type: {type_compte}"
                tk.Label(info_frame, 
                        text=solde_text, 
                        fg=type_color, 
                        bg=CARD_COLOR, 
                        anchor="w").pack(anchor="w")
                
                # Affichage du statut
                statut_color = "green" if statut == "Actif" else "red"
                statut_text = f"Statut: {statut}"
                
                if statut == "Actif" and date_derniere_operation:
                    try:
                        date_derniere = datetime.datetime.strptime(date_derniere_operation, "%Y-%m-%d").strftime("%d/%m/%Y")
                        statut_text = f"Actif depuis {date_derniere}"
                    except:
                        statut_text = f"Statut: {statut}"
                
                elif statut == "Inactif" and date_derniere_operation:
                    try:
                        date_derniere = datetime.datetime.strptime(date_derniere_operation, "%Y-%m-%d")
                        jours_inactif = (datetime.datetime.now() - date_derniere).days
                        statut_text = f"Inactif depuis {jours_inactif} jours"
                    except:
                        statut_text = f"Statut: {statut}"
                
                tk.Label(info_frame, 
                        text=statut_text, 
                        fg=statut_color, 
                        bg=CARD_COLOR, 
                        anchor="w").pack(anchor="w")
                
                try:
                    date_str = str(date_inscription)
                    date_formatted = datetime.datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                except:
                    date_formatted = "Date inconnue"
                    
                tk.Label(info_frame, 
                        text=f"📅 Inscrit le: {date_formatted}", 
                        bg=CARD_COLOR, 
                        anchor="w").pack(anchor="w")
                
                btn_frame = tk.Frame(card, bg=CARD_COLOR)
                btn_frame.pack(side='right', padx=(10, 0))
                
                edit_btn = tk.Button(btn_frame, 
                                    text="✏️ Modifier", 
                                    font=("Arial", 10),
                                    command=lambda id=abonne_id: self.modifier_abonne_par_id(id),
                                    bd=0,
                                    bg="#e0e0e0",
                                    padx=5,
                                    cursor="hand2")
                edit_btn.pack(side='left', padx=2)
                
                profile_btn = tk.Button(btn_frame, 
                                    text="👤 Profil", 
                                    font=("Arial", 10),
                                    command=lambda id=abonne_id: self.afficher_profil(id),
                                    bd=0,
                                    bg="#e0e0e0",
                                    padx=5,
                                    cursor="hand2")
                profile_btn.pack(side='left', padx=2)
                
                delete_btn = tk.Button(btn_frame, 
                                      text="🗑️ Supprimer", 
                                      font=("Arial", 10),
                                      command=lambda id=abonne_id: self.supprimer_abonne_par_id(id),
                                      bd=0,
                                      bg="#e0e0e0",
                                      padx=5,
                                      cursor="hand2")
                delete_btn.pack(side='left', padx=2)
            
            if not found:
                tk.Label(self.scrollable_frame, 
                        text="Aucun abonné trouvé", 
                        bg=BACKGROUND_COLOR, 
                        font=("Helvetica", 12)).pack(pady=20)
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la recherche: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def rapport_global(self):
        """Affiche les statistiques globales"""
        conn = None
        try:
            conn = connexion_db()
            cur = conn.cursor()
            
            cur.execute("SELECT COUNT(*) FROM abonne")
            total = cur.fetchone()[0]
            
            today = datetime.date.today().isoformat()
            cur.execute("SELECT COUNT(*) FROM abonne WHERE date_inscription = ?", (today,))
            aujourdhui = cur.fetchone()[0]
            
            debut_semaine = (datetime.date.today() - datetime.timedelta(days=datetime.date.today().weekday())).isoformat()
            cur.execute("SELECT COUNT(*) FROM abonne WHERE date_inscription >= ?", (debut_semaine,))
            semaine = cur.fetchone()[0]
            
            debut_mois = datetime.date.today().replace(day=1).isoformat()
            cur.execute("SELECT COUNT(*) FROM abonne WHERE date_inscription >= ?", (debut_mois,))
            mois = cur.fetchone()[0]
            
            debut_annee = datetime.date.today().replace(month=1, day=1).isoformat()
            cur.execute("SELECT COUNT(*) FROM abonne WHERE date_inscription >= ?", (debut_annee,))
            annee = cur.fetchone()[0]
            
            # Statistiques par type de compte
            cur.execute("""
                SELECT type_compte, COUNT(*), SUM(solde)
                FROM abonne
                GROUP BY type_compte
            """)
            stats_comptes = cur.fetchall()
            
            # Statistiques par statut (actif/inactif)
            cur.execute("""
                SELECT statut, COUNT(*)
                FROM abonne
                GROUP BY statut
            """)
            stats_statut = cur.fetchall()
            
            report_win = tk.Toplevel(self.container)
            report_win.title("Rapports Statistiques")
            report_win.geometry("500x700")
            report_win.configure(bg=BACKGROUND_COLOR)
            
            report_win.geometry(f"+{self.parent.winfo_x()+100}+{self.parent.winfo_y()+100}")
            
            main_frame = tk.Frame(report_win, bg=BACKGROUND_COLOR, padx=20, pady=20)
            main_frame.pack(fill='both', expand=True)
            
            tk.Label(main_frame, 
                    text="STATISTIQUES DES ABONNÉS", 
                    font=("Helvetica", 16, "bold"),
                    bg=BACKGROUND_COLOR).pack(pady=10)
            
            stats_frame = tk.Frame(main_frame, bg=CARD_COLOR, padx=15, pady=15)
            stats_frame.pack(fill='x', pady=10)
            
            stats = [
                ("Total des abonnés:", total),
                ("Abonnés aujourd'hui:", aujourdhui),
                ("Abonnés cette semaine:", semaine),
                ("Abonnés ce mois:", mois),
                ("Abonnés cette année:", annee)
            ]
            
            for i, (text, value) in enumerate(stats):
                frame = tk.Frame(stats_frame, bg=CARD_COLOR)
                frame.grid(row=i, column=0, sticky='w', pady=5)
                
                lbl_text = tk.Label(frame, text=text, font=("Arial", 12), bg=CARD_COLOR, width=25, anchor='w')
                lbl_text.pack(side='left')
                
                lbl_value = tk.Label(frame, text=value, font=("Arial", 12, "bold"), bg=CARD_COLOR, anchor='w')
                lbl_value.pack(side='left')
            
            # Séparateur
            tk.Frame(stats_frame, bg="LIGHT GRAY", height=2).grid(row=len(stats), column=0, sticky='we', pady=10)
            
            # Statistiques par type de compte
            tk.Label(stats_frame, 
                    text="Répartition par type de compte:", 
                    font=("Arial", 12, "bold"),
                    bg=CARD_COLOR).grid(row=len(stats)+1, column=0, sticky='w', pady=5)
            
            for i, (type_compte, count, solde) in enumerate(stats_comptes):
                frame = tk.Frame(stats_frame, bg=CARD_COLOR)
                frame.grid(row=len(stats)+2+i, column=0, sticky='w', pady=2)
                
                lbl_text = tk.Label(frame, 
                                  text=f"{type_compte}:", 
                                  font=("Arial", 11), 
                                  bg=CARD_COLOR, 
                                  width=15, 
                                  anchor='w')
                lbl_text.pack(side='left')
                
                lbl_count = tk.Label(frame, 
                                   text=f"{count} abonnés", 
                                   font=("Arial", 11), 
                                   bg=CARD_COLOR)
                lbl_count.pack(side='left', padx=10)
                
                lbl_solde = tk.Label(frame, 
                                   text=f"Solde total: {int(solde) if solde else 0} FC", 
                                   font=("Arial", 11), 
                                   bg=CARD_COLOR,
                                   fg="green")
                lbl_solde.pack(side='left')
            
            # Séparateur
            tk.Frame(stats_frame, bg="LIGHT GRAY", height=2).grid(row=len(stats)+len(stats_comptes)+3, column=0, sticky='we', pady=10)
            
            # Statistiques par statut
            tk.Label(stats_frame, 
                    text="Répartition par statut:", 
                    font=("Arial", 12, "bold"),
                    bg=CARD_COLOR).grid(row=len(stats)+len(stats_comptes)+4, column=0, sticky='w', pady=5)
            
            for i, (statut, count) in enumerate(stats_statut):
                frame = tk.Frame(stats_frame, bg=CARD_COLOR)
                frame.grid(row=len(stats)+len(stats_comptes)+5+i, column=0, sticky='w', pady=2)
                
                lbl_text = tk.Label(frame, 
                                  text=f"{statut}:", 
                                  font=("Arial", 11), 
                                  bg=CARD_COLOR, 
                                  width=15, 
                                  anchor='w')
                lbl_text.pack(side='left')
                
                lbl_count = tk.Label(frame, 
                                   text=f"{count} abonnés", 
                                   font=("Arial", 11), 
                                   bg=CARD_COLOR)
                lbl_count.pack(side='left', padx=10)
                
                # Calcul du pourcentage
                pourcentage = (count / total) * 100 if total > 0 else 0
                lbl_pourcentage = tk.Label(frame, 
                                         text=f"({pourcentage:.1f}%)", 
                                         font=("Arial", 11), 
                                         bg=CARD_COLOR,
                                         fg="blue")
                lbl_pourcentage.pack(side='left')
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de la génération du rapport: {str(e)}")
        finally:
            if conn:
                conn.close()
    
    def afficher_repertoire(self):
        """Affiche le répertoire des abonnés"""
        repertoire = tk.Toplevel(self.container)
        repertoire.title("Répertoire des Abonnés")
        repertoire.geometry("900x600")
        repertoire.configure(bg=BACKGROUND_COLOR)
        
        repertoire.geometry(f"+{self.parent.winfo_x()+100}+{self.parent.winfo_y()+100}")
        
        filter_frame = tk.Frame(repertoire, bg=BACKGROUND_COLOR, padx=10, pady=10)
        filter_frame.pack(fill='x')
        
        tk.Label(filter_frame, 
               text="Filtrer par:", 
               bg=BACKGROUND_COLOR).pack(side='left')
        
        reseau_var = tk.StringVar(value="Tous")
        reseaus = ["Tous", "Vodacom", "Africell", "Orange", "Airtel"]
        ttk.Combobox(filter_frame, 
                    textvariable=reseau_var, 
                    values=reseaus, 
                    width=15,
                    state='readonly').pack(side='left', padx=5)
        
        compte_var = tk.StringVar(value="Tous")
        comptes = ["Tous", "Fixe", "Mixte", "Bloqué"]
        ttk.Combobox(filter_frame, 
                    textvariable=compte_var, 
                    values=comptes, 
                    width=15,
                    state='readonly').pack(side='left', padx=5)
        
        statut_var = tk.StringVar(value="Tous")
        statuts = ["Tous", "Actif", "Inactif"]
        ttk.Combobox(filter_frame, 
                    textvariable=statut_var, 
                    values=statuts, 
                    width=15,
                    state='readonly').pack(side='left', padx=5)
        
        search_var = tk.StringVar()
        ttk.Entry(filter_frame, 
                 textvariable=search_var, 
                 width=30).pack(side='left', padx=5)
        
        def apply_filters():
            for i in tree.get_children():
                tree.delete(i)
                
            recherche = search_var.get().lower()
            reseau = reseau_var.get()
            compte = compte_var.get()
            statut = statut_var.get()
            
            conn = None
            try:
                conn = connexion_db()
                cur = conn.cursor()
                cur.execute("""
                    SELECT nom || ' ' || postnom || ' ' || prenom, telephone, type_compte, statut
                    FROM abonne ORDER BY nom
                """)
                
                for row in cur.fetchall():
                    nom, tel, type_compte, statut_abonne = row
                    
                    tel_prefix = tel[:3] if tel else ""
                    reseau_abonne = "Inconnu"
                    if tel_prefix.startswith(('081', '082', '083')):
                        reseau_abonne = "Vodacom"
                    elif tel_prefix.startswith(('090', '091')):
                        reseau_abonne = "Africell"
                    elif tel_prefix.startswith(('084', '085', '089')):
                        reseau_abonne = "Orange"
                    elif tel_prefix.startswith(('097', '098')):
                        reseau_abonne = "Airtel"
                    
                    if (reseau == "Tous" or reseau == reseau_abonne) and \
                       (compte == "Tous" or compte == type_compte) and \
                       (statut == "Tous" or statut == statut_abonne) and \
                       (recherche == "" or recherche in nom.lower()):
                        tree.insert("", tk.END, values=(nom, tel, reseau_abonne, type_compte, statut_abonne))
            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur lors du chargement des données: {str(e)}")
            finally:
                if conn:
                    conn.close()
        
        ttk.Button(filter_frame, 
                  text="Appliquer", 
                  command=apply_filters).pack(side='left', padx=5)
        
        tree_frame = tk.Frame(repertoire, bg=BACKGROUND_COLOR)
        tree_frame.pack(fill='both', expand=True, padx=10, pady=5)
        
        cols = ("Nom", "Téléphone", "Réseau", "Type Compte", "Statut")
        tree = ttk.Treeview(tree_frame, columns=cols, show="headings", style="Treeview")
        
        style = ttk.Style()
        style.configure("Treeview", 
                        background=CARD_COLOR, 
                        fieldbackground=CARD_COLOR, 
                        foreground=TEXT_COLOR)
        style.configure("Treeview.Heading", 
                       background=PRIMARY_COLOR, 
                       foreground="white", 
                       font=('Helvetica', 10, 'bold'))
        
        for col in cols:
            tree.heading(col, text=col)
            tree.column(col, width=150)
        
        vsb = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        
        tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        
        apply_filters()
    
    def afficher_abonnes_par_categorie(self):
        """Affiche les abonnés groupés par catégorie"""
        cat_win = tk.Toplevel(self.container)
        cat_win.title("Abonnés par Catégorie")
        cat_win.geometry("800x600")
        cat_win.configure(bg=BACKGROUND_COLOR)
        
        cat_win.geometry(f"+{self.parent.winfo_x()+100}+{self.parent.winfo_y()+100}")
        
        notebook = ttk.Notebook(cat_win)
        notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        types_compte = ["Fixe", "Mixte", "Bloqué"]
        
        for type_compte in types_compte:
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=type_compte)
            
            tree_frame = tk.Frame(frame, bg=BACKGROUND_COLOR)
            tree_frame.pack(fill='both', expand=True, padx=5, pady=5)
            
            cols = ("Nom", "Téléphone", "Réseau", "Solde", "Statut")
            tree = ttk.Treeview(tree_frame, columns=cols, show="headings", style="Treeview")
            
            for col in cols:
                tree.heading(col, text=col)
                tree.column(col, width=150, anchor="center")
            
            vsb = ttk.Scrollbar(tree_frame, orient='vertical', command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            
            tree.pack(side='left', fill='both', expand=True)
            vsb.pack(side='right', fill='y')
            
            conn = None
            try:
                conn = connexion_db()
                cur = conn.cursor()
                cur.execute("""
                    SELECT nom || ' ' || postnom || ' ' || prenom, telephone, solde, statut
                    FROM abonne 
                    WHERE type_compte = ?
                    ORDER BY nom
                """, (type_compte,))
                
                for row in cur.fetchall():
                    nom, tel, solde, statut = row
                    
                    tel_prefix = tel[:3] if tel else ""
                    reseau = "Inconnu"
                    if tel_prefix.startswith(('081', '082', '083')):
                        reseau = "Vodacom"
                    elif tel_prefix.startswith(('090', '091')):
                        reseau = "Africell"
                    elif tel_prefix.startswith(('084', '085', '089')):
                        reseau = "Orange"
                    elif tel_prefix.startswith(('097', '098')):
                        reseau = "Airtel"
                    
                    tree.insert("", tk.END, values=(nom, tel, reseau, f"{int(solde)} FC" if solde else "-", statut))
            except Exception as e:
                messagebox.showerror("Erreur", f"Erreur lors du chargement des données: {str(e)}")
            finally:
                if conn:
                    conn.close()
    
    def reinitialiser_formulaire(self):
        """Réinitialise le formulaire"""
        self.data["numero_client"].set(generer_numero_client_unique())
        self.data["numero_carte"].set(generer_numero_carte_unique())
        for key in self.data:
            if key not in ("numero_client", "numero_carte", "photo", "type_compte"):
                self.data[key].set("")
        self.data["type_compte"].set("Fixe")
        self.display_photo("")

    def __del__(self):
        """Destructeur pour libérer les ressources"""
        self.webcam.stop_capture()

# --- Pour appeler cette interface depuis form1.py ---
def launch_inscription_interface(parent_window=None):
    if parent_window:
        root = tk.Toplevel(parent_window)
    else:
        root = tk.Tk()
    app = InscriptionInterface(root)
    if not parent_window:
        root.mainloop()    

if __name__ == "__main__":
    launch_inscription_interface()