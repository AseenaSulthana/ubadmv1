import mysql.connector
from mysql.connector import Error
import datetime
import bcrypt
import logging
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import random
import string
import numpy as np
import trimesh

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Database configuration
DB_CONFIG = {
    'port': 3306,
    'host': 'localhost',
    'database': 'unbound3d',
    'user': 'root',
    'password': 'cookie'
}

# Email configuration
EMAIL_CONFIG = {
    'smtp_server': 'smtp.zoho.in',
    'smtp_port': 587,
    'email': 'support@unbound3d.com',
    'password': 'p8RWzm0DFFvm'
}

# Material and color config for backend validation and API
MATERIAL_CONFIG = {
    'FDM': {
        'PLA': ['Black', 'White', 'Yellow', 'Red', 'Blue', 'Grey'],
        'ABS': ['Black', 'White', 'Yellow', 'Red', 'Blue', 'Grey'],
        'PETG': ['Black', 'White', 'Yellow', 'Red', 'Blue', 'Grey'],
        'TPU': ['Black', 'White', 'Yellow', 'Red', 'Blue', 'Grey'],
        'ASA': ['Black', 'White', 'Yellow', 'Red', 'Blue', 'Grey'],
        'PA-CF': ['Black'],
        'PETG-CF': ['Black'],
    },
    'SLA': {
        'ABS': ['Grey', 'Transparent'],
        'Nylon': ['Grey', 'Transparent']
    },
    'SLS': {
        'Nylon': ['Grey'],
        'Nylon CF': ['Grey']
    }
}

# Allowed file extensions for uploads
ALLOWED_EXTENSIONS = {'stl', 'stp', 'step', 'obj', '3ds', 'ply', 'gcode'}

def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_dimensions(filepath, file_extension):
    """Extract dimensions and volume from supported file types."""
    try:
        if file_extension == 'stl':
            from stl import mesh
            model = mesh.Mesh.from_file(filepath)
            all_points = model.vectors.reshape(-1, 3)
            min_coords = np.min(all_points, axis=0)
            max_coords = np.max(all_points, axis=0)
            size = max_coords - min_coords
            volume = model.get_mass_properties()[0] if hasattr(model, 'get_mass_properties') else 0.0
            return ({
                'x': round(float(size[0]), 2),
                'y': round(float(size[1]), 2),
                'z': round(float(size[2]), 2)
            }, float(volume))
        elif file_extension in ['obj', 'ply', '3ds', 'step', 'stp']:
            mesh_obj = trimesh.load(filepath, force='mesh')
            if mesh_obj.is_empty:
                raise ValueError('Mesh is empty')
            bounds = mesh_obj.bounds
            size = bounds[1] - bounds[0]
            if isinstance(mesh_obj, trimesh.Trimesh) and hasattr(mesh_obj, 'volume'):
                volume = mesh_obj.volume
            else:
                volume = 0.0
            return ({
                'x': round(float(size[0]), 2),
                'y': round(float(size[1]), 2),
                'z': round(float(size[2]), 2)
            }, float(volume))
        elif file_extension == 'gcode':
            # GCODE: No geometry, so return 0s
            return ({'x': 0.0, 'y': 0.0, 'z': 0.0}, 0.0)
        else:
            logger.error(f"Unsupported file extension for dimension extraction: {file_extension}")
            return ({'x': 0.0, 'y': 0.0, 'z': 0.0}, 0.0)
    except Exception as e:
        logger.error(f"Error reading {file_extension} file: {e}")
        return ({'x': 0.0, 'y': 0.0, 'z': 0.0}, 0.0)

def get_db_connection():
    """Establish database connection."""
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        return connection
    except Error as e:
        logger.error(f"Error connecting to MySQL: {e}")
        return None

