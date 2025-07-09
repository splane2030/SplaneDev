import os
import sqlite3
from datetime import datetime
import hashlib
import binascii

# Configuration
DB_PATH = os.path.join(os.getenv('APPDATA'), 'MonEpargne', 'money_epargne.db')

def hash_password(password, salt=None):
    """Hash un mot de passe avec salt"""
    if not salt:
        salt = binascii.hexlify(os.urandom(16)).decode()
    pwdhash = binascii.hexlify(
        hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    ).decode()
    return pwdhash, salt

def create_fresh_database():
    """Crée une nouvelle base de données avec toutes les tables"""
    try:
        # Créer le dossier si inexistant
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        
        # Supprimer l'ancien fichier s'il existe
        if os.path.exists(DB_PATH):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = DB_PATH + f".backup_{timestamp}"
            os.rename(DB_PATH, backup_path)
            print(f"Ancienne base sauvegardée comme : {backup_path}")

        # Créer une nouvelle base avec le schéma complet
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Table agent (authentification)
        cursor.execute("""
        CREATE TABLE agent (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom_agent TEXT NOT NULL,
            identifiant TEXT UNIQUE NOT NULL,
            mot_de_passe TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT DEFAULT 'agent',
            date_creation TEXT DEFAULT CURRENT_TIMESTAMP,
            actif INTEGER DEFAULT 1,
            photo BLOB
        )""")
        
        # Table abonne (clients)
        cursor.execute("""
        CREATE TABLE abonne (
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
        )""")
        
        # Table suppleant
        cursor.execute("""
        CREATE TABLE suppleant (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            abonne_id INTEGER NOT NULL,
            nom TEXT NOT NULL,
            telephone TEXT NOT NULL,
            FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE,
            UNIQUE(abonne_id, nom)
        )""")
        
        # Table type_compte
        cursor.execute("""
        CREATE TABLE type_compte (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nom TEXT UNIQUE NOT NULL CHECK(nom IN ('Fixe', 'Mixte', 'Bloqué')),
            description TEXT
        )""")
        
        # Table abonne_compte
        cursor.execute("""
        CREATE TABLE abonne_compte (
            abonne_id INTEGER NOT NULL,
            type_compte_id INTEGER NOT NULL,
            date_activation TEXT NOT NULL,
            solde REAL DEFAULT 0,
            PRIMARY KEY (abonne_id, type_compte_id),
            FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE,
            FOREIGN KEY (type_compte_id) REFERENCES type_compte(id)
        )""")
        
        # Table compte_bloque
        cursor.execute("""
        CREATE TABLE compte_bloque (
            abonne_id INTEGER PRIMARY KEY,
            duree_mois INTEGER NOT NULL CHECK(duree_mois > 0),
            montant_atteindre REAL NOT NULL CHECK(montant_atteindre > 0),
            pourcentage_retrait INTEGER NOT NULL CHECK(pourcentage_retrait BETWEEN 1 AND 100),
            frequence_retrait TEXT NOT NULL CHECK(frequence_retrait IN ('Mensuel', 'Trimestriel', 'Semestriel', 'Annuel')),
            FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE
        )""")
        
        # Table compte_fixe
        cursor.execute("""
        CREATE TABLE compte_fixe (
            abonne_id INTEGER PRIMARY KEY,
            montant_initial REAL NOT NULL CHECK(montant_initial > 0),
            date_debut TEXT NOT NULL,
            date_fin TEXT NOT NULL,
            FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE
        )""")
        
        # Table compte_fixe_page
        cursor.execute("""
        CREATE TABLE compte_fixe_page (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compte_fixe_id INTEGER NOT NULL,
            numero_page INTEGER NOT NULL CHECK(numero_page BETWEEN 1 AND 8),
            cases_remplies INTEGER DEFAULT 0 CHECK(cases_remplies BETWEEN 0 AND 31),
            FOREIGN KEY (compte_fixe_id) REFERENCES compte_fixe(abonne_id) ON DELETE CASCADE,
            UNIQUE(compte_fixe_id, numero_page)
        )""")
        
        # Table depots
        cursor.execute("""
        CREATE TABLE depots (
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
        )""")
        
        # Table retraits
        cursor.execute("""
        CREATE TABLE retraits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_client TEXT NOT NULL,
            montant REAL NOT NULL,
            ref_retrait TEXT UNIQUE,
            heure TEXT NOT NULL,
            date_retrait TEXT NOT NULL,
            agent TEXT NOT NULL,
            statut TEXT DEFAULT 'En attente',
            FOREIGN KEY (numero_client) REFERENCES abonne(numero_client)
        )""")
        
        # Table transactions
        cursor.execute("""
        CREATE TABLE transactions (
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
        )""")
        
        # Table parametres
        cursor.execute("""
        CREATE TABLE parametres (
            cle TEXT PRIMARY KEY,
            valeur TEXT,
            description TEXT,
            modifiable INTEGER DEFAULT 1
        )""")
        
        # Table compte_fixe_cases
        cursor.execute("""
        CREATE TABLE compte_fixe_cases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_client TEXT NOT NULL,
            numero_carte TEXT NOT NULL,
            ref_depot TEXT NOT NULL,
            date_remplissage TEXT NOT NULL,
            montant REAL NOT NULL,
            FOREIGN KEY (numero_client) REFERENCES abonne(numero_client)
        )""")
        
        # Table historique_modifications
        cursor.execute("""
        CREATE TABLE historique_modifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            table_modifiee TEXT NOT NULL,
            id_ligne INTEGER NOT NULL,
            ancienne_valeur TEXT,
            nouvelle_valeur TEXT,
            date_modification TEXT NOT NULL,
            auteur TEXT NOT NULL
        )""")
        
        # Table journal
        cursor.execute("""
        CREATE TABLE journal (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT NOT NULL,
            acteur TEXT NOT NULL,
            date_action TEXT NOT NULL,
            heure_action TEXT NOT NULL,
            cible TEXT,
            details TEXT,
            ip_address TEXT,
            user_agent TEXT
        )""")
        
        # Données initiales
        cursor.executemany(
            "INSERT INTO type_compte (nom, description) VALUES (?, ?)",
            [
                ('Fixe', 'Compte avec montant fixe à épargner'),
                ('Mixte', 'Compte flexible avec options variées'),
                ('Bloqué', 'Compte avec montant bloqué pour une durée déterminée')
            ]
        )
        
        # Créer un compte admin par défaut
        password = 'admin123'
        pwdhash, salt = hash_password(password)
        
        cursor.execute("""
        INSERT INTO agent (
            nom_agent, identifiant, mot_de_passe, salt, role, date_creation
        ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            'Administrateur',
            'admin',
            pwdhash,
            salt,
            'admin',
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        
        conn.commit()
        print(f"Nouvelle base créée avec succès à : {DB_PATH}")
        
    except Exception as e:
        print(f"Erreur lors de la création de la base : {str(e)}")
        if os.path.exists(DB_PATH):
            os.remove(DB_PATH)
        raise
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    print("=== RÉINITIALISATION DE LA BASE DE DONNÉES ===")
    create_fresh_database()
    print("=== OPÉRATION TERMINÉE AVEC SUCCÈS ===")