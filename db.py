import sqlite3
import os
import sys
import hashlib
import shutil
import time
from datetime import datetime
import random
import traceback
import psutil
import logging
import win32api
import stat
import tempfile
import binascii
from typing import Optional, Dict, Tuple, List, Iterator, Union
from contextlib import contextmanager
from PIL import Image, ImageDraw, ImageFont
import io

# ==== CONFIGURATION ====
class DBConfig:
    APP_NAME = "MonEpargne"
    DB_NAME = "money_epargne.db"
    WAL_MODE = True
    MAX_CONNECTIONS = 5
    CONNECTION_TIMEOUT = 30  # seconds

    @classmethod
    def get_app_dir(cls) -> str:
        """Retourne le dossier de l'application avec gestion robuste des permissions"""
        # 1. Essayer APPDATA
        appdata_dir = os.getenv("APPDATA")
        app_folder = os.path.join(appdata_dir, cls.APP_NAME) if appdata_dir else None
        
        # 2. Fallback: TEMP directory
        if not app_folder or not os.access(os.path.dirname(app_folder), os.W_OK):
            temp_dir = tempfile.gettempdir()
            app_folder = os.path.join(temp_dir, cls.APP_NAME)
            print(f"Utilisation du dossier TEMP pour la base de données: {app_folder}")
        
        # Création du répertoire avec permissions
        try:
            os.makedirs(app_folder, exist_ok=True, mode=0o777)
            # Windows: Ajouter permissions explicites (version simplifiée)
            if os.name == 'nt':
                try:
                    import win32security
                    import ntsecuritycon
                    sd = win32security.GetFileSecurity(app_folder, win32security.DACL_SECURITY_INFORMATION)
                    dacl = win32security.ACL()
                    # Ajouter des permissions complètes pour l'utilisateur actuel
                    user, _, _ = win32security.LookupAccountName("", win32api.GetUserName())
                    dacl.AddAccessAllowedAce(win32security.ACL_REVISION, ntsecuritycon.FILE_ALL_ACCESS, user)
                    sd.SetSecurityDescriptorDacl(1, dacl, 0)
                    win32security.SetFileSecurity(app_folder, win32security.DACL_SECURITY_INFORMATION, sd)
                except ImportError:
                    # Fallback si pywin32 n'est pas installé correctement
                    pass
                except Exception as e:
                    print(f"Erreur configuration permissions Windows: {e}")
        except Exception as e:
            print(f"Erreur création dossier: {e}")
            # Fallback ultime: dossier courant
            app_folder = os.path.abspath(".")
            print(f"Utilisation du dossier courant: {app_folder}")
        
        return app_folder

    @classmethod
    def get_db_path(cls) -> str:
        """Retourne le chemin complet de la base de données"""
        local_db = os.path.join(cls.get_app_dir(), cls.DB_NAME)

        # Copier la base originale si nécessaire
        if not os.path.exists(local_db):
            original_db = resource_path(cls.DB_NAME)
            if os.path.exists(original_db):
                try:
                    shutil.copyfile(original_db, local_db)
                    # Appliquer les permissions
                    os.chmod(local_db, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH)
                    print(f"Base copiée de {original_db} vers {local_db}")
                except Exception as e:
                    print(f"Erreur copie DB: {e}")
                    # Créer une base vide si la copie échoue
                    try:
                        conn = sqlite3.connect(local_db)
                        conn.close()
                        print(f"Base vide créée à {local_db}")
                    except Exception as e2:
                        print(f"Échec création base: {e2}")
                        raise PermissionError(f"Échec création base: {e2}")
        
        # Vérification finale des permissions
        try:
            with open(local_db, 'a') as f:
                f.write("\n")  # Test d'écriture
            print(f"Permissions vérifiées sur {local_db}")
        except Exception as e:
            print(f"Permissions insuffisantes sur {local_db}: {str(e)}")
            # Fallback: fichier temporaire
            local_db = os.path.join(tempfile.gettempdir(), cls.DB_NAME)
            print(f"Utilisation DB temporaire: {local_db}")
        
        return local_db

    @classmethod
    def set_file_permissions(cls, filepath: str):
        """Définit les permissions appropriées pour un fichier"""
        try:
            os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH)
        except Exception as e:
            logger.warning(f"Impossible de définir les permissions pour {filepath}: {e}")

