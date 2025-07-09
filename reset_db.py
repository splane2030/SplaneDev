import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.getenv('APPDATA'), 'MonEpargne', 'money_epargne.db')

def create_fresh_database():
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
    
    # Table agent (essentielle pour l'authentification)
    cursor.execute("""
    CREATE TABLE agent (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom_agent TEXT NOT NULL,
        identifiant TEXT UNIQUE NOT NULL,
        mot_de_passe TEXT NOT NULL,
        salt TEXT NOT NULL,
        role TEXT DEFAULT 'agent',
        date_creation TEXT,
        actif INTEGER DEFAULT 1,
        photo BLOB
    )""")
    
    # Table abonne (structure de base)
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
        photo_path TEXT
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS suppleant (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        abonne_id INTEGER NOT NULL,
        nom TEXT NOT NULL,
        telephone TEXT NOT NULL,
        FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE,
        UNIQUE(abonne_id, nom)
    )""")
    
    # Table des types de compte
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS type_compte (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nom TEXT UNIQUE NOT NULL CHECK(nom IN ('Fixe', 'Mixte', 'Bloqué')),
        description TEXT
    )""")

    # Table de liaison abonne-type_compte
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS abonne_compte (
        abonne_id INTEGER NOT NULL,
        type_compte_id INTEGER NOT NULL,
        date_activation TEXT NOT NULL,
        solde REAL DEFAULT 0,
        PRIMARY KEY (abonne_id, type_compte_id),
        FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE,
        FOREIGN KEY (type_compte_id) REFERENCES type_compte(id)
    )""")

    # Table spécifique aux comptes bloqués
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compte_bloque (
        abonne_id INTEGER PRIMARY KEY,
        duree_mois INTEGER NOT NULL CHECK(duree_mois > 0),
        montant_atteindre REAL NOT NULL CHECK(montant_atteindre > 0),
        pourcentage_retrait INTEGER NOT NULL CHECK(pourcentage_retrait BETWEEN 1 AND 100),
        frequence_retrait TEXT NOT NULL CHECK(frequence_retrait IN ('Mensuel', 'Trimestriel', 'Semestriel', 'Annuel')),
        FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE
    )""")

    # Table spécifique aux comptes fixes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compte_fixe (
        abonne_id INTEGER PRIMARY KEY,
        montant_initial REAL NOT NULL CHECK(montant_initial > 0),
        date_debut TEXT NOT NULL,
        date_fin TEXT NOT NULL,
        FOREIGN KEY (abonne_id) REFERENCES abonne(id) ON DELETE CASCADE
    )""")
    
    cursor.execute("""
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
    )""")
    
    cursor.execute("""
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
    )""")

    # Pages des carnets fixes
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compte_fixe_page (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        compte_fixe_id INTEGER NOT NULL,
        numero_page INTEGER NOT NULL CHECK(numero_page BETWEEN 1 AND 8),
        cases_remplies INTEGER DEFAULT 0 CHECK(cases_remplies BETWEEN 0 AND 31),
        FOREIGN KEY (compte_fixe_id) REFERENCES compte_fixe(abonne_id) ON DELETE CASCADE,
        UNIQUE(compte_fixe_id, numero_page)
    )""")

    # Transactions (note: j'ai renommé la table car 'transaction' est un mot réservé)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
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
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS parametres (
        cle TEXT PRIMARY KEY,
        valeur TEXT,
        description TEXT,
        modifiable INTEGER DEFAULT 1
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS compte_fixe_cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        numero_client TEXT NOT NULL,
        numero_carte TEXT NOT NULL,
        ref_depot TEXT NOT NULL,
        date_remplissage TEXT NOT NULL,
        montant REAL NOT NULL,
        FOREIGN KEY (numero_client) REFERENCES abonne(numero_client)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS historique_modifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        table_modifiee TEXT NOT NULL,
        id_ligne INTEGER NOT NULL,
        ancienne_valeur TEXT,
        nouvelle_valeur TEXT,
        date_modification TEXT NOT NULL,
        auteur TEXT NOT NULL
    )""")

    # Journal d'audit
    cursor.execute("""
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
    )""")
    
    # Créez un compte admin par défaut
    from hashlib import pbkdf2_hmac
    import binascii
    salt = binascii.hexlify(os.urandom(16)).decode()
    password_hash = binascii.hexlify(pbkdf2_hmac('sha256', 'admin123'.encode(), salt.encode(), 100000)).decode()
    
    cursor.execute("""
    INSERT INTO agent (nom_agent, identifiant, mot_de_passe, salt, role, date_creation)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (
        'Administrateur',
        'admin',
        password_hash,
        salt,
        'admin',
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))
    
    conn.commit()
    conn.close()
    print(f"Nouvelle base créée avec succès à : {DB_PATH}")

if __name__ == "__main__":
    create_fresh_database()