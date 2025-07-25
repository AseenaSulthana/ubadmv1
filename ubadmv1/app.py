from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import json
from admin import admin_manager
from database import insert_contact_message, create_tables

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this-in-production'

# Initialize database tables
create_tables()

# Main routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/signin')
def signin():
    return render_template('signin.html')

# Admin routes
@app.route('/admin/signin')
def admin_signin():
    return render_template('admin-signin.html')

@app.route('/admin/signup')
def admin_signup():
    return render_template('admin-signup.html')

@app.route('/admin/otp')
def admin_otp():
    return render_template('admin-otp.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    return render_template('admin-dashboard.html')

# Admin API routes
@app.route('/admin/signin', methods=['POST'])
def admin_signin_post():
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'success': False, 'error': 'Email and password are required'})
        
        success, message, admin_data = admin_manager.admin_login(email, password)
        
        if success:
            session['admin_session_id'] = admin_data['session_id']
            session['admin_id'] = admin_data['admin_id']
            return jsonify({'success': True, 'message': message})
        else:
            return jsonify({'success': False, 'error': message})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/signup', methods=['POST'])
def admin_signup_post():
    try:
        data = request.get_json()
        
        required_fields = ['admin_type', 'name', 'designation', 'location', 'mobile', 'email', 'password']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field.replace("_", " ").title()} is required'})
        
        success, message = admin_manager.register_admin(
            data['admin_type'],
            data['name'],
            data['designation'],
            data['location'],
            data['mobile'],
            data['email'],
            data['password']
        )
        
        return jsonify({'success': success, 'error': message if not success else None})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/verify-otp', methods=['POST'])
def admin_verify_otp():
    try:
        data = request.get_json()
        email = data.get('email')
        otp = data.get('otp')
        
        if not email or not otp:
            return jsonify({'success': False, 'error': 'Email and OTP are required'})
        
        success, message = admin_manager.verify_admin_otp(email, otp)
        return jsonify({'success': success, 'error': message if not success else None})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/resend-otp', methods=['POST'])
