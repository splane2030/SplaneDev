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
    log_dir = os.path.join(os.getenv('LOCALAPPDATA', ''), 'MonLogiciel')
    log_path = os.path.join(log_dir, 'app.log')
    
    try:
        os.makedirs(log_dir, exist_ok=True, mode=0o777)
        logging.basicConfig(
            filename=log_path,
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        logger = logging.getLogger(__name__)
        logger.info("Logging initialisé avec succès dans %s", log_path)
        return logger
        
    except Exception as e:
        logging.basicConfig(level=logging.INFO)
        logger = logging.getLogger(__name__)
        logger.error("Impossible de configurer le fichier log: %s", str(e))
        return logger

logger = setup_logging()

def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def get_db_path() -> str:
    appdata_dir = os.getenv("APPDATA")
    app_folder = os.path.join(appdata_dir, "MonEpargne") if appdata_dir else None
    
    if not app_folder or not os.access(os.path.dirname(app_folder), os.W_OK):
        temp_dir = tempfile.gettempdir()
        app_folder = os.path.join(temp_dir, "MonEpargne")
        logger.warning("Utilisation du dossier TEMP pour la base de données")
    
    try:
        os.makedirs(app_folder, exist_ok=True, mode=0o777)
    except Exception as e:
        logger.error(f"Erreur création dossier: {e}")
        app_folder = os.path.abspath(".")
    
    local_db = os.path.join(app_folder, "money_epargne.db")

    if not os.path.exists(local_db):
        original_db = resource_path("money_epargne.db")
        if os.path.exists(original_db):
            try:
                shutil.copyfile(original_db, local_db)
                os.chmod(local_db, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH)
                logger.info("Base copiée de %s vers %s", original_db, local_db)
            except Exception as e:
                logger.error(f"Erreur copie DB: {e}")
                create_empty_db(local_db)
    
    return local_db

def create_empty_db(local_db: str):
    try:
        conn = sqlite3.connect(local_db)
        conn.close()
        logger.info("Base vide créée à %s", local_db)
    except Exception as e:
        logger.critical(f"Échec création base: {e}")
        raise PermissionError(f"Échec création base: {e}")

def diagnostiquer_blocage(chemin_db: str) -> str:
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
                        if chemin_db in f.path:
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
    chemin_db = get_db_path()
    max_attempts = 5
    
    for attempt in range(max_attempts):
        try:
            conn = sqlite3.connect(chemin_db, timeout=30, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA busy_timeout=30000")
            conn.execute("PRAGMA foreign_keys=ON")
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
    return hashlib.sha256((password + salt).encode()).hexdigest()

def ajouter_journal(action: str, acteur: str, cible: Optional[str] = None, details: Optional[str] = None) -> bool:
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
            logger.error(f"Erreur journalisation (tentative {attempt+1}): {e}")
            time.sleep(0.5 * (attempt + 1))
    return False

def generer_numero_client_unique() -> str:
    """Génère un numéro client unique de 4 chiffres"""
    with connexion_db() as conn:
        cur = conn.cursor()
        while True:
            numero = str(random.randint(1000, 9999))
            cur.execute("SELECT COUNT(*) FROM abonne WHERE numero_client = ?", (numero,))
            if cur.fetchone()[0] == 0:
                return numero

def initialiser_base() -> bool:
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
        derniere_operation TEXT,
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
    """
    
    for attempt in range(3):
        try:
            with connexion_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'")
                if not cur.fetchone():
                    cur.executescript(schema)
                    cur.execute("INSERT INTO meta (version, date_mise_a_jour) VALUES (?, ?)",
                               ('1.0', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    logger.info("Base initialisée avec succès")
                else:
                    logger.info("Structure existante détectée")
                return True
                
        except sqlite3.Error as e:
            logger.error(f"⚠️ Erreur initialisation (tentative {attempt+1}/3): {e}")
            time.sleep(1)
    
    logger.critical("❌ Échec initialisation après 3 tentatives")
    return False

# ==================== FONCTIONS CRUD POUR ABONNÉS ====================

def creer_abonne(
    numero_carte: str,
    nom: str,
    postnom: str,
    prenom: str,
    sexe: str,
    date_naissance: str,
    lieu_naissance: str,
    adresse: str,
    telephone: str,
    type_compte: str,
    montant: float,
    suppleant: Optional[str] = None,
    contact_suppleant: Optional[str] = None,
    photo: Optional[str] = None
) -> Tuple[bool, str]:
    """Crée un nouvel abonné dans la base de données"""
    numero_client = generer_numero_client_unique()
    date_inscription = datetime.now().strftime("%Y-%m-%d")
    
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO abonne (
                    numero_client, numero_carte, nom, postnom, prenom, sexe,
                    date_naissance, lieu_naissance, adresse, telephone,
                    suppleant, contact_suppleant, type_compte, montant,
                    photo, date_inscription, solde
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                numero_client, numero_carte, nom, postnom, prenom, sexe,
                date_naissance, lieu_naissance, adresse, telephone,
                suppleant, contact_suppleant, type_compte, montant,
                photo, date_inscription, montant
            ))
            conn.commit()
            
            ajouter_journal(
                "Création abonné",
                "Système",
                numero_client,
                f"Nouvel abonné {nom} {prenom} créé avec le numéro {numero_client}"
            )
            
            return True, numero_client
    except sqlite3.Error as e:
        logger.error(f"Erreur création abonné: {e}")
        return False, str(e)

def obtenir_abonne(numero_client: str) -> Optional[Dict]:
    """Récupère les informations d'un abonné"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM abonne WHERE numero_client = ?", (numero_client,))
            row = cur.fetchone()
            
            if row:
                columns = [col[0] for col in cur.description]
                return dict(zip(columns, row))
            return None
    except sqlite3.Error as e:
        logger.error(f"Erreur récupération abonné {numero_client}: {e}")
        return None

def mettre_a_jour_abonne(
    numero_client: str,
    **updates
) -> bool:
    """Met à jour les informations d'un abonné"""
    if not updates:
        return False
        
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            set_clause = ", ".join([f"{k} = ?" for k in updates.keys()])
            values = list(updates.values())
            values.append(numero_client)
            
            cur.execute(f"""
                UPDATE abonne 
                SET {set_clause}
                WHERE numero_client = ?
            """, values)
            
            conn.commit()
            
            ajouter_journal(
                "Mise à jour abonné",
                "Système",
                numero_client,
                f"Mise à jour des champs: {', '.join(updates.keys())}"
            )
            
            return True
    except sqlite3.Error as e:
        logger.error(f"Erreur mise à jour abonné {numero_client}: {e}")
        return False

def supprimer_abonne(numero_client: str) -> bool:
    """Désactive un abonné (ne le supprime pas vraiment)"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                UPDATE abonne 
                SET statut = 'Inactif'
                WHERE numero_client = ?
            """, (numero_client,))
            
            conn.commit()
            
            ajouter_journal(
                "Désactivation abonné",
                "Système",
                numero_client,
                "Abonné marqué comme inactif"
            )
            
            return True
    except sqlite3.Error as e:
        logger.error(f"Erreur désactivation abonné {numero_client}: {e}")
        return False

# ==================== FONCTIONS CRUD POUR AGENTS ====================

def creer_agent(
    nom_agent: str,
    identifiant: str,
    mot_de_passe: str,
    role: str = "agent",
    photo: Optional[bytes] = None
) -> bool:
    """Crée un nouvel agent"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO agent (
                    nom_agent, identifiant, mot_de_passe, photo, role, date_creation
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                nom_agent,
                identifiant,
                hash_password(mot_de_passe),
                photo,
                role,
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            conn.commit()
            
            ajouter_journal(
                "Création agent",
                "Système",
                identifiant,
                f"Nouvel agent {nom_agent} créé avec le rôle {role}"
            )
            
            return True
    except sqlite3.Error as e:
        logger.error(f"Erreur création agent: {e}")
        return False

def authentifier_agent(identifiant: str, mot_de_passe: str) -> Optional[Dict]:
    """Authentifie un agent"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, nom_agent, role, photo FROM agent 
                WHERE identifiant = ? AND mot_de_passe = ? AND actif = 1
            """, (identifiant, hash_password(mot_de_passe)))
            
            row = cur.fetchone()
            if row:
                columns = [col[0] for col in cur.description]
                return dict(zip(columns, row))
            return None
    except sqlite3.Error as e:
        logger.error(f"Erreur authentification agent {identifiant}: {e}")
        return None

# ==================== FONCTIONS DE TRANSACTION ====================

def effectuer_depot(
    numero_client: str,
    montant: float,
    nom_agent: str,
    methode_paiement: str = "Espèces"
) -> Tuple[bool, str]:
    """Effectue un dépôt pour un client"""
    ref_depot = f"DEP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
    
    try:
        with connexion_db() as conn:
            # Commencer une transaction
            conn.execute("BEGIN TRANSACTION")
            
            # 1. Mettre à jour le solde du client
            cur = conn.cursor()
            cur.execute("""
                UPDATE abonne 
                SET solde = solde + ?, 
                    derniere_operation = 'Dépôt',
                    date_derniere_operation = ?
                WHERE numero_client = ?
            """, (montant, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), numero_client))
            
            # 2. Enregistrer le dépôt
            cur.execute("""
                INSERT INTO depots (
                    numero_client, montant, ref_depot, heure, 
                    nom_complet, date_depot, nom_agent, methode_paiement
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                numero_client,
                montant,
                ref_depot,
                datetime.now().strftime("%H:%M:%S"),
                obtenir_nom_complet_abonne(numero_client),
                datetime.now().strftime("%Y-%m-%d"),
                nom_agent,
                methode_paiement
            ))
            
            # 3. Journaliser l'action
            ajouter_journal(
                "Dépôt effectué",
                nom_agent,
                numero_client,
                f"Dépôt de {montant} via {methode_paiement}. Réf: {ref_depot}"
            )
            
            conn.commit()
            return True, ref_depot
            
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Erreur lors du dépôt pour {numero_client}: {e}")
        return False, str(e)