# ==== LOGGING ====
def setup_logging():
    """Configure le système de logging de manière autonome"""
    # Créer un logger temporaire pour la configuration initiale
    temp_logger = logging.getLogger('temp')
    temp_logger.setLevel(logging.INFO)
    
    log_dir = DBConfig.get_app_dir()
    log_path = os.path.join(log_dir, f"{DBConfig.APP_NAME}.log")
    
    try:
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            encoding='utf-8'
        )
        # Configurer les permissions du fichier de log
        try:
            os.chmod(log_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
        except Exception:
            pass
        
        logger = logging.getLogger(__name__)
        logger.info("Logging configuré avec succès")
        return logger
    except Exception as e:
        # Fallback: logging vers la console
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        logger.error("Erreur configuration logging: %s", str(e))
        return logger

# Initialisation du logger en premier
logger = setup_logging()


# ==== GESTION DES CONNEXIONS ====
class DBManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_pool()
        return cls._instance
    
    def _init_pool(self):
        self._pool = []
        self._max_connections = DBConfig.MAX_CONNECTIONS
        self._timeout = DBConfig.CONNECTION_TIMEOUT
        
    @contextmanager
    def get_connection(self) -> Iterator[sqlite3.Connection]:
        """Gestionnaire de contexte pour les connexions à la base de données"""
        conn = None
        try:
            if len(self._pool) < self._max_connections:
                conn = sqlite3.connect(
                    DBConfig.get_db_path(),
                    timeout=self._timeout,
                    detect_types=sqlite3.PARSE_DECLTYPES,
                    isolation_level='IMMEDIATE'
                )
                # Configuration SQLite optimisée
                conn.execute("PRAGMA foreign_keys = ON")
                conn.execute("PRAGMA journal_mode = WAL")
                conn.execute("PRAGMA synchronous = NORMAL")
                conn.execute("PRAGMA busy_timeout = 30000")
                conn.execute("PRAGMA cache_size = -10000")  # 10MB cache
            else:
                conn = self._pool.pop()
            
            yield conn
            self._pool.append(conn)
            
        except Exception as e:
            if conn:
                conn.close()
            logger.error("Erreur connexion DB: %s", str(e))
            raise

@contextmanager
def connexion_db() -> Iterator[sqlite3.Connection]:
    """Fournit une connexion temporaire avec gestion automatique (compatibilité ascendante)"""
    with DBManager().get_connection() as conn:
        yield conn

def diagnostiquer_blocage(chemin_db: str) -> str:
    """Diagnostique les problèmes de blocage de la base"""
    diagnostics = []
    
    if not os.path.exists(chemin_db):
        return "La base de données n'existe pas"

    try:
        if not os.access(chemin_db, os.R_OK | os.W_OK):
            diagnostics.append("Permissions insuffisantes")
    except Exception as e:
        diagnostics.append(f"Erreur vérification permissions: {str(e)}")

    lock_files = [f"{chemin_db}-wal", f"{chemin_db}-shm", f"{chemin_db}-journal"]
    for lf in lock_files:
        if os.path.exists(lf):
            diagnostics.append(f"Fichier de lock présent: {lf}")

    try:
        for proc in psutil.process_iter(['pid', 'name', 'open_files']):
            try:
                open_files = proc.info.get('open_files')
                if open_files is not None:
                    for f in open_files or []:
                        if chemin_db in getattr(f, 'path', ''):
                            diagnostics.append(f"Processus bloquant: PID {proc.pid} ({proc.info['name']})")
            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError):
                continue
    except Exception as e:
        diagnostics.append(f"Erreur analyse processus: {str(e)}")

    try:
        conn = sqlite3.connect(f"file:{chemin_db}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        diagnostics.append(f"Mode journal: {cursor.fetchone()[0]}")
        cursor.execute("PRAGMA busy_timeout")
        diagnostics.append(f"Busy timeout: {cursor.fetchone()[0]}ms")
        conn.close()
    except Exception as e:
        diagnostics.append(f"Erreur vérification SQLite: {str(e)}")

    return "\n► ".join(["Diagnostic:"] + diagnostics) if diagnostics else "Aucun problème détecté"

# ==== FONCTIONS UTILITAIRES ====
def resource_path(relative_path: str) -> str:
    """Gestion des ressources pour PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

def hash_password(password: str) -> Tuple[str, str]:
    """Hash un mot de passe avec un salt aléatoire (version sécurisée)"""
    salt = binascii.hexlify(os.urandom(16)).decode()
    pwdhash = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return binascii.hexlify(pwdhash).decode(), salt

def verify_password(stored_hash: str, salt: str, provided_password: str) -> bool:
    """Vérifie un mot de passe contre le hash stocké"""
    pwdhash = hashlib.pbkdf2_hmac('sha256', provided_password.encode(), salt.encode(), 100000)
    return stored_hash == binascii.hexlify(pwdhash).decode()

def generate_unique_id(prefix: str = "CLI") -> str:
    """Génère un identifiant unique avec préfixe"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = random.randint(1000, 9999)
    return f"{prefix}-{timestamp}-{random_part}"

def generer_numero_client_unique() -> str:
    """Génère un numéro client unique de 4 chiffres"""
    with DBManager().get_connection() as conn:
        cur = conn.cursor()
        while True:
            numero = str(random.randint(1000, 9999))
            cur.execute("SELECT COUNT(*) FROM abonne WHERE numero_client = ?", (numero,))
            if cur.fetchone()[0] == 0:
                return numero

def generer_numero_carte_unique() -> str:
    """Génère un numéro de carte unique de 10 chiffres"""
    with DBManager().get_connection() as conn:
        cur = conn.cursor()
        while True:
            numero = str(random.randint(1000000000, 9999999999))
            cur.execute("SELECT COUNT(*) FROM abonne WHERE numero_carte = ?", (numero,))
            if cur.fetchone()[0] == 0:
                return numero

def create_default_avatar(name: str, size: Tuple[int, int] = (60, 60)) -> Image.Image:
    """Crée un avatar par défaut avec les initiales"""
    colors = ["#FF5733", "#33FF57", "#3357FF", "#F333FF"]
    bg_color = colors[random.randint(0, len(colors)-1)]
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
    
    return img

def ajouter_agent(nom: str, identifiant: str, mot_de_passe: str, 
                 role: str = 'agent', photo: Optional[Union[str, bytes]] = None) -> bool:
    """Ajoute un nouvel agent avec gestion améliorée de la photo"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            
            # Convertir la photo en BLOB si c'est un chemin
            photo_blob = None
            if isinstance(photo, str) and os.path.exists(photo):
                with open(photo, 'rb') as f:
                    photo_blob = f.read()
            elif isinstance(photo, bytes):
                photo_blob = photo
            
            # Hashage du mot de passe (correction ici - on prend juste le hash, pas le tuple complet)
            mdp_hash, salt = hash_password(mot_de_passe)
            
            cur.execute("""
                INSERT INTO agent (
                    nom_agent, identifiant, mot_de_passe, salt, photo, role, date_creation
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                nom, 
                identifiant, 
                mdp_hash,  # Juste le hash
                salt,      # Le salt séparément
                photo_blob, 
                role, 
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            
            conn.commit()
            ajouter_journal("Ajout agent", "Système", cible=nom)
            return True
            
    except sqlite3.IntegrityError:
        print(f"Erreur: Identifiant '{identifiant}' déjà utilisé")
        return False
    except Exception as e:
        print(f"Erreur ajout agent: {e}")
        return False

def creer_compte_agent(nom: str, identifiant: str, mot_de_passe: str, 
                      role: str = 'agent', photo_path: Optional[str] = None) -> bool:
    """
    Crée un nouveau compte agent avec photo de manière sécurisée
    
    Args:
        nom: Nom complet de l'agent
        identifiant: Identifiant de connexion unique
        mot_de_passe: Mot de passe en clair (sera haché)
        role: Rôle de l'agent (par défaut 'agent')
        photo_path: Chemin vers la photo de profil (optionnel)
    
    Returns:
        bool: True si la création a réussi, False sinon
    """
    try:
        # Vérification des paramètres obligatoires
        if not all([nom, identifiant, mot_de_passe]):
            raise ValueError("Nom, identifiant et mot de passe sont obligatoires")
        
        # Conversion de la photo en BLOB si le chemin est fourni
        photo_blob = None
        if photo_path:
            if not os.path.exists(photo_path):
                logger.warning(f"Le fichier photo {photo_path} n'existe pas")
            else:
                try:
                    with open(photo_path, 'rb') as f:
                        photo_blob = f.read()
                    # Validation de la taille de la photo (max 2MB)
                    if len(photo_blob) > 2 * 1024 * 1024:
                        raise ValueError("La photo ne doit pas dépasser 2MB")
                except Exception as e:
                    logger.error(f"Erreur lecture photo: {e}")
                    photo_blob = None
        
        # Hachage sécurisé du mot de passe
        mdp_hash, salt = hash_password(mot_de_passe)
        
        with DBManager().get_connection() as conn:
            conn.execute("BEGIN")
            cur = conn.cursor()
            
            # Vérification si l'identifiant existe déjà
            cur.execute("SELECT COUNT(*) FROM agent WHERE identifiant = ?", (identifiant,))
            if cur.fetchone()[0] > 0:
                raise sqlite3.IntegrityError("Identifiant déjà utilisé")
            
            # Insertion du nouvel agent
            cur.execute("""
                INSERT INTO agent (
                    nom_agent, identifiant, mot_de_passe, salt, 
                    photo, role, date_creation, actif
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                nom.strip(),
                identifiant.strip(),
                mdp_hash,  # Juste le hash, pas le tuple
                salt,
                photo_blob,
                role.strip(),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                1  # Compte actif par défaut
            ))
            
            conn.commit()
            logger.info(f"Nouvel agent créé: {identifiant}")
            
            # Journalisation de l'action
            ajouter_journal(
                action="Création compte agent",
                acteur="Système",
                cible=identifiant,
                details=f"Rôle: {role}"
            )
            
            return True
            
    except sqlite3.IntegrityError as e:
        logger.error(f"Erreur intégrité: {str(e)}")
        if conn:
            conn.rollback()
        raise ValueError("Cet identifiant est déjà utilisé") from e
    except ValueError as e:
        logger.error(f"Erreur validation: {str(e)}")
        if conn:
            conn.rollback()
        raise
    except Exception as e:
        logger.error(f"Erreur création compte: {str(e)}", exc_info=True)
        if conn:
            conn.rollback()
        raise RuntimeError("Erreur lors de la création du compte") from e


def blob_to_photoimage(blob_data: bytes, size: Tuple[int, int] = (60, 60)) -> Optional[Image.Image]:
    """Convertit des données BLOB en image PIL"""
    if not blob_data:
        return None
        
    try:
        img = Image.open(io.BytesIO(blob_data))
        img = img.resize(size, Image.LANCZOS)
        return img
    except Exception as e:
        logger.error(f"Erreur conversion photo: {e}")
        return None

# ==== INITIALISATION DE LA BASE ====
def initialiser_base() -> bool:
    """
    Initialise la base de données si elle n'existe pas
    Retourne True si l'initialisation a réussi ou si la base existait déjà
    """
    try:
        db_path = DBConfig.get_db_path()
        
        # Si la base existe déjà, vérifier sa structure
        if os.path.exists(db_path):
            with DBManager().get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='abonne'")
                if cur.fetchone():
                    return True  # La base existe et a la bonne structure
        
        # Créer une nouvelle base
        create_empty_db(db_path)
        return True
        
    except Exception as e:
        logger.error("Erreur initialisation base: %s", str(e), exc_info=True)
        return False

def create_empty_db(db_path: str):
    """Crée une base de données vide avec le schéma approprié"""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            
            # Création des tables
            conn.executescript("""
            -- Table principale des abonnés
            CREATE TABLE IF NOT EXISTS abonne (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_client TEXT UNIQUE NOT NULL,
                numero_carte TEXT UNIQUE NOT NULL,
                nom TEXT NOT NULL,
                postnom TEXT,
                prenom TEXT NOT NULL,
                sexe TEXT CHECK(sexe IN ('M', 'F')) NOT NULL,
                date_naissance TEXT NOT NULL,
                lieu_naissance TEXT NOT NULL,
                adresse TEXT NOT NULL,
                telephone TEXT NOT NULL CHECK(length(telephone) = 10),
                date_inscription TEXT NOT NULL,
                statut TEXT DEFAULT 'Actif' CHECK(statut IN ('Actif', 'Inactif', 'Bloqué')),
                photo_path TEXT,
                UNIQUE(nom, postnom, prenom, telephone)
            );

            -- Table des suppléants
            CREATE TABLE IF NOT EXISTS suppleant (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                abonne_id INTEGER NOT NULL,
                nom TEXT NOT NULL,
                telephone TEXT NOT NULL,
                FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE,
                UNIQUE(abonne_id, nom)
            );
            
            CREATE TABLE IF NOT EXISTS agent (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom_agent TEXT NOT NULL,
                identifiant TEXT UNIQUE NOT NULL,
                mot_de_passe TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT DEFAULT 'agent',
                date_creation TEXT,
                actif INTEGER DEFAULT 1,
                photo BLOB
            );

            -- Table des types de compte
            CREATE TABLE IF NOT EXISTS type_compte (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nom TEXT UNIQUE NOT NULL CHECK(nom IN ('Fixe', 'Mixte', 'Bloqué')),
                description TEXT
            );

            -- Table de liaison abonne-type_compte
            CREATE TABLE IF NOT EXISTS abonne_compte (
                abonne_id INTEGER NOT NULL,
                type_compte_id INTEGER NOT NULL,
                date_activation TEXT NOT NULL,
                solde REAL DEFAULT 0,
                PRIMARY KEY (abonne_id, type_compte_id),
                FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE,
                FOREIGN KEY (type_compte_id) REFERENCES type_compte(id)
            );

            -- Table spécifique aux comptes bloqués
            CREATE TABLE IF NOT EXISTS compte_bloque (
                abonne_id INTEGER PRIMARY KEY,
                duree_mois INTEGER NOT NULL CHECK(duree_mois > 0),
                montant_atteindre REAL NOT NULL CHECK(montant_atteindre > 0),
                pourcentage_retrait INTEGER NOT NULL CHECK(pourcentage_retrait BETWEEN 1 AND 100),
                frequence_retrait TEXT NOT NULL CHECK(frequence_retrait IN ('Mensuel', 'Trimestriel', 'Semestriel', 'Annuel')),
                FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE
            );

            -- Table spécifique aux comptes fixes
            CREATE TABLE IF NOT EXISTS compte_fixe (
                abonne_id INTEGER PRIMARY KEY,
                montant_initial REAL NOT NULL CHECK(montant_initial > 0),
                date_debut TEXT NOT NULL,
                date_fin TEXT NOT NULL,
                FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE
            );
            
            CREATE TABLE IF NOT EXISTS depots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_client TEXT NOT NULL,
                montant REAL NOT NULL,
                ref_depot TEXT UNIQUE,
                heure TEXT NOT NULL,
                nom_complet TEXT,
                date_depot TEXT NOT NULL,
                nom_agent TEXT NOT NULL,
                methode_paiement TEXT,
                FOREIGN KEY (numero_client) REFERENCES abonne(numero_client)
            );
            
            CREATE TABLE IF NOT EXISTS retraits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_client TEXT NOT NULL,
                montant REAL NOT NULL,
                ref_retrait TEXT UNIQUE,
                heure TEXT NOT NULL,
                date_retrait TEXT NOT NULL,
                agent TEXT NOT NULL,
                statut TEXT DEFAULT 'En attente',
                FOREIGN KEY (numero_client) REFERENCES abonne(numero_client)
            );

            -- Pages des carnets fixes
            CREATE TABLE IF NOT EXISTS compte_fixe_page (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                compte_fixe_id INTEGER NOT NULL,
                numero_page INTEGER NOT NULL CHECK(numero_page BETWEEN 1 AND 8),
                cases_remplies INTEGER DEFAULT 0 CHECK(cases_remplies BETWEEN 0 AND 31),
                FOREIGN KEY (compte_fixe_id) REFERENCES compte_fixe(abonne_id) ON DELETE CASCADE,
                UNIQUE(compte_fixe_id, numero_page)
            );

            -- Transactions
            CREATE TABLE IF NOT EXISTS transaction (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                abonne_id INTEGER NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('Dépôt', 'Retrait')),
                montant REAL NOT NULL CHECK(montant > 0),
                date TEXT NOT NULL,
                heure TEXT NOT NULL,
                agent TEXT NOT NULL,
                statut TEXT DEFAULT 'Complété' CHECK(statut IN ('Complété', 'En attente', 'Annulé')),
                reference TEXT UNIQUE NOT NULL,
                methode_paiement TEXT,
                FOREIGN KEY (abonne_id) REFERENCES abonne(id)
            );

            -- Journal d'audit
            CREATE TABLE IF NOT EXISTS journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                acteur TEXT NOT NULL,
                date_action TEXT NOT NULL,
                heure_action TEXT NOT NULL,
                cible TEXT,
                details TEXT,
                ip_address TEXT,
                user_agent TEXT
            );

            -- Index pour les recherches fréquentes
            CREATE INDEX IF NOT EXISTS idx_abonne_nom ON abonne(nom, postnom);
            CREATE INDEX IF NOT EXISTS idx_abonne_telephone ON abonne(telephone);
            CREATE INDEX IF NOT EXISTS idx_transaction_date ON transaction(date);
            CREATE INDEX IF NOT EXISTS idx_transaction_abonne ON transaction(abonne_id);
            CREATE INDEX IF NOT EXISTS idx_journal_date ON journal(date_action);

            -- Données de base
            INSERT OR IGNORE INTO type_compte (nom, description) VALUES 
                ('Fixe', 'Compte avec montant fixe à épargner'),
                ('Mixte', 'Compte flexible avec options variées'),
                ('Bloqué', 'Compte avec montant bloqué pour une durée déterminée');
            """)
            
            conn.commit()
            DBConfig.set_file_permissions(db_path)
            logger.info("Base de données vide créée avec succès")
    except Exception as e:
        logger.error("Erreur création DB: %s", str(e), exc_info=True)
        raise

def copy_db_from_resources():
    """Copie la DB depuis les ressources si nécessaire"""
    src_db = resource_path(DBConfig.DB_NAME)
    dest_db = DBConfig.get_db_path()
    
    if os.path.exists(dest_db):
        return
    
    try:
        if os.path.exists(src_db):
            shutil.copy2(src_db, dest_db)
            DBConfig.set_file_permissions(dest_db)
            logger.info("Base de données copiée depuis les ressources")
        else:
            create_empty_db(dest_db)
    except Exception as e:
        logger.error("Erreur copie DB: %s", str(e), exc_info=True)
        raise

def cleanup_lock_files():
    """Nettoie les fichiers de verrouillage SQLite qui pourraient rester"""
    db_path = DBConfig.get_db_path()
    lock_files = [
        f"{db_path}-wal",
        f"{db_path}-shm",
        f"{db_path}-journal"
    ]
    
    for lf in lock_files:
        try:
            if os.path.exists(lf):
                os.remove(lf)
                logger.info(f"Fichier de verrouillage supprimé: {lf}")
        except Exception as e:
            logger.warning(f"Impossible de supprimer le fichier de verrouillage {lf}: {e}")

# ==== FONCTIONS MÉTIER ====
def creer_abonne(data: Dict) -> Tuple[bool, str]:
    """Crée un nouvel abonné dans la base de données"""
    try:
        with DBManager().get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.cursor()
            
            # Générer les identifiants uniques
            numero_client = generate_unique_id("CLI")
            numero_carte = generate_unique_id("CART")
            
            # 1. Insérer l'abonné de base
            cur.execute("""
                INSERT INTO abonne (
                    numero_client, numero_carte, nom, postnom, prenom,
                    sexe, date_naissance, lieu_naissance, adresse,
                    telephone, date_inscription, statut, photo_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                RETURNING id
            """, (
                numero_client,
                numero_carte,
                data['nom'],
                data['postnom'],
                data['prenom'],
                data['sexe'],
                data['date_naissance'],
                data['lieu_naissance'],
                data['adresse'],
                data['telephone'],
                datetime.now().strftime("%Y-%m-%d"),
                'Actif',
                data.get('photo', '')
            ))
            
            abonne_id = cur.fetchone()[0]
            
            # 2. Insérer le suppléant si fourni
            if data.get('suppleant') and data.get('contact_suppleant'):
                cur.execute("""
                    INSERT INTO suppleant (abonne_id, nom, telephone)
                    VALUES (?, ?, ?)
                """, (
                    abonne_id,
                    data['suppleant'],
                    data['contact_suppleant']
                ))
            
            # 3. Lier le type de compte
            cur.execute("SELECT id FROM type_compte WHERE nom = ?", (data['type_compte'],))
            type_compte_id = cur.fetchone()[0]
            
            cur.execute("""
                INSERT INTO abonne_compte (
                    abonne_id, type_compte_id, date_activation, solde
                ) VALUES (?, ?, ?, ?)
            """, (
                abonne_id,
                type_compte_id,
                datetime.now().strftime("%Y-%m-%d"),
                data.get('montant', 0)
            ))
            
            # 4. Gestion spécifique au type de compte
            if data['type_compte'] == 'Bloqué':
                cur.execute("""
                    INSERT INTO compte_bloque (
                        abonne_id, duree_mois, montant_atteindre,
                        pourcentage_retrait, frequence_retrait
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    abonne_id,
                    int(data.get('duree_blocage', 3)),
                    float(data.get('montant_atteindre', 0)),
                    int(data.get('pourcentage_retrait', 30)),
                    data.get('frequence_retrait', 'Mensuel')
                ))
            elif data['type_compte'] == 'Fixe':
                date_fin = (datetime.now() + datetime.timedelta(days=365)).strftime("%Y-%m-%d")
                cur.execute("""
                    INSERT INTO compte_fixe (
                        abonne_id, montant_initial, date_debut, date_fin
                    ) VALUES (?, ?, ?, ?)
                """, (
                    abonne_id,
                    float(data.get('montant', 0)),
                    datetime.now().strftime("%Y-%m-%d"),
                    date_fin
                ))
                
                # Initialiser les pages du carnet
                for page in range(1, 9):
                    cur.execute("""
                        INSERT INTO compte_fixe_page (
                            compte_fixe_id, numero_page, cases_remplies
                        ) VALUES (?, ?, ?)
                    """, (abonne_id, page, 0))
            
            # Journaliser l'action
            ajouter_journal(
                "Création abonné",
                data.get('agent', 'Système'),
                numero_client,
                f"Nouvel abonné {data['nom']} {data['prenom']}"
            )
            
            conn.commit()
            return True, numero_client
            
    except sqlite3.IntegrityError as e:
        conn.rollback()
        logger.error("Erreur intégrité création abonné: %s", str(e))
        return False, f"Erreur de données: {str(e)}"
    except Exception as e:
        conn.rollback()
        logger.error("Erreur création abonné: %s", str(e), exc_info=True)
        return False, f"Erreur système: {str(e)}"