def admin_resend_otp():
    try:
        data = request.get_json()
        email = data.get('email')
        
        if not email:
            return jsonify({'success': False, 'error': 'Email is required'})
        
        from database import generate_otp, send_otp_email
        otp = generate_otp()
        
        if admin_manager.store_admin_otp(email, otp):
            if send_otp_email(email, otp, is_admin=True):
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'Failed to send OTP email'})
        else:
            return jsonify({'success': False, 'error': 'Failed to store OTP'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/check-auth')
def admin_check_auth():
    try:
        session_id = session.get('admin_session_id')
        if not session_id:
            return jsonify({'success': False, 'error': 'No session found'})
        
        success, admin_data = admin_manager.verify_admin_session(session_id)
        if success:
            return jsonify({'success': True, 'admin': admin_data})
        else:
            session.clear()
            return jsonify({'success': False, 'error': 'Invalid session'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    try:
        session_id = session.get('admin_session_id')
        if session_id:
            admin_manager.admin_logout(session_id)
        session.clear()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Admin API endpoints for dashboard data
@app.route('/admin/api/stats')
def admin_api_stats():
    try:
        session_id = session.get('admin_session_id')
        if not session_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        success, admin_data = admin_manager.verify_admin_session(session_id)
        if not success:
            return jsonify({'error': 'Unauthorized'}), 401
        
        stats = admin_manager.get_dashboard_stats()
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/pending-quotes')
def admin_api_pending_quotes():
    try:
        session_id = session.get('admin_session_id')
        if not session_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        success, admin_data = admin_manager.verify_admin_session(session_id)
        if not success:
            return jsonify({'error': 'Unauthorized'}), 401
        
        quotes = admin_manager.get_pending_quotes()
        return jsonify(quotes)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/active-orders')
def admin_api_active_orders():
    try:
        session_id = session.get('admin_session_id')
        if not session_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        success, admin_data = admin_manager.verify_admin_session(session_id)
        if not success:
            return jsonify({'error': 'Unauthorized'}), 401
        
        orders = admin_manager.get_all_orders()
        active_orders = [order for order in orders if order['order_status'] in ['approved', 'printing']]
        return jsonify(active_orders)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/orders')
def admin_api_orders():
    try:
        session_id = session.get('admin_session_id')
        if not session_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        success, admin_data = admin_manager.verify_admin_session(session_id)
        if not success:
            return jsonify({'error': 'Unauthorized'}), 401
        
        orders = admin_manager.get_all_orders()
        return jsonify(orders)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/users')
def admin_api_users():
    try:
        session_id = session.get('admin_session_id')
        if not session_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        success, admin_data = admin_manager.verify_admin_session(session_id)
        if not success:
            return jsonify({'error': 'Unauthorized'}), 401
        
        users = admin_manager.get_all_users()
        return jsonify(users)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/messages')
def admin_api_messages():
    try:
        session_id = session.get('admin_session_id')
        if not session_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        success, admin_data = admin_manager.verify_admin_session(session_id)
        if not success:
            return jsonify({'error':  'Unauthorized'}), 401
        
        messages = admin_manager.get_contact_messages()
        return jsonify(messages)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/api/create-quote', methods=['POST'])
def admin_api_create_quote():
    try:
        session_id = session.get('admin_session_id')
        if not session_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        success, admin_data = admin_manager.verify_admin_session(session_id)
        if not success:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        project_id = data.get('project_id')
        total_price = data.get('total_price')
        breakdown = data.get('breakdown')
        notes = data.get('notes')
        
        if not project_id or not total_price:
            return jsonify({'success': False, 'error': 'Project ID and total price are required'})
        
        success, message = admin_manager.create_quote(project_id, total_price, breakdown, notes)
        return jsonify({'success': success, 'error': message if not success else None})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/api/update-order-status', methods=['POST'])
def admin_api_update_order_status():
    try:
        session_id = session.get('admin_session_id')
        if not session_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        success, admin_data = admin_manager.verify_admin_session(session_id)
        if not success:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        order_id = data.get('order_id')
        status = data.get('status')
        
        if not order_id or not status:
            return jsonify({'success': False, 'error': 'Order ID and status are required'})
        
        success, message = admin_manager.update_order_status(order_id, status)
        return jsonify({'success': success, 'error': message if not success else None})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/api/delete-user', methods=['POST'])
def admin_api_delete_user():
    try:
        session_id = session.get('admin_session_id')
        if not session_id:
            return jsonify({'error': 'Unauthorized'}), 401
        
        success, admin_data = admin_manager.verify_admin_session(session_id)
        if not success:
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = request.get_json()
        user_id = data.get('user_id')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'User ID is required'})
        
        success, message = admin_manager.delete_user(user_id)
        return jsonify({'success': success, 'error': message if not success else None})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/admin/api/project-details')
def admin_api_project_details():
    project_id = request.args.get('project_id')
    if not project_id:
        return jsonify({'success': False, 'error': 'Missing project_id'})
    project, error = admin_manager.get_project_details(project_id)
    if error:
        return jsonify({'success': False, 'error': error})
    return jsonify({'success': True, 'project': project})

# Contact form API
@app.route('/api/contact-message', methods=['POST'])
def api_contact_message():
    try:
        data = request.get_json()
        
        required_fields = ['first_name', 'last_name', 'email', 'message']
        for field in required_fields:
            if not data.get(field):
                return jsonify({'success': False, 'error': f'{field.replace("_", " ").title()} is required'})
        
        success = insert_contact_message(
            data['first_name'],
            data['last_name'],
            data['email'],
            data.get('contact_number'),
            data['message']
        )
        
        if success:
            return jsonify({'success': True, 'message': 'Message sent successfully'})
        else:
            return jsonify({'success': False, 'error': 'Failed to send message'})
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