def effectuer_retrait(
    numero_client: str,
    montant: float,
    nom_agent: str
) -> Tuple[bool, str]:
    """Effectue un retrait pour un client"""
    ref_retrait = f"RET-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"
    
    try:
        with connexion_db() as conn:
            # Commencer une transaction
            conn.execute("BEGIN TRANSACTION")
            
            # 1. Vérifier le solde et les règles de retrait
            cur = conn.cursor()
            cur.execute("""
                SELECT solde, type_compte, pourcentage_retrait 
                FROM abonne 
                WHERE numero_client = ?
            """, (numero_client,))
            solde, type_compte, pourcentage = cur.fetchone()
            
            if type_compte == "Bloque":
                conn.rollback()
                return False, "Compte bloqué - retrait impossible"
                
            montant_max = solde * (pourcentage / 100)
            if montant > montant_max:
                conn.rollback()
                return False, f"Montant dépasse le plafond de {pourcentage}% du solde"
            
            # 2. Mettre à jour le solde
            cur.execute("""
                UPDATE abonne 
                SET solde = solde - ?, 
                    derniere_operation = 'Retrait',
                    date_derniere_operation = ?
                WHERE numero_client = ?
            """, (montant, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), numero_client))
            
            # 3. Enregistrer le retrait
            cur.execute("""
                INSERT INTO retraits (
                    numero_client, montant, ref_retrait, heure, 
                    date_retrait, agent, statut
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                numero_client,
                montant,
                ref_retrait,
                datetime.now().strftime("%H:%M:%S"),
                datetime.now().strftime("%Y-%m-%d"),
                nom_agent,
                "Complété"
            ))
            
            # 4. Journaliser l'action
            ajouter_journal(
                "Retrait effectué",
                nom_agent,
                numero_client,
                f"Retrait de {montant}. Réf: {ref_retrait}"
            )
            
            conn.commit()
            return True, ref_retrait
            
    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"Erreur lors du retrait pour {numero_client}: {e}")
        return False, str(e)

# ==================== FONCTIONS UTILITAIRES ====================

def obtenir_nom_complet_abonne(numero_client: str) -> Optional[str]:
    """Retourne le nom complet d'un abonné"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT nom, postnom, prenom FROM abonne 
                WHERE numero_client = ?
            """, (numero_client,))
            
            row = cur.fetchone()
            if row:
                return " ".join(filter(None, row))
            return None
    except sqlite3.Error as e:
        logger.error(f"Erreur récupération nom abonné {numero_client}: {e}")
        return None

def generer_rapport_mensuel(mois: int, annee: int) -> Dict:
    """Génère un rapport mensuel des transactions"""
    try:
        with connexion_db() as conn:
            cur = conn.cursor()
            
            # Dépôts du mois
            cur.execute("""
                SELECT SUM(montant), COUNT(*) FROM depots
                WHERE strftime('%m', date_depot) = ? 
                AND strftime('%Y', date_depot) = ?
            """, (f"{mois:02d}", str(annee)))
            total_depots, nb_depots = cur.fetchone()
            
            # Retraits du mois
            cur.execute("""
                SELECT SUM(montant), COUNT(*) FROM retraits
                WHERE strftime('%m', date_retrait) = ? 
                AND strftime('%Y', date_retrait) = ?
                AND statut = 'Complété'
            """, (f"{mois:02d}", str(annee)))
            total_retraits, nb_retraits = cur.fetchone()
            
            # Nouveaux clients
            cur.execute("""
                SELECT COUNT(*) FROM abonne
                WHERE strftime('%m', date_inscription) = ? 
                AND strftime('%Y', date_inscription) = ?
            """, (f"{mois:02d}", str(annee)))
            nouveaux_clients = cur.fetchone()[0]
            
            return {
                "mois": mois,
                "annee": annee,
                "total_depots": total_depots or 0,
                "nb_depots": nb_depots or 0,
                "total_retraits": total_retraits or 0,
                "nb_retraits": nb_retraits or 0,
                "nouveaux_clients": nouveaux_clients,
                "solde_net": (total_depots or 0) - (total_retraits or 0)
            }
    except sqlite3.Error as e:
        logger.error(f"Erreur génération rapport {mois}/{annee}: {e}")
        return {}

# ==================== POINT D'ENTRÉE ====================

if __name__ == "__main__":
    print("=== INITIALISATION DE L'APPLICATION ===")
    print(f"📂 Chemin base: {get_db_path()}")
    
    try:
        print("\n🔍 Diagnostic initial:")
        print(diagnostiquer_blocage(get_db_path()))
        
        print("\n⚙️ Initialisation de la base...")
        if initialiser_base():
            print("\n✅ Initialisation terminée avec succès")
        
        print("\n🔍 Diagnostic final:")
        print(diagnostiquer_blocage(get_db_path()))
        
    except PermissionError as pe:
        print(f"\n🔒 ERREUR PERMISSIONS: {str(pe)}")
        logger.critical(f"Erreur permissions: {str(pe)}")
    except Exception as e:
        print(f"\n💥 ERREUR CRITIQUE: {type(e).__name__}")
        logger.exception("Erreur critique lors de l'initialisation")