def effectuer_depot(abonne_id: int, montant: float, agent: str) -> Tuple[bool, str]:
    """Effectue un dépôt pour un client"""
    reference = f"DEP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
    
    try:
        with DBManager().get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.cursor()
            
            # 1. Vérifier que l'abonné existe et est actif
            cur.execute("""
                SELECT a.id, ac.solde, tc.nom 
                FROM abonne a
                JOIN abonne_compte ac ON a.id = ac.abonne_id
                JOIN type_compte tc ON ac.type_compte_id = tc.id
                WHERE a.id = ? AND a.statut = 'Actif'
            """, (abonne_id,))
            
            if not (abonne := cur.fetchone()):
                raise ValueError("Abonné introuvable ou inactif")
            
            _, ancien_solde, type_compte = abonne
            
            # 2. Mettre à jour le solde
            cur.execute("""
                UPDATE abonne_compte 
                SET solde = solde + ?
                WHERE abonne_id = ?
                RETURNING solde
            """, (montant, abonne_id))
            
            nouveau_solde = cur.fetchone()[0]
            
            # 3. Enregistrer la transaction
            cur.execute("""
                INSERT INTO transaction (
                    abonne_id, type, montant, date, heure, agent, reference
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                abonne_id, 
                'Dépôt', 
                montant,
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%H:%M:%S"),
                agent,
                reference
            ))
            
            # 4. Journaliser
            ajouter_journal(
                "Dépôt effectué",
                agent,
                str(abonne_id),
                f"Dépôt de {montant} FC. Type: {type_compte}. Nouveau solde: {nouveau_solde}"
            )
            
            conn.commit()
            return True, reference
            
    except ValueError as e:
        conn.rollback()
        logger.warning("Dépôt refusé: %s", str(e))
        return False, str(e)
    except sqlite3.Error as e:
        conn.rollback()
        logger.error("Erreur dépôt DB: %s", str(e))
        return False, f"Erreur base de données: {str(e)}"
    except Exception as e:
        conn.rollback()
        logger.error("Erreur dépôt: %s", str(e), exc_info=True)
        return False, f"Erreur système: {str(e)}"

def effectuer_retrait(abonne_id: int, montant: float, agent: str) -> Tuple[bool, str]:
    """Effectue un retrait pour un client"""
    reference = f"RET-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
    
    try:
        with DBManager().get_connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.cursor()
            
            # 1. Vérifier l'éligibilité au retrait
            cur.execute("""
                SELECT a.id, ac.solde, tc.nom, 
                       cb.pourcentage_retrait, cb.montant_atteindre
                FROM abonne a
                JOIN abonne_compte ac ON a.id = ac.abonne_id
                JOIN type_compte tc ON ac.type_compte_id = tc.id
                LEFT JOIN compte_bloque cb ON a.id = cb.abonne_id
                WHERE a.id = ? AND a.statut = 'Actif'
            """, (abonne_id,))
            
            if not (abonne := cur.fetchone()):
                raise ValueError("Abonné introuvable ou inactif")
            
            _, solde, type_compte, pourcentage, montant_atteindre = abonne
            
            # 2. Vérifier les règles selon le type de compte
            if type_compte == 'Bloqué':
                if solde < montant_atteindre:
                    raise ValueError(f"Le solde ({solde}) n'a pas atteint le montant requis ({montant_atteindre})")
                
                montant_max = solde * (pourcentage / 100)
                if montant > montant_max:
                    raise ValueError(f"Montant dépasse le plafond de {pourcentage}% du solde (max: {montant_max})")
            
            elif solde < montant:
                raise ValueError("Solde insuffisant")
            
            # 3. Mettre à jour le solde
            cur.execute("""
                UPDATE abonne_compte 
                SET solde = solde - ?
                WHERE abonne_id = ?
                RETURNING solde
            """, (montant, abonne_id))
            
            nouveau_solde = cur.fetchone()[0]
            
            # 4. Enregistrer la transaction
            cur.execute("""
                INSERT INTO transaction (
                    abonne_id, type, montant, date, heure, agent, reference, statut
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                abonne_id, 
                'Retrait', 
                montant,
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%H:%M:%S"),
                agent,
                reference,
                'Complété'
            ))
            
            # 5. Journaliser
            ajouter_journal(
                "Retrait effectué",
                agent,
                str(abonne_id),
                f"Retrait de {montant} FC. Type: {type_compte}. Nouveau solde: {nouveau_solde}"
            )
            
            conn.commit()
            return True, reference
            
    except ValueError as e:
        conn.rollback()
        logger.warning("Retrait refusé: %s", str(e))
        return False, str(e)
    except sqlite3.Error as e:
        conn.rollback()
        logger.error("Erreur retrait DB: %s", str(e))
        return False, f"Erreur base de données: {str(e)}"
    except Exception as e:
        conn.rollback()
        logger.error("Erreur retrait: %s", str(e), exc_info=True)
        return False, f"Erreur système: {str(e)}"

