import sqlite3
import os
import sys
import hashlib
import shutil
import time
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import random
import traceback
import psutil
from typing import List, Dict, Optional, Tuple, Union
import io
import logging
import stat
import tempfile

# ==== CONFIGURATION ROBUSTE DES LOGS ====
def setup_logging():
    """Configure le logging avec plusieurs niveaux de fallback"""
    # 1. Essayer LOCALAPPDATA (recommandé par Microsoft)
    log_dir = os.path.join(os.getenv('LOCALAPPDATA', ''), 'MonLogiciel')
    log_path = os.path.join(log_dir, 'app.log')
    
    try:
        # Créer le dossier avec permissions étendues
        os.makedirs(log_dir, exist_ok=True, mode=0o777)
        
        # Tester les permissions
        with open(log_path, 'a') as test_file:
            test_file.write(f"Initialisation des logs à {datetime.now()}\n")
        
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger(__name__)
        logger.info("Logging initialisé avec succès dans %s", log_path)
        return logger
        
    except Exception as e:
        # 2. Fallback: TEMP directory
        try:
            temp_dir = tempfile.gettempdir()
            log_dir = os.path.join(temp_dir, 'MonLogiciel')
            os.makedirs(log_dir, exist_ok=True, mode=0o777)
            log_path = os.path.join(log_dir, 'app.log')
            
            logging.basicConfig(
                filename=log_path,
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s'
            )
            logger = logging.getLogger(__name__)
            logger.error("Fallback TEMP: Échec configuration log initiale: %s", str(e))
            return logger
        except:
            # 3. Fallback ultime: logging console
            logging.basicConfig(level=logging.INFO)
            logger = logging.getLogger(__name__)
            logger.error("Fallback console: Impossible de configurer le fichier log")
            return logger

logger = setup_logging()

