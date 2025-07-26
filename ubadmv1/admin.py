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
        """Check if admin limit (3) is reached"""
        connection = self.get_connection()
        if not connection:
            return False, "Database connection failed"
        
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM admins WHERE is_active = TRUE")
            count = cursor.fetchone()[0]
            if count >= 3:
                return False, "Maximum admin limit (3) reached"
            return True, "Admin can be created"
        except Exception as e:
            logger.error(f"Error checking admin limit: {e}")
            return False, "Error checking admin limit"
        finally:
            cursor.close()
    
    def get_available_admin_types(self):
        """Get available admin types that haven't been registered yet"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor()
        try:
            # Get all admin types that exist
            cursor.execute("SELECT admin_type FROM admins WHERE is_active = TRUE")
            existing_types = [row[0] for row in cursor.fetchall()]
            
            # Return available types
            all_types = ['superadmin', 'techadmin', 'support']
            available_types = [admin_type for admin_type in all_types if admin_type not in existing_types]
            
            return available_types
        except Exception as e:
            logger.error(f"Error getting available admin types: {e}")
            return []
        finally:
            cursor.close()
    
    def register_admin(self, admin_type, name, designation, location, mobile, email, password):
        """Register a new admin"""
        # Validate inputs
        if admin_type not in ['superadmin', 'techadmin', 'support']:
            return False, "Invalid admin type. Must be 'superadmin', 'techadmin', or 'support'"
        
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
        """Get all orders with project and user details for printing and completed projects"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT o.*, p.project_name, p.status as project_status, u.name as user_name, u.email as user_email,
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
    
    def get_quoted_projects(self):
        """Get projects that have been quoted"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT p.project_id, p.project_name, p.amount as total_price, p.status,
                       u.name as user_name, u.email as user_email,
                       q.created_at as quoted_at, q.quote_id, q.breakdown, q.notes
                FROM projects p
                JOIN users u ON p.user_id = u.user_id
                LEFT JOIN quotes q ON p.project_id = q.project_id
                WHERE p.status = 'quoted'
                ORDER BY q.created_at DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting quoted projects: {e}")
            return []
        finally:
            cursor.close()
    
    def get_paid_projects(self):
        """Get projects that have been paid for"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT p.project_id, p.project_name, p.amount as total_price, p.status,
                       u.name as user_name, u.email as user_email,
                       q.created_at as quoted_at, q.quote_id,
                       py.payment_id, py.amount as paid_amount, py.status as payment_status,
                       py.created_at as payment_date, py.razorpay_payment_id
                FROM projects p
                JOIN users u ON p.user_id = u.user_id
                LEFT JOIN quotes q ON p.project_id = q.project_id
                LEFT JOIN payments py ON p.project_id = py.project_id
                WHERE (p.status = 'paid' OR p.status = 'printing') AND py.status = 'completed'
                ORDER BY py.created_at DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting paid projects: {e}")
            return []
        finally:
            cursor.close()
    
    def get_quote_details(self, project_id):
        """Get detailed quote information for a project"""
        connection = self.get_connection()
        if not connection:
            return {'success': False, 'error': 'Database connection failed'}
        
        cursor = connection.cursor(dictionary=True)
        try:
            # Get project, quote, and payment details
            cursor.execute('''
                SELECT p.*, u.name as user_name, u.email as user_email,
                       q.quote_id, q.total_price, q.breakdown, q.notes, 
                       q.created_at as quoted_at, q.valid_until,
                       py.payment_id, py.order_id, py.amount as paid_amount, py.status as payment_status,
                       py.created_at as payment_date, py.updated_at as payment_updated_at,
                       py.razorpay_payment_id, py.razorpay_order_id, py.razorpay_signature
                FROM projects p
                JOIN users u ON p.user_id = u.user_id
                LEFT JOIN quotes q ON p.project_id = q.project_id
                LEFT JOIN payments py ON p.project_id = py.project_id
                WHERE p.project_id = %s
            ''', (project_id,))
            
            project_data = cursor.fetchone()
            if not project_data:
                return {'success': False, 'error': 'Project not found'}
            
            # Get project files
            cursor.execute('''
                SELECT filename, file_size, file_type, created_at
                FROM project_files
                WHERE project_id = %s
            ''', (project_id,))
            
            files = cursor.fetchall()
            
            # Format the response
            result = {
                'success': True,
                'project': {
                    'project_id': project_data['project_id'],
                    'project_name': project_data['project_name'],
                    'user_name': project_data['user_name'],
                    'user_email': project_data['user_email'],
                    'purpose': project_data['purpose'],
                    'file_count': project_data['file_count'],
                    'status': project_data['status'],
                    'created_at': project_data['created_at'].strftime('%Y-%m-%d %H:%M') if project_data['created_at'] else None
                },
                'quote': {
                    'quote_id': project_data['quote_id'],
                    'total_price': float(project_data['total_price']) if project_data['total_price'] else 0,
                    'breakdown': project_data['breakdown'],
                    'notes': project_data['notes'],
                    'quoted_at': project_data['quoted_at'].strftime('%Y-%m-%d %H:%M') if project_data['quoted_at'] else None,
                    'valid_until': project_data['valid_until'].strftime('%Y-%m-%d') if project_data['valid_until'] else None
                },
                'payment': {
                    'payment_id': project_data['payment_id'],
                    'order_id': project_data['order_id'],
                    'paid_amount': float(project_data['paid_amount']) if project_data['paid_amount'] else 0,
                    'payment_status': project_data['payment_status'],
                    'payment_date': project_data['payment_date'].strftime('%Y-%m-%d %H:%M') if project_data['payment_date'] else None,
                    'payment_updated_at': project_data['payment_updated_at'].strftime('%Y-%m-%d %H:%M') if project_data['payment_updated_at'] else None,
                    'razorpay_payment_id': project_data['razorpay_payment_id'],
                    'razorpay_order_id': project_data['razorpay_order_id'],
                    'razorpay_signature': project_data['razorpay_signature']
                },
                'files': [
                    {
                        'file_name': f['filename'],
                        'file_size': round(f['file_size'] / 1024 / 1024, 2),  # MB
                        'file_type': f['file_type'],
                        'created_at': f['created_at'].strftime('%Y-%m-%d %H:%M') if f['created_at'] else None
                    }
                    for f in files
                ]
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting quote details: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            cursor.close()
    
    def get_project_files(self, project_id):
        """Get project files for a specific project"""
        connection = self.get_connection()
        if not connection:
            return {'success': False, 'error': 'Database connection failed'}
        
        cursor = connection.cursor(dictionary=True)
        try:
            # Get project details
            cursor.execute('''
                SELECT p.*, u.name as user_name, u.email as user_email
                FROM projects p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.project_id = %s
            ''', (project_id,))
            
            project_data = cursor.fetchone()
            if not project_data:
                return {'success': False, 'error': 'Project not found'}
            
            # Get project files with all relevant columns
            cursor.execute('''
                SELECT filename, file_size, file_type, created_at, file_description, print_type, material, color, infill_percentage, scale, painting, electroplating, post_processing, dimensions, volume, quality, is_configured, file_path
                FROM project_files
                WHERE project_id = %s
                ORDER BY created_at ASC
            ''', (project_id,))
            
            files = cursor.fetchall()
            
            # Format the response
            result = {
                'success': True,
                'project': {
                    'project_id': project_data['project_id'],
                    'project_name': project_data['project_name'],
                    'user_name': project_data['user_name'],
                    'user_email': project_data['user_email'],
                    'purpose': project_data['purpose'],
                    'file_count': project_data['file_count'],
                    'status': project_data['status'],
                    'created_at': project_data['created_at'].strftime('%Y-%m-%d %H:%M') if project_data['created_at'] else None
                },
                'files': [
                    {
                        'file_name': f['filename'],
                        'file_size': round(f['file_size'] / 1024 / 1024, 2),  # MB
                        'file_type': f['file_type'],
                        'created_at': f['created_at'].strftime('%Y-%m-%d %H:%M') if f['created_at'] else None,
                        'description': f['file_description'],
                        'print_type': f['print_type'],
                        'material': f['material'],
                        'color': f['color'],
                        'infill_percentage': f['infill_percentage'],
                        'scale': f['scale'],
                        'painting': f['painting'],
                        'electroplating': f['electroplating'],
                        'post_processing': f['post_processing'],
                        'dimensions': f['dimensions'],
                        'volume': f['volume'],
                        'quality': f['quality'],
                        'is_configured': f['is_configured'],
                        'file_path': f['file_path'],
                        'download_link': f"/static/uploads/{f['file_path']}" if f['file_path'] else None
                    }
                    for f in files
                ]
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting project files: {e}")
            return {'success': False, 'error': str(e)}
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
        """Get dashboard statistics with payment analytics"""
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
            
            # Payment Analytics - Monthly Revenue from Payments
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) FROM payments 
                WHERE status = 'completed' OR status = 'paid'
                AND MONTH(created_at) = MONTH(CURRENT_DATE())
                AND YEAR(created_at) = YEAR(CURRENT_DATE())
            ''')
            stats['monthly_revenue'] = float(cursor.fetchone()[0])
            
            # Total Revenue from Payments
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) FROM payments 
                WHERE status = 'completed' OR status = 'paid'
            ''')
            stats['total_revenue'] = float(cursor.fetchone()[0])
            
            # Total Orders
            cursor.execute("SELECT COUNT(*) FROM orders")
            stats['total_orders'] = cursor.fetchone()[0]
            
            # Completed Orders
            cursor.execute("SELECT COUNT(*) FROM orders WHERE order_status = 'completed'")
            stats['completed_orders'] = cursor.fetchone()[0]
            
            # Success Rate
            if stats['total_orders'] > 0:
                stats['success_rate'] = round((stats['completed_orders'] / stats['total_orders']) * 100, 1)
            else:
                stats['success_rate'] = 0
            
            # Payment Statistics
            cursor.execute('''
                SELECT COUNT(*) FROM payments 
                WHERE status = 'completed' OR status = 'paid'
            ''')
            stats['total_payments'] = cursor.fetchone()[0]
            
            # Pending Payments
            cursor.execute('''
                SELECT COUNT(*) FROM payments 
                WHERE status = 'created'
            ''')
            stats['pending_payments'] = cursor.fetchone()[0]
            
            # Average Payment Amount
            cursor.execute('''
                SELECT COALESCE(AVG(amount), 0) FROM payments 
                WHERE status = 'completed' OR status = 'paid'
            ''')
            stats['avg_payment_amount'] = float(cursor.fetchone()[0])
            
            # This Week's Revenue
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) FROM payments 
                WHERE status = 'completed' OR status = 'paid'
                AND created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
            ''')
            stats['weekly_revenue'] = float(cursor.fetchone()[0])
            
            # Today's Revenue
            cursor.execute('''
                SELECT COALESCE(SUM(amount), 0) FROM payments 
                WHERE status = 'completed' OR status = 'paid'
                AND DATE(created_at) = CURRENT_DATE()
            ''')
            stats['today_revenue'] = float(cursor.fetchone()[0])
            
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

    def update_project_status(self, project_id, status):
        """Update the status of a project (e.g., to 'printing')"""
        connection = self.get_connection()
        if not connection:
            return False, 'Database connection failed'
        cursor = connection.cursor()
        try:
            cursor.execute('UPDATE projects SET status = %s WHERE project_id = %s', (status, project_id))
            connection.commit()
            return True, None
        except Exception as e:
            connection.rollback()
            logger.error(f"Error updating project status: {e}")
            return False, str(e)
        finally:
            cursor.close()

    def get_all_payment_records(self):
        """Get all payment records with project and user details"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT py.*, p.project_name, u.name as user_name, u.email as user_email
                FROM payments py
                LEFT JOIN projects p ON py.project_id = p.project_id
                LEFT JOIN users u ON p.user_id = u.user_id
                ORDER BY py.created_at DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting payment records: {e}")
            return []
        finally:
            cursor.close()

    def get_chart_data(self):
        """Get data for charts and visualizations"""
        connection = self.get_connection()
        if not connection:
            return {}

        cursor = connection.cursor()
        try:
            chart_data = {}
            # Revenue trends for last 7 days
            cursor.execute('''
                SELECT DATE(created_at) as date, SUM(amount) as daily_revenue
                FROM payments
                WHERE (status = 'completed' OR status = 'paid')
                AND created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
                GROUP BY DATE(created_at)
                ORDER BY date
            ''')
            revenue_data = cursor.fetchall()
            dates = [str(row[0]) for row in revenue_data]
            revenues = [float(row[1]) for row in revenue_data]
            chart_data['revenue_trends'] = {'labels': dates, 'data': revenues}

            # Payment status distribution
            cursor.execute('''
                SELECT status, COUNT(*) as count, SUM(amount) as total_amount
                FROM payments
                GROUP BY status
            ''')
            payment_data = cursor.fetchall()
            payment_labels = [row[0] for row in payment_data]
            payment_counts = [int(row[1]) for row in payment_data]
            payment_amounts = [float(row[2]) for row in payment_data]
            
            # Assign colors based on status
            colors = []
            for status in payment_labels:
                if status in ['completed', 'paid']:
                    colors.append('#10b981')  # Green
                elif status == 'created':
                    colors.append('#f59e0b')  # Yellow
                else:
                    colors.append('#ef4444')  # Red
            
            chart_data['payment_distribution'] = {
                'labels': payment_labels, 
                'counts': payment_counts, 
                'amounts': payment_amounts, 
                'colors': colors
            }

            # Monthly revenue for last 6 months
            cursor.execute('''
                SELECT DATE_FORMAT(created_at, '%Y-%m') as month, SUM(amount) as monthly_revenue
                FROM payments
                WHERE (status = 'completed' OR status = 'paid')
                AND created_at >= DATE_SUB(CURRENT_DATE(), INTERVAL 6 MONTH)
                GROUP BY DATE_FORMAT(created_at, '%Y-%m')
                ORDER BY month
            ''')
            monthly_data = cursor.fetchall()
            monthly_labels = [row[0] for row in monthly_data]
            monthly_revenues = [float(row[1]) for row in monthly_data]
            chart_data['monthly_revenue'] = {'labels': monthly_labels, 'data': monthly_revenues}

            return chart_data
        except Exception as e:
            logger.error(f"Error getting chart data: {e}")
            return {}
        finally:
            cursor.close()
    
    def get_all_admins(self):
        """Get all admin users (superadmin only)"""
        connection = self.get_connection()
        if not connection:
            return []
        
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute('''
                SELECT admin_id, admin_type, name, designation, location, email, mobile, is_active, created_at
                FROM admins
                ORDER BY created_at DESC
            ''')
            return cursor.fetchall()
        except Exception as e:
            logger.error(f"Error getting all admins: {e}")
            return []
        finally:
            cursor.close()
    
    def remove_admin(self, admin_id):
        """Remove an admin (superadmin only)"""
        connection = self.get_connection()
        if not connection:
            return False, "Database connection failed"
        
        cursor = connection.cursor()
        try:
            # Check if admin exists and is not superadmin
            cursor.execute("SELECT admin_type FROM admins WHERE admin_id = %s", (admin_id,))
            admin = cursor.fetchone()
            if not admin:
                return False, "Admin not found"
            
            if admin[0] == 'superadmin':
                return False, "Cannot remove superadmin"
            
            # Deactivate admin instead of deleting
            cursor.execute("UPDATE admins SET is_active = FALSE WHERE admin_id = %s", (admin_id,))
            connection.commit()
            
            return True, "Admin removed successfully"
        except Exception as e:
            connection.rollback()
            logger.error(f"Error removing admin: {e}")
            return False, f"Failed to remove admin: {str(e)}"
        finally:
            cursor.close()
    
    def reply_to_message(self, message_id, reply_text, admin_data):
        """Send email reply to a contact message"""
        connection = self.get_connection()
        if not connection:
            return False, "Database connection failed"
        
        cursor = connection.cursor(dictionary=True)
        try:
            # Get the original message
            cursor.execute('''
                SELECT first_name, last_name, email, message
                FROM contact_messages
                WHERE id = %s
            ''', (message_id,))
            original_message = cursor.fetchone()
            
            if not original_message:
                return False, "Message not found"
            
            # Send email reply
            subject = f"Re: Your message to Unbound3D Support"
            body = f"""
Dear {original_message['first_name']} {original_message['last_name']},

Thank you for contacting Unbound3D Support.

{reply_text}

Best regards,
{admin_data['name']}
Unbound3D Support Team

---
Original message:
{original_message['message']}
            """
            
            # Send email using the new send_email function
            from database import send_email
            if send_email(original_message['email'], subject, body):
                return True, "Reply sent successfully"
            else:
                return False, "Failed to send email reply"
                
        except Exception as e:
            logger.error(f"Error replying to message: {e}")
            return False, f"Failed to send reply: {str(e)}"
        finally:
            cursor.close()

# Global admin manager instance
admin_manager = AdminManager()