def ajouter_journal(action: str, acteur: str, cible: Optional[str] = None, 
                   details: Optional[str] = None) -> bool:
    """Ajoute une entrée dans le journal"""
    try:
        with DBManager().get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO journal (
                    action, acteur, cible, details, 
                    date_action, heure_action
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                action, 
                acteur, 
                cible, 
                details,
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%H:%M:%S")
            ))
            conn.commit()
            return True
    except Exception as e:
        logger.error("Erreur journalisation: %s", str(e))
        return False

def creer_agent(nom: str, identifiant: str, mot_de_passe: str, 
                role: str = "agent", photo: Optional[bytes] = None) -> bool:
    """Crée un nouvel agent avec mot de passe sécurisé"""
    try:
        mot_de_passe_hash, salt = hash_password(mot_de_passe)
        
        with DBManager().get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO agent (
                    nom, identifiant, mot_de_passe, salt,
                    role, date_creation, photo
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                nom,
                identifiant,
                mot_de_passe_hash,
                salt,
                role,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                photo
            ))
            conn.commit()
            
            ajouter_journal(
                "Création agent",
                "Système",
                identifiant,
                f"Nouvel agent {nom} avec rôle {role}"
            )
            return True
    except sqlite3.IntegrityError:
        logger.warning("Identifiant agent déjà existant: %s", identifiant)
        return False
    except Exception as e:
        logger.error("Erreur création agent: %s", str(e))
        return False

