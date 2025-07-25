-- Unbound3D Platform: Database Schema Creation Script
-- Run this script in your MySQL client to create all necessary tables

-- Users table
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
    ub_coins INT DEFAULT 5, -- UB Coins, default 5 for all users
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE INDEX idx_email (email),
    INDEX idx_purpose (purpose)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Insert dummy GLOBAL user (replace <hashed_password> with a bcrypt hash if needed)
INSERT IGNORE INTO users (user_id, name, email, password, purpose, is_verified)
VALUES ('GLOBAL', 'Global Counter', 'global@unbound3d.com', '<hashed_password>', 'industry', TRUE);

-- ID counters table
CREATE TABLE IF NOT EXISTS id_counters (
    counter_type ENUM('client', 'project', 'quote', 'order') NOT NULL,
    year CHAR(4) NOT NULL,
    user_id VARCHAR(20),
    counter INT DEFAULT 0,
    PRIMARY KEY (counter_type, year, user_id(20)),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- OTP codes table
CREATE TABLE IF NOT EXISTS otp_codes (
    otp_id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    otp_code VARCHAR(6) NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    is_used BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_email_otp (email, otp_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Projects table (revised)
CREATE TABLE IF NOT EXISTS projects (
    project_id VARCHAR(30) PRIMARY KEY,
    user_id VARCHAR(20) NOT NULL,
    project_name VARCHAR(255) NOT NULL,
    file_count INT DEFAULT 0,
    description TEXT,
    purpose ENUM('personal', 'industry', 'functional', 'ideal') NOT NULL,
    consultation BOOLEAN DEFAULT FALSE,
    amount DECIMAL(10,2) DEFAULT 0.0,
    status ENUM('uploaded','quoted','approved','printing','completed','delivered','paid') DEFAULT 'uploaded',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    INDEX idx_user_id_status (user_id, status),
    INDEX idx_project_name (project_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Project Files table (revised)
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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(project_id) ON DELETE CASCADE,
    INDEX idx_project_id (project_id),
    INDEX idx_file_id (file_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Quotes table
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Orders table
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Products table
CREATE TABLE IF NOT EXISTS products (
    product_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category ENUM('printer', 'filament', 'accessory') NOT NULL,
    description TEXT,
    price DECIMAL(10,2) NOT NULL,
    stock_quantity INT DEFAULT 0,
    specifications JSON,
    images JSON,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_category (category),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Cart table
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Print farms table
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Printers table
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Print jobs table
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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS contact_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    contact_number VARCHAR(30),
    message TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
