import mysql.connector
from mysql.connector import Error
import bcrypt
import datetime
import secrets
import re
from database import get_db_connection, generate_otp, send_otp_email, logger

class AdminManager:
    """Admin management class with full database access"""
    
    def __init__(self):
        self.connection = None
    
    def get_connection(self):
        """Get database connection"""
        if not self.connection or not self.connection.is_connected():
            self.connection = get_db_connection()
        return self.connection
    
    def validate_password(self, password):
        """Validate password strength"""
        if len(password) < 8:
            return False, "Password must be at least 8 characters long"
        if not re.search(r"[A-Z]", password):
            return False, "Password must contain at least one uppercase letter"
        if not re.search(r"[a-z]", password):
            return False, "Password must contain at least one lowercase letter"
        if not re.search(r"\d", password):
            return False, "Password must contain at least one digit"
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
            return False, "Password must contain at least one special character"
        return True, "Password is valid"
    
    def validate_mobile(self, mobile):
        """Validate mobile number (exactly 10 digits)"""
        if not re.match(r'^\+\d{1,4}\d{10}$', mobile):
            return False, "Mobile number must be in format +countrycode followed by exactly 10 digits"
        return True, "Mobile number is valid"
    
    def check_admin_limit(self):
        """Check if admin limit (2) is reached"""
        connection = self.get_connection()
        if not connection:
            return False, "Database connection failed"
        
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM admins WHERE is_active = TRUE")
            count = cursor.fetchone()[0]
            if count >= 2:
                return False, "Maximum admin limit (2) reached"
            return True, "Admin can be created"
        except Exception as e:
            logger.error(f"Error checking admin limit: {e}")
            return False, "Error checking admin limit"
        finally:
            cursor.close()
    
    def register_admin(self, admin_type, name, designation, location, mobile, email, password):
        """Register a new admin"""
        # Validate inputs
        if admin_type not in ['superadmin', 'techadmin']:
            return False, "Invalid admin type. Must be 'superadmin' or 'techadmin'"
        
        # Check admin limit
        can_create, message = self.check_admin_limit()
        if not can_create:
            return False, message
        
        # Validate password
        is_valid, password_message = self.validate_password(password)
        if not is_valid:
            return False, password_message
        
        # Validate mobile
        is_valid, mobile_message = self.validate_mobile(mobile)
        if not is_valid:
            return False, mobile_message
        
        connection = self.get_connection()
        if not connection:
            return False, "Database connection failed"
        
        cursor = connection.cursor()
        try:
            # Check if admin type already exists
            cursor.execute("SELECT admin_id FROM admins WHERE admin_type = %s", (admin_type,))
            if cursor.fetchone():
                return False, f"Admin type '{admin_type}' already exists"
            
            # Check if email already exists
            cursor.execute("SELECT admin_id FROM admins WHERE email = %s", (email,))
            if cursor.fetchone():
                return False, "Email already registered"
            
            # Hash password
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            # Insert admin
            cursor.execute('''
                INSERT INTO admins (admin_type, name, designation, location, mobile, email, password)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (admin_type, name, designation, location, mobile, email, hashed_password))
            
            connection.commit()
            
            # Send OTP for verification
            otp = generate_otp()
            self.store_admin_otp(email, otp)
            send_otp_email(email, otp, is_admin=True)
            
            return True, "Admin registered successfully. Please verify email with OTP."
            
        except Exception as e:
            connection.rollback()
            logger.error(f"Error registering admin: {e}")
            return False, f"Registration failed: {str(e)}"
        finally:
            cursor.close()
    
    def store_admin_otp(self, email, otp):
        """Store OTP for admin verification"""
        connection = self.get_connection()
        if not connection:
            return False
        
        cursor = connection.cursor()
        try:
            expires_at = datetime.datetime.now() + datetime.timedelta(minutes=10)
            cursor.execute('''
                INSERT INTO admin_otp_codes (email, otp_code, expires_at)
                VALUES (%s, %s, %s)
            ''', (email, otp, expires_at))
            connection.commit()
            return True
        except Exception as e:
            logger.error(f"Error storing admin OTP: {e}")
            return False
        finally:
            cursor.close()
    
    def verify_admin_otp(self, email, otp):
        """Verify admin OTP and activate account"""
        connection = self.get_connection()
        if not connection:
            return False, "Database connection failed"
        
        cursor = connection.cursor()
        try:
            # Check OTP
            cursor.execute('''
                SELECT otp_id FROM admin_otp_codes 
                WHERE email = %s AND otp_code = %s AND expires_at > NOW() AND is_used = FALSE
            ''', (email, otp))
            
            otp_record = cursor.fetchone()
            if not otp_record:
                return False, "Invalid or expired OTP"
            
            # Mark OTP as used
            cursor.execute('''
                UPDATE admin_otp_codes SET is_used = TRUE WHERE otp_id = %s
            ''', (otp_record[0],))
            
            # Activate admin account
            cursor.execute('''
                UPDATE admins SET is_verified = TRUE WHERE email = %s
            ''', (email,))
            
            connection.commit()
            return True, "Admin account verified successfully"
            
        except Exception as e:
            connection.rollback()
            logger.error(f"Error verifying admin OTP: {e}")
            return False, "OTP verification failed"
        finally:
            cursor.close()
    
    def admin_login(self, email, password):
        """Admin login"""
        connection = self.get_connection()
        if not connection:
            return False, "Database connection failed", None
        
        cursor = connection.cursor()
        try:
            cursor.execute('''
                SELECT admin_id, admin_type, name, password, is_verified, is_active 
                FROM admins WHERE email = %s
            ''', (email,))
            
            admin = cursor.fetchone()
            if not admin:
                return False, "Invalid email or password", None
            
            admin_id, admin_type, name, hashed_password, is_verified, is_active = admin
            
            if not is_active:
                return False, "Admin account is deactivated", None
            
            if not is_verified:
                return False, "Admin account not verified. Please verify with OTP.", None
            
            # Check password
            if not bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8')):
                return False, "Invalid email or password", None
            
            # Update last login
            cursor.execute('''
                UPDATE admins SET last_login = NOW() WHERE admin_id = %s
            ''', (admin_id,))
            
            # Create session
            session_id = secrets.token_urlsafe(32)
            expires_at = datetime.datetime.now() + datetime.timedelta(hours=24)
            
            cursor.execute('''
                INSERT INTO admin_sessions (session_id, admin_id, expires_at)
                VALUES (%s, %s, %s)
            ''', (session_id, admin_id, expires_at))
            
            connection.commit()
            
            admin_data = {
                'admin_id': admin_id,
                'admin_type': admin_type,
                'name': name,
                'email': email,
                'session_id': session_id
            }
            
            return True, "Login successful", admin_data
            
        except Exception as e:
            logger.error(f"Error in admin login: {e}")
            return False, "Login failed", None
        finally:
            cursor.close()
    
    def verify_admin_session(self, session_id):
        """Verify admin session"""
        connection = self.get_connection()
        if not connection:
            return False, None
        
        cursor = connection.cursor()
        try:
            cursor.execute('''
                SELECT a.admin_id, a.admin_type, a.name, a.email
                FROM admin_sessions s
                JOIN admins a ON s.admin_id = a.admin_id
                WHERE s.session_id = %s AND s.expires_at > NOW() AND a.is_active = TRUE
            ''', (session_id,))
            
            admin = cursor.fetchone()
            if admin:
                return True, {
                    'admin_id': admin[0],
                    'admin_type': admin[1],
                    'name': admin[2],
                    'email': admin[3]
                }
            return False, None
            
        except Exception as e:
            logger.error(f"Error verifying admin session: {e}")
            return False, None
        finally:
            cursor.close()
    
    def admin_logout(self, session_id):
        """Admin logout"""
        connection = self.get_connection()
        if not connection:
            return False
        
        cursor = connection.cursor()
        try:
            cursor.execute('DELETE FROM admin_sessions WHERE session_id = %s', (session_id,))
            connection.commit()
            return True
        except Exception as e:
            logger.error(f"Error in admin logout: {e}")
            return False
        finally:
            cursor.close()
    
    # Database CRUD Operations
    def get_all_users(self):
        """Get all users"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT user_id, name, designation, company, location, purpose, mobile, email, 
                       is_verified, ub_coins, created_at, updated_at
                FROM users WHERE user_id != 'GLOBAL'
                ORDER BY created_at DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting users: {e}")
            return []
        finally:
            cursor.close()
    
    def get_all_projects(self):
        """Get all projects with user details"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT p.*, u.name as user_name, u.email as user_email
                FROM projects p
                JOIN users u ON p.user_id = u.user_id
                ORDER BY p.created_at DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting projects: {e}")
            return []
        finally:
            cursor.close()
    
    def get_all_quotes(self):
        """Get all quotes with project and user details"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT q.*, p.project_name, p.status as project_status, 
                       u.name as user_name, u.email as user_email
                FROM quotes q
                JOIN projects p ON q.project_id = p.project_id
                JOIN users u ON q.user_id = u.user_id
                ORDER BY q.created_at DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting quotes: {e}")
            return []
        finally:
            cursor.close()
    
    def get_all_orders(self):
        """Get all orders with project and user details"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT o.*, p.project_name, u.name as user_name, u.email as user_email,
                       pf.farm_name, pr.printer_name
                FROM orders o
                LEFT JOIN projects p ON o.project_id = p.project_id
                JOIN users u ON o.user_id = u.user_id
                LEFT JOIN print_farms pf ON o.assigned_farm_id = pf.farm_id
                LEFT JOIN printers pr ON o.printer_id = pr.printer_id
                ORDER BY o.created_at DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting orders: {e}")
            return []
        finally:
            cursor.close()
    
    def get_pending_quotes(self):
        """Get projects pending quotes"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT p.*, u.name as user_name, u.email as user_email
                FROM projects p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.status = 'uploaded'
                ORDER BY p.created_at ASC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting pending quotes: {e}")
            return []
        finally:
            cursor.close()
    
    def create_quote(self, project_id, total_price, breakdown, notes=None):
        """Create a quote for a project"""
        connection = self.get_connection()
        if not connection:
            return False, "Database connection failed"
        
        cursor = connection.cursor()
        try:
            # Get project details
            cursor.execute('''
                SELECT user_id, purpose, file_count, consultation
                FROM projects WHERE project_id = %s
            ''', (project_id,))
            
            project = cursor.fetchone()
            if not project:
                return False, "Project not found"
            
            user_id, purpose, file_count, consultation = project
            
            # Generate quote ID
            from database import generate_custom_id
            current_year = str(datetime.datetime.now().year)
            quote_id = generate_custom_id('quote', current_year, user_id)
            
            # Calculate valid until date (30 days from now)
            valid_until = datetime.date.today() + datetime.timedelta(days=30)
            
            # Insert quote
            cursor.execute('''
                INSERT INTO quotes (quote_id, project_id, user_id, purpose, no_of_files, 
                                  consultation, total_price, breakdown, notes, valid_until)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (quote_id, project_id, user_id, purpose, file_count, consultation, 
                  total_price, breakdown, notes, valid_until))
            
            # Update project status
            cursor.execute('''
                UPDATE projects SET status = 'quoted', amount = %s WHERE project_id = %s
            ''', (total_price, project_id))
            
            connection.commit()
            
            # Send quote email
            cursor.execute('''
                SELECT u.name, u.email, p.project_name
                FROM users u
                JOIN projects p ON u.user_id = p.user_id
                WHERE p.project_id = %s
            ''', (project_id,))
            
            user_data = cursor.fetchone()
            if user_data:
                from database import send_quote_email
                send_quote_email(user_data[1], user_data[0], user_data[2], total_price)
            
            return True, "Quote created successfully"
            
        except Exception as e:
            connection.rollback()
            logger.error(f"Error creating quote: {e}")
            return False, f"Failed to create quote: {str(e)}"
        finally:
            cursor.close()
    
    def update_order_status(self, order_id, status):
        """Update order status"""
        connection = self.get_connection()
        if not connection:
            return False, "Database connection failed"
        
        cursor = connection.cursor()
        try:
            cursor.execute('''
                UPDATE orders SET order_status = %s WHERE order_id = %s
            ''', (status, order_id))
            
            connection.commit()
            return True, "Order status updated successfully"
            
        except Exception as e:
            connection.rollback()
            logger.error(f"Error updating order status: {e}")
            return False, f"Failed to update order status: {str(e)}"
        finally:
            cursor.close()
    
    def get_dashboard_stats(self):
        """Get dashboard statistics"""
        connection = self.get_connection()
        if not connection:
            return {}
        
        cursor = connection.cursor()
        try:
            stats = {}
            
            # Pending quotes
            cursor.execute("SELECT COUNT(*) FROM projects WHERE status = 'uploaded'")
            stats['pending_quotes'] = cursor.fetchone()[0]
            
            # Active orders
            cursor.execute("SELECT COUNT(*) FROM orders WHERE order_status IN ('approved', 'printing')")
            stats['active_orders'] = cursor.fetchone()[0]
            
            # Total users
            cursor.execute("SELECT COUNT(*) FROM users WHERE user_id != 'GLOBAL'")
            stats['total_users'] = cursor.fetchone()[0]
            
            # Monthly revenue
            cursor.execute('''
                SELECT COALESCE(SUM(total_amount), 0) FROM orders 
                WHERE payment_status = 'completed' 
                AND MONTH(created_at) = MONTH(CURRENT_DATE())
                AND YEAR(created_at) = YEAR(CURRENT_DATE())
            ''')
            stats['monthly_revenue'] = float(cursor.fetchone()[0])
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {e}")
            return {}
        finally:
            cursor.close()
    
    def get_contact_messages(self):
        """Get all contact messages"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT * FROM contact_messages 
                ORDER BY created_at DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting contact messages: {e}")
            return []
        finally:
            cursor.close()
    
    def delete_user(self, user_id):
        """Delete a user"""
        connection = self.get_connection()
        if not connection:
            return False, "Database connection failed"
        
        cursor = connection.cursor()
        try:
            cursor.execute('DELETE FROM users WHERE user_id = %s', (user_id,))
            connection.commit()
            return True, "User deleted successfully"
        except Exception as e:
            connection.rollback()
            logger.error(f"Error deleting user: {e}")
            return False, f"Failed to delete user: {str(e)}"
        finally:
            cursor.close()
    
    def delete_project(self, project_id):
        """Delete a project"""
        connection = self.get_connection()
        if not connection:
            return False, "Database connection failed"
        
        cursor = connection.cursor()
        try:
            cursor.execute('DELETE FROM projects WHERE project_id = %s', (project_id,))
            connection.commit()
            return True, "Project deleted successfully"
        except Exception as e:
            connection.rollback()
            logger.error(f"Error deleting project: {e}")
            return False, f"Failed to delete project: {str(e)}"
        finally:
            cursor.close()

    def get_project_details(self, project_id):
        """Get project details and associated files by project_id"""
        connection = self.get_connection()
        if not connection:
            return None, "Database connection failed"
        cursor = connection.cursor(dictionary=True)
        try:
            # Fetch project and user info
            cursor.execute('''
                SELECT p.*, u.name as user_name, u.email as user_email
                FROM projects p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.project_id = %s
            ''', (project_id,))
            project = cursor.fetchone()
            if not project:
                return None, "Project not found"
            # Fetch project files
            cursor.execute('''
                SELECT filename, file_size, file_type, created_at
                FROM project_files
                WHERE project_id = %s
            ''', (project_id,))
            files = cursor.fetchall()
            # Format file info
            file_list = [
                {
                    'file_name': f['filename'],
                    'file_size': round(f['file_size'] / 1024 / 1024, 2),  # MB
                    'file_type': f['file_type'],
                    'created_at': f['created_at'].strftime('%Y-%m-%d %H:%M') if f['created_at'] else None
                }
                for f in files
            ]
            # Compose result
            result = {
                'project_id': project['project_id'],
                'project_name': project['project_name'],
                'user_name': project['user_name'],
                'purpose': project['purpose'],
                'file_count': project['file_count'],
                'created_at': project['created_at'].strftime('%Y-%m-%d %H:%M') if project['created_at'] else None,
                'files': file_list
            }
            return result, None
        except Exception as e:
            logger.error(f"Error fetching project details: {e}")
            return None, str(e)
        finally:
            cursor.close()

# Global admin manager instance
admin_manager = AdminManager()