def authentifier_agent(identifiant: str, mot_de_passe: str) -> Optional[Dict]:
    """Authentifie un agent"""
    try:
        with DBManager().get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, nom, mot_de_passe, salt, role, photo 
                FROM agent 
                WHERE identifiant = ? AND actif = 1
            """, (identifiant,))
            
            if row := cur.fetchone():
                id_agent, nom, stored_hash, salt, role, photo = row
                if verify_password(stored_hash, salt, mot_de_passe):
                    ajouter_journal(
                        "Connexion",
                        identifiant,
                        None,
                        "Connexion réussie"
                    )
                    return {
                        'id': id_agent,
                        'nom': nom,
                        'role': role,
                        'photo': photo
                    }
            
            ajouter_journal(
                "Tentative connexion",
                identifiant,
                None,
                "Échec authentification"
            )
            return None
    except Exception as e:
        logger.error("Erreur authentification: %s", str(e))
        return None

def get_abonne(abonne_id: int) -> Optional[Dict]:
    """Récupère les informations complètes d'un abonné"""
    try:
        with DBManager().get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # Informations de base
            cur.execute("""
                SELECT a.*, 
                       GROUP_CONCAT(s.nom, '|') as suppleants,
                       GROUP_CONCAT(s.telephone, '|') as contacts_suppleants
                FROM abonne a
                LEFT JOIN suppleant s ON a.id = s.abonne_id
                WHERE a.id = ?
                GROUP BY a.id
            """, (abonne_id,))
            
            if not (abonne := cur.fetchone()):
                return None
            
            result = dict(abonne)
            
            # Détails du type de compte
            cur.execute("""
                SELECT tc.nom as type_compte, ac.solde
                FROM abonne_compte ac
                JOIN type_compte tc ON ac.type_compte_id = tc.id
                WHERE ac.abonne_id = ?
            """, (abonne_id,))
            
            if compte := cur.fetchone():
                result.update(dict(compte))
                
                # Détails spécifiques au type de compte
                if compte['type_compte'] == 'Bloqué':
                    cur.execute("""
                        SELECT * FROM compte_bloque 
                        WHERE abonne_id = ?
                    """, (abonne_id,))
                    if blocage := cur.fetchone():
                        result.update(dict(blocage))
                
                elif compte['type_compte'] == 'Fixe':
                    cur.execute("""
                        SELECT cf.*, 
                               SUM(cfp.cases_remplies) as total_cases,
                               COUNT(CASE WHEN cfp.cases_remplies = 31 THEN 1 END) as pages_completes
                        FROM compte_fixe cf
                        LEFT JOIN compte_fixe_page cfp ON cf.abonne_id = cfp.compte_fixe_id
                        WHERE cf.abonne_id = ?
                    """, (abonne_id,))
                    if fixe := cur.fetchone():
                        result.update(dict(fixe))
            
            # Dernières transactions
            cur.execute("""
                SELECT * FROM transaction
                WHERE abonne_id = ?
                ORDER BY date DESC, heure DESC
                LIMIT 5
            """, (abonne_id,))
            result['transactions'] = [dict(row) for row in cur.fetchall()]
            
            return result
            
    except Exception as e:
        logger.error("Erreur récupération abonné: %s", str(e))
        return None