def generate_custom_id(counter_type, year, user_id=None):
    """Generate custom ID using id_counters table."""
    connection = get_db_connection()
    if not connection:
        logger.error("Database connection failed")
        raise Exception("Database connection failed")
    cursor = connection.cursor()
    try:
        effective_user_id = 'GLOBAL' if counter_type == 'client' else user_id
        if counter_type != 'client':
            cursor.execute('SELECT user_id FROM users WHERE user_id = %s', (user_id,))
            if not cursor.fetchone():
                logger.error(f"User ID {user_id} does not exist")
                raise ValueError(f"User ID {user_id} does not exist")
        cursor.execute('''
            SELECT counter FROM id_counters 
            WHERE counter_type = %s AND year = %s AND user_id = %s
            FOR UPDATE
        ''', (counter_type, year, effective_user_id))
        result = cursor.fetchone()
        logger.debug(f"Counter query result: {result}")
        if result:
            # Ensure result[0] is an integer or can be converted to int
            value = result[0]
            counter = 1
            if isinstance(value, int):
                counter = value + 1
            elif isinstance(value, str) and value.isdigit():
                counter = int(value) + 1
            elif isinstance(value, float):
                counter = int(value) + 1
            # else: leave counter as 1 for any other type (date, None, etc.)
            cursor.execute('''
                UPDATE id_counters 
                SET counter = %s 
                WHERE counter_type = %s AND year = %s AND user_id = %s
            ''', (counter, counter_type, year, effective_user_id))
        else:
            counter = 1
            cursor.execute('''
                INSERT INTO id_counters (counter_type, year, user_id, counter)
                VALUES (%s, %s, %s, %s)
            ''', (counter_type, year, effective_user_id, counter))
        connection.commit()
        logger.debug(f"Counter updated/inserted: {counter}")
        if counter_type == 'client':
            generated_id = f"UB{year}C{counter}"
        elif counter_type == 'project':
            generated_id = f"{user_id}P{counter}"
        elif counter_type == 'quote':
            generated_id = f"{user_id}Q{counter}"
        elif counter_type == 'order':
            generated_id = f"{user_id}OR{counter}"
        elif counter_type == 'file':
            generated_id = f"{user_id}F{counter}"
        else:
            raise ValueError("Invalid counter type")
        logger.info(f"Generated ID: {generated_id}")
        return generated_id
    except Exception as e:
        connection.rollback()
        logger.error(f"Error in generate_custom_id: {e}")
        raise
    finally:
        cursor.close()
        connection.close()