def resource_path(relative_path: str) -> str:
    """Résout les chemins pour PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_db_path() -> str:
    """Retourne le chemin de la base de données avec gestion robuste des permissions"""
    # 1. Essayer APPDATA
    appdata_dir = os.getenv("APPDATA")
    app_folder = os.path.join(appdata_dir, "MyApp") if appdata_dir else None
    
    # 2. Fallback: TEMP directory
    if not app_folder or not os.access(os.path.dirname(app_folder), os.W_OK):
        temp_dir = tempfile.gettempdir()
        app_folder = os.path.join(temp_dir, "MyApp")
        logger.warning("Utilisation du dossier TEMP pour la base de données")
    
    # Création du répertoire avec permissions
    try:
        os.makedirs(app_folder, exist_ok=True, mode=0o777)
        # Windows: Ajouter permissions explicites
        if os.name == 'nt':
            import win32api
            import win32con
            win32api.SetFileSecurity(
                app_folder,
                win32con.DACL_SECURITY_INFORMATION,
                win32api.SECURITY_ATTRIBUTES().Initialize(
                    None, None, True, True, None, None, None, 
                    win32con.FILE_GENERIC_READ | win32con.FILE_GENERIC_WRITE
                )
            )
    except Exception as e:
        logger.error(f"Erreur création dossier: {e}")
        # Fallback ultime: dossier courant
        app_folder = os.path.abspath(".")
    
    local_db = os.path.join(app_folder, "data_epargne.db")

    # Copier la base originale si nécessaire
    if not os.path.exists(local_db):
        original_db = resource_path("data_epargne.db")
        if os.path.exists(original_db):
            try:
                shutil.copyfile(original_db, local_db)
                # Appliquer les permissions
                os.chmod(local_db, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH)
                logger.info("Base copiée de %s vers %s", original_db, local_db)
            except Exception as e:
                logger.error(f"Erreur copie DB: {e}")
                # Créer une base vide si la copie échoue
                try:
                    conn = sqlite3.connect(local_db)
                    conn.close()
                    logger.info("Base vide créée à %s", local_db)
                except Exception as e2:
                    logger.critical(f"Échec création base: {e2}")
                    raise PermissionError(f"Échec création base: {e2}")
    
    # Vérification finale des permissions
    try:
        with open(local_db, 'a') as f:
            f.write("\n")  # Test d'écriture
        logger.info("Permissions vérifiées sur %s", local_db)
    except Exception as e:
        logger.critical(f"Permissions insuffisantes sur {local_db}: {str(e)}")
        # Fallback: fichier temporaire
        local_db = os.path.join(tempfile.gettempdir(), "data_epargne.db")
        logger.error("Utilisation DB temporaire: %s", local_db)
    
    return local_db

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

def connexion_db() -> sqlite3.Connection:
    """Établit une connexion à la base de données avec gestion des erreurs"""
    chemin_db = get_db_path()
    max_attempts = 5
    
    for attempt in range(max_attempts):
        try:
            conn = sqlite3.connect(
                chemin_db,
                timeout=30,
                check_same_thread=False
            )
            
            # Configuration optimale
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA foreign_keys=ON")
            
            # Test de la connexion
            conn.execute("SELECT 1").fetchone()
            return conn
            
        except sqlite3.OperationalError as e:
            if attempt == max_attempts - 1:
                diagnostic = diagnostiquer_blocage(chemin_db)
                raise sqlite3.OperationalError(
                    f"Échec connexion après {max_attempts} tentatives\n"
                    f"Dernier diagnostic:\n{diagnostic}"
                ) from e
            time.sleep(min(2 ** attempt, 10))
    
    raise sqlite3.Error("Échec inattendu de connexion")

# ==================== FONCTIONS DE GESTION ====================

def hash_password(password: str, salt: str = "fixed_salt_value") -> str:
    """Hash un mot de passe avec SHA-256 et un sel"""
    return hashlib.sha256((password + salt).encode()).hexdigest()

def generer_numero_client_unique() -> str:
    """Génère un numéro client unique de 4 chiffres"""
    with connexion_db() as conn:
        cur = conn.cursor()
        while True:
            numero = str(random.randint(1000, 9999))
            cur.execute("SELECT COUNT(*) FROM abonne WHERE numero_client = ?", (numero,))
            if cur.fetchone()[0] == 0:
                return numero

def generer_numero_carte_unique() -> str:
    """Génère un numéro de carte unique de 10 chiffres"""
    with connexion_db() as conn:
        cur = conn.cursor()
        while True:
            numero = str(random.randint(1000000000, 9999999999))
            cur.execute("SELECT COUNT(*) FROM abonne WHERE numero_carte = ?", (numero,))
            if cur.fetchone()[0] == 0:
                return numero

def initialiser_pages_compte_fixe(numero_carte: str) -> bool:
    logger.debug(f"Tentative d'initialisation des pages pour {numero_carte}")
    try:
        with connexion_db() as conn:
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
        with connexion_db() as conn:
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
            
# ==================== FONCTIONS POUR LA GESTION DES AGENTS ====================

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
            
            # Hashage du mot de passe
            mdp_hash = hash_password(mot_de_passe)
            
            cur.execute("""
                INSERT INTO agent (
                    nom_agent, identifiant, mot_de_passe, photo, role, date_creation
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                nom, identifiant, mdp_hash, 
                photo_blob, role, datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

def get_all_users() -> List[Dict]:
    """Récupère tous les agents avec gestion améliorée des photos"""
    try:
        with connexion_db() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("""
                SELECT id, nom_agent, photo, identifiant, 
                       role, date_creation, actif
                FROM agent
                ORDER BY nom_agent
            """)
            
            agents = []
            for row in cur.fetchall():
                agent = dict(row)
                
                # Conversion du BLOB photo si nécessaire
                if 'photo' in agent and isinstance(agent['photo'], bytes):
                    try:
                        # Pour l'interface, on garde le BLOB et on gérera l'affichage séparément
                        pass
                    except Exception as e:
                        print(f"Erreur conversion photo: {e}")
                        agent['photo'] = None
                
                agents.append(agent)
            
            return agents
            
    except sqlite3.Error as e:
        print(f"Erreur récupération agents: {e}")
        return []

def verifier_mot_de_passe(nom_utilisateur: str, mot_de_passe: str) -> Tuple[bool, Optional[Dict]]:
    """
    Vérifie les identifiants de connexion
    Retourne un tuple (succès, infos_agent)
    """
    if not nom_utilisateur or not mot_de_passe:
        return (False, None)
        
    try:
        with connexion_db() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            cur.execute("""
                SELECT * FROM agent 
                WHERE (nom_agent = ? OR identifiant = ?) AND actif = 1
                LIMIT 1
            """, (nom_utilisateur, nom_utilisateur))
            
            agent = cur.fetchone()
            if not agent:
                # Hash fictif pour éviter les attaques temporelles
                hash_password("dummy_value")
                return (False, None)
            
            # Comparaison sécurisée des hashs
            stored_hash = agent['mot_de_passe']
            input_hash = hash_password(mot_de_passe)
            
            if stored_hash == input_hash:
                return (True, dict(agent))
            else:
                return (False, None)
                
    except sqlite3.Error as e:
        print(f"Erreur vérification mot de passe: {e}")
        return (False, None)

def get_agent_photo(agent_id: int) -> Optional[bytes]:
    """Récupère la photo d'un agent sous forme de données binaires"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT photo FROM agent WHERE id = ?", (agent_id,))
            result = cur.fetchone()
            return result[0] if result else None
    except sqlite3.Error as e:
        print(f"Erreur récupération photo: {e}")
        return None

# ==================== FONCTIONS POUR L'INTERFACE ====================

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

def blob_to_photoimage(blob_data: bytes, size: Tuple[int, int] = (60, 60)) -> Optional[Image.Image]:
    """Convertit des données BLOB en image PIL"""
    if not blob_data:
        return None
        
    try:
        img = Image.open(io.BytesIO(blob_data))
        img = img.resize(size, Image.LANCZOS)
        return img
    except Exception as e:
        print(f"Erreur conversion photo: {e}")
        return None

# ==================== AUTRES FONCTIONS ESSENTIELLES ====================

def ajouter_journal(action: str, acteur: str, cible: Optional[str] = None, 
                   details: Optional[str] = None) -> bool:
    """Ajoute une entrée dans le journal"""
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
                    datetime.now().strftime("%Y-%m-%d"),
                    datetime.now().strftime("%H:%M:%S")
                ))
                conn.commit()
                return True
        except sqlite3.Error as e:
            print(f"Erreur journalisation (tentative {attempt+1}): {e}")
            time.sleep(0.5 * (attempt + 1))
    return False

def creer_compte_agent(nom: str, identifiant: str, mot_de_passe: str, role: str = 'agent', photo_path: str = None) -> bool:
    """Crée un nouveau compte agent avec photo"""
    try:
        photo_blob = None
        if photo_path and os.path.exists(photo_path):
            with open(photo_path, 'rb') as f:
                photo_blob = f.read()
        
        with connexion_db() as conn:
            cur = conn.cursor()
            mdp_hash = hash_password(mot_de_passe)
            cur.execute("""
                INSERT INTO agent (nom_agent, identifiant, mot_de_passe, photo, role, date_creation)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (nom, identifiant, mdp_hash, photo_blob, role, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
            return True
    except sqlite3.IntegrityError:
        print("Erreur: Identifiant déjà utilisé")
        return False
    except Exception as e:
        print(f"Erreur création compte: {e}")
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

# ==================== INITIALISATION ET MIGRATION ====================

def initialiser_base() -> bool:
    """Initialise la structure de la base de données"""
    schema = """
    PRAGMA foreign_keys = ON;
    PRAGMA journal_mode = WAL;
    PRAGMA synchronous = NORMAL;
    
    CREATE TABLE IF NOT EXISTS meta (
        version TEXT PRIMARY KEY,
        date_mise_a_jour TEXT
    );
    
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
        derniere_operation,
        date_derniere_operation TEXT,
        statut TEXT DEFAULT 'Actif' CHECK(statut IN ('Actif', 'Inactif', 'Bloqué')),
        UNIQUE(numero_client, type_compte)
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
        date_fin TEXT NOT NULL,
        FOREIGN KEY (numero_carte) REFERENCES abonne(numero_carte)
    );
    
    CREATE TABLE IF NOT EXISTS compte_fixe_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_carte TEXT NOT NULL,
        numero_client TEXT NOT NULL,
        page INTEGER NOT NULL,
        cases_remplies INTEGER DEFAULT 0,
        FOREIGN KEY (numero_carte) REFERENCES abonne(numero_carte),
        FOREIGN KEY (numero_client) REFERENCES abonne(numero_client),
        UNIQUE(numero_carte, page)
    );
    
    CREATE TABLE IF NOT EXISTS parametres (
        cle TEXT PRIMARY KEY,
        valeur TEXT,
        description TEXT,
        modifiable INTEGER DEFAULT 1
    );
    
    CREATE TABLE IF NOT EXISTS compte_fixe_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_client TEXT NOT NULL,
        numero_carte TEXT NOT NULL,
        ref_depot TEXT NOT NULL,
        date_remplissage TEXT NOT NULL,
        montant REAL NOT NULL,
        FOREIGN KEY (numero_client) REFERENCES abonne(numero_client)
    );
    
    CREATE TABLE IF NOT EXISTS historique_modifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_modifiee TEXT NOT NULL,
        id_ligne INTEGER NOT NULL,
        ancienne_valeur TEXT,
        nouvelle_valeur TEXT,
        date_modification TEXT NOT NULL,
        auteur TEXT NOT NULL
    );
    """
    
    for attempt in range(3):
        try:
            with connexion_db() as conn:
                cur = conn.cursor()
                
                # Vérifier si la base est déjà initialisée
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'")
                if not cur.fetchone():
                    print("⚙️ Création de la structure de base...")
                    cur.executescript(schema)
                    
                    # Paramètres par défaut
                    parametres = [
                        ('taux_interet', '5.0', "Taux d'intérêt annuel (%)", 1),
                        ('retrait_min', '1000', "Montant minimum pour retrait", 1),
                        ('depot_min', '500', "Montant minimum pour dépôt", 1),
                        ('timeout_db', '30', "Timeout base de données (secondes)", 0)
                    ]
                    cur.executemany("INSERT INTO parametres VALUES (?, ?, ?, ?)", parametres)
                    
                    # Version initiale
                    cur.execute("INSERT INTO meta (version, date_mise_a_jour) VALUES (?, ?)",
                               ('1.0', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    
                    conn.commit()
                    print("✅ Base initialisée avec succès")
                else:
                    print("ℹ️ Structure existante détectée")
                
                return True
                
        except sqlite3.Error as e:
            print(f"⚠️ Erreur initialisation (tentative {attempt+1}/3): {e}")
            time.sleep(1)
    
    print("❌ Échec initialisation après 3 tentatives")
    return False

def migrer_donnees() -> bool:
    """Migre les données des anciennes versions"""
    migrations = [
        """
        ALTER TABLE abonne ADD COLUMN dernier_acces TEXT;
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_abonne_numero_client ON abonne(numero_client);
        """,
        """
        CREATE TABLE IF NOT EXISTS compte_fixe_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_carte TEXT NOT NULL,
            numero_client TEXT NOT NULL,
            page INTEGER NOT NULL,
            cases_remplies INTEGER DEFAULT 0,
            FOREIGN KEY (numero_carte) REFERENCES abonne(numero_carte),
            FOREIGN KEY (numero_client) REFERENCES abonne(numero_client),
            UNIQUE(numero_carte, page)
        );
        """
    ]
    
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            
            # Vérifier la version
            cur.execute("SELECT version FROM meta LIMIT 1")
            row = cur.fetchone()
            if not row:
                # Aucune version enregistrée, on initialise à 1.0
                cur.execute("INSERT INTO meta (version, date_mise_a_jour) VALUES (?, ?)",
                          ('1.0', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                version = '1.0'
            else:
                version = row[0]
            
            if version == '1.0':
                for migration in migrations:
                    try:
                        cur.executescript(migration)
                    except sqlite3.Error as e:
                        print(f"⚠️ Migration partielle échouée: {e}")
                
                # Mettre à jour la version
                cur.execute("UPDATE meta SET version=?, date_mise_a_jour=?",
                           ('1.1', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                
                conn.commit()
                print("✅ Migration 1.0 → 1.1 effectuée")
            
            return True
            
    except sqlite3.Error as e:
        print(f"❌ Erreur migration: {e}")
        return False

# ==================== DONNÉES DE TEST ====================

def creer_donnees_test() -> bool:
    """Crée des données de test pour le développement avec une gestion robuste des erreurs"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            
            # Vérifier si des données existent déjà
            cur.execute("SELECT COUNT(*) FROM agent")
            if cur.fetchone()[0] > 0:
                print("ℹ️ Données de test déjà existantes")
                return True  # Retourne True car ce n'est pas une erreur
            
            print("⚙️ Création des données de test...")
            
            # 1. Création des agents de test
            agents = [
                ("Admin", "admin", "admin123", "admin", None),
                ("Agent 1", "agent1", "agent123", "agent", None),
                ("Agent 2", "agent2", "agent123", "agent", None)
            ]
            
            for nom, identifiant, mdp, role, photo in agents:
                try:
                    cur.execute("""
                        INSERT INTO agent 
                        (nom_agent, identifiant, mot_de_passe, role, date_creation, photo)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        nom, 
                        identifiant, 
                        hash_password(mdp), 
                        role, 
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        photo
                    ))
                except sqlite3.IntegrityError as e:
                    print(f"⚠️ Erreur création agent {nom}: {e}")
                    conn.rollback()
                    continue
            
            # 2. Préparation de la photo test
            photos_dir = os.path.join(os.path.dirname(get_db_path()), "photos")
            os.makedirs(photos_dir, exist_ok=True, mode=0o777)
            photo_test = os.path.join(photos_dir, "test.jpg")
            
            if not os.path.exists(photo_test):
                try:
                    img = Image.new('RGB', (200, 200), color='blue')
                    draw = ImageDraw.Draw(img)
                    draw.text((50, 100), "PHOTO TEST", fill='white')
                    img.save(photo_test)
                    # Appliquer les permissions
                    os.chmod(photo_test, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
                except Exception as e:
                    print(f"⚠️ Erreur création photo test: {e}")
                    photo_test = None
            
            # 3. Création des abonnés de test
            abonnes = [
                {
                    "numero_client": "CLI001",
                    "numero_carte": generer_numero_carte_unique(),
                    "nom": "Doe",
                    "prenom": "John",
                    "sexe": "M",
                    "date_naissance": "1990-01-15",
                    "lieu_naissance": "Paris",
                    "adresse": "123 Rue Test",
                    "telephone": "0123456789",
                    "suppleant": "Jane Doe",
                    "contact_suppleant": "0987654321",
                    "type_compte": "Fixe",
                    "montant": 50000.0,
                    "photo": photo_test,
                    "date_inscription": datetime.now().strftime("%Y-%m-%d")
                },
                {
                    "numero_client": "CLI002",
                    "numero_carte": generer_numero_carte_unique(),
                    "nom": "Smith",
                    "prenom": "Alice",
                    "sexe": "F",
                    "date_naissance": "1985-05-20",
                    "lieu_naissance": "Lyon",
                    "adresse": "456 Avenue Exemple",
                    "telephone": "0678912345",
                    "suppleant": "Bob Smith",
                    "contact_suppleant": "0632145879",
                    "type_compte": "Mixte",
                    "montant": 30000.0,
                    "photo": None,
                    "date_inscription": datetime.now().strftime("%Y-%m-%d")
                }
            ]
            
            for abonne in abonnes:
                try:
                    # Insertion de l'abonné
                    cur.execute("""
                        INSERT INTO abonne (
                            numero_client, numero_carte, nom, postnom, prenom, sexe,
                            date_naissance, lieu_naissance, adresse, telephone,
                            suppleant, contact_suppleant, type_compte, montant, 
                            photo, date_inscription
                        ) VALUES (
                            :numero_client, :numero_carte, :nom, :postnom, :prenom, :sexe,
                            :date_naissance, :lieu_naissance, :adresse, :telephone,
                            :suppleant, :contact_suppleant, :type_compte, :montant,
                            :photo, :date_inscription
                        )
                    """, {
                        'numero_client': abonne["numero_client"],
                        'numero_carte': abonne["numero_carte"],
                        'nom': abonne["nom"],
                        'postnom': '',  # postnom non fourni dans les données de test
                        'prenom': abonne["prenom"],
                        'sexe': abonne["sexe"],
                        'date_naissance': abonne["date_naissance"],
                        'lieu_naissance': abonne["lieu_naissance"],
                        'adresse': abonne["adresse"],
                        'telephone': abonne["telephone"],
                        'suppleant': abonne["suppleant"],
                        'contact_suppleant': abonne["contact_suppleant"],
                        'type_compte': abonne["type_compte"],
                        'montant': abonne["montant"],
                        'photo': abonne["photo"],
                        'date_inscription': abonne["date_inscription"]
                    })
                    
                    # Pour les comptes fixes, créer l'entrée dans compte_fixe
                    if abonne["type_compte"] == "Fixe":
                        date_debut = datetime.strptime(abonne["date_inscription"], "%Y-%m-%d")
                        date_fin = date_debut.replace(year=date_debut.year + 1)
                        
                        cur.execute("""
                            INSERT INTO compte_fixe (
                                numero_client, numero_carte, 
                                montant_initial, date_debut, date_fin
                            ) VALUES (?, ?, ?, ?, ?)
                        """, (
                            abonne["numero_client"],
                            abonne["numero_carte"],
                            abonne["montant"],
                            date_debut.strftime("%Y-%m-%d"),
                            date_fin.strftime("%Y-%m-%d")
                        ))
                        
                        # Initialiser les pages du compte fixe
                        if not initialiser_pages_compte_fixe(abonne["numero_carte"]):
                            raise RuntimeError("Échec initialisation des pages du compte fixe")
                
                except sqlite3.IntegrityError as e:
                    print(f"⚠️ Erreur création abonné {abonne['numero_client']}: {e}")
                    conn.rollback()
                    continue
                except Exception as e:
                    print(f"⚠️ Erreur inattendue avec abonné {abonne['numero_client']}: {e}")
                    conn.rollback()
                    continue
            
            # 4. Ajout de dépôts de test
            depot1 = {
                "numero_client": "CLI001",
                "montant": 5000.0,
                "ref_depot": "DEP001",
                "heure": "10:30:00",
                "date_depot": datetime.now().strftime("%Y-%m-%d"),
                "nom_agent": "Admin",
                "methode_paiement": "Espèces"
            }
            ajouter_depot(**depot1)
            
            depot2 = {
                "numero_client": "CLI002",
                "montant": 3000.0,
                "ref_depot": "DEP002",
                "heure": "11:45:00",
                "date_depot": datetime.now().strftime("%Y-%m-%d"),
                "nom_agent": "Agent 1",
                "methode_paiement": "Mobile"
            }
            ajouter_depot(**depot2)
            
            conn.commit()
            print("✅ Données de test créées avec succès")
            return True
            
    except sqlite3.Error as e:
        print(f"❌ Erreur SQLite lors de la création des données test: {e}")
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"❌ Erreur inattendue lors de la création des données test: {e}")
        traceback.print_exc()
        return False


# ==================== POINT D'ENTRÉE ====================

if __name__ == "__main__":
    print("=== INITIALISATION DE L'APPLICATION ===")
    print(f"📂 Chemin base: {get_db_path()}")
    
    try:
        print("\n🔍 Diagnostic initial:")
        print(diagnostiquer_blocage(get_db_path()))
        
        print("\n⚙️ Initialisation de la base...")
        if initialiser_base():
            print("\n🔄 Migration des données...")
            if migrer_donnees():
                print("\n🔧 Correction des comptes fixes existants...")
                nb_corriges = corriger_comptes_fixes_existants()
                print(f"   {nb_corriges} comptes corrigés")
                print("\n🧪 Création données test...")
                creer_donnees_test()
        
        print("\n🔍 Diagnostic final:")
        print(diagnostiquer_blocage(get_db_path()))
        print("\n✅ Initialisation terminée avec succès")
        
    except PermissionError as pe:
        print(f"\n🔒 ERREUR PERMISSIONS: {str(pe)}")
        print("\n🛑 L'application nécessite des droits d'accès pour fonctionner")
        print("➡️ Veuillez exécuter en tant qu'administrateur ou vérifier les permissions")
        logger.critical(f"Erreur permissions: {str(pe)}")
    except Exception as e:
        print(f"\n💥 ERREUR CRITIQUE: {type(e).__name__}")
        print(f"📌 Message: {str(e)}")
        print("\n🔍 Diagnostic d'erreur:")
        print(diagnostiquer_blocage(get_db_path()))
        print("\n🛑 L'application s'est arrêtée à cause d'une erreur")
        logger.exception("Erreur critique lors de l'initialisation")