def initialiser_pages_compte_fixe(numero_carte: str) -> bool:
    logger.debug(f"Tentative d'initialisation des pages pour {numero_carte}")
    try:
        with DBManager().get_connection() as conn:
            cur = conn.cursor()
            
            # 1. Vérifier que le compte fixe existe et récupérer le numéro client
            cur.execute("SELECT numero_client FROM compte_fixe WHERE numero_carte = ?", (numero_carte,))
            result = cur.fetchone()
            
            if not result:
                logger.error(f"Aucun compte fixe trouvé pour la carte {numero_carte}")
                return False
                
            numero_client = result[0]
            
            # 2. Vérifier si les pages existent déjà
            cur.execute("SELECT COUNT(*) FROM compte_fixe_pages WHERE numero_carte = ?", (numero_carte,))
            if cur.fetchone()[0] > 0:
                logger.warning(f"Pages déjà existantes pour {numero_carte}")
                return False
                
            # 3. Initialiser les 8 pages avec le numéro client
            for page in range(1, 9):
                cur.execute("""
                    INSERT INTO compte_fixe_pages (numero_carte, numero_client, page, cases_remplies)
                    VALUES (?, ?, ?, 0)
                """, (numero_carte, numero_client, page))
                
            conn.commit()
            logger.info(f"Pages initialisées avec succès pour {numero_carte} (client: {numero_client})")
            return True
            
    except Exception as e:
        logger.error(f"Erreur lors de l'initialisation des pages pour {numero_carte}: {str(e)}", exc_info=True)
        return False