def create_tables():
    """Create necessary database tables."""
    connection = get_db_connection()
    if connection:
        cursor = connection.cursor()
        try:
            # Users table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id VARCHAR(20) PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    designation VARCHAR(255),
                    company VARCHAR(100),
                    location VARCHAR(255),
                    purpose ENUM('personal', 'industry') NOT NULL,
                    mobile VARCHAR(20),
                    email VARCHAR(255) NOT NULL,
                    password VARCHAR(255) NOT NULL,
                    is_verified BOOLEAN DEFAULT FALSE,
                    ub_coins INT DEFAULT 5,  -- UB Coins, default 5 for all users
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    UNIQUE INDEX idx_email (email),
                    INDEX idx_purpose (purpose)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')
            # Insert dummy GLOBAL user
            cursor.execute('''
                INSERT IGNORE INTO users (user_id, name, email, password, purpose, is_verified)
                VALUES ('GLOBAL', 'Global Counter', 'global@unbound3d.com', %s, 'industry', TRUE)
            ''', (bcrypt.hashpw('dummy_password'.encode('utf-8'), bcrypt.gensalt()).decode('utf-8'),))

            # Admin table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    admin_id INT AUTO_INCREMENT PRIMARY KEY,
                    admin_type ENUM('superadmin', 'techadmin') NOT NULL UNIQUE,
                    name VARCHAR(255) NOT NULL,
                    designation VARCHAR(255) NOT NULL,
                    location VARCHAR(255) NOT NULL,
                    mobile VARCHAR(20) NOT NULL,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password VARCHAR(255) NOT NULL,
                    is_verified BOOLEAN DEFAULT FALSE,
                    is_active BOOLEAN DEFAULT TRUE,
                    last_login TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_email (email),
                    INDEX idx_admin_type (admin_type)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Admin OTP codes table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_otp_codes (
                    otp_id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    otp_code VARCHAR(6) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    is_used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_email_otp (email, otp_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Admin sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    session_id VARCHAR(255) PRIMARY KEY,
                    admin_id INT NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (admin_id) REFERENCES admins(admin_id) ON DELETE CASCADE,
                    INDEX idx_admin_id (admin_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # ID counters table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS id_counters (
                    counter_type ENUM('client', 'project', 'quote', 'order') NOT NULL,
                    year CHAR(4) NOT NULL,
                    user_id VARCHAR(20),
                    counter INT DEFAULT 0,
                    PRIMARY KEY (counter_type, year, user_id(20)),
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    INDEX idx_user_id (user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # OTP codes table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS otp_codes (
                    otp_id INT AUTO_INCREMENT PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    otp_code VARCHAR(6) NOT NULL,
                    expires_at TIMESTAMP NOT NULL,
                    is_used BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_email_otp (email, otp_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Projects table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS projects (
                    project_id VARCHAR(30) PRIMARY KEY,
                    user_id VARCHAR(20) NOT NULL,
                    project_name VARCHAR(255) NOT NULL,
                    file_count INT DEFAULT 0,
                    description TEXT,
                    purpose ENUM('functional', 'ideal') NOT NULL,
                    consultation BOOLEAN DEFAULT FALSE,
                    amount DECIMAL(10,2) DEFAULT 0.0,
                    status ENUM('uploaded','quoted','approved','printing','completed','delivered','paid') DEFAULT 'uploaded',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    INDEX idx_user_id_status (user_id, status),
                    INDEX idx_project_name (project_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Project Files table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS project_files (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    file_id VARCHAR(30) NOT NULL,
                    project_id VARCHAR(30) NOT NULL,
                    filename VARCHAR(255) NOT NULL,
                    file_path VARCHAR(255) NOT NULL,
                    file_size INT NOT NULL,
                    file_type VARCHAR(10) NOT NULL,
                    is_configured BOOLEAN DEFAULT FALSE,
                    print_type VARCHAR(50),
                    material VARCHAR(50),
                    color VARCHAR(50),
                    infill_percentage INT DEFAULT 20,
                    scale FLOAT DEFAULT 1.0,
                    painting BOOLEAN DEFAULT FALSE,
                    electroplating BOOLEAN DEFAULT FALSE,
                    post_processing JSON,
                    dimensions JSON,
                    volume FLOAT DEFAULT 0.0,
                    quality VARCHAR(50) DEFAULT NULL,
                    file_description TEXT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
                    INDEX idx_project_id (project_id),
                    INDEX idx_file_id (file_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Quotes table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS quotes (
                    quote_id VARCHAR(30) PRIMARY KEY,
                    project_id VARCHAR(30) NOT NULL,
                    user_id VARCHAR(20) NOT NULL,
                    purpose ENUM('functional', 'ideal') NOT NULL,
                    no_of_files INT NOT NULL,
                    consultation BOOLEAN DEFAULT FALSE,
                    description TEXT,
                    total_price DECIMAL(10,2) NOT NULL,
                    breakdown JSON,
                    notes TEXT,
                    valid_until DATE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    INDEX idx_user_id (user_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Orders table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    order_id VARCHAR(30) PRIMARY KEY,
                    project_id VARCHAR(30),
                    user_id VARCHAR(20) NOT NULL,
                    order_number VARCHAR(50) NOT NULL,
                    order_type ENUM('project', 'product') DEFAULT 'project',
                    total_amount DECIMAL(10,2) NOT NULL,
                    payment_status ENUM('pending', 'completed', 'failed') DEFAULT 'pending',
                    order_status ENUM('pending', 'approved', 'printing', 'completed', 'shipped', 'delivered') DEFAULT 'pending',
                    assigned_farm_id INT,
                    printer_id INT,
                    invoice_number VARCHAR(50),
                    shipping_address TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE SET NULL,
                    UNIQUE INDEX idx_order_number (order_number),
                    INDEX idx_user_id_status (user_id, order_status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Products table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    product_id INT AUTO_INCREMENT PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    category ENUM('printer', 'filament', 'accessory') NOT NULL,
                    description TEXT,
                    price INT NOT NULL,
                    stock_quantity INT DEFAULT 0,
                    specifications JSON,
                    images JSON,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_category (category),
                    INDEX idx_name (name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Cart table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cart (
                    cart_id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id VARCHAR(20) NOT NULL,
                    product_id INT NOT NULL,
                    quantity INT DEFAULT 1 CHECK (quantity > 0),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE,
                    INDEX idx_user_id (user_id),
                    UNIQUE INDEX idx_user_product (user_id, product_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Print farms table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS print_farms (
                    farm_id INT AUTO_INCREMENT PRIMARY KEY,
                    owner_id VARCHAR(20) NOT NULL,
                    farm_name VARCHAR(255) NOT NULL,
                    location VARCHAR(255) NOT NULL,
                    description TEXT,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (owner_id) REFERENCES users(user_id) ON DELETE CASCADE,
                    INDEX idx_owner_id (owner_id),
                    INDEX idx_farm_name (farm_name)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Printers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS printers (
                    printer_id INT AUTO_INCREMENT PRIMARY KEY,
                    farm_id INT NOT NULL,
                    printer_name VARCHAR(255) NOT NULL,
                    printer_model VARCHAR(255) NOT NULL,
                    print_technology ENUM('FDM', 'SLA', 'SLS') NOT NULL,
                    build_volume VARCHAR(100),
                    supported_materials JSON,
                    status ENUM('idle', 'printing', 'maintenance', 'offline') DEFAULT 'idle',
                    current_job_id INT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (farm_id) REFERENCES print_farms(farm_id) ON DELETE CASCADE,
                    INDEX idx_farm_id (farm_id),
                    INDEX idx_status (status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Print jobs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS print_jobs (
                    job_id INT AUTO_INCREMENT PRIMARY KEY,
                    order_id VARCHAR(30) NOT NULL,
                    printer_id INT NOT NULL,
                    job_status ENUM('queued', 'printing', 'paused', 'completed', 'failed') DEFAULT 'queued',
                    progress_percentage INT DEFAULT 0 CHECK (progress_percentage BETWEEN 0 AND 100),
                    current_layer INT DEFAULT 0,
                    total_layers INT DEFAULT 0,
                    estimated_time_remaining INT,
                    temperature_data JSON,
                    started_at TIMESTAMP NULL,
                    completed_at TIMESTAMP NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE,
                    FOREIGN KEY (printer_id) REFERENCES printers(printer_id) ON DELETE CASCADE,
                    INDEX idx_order_id (order_id),
                    INDEX idx_printer_id_status (printer_id, job_status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Payments table for Razorpay
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS payments (
                    payment_id VARCHAR(50) PRIMARY KEY,
                    order_id VARCHAR(50) NOT NULL,
                    project_id VARCHAR(30) NOT NULL,
                    amount DECIMAL(10,2) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    razorpay_payment_id VARCHAR(50),
                    razorpay_order_id VARCHAR(50),
                    razorpay_signature VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
                    INDEX idx_project_id (project_id),
                    INDEX idx_order_id (order_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            # Contact messages table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS contact_messages (
                    message_id INT AUTO_INCREMENT PRIMARY KEY,
                    first_name VARCHAR(255) NOT NULL,
                    last_name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) NOT NULL,
                    contact_number VARCHAR(20),
                    message TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_email (email)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            ''')

            connection.commit()
        except Exception as e:
            connection.rollback()
            logger.error(f"Error creating tables: {e}")
        finally:
            cursor.close()
            connection.close()

def add_file_count_column():
    """Add file_count column to projects table if it does not exist."""
    connection = get_db_connection()
    if not connection:
        logger.error("Database connection failed for schema update.")
        return
    cursor = connection.cursor()
    try:
        cursor.execute("SHOW COLUMNS FROM projects LIKE 'file_count'")
        result = cursor.fetchone()
        if not result:
            cursor.execute("ALTER TABLE projects ADD COLUMN file_count INT DEFAULT 0")
            connection.commit()
            logger.info("Added 'file_count' column to 'projects' table.")
        else:
            logger.info("'file_count' column already exists in 'projects' table.")
    except Exception as e:
        logger.error(f"Error adding 'file_count' column: {e}")
    finally:
        cursor.close()
        connection.close()

# One-time schema fix (safe to leave, will do nothing if already fixed)
add_file_count_column()

# Add columns if not present (for migration)
def add_project_files_columns():
    connection = get_db_connection()
    if not connection:
        logger.error("Database connection failed for schema update.")
        return
    cursor = connection.cursor()
    try:
        cursor.execute("SHOW COLUMNS FROM project_files LIKE 'quality'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE project_files ADD COLUMN quality VARCHAR(50) DEFAULT NULL")
            logger.info("Added 'quality' column to 'project_files' table.")
        cursor.execute("SHOW COLUMNS FROM project_files LIKE 'file_description'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE project_files ADD COLUMN file_description TEXT DEFAULT NULL")
            logger.info("Added 'file_description' column to 'project_files' table.")
        connection.commit()
    except Exception as e:
        logger.error(f"Error adding columns to project_files: {e}")
    finally:
        cursor.close()
        connection.close()
add_project_files_columns()

def generate_otp():
    """Generate a 6-digit OTP."""
    return ''.join(random.choices(string.digits, k=6))

def send_otp_email(email, otp, is_admin=False):
    """Send OTP email for verification."""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['email']
        msg['To'] = email
        
        if is_admin:
            msg['Subject'] = "Unbound3D Admin - Email Verification OTP"
            body = f"""
            Welcome to Unbound3D Admin Panel!
            
            Your admin verification OTP is: {otp}
            
            This OTP will expire in 10 minutes.
            
            If you didn't request this, please contact the system administrator immediately.
            
            Best regards,
            Unbound3D Admin Team
            """
        else:
            msg['Subject'] = "Unbound3D - Email Verification OTP"
            body = f"""
            Welcome to Unbound3D!
            
            Your email verification OTP is: {otp}
            
            This OTP will expire in 10 minutes.
            
            If you didn't request this, please ignore this email.
            
            Best regards,
            Unbound3D Team
            """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['email'], EMAIL_CONFIG['password'])
        server.sendmail(EMAIL_CONFIG['email'], email, msg.as_string())
        server.quit()
        
        logger.info(f"OTP email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {email}: {e}")
        return False

def send_email(email, subject, body, is_admin=False):
    """Send general email."""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['email']
        msg['To'] = email
        msg['Subject'] = subject
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['email'], EMAIL_CONFIG['password'])
        server.sendmail(EMAIL_CONFIG['email'], email, msg.as_string())
        server.quit()
        
        logger.info(f"Email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Error sending email to {email}: {e}")
        return False

def send_quote_email(email, name, project_name, quote_price):
    """Send quote email to user."""
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_CONFIG['email']
        msg['To'] = email
        msg['Subject'] = f"Quote Ready for {project_name} - Unbound3D"
        
        body = f"""
        Dear {name},
        
        Great news! Your quote for "{project_name}" is ready.
        
        Quote Amount: ₹{quote_price}
        Valid Until: {(datetime.date.today() + datetime.timedelta(days=30)).strftime('%B %d, %Y')}
        
        Please log in to your dashboard to review and accept the quote.
        
        Best regards,
        Unbound3D Team
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP(EMAIL_CONFIG['smtp_server'], EMAIL_CONFIG['smtp_port'])
        server.starttls()
        server.login(EMAIL_CONFIG['email'], EMAIL_CONFIG['password'])
        server.sendmail(EMAIL_CONFIG['email'], email, msg.as_string())
        server.quit()
        
        logger.info(f"Quote email sent to {email}")
        return True
    except Exception as e:
        logger.error(f"Error sending quote email to {email}: {e}")
        return False

def insert_contact_message(first_name, last_name, email, contact_number, message):
    connection = get_db_connection()
    if not connection:
        return False
    cursor = connection.cursor()
    try:
        cursor.execute('''
            INSERT INTO contact_messages (first_name, last_name, email, contact_number, message)
            VALUES (%s, %s, %s, %s, %s)
        ''', (first_name, last_name, email, contact_number, message))
        connection.commit()
        return True
    except Exception as e:
        print('Error inserting contact message:', e)
        connection.rollback()
        return False
    finally:
        cursor.close()
        connection.close()

RAZORPAY_KEY_ID = 'rzp_live_SrimzLFuJGFzwZ'
RAZORPAY_KEY_SECRET = 'g1PBkCrLUfnGvzE4R2k8uHp6'

# Initialize tables on import
create_tables()