def corriger_comptes_fixes_existants() -> int:
    """Corrige les comptes fixes existants en ajoutant le numéro client dans les pages"""
    logger.info("Début de la correction des comptes fixes existants")
    try:
        with DBManager().get_connection() as conn:
            cur = conn.cursor()
            
            # 1. Récupérer tous les comptes fixes
            cur.execute("SELECT numero_carte, numero_client FROM compte_fixe")
            comptes = cur.fetchall()
            
            comptes_corriges = 0
            
            for numero_carte, numero_client in comptes:
                try:
                    # 2. Vérifier si les pages ont besoin d'être corrigées
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM compte_fixe_pages 
                        WHERE numero_carte = ? AND numero_client IS NULL
                    """, (numero_carte,))
                    
                    count = cur.fetchone()[0]
                    if count > 0:
                        # 3. Mettre à jour les pages existantes
                        cur.execute("""
                            UPDATE compte_fixe_pages
                            SET numero_client = ?
                            WHERE numero_carte = ? AND numero_client IS NULL
                        """, (numero_client, numero_carte))
                        comptes_corriges += 1
                        logger.debug(f"Compte {numero_carte} corrigé (client: {numero_client})")
                    
                except Exception as e:
                    logger.error(f"Erreur correction compte {numero_carte}: {str(e)}", exc_info=True)
                    conn.rollback()
                    continue
                
            conn.commit()
            logger.info(f"{comptes_corriges}/{len(comptes)} comptes fixes corrigés")
            return comptes_corriges
            
    except Exception as e:
        logger.error(f"Erreur globale correction comptes: {str(e)}", exc_info=True)
        return 0

def rechercher_abonnes(criteres: Dict) -> List[Dict]:
    """Recherche des abonnés selon plusieurs critères"""
    try:
        with DBManager().get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            query = """
                SELECT a.id, a.numero_client, a.nom, a.postnom, a.prenom, 
                       a.telephone, a.date_inscription, a.statut,
                       tc.nom as type_compte, ac.solde
                FROM abonne a
                JOIN abonne_compte ac ON a.id = ac.abonne_id
                JOIN type_compte tc ON ac.type_compte_id = tc.id
                WHERE 1=1
            """
            params = []
            
            # Construction dynamique de la requête
            if nom := criteres.get('nom'):
                query += " AND (a.nom LIKE ? OR a.postnom LIKE ? OR a.prenom LIKE ?)"
                params.extend([f"%{nom}%", f"%{nom}%", f"%{nom}%"])
            
            if telephone := criteres.get('telephone'):
                query += " AND a.telephone LIKE ?"
                params.append(f"%{telephone}%")
            
            if type_compte := criteres.get('type_compte'):
                query += " AND tc.nom = ?"
                params.append(type_compte)
            
            if statut := criteres.get('statut'):
                query += " AND a.statut = ?"
                params.append(statut)
            
            if date_debut := criteres.get('date_debut'):
                query += " AND a.date_inscription >= ?"
                params.append(date_debut)
            
            if date_fin := criteres.get('date_fin'):
                query += " AND a.date_inscription <= ?"
                params.append(date_fin)
            
            query += " ORDER BY a.nom, a.postnom"
            
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
            
    except Exception as e:
        logger.error("Erreur recherche abonnés: %s", str(e))
        return []

# ==== SAUVEGARDE ET MAINTENANCE ====
def backup_database() -> bool:
    """Crée une sauvegarde chiffrée de la base de données"""
    original_path = DBConfig.get_db_path()
    backup_dir = os.path.join(DBConfig.get_app_dir(), "backups")
    os.makedirs(backup_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"backup_{timestamp}.db")
    
    try:
        # Utilisation de la copie atomique de SQLite
        with sqlite3.connect(original_path) as conn:
            conn.execute(f"VACUUM INTO '{backup_path}'")
        
        # Chiffrement optionnel (nécessite pycryptodome)
        try:
            from Crypto.Cipher import AES
            from Crypto.Util.Padding import pad
            
            key = os.urandom(32)  # Clé AES-256
            cipher = AES.new(key, AES.MODE_CBC)
            
            with open(backup_path, 'rb') as f:
                data = f.read()
            
            # Padding des données
            padded_data = pad(data, AES.block_size)
            
            # Chiffrement
            encrypted_data = cipher.iv + cipher.encrypt(padded_data)
            
            # Sauvegarde de la clé
            key_path = os.path.join(backup_dir, f"backup_{timestamp}.key")
            with open(key_path, 'wb') as f:
                f.write(key)
            
            # Écriture des données chiffrées
            encrypted_path = os.path.join(backup_dir, f"backup_{timestamp}.enc")
            with open(encrypted_path, 'wb') as f:
                f.write(encrypted_data)
            
            # Suppression du fichier non chiffré
            os.remove(backup_path)
            
        except ImportError:
            pass
            
        logger.info(f"Sauvegarde créée: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Erreur sauvegarde: {str(e)}", exc_info=True)
        return False

def reinitialiser_mot_de_passe(identifiant: str, nouveau_mot_de_passe: str) -> bool:
    """Réinitialise le mot de passe d'un agent"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            mdp_hash = hash_password(nouveau_mot_de_passe)
            cur.execute("UPDATE agent SET mot_de_passe = ? WHERE identifiant = ?", 
                       (mdp_hash, identifiant))
            conn.commit()
            return cur.rowcount > 0
    except sqlite3.Error as e:
        print(f"Erreur réinitialisation mot de passe: {e}")
        return False

def get_all_abonnes() -> List[Dict]:
    """Récupère tous les abonnés"""
    try:
        with connexion_db() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM abonne
                ORDER BY date_inscription DESC
            """)
            return [dict(row) for row in cur.fetchall()]
    except sqlite3.Error as e:
        print(f"Erreur récupération abonnés: {e}")
        return []

def get_all_depots() -> List[Dict]:
    """Récupère tous les dépôts"""
    try:
        with connexion_db() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM depots
                ORDER BY date_depot DESC, heure DESC
            """)
            return [dict(row) for row in cur.fetchall()]
    except sqlite3.Error as e:
        print(f"Erreur récupération dépôts: {e}")
        return []

def get_all_retraits() -> List[Dict]:
    """Récupère tous les retraits"""
    try:
        with connexion_db() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM retraits
                ORDER BY date_retrait DESC, heure DESC
            """)
            return [dict(row) for row in cur.fetchall()]
    except sqlite3.Error as e:
        print(f"Erreur récupération retraits: {e}")
        return []

def get_all_logs() -> List[Dict]:
    """Récupère tous les logs du journal"""
    try:
        with connexion_db() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM journal
                ORDER BY date_action DESC, heure_action DESC
            """)
            return [dict(row) for row in cur.fetchall()]
    except sqlite3.Error as e:
        print(f"Erreur récupération logs: {e}")
        return []

# ==================== FONCTIONS POUR LES DEPOTS ====================

def get_client_by_card(numero_carte: str) -> Optional[Dict]:
    """Trouve un client par son numéro de carte"""
    try:
        with connexion_db() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM abonne WHERE numero_carte = ?", (numero_carte,))
            return cur.fetchone()
    except sqlite3.Error as e:
        print(f"Erreur recherche client: {e}")
        return None

def ajouter_depot(numero_client: str, montant: float, ref_depot: str, 
                 heure: str, date_depot: str, nom_agent: str, 
                 methode_paiement: str = "Espèces") -> bool:
    """Ajoute un nouveau dépôt dans la base"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            
            # Vérifier que le client existe
            cur.execute("SELECT COUNT(*) FROM abonne WHERE numero_client = ?", (numero_client,))
            if cur.fetchone()[0] == 0:
                return False  # Client non trouvé
            
            # Récupérer le nom complet du client
            cur.execute("SELECT nom, postnom, prenom FROM abonne WHERE numero_client = ?", (numero_client,))
            result = cur.fetchone()
            nom_complet = ""
            if result:
                nom_complet = f"{result[2]} {result[1]} {result[0]}"  # prénom, postnom, nom
            
            # Vérifier l'unicité de la référence
            cur.execute("SELECT COUNT(*) FROM depots WHERE ref_depot = ?", (ref_depot,))
            if cur.fetchone()[0] > 0:
                return False  # Référence déjà utilisée
            
            # Insérer le dépôt
            cur.execute("""
                INSERT INTO depots (
                    numero_client, montant, ref_depot, heure, 
                    date_depot, nom_agent, methode_paiement, nom_complet
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                numero_client, montant, ref_depot, heure,
                date_depot, nom_agent, methode_paiement, nom_complet
            ))
            
            # Mettre à jour le solde du client
            cur.execute("""
                UPDATE abonne 
                SET solde = solde + ?
                WHERE numero_client = ?
            """, (montant, numero_client))
            
            conn.commit()
            ajouter_journal("Dépôt", nom_agent, cible=numero_client, details=f"Montant: {montant}, Ref: {ref_depot}")
            return True
    except sqlite3.Error as e:
        print(f"Erreur ajout dépôt: {e}")
        return False


def optimiser_base() -> bool:
    """Optimise les performances de la base de données"""
    try:
        with DBManager().get_connection() as conn:
            conn.execute("VACUUM")
            conn.execute("ANALYZE")
            conn.execute("PRAGMA optimize")
            logger.info("Base de données optimisée")
            return True
    except Exception as e:
        logger.error("Erreur optimisation DB: %s", str(e))
        return False

# ==== POINT D'ENTRÉE ====
if __name__ == "__main__":
    print("=== INITIALISATION DE L'APPLICATION ===")
    print(f"📂 Dossier application: {DBConfig.get_app_dir()}")
    print(f"📄 Chemin base de données: {DBConfig.get_db_path()}")
    
    try:
        # Nettoyage initial
        cleanup_lock_files()
        
        # Initialisation de la base
        print("\n⚙️ Initialisation de la base...")
        initialiser_base()
        copy_db_from_resources()
        
        # Test de connexion
        with DBManager().get_connection() as conn:
            print("\n✅ Connexion à la base établie avec succès")
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM sqlite_master")
            print(f"📊 Nombre de tables: {cur.fetchone()[0]}")
        
        # Créer un admin par défaut si nécessaire
        if not authentifier_agent("admin", "admin123"):
            if creer_agent(
                nom="Administrateur",
                identifiant="admin",
                mot_de_passe="admin123",
                role="admin"
            ):
                print("\n👤 Compte admin créé (identifiant: admin, mot de passe: admin123)")
        
        print("\n🔍 Diagnostic final:")
        print(f"Taille DB: {os.path.getsize(DBConfig.get_db_path()) / 1024:.2f} KB")
        
    except Exception as e:
        print(f"\n❌ ERREUR: {str(e)}")
        logger.exception("Erreur critique lors de l'initialisation")
        sys.exit(1)